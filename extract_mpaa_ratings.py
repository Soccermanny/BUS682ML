import pandas as pd

# Load the enriched dataset
df = pd.read_csv('project_2_data_filled_with_api.csv')

# Select only the MPAA rating columns we need
mpaa_data = df[['imdb_id', 'title', 'release_year', 'mpaa_rating', 'mpaa_rating_source']].copy()

# Filter to only rows with MPAA ratings
mpaa_with_ratings = mpaa_data[mpaa_data['mpaa_rating'].notna()].copy()

# Save to CSV
output_file = 'MPAA_RATINGS_SCRAPED.csv'
mpaa_with_ratings.to_csv(output_file, index=False)

print(f"✅ MPAA Ratings CSV Created: {output_file}")
print(f"\nStatistics:")
print(f"Total films with MPAA ratings: {len(mpaa_with_ratings):,}")
print(f"Total films in dataset: {len(df):,}")
print(f"Coverage: {len(mpaa_with_ratings)/len(df)*100:.1f}%")

print(f"\nColumns included:")
print(f"  - imdb_id")
print(f"  - title")
print(f"  - release_year")
print(f"  - mpaa_rating")
print(f"  - mpaa_rating_source")

print(f"\nRating Distribution:")
print(mpaa_with_ratings['mpaa_rating'].value_counts().sort_index())

print(f"\nSource Distribution:")
print(mpaa_with_ratings['mpaa_rating_source'].value_counts())

print(f"\nFirst 10 records:")
print(mpaa_with_ratings.head(10).to_string())
