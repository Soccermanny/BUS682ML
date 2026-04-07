import pandas as pd

df = pd.read_csv('project_2_data_filled_with_api.csv')

# List all columns
print("All columns in dataset:")
for i, col in enumerate(df.columns, 1):
    print(f"{i:2d}. {col}")

# Check for any columns with rating, code, hays, mpaa
rating_keywords = ['rating', 'code', 'hays', 'mpaa', 'certificate']
matching_cols = []
for col in df.columns:
    if any(keyword in col.lower() for keyword in rating_keywords):
        matching_cols.append(col)

if matching_cols:
    print(f"\nColumns containing rating/code keywords: {matching_cols}")
    print("\nSample data from these columns:")
    print(df[matching_cols].head(10))
else:
    print("\nNo MPAA/rating columns found in dataset yet")
    print("\n⚠️ The enrichment process crashed before completing MPAA scraping")
    print("Current status: 130/744 films processed for budgets")
