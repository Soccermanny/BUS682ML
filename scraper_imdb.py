import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from google.cloud import storage
import io
import os
import re

# Thread-safe printing
print_lock = Lock()

def extract_rating_value(text):
    if not text:
        return None
    if re.fullmatch(r"\s*/\s*10\s*", text):
        return None

    match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", text)
    if match:
        return match.group(1)

    numbers = re.findall(r"\d+(?:\.\d+)?", text)
    for number in numbers:
        try:
            value = float(number)
        except ValueError:
            continue
        if 0 < value <= 10:
            return number

    return None

def extract_year(soup):
    """Extract release year from an IMDb page.
    Method 1: JSON-LD datePublished field (most reliable).
    Method 2: <title> tag — typically 'Movie Title (YEAR) - IMDb'.
    """
    # Method 1: JSON-LD structured data
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or '')
            date = data.get('datePublished', '')
            if date:
                m = re.search(r'(\d{4})', date)
                if m:
                    return m.group(1)
        except (json.JSONDecodeError, TypeError):
            continue

    # Method 2: page <title> tag
    title_tag = soup.find('title')
    if title_tag:
        m = re.search(r'\((\d{4})\)', title_tag.get_text())
        if m:
            return m.group(1)

    return ""


def scrape_imdb_rating(imdb_id, index, total):
    """Scrape rating and release year for a single IMDb ID"""
    url = f"https://www.imdb.com/title/{imdb_id}"
    attempts = 0
    max_attempts = 3
    rating = ""
    year = ""
    
    while attempts < max_attempts:
        attempts += 1
        try:
            # Fetch the page
            response = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            # Brief delay to be polite to IMDb servers
            time.sleep(1.0)
            
            soup = BeautifulSoup(response.text, "html.parser")
            rating = ""

            # Method 1 (most reliable): JSON-LD structured data
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    ld = json.loads(script.string or "")
                    rv = ld.get("aggregateRating", {}).get("ratingValue")
                    if rv is not None:
                        rating = str(rv)
                        break
                except Exception:
                    pass

            # Method 2: data-testid div (current IMDb DOM as of 2025-2026)
            if not rating:
                rating_div = soup.find("div", {"data-testid": "hero-rating-bar__aggregate-rating__score"})
                if rating_div:
                    rating_span = rating_div.find("span")
                    if rating_span:
                        rating = rating_span.get_text(strip=True)

            # Method 3: aria-label "View User Ratings" anchor (e.g. "8.7/102.2M")
            if not rating:
                a = soup.find("a", {"aria-label": "View User Ratings"})
                if a:
                    m = re.search(r"(\d+(?:\.\d+)?)/", a.get_text(strip=True))
                    if m:
                        rating = m.group(1)

            # Method 4: any span whose text is a bare number between 1–10
            if not rating:
                for span in soup.find_all("span"):
                    t = span.get_text(strip=True)
                    try:
                        v = float(t)
                        if 1.0 <= v <= 10.0 and re.fullmatch(r"\d+\.\d", t):
                            rating = t
                            break
                    except ValueError:
                        pass

            if not rating:
                rating = "Not found"

            # Normalize rating to a single number (strip vote counts like "5.1/1027K")
            if rating not in ["Not found", "Error"]:
                normalized = extract_rating_value(rating)
                if normalized:
                    rating = normalized
                else:
                    rating = "Not found"

            # Extract release year
            if not year:
                year = extract_year(soup)

            if rating != "Not found":
                break
            if attempts < max_attempts:
                time.sleep(2.0)
        except Exception as e:
            rating = "Error"
            status = f"❌ {str(e)[:30]}"
            if attempts < max_attempts:
                time.sleep(2.0)
            continue
    
    status = f"✅ {rating}"
    if attempts > 1 and rating not in ["Not found", "Error"]:
        status += f" (attempt {attempts})"
    
    # Thread-safe printing
    with print_lock:
        print(f"[{index}/{total}] {imdb_id} ... {status}")
    
    return {
        "IMDb ID": imdb_id,
        "URL": url,
        "User Rating": rating,
        "year": year
    }

def download_from_gcs(bucket_name, source_blob_name):
    """Download file from Google Cloud Storage"""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    
    # Download to memory
    content = blob.download_as_bytes()
    return pd.read_csv(io.BytesIO(content))

