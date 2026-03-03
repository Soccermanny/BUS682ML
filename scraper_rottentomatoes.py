import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from google.cloud import storage
from deep_translator import GoogleTranslator
from langdetect import detect, LangDetectException
import io
import os
import re

# Thread-safe printing
print_lock = Lock()

def clean_movie_title_for_url(title):
    """Convert movie title to Rotten Tomatoes URL format"""
    # Remove special characters and replace spaces with underscores
    # Convert to lowercase
    clean = title.lower()
    # Remove apostrophes, quotes, and other special chars
    clean = re.sub(r"[''\"`:;,!?&]", '', clean)
    # Replace spaces and dashes with underscores
    clean = re.sub(r'[\s\-]+', '_', clean)
    # Remove any remaining non-alphanumeric characters except underscores
    clean = re.sub(r'[^a-z0-9_]', '', clean)
    # Remove leading/trailing underscores
    clean = clean.strip('_')
    return clean

def is_imdb_id(value):
    """Check if a value looks like an IMDb title ID (e.g., tt1234567)."""
    if value is None:
        return False
    return bool(re.fullmatch(r'tt\d+', str(value).strip().lower()))

def translate_to_english(title):
    """Detect language and translate to English if not already English."""
    try:
        lang = detect(title)
        if lang == 'en':
            return title
        translated = GoogleTranslator(source='auto', target='en').translate(title)
        return translated if translated else title
    except (LangDetectException, Exception):
        return title

def extract_rt_scores(soup):
    """Extract Tomatometer and Popcornmeter scores from RT page.

    RT renders score-board via JS web components (not in static HTML).
    The static HTML places each movie's scores inside <media-scorecard> tags
    as <rt-text> elements. 'More Like This' scores appear inside
    <tile-poster-card> inside <carousel-slider> — we exclude those entirely.
    """
    tomatometer = None
    popcornmeter = None

    try:
        # Method 1: rt-text elements whose immediate parent is <media-scorecard>
        # First occurrence = Tomatometer, second = Popcornmeter (audience/popcorn)
        # This is specific to the current movie and excludes all sidebar/related content.
        scorecard_scores = []
        for el in soup.find_all('rt-text'):
            if el.parent and el.parent.name == 'media-scorecard':
                text = el.get_text(strip=True).replace('%', '')
                if text.isdigit():
                    scorecard_scores.append(int(text))
        if len(scorecard_scores) >= 1:
            tomatometer = scorecard_scores[0]
        if len(scorecard_scores) >= 2:
            popcornmeter = scorecard_scores[1]

        # Method 2: JSON-LD structured data (fallback for tomatometer only)
        if tomatometer is None:
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.string or '')
                    entries = data if isinstance(data, list) else [data]
                    for entry in entries:
                        if entry.get('@type') not in ('Movie', 'TVSeries', 'VideoObject'):
                            continue
                        agg = entry.get('aggregateRating', {})
                        raw = agg.get('ratingValue') or agg.get('averageRating')
                        if raw is not None:
                            val = float(str(raw))
                            tomatometer = int(val) if val > 10 else int(val * 10)
                        break
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue

    except Exception as e:
        print(f"Error extracting scores: {e}")

    return tomatometer, popcornmeter

