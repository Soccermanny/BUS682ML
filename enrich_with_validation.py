#!/usr/bin/env python3
"""
Validation Enrichment Script - Budget & MPAA with Data Quality Checks
======================================================================
1. Scrapes budgets from ALL films (4-layer strategy)
2. For existing budgets: Creates "Budget Check" column comparing original vs scraped
3. For missing budgets: Creates "Added budgets" column with newly found budgets
4. Scrapes MPAA ratings with 3-retry strategy
5. Validates data quality before final output
"""

import os
import pandas as pd
import requests
import logging
from typing import Optional, Tuple
import time
from bs4 import BeautifulSoup
from datetime import datetime
import re
import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import warnings
warnings.filterwarnings('ignore')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"

class ValidationEnricher:
    """Enriches movie data with validation and quality checks"""
    
    def __init__(self, tmdb_api_key: str):
        self.tmdb_key = tmdb_api_key
        self.session = self._create_session()
        self.wikidata_cache = {}
        self.wikipedia_cache = {}
    
    def _create_session(self):
        """Create requests session with retry strategy"""
        session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session
    
    # ==================== BUDGET LAYERS ====================
    
    def get_tmdb_id_by_imdb(self, imdb_id: str) -> Optional[int]:
        """Layer 1: Get TMDB ID from IMDb ID"""
        try:
            response = self.session.get(
                f"{TMDB_BASE_URL}/find/{imdb_id}",
                params={"api_key": self.tmdb_key, "external_source": "imdb_id"},
                timeout=10
            )
            response.raise_for_status()
            results = response.json().get("movie_results", [])
            if results:
                return results[0].get("id")
        except requests.RequestException as e:
            logger.debug(f"TMDB lookup failed for {imdb_id}: {e}")
        return None
    
    def get_budget_by_tmdb_id(self, tmdb_id: int) -> Optional[int]:
        """Get budget from TMDB"""
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
            logger.debug(f"TMDB budget fetch failed for {tmdb_id}: {e}")
        return None
    
    def get_budget_from_imdb_scraping(self, imdb_id: str) -> Optional[int]:
        """Layer 2: Scrape budget from IMDb website"""
        try:
            url = f"https://www.imdb.com/title/{imdb_id}/"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = self.session.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for budget in metadata lists
            for ul in soup.find_all('ul', class_='ipc-metadata-list'):
                for li in ul.find_all('li'):
                    text = li.get_text(strip=True)
                    if 'Budget' in text or 'Production Budget' in text:
                        match = re.search(r'\$\s*([\d,]+(?:\.\d+)?)\s*(?:million|M)?', text, re.IGNORECASE)
                        if match:
                            amount = float(match.group(1).replace(',', ''))
                            if 'million' in text.lower():
                                amount *= 1_000_000
                            return int(amount)
            
            # Check structured data
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and 'budget' in data:
                        match = re.search(r'[\d,]+', str(data['budget']).replace(',', ''))
                        if match:
                            return int(match.group())
                except:
                    continue
        
        except requests.RequestException as e:
            logger.debug(f"IMDb scraping failed for {imdb_id}: {e}")
        
        return None
    
    def get_budget_from_wikidata(self, title: str, year: Optional[int] = None) -> Optional[int]:
        """Layer 3: Query Wikidata for production cost"""
        try:
            cache_key = f"{title}:{year}"
            if cache_key in self.wikidata_cache:
                return self.wikidata_cache[cache_key]
            
            query = f"""
            SELECT DISTINCT ?productionCost WHERE {{
              ?film wdt:P31 wd:Q11024 .
              ?film rdfs:label "{title}"@en .
              OPTIONAL {{ ?film wdt:P2130 ?productionCost . }}
            }} LIMIT 1
            """
            
            response = self.session.get(
                'https://query.wikidata.org/sparql',
                params={'query': query, 'format': 'json'},
                headers={'User-Agent': 'BUS682-MovieValidation/1.0'},
                timeout=12
            )
            response.raise_for_status()
            results = response.json().get('results', {}).get('bindings', [])
            
            if results and 'productionCost' in results[0]:
                budget = int(float(results[0]['productionCost']['value']))
                self.wikidata_cache[cache_key] = budget
                return budget
        
        except Exception as e:
            logger.debug(f"Wikidata query failed for '{title}': {e}")
        
        return None
    
    def get_budget_from_wikipedia(self, title: str, year: Optional[int] = None) -> Optional[int]:
        """Layer 4: Search Wikipedia and extract budget"""
        try:
            cache_key = f"{title}:{year}"
            if cache_key in self.wikipedia_cache:
                return self.wikipedia_cache[cache_key]
            
            # Search Wikipedia
            response = self.session.get(
                'https://en.wikipedia.org/w/api.php',
                params={
                    'action': 'query',
                    'list': 'search',
                    'srsearch': f"{title} {year}" if year else title,
                    'format': 'json'
                },
                timeout=10
            )
            response.raise_for_status()
            results = response.json().get('query', {}).get('search', [])
            
            if not results:
                return None
            
            # Get article text
            article_title = results[0]['title']
            response = self.session.get(
                'https://en.wikipedia.org/w/api.php',
                params={
                    'action': 'query',
                    'titles': article_title,
                    'prop': 'extracts',
                    'explaintext': True,
                    'format': 'json'
                },
                timeout=10
            )
            response.raise_for_status()
            pages = response.json().get('query', {}).get('pages', {})
            
            if not pages:
                return None
            
            text = list(pages.values())[0].get('extract', '')
            
            # Extract budget with regex
            patterns = [
                r'budget.*?\$\s*([\d,]+)',
                r'production.*?cost.*?\$\s*([\d,]+)',
                r'\$\s*([\d,]+)\s*million'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    amount = float(match.group(1).replace(',', ''))
                    if 'million' in text[match.start():match.start()+50].lower():
                        amount *= 1_000_000
                    budget = int(amount)
                    self.wikipedia_cache[cache_key] = budget
                    return budget
        
        except Exception as e:
            logger.debug(f"Wikipedia search failed for '{title}': {e}")
        
        return None
    
    def scrape_budget_all_layers(self, imdb_id: str, title: str, year: Optional[int] = None) -> Tuple[Optional[int], str]:
        """Scrape budget from all 4 layers"""
        
        # Layer 1: TMDB
        tmdb_id = self.get_tmdb_id_by_imdb(imdb_id)
        if tmdb_id:
            budget = self.get_budget_by_tmdb_id(tmdb_id)
            if budget:
                return budget, "tmdb_api"
        
        time.sleep(0.3)
        
        # Layer 2: IMDb scraping
        budget = self.get_budget_from_imdb_scraping(imdb_id)
        if budget:
            return budget, "imdb_scraping"
        
        time.sleep(0.3)
        
        # Layer 3: Wikidata
        budget = self.get_budget_from_wikidata(title, year)
        if budget:
            return budget, "wikidata"
        
        time.sleep(1)  # Wikidata is slow
        
        # Layer 4: Wikipedia
        budget = self.get_budget_from_wikipedia(title, year)
        if budget:
            return budget, "wikipedia"
        
        return None, "not_found"
    
    # ==================== MPAA SCRAPING ====================
    
    def get_mpaa_rating(self, imdb_id: str) -> Optional[str]:
        """Scrape MPAA rating from IMDb with 3 retries"""
        for attempt in range(3):
            try:
                url = f"https://www.imdb.com/title/{imdb_id}/"
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                response = self.session.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for MPAA rating in various locations
                for ul in soup.find_all('ul', class_='ipc-metadata-list'):
                    for li in ul.find_all('li'):
                        text = li.get_text(strip=True)
                        if any(rating in text for rating in ['G', 'PG', 'PG-13', 'R', 'NC-17', 'Not Rated', 'Not rated']):
                            # Extract rating
                            match = re.search(r'(G|PG-13|PG|R|NC-17|Not Rated|Not rated)', text)
                            if match:
                                return match.group(1)
                
                time.sleep(2)  # Rate limiting
                
            except requests.RequestException as e:
                logger.debug(f"MPAA scrape attempt {attempt+1} failed for {imdb_id}: {e}")
                time.sleep(2)
        
        return None
    
    # ==================== MAIN ENRICHMENT ====================
    
    def enrich_with_validation(self, input_csv: str, output_csv: str):
        """Main enrichment with budget validation"""
        
        logger.info("Loading corrected data...")
        df = pd.read_csv(input_csv)
        
        total_films = len(df)
        logger.info(f"Processing {total_films:,} films with validation...")
        
        # Initialize new columns
        df['Budget_Check'] = None  # For existing budgets: comparison result
        df['Added_Budgets'] = None  # For missing budgets: newly found data
        df['Budget_Source'] = 'original'  # Track source
        df['MPAA_Rating'] = None
        df['MPAA_Source'] = None
        
        films_with_existing = df['production_budget'].notna().sum()
        films_missing = df['production_budget'].isna().sum()
        
        logger.info(f"Films with existing budgets: {films_with_existing:,}")
        logger.info(f"Films missing budgets: {films_missing:,}")
        
        logger.info("\n=== PHASE 1: BUDGET VALIDATION & ENRICHMENT ===\n")
        
        for idx, row in df.iterrows():
            imdb_id = row['imdb_id']
            title = row['title']
            year = int(row['release_year']) if pd.notna(row['release_year']) else None
            existing_budget = row['production_budget']
            
            if (idx + 1) % 100 == 0:
                logger.info(f"  [{idx+1:,}/{total_films:,}] {title}")
            
            # Scrape budget from all layers
            scraped_budget, source = self.scrape_budget_all_layers(imdb_id, title, year)
            
            if scraped_budget:
                if pd.notna(existing_budget):
                    # VALIDATION: Compare scraped vs existing
                    match = "MATCH" if abs(scraped_budget - existing_budget) < 1000 else "MISMATCH"
                    df.at[idx, 'Budget_Check'] = f"{match}: Scraped ${scraped_budget:,} vs Existing ${existing_budget:,}"
                    logger.debug(f"  Budget Check [{idx+1}]: {match}")
                else:
                    # NEW DATA: Add to Added_Budgets column
                    df.at[idx, 'Added_Budgets'] = scraped_budget
                    df.at[idx, 'Budget_Source'] = source
                    logger.debug(f"  Added budget [{idx+1}]: ${scraped_budget:,} from {source}")
            else:
                if pd.isna(existing_budget):
                    df.at[idx, 'Budget_Check'] = "NOT_FOUND_IN_ANY_SOURCE"
        
        logger.info("\n=== PHASE 2: MPAA RATING SCRAPING ===\n")
        
        for idx, row in df.iterrows():
            imdb_id = row['imdb_id']
            title = row['title']
            
            if (idx + 1) % 100 == 0:
                logger.info(f"  [{idx+1:,}/{total_films:,}] {title}")
            
            # Scrape MPAA rating
            rating = self.get_mpaa_rating(imdb_id)
            if rating:
                df.at[idx, 'MPAA_Rating'] = rating
                df.at[idx, 'MPAA_Source'] = 'imdb_scraping'
        
        # ====================  SAVE & REPORT ====================
        
        logger.info("\n=== SAVING RESULTS ===\n")
        
        df.to_csv(output_csv, index=False)
        logger.info(f"✅ Enriched data saved to {output_csv}")
        
        # Report statistics
        logger.info(f"\n=== VALIDATION REPORT ===")
        
        budget_checks = df['Budget_Check'].notna().sum()
        matches = len(df[df['Budget_Check'].str.contains('MATCH', na=False)])
        mismatches = len(df[df['Budget_Check'].str.contains('MISMATCH', na=False)])
        
        added_budgets = df['Added_Budgets'].notna().sum()
        mpaa_found = df['MPAA_Rating'].notna().sum()
        
        logger.info(f"Budget Validation Results:")
        logger.info(f"  - Budget Checks performed: {budget_checks}")
        logger.info(f"  - Matches: {matches}")
        logger.info(f"  - Mismatches: {mismatches}")
        logger.info(f"  - New budgets added: {added_budgets}")
        logger.info(f"\nMPAA Ratings Scraped:")
        logger.info(f"  - Ratings found: {mpaa_found} / {total_films:,}")
        logger.info(f"  - Success rate: {mpaa_found/total_films*100:.1f}%")

def main():
    tmdb_api_key = os.getenv('TMDB_API_KEY')
    
    if not tmdb_api_key:
        logger.error("TMDB_API_KEY environment variable not set!")
        return
    
    # Create output directory if it doesn't exist
    output_dir = '/app/output'
    if not os.path.exists(output_dir):
        output_dir = '.'
    
    enricher = ValidationEnricher(tmdb_api_key)
    
    input_file = 'project_2_data_filled_with_api.csv'
    output_file = os.path.join(output_dir, 'project_2_data_enriched_with_validation.csv')
    
    enricher.enrich_with_validation(input_file, output_file)

if __name__ == "__main__":
    main()