def upload_to_gcs(bucket_name, destination_blob_name, dataframe):
    """Upload DataFrame to Google Cloud Storage as Excel"""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    
    # Write to memory buffer
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        dataframe.to_excel(writer, index=False, sheet_name='IMDb Ratings')
        
        worksheet = writer.sheets['IMDb Ratings']
        for idx, col in enumerate(dataframe.columns):
            max_length = max(
                dataframe[col].astype(str).apply(len).max(),
                len(col)
            ) + 2
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_length, 50)
        
        for cell in worksheet[1]:
            cell.font = cell.font.copy(bold=True)
    
    buffer.seek(0)
    blob.upload_from_file(buffer, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    print(f"\n✅ Uploaded to gs://{bucket_name}/{destination_blob_name}")

if __name__ == "__main__":
    # GCP Configuration - SET THESE AS ENVIRONMENT VARIABLES
    BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME', 'your-bucket-name')  # ✏️ Change this
    INPUT_FILE = os.environ.get('INPUT_FILE', 'input/movies.csv')  # ✏️ Path in bucket
    OUTPUT_FILE = os.environ.get('OUTPUT_FILE', 'output/imdb_ratings_output.xlsx')  # ✏️ Output path
    MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '5'))  # ✏️ Reduced to 5 with 3.5s delay
    
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Input: {INPUT_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Threads: {MAX_WORKERS}")
    print(f"Delay per request: 3.5 seconds\n")
    
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
    print(f"Each request waits 3.5 seconds for page load\n")
    
    SAVE_INTERVAL = 1000  # Save progress to GCS every N completed movies

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_id = {
            executor.submit(scrape_imdb_rating, imdb_id, i+1, len(imdb_ids)): imdb_id 
            for i, imdb_id in enumerate(imdb_ids)
        }
        
        for future in as_completed(future_to_id):
            result = future.result()
            results.append(result)

            # Incremental save every SAVE_INTERVAL movies
            if len(results) % SAVE_INTERVAL == 0:
                partial_df = pd.DataFrame(results)
                partial_df['sort_key'] = partial_df['IMDb ID'].apply(lambda x: imdb_ids.index(x))
                partial_df = partial_df.sort_values('sort_key').drop('sort_key', axis=1).reset_index(drop=True)
                partial_final = df.copy()
                partial_final = partial_final[partial_final[imdb_id_column].astype(str).str.strip().isin(partial_df['IMDb ID'])].copy()
                partial_final['User Rating'] = partial_df['User Rating'].values
                partial_final['year'] = partial_df['year'].values
                checkpoint_file = OUTPUT_FILE.replace('.xlsx', f'_checkpoint_{len(results)}.xlsx')
                try:
                    upload_to_gcs(BUCKET_NAME, checkpoint_file, partial_final)
                    print(f"[Checkpoint] Saved {len(results)}/{len(imdb_ids)} to {checkpoint_file}")
                except Exception as e:
                    print(f"[Checkpoint] Save failed: {e}")

    elapsed_time = time.time() - start_time
    
    # Sort results
    results_df = pd.DataFrame(results)
    results_df['sort_key'] = results_df['IMDb ID'].apply(lambda x: imdb_ids.index(x))
    results_df = results_df.sort_values('sort_key').drop('sort_key', axis=1).reset_index(drop=True)
    
    # Merge with original data
    final_df = df.copy()
    final_df["User Rating"] = results_df["User Rating"]
    final_df["year"] = results_df["year"]
    
    print("\n" + "="*70)
    print("PREVIEW OF RESULTS:")
    print("="*70)
    print(final_df.head(10).to_string(index=False))
    
    # Upload to GCS
    print("\nUploading results to Google Cloud Storage...")
    upload_to_gcs(BUCKET_NAME, OUTPUT_FILE, final_df)
    
    print(f"\n📊 Total movies processed: {len(final_df)}")
    print(f"✅ Ratings found: {len(final_df[final_df['User Rating'].str.contains('/', na=False)])}")
    print(f"⏱️ Time taken: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
    print(f"⚡ Speed: {len(final_df)/elapsed_time:.2f} movies/second")