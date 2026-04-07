import pandas as pd

df = pd.read_csv('project_2_data_filled_with_api.csv')
print("Columns in dataset:")
print(df.columns.tolist())
print(f"\nTotal columns: {len(df.columns)}")
print(f"\nDataset shape: {df.shape}")

# Check for rating-related columns
rating_cols = [col for col in df.columns if 'rating' in col.lower()]
print(f"\nRating-related columns: {rating_cols}")

# Check first few rows
print("\nFirst 5 rows of key columns:")
key_cols = ['imdb_id', 'title', 'release_year'] + rating_cols
available_cols = [col for col in key_cols if col in df.columns]
print(df[available_cols].head())
