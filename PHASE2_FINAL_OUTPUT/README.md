# Phase 2 - Final Enrichment Output

**Date Created:** April 6, 2026  
**Purpose:** Complete enriched dataset with production budgets and MPAA ratings

---

## Contents

### 📊 Data Files

#### `project_2_data_filled_with_api.csv`
- **Purpose:** Main enriched dataset - FINAL OUTPUT
- **Records:** 3,438 films
- **New Columns Added:**
  - `production_budget` - Enriched with 3-layer fallback (TMDB → Wikidata → Wikipedia)
  - `production_budget_source` - Track data origin: "tmdb_api" | "wikidata" | "wikipedia" | "original" | "not_found"
  - `mpaa_rating` - Enriched with IMDb 3-retry scraping strategy
  - `mpaa_rating_source` - Track data origin: "imdb_scraping" | "original" | "not_found"
- **Expected Coverage:**
  - Budgets: ~40-60% success on missing-budget films (~300-530 enriched)
  - MPAA Ratings: ~90%+ success

#### `project_2_data_filled_with_api_with_efficiency.csv`
- **Purpose:** Alternative version with efficiency metrics
- **Difference:** Includes additional feature engineering calculations

---

## 📄 Documentation & Scripts

#### `PROJECT_CONTEXT.md`
- Comprehensive reference document
- Complete architecture explanation
- API configurations and patterns
- Troubleshooting guide
- **Use this for:** Understanding the full enrichment pipeline

#### `enrich_combined.py`
- Main enrichment script source code
- Implements 3-layer budget fallback strategy
- Implements 3-retry IMDb scraping for MPAA ratings
- **Use this for:** Reference on how enrichment was performed

---

## 🔄 Enrichment Pipeline Summary

### Phase 1: Budget Enrichment (3-Layer Fallback)
```
Layer 1: TMDB API
  └─ Lookup by IMDb ID → Get TMDB ID → Retrieve budget
    
Layer 2: Wikidata SPARQL
  └─ SPARQL query: Production cost (wdt:P2130)
  └─ Match: Title + Year
    
Layer 3: Wikipedia API
  └─ Article search by title
  └─ Regex extraction: Budget patterns
  └─ Handle currency: "10 million" → 10,000,000
```

**Expected Results:**
- TMDB: ~50-100 films
- Wikidata: ~200-350 films  
- Wikipedia: ~50-80 films
- Not Found: ~300 films

### Phase 2: MPAA Rating Enrichment
```
IMDb 3-Retry Scraping Strategy
  └─ Up to 3 attempts per film
  └─ 5-second rate limiting per request
  └─ Multiple extraction methods:
      ├─ Span-based extraction
      ├─ MPAA label search
      └─ Pre-Code inference (1930-1934 films)
```

**Expected Results:**
- Success: ~90%+ of missing MPAA ratings
- Not Found: ~10% or fewer

---

## 📋 Data Quality Notes

### Budget Source Breakdown
When analyzing `production_budget_source` column:
- `"original"` = Already in dataset (2,694 films)
- `"tmdb_api"` = Retrieved from TMDB API
- `"wikidata"` = Retrieved from Wikidata (better for classic films)
- `"wikipedia"` = Retrieved from Wikipedia
- `"not_found"` = Could not retrieve from any source

### MPAA Rating Source Breakdown
When analyzing `mpaa_rating_source` column:
- `"original"` = Already in dataset
- `"imdb_scraping"` = Retrieved via IMDb web scraping
- `"not_found"` = Could not retrieve

---

## 🔧 How to Use These Files

### 1. Load the Enriched Data
```python
import pandas as pd

df = pd.read_csv('project_2_data_filled_with_api.csv')

# Check enrichment results
print(df['production_budget_source'].value_counts())
print(df['mpaa_rating_source'].value_counts())
```

### 2. Analyze by Source
```python
# Films enriched from each source
tmdb_films = df[df['production_budget_source'] == 'tmdb_api']
wikidata_films = df[df['production_budget_source'] == 'wikidata']
wikipedia_films = df[df['production_budget_source'] == 'wikipedia']

print(f"TMDB: {len(tmdb_films)} films")
print(f"Wikidata: {len(wikidata_films)} films")
print(f"Wikipedia: {len(wikipedia_films)} films")
```

### 3. Understand Enrichment Coverage
```python
# Budget enrichment coverage
budgets_filled = df[df['production_budget'].notna()]
budget_coverage = len(budgets_filled) / len(df) * 100

# MPAA enrichment coverage
mpaa_filled = df[df['mpaa_rating'].notna()]
mpaa_coverage = len(mpaa_filled) / len(df) * 100

print(f"Budget Coverage: {budget_coverage:.1f}%")
print(f"MPAA Coverage: {mpaa_coverage:.1f}%")
```

---

## 🗂️ Related Files (in Parent Directory)

If you need to re-run or debug:
- `movie_clustering.py` - Reference for 3-layer pattern
- `main.py` - Reference for scraping patterns
- Cache files (auto-generated on first run):
  - `cache_wikidata_budgets.json`
  - `cache_wikipedia_budgets.json`

---

## ⚙️ Technical Details

### Enrichment Parameters
- **Similarity Threshold:** 0.85 (for title matching)
- **TMDB Rate Limit:** 40 requests/10 seconds
- **Wikidata Rate Limit:** ~1 request/second (0.5s delays)
- **Wikipedia Rate Limit:** 1-2 seconds between requests
- **IMDb Scraping:** 5-second delays per request

### Caching Strategy
- Wikidata results cached in `cache_wikidata_budgets.json`
- Wikipedia results cached in `cache_wikipedia_budgets.json`
- Cache persists between runs (incremental enrichment)

---

## 🚀 Next Steps

1. **Load & Validate:** Verify data with code samples above
2. **Analyze Source Distribution:** Check breakdown by source
3. **Quality Check:** Look for outliers or patterns by era/country
4. **Integration:** Use enriched data for downstream analysis/clustering

---

## 📞 Reference

For complete documentation and troubleshooting:
→ See `PROJECT_CONTEXT.md` in this folder

---

**Status:** ✅ Phase 2 (Final Enrichment) Complete  
**Output Ready:** Yes  
**Ready for Downstream Analysis:** Yes
