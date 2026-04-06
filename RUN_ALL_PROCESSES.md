# BUS682 Project 1 Run Guide

## What This Folder Does
This project has three main workflows:

1. IMDb scraping (`scraper_imdb.py` or `main.py`) -> `output/imdb_ratings_output.xlsx` in GCS
2. Rotten Tomatoes scraping (`scraper_rottentomatoes.py`) -> `output/rotten_tomatoes_scores.xlsx` in GCS
3. Clustering/enrichment (`movie_clustering.py`) using TMDB + Wikipedia + Wikidata -> `movie_clusters.csv` and `movie_clusters.html`

There is also a feature utility:

- `cluster_features.py` for feature-level clustering from `feature_taxonomy.csv` + `feature_data_longform.csv`

## Prerequisites

1. Python 3.11+
2. Virtual environment (already present as `.venv`)
3. Dependencies

```powershell
pip install -r requirements.txt
pip install -r requirements.clustering.txt
```

4. For cloud usage: authenticated `gcloud` and access to your GCS bucket/Cloud Run jobs

## Local Setup (Windows PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements.clustering.txt
```

## A) Run IMDb Scraper (GCS)

Script: `scraper_imdb.py` (or `main.py`, similar role)

Required environment variables:

- `GCS_BUCKET_NAME`
- `INPUT_FILE` (default: `input/movies.csv`)
- `OUTPUT_FILE` (default: `output/imdb_ratings_output.xlsx`)
- `MAX_WORKERS`

Example:

```powershell
$env:GCS_BUCKET_NAME = "your-bucket"
$env:INPUT_FILE = "input/movies.csv"
$env:OUTPUT_FILE = "output/imdb_ratings_output.xlsx"
$env:MAX_WORKERS = "5"
python .\scraper_imdb.py
```

## B) Run Rotten Tomatoes Scraper (GCS)

Script: `scraper_rottentomatoes.py`

Required environment variables:

- `GCS_BUCKET_NAME`
- `INPUT_FILE` (default: `output/imdb_ratings_output.xlsx`)
- `OUTPUT_FILE` (default: `output/rotten_tomatoes_scores.xlsx`)
- `MAX_WORKERS`

Example:

```powershell
$env:GCS_BUCKET_NAME = "your-bucket"
$env:INPUT_FILE = "output/imdb_ratings_output.xlsx"
$env:OUTPUT_FILE = "output/rotten_tomatoes_scores.xlsx"
$env:MAX_WORKERS = "10"
python .\scraper_rottentomatoes.py
```

## C) Run Movie Clustering + Enrichment

Script: `movie_clustering.py`

Required for local mode:

- `TMDB_API_KEY`
- `MOVIES_CSV` (default: `genre_data.csv`)

Optional for GCS mode:

- `GCS_BUCKET_NAME`
- `INPUT_BLOB` (default: `output/imdb_ratings_output.xlsx`)
- `OUTPUT_PREFIX` (default: `output/clustering`)

Local run example:

```powershell
$env:TMDB_API_KEY = "your_tmdb_key_here"
$env:MOVIES_CSV = "genre_data.csv"
python .\movie_clustering.py
```

Expected local outputs:

- `movie_clusters.csv`
- `movie_clusters.html`
- `cache_tmdb.json`
- `cache_wikipedia.json`
- `cache_wikidata.json`
- `cache_translations.json`

## D) Optional Feature Clustering Utility

Script: `cluster_features.py`

```powershell
python .\cluster_features.py --features feature_taxonomy.csv --longform feature_data_longform.csv --out-csv feature_clusters.csv --out-plot feature_clusters.png --auto-k --max-k 8
```

## Cloud Build Commands

The repo contains:

- `cloudbuild.imdb.yaml` + `Dockerfile.imdb`
- `cloudbuild.clustering.yaml` + `Dockerfile.clustering`
- `Dockerfile` (RT scraper container)

Build examples:

```powershell
gcloud builds submit --config cloudbuild.imdb.yaml
gcloud builds submit --config cloudbuild.clustering.yaml
```

## API Key Location Findings

### TMDB key

- A real TMDB key is **not committed** in this repository.
- The code reads `TMDB_API_KEY` from the environment in `movie_clustering.py`.
- The in-file value is a placeholder: `PASTE_YOUR_TMDB_KEY_HERE`.

### What was checked

- No `.env` file found in this project folder.
- `TMDB_API_KEY` is not set in the current terminal session.

### Where you can copy it from

1. Current shell (if set there):

```powershell
echo $env:TMDB_API_KEY
```

2. Cloud Run Job environment:

```powershell
gcloud run jobs describe movie-clustering --region us-central1 --format="yaml(spec.template.spec.containers[0].env)"
```

3. Secret manager / profile scripts you use to inject env vars.

## Notebook Note

- `PROJECT_HOLLYWOOD/Project_HOLLYWOOD (1).ipynb` references `OMDB_API_KEY` from env/SECRETS.
- No hardcoded OMDB key value was found.
