import pandas as pd

# Load dataset
df = pd.read_csv('project_2_data_filled_with_api.csv')

# Create MPAA ratings CSV with movie info
mpaa_csv = df[['imdb_id', 'title', 'release_year']].copy()
mpaa_csv.columns = ['Movie_ID', 'Movie_Name', 'Release_Year']

# Add empty MPAA_Rating column (to be filled by scraping)
mpaa_csv['MPAA_Rating'] = pd.NA
mpaa_csv['Scraping_Source'] = pd.NA

# Save
output_file = 'MPAA_Ratings_Template.csv'
mpaa_csv.to_csv(output_file, index=False)

print(f"✅ MPAA Ratings CSV Created: {output_file}")
print(f"\nFile contains:")
print(f"  - Movie_ID (IMDb ID)")
print(f"  - Movie_Name")
print(f"  - Release_Year")
print(f"  - MPAA_Rating (to be filled)")
print(f"  - Scraping_Source (to be filled)")
print(f"\nTotal films: {len(mpaa_csv):,}")
print(f"\nFirst 10 rows:")
print(mpaa_csv.head(10).to_string(index=False))

print(f"\n⚠️ NOTE: MPAA ratings are not yet populated.")
print(f"   The enrichment process crashed at film 130/744 during budget phase.")
print(f"   MPAA scraping phase hasn't started yet.")
print(f"   Please allow the enrichment to complete, then update this CSV with the results.")
