# SETUP INSTRUCTIONS FOR DATA ENRICHMENT SCRIPT

## Overview
The script `enrich_missing_data.py` will:
1. **Fill 744 missing production budgets** using TMDB API + IMDb ID lookup
2. **Fetch MPAA ratings** for all 3,438 films using OMDB API
3. **Save enriched dataset** as `project_2_data_enriched_v2.csv`

## Prerequisites

You need API keys from:
- **TMDB** (The Movie Database): https://www.themoviedb.org/settings/api
- **OMDB** (The Open Movie Database): http://www.omdbapi.com/apikey.aspx

Both offer free tiers with sufficient limits for this project.

## Option 1: Set Environment Variables (Recommended)

### Windows PowerShell:
```powershell
# Set temporary environment variables
$env:TMDB_API_KEY="your_tmdb_api_key_here"
$env:OMDB_API_KEY="your_omdb_api_key_here"

# Run the script
python enrich_missing_data.py
```

### Windows Command Prompt:
```cmd
set TMDB_API_KEY=your_tmdb_api_key_here
set OMDB_API_KEY=your_omdb_api_key_here
python enrich_missing_data.py
```

### Mac/Linux:
```bash
export TMDB_API_KEY="your_tmdb_api_key_here"
export OMDB_API_KEY="your_omdb_api_key_here"
python enrich_missing_data.py
```

## Option 2: Create .env File

1. Create a file named `.env` in this directory:
```
TMDB_API_KEY=your_tmdb_api_key_here
OMDB_API_KEY=your_omdb_api_key_here
```

2. Run the script:
```bash
python enrich_missing_data.py
```

## Option 3: Run Interactively

Just run:
```bash
python enrich_missing_data.py
```

The script will prompt you to enter your API keys.

## Expected Output

The script will:
- Fill budgets for ~600-700 out of 744 missing films (success rate depends on TMDB coverage)
- Fetch MPAA ratings for ~3,200+ out of 3,438 films (success rate depends on OMDB coverage)
- Generate a detailed log showing which films were enriched
- Save the output as `project_2_data_enriched_v2.csv`

## Estimated Runtime

- **Budget filling**: ~15-20 minutes (with API rate limiting)
- **MPAA rating fetching**: ~30-40 minutes (with API rate limiting)
- **Total**: ~45-60 minutes

## Output Columns

The enriched CSV will include:
- All original columns from `project_2_data_filled_with_api.csv`
- **`production_budget`** (updated with TMDB data)
- **`production_budget_source`** (updated to "tmdb_api_via_imdb" if filled)
- **`mpaa_rating`** (NEW - populated from OMDB)
- **`mpaa_rating_source`** (NEW - "omdb_api" or "original_data")

## Troubleshooting

**Issue**: "Invalid API key"
- **Solution**: Verify your API keys are correct by testing them manually at the API websites

**Issue**: "Rate limit exceeded"
- **Solution**: The script includes automatic rate limiting (1-2 second delays). If you hit limits, increase delays in code.

**Issue**: Script takes too long
- **Solution**: This is normal - APIs are rate limited to protect servers. Full enrichment takes ~45-60 minutes.

## Next Steps

After enrichment, merge the enriched data with Phase 1 analysis:
```python
import pandas as pd

df_enriched = pd.read_csv('project_2_data_enriched_v2.csv')
df_phase1 = pd.read_csv('project_2_data_filled_with_api_with_efficiency.csv')

# Merge on IMDb ID
df_merged = df_phase1.merge(
    df_enriched[['imdb_id', 'production_budget', 'mpaa_rating']],
    on='imdb_id',
    how='left',
    suffixes=('', '_from_enrichment')
)

# Use enriched budget if available
df_merged['production_budget'] = df_merged['production_budget_from_enrichment'].fillna(df_merged['production_budget'])
df_merged = df_merged.drop('production_budget_from_enrichment', axis=1)

df_merged.to_csv('project_2_data_complete.csv', index=False)
```
