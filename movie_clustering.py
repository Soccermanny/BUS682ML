"""
Movie Clustering with UMAP + HDBSCAN
=====================================
Data sources (all free beyond TMDB key):
  - TMDB         → ratings, runtime, popularity, genres
  - Wikipedia    → full plot summaries
  - Wikidata     → country, decade, source material, director nationality
  - Google Translate → auto-detects + translates non-English titles

TMDB Lookup — 3-layer fallback per movie:
  Layer 1 → Search by tt/IMDb code       (if movie_id column contains tt number)
  Layer 2 → Search by movie_name + year  (original title)
  Layer 3 → Search by translated_title + year (Google Translate → English)
  Each layer waits up to 5 seconds and retries once before falling back.

Performance:
  All API fetches (TMDB, Wikipedia, Wikidata, Translation) run with
  parallel workers using ThreadPoolExecutor so your full dataset is
  processed concurrently rather than one at a time.

CSV format required:
  movie_id | movie_name | genre | year
  (movie_id can be a tt number OR any internal ID)

Requirements:
    pip install requests pandas numpy scikit-learn sentence-transformers umap-learn hdbscan plotly tqdm
"""

import os
import re
import time
import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import numpy as np
import pandas as pd
from tqdm import tqdm
from sklearn.preprocessing import StandardScaler
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from deep_translator import GoogleTranslator
from langdetect import detect, LangDetectException
import umap
import hdbscan
import plotly.express as px
import plotly.graph_objects as go
try:
    from google.cloud import storage as _gcs
    _GCS_AVAILABLE = True
except ImportError:
    _GCS_AVAILABLE = False


# ╔══════════════════════════════════════════════════════════════╗
# ║                  USER CONFIGURATION                          ║
# ║         ← THE ONLY SECTION YOU NEED TO EDIT →               ║
# ╚══════════════════════════════════════════════════════════════╝

# ┌──────────────────────────────────────────────────────────────┐
# │  INSERT #1 — TMDB API KEY                                    │
# │  Get yours free at: https://www.themoviedb.org/settings/api  │
# └──────────────────────────────────────────────────────────────┘
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "PASTE_YOUR_TMDB_KEY_HERE")

# ┌──────────────────────────────────────────────────────────────┐
# │  INSERT #2 — YOUR CSV FILENAME                               │
# │  Must be in the same folder as this script.                  │
# │  Required columns: movie_id | movie_name | genre | year      │
# │  movie_id can be a tt number (tt1234567) or any internal ID  │
# └──────────────────────────────────────────────────────────────┘
MOVIES_CSV = os.getenv("MOVIES_CSV", "genre_data.csv")

# ── GCP / GCS (set when running on Cloud Run) ─────────────────
# Leave blank for local use; set on Cloud Run job env vars.
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")
INPUT_BLOB      = os.getenv("INPUT_BLOB",  "output/imdb_ratings_output.xlsx")
OUTPUT_PREFIX   = os.getenv("OUTPUT_PREFIX", "output/clustering")

# ╔══════════════════════════════════════════════════════════════╗
# ║              TUNING PARAMETERS (optional)                    ║
# ║   These work well as-is — only change if results are off     ║
# ╚══════════════════════════════════════════════════════════════╝

# How closely a title must match a TMDB result (0.0–1.0).
# Lower to 0.75 if too many movies go unmatched.
# Raise to 0.92 if you're getting wrong-movie matches.
TITLE_MATCH_THRESHOLD = 0.85

# ── Parallel workers ─────────────────────────────────────────
# Number of simultaneous API calls per fetch stage.
# 10 is the safe ceiling — matches IMDb/RT scraper caps.
# Lower to 5 if you hit TMDB or Wikidata rate limits.
WORKERS = 10

# ── Per-request timeout and retry delay ──────────────────────
# How many seconds to wait for an API response before retrying.
REQUEST_TIMEOUT = 10
# How long to wait (seconds) before a single retry on timeout/error.
RETRY_DELAY = 5

# ── UMAP ─────────────────────────────────────────────────────
UMAP_N_NEIGHBORS = 15
UMAP_MIN_DIST    = 0.0
UMAP_METRIC      = "cosine"

# ── HDBSCAN ──────────────────────────────────────────────────
HDBSCAN_MIN_CLUSTER_SIZE = 15
HDBSCAN_MIN_SAMPLES      = 5

# ── Embedding dimensions (TF-IDF + SVD) ──────────────────────
# Higher = more expressive, slower. 300 is a good balance.
EMBEDDING_DIMS = 300

# ── Output filenames ──────────────────────────────────────────
_LOCAL_DIR         = "/tmp" if GCS_BUCKET_NAME else "."
OUTPUT_HTML        = os.path.join(_LOCAL_DIR, "movie_clusters.html")
OUTPUT_CSV         = os.path.join(_LOCAL_DIR, "movie_clusters.csv")

# ── Cache filenames (auto-created on first run) ───────────────
CACHE_TRANSLATIONS = os.path.join(_LOCAL_DIR, "cache_translations.json")
CACHE_TMDB         = os.path.join(_LOCAL_DIR, "cache_tmdb.json")
CACHE_WIKIPEDIA    = os.path.join(_LOCAL_DIR, "cache_wikipedia.json")
CACHE_WIKIDATA     = os.path.join(_LOCAL_DIR, "cache_wikidata.json")

# ── API base URLs (do not change) ────────────────────────────
TMDB_BASE       = "https://api.themoviedb.org/3"
WIKI_API        = "https://en.wikipedia.org/w/api.php"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"


# ══════════════════════════════════════════════════════════════
# THREAD-SAFE CACHE HELPERS
# ══════════════════════════════════════════════════════════════

