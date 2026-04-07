import pandas as pd
import os
import time

print("="*80)
print("ENRICHED BUDGET DATA MERGER")
print("="*80)

# Check which enriched files exist
files_to_check = [
    'project_2_data_enriched_complete.csv',
    'project_2_data_filled_with_api.csv'
]

enriched_file = None
for f in files_to_check:
    if os.path.exists(f):
        enriched_file = f
        print(f"\n✅ Found enriched file: {f}")
        break

if not enriched_file:
    print("\n⏳ Enriched file not yet created")
    print("The enrichment process is still running (currently ~11% complete)")
    print("\nTo add budget data when ready:")
    print("  1. Wait for enrichment to complete (2-3 more hours)")
    print("  2. Run this script again to merge the data")
    exit(0)

# Load both files
print("\nLoading data files...")
df_original = pd.read_csv('project_2_data_filled_with_api.csv')
df_enriched = pd.read_csv(enriched_file)

print(f"Original: {len(df_original)} films")
print(f"Enriched: {len(df_enriched)} films")

# Check what's new
print("\n" + "="*80)
print("BUDGET ENRICHMENT SUMMARY")
print("="*80)

if 'production_budget_source' in df_enriched.columns:
    print("\nBudget sources in enriched file:")
    sources = df_enriched['production_budget_source'].value_counts()
    for source, count in sources.items():
        pct = count / len(df_enriched) * 100
        print(f"  {source:30s}: {count:5,} ({pct:5.1f}%)")
    
    # Show new enriched budgets
    enriched_from_apis = df_enriched[
        df_enriched['production_budget_source'].isin(['tmdb_api', 'wikidata', 'wikipedia'])
    ]
    
    print(f"\n✅ NEW BUDGETS ENRICHED: {len(enriched_from_apis)} films")
    
    if len(enriched_from_apis) > 0:
        print("\nSample enriched films:")
        sample = enriched_from_apis[['title', 'release_year', 'production_budget', 'production_budget_source']].head(10)
        print(sample.to_string(index=False))

# Merge: Update original with enriched data
print("\n" + "="*80)
print("MERGING ENRICHED DATA INTO FINAL OUTPUT")
print("="*80)

# Copy all columns from enriched to original
budget_cols = ['production_budget', 'production_budget_source']
for col in budget_cols:
    if col in df_enriched.columns:
        df_original[col] = df_enriched[col]
        print(f"✅ Merged column: {col}")

# Save merged result
output_file = 'project_2_data_filled_with_api.csv'
print(f"\nSaving merged data to: {output_file}")
df_original.to_csv(output_file, index=False)

# Verify
print("\n" + "="*80)
print("FINAL DATASET STATUS")
print("="*80)
df_final = pd.read_csv(output_file)

if 'production_budget' in df_final.columns:
    budgets_filled = df_final['production_budget'].notna().sum()
    budgets_missing = df_final['production_budget'].isna().sum()
    print(f"\nFilms with budgets: {budgets_filled:,} ({budgets_filled/len(df_final)*100:.1f}%)")
    print(f"Films missing budgets: {budgets_missing:,} ({budgets_missing/len(df_final)*100:.1f}%)")

if 'production_budget_source' in df_final.columns:
    print("\nBudget source breakdown in FINAL FILE:")
    sources = df_final['production_budget_source'].value_counts()
    for source, count in sources.items():
        pct = count / len(df_final) * 100
        print(f"  {source:30s}: {count:5,} ({pct:5.1f}%)")

print("\n✅ Merge complete! Enriched budgets added to final output.")
