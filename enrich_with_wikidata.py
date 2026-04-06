#!/usr/bin/env python3
"""
Enhanced Enrichment with Wikidata Fallback
===========================================

4-Layer Budget Filling Strategy:
1. TMDB API (primary, modern films)
2. Wikidata SPARQL (fallback, classic films)
3. Wikipedia infobox parsing (historical data, box office records)
4. ISC Database / Box Office Mojo archives (last resort estimation)
"""

import os
import pandas as pd
import requests
import logging
import json
import time
from typing import Optional, Tuple
import re
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# API Configuration
TMDB_BASE_URL = "https://api.themoviedb.org/3"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

# Cache file for Wikidata results
CACHE_FILE = "cache_wikidata_budgets.json"

class EnhancedBudgetEnricher:
    """4-layer budget enrichment strategy"""
    
    def __init__(self, tmdb_api_key: str):
        self.tmdb_key = tmdb_api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.cache = self._load_cache()
    
    def _load_cache(self) -> dict:
        """Load Wikidata cache"""
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_cache(self):
        """Save Wikidata cache"""
        with open(CACHE_FILE, 'w') as f:
            json.dump(self.cache, f, indent=2)
    
    # ==================== LAYER 1: TMDB ====================
    
    def layer1_tmdb(self, imdb_id: str, title: str, year: Optional[int] = None) -> Optional[int]:
        """Layer 1: TMDB API (primary source for modern films)"""
        if not imdb_id or not str(imdb_id).startswith("tt"):
            return None
        
        try:
            # Find TMDB ID using IMDb ID
            response = self.session.get(
                f"{TMDB_BASE_URL}/find/{imdb_id}",
                params={"api_key": self.tmdb_key, "external_source": "imdb_id"},
                timeout=10
            )
            response.raise_for_status()
            matches = response.json().get("movie_results", [])
            
            if matches:
                tmdb_id = matches[0].get("id")
                
                # Get budget details
                detail = self.session.get(
                    f"{TMDB_BASE_URL}/movie/{tmdb_id}",
                    params={"api_key": self.tmdb_key},
                    timeout=10
                )
                detail.raise_for_status()
                budget = detail.json().get("budget", 0)
                
                if budget and budget > 0:
                    logger.debug(f"  Layer 1 (TMDB): SUCCESS ${budget:,}")
                    return int(budget)
        
        except requests.RequestException as e:
            logger.debug(f"  Layer 1 (TMDB): {type(e).__name__}")
        
        return None
    
    # ==================== LAYER 2: WIKIDATA ====================
    
    def layer2_wikidata(self, title: str, year: Optional[int] = None) -> Optional[int]:
        """Layer 2: Wikidata SPARQL (fallback for classic films)"""
        
        # Check cache first
        cache_key = f"{title.lower()}:{year}"
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if cached.get("budget"):
                logger.debug(f"  Layer 2 (Wikidata): CACHED ${cached['budget']:,}")
                return cached["budget"]
        
        query = f"""
SELECT DISTINCT ?productionCost
WHERE {{
  ?film wdt:P31 wd:Q11024 .
  ?film rdfs:label "{title}"@en .
  OPTIONAL {{ ?film wdt:P2130 ?productionCost . }}
  {f'FILTER(YEAR(xsd:dateTime(STR(NOW()))) - {year} < 10)' if year else ''}
}}
LIMIT 1
"""
        
        try:
            response = self.session.get(
                WIKIDATA_SPARQL,
                params={"query": query, "format": "json"},
                headers={"User-Agent": "BudgetBot/1.0"},
                timeout=15
            )
            response.raise_for_status()
            
            bindings = response.json().get("results", {}).get("bindings", [])
            if bindings and bindings[0].get("productionCost"):
                budget = int(bindings[0]["productionCost"]["value"])
                
                # Cache it
                self.cache[cache_key] = {"budget": budget, "source": "wikidata"}
                self._save_cache()
                
                logger.debug(f"  Layer 2 (Wikidata): SUCCESS ${budget:,}")
                return budget
        
        except requests.exceptions.Timeout:
            logger.debug(f"  Layer 2 (Wikidata): TIMEOUT")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logger.debug(f"  Layer 2 (Wikidata): RATE LIMITED")
            else:
                logger.debug(f"  Layer 2 (Wikidata): HTTP {e.response.status_code}")
        except Exception as e:
            logger.debug(f"  Layer 2 (Wikidata): {type(e).__name__}")
        
        return None
    
    # ==================== LAYER 3: WIKIPEDIA ====================
    
    def layer3_wikipedia(self, title: str, year: Optional[int] = None) -> Optional[int]:
        """Layer 3: Wikipedia infobox (historical records, box office archives)"""
        
        try:
            # Find Wikipedia article
            search = self.session.get(
                WIKIPEDIA_API,
                params={"action": "query", "list": "search", "srsearch": f"{title} film", "format": "json"},
                timeout=10
            )
            search.raise_for_status()
            
            results = search.json().get("query", {}).get("search", [])
            if not results:
                return None
            
            page_title = results[0]["title"]
            
            # Get article text
            article = self.session.get(
                WIKIPEDIA_API,
                params={"action": "query", "titles": page_title, "prop": "extracts", "format": "json"},
                timeout=10
            )
            article.raise_for_status()
            
            pages = article.json().get("query", {}).get("pages", {})
            if not pages:
                return None
            
            text = list(pages.values())[0].get("extract", "")
            
            # Search for budget patterns in Wikipedia text
            # Patterns: "$X million", "$X,XXX,XXX", "budget of $X"
            patterns = [
                r"budget[^:]*?\$\s*([\d,]+)\s*(?:million)?",
                r"production cost[^:]*?\$\s*([\d,]+)",
                r"\$\s*([\d,]+(?:,\d{3})*)\s*budget",
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    budget_str = match.group(1).replace(",", "")
                    try:
                        budget = int(budget_str)
                        # If matched "million", multiply
                        if "million" in text[match.start():match.end()].lower():
                            budget *= 1_000_000
                        
                        if budget > 0:
                            logger.debug(f"  Layer 3 (Wikipedia): SUCCESS ${budget:,}")
                            return budget
                    except ValueError:
                        pass
        
        except requests.RequestException as e:
            logger.debug(f"  Layer 3 (Wikipedia): {type(e).__name__}")
        
        return None
    
    # ==================== LAYER 4: ESTIMATION ====================
    
    def layer4_estimation(self, title: str, year: Optional[int] = None) -> Optional[int]:
        """Layer 4: Simple estimation based on release era"""
        
        if not year:
            return None
        
        # Rough budget estimates based on era (in USD)
        # These can be refined with historical research
        era_estimates = {
            (1920, 1929): 250_000,    # Silent era
            (1930, 1939): 500_000,    # Pre-Code
            (1940, 1949): 750_000,    # Golden Age
            (1950, 1959): 1_000_000,  # 50s
            (1960, 1969): 3_000_000,  # 60s
            (1970, 1979): 8_000_000,  # 70s
            (1980, 1999): 30_000_000, # 80s-90s
            (2000, 2009): 60_000_000, # 2000s
            (2010, 2030): 100_000_000, # 2010s+
        }
        
        estimated = None
        for (start, end), amount in era_estimates.items():
            if start <= year <= end:
                estimated = amount
                break
        
        if estimated:
            logger.debug(f"  Layer 4 (Estimation): GUESSED ${estimated:,} (era-based)")
            return estimated
        
        return None
    
    # ==================== MAIN METHOD ====================
    
    def get_budget(self, imdb_id: str, title: str, year: Optional[int] = None) -> Tuple[Optional[int], str]:
        """4-layer fallback strategy"""
        
        logger.debug(f"  Trying 4 layers for '{title}' ({year})")
        
        # Layer 1: TMDB
        budget = self.layer1_tmdb(imdb_id, title, year)
        if budget:
            return budget, "tmdb"
        
        time.sleep(0.5)  # Polite rate limiting
        
        # Layer 2: Wikidata
        budget = self.layer2_wikidata(title, year)
        if budget:
            return budget, "wikidata"
        
        time.sleep(0.5)
        
        # Layer 3: Wikipedia
        budget = self.layer3_wikipedia(title, year)
        if budget:
            return budget, "wikipedia"
        
        # Layer 4: Estimation (commented out - use only if needed)
        # budget = self.layer4_estimation(title, year)
        # if budget:
        #     return budget, "estimation"
        
        return None, "not_found"


# ==================== USAGE EXAMPLE ====================

if __name__ == "__main__":
    enricher = EnhancedBudgetEnricher("41295f19715b4ff8545eb9bd0a42917a")
    
    test_cases = [
        ("tt0023293", "The Old Dark House", 1932),
        ("tt1345836", "The Dark Knight Rises", 2012),
    ]
    
    print("Testing 4-layer budget enrichment:\n")
    for imdb_id, title, year in test_cases:
        print(f"🎬 {title} ({year})")
        budget, source = enricher.get_budget(imdb_id, title, year)
        if budget:
            print(f"   ✅ Found: ${budget:,} ({source})\n")
        else:
            print(f"   ❌ Not found\n")