_cache_lock = threading.RLock()
# Thread-safe printing (matches scraper_rottentomatoes.py pattern)
print_lock = threading.Lock()


# ══════════════════════════════════════════════════════════════
# GCS HELPERS
# ══════════════════════════════════════════════════════════════

def _gcs_client():
    return _gcs.Client()


def gcs_download_to_file(bucket_name: str, blob_name: str, local_path: str):
    """Download a GCS object to a local path."""
    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    blob   = bucket.blob(blob_name)
    blob.download_to_filename(local_path)
    print(f"  Downloaded gs://{bucket_name}/{blob_name} -> {local_path}")


def gcs_upload_from_file(bucket_name: str, blob_name: str, local_path: str):
    """Upload a local file to GCS."""
    client = _gcs_client()
    bucket = client.bucket(bucket_name)
    blob   = bucket.blob(blob_name)
    blob.upload_from_filename(local_path)
    print(f"  Uploaded {local_path} -> gs://{bucket_name}/{blob_name}")


def load_cache(path: str) -> dict:
    with _cache_lock:
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        return json.loads(content)
            except (json.JSONDecodeError, ValueError, OSError):
                pass
    return {}


def save_cache(path: str, data: dict):
    with _cache_lock:
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


def update_cache(path: str, key: str, value) -> dict:
    """Thread-safe single-key update — loads, updates, saves."""
    with _cache_lock:
        cache = load_cache(path)
        cache[key] = value
        with open(path, "w") as f:
            json.dump(cache, f, indent=2)
        return cache


# ══════════════════════════════════════════════════════════════
# GENERAL HELPERS
# ══════════════════════════════════════════════════════════════

def normalize_title(title: str) -> str:
    t = title.lower().strip()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\b(the|a|an)\b", "", t)
    return re.sub(r"\s+", " ", t).strip()


def title_similarity(a: str, b: str) -> float:
    a, b = normalize_title(a), normalize_title(b)
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    longer       = max(len(a), len(b))
    matches      = sum(ca == cb for ca, cb in zip(a, b))
    words_a      = set(a.split())
    words_b      = set(b.split())
    word_overlap = len(words_a & words_b) / max(len(words_a), len(words_b), 1)
    return (matches / longer * 0.5) + (word_overlap * 0.5)


def make_cache_key(movie_name: str, year) -> str:
    return f"{normalize_title(str(movie_name))}::{year}"


def is_imdb_id(value: str) -> bool:
    """Returns True if the value looks like an IMDb tt number."""
    if value is None:
        return False
    return bool(re.fullmatch(r'tt\d+', str(value).strip().lower()))


def robust_get(url: str, params: dict = None, json_body: dict = None,
               headers: dict = None, method: str = "GET") -> requests.Response | None:
    """
    Makes an HTTP request with one automatic retry after RETRY_DELAY seconds.
    Returns the Response object or None on failure.
    """
    for attempt in range(2):
        try:
            if method == "POST":
                r = requests.post(url, params=params, json=json_body,
                                  headers=headers, timeout=REQUEST_TIMEOUT)
            else:
                r = requests.get(url, params=params,
                                 headers=headers, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if attempt == 0:
                # First failure — wait RETRY_DELAY seconds then try once more
                time.sleep(RETRY_DELAY)
            else:
                return None
    return None


# ══════════════════════════════════════════════════════════════
# STEP 1A — Load CSV
# ══════════════════════════════════════════════════════════════

def load_csv(filepath: str) -> pd.DataFrame:
    if not os.path.exists(filepath):
        raise FileNotFoundError(
            f"\n'{filepath}' not found.\n"
            f"   Place your input file in the same folder as this script."
        )

    ext = os.path.splitext(filepath)[1].lower()
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(filepath)
    else:
        df = pd.read_csv(filepath)

    # Normalise IMDb scraper output column names
    df.columns = [c.strip() for c in df.columns]
    if "User Rating" in df.columns and "imdb_rating" not in df.columns:
        df = df.rename(columns={"User Rating": "imdb_rating"})

    required = {"movie_name", "genre"}
    missing  = required - set(df.columns)
    if missing:
        raise ValueError(
            f"\n❌ CSV missing columns: {missing}\n"
            f"   Required: movie_name, genre\n"
            f"   Recommended: movie_id (tt codes), year"
        )

    df["movie_name"] = df["movie_name"].astype(str).str.strip()

    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    else:
        print("  ⚠ No 'year' column — year matching disabled (less accurate)")
        df["year"] = pd.NA

    if "movie_id" not in df.columns:
        df["movie_id"] = ""

    # Normalize tt codes
    df["movie_id"] = df["movie_id"].astype(str).str.strip()
    df["movie_id"] = df["movie_id"].apply(
        lambda x: ("tt" + x) if re.match(r"^\d{7,8}$", x) else x
    )

    tt_count = df["movie_id"].apply(is_imdb_id).sum()
    print(f"  Loaded {len(df)} movies from {filepath}")
    print(f"  tt/IMDb codes found: {tt_count} / {len(df)}")
    return df


# ══════════════════════════════════════════════════════════════
# STEP 1B — Language detection + translation
# ══════════════════════════════════════════════════════════════

def detect_and_translate(title: str) -> tuple:
    """
    Detects the language of a title using langdetect.
    If not English, translates to English via deep-translator (free, no API key).
    Returns: (translated_title, detected_language_code, was_translated)
    Matches the translation approach used in scraper_rottentomatoes.py.
    """
    try:
        lang_code = detect(title)
    except LangDetectException:
        return title, "unknown", False

    if lang_code == "en":
        return title, "en", False

    try:
        translated = GoogleTranslator(source="auto", target="en").translate(title)
        if translated:
            return translated, lang_code, True
    except Exception:
        pass

    return title, lang_code, False


def _translate_worker(row) -> dict:
    title = row["movie_name"]
    cache = load_cache(CACHE_TRANSLATIONS)
    if title in cache:
        return {"title": title, **cache[title]}

    trans, lang, was_trans = detect_and_translate(title)
    entry = {
        "translated_title":  trans,
        "detected_language": lang,
        "was_translated":    was_trans,
    }
    update_cache(CACHE_TRANSLATIONS, title, entry)
    return {"title": title, **entry}


def translate_all_titles(csv_df: pd.DataFrame) -> pd.DataFrame:
    """
    Runs language detection + translation for every title in parallel.
    Results cached in cache_translations.json.
    """
    rows    = [row for _, row in csv_df.iterrows()]
    results = {}

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(_translate_worker, row): row["movie_name"]
                   for row in rows}
        for future in tqdm(as_completed(futures),
                           total=len(futures), desc="  Translating"):
            res = future.result()
            results[res["title"]] = res

    translated_titles, detected_languages, was_translated_flags = [], [], []
    for _, row in csv_df.iterrows():
        entry = results.get(row["movie_name"], {})
        translated_titles.append(entry.get("translated_title", row["movie_name"]))
        detected_languages.append(entry.get("detected_language", "en"))
        was_translated_flags.append(entry.get("was_translated", False))

        if entry.get("was_translated"):
            print(f"  [{entry.get('detected_language','?').upper()}] "
                  f"'{row['movie_name']}' → '{entry.get('translated_title','')}'")

    df                      = csv_df.copy()
    df["translated_title"]  = translated_titles
    df["detected_language"] = detected_languages
    df["was_translated"]    = was_translated_flags

    n_foreign = sum(was_translated_flags)
    print(f"  Foreign-language titles: {n_foreign} / {len(df)}")
    return df


