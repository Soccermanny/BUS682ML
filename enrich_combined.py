#!/usr/bin/env python3
"""
Combined Enrichment Script - 4-Layer Strategy
==============================================
1. TMDB API (primary, via IMDb ID lookup)
2. IMDb website scraping (fallback, direct page parsing)
3. Wikidata SPARQL (secondary, classic films)
4. Wikipedia infobox parsing (tertiary, historical records)

All budgets are labeled with source: tmdb_api | imdb_scraping | wikidata | wikipedia | not_found
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Thread-safe printing
print_lock = Lock()

# API Configuration
TMDB_BASE_URL = "https://api.themoviedb.org/3"
WIKIDATA_SPARQL = "https://query.wikidata.org/sparql"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

# Cache files
CACHE_WIKIDATA = "cache_wikidata_budgets.json"
CACHE_WIKIPEDIA = "cache_wikipedia_budgets.json"


class CombinedMovieEnricher:
    def __init__(self, tmdb_api_key: str):
        self.tmdb_key = tmdb_api_key
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.cache_wd = self._load_cache(CACHE_WIKIDATA)
        self.cache_wp = self._load_cache(CACHE_WIKIPEDIA)
    
    def _load_cache(self, cache_file: str) -> dict:
        """Load cache from disk"""
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_cache(self, cache_file: str, cache_data: dict):
        """Save cache to disk"""
        try:
            with open(cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            logger.debug(f"Could not save cache: {e}")
        
    def _is_missing(self, value) -> bool:
        """Check if a value is missing/null/NaN"""
        if value is None or pd.isna(value):
            return True
        text = str(value).strip().lower()
        return text in {"", "na", "n/a", "nan", "none", "not found"}
    
    # ==================== LAYER 2: WIKIDATA BUDGET ====================
    
    def layer2_wikidata(self, title: str, year: Optional[int] = None) -> Tuple[Optional[int], str]:
        """Layer 2: Wikidata SPARQL - production cost (wdt:P2130)"""
        
        # Check cache first
        cache_key = f"{title.lower()}:{year}"
        if cache_key in self.cache_wd:
            cached = self.cache_wd[cache_key]
            if cached.get("budget"):
                logger.debug(f"      Layer 2 (Wikidata CACHED): ${cached['budget']:,}")
                return cached["budget"], "wikidata"
        
        query = f"""
