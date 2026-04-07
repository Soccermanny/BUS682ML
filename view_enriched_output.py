import pandas as pd
import numpy as np

# Load the enriched dataset
df = pd.read_csv('project_2_data_filled_with_api.csv')

print("="*80)
print("FINAL ENRICHED DATASET SUMMARY")
print("="*80)
print(f"\nTotal Records: {len(df):,}")
print(f"Total Columns: {len(df.columns)}")

# Check for budget and MPAA columns
print("\n" + "="*80)
print("PRODUCTION BUDGET SUMMARY")
print("="*80)

if 'production_budget' in df.columns:
    budgets_filled = df['production_budget'].notna().sum()
    budgets_missing = df['production_budget'].isna().sum()
    print(f"Films with budgets: {budgets_filled:,} ({budgets_filled/len(df)*100:.1f}%)")
    print(f"Films missing budgets: {budgets_missing:,} ({budgets_missing/len(df)*100:.1f}%)")
    print(f"Min budget: ${df['production_budget'].min():,.0f}")
    print(f"Max budget: ${df['production_budget'].max():,.0f}")
    print(f"Mean budget: ${df['production_budget'].mean():,.0f}")
    print(f"Median budget: ${df['production_budget'].median():,.0f}")

if 'production_budget_source' in df.columns:
    print("\nBudget Source Breakdown:")
    source_counts = df['production_budget_source'].value_counts()
    for source, count in source_counts.items():
        pct = count / len(df) * 100
        print(f"  {source:20s}: {count:5,} films ({pct:5.1f}%)")

# Check for MPAA ratings
print("\n" + "="*80)
print("MPAA RATING SUMMARY")
print("="*80)

if 'mpaa_rating' in df.columns:
    ratings_filled = df['mpaa_rating'].notna().sum()
    ratings_missing = df['mpaa_rating'].isna().sum()
    print(f"Films with MPAA ratings: {ratings_filled:,} ({ratings_filled/len(df)*100:.1f}%)")
    print(f"Films missing MPAA ratings: {ratings_missing:,} ({ratings_missing/len(df)*100:.1f}%)")
    
    print("\nRating Distribution:")
    rating_counts = df['mpaa_rating'].value_counts().sort_index()
    for rating, count in rating_counts.items():
        pct = count / len(df) * 100
        print(f"  {rating:20s}: {count:5,} films ({pct:5.1f}%)")

if 'mpaa_rating_source' in df.columns:
    print("\nMPAA Rating Source Breakdown:")
    source_counts = df['mpaa_rating_source'].value_counts()
    for source, count in source_counts.items():
        pct = count / len(df) * 100
        print(f"  {source:20s}: {count:5,} films ({pct:5.1f}%)")

# Show sample records with key columns
print("\n" + "="*80)
print("SAMPLE RECORDS (First 10 with budgets and MPAA)")
print("="*80)

sample_cols = ['title', 'release_year', 'production_budget', 'production_budget_source', 'mpaa_rating', 'mpaa_rating_source']
available_cols = [col for col in sample_cols if col in df.columns]
sample = df[available_cols].head(10)

pd.set_option('display.max_columns', None)
pd.set_option('display.width', None)
pd.set_option('display.max_colwidth', 25)
print(sample.to_string())

# Show films enriched from Wikidata
print("\n" + "="*80)
print("SAMPLE: FILMS ENRICHED FROM WIKIDATA")
print("="*80)
if 'production_budget_source' in df.columns:
    wikidata_films = df[df['production_budget_source'] == 'wikidata'].head(5)
    if len(wikidata_films) > 0:
        print(wikidata_films[available_cols].to_string())
    else:
        print("No films enriched from Wikidata in this dataset")

# Show films enriched from Wikipedia
print("\n" + "="*80)
print("SAMPLE: FILMS ENRICHED FROM WIKIPEDIA")
print("="*80)
if 'production_budget_source' in df.columns:
    wiki_films = df[df['production_budget_source'] == 'wikipedia'].head(5)
    if len(wiki_films) > 0:
        print(wiki_films[available_cols].to_string())
    else:
        print("No films enriched from Wikipedia in this dataset")

print("\n" + "="*80)
print("OUTPUT FILE LOCATION")
print("="*80)
print("📁 See PHASE2_FINAL_OUTPUT folder for complete enriched dataset")
print("📊 Main file: project_2_data_filled_with_api.csv")
print("📄 Documentation: PHASE2_FINAL_OUTPUT/README.md")
