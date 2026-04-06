#!/usr/bin/env python3
"""
Enrichment Script for Missing Movie Data
- Fills missing production budgets (744 films) using TMDB API + IMDb ID lookup
- Fetches MPAA ratings (all 3,438 films) using OMDB API
- Saves enriched dataset
"""

import os
import pandas as pd
import requests
import logging
from typing import Optional, Dict, Tuple
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API Configuration
TMDB_BASE_URL = "https://api.themoviedb.org/3"
OMDB_BASE_URL = "http://www.omdbapi.com"

class MovieDataEnricher:
    def __init__(self, tmdb_api_key: str, omdb_api_key: str):
        self.tmdb_key = tmdb_api_key
        self.omdb_key = omdb_api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })
        
    def _is_missing(self, value) -> bool:
        """Check if a value is missing/null/NaN"""
        if value is None or pd.isna(value):
            return True
        text = str(value).strip().lower()
        return text in {"", "na", "n/a", "nan", "none", "not found"}
    
    # ==================== TMDB BUDGET METHODS ====================
    
    def get_tmdb_id_by_imdb(self, imdb_id: str) -> Optional[int]:
        """Find TMDB ID using IMDb ID"""
        if not imdb_id or not str(imdb_id).startswith("tt"):
            return None
        
        try:
            response = self.session.get(
                f"{TMDB_BASE_URL}/find/{imdb_id}",
                params={"api_key": self.tmdb_key, "external_source": "imdb_id"},
                timeout=10
            )
            response.raise_for_status()
            matches = response.json().get("movie_results", [])
            if matches:
                return matches[0].get("id")
        except requests.RequestException as e:
            logger.warning(f"Error looking up TMDB ID for {imdb_id}: {e}")
        
        return None
    
    def get_budget_by_tmdb_id(self, tmdb_id: int) -> Optional[int]:
        """Fetch budget from TMDB using TMDB ID"""
        try:
            response = self.session.get(
                f"{TMDB_BASE_URL}/movie/{tmdb_id}",
                params={"api_key": self.tmdb_key},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            budget = data.get("budget")
            if budget and budget > 0:
                return int(budget)
        except requests.RequestException as e:
            logger.warning(f"Error fetching TMDB data for ID {tmdb_id}: {e}")
        
        return None
    
    def get_budget_by_imdb_id(self, imdb_id: str) -> Tuple[Optional[int], str]:
        """Get budget for a film using IMDb ID. Returns (budget, source)"""
        tmdb_id = self.get_tmdb_id_by_imdb(imdb_id)
        if tmdb_id:
            budget = self.get_budget_by_tmdb_id(tmdb_id)
            if budget:
                return budget, "tmdb_api_via_imdb"
        
        return None, "not_found"
    
    # ==================== OMDB MPAA RATING METHODS ====================
    
    def get_mpaa_rating_by_imdb(self, imdb_id: str) -> Tuple[Optional[str], str]:
        """Fetch MPAA rating from OMDB using IMDb ID. Returns (rating, source)"""
        if not imdb_id or not str(imdb_id).startswith("tt"):
            return None, "invalid_imdb_id"
        
        try:
            response = self.session.get(
                OMDB_BASE_URL,
                params={"i": imdb_id, "apikey": self.omdb_key, "type": "movie"},
                timeout=10
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("Response") == "True":
                rating = data.get("Rated")
                if rating and rating not in ["N/A", "", None]:
                    return rating, "omdb_api"
        except requests.RequestException as e:
            logger.warning(f"Error fetching OMDB data for {imdb_id}: {e}")
        
        return None, "not_found"
    
    # ==================== MAIN ENRICHMENT METHOD ====================
    
    def enrich_dataset(self, input_csv: str, output_csv: str) -> pd.DataFrame:
        """
        Main enrichment pipeline:
        1. Load data
        2. Fill missing budgets
        3. Fetch MPAA ratings
        4. Save enriched dataset
        """
        
        logger.info("Loading data...")
        df = pd.read_csv(input_csv)
        
        # Initialize new columns if they don't exist
        if 'mpaa_rating' not in df.columns:
            df['mpaa_rating'] = None
        if 'mpaa_rating_source' not in df.columns:
            df['mpaa_rating_source'] = 'original_data'
        
        # Store original counts
        original_budget_count = df['production_budget'].notna().sum()
        original_mpaa_count = df['mpaa_rating'].notna().sum()
        
        # ========== PHASE 1: Fill Missing Budgets ==========
        logger.info(f"\n=== PHASE 1: FILLING MISSING BUDGETS ({df['production_budget'].isna().sum()} films) ===")
        
        missing_budget_indices = df[df['production_budget'].isna()].index
        budget_filled = 0
        
        for idx, row in enumerate(missing_budget_indices, 1):
            imdb_id = df.at[row, 'imdb_id']
            title = df.at[row, 'title']
            
            budget, source = self.get_budget_by_imdb_id(imdb_id)
            
            if budget:
                df.at[row, 'production_budget'] = budget
                if 'production_budget_source' in df.columns:
                    df.at[row, 'production_budget_source'] = source
                budget_filled += 1
                logger.info(f"  [{idx}/{len(missing_budget_indices)}] {title} ({imdb_id}): ${budget:,}")
            else:
                logger.info(f"  [{idx}/{len(missing_budget_indices)}] {title} ({imdb_id}): NOT FOUND")
            
            # Rate limiting
            if idx % 10 == 0:
                time.sleep(1)
        
        new_budget_count = df['production_budget'].notna().sum()
        logger.info(f"\nBudget Summary:")
        logger.info(f"  Before: {original_budget_count} films")
        logger.info(f"  Filled: {budget_filled} films")
        logger.info(f"  After:  {new_budget_count} films")
        logger.info(f"  Success Rate: {budget_filled / len(missing_budget_indices) * 100:.1f}%")
        
        # ========== PHASE 2: Fetch MPAA Ratings ==========
        logger.info(f"\n=== PHASE 2: FETCHING MPAA RATINGS (all {len(df)} films) ===")
        
        mpaa_filled = 0
        mpaa_already_had = 0
        
        for idx, row in enumerate(df.iterrows(), 1):
            row_idx, row_data = row
            imdb_id = row_data['imdb_id']
            title = row_data['title']
            
            # Check if already has MPAA rating
            if pd.notna(row_data['mpaa_rating']):
                mpaa_already_had += 1
                continue
            
            rating, source = self.get_mpaa_rating_by_imdb(imdb_id)
            
            if rating:
                df.at[row_idx, 'mpaa_rating'] = rating
                df.at[row_idx, 'mpaa_rating_source'] = source
                mpaa_filled += 1
                logger.info(f"  [{idx}/{len(df)}] {title} ({imdb_id}): {rating}")
            
            # Rate limiting
            if idx % 10 == 0:
                time.sleep(0.5)
        
        new_mpaa_count = df['mpaa_rating'].notna().sum()
        logger.info(f"\nMPAA Rating Summary:")
        logger.info(f"  Already had: {mpaa_already_had} films")
        logger.info(f"  Newly fetched: {mpaa_filled} films")
        logger.info(f"  Total: {new_mpaa_count} films")
        logger.info(f"  Still missing: {len(df) - new_mpaa_count} films")
        
        # ========== SAVE ENRICHED DATA ==========
        logger.info(f"\nSaving enriched dataset to {output_csv}...")
        df.to_csv(output_csv, index=False)
        
        logger.info(f"\n=== ENRICHMENT COMPLETE ===")
        logger.info(f"Output file: {output_csv}")
        logger.info(f"Total records: {len(df)}")
        
        return df


def main():
    """Main execution function"""
    import sys
    
    # Get API keys
    tmdb_api_key = os.getenv('TMDB_API_KEY')
    omdb_api_key = os.getenv('OMDB_API_KEY')
    
    if not tmdb_api_key:
        tmdb_api_key = input("Enter your TMDB API key: ").strip()
    
    if not omdb_api_key:
        omdb_api_key = input("Enter your OMDB API key: ").strip()
    
    if not tmdb_api_key or not omdb_api_key:
        logger.error("API keys are required!")
        sys.exit(1)
    
    # Initialize enricher
    enricher = MovieDataEnricher(tmdb_api_key, omdb_api_key)
    
    # Run enrichment
    input_file = 'project_2_data_filled_with_api.csv'
    output_file = 'project_2_data_enriched_v2.csv'
    
    enricher.enrich_dataset(input_file, output_file)
    
    logger.info(f"\nDone! Enriched data saved to {output_file}")


if __name__ == "__main__":
    main()