# ══════════════════════════════════════════════════════════════
# STEP 1C — TMDB: 3-layer lookup
# ══════════════════════════════════════════════════════════════

def _tmdb_by_tt(tt_code: str) -> dict:
    """
    Layer 1: Look up a movie using its IMDb tt number via TMDB /find endpoint.
    Returns the first movie_result or {}.
    """
    r = robust_get(
        f"{TMDB_BASE}/find/{tt_code}",
        params={"api_key": TMDB_API_KEY, "external_source": "imdb_id"}
    )
    if not r:
        return {}
    results = r.json().get("movie_results", [])
    return results[0] if results else {}


def _tmdb_by_title(query_title: str, year) -> dict:
    """
    Layers 2 & 3: Search TMDB by title + year.
    Accepts the first candidate that passes title similarity + year checks.
    """
    params = {
        "api_key":  TMDB_API_KEY,
        "query":    query_title,
        "language": "en-US",
        "page":     1,
    }
    if pd.notna(year):
        params["year"] = int(year)

    r = robust_get(f"{TMDB_BASE}/search/movie", params=params)
    if not r:
        return {}

    for result in r.json().get("results", [])[:5]:
        tmdb_title = result.get("title", "")
        tmdb_date  = result.get("release_date", "")
        tmdb_year  = int(tmdb_date[:4]) if tmdb_date and len(tmdb_date) >= 4 else None

        if title_similarity(query_title, tmdb_title) < TITLE_MATCH_THRESHOLD:
            continue
        if pd.notna(year) and tmdb_year is not None and int(year) != tmdb_year:
            continue
        return result

    return {}


def _tmdb_details(tmdb_id: int) -> dict:
    r = robust_get(
        f"{TMDB_BASE}/movie/{tmdb_id}",
        params={"api_key": TMDB_API_KEY}
    )
    return r.json() if r else {}


def _tmdb_worker(row) -> tuple:
    """
    Runs the 3-layer TMDB lookup for a single movie row.
    Returns (cache_key, result_dict, layer_used)

    Layer 1 — tt code   (only if movie_id is a valid tt number)
    Layer 2 — original movie_name + year
    Layer 3 — translated_title + year  (only if translation occurred)
    """
    name       = row["movie_name"]
    year       = row.get("year", pd.NA)
    movie_id   = str(row.get("movie_id", ""))
    translated = row.get("translated_title", name)
    key        = make_cache_key(name, year)

    # Check cache first
    cache = load_cache(CACHE_TMDB)
    if key in cache:
        return key, cache[key], "cached"

    match      = {}
    layer_used = "none"

    # ── Layer 1: tt code ─────────────────────────────────────
    if is_imdb_id(movie_id):
        match = _tmdb_by_tt(movie_id)
        if match:
            layer_used = f"tt:{movie_id}"

    # ── Layer 2: original title + year ───────────────────────
    if not match:
        match = _tmdb_by_title(name, year)
        if match:
            layer_used = "title+year"

    # ── Layer 3: translated title + year ─────────────────────
    if not match and translated != name:
        match = _tmdb_by_title(translated, year)
        if match:
            layer_used = f"translated:{translated}"

    if not match:
        update_cache(CACHE_TMDB, key, {})
        return key, {}, "none"

    details = _tmdb_details(match["id"])
    record  = {
        "tmdb_id":       match["id"],
        "title":         details.get("title", name),
        "overview":      details.get("overview", ""),
        "vote_average":  details.get("vote_average"),
        "vote_count":    details.get("vote_count"),
        "popularity":    details.get("popularity"),
        "runtime":       details.get("runtime"),
        "release_date":  details.get("release_date", ""),
        "tmdb_genres":   [g["name"] for g in details.get("genres", [])],
        "matched_title": match.get("title", ""),
        "lookup_layer":  layer_used,
    }
    update_cache(CACHE_TMDB, key, record)
    return key, record, layer_used


