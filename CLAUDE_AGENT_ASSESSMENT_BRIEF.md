# BUS682 Project 2 - Claude Agent Assessment Brief

Generated: 2026-04-06

## 1) Session Recap (What Was Done In This Conversation)

- Reviewed the process/run guide and captured reusable workflow notes from [RUN_ALL_PROCESSES.md](RUN_ALL_PROCESSES.md).
- Compared [project_2_data.xlsx.csv](project_2_data.xlsx.csv) with [api_usage_with_box_office.csv](api_usage_with_box_office.csv).
- Built API override outputs:
  - [final_api_usage_overridden.csv](final_api_usage_overridden.csv)
  - [final_api_usage_overridden_validated.csv](final_api_usage_overridden_validated.csv)
  - [amount_mismatch_report.csv](amount_mismatch_report.csv)
- Validated override consistency:
  - Amount mismatches against Project 2 reference: 0 in [amount_mismatch_report.csv](amount_mismatch_report.csv).
- Created inferred factor reverse-mapping:
  - [factor_reverse_mapping.csv](factor_reverse_mapping.csv)
- Created merged Project 2 + API reference output with source and success metrics:
  - [project_2_data_filled_with_api.csv](project_2_data_filled_with_api.csv)
- Added budget-efficiency success columns in:
  - [project_2_data_filled_with_api_with_efficiency.csv](project_2_data_filled_with_api_with_efficiency.csv)
- Added script to fetch missing production budgets from TMDB API:
  - [fill_missing_budgets.py](fill_missing_budgets.py)
- Current blocker noted during session:
  - `TMDB_API_KEY` was not set in shell, so live budget backfill was prepared but not executed.

## 2) Current Data State (Important)

- Project rows: 3438.
- API rows: 3438.
- Revenue fields were fully aligned for matched IDs.
- Missing `production_budget` rows remain in Project-derived outputs until TMDB budget backfill is run.
- Budget success metrics are available only for rows where `production_budget` is present.

## 3) Recommended Immediate Next Step For Claude

1. Set `TMDB_API_KEY` in environment.
2. Run [fill_missing_budgets.py](fill_missing_budgets.py) on [project_2_data_filled_with_api_with_efficiency.csv](project_2_data_filled_with_api_with_efficiency.csv).
3. Recompute/rank by budget efficiency (`budget_efficiency_ratio`) and validate fill rate.
4. Review low-confidence title/year matches if any `tmdb_api_title_year` fills occur.

## 4) File Inventory Summary (Top-Level + Subfolder)

### Project Meta / Environment

- [.gcloudignore](.gcloudignore): Ignore rules for Google Cloud build/deploy context.
- [.gitignore](.gitignore): Git ignore rules.
- [.git/](.git/): Git metadata.
- [.venv/](.venv/): Local Python virtual environment.
- [.vscode/](.vscode/): VS Code workspace settings/tasks/extensions metadata.

### Core Documentation

- [README.md](README.md): Main project overview and workflow summary.
- [RUN_ALL_PROCESSES.md](RUN_ALL_PROCESSES.md): Detailed runbook for IMDb, Rotten Tomatoes, clustering, and cloud build usage.
- [RUN_ALL_PROCESSES.txt](RUN_ALL_PROCESSES.txt): Text variant of run instructions.

### Core Pipelines / Source Scripts

- [main.py](main.py): IMDb scraping workflow entry (similar role to scraper script).
- [scraper_imdb.py](scraper_imdb.py): IMDb scraper, reads input list and writes ratings output.
- [scraper_rottentomatoes.py](scraper_rottentomatoes.py): Rotten Tomatoes scraping pipeline.
- [movie_clustering.py](movie_clustering.py): Clustering/enrichment using TMDB, Wikipedia, Wikidata, translation caches.
- [cluster_features.py](cluster_features.py): Feature-level clustering utility.
- [enrich_box_office.py](enrich_box_office.py): Adds/repairs box office via reference and TMDB fallback.
- [fill_missing_budgets.py](fill_missing_budgets.py): New script added in this session to backfill missing production budgets from TMDB.
- [debug_rt.py](debug_rt.py): Debug helper for Rotten Tomatoes parsing/inspection.