SELECT DISTINCT ?productionCost
WHERE {{
  ?film wdt:P31 wd:Q11024 .
  ?film rdfs:label "{title.replace('"', '')}"@en .
  OPTIONAL {{ ?film wdt:P2130 ?productionCost . }}
}}
LIMIT 1
"""
        
        try:
            response = self.session.get(
                WIKIDATA_SPARQL,
                params={"query": query, "format": "json"},
                headers={"User-Agent": "BudgetBot/1.0", "Accept": "application/sparql-results+json"},
                timeout=12
            )
            response.raise_for_status()
            
            bindings = response.json().get("results", {}).get("bindings", [])
            if bindings and bindings[0].get("productionCost"):
                budget = int(bindings[0]["productionCost"]["value"])
                
                # Cache it
                self.cache_wd[cache_key] = {"budget": budget}
                self._save_cache(CACHE_WIKIDATA, self.cache_wd)
                
                logger.debug(f"      Layer 2 (Wikidata): SUCCESS ${budget:,}")
                return budget, "wikidata"
        
        except requests.exceptions.Timeout:
            logger.debug(f"      Layer 2 (Wikidata): TIMEOUT")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                logger.debug(f"      Layer 2 (Wikidata): RATE LIMITED (429)")
            else:
                logger.debug(f"      Layer 2 (Wikidata): HTTP {e.response.status_code}")
        except Exception as e:
            logger.debug(f"      Layer 2 (Wikidata): {type(e).__name__}")
        
        return None, "not_found"
    
    # ==================== LAYER 3: WIKIPEDIA BUDGET ====================
    
    def layer3_wikipedia(self, title: str, year: Optional[int] = None) -> Tuple[Optional[int], str]:
        """Layer 3: Wikipedia infobox parsing - budget extraction"""
        
        # Check cache first
        cache_key = f"{title.lower()}:{year}"
        if cache_key in self.cache_wp:
            cached = self.cache_wp[cache_key]
            if cached.get("budget"):
                logger.debug(f"      Layer 3 (Wikipedia CACHED): ${cached['budget']:,}")
                return cached["budget"], "wikipedia"
        
        try:
            # Search for Wikipedia article
            search = self.session.get(
                WIKIPEDIA_API,
                params={"action": "query", "list": "search", "srsearch": f"{title} film", "format": "json"},
                timeout=10
            )
            search.raise_for_status()
            
            results = search.json().get("query", {}).get("search", [])
            if not results:
                return None, "not_found"
            
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
                return None, "not_found"
            
            text = list(pages.values())[0].get("extract", "")
            
            # Search for budget patterns in Wikipedia text
            # Patterns: "$X million", "$X,XXX,XXX", "budget of $X", "production budget"
            patterns = [
                r"(?:production\s+)?budget[^:]*?\$\s*([\d,]+)\s*(?:million)?",
                r"production\s+cost[^:]*?\$\s*([\d,]+)",
                r"\$\s*([\d,]+(?:,\d{3})*)\s*(?:production\s+)?budget",
                r"budget.*?\$\s*([\d,]+(?:,\d{3})*)",
            ]
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    budget_str = match.group(1).replace(",", "")
                    try:
                        budget = int(budget_str)
                        
                        # Check if "million" appears near the match
                        match_context = text[max(0, match.start()-100):match.end()+100].lower()
                        if "million" in match_context and budget < 1000:
                            budget *= 1_000_000
                        
                        if budget > 0 and budget < 1_000_000_000:  # Sanity check (< $1B)
                            # Cache it
                            self.cache_wp[cache_key] = {"budget": budget}
                            self._save_cache(CACHE_WIKIPEDIA, self.cache_wp)
                            
                            logger.debug(f"      Layer 3 (Wikipedia): SUCCESS ${budget:,}")
                            return budget, "wikipedia"
                    except ValueError:
                        pass
        
        except requests.exceptions.Timeout:
            logger.debug(f"      Layer 3 (Wikipedia): TIMEOUT")
        except requests.RequestException as e:
            logger.debug(f"      Layer 3 (Wikipedia): {type(e).__name__}")
        except Exception as e:
            logger.debug(f"      Layer 3 (Wikipedia): {type(e).__name__}")
        
        return None, "not_found"
    
    # ==================== TMDB BUDGET METHODS ====================
    
    def normalize_title(self, title: str) -> str:
        """Normalize title for matching (from movie_clustering.py)"""
        import re
        t = title.lower().strip()
        t = re.sub(r"[^\w\s]", "", t)
        t = re.sub(r"\b(the|a|an)\b", "", t)
        return re.sub(r"\s+", " ", t).strip()
    
    def title_similarity(self, a: str, b: str) -> float:
        """Calculate title similarity score (from movie_clustering.py)"""
        a, b = self.normalize_title(a), self.normalize_title(b)
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
    
    def get_tmdb_id_by_imdb(self, imdb_id: str) -> Optional[int]:
        """Find TMDB ID using IMDb ID (Layer 1)"""
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
    
    def get_tmdb_id_by_title(self, title: str, year: Optional[int] = None) -> Optional[int]:
        """Search TMDB by title + year (Layers 2 & 3) - returns first match with title_similarity > 0.85"""
        if not title or not title.strip():
            return None
        
        try:
            params = {
                "api_key": self.tmdb_key,
                "query": title,
                "language": "en-US",
                "page": 1,
            }
            if year:
                params["year"] = int(year)
            
            response = self.session.get(
                f"{TMDB_BASE_URL}/search/movie",
                params=params,
                timeout=10
            )
            response.raise_for_status()
            
            for result in response.json().get("results", [])[:5]:
                tmdb_title = result.get("title", "")
                tmdb_date = result.get("release_date", "")
                tmdb_year = int(tmdb_date[:4]) if tmdb_date and len(tmdb_date) >= 4 else None
                
                # Check title similarity (threshold: 0.85)
                if self.title_similarity(title, tmdb_title) < 0.85:
                    continue
                
                # Check year match if both available
                if year and tmdb_year is not None and int(year) != tmdb_year:
                    continue
                
                return result.get("id")
        
        except requests.RequestException as e:
            logger.warning(f"Error searching TMDB for '{title}': {e}")
        
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
    
    def get_budget_from_imdb_scraping(self, imdb_id: str) -> Optional[int]:
        """Scrape IMDb page for budget information - Layer 2"""
        try:
            url = f"https://www.imdb.com/title/{imdb_id}/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for budget in various formats on IMDb page
            for ul in soup.find_all('ul', class_='ipc-metadata-list'):
                for li in ul.find_all('li'):
                    text = li.get_text(strip=True)
                    if 'Budget' in text or 'Production Budget' in text:
                        # Extract dollar amount
                        import re
                        match = re.search(r'\$\s*([\d,]+(?:\.\d+)?)\s*(?:million|M)?', text, re.IGNORECASE)
                        if match:
                            amount = float(match.group(1).replace(',', ''))
                            if 'million' in text.lower():
                                amount *= 1_000_000
                            return int(amount)
            
            # Alternative: Look in schema.org structured data
            import json as json_lib
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json_lib.loads(script.string)
                    if isinstance(data, dict) and 'budget' in data:
                        budget_str = str(data['budget'])
                        match = re.search(r'[\d,]+', budget_str.replace(',', ''))
                        if match:
                            return int(match.group())
                except:
                    continue
                    
        except requests.RequestException as e:
            logger.debug(f"IMDb scraping failed for {imdb_id}: {e}")
        
        return None

    def get_budget_by_imdb_id(self, imdb_id: str, title: str, year: Optional[int] = None) -> Tuple[Optional[int], str]:
        """4-layer budget lookup with source tracking:
        Layer 1: TMDB API (via IMDb ID)
        Layer 2: IMDb website scraping
        Layer 3: Wikidata SPARQL (production cost property)
        Layer 4: Wikipedia infobox (budget extraction)
        
        Returns (budget_amount, source_label)
        """
        logger.debug(f"    Budget lookup: {imdb_id} '{title}' ({year})")
        
        # Layer 1: Try TMDB API
        logger.debug(f"      Layer 1 (TMDB API)")
        tmdb_id = self.get_tmdb_id_by_imdb(imdb_id)
        if tmdb_id:
            budget = self.get_budget_by_tmdb_id(tmdb_id)
            if budget:
                logger.debug(f"      ✓ Layer 1 SUCCESS: TMDB API - ${budget:,}")
                return budget, "tmdb_api"
        
        time.sleep(0.5)  # Polite rate limiting
        
        # Layer 2: Fallback to IMDb scraping
        logger.debug(f"      Layer 2 (IMDb scraping)")
        budget = self.get_budget_from_imdb_scraping(imdb_id)
        if budget:
            logger.debug(f"      ✓ Layer 2 SUCCESS: IMDb scraping - ${budget:,}")
            return budget, "imdb_scraping"
        
        time.sleep(0.5)  # Polite rate limiting
        
        # Layer 3: Fallback to Wikidata
        logger.debug(f"      Layer 3 (Wikidata)")
        budget, source = self.layer2_wikidata(title, year)
        if budget:
            logger.debug(f"      ✓ Layer 3 SUCCESS: Wikidata - ${budget:,}")
            return budget, source
        
        time.sleep(0.5)
        
        # Layer 4: Fallback to Wikipedia
        logger.debug(f"      Layer 4 (Wikipedia)")
        budget, source = self.layer3_wikipedia(title, year)
        if budget:
            logger.debug(f"      ✓ Layer 4 SUCCESS: Wikipedia - ${budget:,}")
            return budget, source
        
        # No data found from any source
        logger.debug(f"      ✗ All layers exhausted: NOT FOUND")
        return None, "not_found"
    
    # ==================== IMDB MPAA SCRAPING METHODS ====================
    
    def extract_rating_from_soup(self, soup) -> Optional[str]:
        """Extract rating from BeautifulSoup object (from main.py)"""
        rating = ""
        
        # Method 1: Find rating span
        rating_elem = soup.find("span", class_="sc-eb51e184-1")
        if rating_elem:
            rating = rating_elem.get_text(strip=True)
        
        # Method 2: Search for /10 pattern
        if not rating:
            for span in soup.find_all("span"):
                text = span.get_text(strip=True)
                if "/10" in text and len(text) < 10:
                    rating = text
                    break
        
        if rating:
            import re
            match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*10", rating)
            if match:
                return match.group(1)
        
        return None
    
    def extract_mpaa_from_soup(self, soup) -> Tuple[str, datetime]:
        """Extract MPAA rating and release date from BeautifulSoup object"""
        code_rating = ""
        release_date = None
        
        try:
            # === EXTRACT RELEASE DATE ===
            for a_tag in soup.find_all("a", href=True):
                if "/releaseinfo" in a_tag.get("href", ""):
                    date_text = a_tag.get_text(strip=True)
                    try:
                        if "," in date_text:
                            release_date = datetime.strptime(date_text, "%B %d, %Y")
                            break
                        elif len(date_text.split()) == 3:
                            parts = date_text.split()
                            if parts[1].isalpha():
                                release_date = datetime.strptime(date_text, "%d %B %Y")
                            else:
                                release_date = datetime.strptime(date_text, "%B %d %Y")
                            break
                        elif len(date_text) == 4 and date_text.isdigit():
                            release_date = datetime(int(date_text), 1, 1)
                            break
                    except:
                        pass
            
            # === EXTRACT MPAA RATING ===
            mpaa_found = False
            for span in soup.find_all("span"):
                text = span.get_text(strip=True)
                # Common MPAA ratings
                if text in ["G", "PG", "PG-13", "R", "NC-17", "X", "M", "GP", "Approved", "Passed"]:
                    code_rating = text
                    mpaa_found = True
                    break
            
            # Alternative: Look for "MPAA" label
            if not mpaa_found:
                mpaa_label = soup.find("span", string="MPAA")
                if mpaa_label:
                    parent = mpaa_label.parent
                    for span in parent.find_all("span"):
                        text = span.get_text(strip=True)
                        if text and text != "MPAA":
                            code_rating = text
                            mpaa_found = True
                            break
            
            # If no MPAA rating found, check release date
            if not mpaa_found:
                if release_date:
                    # MPAA rating system started November 1, 1968
                    mpaa_start_date = datetime(1968, 11, 1)
                    if release_date < mpaa_start_date:
                        code_rating = "Pre-Code"
                    else:
                        code_rating = "N/A"
                else:
                    code_rating = "Unknown"
        
        except Exception as e:
            logger.warning(f"Error extracting MPAA: {e}")
            code_rating = "Error"
        
        return code_rating, release_date
    
    def get_mpaa_rating_by_imdb(self, imdb_id: str, index: int = 1, total: int = 1) -> Tuple[Optional[str], str]:
        """Fetch MPAA rating from IMDb using web scraping with retry logic (from main.py)
        
        Retry strategy:
        - Up to 3 attempts to fetch and parse
        - 5 second delay per request
        - Multiple fallback extraction methods
        - Release date inference for Pre-Code detection
        """
        if not imdb_id or not str(imdb_id).startswith("tt"):
            return None, "invalid_imdb_id"
        
        url = f"https://www.imdb.com/title/{imdb_id}"
        mpaa_rating = None
        soup = None
        attempts = 0
        max_attempts = 3
        
        # Try up to 3 times to get the page
        while attempts < max_attempts and mpaa_rating is None:
            attempts += 1
            try:
                response = self.session.get(url, timeout=15, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                })
                response.raise_for_status()
                time.sleep(5)  # Rate limiting (5 seconds like main.py)
                
                soup = BeautifulSoup(response.text, "html.parser")
                mpaa_rating, _ = self.extract_mpaa_from_soup_with_retry(soup)
                
                if mpaa_rating is None and attempts < max_attempts:
                    logger.info(f"  [{index}/{total}] {imdb_id}: Rating not found, retry {attempts}/{max_attempts}")
                    time.sleep(2)  # Wait before retry
            
            except requests.RequestException as e:
                logger.warning(f"  [{index}/{total}] {imdb_id}: Error attempt {attempts}: {str(e)[:30]}")
                if attempts < max_attempts:
                    time.sleep(2)
                soup = None
        
        # If still no rating after 3 attempts, check release date for Pre-Code inference
        if mpaa_rating is None and soup:
            mpaa_rating, _ = self.extract_mpaa_from_soup_with_retry(soup)
        
        if mpaa_rating and mpaa_rating not in ["Error", "Unknown", "Unknown Date"]:
            return mpaa_rating, "imdb_scrape"
        
        return None, "not_found"
    
    def extract_mpaa_from_soup_with_retry(self, soup) -> Tuple[Optional[str], Optional[datetime]]:
        """Extract MPAA rating with fallback logic (from main.py lines 190-240)"""
        import re
        code_rating = ""
        release_date = None
        
        try:
            # === EXTRACT RELEASE DATE ===
            for a_tag in soup.find_all("a", href=True):
                if "/releaseinfo" in a_tag.get("href", ""):
                    date_text = a_tag.get_text(strip=True)
                    try:
                        # Try "January 15, 1939" format
                        if "," in date_text:
                            release_date = datetime.strptime(date_text, "%B %d, %Y")
                            break
                        # Try "15 January 1939" format
                        elif len(date_text.split()) == 3:
                            parts = date_text.split()
                            if parts[1].isalpha():
                                release_date = datetime.strptime(date_text, "%d %B %Y")
                            else:
                                release_date = datetime.strptime(date_text, "%B %d %Y")
                            break
                        # Try "1939" year-only format
                        elif len(date_text) == 4 and date_text.isdigit():
                            release_date = datetime(int(date_text), 1, 1)
                            break
                    except:
                        pass
            
            # Fallback: search page text for year only
            if not release_date:
                for element in soup.find_all(string=True):
                    text = str(element).strip()
                    if len(text) == 4 and text.isdigit():
                        year = int(text)
                        if 1900 <= year <= 2030:
                            release_date = datetime(year, 1, 1)
                            break
            
            # === EXTRACT MPAA RATING ===
            # Method 1: Find rating span directly
            mpaa_found = False
            for span in soup.find_all("span"):
                text = span.get_text(strip=True)
                # Common MPAA ratings (and older ratings like "Approved", "Passed", "Pre-Code")
                if text in ["G", "PG", "PG-13", "R", "NC-17", "X", "M", "GP", "Approved", "Passed", "Pre-Code"]:
                    code_rating = text
                    mpaa_found = True
                    break
            
            # Method 2: Look for "MPAA" label
            if not mpaa_found:
                mpaa_label = soup.find("span", string="MPAA")
                if mpaa_label:
                    parent = mpaa_label.parent
                    for span in parent.find_all("span"):
                        text = span.get_text(strip=True)
                        if text and text != "MPAA":
                            code_rating = text
                            mpaa_found = True
                            break
            
            # Method 3: If no MPAA found, infer from release date (Pre-Code before 1968-11-01)
            if not mpaa_found:
                if release_date:
                    mpaa_start_date = datetime(1968, 11, 1)
                    if release_date < mpaa_start_date:
                        code_rating = "Pre-Code"
                    else:
                        code_rating = "N/A"
                else:
                    code_rating = "Unknown Date"
        
        except Exception as e:
            logger.warning(f"Error extracting MPAA: {e}")
            code_rating = "Error"
        
        return code_rating if code_rating else None, release_date
    
    # ==================== MAIN ENRICHMENT METHOD ====================
    
    def enrich_dataset(self, input_csv: str, output_csv: str) -> pd.DataFrame:
        """
        Main enrichment pipeline:
        1. Load data
        2. Fill missing budgets (4-layer: TMDB → IMDb scraping → Wikidata → Wikipedia)
        3. Fetch MPAA ratings (IMDb scraping with 3-retry)
        4. Save enriched dataset with source labels
        """
        
        logger.info("Loading data...")
        df = pd.read_csv(input_csv)
        
        # Initialize columns if they don't exist
        if 'production_budget_source' not in df.columns:
            df['production_budget_source'] = 'original'
        if 'mpaa_rating' not in df.columns:
            df['mpaa_rating'] = None
        if 'mpaa_rating_source' not in df.columns:
            df['mpaa_rating_source'] = 'original'
        
        # Store original counts
        original_budget_count = df['production_budget'].notna().sum()
        original_mpaa_count = df['mpaa_rating'].notna().sum()
        
        # ========== PHASE 1: Fill Missing Budgets (3-Layer Strategy) ==========
        logger.info(f"\n=== PHASE 1: FILLING MISSING BUDGETS (3-Layer: TMDB → Wikidata → Wikipedia) ===")
        logger.info(f"Films needing budgets: {df['production_budget'].isna().sum()}")
        
        missing_budget_indices = df[df['production_budget'].isna()].index
        budget_filled = 0
        budget_by_source = {"tmdb_api": 0, "wikidata": 0, "wikipedia": 0, "not_found": 0}
        
        for idx, row in enumerate(missing_budget_indices, 1):
            imdb_id = df.at[row, 'imdb_id']
            title = df.at[row, 'title']
            year = df.at[row, 'release_year'] if 'release_year' in df.columns else None
            
            budget, source = self.get_budget_by_imdb_id(imdb_id, title, year)
            
            if budget:
                df.at[row, 'production_budget'] = budget
                df.at[row, 'production_budget_source'] = source
                budget_filled += 1
                budget_by_source[source] += 1
                logger.info(f"  [{idx}/{len(missing_budget_indices)}] {title} ({imdb_id}): ${budget:,} [from {source}]")
            else:
                budget_by_source["not_found"] += 1
                logger.info(f"  [{idx}/{len(missing_budget_indices)}] {title} ({imdb_id}): NOT FOUND")
            
            # Rate limiting
            if idx % 10 == 0:
                time.sleep(1)
        
        new_budget_count = df['production_budget'].notna().sum()
        logger.info(f"\n=== Budget Enrichment Summary ===")
        logger.info(f"  Before: {original_budget_count} films with budgets")
        logger.info(f"  Filled: {budget_filled} films")
        logger.info(f"  After:  {new_budget_count} films with budgets")
        logger.info(f"  Success Rate: {budget_filled / len(missing_budget_indices) * 100:.1f}%")
        logger.info(f"\n=== Breakdown by Source ===")
        logger.info(f"  TMDB API:  {budget_by_source['tmdb_api']} films")
        logger.info(f"  Wikidata:  {budget_by_source['wikidata']} films")
        logger.info(f"  Wikipedia: {budget_by_source['wikipedia']} films")
        logger.info(f"  Not Found: {budget_by_source['not_found']} films")
        
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
            
            rating, source = self.get_mpaa_rating_by_imdb(imdb_id, idx, len(df))
            
            if rating:
                df.at[row_idx, 'mpaa_rating'] = rating
                df.at[row_idx, 'mpaa_rating_source'] = source
                mpaa_filled += 1
                logger.info(f"  [{idx}/{len(df)}] {title} ({imdb_id}): {rating} [imdb_scrape]")
            
            # Rate limiting
            if idx % 10 == 0:
                time.sleep(0.5)
        
        new_mpaa_count = df['mpaa_rating'].notna().sum()
        logger.info(f"\n=== MPAA Rating Summary ===")
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
    
    tmdb_api_key = os.getenv('TMDB_API_KEY')
    
    if not tmdb_api_key:
        tmdb_api_key = input("Enter your TMDB API key: ").strip()
    
    if not tmdb_api_key:
        logger.error("TMDB API key is required!")
        sys.exit(1)
    
    # Initialize enricher
    enricher = CombinedMovieEnricher(tmdb_api_key)
    
    # Run enrichment
    input_file = 'project_2_data_filled_with_api.csv'
    output_file = 'project_2_data_enriched_complete.csv'
    
    enricher.enrich_dataset(input_file, output_file)
    
    logger.info(f"\nDone! Enriched data saved to {output_file}")


if __name__ == "__main__":
    main()
