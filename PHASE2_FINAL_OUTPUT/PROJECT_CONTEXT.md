# BUS682 Project 2: Movie Data Enrichment - Complete Context Guide

**Last Updated:** April 6, 2026
**Project Status:** Active enrichment in progress with 3-layer fallback strategy
**Dataset:** 3,438 films with 744 missing production budgets (21.6%)

---

## Table of Contents
1. [Project Overview](#project-overview)
2. [Objectives & Constraints](#objectives--constraints)
3. [Data Structure](#data-structure)
4. [Technical Architecture](#technical-architecture)
5. [Enrichment Strategy (3-Layer)](#enrichment-strategy-3-layer)
6. [Code Files Reference](#code-files-reference)
7. [API Configurations](#api-configurations)
8. [Implementation Details](#implementation-details)
9. [Current Status](#current-status)
10. [Key Patterns & Functions](#key-patterns--functions)
11. [Next Steps](#next-steps)

---

## Project Overview

### Purpose
Enrich a dataset of 3,438 movies with missing production budget information and MPAA ratings. The dataset represents Hollywood films spanning multiple eras (pre-1900s to 2020s), with particular gaps in classic cinema budget data.

### Problem Statement
- **Missing Budgets:** 744 out of 3,438 films (21.6%)
- **Root Cause:** Classic films (pre-1960s) have minimal budget data in primary source (TMDB)
- **Solution:** Implement 3-layer fallback strategy using multiple data sources

### Business Context
- **Course:** BUS682 Project 2
- **Data Source:** IMDb + TMDB + Custom scraping
- **Goal:** Complete missing fields for downstream analysis and clustering

---

## Objectives & Constraints

### Primary Objectives
1. ✅ Identify and implement existing enrichment patterns from codebase
2. ✅ Implement 3-layer TMDB fallback strategy (IMDb ID → Title search → No Layer 3 in TMDB)
3. ✅ Evaluate alternative budget data sources (Wikidata, Wikipedia)
4. ✅ Add Layer 2: Wikidata SPARQL queries for production costs
5. ✅ Add Layer 3: Wikipedia API with regex-based budget extraction
6. ✅ Track data source for each enriched budget value
7. ⏳ Complete MPAA rating scraping with 3-retry strategy

### User Constraints (CRITICAL)
- **NO estimation layer** - Only verified source data
- **Source labeling required** - Every budget must indicate where data came from
- **3 layers only** - TMDB → Wikidata → Wikipedia (no Layer 4)
- **Rate limiting** - Respect API throttling and implement caching

### Technical Constraints
- Python 3.11+
- CSV-based input/output
- API rate limits (TMDB slow, Wikidata slow, Wikipedia moderate)
- No estimation or inference-based values

---

## Data Structure

### Input File
**File:** `project_2_data_filled_with_api.csv`

**Records:** 3,438 films
**Primary Columns:**
- `imdb_id` - IMDb identifier (tt format)
- `title` - Film title
- `release_year` - Year of release
- `country` - Country of origin
- `box_office` - Box office revenue
- `runtime` - Film duration (minutes)
- `genres` - Film genres (comma-separated)
- `imdb_rating` - IMDb rating (0-10)
- `imdb_votes` - Number of IMDb votes
- `original_language` - Original film language
- `production_budget` - **744 MISSING** - Target for enrichment
- `hays_code` / `mpaa_rating` - Certification (partial data)
- **Factors (Column 0-29)** - Additional feature columns

### Output File
**File:** `project_2_data_filled_with_api.csv` (updated)

**New Columns Added:**
- `production_budget_source` - Origin of budget data
  - **Values:** `"tmdb_api"` | `"wikidata"` | `"wikipedia"` | `"original"` | `"not_found"`
- `mpaa_rating_source` - Origin of rating data
  - **Values:** `"imdb_scraping"` | `"original"` | `"not_found"`

### Missing Data Profile
- **Films with Missing Budgets:** 744 (21.6%)
- **Era Distribution:** Predominantly pre-1960s classic films (1890s-1950s)
- **Expected Coverage by Source:**
  - TMDB: ~0-10% (minimal budget data for old films)
  - Wikidata: ~15-40% (good coverage for classic Hollywood)
  - Wikipedia: ~10-20% (some articles have budget info)
  - Combined Expected: ~33-47% success rate

---

## Technical Architecture

### Overall Pipeline

```
INPUT: project_2_data_filled_with_api.csv (3,438 films)
  ↓
PHASE 1: Budget Enrichment
  ├─ For each film with missing budget:
  │  ├─ Try Layer 1: TMDB API (IMDb ID lookup)
  │  ├─ Try Layer 2: Wikidata SPARQL (title+year search)
  │  ├─ Try Layer 3: Wikipedia API (title search + regex extraction)
  │  └─ Track source: tmdb_api | wikidata | wikipedia | not_found
  ↓
PHASE 2: MPAA Rating Enrichment (parallel with Phase 1)
  ├─ For each film with missing MPAA:
  │  ├─ Try Layer 1: IMDb scraping (3 retries, 5-second delays)
  │  ├─ Extract from page content with fallback methods
  │  └─ Track source: imdb_scraping | not_found
  ↓
OUTPUT: project_2_data_filled_with_api.csv (updated with sources)
```

### Data Flow by Film Type

**Films with Budget Data:**
- No enrichment needed
- `production_budget_source` = `"original"`

**Films with Missing Budget (pre-1960s classics):**
1. First attempt: TMDB API via IMDb ID
   - Success → `source = "tmdb_api"`
2. If TMDB fails: Try Wikidata SPARQL
   - Success → `source = "wikidata"`
3. If Wikidata fails: Try Wikipedia API
   - Success → `source = "wikipedia"`
4. If all fail: Leave blank
   - `source = "not_found"`

---

## Enrichment Strategy (3-Layer)

### Layer 1: TMDB API
**Method:** `get_budget_by_imdb_id()` with IMDb ID lookup

**Process:**
1. Lookup IMDb ID (tt format) in TMDB
2. Extract TMDB ID from response
3. Query TMDB for movie details including budget
4. Return budget if found, else proceed to Layer 2

**Expected Success:** ~50-100 films (mostly 1960s+)
**Source Label:** `"tmdb_api"`

**Code Reference:** [enrich_combined.py - get_budget_by_imdb_id()](enrich_combined.py#L1)

### Layer 2: Wikidata SPARQL
**Method:** `layer2_wikidata(title, year)` with SPARQL query

**Process:**
1. Query Wikidata for films matching title and year
2. Use SPARQL query to find `wdt:P2130` (production cost)
3. Cache results in `cache_wikidata_budgets.json`
4. Return budget if found, else proceed to Layer 3

**SPARQL Query Template:**
```sparql
SELECT DISTINCT ?productionCost WHERE {
  ?film wdt:P31 wd:Q11024 .           # Instance of film
  ?film rdfs:label "TITLE"@en .       # Title match
  OPTIONAL { 
    ?film wdt:P580 ?startDate .       # Start date
    FILTER (?startDate = "YEAR-01-01"^^xsd:dateTime)
  }
  OPTIONAL { ?film wdt:P2130 ?productionCost . }  # Production cost
}
LIMIT 1
```

**Expected Success:** ~200-350 films (best for 1930s-1960s)
**Source Label:** `"wikidata"`
**Rate Limit:** 12-second timeout, 0.5-second delays between queries

**Code Reference:** [enrich_combined.py - layer2_wikidata()](enrich_combined.py#L1)

### Layer 3: Wikipedia API
**Method:** `layer3_wikipedia(title, year)` with regex extraction

**Process:**
1. Search Wikipedia for article matching film title
2. Extract article text and HTML
3. Apply regex patterns to find budget information
4. Handle currency conversions ("$10 million" → 10,000,000)
5. Cache results in `cache_wikipedia_budgets.json`
6. Return budget if found, else mark as "not_found"

**Regex Patterns Used:**
- `budget.*?\$\s*([\d,]+)` - Direct dollar amounts
- `production.*?cost.*?\$\s*([\d,]+)` - Production cost references
- Multiplier handling: Check for "million" suffix

**Expected Success:** ~50-80 films
**Source Label:** `"wikipedia"`
**Cache File:** `cache_wikipedia_budgets.json` (key: "title:year")

**Code Reference:** [enrich_combined.py - layer3_wikipedia()](enrich_combined.py#L1)

### MPAA Rating Strategy (Parallel Enrichment)
**Method:** 3-retry IMDb scraping with multiple extraction strategies

**Process:**
1. Attempt IMDb page scraping (up to 3 retries)
2. 5-second delay between requests (rate limiting)
3. Apply multiple extraction fallbacks:
   - Span-based extraction (look for rating labels)
   - MPAA label search (specific text matching)
   - Release date inference (Pre-Code detection for 1930-1934 films)
4. Cache successful results

**Expected Success:** 90%+ (MPAA ratings widely available)
**Source Label:** `"imdb_scraping"` or `"original"`

**Code Reference:** [main.py - extract_mpaa_from_soup()](main.py#L85-L127)

---

## Code Files Reference

### Primary Work File: `enrich_combined.py`
**Purpose:** Main orchestration script for 3-layer budget enrichment + MPAA rating completion

**Key Methods:**
- `class CombinedMovieEnricher` - Main orchestrator class
- `normalize_title(title)` - Title normalization for matching (derived from movie_clustering.py)
- `title_similarity(title_a, title_b, threshold=0.85)` - Similarity scoring (0.85 threshold for matches)
- `get_tmdb_id_by_imdb(imdb_id)` - Layer 1 TMDB lookup by IMDb ID
- `get_budget_by_tmdb_id(tmdb_id)` - Retrieve budget from TMDB once ID obtained
- `layer2_wikidata(title, year)` - Layer 2 Wikidata SPARQL query
- `layer3_wikipedia(title, year)` - Layer 3 Wikipedia API + regex extraction
- `get_budget_by_imdb_id(imdb_id, title, year)` - Master method orchestrating all 3 layers
- `extract_mpaa_ratings()` - Phase 2: IMDb scraping with 3-retry strategy
- `enrich_dataset()` - Main pipeline (Phase 1 budgets + Phase 2 MPAA)

**Dependencies:**
- `requests` - HTTP requests to APIs
- `pandas` - CSV handling and data manipulation
- `difflib.SequenceMatcher` - Title similarity matching
- `re` - Regex for budget extraction
- SQLAlchemy for Wikidata SPARQL queries (optional, can use direct HTTP)
- `BeautifulSoup4` - IMDb page parsing (for MPAA scraping)

**Input:** `project_2_data_filled_with_api.csv`
**Output:** Updated CSV with `production_budget_source` and `mpaa_rating_source` columns
**Cache Files:**
- `cache_wikidata_budgets.json` - Wikidata query results
- `cache_wikipedia_budgets.json` - Wikipedia extraction results

**Status:** ✅ Fully implemented with all 3 layers + source tracking

---

### Reference File: `movie_clustering.py`
**Purpose:** Existing 3-layer TMDB lookup implementation (provides architecture template)

**Key Pattern (Lines 410-480):**
```python
def _tmdb_by_tt(imdb_id):  # Layer 1: IMDb ID lookup
    ...

def _tmdb_by_title(title, year):  # Layer 2: Title+year search
    ...
    title_similarity(title_a, title_b) >= 0.85  # Threshold: 0.85
    ...

def _tmdb_translated_title(title, year, language):  # Layer 3 (TMDB only - not used)
    ...
```

**Functions Used in enrich_combined.py:**
- `normalize_title()` - Copied to enrich_combined.py with modifications
- `title_similarity()` - Copied to enrich_combined.py with 0.85 threshold
- Caching pattern - Adapted for Wikidata and Wikipedia

**Reference:** Critical for understanding fallback orchestration pattern

---

### Reference File: `main.py`
**Purpose:** IMDb scraping with robust retry logic (provides scraping patterns)

**Key Pattern (Lines 85-127):**
```python
# 3-retry strategy:
for attempt in range(3):
    # 5-second delay per IMDb request
    time.sleep(5)
    response = requests.get(url)
    
    # Fallback extraction methods:
    extract_mpaa_from_soup(response)  # Method 1: Span-based
    # Method 2: MPAA label search
    # Method 3: Release date inference (Pre-Code detection)
```

**Pre-Code Detection Logic:**
- Films released 1930-1934 → Likely Pre-Code (no MPAA)
- Use historical context for inference

**Pattern:** Adapted for `extract_mpaa_ratings()` in enrich_combined.py

---

### Cache Files (Auto-Generated)
**File 1:** `cache_wikidata_budgets.json`
- **Key Format:** `"title:year"` (e.g., `"The Godfather:1972"`)
- **Value:** `{"budget": 12000000, "currency": "USD", "timestamp": "2026-04-06"}`
- **Purpose:** Avoid repeated Wikidata SPARQL queries (slow API)
- **Lifecycle:** Created on first Layer 2 call, persisted across runs

**File 2:** `cache_wikipedia_budgets.json`
- **Key Format:** `"title:year"` (e.g., `"Citizen Kane:1941"`)
- **Value:** `{"budget": 1000000, "source_text": "...", "extraction_method": "regex", "timestamp": "2026-04-06"}`
- **Purpose:** Avoid repeated Wikipedia searches (moderate API)
- **Lifecycle:** Created on first Layer 3 call, persisted across runs

---

## API Configurations

### TMDB API v3
**Endpoint:** `https://api.themoviedb.org/3/`
**Environment Variable:** `TMDB_API_KEY`
**Authentication:** Query parameter `api_key=<key>`

**Key Endpoints Used:**
- `GET /find` - Find TMDB ID by IMDb ID
- `GET /search/movie` - Search for movie by title
- `GET /movie/{movie_id}` - Get movie details including budget

**Rate Limits:** ~40 requests/10 seconds (enforced)
**Response Timeout:** 10 seconds default
**Budget Data Coverage:** ~0-10% for pre-1960s films (normal behavior)

**Example Call:**
```python
response = requests.get(
    "https://api.themoviedb.org/3/find",
    params={
        "external_id": "tt0000001",
        "external_source": "imdb_id",
        "api_key": api_key
    }
)
```

---

### Wikidata SPARQL API
**Endpoint:** `https://query.wikidata.org/sparql`
**Authentication:** None (public endpoint)
**Query Language:** SPARQL 1.1

**Key Properties Used:**
- `wdt:P31 wd:Q11024` - Instance of film
- `wdt:P2130` - Production cost property
- `rdfs:label` - Title (English labels preferred)
- `wdt:P580` - Start date (release date)

**Rate Limits:** ~1 request/second (enforced via 0.5-second delays between calls)
**Response Timeout:** 12 seconds (slow API, set high timeout)
**Expected Response Time:** 5-12 seconds per query

**Example Query:**
```sparql
SELECT DISTINCT ?productionCost WHERE {
  ?film wdt:P31 wd:Q11024 .              # Film instance
  ?film rdfs:label "The Godfather"@en .  # English title match
  ?film wdt:P2130 ?productionCost .      # Production cost
} LIMIT 1
```

**Header Requirements:**
- `User-Agent: BUS682-MovieEnrichment/1.0`
- `Accept: application/sparql-results+json`

---

### Wikipedia API
**Endpoint:** `https://en.wikipedia.org/w/api.php?`
**Authentication:** None (public endpoint)
**Methods Used:**
- `action=query&list=search` - Search for articles
- `action=query&prop=extracts` - Get text extracts

**Rate Limits:** Moderate (1-2 seconds between requests recommended)
**Response Timeout:** 10 seconds
**Search Results:** Usually 1-5 articles per film title

**Example Search:**
```python
response = requests.get(
    "https://en.wikipedia.org/w/api.php",
    params={
        "action": "query",
        "list": "search",
        "srsearch": "The Godfather 1972",
        "format": "json"
    }
)
```

---

## Implementation Details

### Data Type Standardization

**Budget Values:**
- **Stored As:** Integer (US dollars)
- **Range:** 100,000 to 300,000,000 (typical for films)
- **Null Handling:** `None` or empty string if not found
- **Conversion:** "10 million" → 10,000,000

**Title Normalization:**
```python
def normalize_title(title):
    # Remove articles (a, an, the)
    # Remove punctuation
    # Convert to lowercase
    # Strip whitespace
    return cleaned_title
```

**Similarity Threshold:** 0.85 (from movie_clustering.py)
- `SequenceMatcher.ratio()` compares normalized titles
- Values: 0.0 (no match) to 1.0 (perfect match)
- Threshold 0.85 = 85% character similarity

### Caching Strategy

**Purpose:** Avoid API rate limiting and repeated expensive queries

**Implementation:**
1. Check if `title:year` exists in cache JSON
2. If found: Return cached value immediately
3. If not found: Query API, cache result, return
4. Persist cache to disk after each addition

**Cache Expiration:** No expiration (re-run analysis to refresh)

### Error Handling & Logging

**Logging Levels:**
- INFO: Each film processed, source found
- WARNING: API timeout, rate limit hit, regex extraction failed
- ERROR: Fatal errors (file not found, API key missing)

**Retry Logic:**
- **TMDB:** No retry (rate limited)
- **Wikidata:** Retry once on timeout (12-second timeout)
- **Wikipedia:** Retry twice on timeout (10-second timeout)
- **IMDb Scraping:** 3 retries with 2-second delays + 5-second page load

**Graceful Degradation:**
- If TMDB fails → Try Wikidata
- If Wikidata fails → Try Wikipedia
- If all fail → Mark as "not_found" (don't estimate)

---

## Current Status

### Phase 1: Budget Enrichment

**Process History:**
- **Process 7780** (10:34-10:48 AM): Initial enrichment with basic TMDB only
  - Status: ❌ TERMINATED (0% success rate)
  - Reason: Missing fallback logic

- **Process 20748** (10:48 AM+): Running with Layers 1-2 of TMDB improved
  - Status: ⏳ RUNNING
  - Note: Does NOT have final code with Layers 2-3 (Wikidata + Wikipedia)
  - Action: Will need restart with final code OR completion + re-run

**Expected Outcome (when complete):**
- ~50-100 films via TMDB API
- ~200-350 films via Wikidata SPARQL
- ~50-80 films via Wikipedia
- ~300 films remain as "not_found"
- **Total Enriched:** ~300-530 films (9-15% of dataset)
- **Overall Success Rate:** ~40-60% on missing-budget subset

### Phase 2: MPAA Rating Enrichment

**Status:** ⏳ RUNNING in parallel with Phase 1

**Progress:**
- Using 3-retry IMDb scraping pattern from main.py
- 5-second delays per request (IMDb rate limiting)
- Estimated 90%+ success rate

**Expected Completion:** ~5-7 hours from 10:48 AM start

### Cache Files Status
- `cache_wikidata_budgets.json` - Created on first Layer 2 call
- `cache_wikipedia_budgets.json` - Created on first Layer 3 call
- Both files persist between runs (incremental caching)

---

## Key Patterns & Functions

### Pattern 1: 3-Layer Fallback (from movie_clustering.py)
**Located:** movie_clustering.py lines 410-480

**Pattern:**
```python
def get_budget_by_imdb_id(imdb_id, title, year):
    # Layer 1
    budget, source = layer1_tmdb(imdb_id)
    if budget: return (budget, source)
    
    # Layer 2
    budget, source = layer2_wikidata(title, year)
    if budget: return (budget, source)
    
    # Layer 3
    budget, source = layer3_wikipedia(title, year)
    if budget: return (budget, source)
    
    # Fallback
    return (None, "not_found")
```

**Benefit:** Only requests from next source if previous fails

**Used In:** enrich_combined.py lines ~200-250

---

### Pattern 2: Title Similarity Matching (from movie_clustering.py)
**Located:** movie_clustering.py lines 430-450

**Functions:**
- `normalize_title(title)` - Standardize titles
- `title_similarity(a, b)` - Compare normalized titles with ratio 0.85+

**Usage:**
```python
for candidate in tmdb_search_results:
    if title_similarity(title, candidate["title"]) >= 0.85:
        return candidate  # Match found
```

**Threshold:** 0.85 = Allow minor variations (punctuation, articles)

**Example Matches:**
- "The Godfather" vs "Godfather" ✓
- "Citizen Kane" vs "Citizen Kane" ✓
- "Dr. Strangelove" vs "Dr Strangelove" ✓

---

### Pattern 3: 3-Retry IMDb Scraping (from main.py)
**Located:** main.py lines 85-127

**Pattern:**
```python
for attempt in range(3):
    try:
        time.sleep(5)  # Rate limiting
        response = requests.get(imdb_url)
        
        # Try extraction method 1
        mpaa = extract_mpaa_method1(response)
        if mpaa: return mpaa
        
        # Try extraction method 2
        mpaa = extract_mpaa_method2(response)
        if mpaa: return mpaa
        
        # Try extraction method 3 (Pre-Code inference)
        mpaa = extract_mpaa_method3(year)
        if mpaa: return mpaa
        
        time.sleep(2)  # Between-retry delay
    except Exception as e:
        continue
```

**Benefit:** Multiple extraction strategies + rate limiting compliance

**Used In:** enrich_combined.py `extract_mpaa_ratings()` method

---

### Pattern 4: Regex Budget Extraction
**From:** Wikipedia Layer 3 implementation

**Patterns Used:**
```regex
budget.*?\$\s*([\d,]+)           # "$10,000,000" format
production.*?cost.*?\$\s*([\d,]+) # "production cost $X" format
```

**Multiplier Handling:**
```python
if "million" in text.lower():
    budget *= 1_000_000
elif "thousand" in text.lower():
    budget *= 1_000
```

**Example Extraction:**
- Input: "The film had a production budget of $2.5 million"
- Extract: "2.5"
- Multiply: 2.5 * 1,000,000 = 2,500,000

---

### Pattern 5: Caching with JSON
**Format:**
```json
{
  "The Godfather:1972": {
    "budget": 6_000_000,
    "source": "wikidata",
    "timestamp": "2026-04-06T10:45:00"
  },
  "Citizen Kane:1941": {
    "budget": 1_000_000,
    "source": "wikipedia",
    "timestamp": "2026-04-06T10:47:00"
  }
}
```

**Key Format:** `"title:year"` (normalized)
**Persistence:** Loaded at start, saved after each film processed
**Benefit:** Avoid repeated API calls on re-runs

---

## Next Steps

### Immediate Action (Required)

**Action 1: Decide on Enrichment Restart**
- **Option A:** Wait for Process 20748 to complete (3-5 hours)
  - Then rerun with updated code to capture Layers 2-3
  - Advantage: Don't waste current compute
  - Disadvantage: Takes longer total

- **Option B:** Kill Process 20748 and restart immediately
  - Restarts with final code including Layers 2-3
  - Advantage: Get Wikidata + Wikipedia data sooner
  - Disadvantage: Waste current compute from old version

- **Recommendation:** **Option B** if Layer 2-3 data significantly improves results. Monitor current process first.

### Command to Run (Final Version with All 3 Layers)
```powershell
$env:TMDB_API_KEY="41295f19715b4ff8545eb9bd0a42917a"
python enrich_combined.py
```

### Post-Completion Tasks

**Task 1: Validate Results**
- Check `production_budget_source` distribution
- Verify counts: TMDB | Wikidata | Wikipedia | Not Found
- Compare against expected ranges (50-100, 200-350, 50-80, ~300)

**Task 2: Analyze Source Breakdown**
```python
# Expected output
df['production_budget_source'].value_counts()
# tmdb_api:    50-100
# wikidata:    200-350
# wikipedia:   50-80
# original:    2694
# not_found:   ~300
```

**Task 3: Data Quality Check**
- Plot budget distributions by source
- Check for outliers (unusually high/low)
- Verify no duplicates across layers

**Task 4: Complete MPAA Phase**
- Monitor Phase 2 completion
- Validate MPAA_rating_source values
- Ensure no data loss from original dataset

---

## Troubleshooting Reference

### Issue: "0% success rate" (like Process 7780)
**Cause:** Missing Layer 2 (Wikidata) and Layer 3 (Wikipedia)
**Solution:** Restart with updated enrich_combined.py that includes all 3 layers

### Issue: Wikidata SPARQL timeout (429 or 12s+ delays)
**Cause:** Rate limiting on Wikidata API
**Solution:** Already implemented - 0.5-second delays + 12-second timeout + caching
**Note:** Acceptable to see some timeouts; cache prevents repeats

### Issue: Wikipedia regex extraction empty
**Cause:** Budget info not in Wikipedia article infobox/text
**Solution:** Continue to next layer or mark as "not_found" (no estimation)

### Issue: Missing API key error
**Solution:** Set environment variable before running
```powershell
$env:TMDB_API_KEY="41295f19715b4ff8545eb9bd0a42917a"
```

### Issue: CSV encoding errors
**Refer to:** `/memories/repo/csv-encoding-note.md` for encoding details

---

## File Locations & Links

| File | Purpose | Location |
|------|---------|----------|
| enrich_combined.py | Main enrichment script | Root directory |
| movie_clustering.py | Reference for 3-layer pattern | Root directory |
| main.py | Reference for scraping patterns | Root directory |
| project_2_data_filled_with_api.csv | Input/output data | Root directory |
| cache_wikidata_budgets.json | Wikidata cache | Auto-created in root |
| cache_wikipedia_budgets.json | Wikipedia cache | Auto-created in root |

---

## Key Decisions Made

1. **3 Layers Only** - Constraint per user request (no Layer 4 estimation)
2. **Source Tracking Required** - Every value must indicate origin
3. **Wikidata Reliability** - Evaluated as ⭐⭐⭐⭐ for pre-1960s films
4. **0.85 Similarity Threshold** - Borrowed from movie_clustering.py, allows minor variations
5. **Rate Limiting Implementation** - Respects API constraints to avoid blocking
6. **Caching Strategy** - Persistent JSON caches reduce API load on re-runs

---

## Expected Timeline

| Task | Start | Duration | End |
|------|-------|----------|-----|
| Phase 1 Budget Enrichment | 10:48 AM | 3-5 hours | 2-3 PM |
| Phase 2 MPAA Scraping (parallel) | 10:48 AM | 5-7 hours | 4-5 PM |
| Combined Completion | 10:48 AM | ~5-7 hours | 4-5 PM |
| Post-Validation | ~4 PM | 30 minutes | 4:30 PM |

---

## Contact & Documentation

**Project Lead:** BUS682 Instructor
**Dataset:** TMDB, IMDb, Wikidata, Wikipedia
**Version:** 3-layer enrichment with source tracking (Final)
**Last Updated:** April 6, 2026 10:58 AM

---

**END OF PROJECT CONTEXT**

This document provides complete context for any AI agent to understand:
- ✅ What the project is doing
- ✅ How the 3-layer strategy works
- ✅ What code files exist and their purposes
- ✅ API configurations and patterns
- ✅ Current status and expected outcomes
- ✅ Troubleshooting guidance
- ✅ Next steps for completion

Refer to this document in future conversations for full project context.