### Container / Cloud Build Config

- [Dockerfile](Dockerfile): Container definition for RT-oriented run.
- [Dockerfile.imdb](Dockerfile.imdb): IMDb scraper container definition.
- [Dockerfile.clustering](Dockerfile.clustering): Clustering container definition.
- [cloudbuild.imdb.yaml](cloudbuild.imdb.yaml): GCP build config for IMDb image.
- [cloudbuild.clustering.yaml](cloudbuild.clustering.yaml): GCP build config for clustering image.

### Dependency Manifests

- [requirements.txt](requirements.txt): General dependencies.
- [requirements.clustering.txt](requirements.clustering.txt): Clustering/enrichment-specific dependencies.

### Primary Input / Base Datasets

- [project_2_data.xlsx](project_2_data.xlsx): Original Project 2 workbook.
- [project_2_data.xlsx.csv](project_2_data.xlsx.csv): CSV-exported Project 2 base table.
- [api_usage_input.csv](api_usage_input.csv): API usage input table.
- [factor descriptions.csv](factor%20descriptions.csv): Factor ID/name/description reference.
- [factor descriptions.xlsx](factor%20descriptions.xlsx): Spreadsheet version of factor descriptions.

### Derived / Merged / Validation Outputs

- [api_usage_with_box_office.csv](api_usage_with_box_office.csv): API usage with box office fields.
- [final_api_usage_overridden_validated.csv](final_api_usage_overridden_validated.csv): Validated override dataset (source and match markers included).
- [amount_mismatch_report.csv](amount_mismatch_report.csv): Validation mismatch report.
- [project_2_data_filled_with_api.csv](project_2_data_filled_with_api.csv): Project 2 enriched with API reference fields and money-success metrics.
- [project_2_data_filled_with_api_with_efficiency.csv](project_2_data_filled_with_api_with_efficiency.csv): Added budget efficiency columns.
- [results_fixed_with_box_office.csv](results_fixed_with_box_office.csv): Large downstream result set with box office.
- [results_fixed_with_box_office_v2.csv](results_fixed_with_box_office_v2.csv): Revised version of above.
- [factor_reverse_mapping.csv](factor_reverse_mapping.csv): Inferred reverse mapping from factors to granular trait bundles.

### Caches / Data Snapshots / Logs

- [cache_translations.json](cache_translations.json): Translation cache used by enrichment workflow.
- [tmdb_movies.json](tmdb_movies.json): TMDB data cache/snapshot.
- [clustering_pid.txt](clustering_pid.txt): Last clustering process ID record.
- [clustering_run.log](clustering_run.log): Clustering run stdout log.
- [clustering_err.log](clustering_err.log): Clustering run stderr log.

### Subfolder: PROJECT_HOLLYWOOD

- [PROJECT_HOLLYWOOD/Project_HOLLYWOOD (1).ipynb](PROJECT_HOLLYWOOD/Project_HOLLYWOOD%20(1).ipynb): Notebook analysis artifact (OMDB-related usage noted in run guide).
- [PROJECT_HOLLYWOOD/DS_Store](PROJECT_HOLLYWOOD/DS_Store): System metadata file.

## 5) Assumptions / Caveats

- The factor reverse mapping in [factor_reverse_mapping.csv](factor_reverse_mapping.csv) is inferential, not a direct inversion of original factor-loading matrices.
- Budget backfill cannot execute without valid TMDB credentials.
- Efficiency metrics are undefined where budget is missing or zero.

## 6) Minimal Command Hints For Claude

- Activate venv (PowerShell):
  - `./.venv/Scripts/Activate.ps1`
- Set TMDB key:
  - `$env:TMDB_API_KEY = "<YOUR_KEY>"`
- Fill budgets:
  - `python fill_missing_budgets.py --input project_2_data_filled_with_api_with_efficiency.csv --output project_2_data_filled_with_api_budget_filled.csv`

## 7) Assessment Targets For Claude

- Verify data lineage and reproducibility from source files to final artifacts.
- Audit API fill confidence for title/year fallbacks.
- Validate whether efficiency metric choice should be ratio only, score only, or both.
- Propose handling strategy for remaining missing budgets and outlier revenues.
