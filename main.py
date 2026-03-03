import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from google.cloud import storage
from datetime import datetime
import io
import os
import re

# Thread-safe printing
print_lock = Lock()

def extract_movie_title_from_soup(soup):
    """Extract movie title from IMDb page"""
    title = ""
    
    # Method 1: Look for the main title in h1
    h1 = soup.find("h1", class_="sc-7c7b364-0")
    if h1:
        title_elem = h1.find("span")
        if title_elem:
            title = title_elem.get_text(strip=True)
    
    # Method 2: Search for title in meta tag
    if not title:
        meta_tag = soup.find("meta", property="og:title")
        if meta_tag:
            title = meta_tag.get("content", "").strip()
            # Remove release year if present (e.g., "Movie Title (2023)" -> "Movie Title")
            title = re.sub(r'\s*\(\d{4}\)\s*$', '', title)
    
    # Method 3: Search for title attribute in page
    if not title:
        for span in soup.find_all("span"):
            text = span.get_text(strip=True)
            if len(text) > 3 and len(text) < 200 and not any(char.isdigit() for char in text[:10]):
                title = text
                break
    
    return title.strip() if title else ""

def extract_rating_from_soup(soup):
    """Extract rating from BeautifulSoup object"""
    rating = ""
    
    # Method 1: Find rating span
    rating_elem = soup.find("span", class_="sc-eb51e184-1")
    if rating_elem:
        rating = rating_elem.get_text(strip=True)
    
    # Method 2: Search for /10 pattern
    if not rating:
        for span in soup.find_all("span"):
            text = span.get_text(strip=True)
            if "/10" in text and len(text) < 10:
                rating = text
                break
    
    # Method 3: Check rating bar
    if not rating:
        rating_div = soup.find("div", {"data-testid": "hero-rating-bar__aggregate-rating__score"})
        if rating_div:
            rating_span = rating_div.find("span")
            if rating_span:
                rating = rating_span.get_text(strip=True)
    
    if rating:
        if re.fullmatch(r"\s*/\s*10\s*", rating):
            return None

        match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", rating)
        if match:
            return match.group(1)

        numbers = re.findall(r"\d+(?:\.\d+)?", rating)
        for number in numbers:
            try:
                value = float(number)
            except ValueError:
                continue
            if 0 < value <= 10:
                return number

    return None

def scrape_imdb_rating_and_code(imdb_id, index, total):
    """Scrape rating, MPAA/Hays Code, and release date for a single IMDb ID with retry logic"""
    url = f"https://www.imdb.com/title/{imdb_id}"
    
    rating_number = None
    soup = None
    attempts = 0
    max_attempts = 3
    
    # Try up to 3 times to get the rating
    while attempts < max_attempts and rating_number is None:
        attempts += 1
        
        try:
            # Fetch the page
            response = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            # Wait 5 seconds for page to fully load
            time.sleep(5.0)
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Try to extract rating
            rating_number = extract_rating_from_soup(soup)
            
            if rating_number is None and attempts < max_attempts:
                with print_lock:
                    print(f"[{index}/{total}] {imdb_id} ... ⚠️ Rating not found, retry {attempts}/{max_attempts}")
                # Wait a bit longer before retry
                time.sleep(2.0)
            
        except Exception as e:
            with print_lock:
                print(f"[{index}/{total}] {imdb_id} ... ❌ Error on attempt {attempts}: {str(e)[:30]}")
            if attempts < max_attempts:
                time.sleep(2.0)
            soup = None
    
    # If still no rating after 3 attempts, mark as N/A
    if rating_number is None:
        rating_number = "N/A"
    
    # Now extract other data (only need to do this once, using last successful soup)
    code_rating = "Error"
    release_month = ""
    release_day = ""
    release_year = ""
    
    if soup:
        try:
            # === EXTRACT RELEASE DATE ===
            release_date = None
            
            # Look for release date in various places
            for a_tag in soup.find_all("a", href=True):
                if "/releaseinfo" in a_tag.get("href", ""):
                    date_text = a_tag.get_text(strip=True)
                    try:
                        # Try to parse dates like "January 15, 1939"
                        if "," in date_text:
                            release_date = datetime.strptime(date_text, "%B %d, %Y")
                            release_month = release_date.strftime("%B")
                            release_day = str(release_date.day)
                            release_year = str(release_date.year)
                            break
                        # Try "15 January 1939" format
                        elif len(date_text.split()) == 3:
                            parts = date_text.split()
                            if parts[1].isalpha():
                                release_date = datetime.strptime(date_text, "%d %B %Y")
                            else:
                                release_date = datetime.strptime(date_text, "%B %d %Y")
                            release_month = release_date.strftime("%B")
                            release_day = str(release_date.day)
                            release_year = str(release_date.year)
                            break
                        # Just a year like "1939"
                        elif len(date_text) == 4 and date_text.isdigit():
                            release_date = datetime(int(date_text), 1, 1)
                            release_year = date_text
                            break
                    except:
                        pass
            
            # Fallback: search page text for year only
            if not release_year:
                for element in soup.find_all(string=True):
                    text = str(element).strip()
                    if len(text) == 4 and text.isdigit():
                        year = int(text)
                        if 1900 <= year <= 2030:
                            release_date = datetime(year, 1, 1)
                            release_year = text
                            break
            
            # === EXTRACT MPAA/HAYS CODE ===
            code_rating = ""
            
            # Look for MPAA rating
            mpaa_found = False
            for span in soup.find_all("span"):
                text = span.get_text(strip=True)
                # Common MPAA ratings
                if text in ["G", "PG", "PG-13", "R", "NC-17", "X", "M", "GP", "Approved", "Passed"]:
                    code_rating = text
                    mpaa_found = True
                    break
            
            # Alternative: Look for "MPAA" label
            if not mpaa_found:
                mpaa_label = soup.find("span", string="MPAA")
                if mpaa_label:
                    parent = mpaa_label.parent
                    for span in parent.find_all("span"):
                        text = span.get_text(strip=True)
                        if text and text != "MPAA":
                            code_rating = text
                            mpaa_found = True
                            break
            
            # If no MPAA rating found, check release date
            if not mpaa_found:
                if release_date:
                    # MPAA rating system started November 1, 1968
                    mpaa_start_date = datetime(1968, 11, 1)
                    
                    if release_date < mpaa_start_date:
                        code_rating = "Pre-Code"
                    else:
                        code_rating = "N/A"
                else:
                    # If we couldn't determine release date
                    code_rating = "Unknown Date"
        
        except Exception as e:
            code_rating = "Error"
    
    status = f"✅ {rating_number} | {code_rating}"
    if release_year:
        status += f" | {release_year}"
    if attempts > 1 and rating_number != "N/A":
        status += f" (attempt {attempts})"
    
    # Thread-safe printing
    with print_lock:
        print(f"[{index}/{total}] {imdb_id} ... {status}")
    
    # Extract movie title
    movie_title = ""
    if soup:
        movie_title = extract_movie_title_from_soup(soup)
    
    return {
        "IMDb ID": imdb_id,
        "Movie Title": movie_title,
        "URL": url,
        "User Rating": rating_number,
        "MPAA/Hays Code": code_rating,
        "Release Month": release_month,
        "Release Day": release_day,
        "Release Year": release_year
    }