def fetch_all_tmdb(csv_df: pd.DataFrame) -> dict:
    """
    Runs the 3-layer TMDB lookup for every movie in parallel.
    Prints which layer succeeded for each match.
    """
    rows         = [row for _, row in csv_df.iterrows()]
    cache        = load_cache(CACHE_TMDB)
    pending      = [r for r in rows
                    if make_cache_key(r["movie_name"], r.get("year", pd.NA)) not in cache]

    print(f"  {len(cache)} already cached, fetching {len(pending)} new movies...")

    layer_counts = {"tt:imdb": 0, "title+year": 0, "translated": 0, "none": 0}

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(_tmdb_worker, row): row["movie_name"]
                   for row in pending}
        for future in tqdm(as_completed(futures),
                           total=len(futures), desc="  TMDB"):
            key, record, layer = future.result()
            movie_name = futures[future]

            if layer == "none":
                layer_counts["none"] += 1
                print(f"  ⚠ No match (all 3 layers failed): '{movie_name}'")
            elif layer.startswith("tt:"):
                layer_counts["tt:imdb"] += 1
            elif layer == "title+year":
                layer_counts["title+year"] += 1
            elif layer.startswith("translated:"):
                layer_counts["translated"] += 1
                print(f"  ✓ Matched via translation: '{movie_name}'"
                      f" → '{layer.split(':', 1)[1]}'")

    final_cache = load_cache(CACHE_TMDB)
    print(f"\n  Match summary:")
    print(f"    Layer 1 (tt code):        {layer_counts['tt:imdb']}")
    print(f"    Layer 2 (title+year):     {layer_counts['title+year']}")
    print(f"    Layer 3 (translated):     {layer_counts['translated']}")
    print(f"    Failed all layers:        {layer_counts['none']}")
    return final_cache


# ══════════════════════════════════════════════════════════════
# STEP 1D — Wikipedia: full plot summaries (parallel)
# ══════════════════════════════════════════════════════════════

def _fetch_plot(title: str, year) -> str:
    year_str = str(int(year)) if pd.notna(year) else ""
    queries  = [f"{title} {year_str} film".strip(), f"{title} film"]

    for query in queries:
        r = robust_get(WIKI_API, params={
            "action": "query", "list": "search",
            "srsearch": query, "srlimit": 3, "format": "json",
        }, headers={"User-Agent": "MovieClusterBot/1.0"})

        if not r:
            continue

        hits = r.json().get("query", {}).get("search", [])
        if not hits:
            continue

        page_title = hits[0]["title"]
        r2 = robust_get(WIKI_API, params={
            "action": "query", "titles": page_title,
            "prop": "extracts", "explaintext": True,
            "exsectionformat": "plain", "format": "json",
        }, headers={"User-Agent": "MovieClusterBot/1.0"})

        if not r2:
            continue

        pages     = r2.json().get("query", {}).get("pages", {})
        full_text = next(iter(pages.values())).get("extract", "")
        if not full_text:
            continue

        plot_match = re.search(
            r"==\s*Plot\s*==\s*\n(.*?)(?=\n==\s|\Z)",
            full_text, re.DOTALL | re.IGNORECASE
        )
        if plot_match:
            return plot_match.group(1).strip()[:2000]
        return full_text[:1000]

    return ""


def _wiki_worker(row_and_tmdb: tuple) -> tuple:
    row, tmdb = row_and_tmdb
    name = row["movie_name"]
    year = row.get("year", pd.NA)
    key  = make_cache_key(name, year)

    cache = load_cache(CACHE_WIKIPEDIA)
    if key in cache:
        return key, cache[key]

    if not tmdb:
        entry = {"wiki_plot": "", "matched": False}
        update_cache(CACHE_WIKIPEDIA, key, entry)
        return key, entry

    verified_title = tmdb.get("title", name)
    plot           = _fetch_plot(verified_title, year)
    entry          = {"wiki_plot": plot, "matched": True}
    update_cache(CACHE_WIKIPEDIA, key, entry)
    return key, entry


def fetch_all_wikipedia(csv_df: pd.DataFrame, tmdb_cache: dict) -> dict:
    """Fetches Wikipedia plots in parallel for confirmed TMDB matches only."""
    rows_and_tmdb = []
    for _, row in csv_df.iterrows():
        key  = make_cache_key(row["movie_name"], row.get("year", pd.NA))
        tmdb = tmdb_cache.get(key, {})
        rows_and_tmdb.append((row, tmdb))

    wiki_cache = load_cache(CACHE_WIKIPEDIA)
    pending    = [(r, t) for r, t in rows_and_tmdb
                  if make_cache_key(r["movie_name"], r.get("year", pd.NA))
                  not in wiki_cache]

    print(f"  {len(wiki_cache)} already cached, fetching {len(pending)} new plots...")

    with ThreadPoolExecutor(max_workers=WORKERS) as executor:
        futures = {executor.submit(_wiki_worker, item): item[0]["movie_name"]
                   for item in pending}
        for future in tqdm(as_completed(futures),
                           total=len(futures), desc="  Wikipedia"):
            future.result()

    return load_cache(CACHE_WIKIPEDIA)


# ══════════════════════════════════════════════════════════════
# STEP 1E — Wikidata: structured metadata (parallel)
# ══════════════════════════════════════════════════════════════

