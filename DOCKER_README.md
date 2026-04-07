# Docker Setup for Movie Data Enrichment

This Docker setup runs the movie enrichment validation script in a containerized environment.

## Prerequisites

**Install Docker:**
- **Windows:** Download [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop)
- Ensure Docker is running before proceeding

## Quick Start

### Option 1: Using Docker Compose (Easiest)

```powershell
cd C:\Users\manny\Documents\BUS682_Project2
docker-compose up --build
```

This will:
1. ✅ Build the Docker image
2. ✅ Start the enrichment process
3. ✅ Output logs to your terminal
4. ✅ Save results to `./output/` folder

### Option 2: Using Docker CLI

```powershell
# Build the image
docker build -t movie-enrichment .

# Run the container
docker run -it `
  -e TMDB_API_KEY=575a07d93b4face7cb66e921afb5de98 `
  -v "$(pwd)/output:/app/output" `
  -v "$(pwd)/project_2_data_filled_with_api.csv:/app/project_2_data_filled_with_api.csv" `
  movie-enrichment
```

## What the Script Does

**Phase 1: Budget Validation & Enrichment**
- Scrapes budgets from ALL 3,438 films using 4-layer strategy:
  1. TMDB API
  2. IMDb website scraping
  3. Wikidata SPARQL
  4. Wikipedia parsing
- Creates **"Budget_Check"** column: Compares scraped vs existing budgets
- Creates **"Added_Budgets"** column: New budgets for films that were missing them

**Phase 2: MPAA Rating Scraping**
- Scrapes MPAA ratings from IMDb with 3-retry strategy
- Creates **"MPAA_Rating"** and **"MPAA_Source"** columns

**Phase 3: Data Quality Report**
- Reports validation statistics
- Shows budget matches vs mismatches
- Reports MPAA scraping success rate

## Output Files

**Location:** `./output/`

- **project_2_data_enriched_with_validation.csv** - Final enriched dataset with:
  - All original columns preserved
  - `Budget_Check` - Validation results for existing budgets
  - `Added_Budgets` - New budgets found from sources
  - `Budget_Source` - Which layer provided the budget
  - `MPAA_Rating` - Scraped MPAA ratings
  - `MPAA_Source` - Source of rating (imdb_scraping)

## Monitoring Progress

### View logs in real-time:
```powershell
# If using docker-compose
docker-compose logs -f

# If using docker run (command will show logs directly)
```

### Check container status:
```powershell
docker ps
docker ps -a  # Show all containers (including stopped ones)
```

## Stop the Process

```powershell
# Graceful shutdown
docker-compose down

# Or force stop
docker stop movie_enrichment
```

## Clean Up

```powershell
# Remove container
docker rm movie_enrichment

# Remove image
docker rmi movie-enrichment

# Remove all (containers + images + volumes)
docker-compose down -v
```

## Troubleshooting

### Error: "Cannot connect to Docker daemon"
→ Make sure Docker Desktop is running

### Error: "TMDB_API_KEY not set"
→ The environment variable is already set in `docker-compose.yml`
→ If running manual `docker run`, include the `-e` flag

### Port conflicts
→ This script doesn't use any ports, so this shouldn't be an issue

### Low disk space
→ Docker images can be large; ensure you have ~2GB free

## Estimated Runtime

- **Total runtime:** 4-8 hours
- **Budget validation phase:** 2-4 hours (3,438 films × 4 layers)
- **MPAA scraping phase:** 2-4 hours (3,438 films × 3 retries max)

## Environment Variables

Located in `docker-compose.yml`:
- `TMDB_API_KEY` - Your TMDB API key
- `PYTHONUNBUFFERED=1` - Ensures logs are printed in real-time

To change the API key, edit `docker-compose.yml` or pass with `-e` flag:
```powershell
docker run -e TMDB_API_KEY="your_new_key" ...
```

## Next Steps

1. Run `docker-compose up --build`
2. Wait for completion (4-8 hours)
3. Check `./output/project_2_data_enriched_with_validation.csv`
4. Analyze the `Budget_Check` and `Added_Budgets` columns
5. Review MPAA ratings in the `MPAA_Rating` column

Enjoy your enriched dataset! 🎬
