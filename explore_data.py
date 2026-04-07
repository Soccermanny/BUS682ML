import pandas as pd
import numpy as np

# Load data
df = pd.read_csv('project_2_data_corrected.csv', encoding='utf-8')
print(f'Total rows: {len(df)}')
print(f'\nCountries present:')
print(df['country'].value_counts())

# Filter to Domestic
domestic = df[df['country'] == 'Domestic'].copy()
print(f'\nDomestic subset size: {len(domestic)}')

# Check box office and budget coverage
print(f'\nBox Office Statistics (Domestic):')
print(f'  Non-null: {domestic["box_office"].notna().sum()}')
print(f'  Min: ${domestic["box_office"].min():,.0f}')
print(f'  Max: ${domestic["box_office"].max():,.0f}')
print(f'  Mean: ${domestic["box_office"].mean():,.0f}')
print(f'  Median: ${domestic["box_office"].median():,.0f}')

print(f'\nProduction Budget Coverage (Domestic):')
print(f'  Non-null: {domestic["production_budget"].notna().sum()}')
print(f'  Missing: {domestic["production_budget"].isna().sum()} ({100*domestic["production_budget"].isna().sum()/len(domestic):.1f}%)')

print(f'\nFactor columns check:')
factor_cols = [col for col in df.columns if col.startswith('Factor_')]
print(f'  Number of factors: {len(factor_cols)}')
print(f'  Factor columns: {factor_cols}')

print(f'\nGenres sample:')
print(domestic['genres'].head().tolist())

print(f'\nOriginal languages:')
print(f'  Unique languages: {domestic["original_language"].nunique()}')
print(domestic['original_language'].value_counts().head(10))
