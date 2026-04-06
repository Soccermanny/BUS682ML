#!/usr/bin/env python3
import requests

tmdb_key = '41295f19715b4ff8545eb9bd0a42917a'
tmdb_id = 31592  # TMDB ID for The Old Dark House

url = f'https://api.themoviedb.org/3/movie/{tmdb_id}'
params = {'api_key': tmdb_key}

try:
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()
    print(f'Budget: ${data.get("budget", "N/A")}')
    print(f'Revenue: ${data.get("revenue", "N/A")}')
except Exception as e:
    print(f'Error: {e}')
