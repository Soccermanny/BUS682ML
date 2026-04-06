#!/usr/bin/env python3
import requests

tmdb_key = '41295f19715b4ff8545eb9bd0a42917a'
imdb_id = 'tt0023293'  # The Old Dark House

# Test TMDB find endpoint
url = f'https://api.themoviedb.org/3/find/{imdb_id}'
params = {
    'api_key': tmdb_key,
    'external_source': 'imdb_id'
}

print(f'Testing TMDB API with IMDb ID: {imdb_id}')
print(f'URL: {url}')

try:
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    print(f'Response status: {response.status_code}')
    print(f'Movie results: {len(data.get("movie_results", []))} films found')
    if data.get("movie_results"):
        print(f'First result: {data["movie_results"][0]}')
    else:
        print('No results found')
        print(f'Full response: {data}')
except requests.exceptions.RequestException as e:
    print(f'Request error: {e}')
except Exception as e:
    print(f'Error: {e}')