WIKIDATA_QUERY = """
SELECT DISTINCT
  ?countryLabel ?wdGenreLabel ?sourceMaterialTypeLabel
  ?directorNationalityLabel ?decade
WHERE {{
  ?film wdt:P31 wd:Q11424 .
  ?film rdfs:label "{title}"@en .

  OPTIONAL {{ ?film wdt:P495 ?country . }}
  OPTIONAL {{ ?film wdt:P136 ?wdGenre . }}
  OPTIONAL {{
    ?film wdt:P144 ?sourceMaterial .
    ?sourceMaterial wdt:P31 ?sourceMaterialType .
  }}
  OPTIONAL {{
    ?film wdt:P57 ?director .
    ?director wdt:P27 ?directorNationality .
  }}
  OPTIONAL {{
    ?film wdt:P577 ?pubDate .
    BIND(CONCAT(STR(FLOOR(YEAR(?pubDate) / 10) * 10), "s") AS ?decade)
    {year_filter}
  }}
  SERVICE wikibase:label {{
    bd:serviceParam wikibase:language "en" .
  }}
}}
LIMIT 15
"""


def _fetch_wikidata(title: str, year) -> dict:
    year_filter = f"FILTER(YEAR(?pubDate) = {int(year)})" if pd.notna(year) else ""
    query = WIKIDATA_QUERY.format(
        title=title.replace('"', '\\"'),
        year_filter=year_filter
    )
    r = robust_get(
        WIKIDATA_SPARQL,
        params={"query": query, "format": "json"},
        headers={
            "User-Agent": "MovieClusterBot/1.0",
            "Accept":     "application/sparql-results+json",
        }
    )
    if not r:
        return {}

    bindings = r.json().get("results", {}).get("bindings", [])
    if not bindings:
        return {}

    countries, wd_genres, source_types, dir_nats, decades = (set() for _ in range(5))
    for b in bindings:
        if b.get("countryLabel"):       countries.add(b["countryLabel"]["value"])
        if b.get("wdGenreLabel"):       wd_genres.add(b["wdGenreLabel"]["value"])
        if b.get("sourceMaterialTypeLabel"):
            source_types.add(b["sourceMaterialTypeLabel"]["value"])
        if b.get("directorNationalityLabel"):
            dir_nats.add(b["directorNationalityLabel"]["value"])
        if b.get("decade"):             decades.add(b["decade"]["value"])

    return {
        "wd_countries":              list(countries),
        "wd_genres":                 list(wd_genres),
        "wd_source_material_types":  list(source_types),
        "wd_director_nationalities": list(dir_nats),
        "wd_decade":                 list(decades)[0] if decades else "",
        "matched": True,
    }


def _wd_worker(row_and_tmdb: tuple) -> tuple:
    row, tmdb = row_and_tmdb
    name = row["movie_name"]
    year = row.get("year", pd.NA)
    key  = make_cache_key(name, year)

    cache = load_cache(CACHE_WIKIDATA)
    if key in cache:
        return key, cache[key]

    if not tmdb:
        entry = {"matched": False}
        update_cache(CACHE_WIKIDATA, key, entry)
        return key, entry

    verified_title = tmdb.get("title", name)
    data           = _fetch_wikidata(verified_title, year)
    entry          = data if data else {"matched": False}
    update_cache(CACHE_WIKIDATA, key, entry)
    return key, entry


