#!/usr/bin/env python3
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import logging
import re
from datetime import datetime
from typing import Optional, Tuple

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

TMDB_API_KEY = "41295f19715b4ff8545eb9bd0a42917a"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

# Test data
test_films = [
    ("tt0023293", "The Old Dark House", 1932),
    ("tt0000001", "Carmencita", 1894),
    ("tt0000002", "The Arrival of a Train at La Ciotat Station", 1896),
]

session = requests.Session()

def normalize_title(title: str) -> str:
    """Normalize title for matching"""
    t = title.lower().strip()
    t = re.sub(r"[^\w\s]", "", t)
    t = re.sub(r"\b(the|a|an)\b", "", t) 
    return re.sub(r"\s+", " ", t).strip()

def title_similarity(a: str, b: str) -> float:
    """Calculate title similarity score"""
    a, b = normalize_title(a), normalize_title(b)
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    longer = max(len(a), len(b))
    matches = sum(ca == cb for ca, cb in zip(a, b))
    words_a = set(a.split())
    words_b = set(b.split())
    word_overlap = len(words_a & words_b) / max(len(words_a), len(words_b), 1)
    return (matches / longer * 0.5) + (word_overlap * 0.5)

def get_tmdb_id_by_imdb(imdb_id: str) -> Optional[int]:
    """Find TMDB ID using IMDb ID (Layer 1)"""
    if not imdb_id or not str(imdb_id).startswith("tt"):
        return None
    
    try:
        response = session.get(
            f"{TMDB_BASE_URL}/find/{imdb_id}",
            params={"api_key": TMDB_API_KEY, "external_source": "imdb_id"},
            timeout=10
        )
        response.raise_for_status()
        matches = response.json().get("movie_results", [])
        if matches:
            tmdb_id = matches[0].get("id")
            logger.info(f"  Layer 1 SUCCESS: {imdb_id} -> TMDB ID {tmdb_id}")
            return tmdb_id
        else:
            logger.debug(f"  Layer 1: No matches for {imdb_id}")
    except Exception as e:
        logger.warning(f"  Layer 1 error: {e}")
    
    return None

def get_tmdb_id_by_title(title: str, year: Optional[int] = None) -> Optional[int]:
    """Search TMDB by title + year (Layers 2 & 3)"""
    if not title or not title.strip():
        return None
    
    try:
        params = {
            "api_key": TMDB_API_KEY,
            "query": title,
            "language": "en-US",
            "page": 1,
        }
        if year:
            params["year"] = int(year)
        
        response = session.get(
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
            sim = title_similarity(title, tmdb_title)
            logger.debug(f"    Checking '{tmdb_title}' (similarity: {sim:.2f})")
            
            if sim < 0.85:
                continue
            
            # Check year match if both available
            if year and tmdb_year is not None and int(year) != tmdb_year:
                logger.debug(f"    Year mismatch: {year} vs {tmdb_year}")
                continue
            
            tmdb_id = result.get("id")
            logger.info(f"  Layer 2 SUCCESS: '{title}' ({year}) -> TMDB ID {tmdb_id} ('{tmdb_title}')")
            return tmdb_id
    
    except Exception as e:
        logger.warning(f"  Layer 2 error: {e}")
    
    return None

def get_tmdb_id_by_imdb_with_fallback(imdb_id: str, title: str, year: Optional[int] = None) -> Optional[int]:
    """3-layer fallback"""
    logger.info(f"\nLooking up: {imdb_id} '{title}' ({year})")
    
    # Layer 1: IMDb ID
    tmdb_id = get_tmdb_id_by_imdb(imdb_id)
    if tmdb_id:
        return tmdb_id
    
    # Layer 2: Title + year
    if title:
        tmdb_id = get_tmdb_id_by_title(title, year)
        if tmdb_id:
            return tmdb_id
    
    logger.info(f"  All layers failed: NOT FOUND")
    return None

# Test
for imdb_id, title, year in test_films:
    tmdb_id = get_tmdb_id_by_imdb_with_fallback(imdb_id, title, year)
    time.sleep(2)  # Rate limiting

print("\nTest complete!")
