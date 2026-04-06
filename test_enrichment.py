#!/usr/bin/env python3
import pandas as pd
import os
import sys
import logging

logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

# Change to project directory
os.chdir('c:\\Users\\manny\\Documents\\BUS682_Project2')

# Import our enrichment script
from enrich_combined import CombinedMovieEnricher

# Load the data
df = pd.read_csv('project_2_data_filled_with_api.csv')

# Get only the films with missing budgets
missing = df[df['production_budget'].isna()].head(5)

print(f"Testing with {len(missing)} films with missing budgets:")
print(f"Columns available: {list(df.columns)[:10]}...")  # First 10 columns
print(f"'release_year' in columns: {'release_year' in df.columns}")
print()

enricher = CombinedMovieEnricher("41295f19715b4ff8545eb9bd0a42917a")

# Test first 5 missing budgets
for idx, (row_idx, row) in enumerate(missing.iterrows(), 1):
    imdb_id = row['imdb_id']
    title = row['title']
    year = row.get('release_year', None)
    
    print(f"\n[{idx}] {imdb_id} | '{title}' | Year: {year} (type: {type(year).__name__})")
    
    budget, source = enricher.get_budget_by_imdb_id(imdb_id, title, year)
    print(f"    Result: Budget={budget}, Source={source}")

print("\nTest complete!")