def download_from_gcs(bucket_name, source_blob_name):
    """Download file from Google Cloud Storage"""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    
    content = blob.download_as_bytes()
    return pd.read_csv(io.BytesIO(content))

def upload_to_gcs(bucket_name, destination_blob_name, dataframe):
    """Upload DataFrame to Google Cloud Storage as Excel"""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        dataframe.to_excel(writer, index=False, sheet_name='IMDb Ratings')
        
        worksheet = writer.sheets['IMDb Ratings']
        
        # Set column widths
        column_widths = {
            'A': 15,  # IMDb ID
            'B': 50,  # URL
            'C': 15,  # User Rating
            'D': 20,  # MPAA/Hays Code
            'E': 15,  # Release Month
            'F': 12,  # Release Day
            'G': 12   # Release Year
        }
        
        for col_letter, width in column_widths.items():
            worksheet.column_dimensions[col_letter].width = width
        
        # Bold header row
        for cell in worksheet[1]:
            cell.font = cell.font.copy(bold=True)
    
    buffer.seek(0)
    blob.upload_from_file(buffer, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    print(f"\n✅ Uploaded to gs://{bucket_name}/{destination_blob_name}")

if __name__ == "__main__":
    # GCP Configuration
    BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME', 'your-bucket-name')
    INPUT_FILE = os.environ.get('INPUT_FILE', 'input/movies.csv')
    OUTPUT_FILE = os.environ.get('OUTPUT_FILE', 'output/imdb_ratings_output.xlsx')
    MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '10'))
    
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Input: {INPUT_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Threads: {MAX_WORKERS}")
    print(f"Delay per request: 5.0 seconds")
    print(f"Retry attempts for failed ratings: 3\n")
    
    # Download input CSV from GCS
    print("Downloading CSV from Google Cloud Storage...")
    df = download_from_gcs(BUCKET_NAME, INPUT_FILE)
    
    imdb_id_column = df.columns[0]
    print(f"Using column: '{imdb_id_column}'")
    print(f"Found {len(df)} movies to scrape\n")
    
    imdb_ids = [str(row[imdb_id_column]).strip() for _, row in df.iterrows()]
    
    start_time = time.time()
    results = []
    
    print(f"Starting scrape with {MAX_WORKERS} concurrent threads...")
    print(f"Movies with failed ratings will be retried up to 3 times\n")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_id = {
            executor.submit(scrape_imdb_rating_and_code, imdb_id, i+1, len(imdb_ids)): imdb_id 
            for i, imdb_id in enumerate(imdb_ids)
        }
        
        for future in as_completed(future_to_id):
            result = future.result()
            results.append(result)
    
    elapsed_time = time.time() - start_time
    
    # Sort results
    results_df = pd.DataFrame(results)
    results_df['sort_key'] = results_df['IMDb ID'].apply(lambda x: imdb_ids.index(x))
    results_df = results_df.sort_values('sort_key').drop('sort_key', axis=1).reset_index(drop=True)
    
    # Merge with original data
    final_df = df.copy()
    final_df["User Rating"] = results_df["User Rating"]
    final_df["MPAA/Hays Code"] = results_df["MPAA/Hays Code"]
    final_df["Release Month"] = results_df["Release Month"]
    final_df["Release Day"] = results_df["Release Day"]
    final_df["Release Year"] = results_df["Release Year"]
    
    print("\n" + "="*70)
    print("PREVIEW OF RESULTS:")
    print("="*70)
    print(final_df.head(10).to_string(index=False))
    
    # Count statistics
    na_ratings = len(final_df[final_df['User Rating'] == 'N/A'])
    found_ratings = len(final_df[final_df['User Rating'] != 'N/A'])
    
    # Upload to GCS
    print("\nUploading results to Google Cloud Storage...")
    upload_to_gcs(BUCKET_NAME, OUTPUT_FILE, final_df)
    
    print(f"\n📊 Total movies processed: {len(final_df)}")
    print(f"✅ Ratings found: {found_ratings}")
    print(f"⚠️ Ratings N/A (after 3 attempts): {na_ratings}")
    print(f"⏱️ Time taken: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
    print(f"⚡ Speed: {len(final_df)/elapsed_time:.2f} movies/second")
