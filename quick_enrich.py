#!/usr/bin/env python3
"""
Quick Enrichment Runner - Simplified version with minimal setup
Usage: python quick_enrich.py [TMDB_KEY] [OMDB_KEY]
"""

import sys
import os

def main():
    if len(sys.argv) >= 3:
        tmdb_key = sys.argv[1]
        omdb_key = sys.argv[2]
    else:
        print("=== MOVIE DATA ENRICHMENT SETUP ===\n")
        print("This will fill 744 missing budgets and fetch MPAA ratings for 3,438 films\n")
        
        tmdb_key = input("Enter your TMDB API key: ").strip()
        omdb_key = input("Enter your OMDB API key: ").strip()
        
        if not tmdb_key or not omdb_key:
            print("ERROR: API keys are required!")
            sys.exit(1)
    
    # Set environment variables
    os.environ['TMDB_API_KEY'] = tmdb_key
    os.environ['OMDB_API_KEY'] = omdb_key
    
    print("\nStarting enrichment process...")
    print("(This may take 45-60 minutes)\n")
    
    # Import and run the enricher
    from enrich_missing_data import MovieDataEnricher
    import pandas as pd
    
    enricher = MovieDataEnricher(tmdb_key, omdb_key)
    enricher.enrich_dataset('project_2_data_filled_with_api.csv', 'project_2_data_enriched_v2.csv')
    
    print("\n✓ Enrichment complete!")
    print("Output: project_2_data_enriched_v2.csv")


if __name__ == "__main__":
    main()