def fetch_all_wikidata(csv_df: pd.DataFrame, tmdb_cache: dict) -> dict:
    """Fetches Wikidata records in parallel for confirmed TMDB matches only."""
    rows_and_tmdb = []
    for _, row in csv_df.iterrows():
        key  = make_cache_key(row["movie_name"], row.get("year", pd.NA))
        tmdb = tmdb_cache.get(key, {})
        rows_and_tmdb.append((row, tmdb))

    wd_cache = load_cache(CACHE_WIKIDATA)
    pending  = [(r, t) for r, t in rows_and_tmdb
                if make_cache_key(r["movie_name"], r.get("year", pd.NA))
                not in wd_cache]

    print(f"  {len(wd_cache)} already cached, fetching {len(pending)} new records...")

    # Wikidata SPARQL is stricter about rate limits — use fewer workers
    wd_workers = max(1, WORKERS // 2)
    with ThreadPoolExecutor(max_workers=wd_workers) as executor:
        futures = {executor.submit(_wd_worker, item): item[0]["movie_name"]
                   for item in pending}
        for future in tqdm(as_completed(futures),
                           total=len(futures), desc="  Wikidata"):
            future.result()

    return load_cache(CACHE_WIKIDATA)


# ══════════════════════════════════════════════════════════════
# STEP 1F — Merge all sources
# ══════════════════════════════════════════════════════════════

def merge_sources(csv_df, tmdb_cache, wiki_cache, wd_cache) -> pd.DataFrame:
    records = []
    skipped = []

    for _, row in csv_df.iterrows():
        name       = row["movie_name"]
        year       = row.get("year", pd.NA)
        csv_genre  = row.get("genre", "")
        movie_id   = row.get("movie_id", "")
        translated = row.get("translated_title", name)
        lang       = row.get("detected_language", "en")
        was_trans  = row.get("was_translated", False)
        key        = make_cache_key(name, year)

        tmdb = tmdb_cache.get(key, {})
        if not tmdb:
            skipped.append(name)
            continue

        wiki = wiki_cache.get(key, {})
        wd   = wd_cache.get(key, {})

        wiki_plot     = wiki.get("wiki_plot", "").strip()
        tmdb_overview = tmdb.get("overview", "").strip()

        if wiki_plot and len(wiki_plot) > 100:
            combined_text = (tmdb_overview + " " + wiki_plot).strip()
        elif tmdb_overview:
            combined_text = tmdb_overview
        else:
            combined_text = translated if translated else name

        records.append({
            # ── Identifiers ──────────────────────────────────────
            "movie_id":          movie_id,
            "title":             tmdb.get("title", name),
            "csv_name":          name,
            "csv_genre":         csv_genre,
            "year":              year,
            "detected_language": lang,
            "was_translated":    was_trans,
            "translated_title":  translated,
            "lookup_layer":      tmdb.get("lookup_layer", ""),

            # ── Text for embedding ────────────────────────────────
            "combined_text":  combined_text,
            "tmdb_overview":  tmdb_overview,

            # ── TMDB metadata ─────────────────────────────────────
            "vote_average":  tmdb.get("vote_average"),
            "vote_count":    tmdb.get("vote_count"),
            "popularity":    tmdb.get("popularity"),
            "runtime":       tmdb.get("runtime"),
            "release_date":  tmdb.get("release_date", ""),
            "tmdb_genres":   ", ".join(tmdb.get("tmdb_genres", [])),

            # ── Wikipedia (end of CSV) ────────────────────────────
            "wiki_plot":     wiki_plot,

            # ── Wikidata (end of CSV) ─────────────────────────────
            "wd_country":              ", ".join(wd.get("wd_countries", [])),
            "wd_genres":               ", ".join(wd.get("wd_genres", [])),
            "wd_source_material":      ", ".join(wd.get("wd_source_material_types", [])),
            "wd_director_nationality": ", ".join(wd.get("wd_director_nationalities", [])),
            "wd_decade":               wd.get("wd_decade", ""),

            # ── Internal (feature engineering only) ──────────────
            "_wd_countries_list": wd.get("wd_countries", []),
            "_wd_source_list":    wd.get("wd_source_material_types", []),
        })

    if skipped:
        print(f"  Excluded {len(skipped)} unmatched movies from clustering")

    df = pd.DataFrame(records)
    print(f"  Merged {len(df)} confirmed-match movies")
    return df


# ══════════════════════════════════════════════════════════════
# STEP 2 — Clean and prepare
# ══════════════════════════════════════════════════════════════

def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    print("\n[2/6] Preparing data...")

    before = len(df)
    df     = df[df["combined_text"].notna() & (df["combined_text"].str.len() > 30)].copy()
    if len(df) < before:
        print(f"  Dropped {before - len(df)} rows with no usable text")

    df["release_year"] = pd.to_datetime(df["release_date"], errors="coerce").dt.year

    for col in ["vote_average", "vote_count", "popularity", "runtime"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
        df[col] = df[col].fillna(df[col].median())

    df["log_vote_count"] = np.log1p(df["vote_count"])
    df["log_popularity"] = np.log1p(df["popularity"])
    df["has_wiki_plot"]  = (df["wiki_plot"].str.len() > 100).astype(int)
    df["is_adaptation"]  = df["_wd_source_list"].apply(
        lambda x: 1 if isinstance(x, list) and len(x) > 0 else 0
    )

    df = df.reset_index(drop=True)
    print(f"  {len(df)} movies ready")
    print(f"  Wikipedia plots:  {df['has_wiki_plot'].sum()} / {len(df)}")
    print(f"  Wikidata records: {(df['wd_country'] != '').sum()} / {len(df)}")
    print(f"  Translated:       {df['was_translated'].sum()} / {len(df)}")
    return df


# ══════════════════════════════════════════════════════════════
# STEP 3 — Embed + feature matrix
# ══════════════════════════════════════════════════════════════

def embed_texts(df: pd.DataFrame) -> np.ndarray:
    print(f"\n[3/6] Embedding text with TF-IDF + SVD (dims={EMBEDDING_DIMS})...")
    texts  = df["combined_text"].tolist()
    tfidf  = TfidfVectorizer(
        max_features=20000,
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=2,
        strip_accents="unicode",
    )
    sparse     = tfidf.fit_transform(texts)
    n_dims     = min(EMBEDDING_DIMS, sparse.shape[1] - 1)
    svd        = TruncatedSVD(n_components=n_dims, random_state=42)
    embeddings = svd.fit_transform(sparse)
    print(f"  Embeddings shape: {embeddings.shape}  "
          f"(explained variance: {svd.explained_variance_ratio_.sum():.1%})")
    return embeddings


def build_feature_matrix(df: pd.DataFrame, embeddings: np.ndarray) -> np.ndarray:
    print("\n  Building feature matrix...")

    meta_cols   = ["vote_average", "log_vote_count", "log_popularity",
                   "runtime", "is_adaptation"]
    meta_cols   = [c for c in meta_cols if c in df.columns]
    scaler      = StandardScaler()
    meta_scaled = scaler.fit_transform(df[meta_cols].fillna(0))

    all_countries = [c for lst in df["_wd_countries_list"] for c in lst]
    top_countries = [c for c, _ in Counter(all_countries).most_common(15)]
    country_mat   = np.zeros((len(df), max(len(top_countries), 1)))
    for i, lst in enumerate(df["_wd_countries_list"]):
        for c in lst:
            if c in top_countries:
                country_mat[i, top_countries.index(c)] = 1

    all_sources = [s for lst in df["_wd_source_list"] for s in lst]
    top_sources = [s for s, _ in Counter(all_sources).most_common(10)]
    source_mat  = np.zeros((len(df), max(len(top_sources), 1)))
    for i, lst in enumerate(df["_wd_source_list"]):
        for s in lst:
            if s in top_sources:
                source_mat[i, top_sources.index(s)] = 1

    combined = np.hstack([
        embeddings   * 2.0,
        meta_scaled  * 0.5,
        country_mat  * 0.4,
        source_mat   * 0.3,
    ])

    print(f"  Shape: {combined.shape}  "
          f"(embed={embeddings.shape[1]}, meta={meta_scaled.shape[1]}, "
          f"country={country_mat.shape[1]}, source={source_mat.shape[1]})")
    return combined


# ══════════════════════════════════════════════════════════════
# STEP 4 — UMAP
# ══════════════════════════════════════════════════════════════

def run_umap(features: np.ndarray) -> np.ndarray:
    print(f"\n[4/6] Running UMAP...")
    reducer = umap.UMAP(
        n_neighbors=min(UMAP_N_NEIGHBORS, len(features) - 1),
        min_dist=UMAP_MIN_DIST, n_components=2,
        metric=UMAP_METRIC, random_state=42, verbose=False
    )
    embedding_2d = reducer.fit_transform(features)
    print(f"  Done → {embedding_2d.shape}")
    return embedding_2d


# ══════════════════════════════════════════════════════════════
# STEP 5 — HDBSCAN
# ══════════════════════════════════════════════════════════════

def run_hdbscan(embedding_2d: np.ndarray) -> hdbscan.HDBSCAN:
    min_size = min(HDBSCAN_MIN_CLUSTER_SIZE, max(3, len(embedding_2d) // 20))
    print(f"\n[5/6] Running HDBSCAN (min_cluster_size={min_size})...")
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_size, min_samples=HDBSCAN_MIN_SAMPLES,
        metric="euclidean", cluster_selection_method="eom", prediction_data=True
    )
    clusterer.fit(embedding_2d)
    labels     = clusterer.labels_
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    n_noise    = (labels == -1).sum()
    print(f"  Found {n_clusters} clusters, "
          f"{n_noise} noise points ({100 * n_noise / len(labels):.1f}%)")
    return clusterer


# ══════════════════════════════════════════════════════════════
# STEP 6 — Label clusters + visualize
# ══════════════════════════════════════════════════════════════

STOPWORDS = {
    "this", "that", "with", "from", "they", "their", "have", "when", "will",
    "after", "while", "where", "which", "about", "into", "onto", "over",
    "must", "also", "been", "being", "both", "each", "more", "most", "such",
    "than", "then", "them", "these", "those", "only", "even", "very", "just",
    "make", "find", "help", "take", "back", "come", "goes", "life", "time",
    "what", "when", "able", "around", "before", "become", "becomes", "young",
    "soon", "begins", "begin", "tries", "forced", "brings", "faces", "named",
    "story", "lives", "love", "world", "man", "woman", "team", "group",
    "along", "order", "until", "seeks", "works", "discover", "small",
    "returns", "decides", "discovers", "attempts", "allows", "reveals",
    "during", "later", "finds", "takes", "leaves", "tells", "meets",
}


def get_cluster_keywords(df, cid, top_n=5):
    words = []
    for text in df[df["cluster"] == cid]["combined_text"]:
        words.extend(re.findall(r"\b[a-z]{5,}\b", text.lower()))
    words = [w for w in words if w not in STOPWORDS]
    return [w for w, _ in Counter(words).most_common(top_n)]


def label_clusters(df: pd.DataFrame) -> pd.DataFrame:
    print("\n[6/6] Labeling clusters...")
    cluster_ids = sorted([c for c in df["cluster"].unique() if c != -1])
    label_map   = {-1: "Noise / Outlier"}

    for cid in cluster_ids:
        size      = (df["cluster"] == cid).sum()
        keywords  = get_cluster_keywords(df, cid)
        countries = list({
            c for lst in df[df["cluster"] == cid]["_wd_countries_list"]
            if isinstance(lst, list) for c in lst
        })
        country_tag = f" [{', '.join(countries[:2])}]" if countries else ""
        sample      = df[df["cluster"] == cid]["title"].sample(min(3, size)).tolist()
        label       = f"Cluster {cid}{country_tag}: {', '.join(keywords[:3])}"
        label_map[cid] = label
        print(f"  {label} ({size} films) — e.g. {sample}")

    df["cluster_label"] = df["cluster"].map(label_map)
    return df


def build_visualization(df: pd.DataFrame) -> go.Figure:
    df_clusters = df[df["cluster"] != -1]
    df_noise    = df[df["cluster"] == -1]

    fig = px.scatter(
        df_clusters, x="x", y="y", color="cluster_label",
        hover_name="title",
        hover_data={
            "x": False, "y": False,
            "csv_genre": True, "detected_language": True,
            "translated_title": True, "lookup_layer": True,
            "release_year": True, "wd_country": True,
            "wd_decade": True, "wd_source_material": True,
            "vote_average": ":.1f", "runtime": True,
            "cluster_label": True, "tmdb_overview": True,
        },
        title="🎬 Movie Clusters via UMAP + HDBSCAN<br>"
              "<sup>3-layer TMDB lookup · Wikipedia · Wikidata · "
              "Google Translate</sup>",
        width=1200, height=800,
    )

    if len(df_noise) > 0:
        fig.add_trace(go.Scatter(
            x=df_noise["x"], y=df_noise["y"], mode="markers",
            marker=dict(size=3, color="lightgrey", opacity=0.4),
            name="Noise / Outlier",
            hovertemplate="<b>%{customdata[0]}</b><extra></extra>",
            customdata=df_noise[["title"]].values
        ))

    fig.update_traces(marker=dict(size=8, opacity=0.85), selector=dict(mode="markers"))
    fig.update_layout(
        plot_bgcolor="#0f1117", paper_bgcolor="#0f1117",
        font=dict(color="#e0e0e0"),
        legend=dict(bgcolor="#1a1d27", bordercolor="#333",
                    borderwidth=1, font=dict(size=11)),
        title_font=dict(size=18),
        xaxis=dict(showticklabels=False, showgrid=False, zeroline=False, title=""),
        yaxis=dict(showticklabels=False, showgrid=False, zeroline=False, title=""),
        margin=dict(l=20, r=20, t=80, b=20),
    )
    return fig


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    global MOVIES_CSV
    print("=" * 65)
    print("  Movie Clustering: UMAP + HDBSCAN Pipeline")
    print("  Sources: TMDB · Wikipedia · Wikidata · Google Translate")
    print(f"  Workers: {WORKERS} parallel  |  Retry delay: {RETRY_DELAY}s")
    print(f"  CSV: {MOVIES_CSV}  |  Translation: langdetect + deep-translator")
    print("=" * 65)

    # ── Validate user inserts ────────────────────────────────
    errors = []
    if TMDB_API_KEY == "PASTE_YOUR_TMDB_KEY_HERE":
        errors.append("INSERT #1 — TMDB_API_KEY not set  (set env var TMDB_API_KEY)")

    # If running on GCP, download input file from GCS to /tmp first
    if GCS_BUCKET_NAME:
        if not _GCS_AVAILABLE:
            errors.append("google-cloud-storage not installed but GCS_BUCKET_NAME is set")
        else:
            ext = os.path.splitext(INPUT_BLOB)[1].lower()
            local_input = f"/tmp/input_data{ext}"
            try:
                gcs_download_to_file(GCS_BUCKET_NAME, INPUT_BLOB, local_input)
                MOVIES_CSV = local_input
            except Exception as e:
                errors.append(f"Failed to download input from GCS: {e}")
    elif not os.path.exists(MOVIES_CSV):
        errors.append(f"INSERT #2 — '{MOVIES_CSV}' not found in this folder  (set env var MOVIES_CSV)")
    if errors:
        print("\n❌ Fix the following before running:")
        for e in errors:
            print(f"   • {e}")
        return

    # 1A. Load
    print(f"\n[1/6] Loading '{MOVIES_CSV}'...")
    csv_df = load_csv(MOVIES_CSV)

    # 1B. Translate
    print("\n  → Detecting languages + translating non-English titles...")
    csv_df = translate_all_titles(csv_df)

    # 1C. TMDB (3-layer)
    print("\n  → TMDB lookup (Layer 1: tt code → Layer 2: title+year → "
          "Layer 3: translated+year)...")
    tmdb_cache = fetch_all_tmdb(csv_df)

    # 1D. Wikipedia
    print("\n  → Wikipedia plot summaries (confirmed matches only)...")
    wiki_cache = fetch_all_wikipedia(csv_df, tmdb_cache)

    # 1E. Wikidata
    print("\n  → Wikidata metadata (confirmed matches only)...")
    wd_cache = fetch_all_wikidata(csv_df, tmdb_cache)

    # 1F. Merge
    print("\n  → Merging all sources...")
    df = merge_sources(csv_df, tmdb_cache, wiki_cache, wd_cache)

    if len(df) < 10:
        print(f"\n⚠ Only {len(df)} matched movies — need at least 10.")
        return

    # 2–5
    df           = prepare_dataframe(df)
    embeddings   = embed_texts(df)
    features     = build_feature_matrix(df, embeddings)
    embedding_2d = run_umap(features)
    df["x"]      = embedding_2d[:, 0]
    df["y"]      = embedding_2d[:, 1]

    clusterer             = run_hdbscan(embedding_2d)
    df["cluster"]         = clusterer.labels_
    df["outlier_score"]   = clusterer.outlier_scores_
    df["membership_prob"] = clusterer.probabilities_

    df  = label_clusters(df)
    fig = build_visualization(df)

    # Save HTML
    fig.write_html(OUTPUT_HTML)
    print(f"\n✅ Visualization saved  → {OUTPUT_HTML}")

    # Save CSV — Wikipedia + Wikidata columns at the end
    core_cols = [
        "movie_id", "title", "csv_name", "csv_genre", "year",
        "detected_language", "was_translated", "translated_title",
        "lookup_layer", "release_date", "release_year",
        "vote_average", "vote_count", "popularity", "runtime", "tmdb_genres",
        "cluster", "cluster_label", "outlier_score", "membership_prob",
        "x", "y",
    ]
    enrichment_cols = [
        "wiki_plot",                                    # ← Wikipedia
        "wd_country", "wd_genres", "wd_source_material",  # ← Wikidata
        "wd_director_nationality", "wd_decade",
    ]
    all_cols    = core_cols + enrichment_cols
    export_cols = [c for c in all_cols if c in df.columns]
    remaining   = [c for c in df.columns
                   if c not in export_cols and not c.startswith("_")]
    export_cols += remaining

    df[export_cols].to_csv(OUTPUT_CSV, index=False)
    print(f"Data saved -> {OUTPUT_CSV}")
    print(f"   Columns: core -> wiki_plot -> wd_country/wd_genres/"
          f"wd_source_material/wd_director_nationality/wd_decade")

    # Upload outputs to GCS if running on Cloud Run
    if GCS_BUCKET_NAME and _GCS_AVAILABLE:
        gcs_upload_from_file(GCS_BUCKET_NAME, f"{OUTPUT_PREFIX}/movie_clusters.csv",  OUTPUT_CSV)
        gcs_upload_from_file(GCS_BUCKET_NAME, f"{OUTPUT_PREFIX}/movie_clusters.html", OUTPUT_HTML)
        print(f"Outputs uploaded to gs://{GCS_BUCKET_NAME}/{OUTPUT_PREFIX}/")

    # Summary
    print("\n── Top 10 Most Anomalous Films ──")
    sc = ["title", "csv_genre", "lookup_layer", "detected_language",
          "wd_country", "wd_decade", "vote_average", "outlier_score"]
    sc = [c for c in sc if c in df.columns]
    print(df.nlargest(10, "outlier_score")[sc].to_string(index=False))
    print(f"\nDone! Open {OUTPUT_HTML} in your browser.")


if __name__ == "__main__":
    main()