def scrape_rotten_tomatoes(movie_title, release_year, index, total):
    """Scrape Rotten Tomatoes scores for a movie with retry logic"""

    if is_imdb_id(movie_title):
        with print_lock:
            print(f"[{index}/{total}] {movie_title} ({release_year}) ... ⚠️ Skipped (IMDb ID provided instead of movie name)")
        return {
            "Movie Title": movie_title,
            "Tomatometer": "NF",
            "Popcornmeter": "NF",
            "RT URL": "NF"
        }
    
    # Clean title for URL
    url_title = clean_movie_title_for_url(movie_title)
    
    # Try without year first
    base_url = f"https://www.rottentomatoes.com/m/{url_title}"
    
    tomatometer_score = None
    popcornmeter_score = None
    url_used = base_url
    attempts = 0
    max_attempts = 2  # Try without year, then with year
    
    while attempts < max_attempts and (tomatometer_score is None or popcornmeter_score is None):
        attempts += 1
        
        if attempts == 1:
            # First attempt: without year
            url = base_url
        else:
            # Second attempt: with year
            if release_year:
                url = f"{base_url}_{release_year}"
                url_used = url
            else:
                # No year available, can't try again
                break
        
        try:
            response = requests.get(url, timeout=15, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            
            # Wait 5 seconds
            time.sleep(5.0)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                tomatometer, popcornmeter = extract_rt_scores(soup)
                
                if tomatometer is not None or popcornmeter is not None:
                    tomatometer_score = tomatometer
                    popcornmeter_score = popcornmeter
                    break
            
            elif response.status_code == 404 and attempts < max_attempts:
                with print_lock:
                    print(f"[{index}/{total}] {movie_title} ... ⚠️ Not found at {url}, trying with year")
        
        except Exception as e:
            with print_lock:
                print(f"[{index}/{total}] {movie_title} ... ❌ Error: {str(e)[:30]}")
    
    # Convert percentages to scores out of 10
    tomatometer_out_of_10 = ""
    popcornmeter_out_of_10 = ""
    
    if tomatometer_score is not None:
        # Convert percentage (0-100) to score out of 10
        score = tomatometer_score / 10
        tomatometer_out_of_10 = str(int(score)) if score == int(score) else str(round(score, 1))
    else:
        tomatometer_out_of_10 = "NF"

    if popcornmeter_score is not None:
        # Convert percentage (0-100) to score out of 10
        score = popcornmeter_score / 10
        popcornmeter_out_of_10 = str(int(score)) if score == int(score) else str(round(score, 1))
    else:
        popcornmeter_out_of_10 = "NF"
    
    status = f"✅ Tomato: {tomatometer_out_of_10} | Popcorn: {popcornmeter_out_of_10}"
    
    with print_lock:
        print(f"[{index}/{total}] {movie_title} ({release_year}) ... {status}")
    
    return {
        "Movie Title": movie_title,
        "Tomatometer": tomatometer_out_of_10,
        "Popcornmeter": popcornmeter_out_of_10,
        "RT URL": url_used
    }

def download_from_gcs(bucket_name, source_blob_name):
    """Download file from Google Cloud Storage"""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(source_blob_name)
    
    # Determine file type
    if source_blob_name.endswith('.xlsx'):
        content = blob.download_as_bytes()
        return pd.read_excel(io.BytesIO(content))
    else:
        content = blob.download_as_bytes()
        return pd.read_csv(io.BytesIO(content))

def upload_to_gcs(bucket_name, destination_blob_name, dataframe):
    """Upload DataFrame to Google Cloud Storage as Excel"""
    storage_client = storage.Client()
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(destination_blob_name)
    
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        dataframe.to_excel(writer, index=False, sheet_name='RT Scores')
        
        worksheet = writer.sheets['RT Scores']
        
        # Auto-adjust column widths
        for idx, col in enumerate(dataframe.columns):
            max_length = max(
                dataframe[col].astype(str).apply(len).max(),
                len(col)
            ) + 2
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_length, 50)
        
        # Bold header row
        for cell in worksheet[1]:
            cell.font = cell.font.copy(bold=True)
    
    buffer.seek(0)
    blob.upload_from_file(buffer, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    print(f"\n✅ Uploaded to gs://{bucket_name}/{destination_blob_name}")

if __name__ == "__main__":
    # GCP Configuration
    BUCKET_NAME = os.environ.get('GCS_BUCKET_NAME', 'imdb-scraper-bucket')
    INPUT_FILE = os.environ.get('INPUT_FILE', 'output/imdb_ratings_output.xlsx')
    OUTPUT_FILE = os.environ.get('OUTPUT_FILE', 'output/rotten_tomatoes_scores.xlsx')
    MAX_WORKERS = int(os.environ.get('MAX_WORKERS', '10'))
    
    print(f"Bucket: {BUCKET_NAME}")
    print(f"Input: {INPUT_FILE}")
    print(f"Output: {OUTPUT_FILE}")
    print(f"Threads: {MAX_WORKERS}")
    print(f"Delay per request: 5.0 seconds\n")
    
    # Download input file from GCS (IMDb results)
    print("Downloading IMDb results from Google Cloud Storage...")
    df = download_from_gcs(BUCKET_NAME, INPUT_FILE)
    
    print(f"Columns in input file: {list(df.columns)}\n")
    print(f"Found {len(df)} movies to scrape from Rotten Tomatoes\n")
    
    # Prepare movie list with titles and years
    movies = []
    for _, row in df.iterrows():
        # Get movie title from known title columns; ignore IMDb IDs like tt1234567
        title = None
        title_columns = ['movie_name', 'Movie Title', 'Title', 'title', 'primaryTitle', 'primary_title']
        for column_name in title_columns:
            if column_name in df.columns and pd.notna(row[column_name]):
                candidate = str(row[column_name]).strip()
                if candidate and candidate.lower() != 'nan' and not is_imdb_id(candidate):
                    title = candidate
                    break
        
        # If still no valid movie-name title, skip this row
        if not title or title == 'nan':
            continue
        
        # Get release year
        year = ""
        if 'Release Year' in df.columns:
            year = str(row['Release Year']) if pd.notna(row['Release Year']) else ""
        elif 'Year' in df.columns:
            year = str(row['Year']) if pd.notna(row['Year']) else ""
        elif 'release_year' in df.columns:
            year = str(row['release_year']) if pd.notna(row['release_year']) else ""
        elif 'year' in df.columns:
            year = str(row['year']) if pd.notna(row['year']) else ""
        
        # Remove .0 from year if present (e.g., "2024.0" -> "2024")
        if year and '.' in year:
            year = year.split('.')[0]
        
        # Translate non-English titles to English for RT URL matching
        title_en = translate_to_english(title)
        movies.append({"title": title_en, "original_title": title, "year": year})
    
    print(f"Successfully parsed {len(movies)} movie titles\n")
    
    start_time = time.time()
    results = []
    
    print(f"Starting Rotten Tomatoes scrape with {MAX_WORKERS} concurrent threads...\n")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_movie = {
            executor.submit(scrape_rotten_tomatoes, movie["title"], movie["year"], i+1, len(movies)): movie
            for i, movie in enumerate(movies)
        }
        
        for future in as_completed(future_to_movie):
            result = future.result()
            results.append(result)
    
    elapsed_time = time.time() - start_time
    
    # Sort results to match original order
    results_df = pd.DataFrame(results)
    results_df['sort_key'] = results_df['Movie Title'].apply(
        lambda x: next((i for i, m in enumerate(movies) if m["title"] == x), -1)
    )
    results_df = results_df.sort_values('sort_key').drop('sort_key', axis=1).reset_index(drop=True)
    
    # Merge with original IMDb data
    final_df = df.copy()
    final_df["Tomatometer"] = results_df["Tomatometer"]
    final_df["Popcornmeter"] = results_df["Popcornmeter"]
    final_df["RT URL"] = results_df["RT URL"]
    
    print("\n" + "="*70)
    print("PREVIEW OF RESULTS:")
    print("="*70)
    print(final_df.head(10).to_string(index=False))
    
    # Count statistics
    tomato_found = len(final_df[final_df['Tomatometer'] != 'NF'])
    popcorn_found = len(final_df[final_df['Popcornmeter'] != 'NF'])
    
    # Upload to GCS
    print("\nUploading results to Google Cloud Storage...")
    upload_to_gcs(BUCKET_NAME, OUTPUT_FILE, final_df)
    
    print(f"\n📊 Total movies processed: {len(final_df)}")
    print(f"🍅 Tomatometer scores found: {tomato_found}")
    print(f"🍿 Popcornmeter scores found: {popcorn_found}")
    print(f"⏱️ Time taken: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
    print(f"⚡ Speed: {len(final_df)/elapsed_time:.2f} movies/second")