import argparse
import os
from typing import Optional
import re

import pandas as pd
import requests

TMDB_BASE = "https://api.themoviedb.org/3"


def _is_missing(value) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in {"", "na", "n/a", "not found", "nan", "none"}


def _tmdb_revenue_by_imdb(imdb_id: str, api_key: str, timeout: int = 15) -> Optional[int]:
    if not imdb_id or not imdb_id.startswith("tt"):
        return None

    find_resp = requests.get(
        f"{TMDB_BASE}/find/{imdb_id}",
        params={"api_key": api_key, "external_source": "imdb_id"},
        timeout=timeout,
    )
    find_resp.raise_for_status()
    matches = find_resp.json().get("movie_results", [])
    if not matches:
        return None

    tmdb_id = matches[0].get("id")
    if not tmdb_id:
        return None

    detail_resp = requests.get(
        f"{TMDB_BASE}/movie/{tmdb_id}",
        params={"api_key": api_key},
        timeout=timeout,
    )
    detail_resp.raise_for_status()
    revenue = detail_resp.json().get("revenue")
    if revenue in (None, 0):
        return None
    return int(revenue)


def _normalize_title(title: str) -> str:
    text = str(title).lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _title_similarity(a: str, b: str) -> float:
    na = _normalize_title(a)
    nb = _normalize_title(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    words_a = set(na.split())
    words_b = set(nb.split())
    overlap = len(words_a & words_b) / max(len(words_a), len(words_b), 1)

    char_matches = sum(ca == cb for ca, cb in zip(na, nb))
    char_score = char_matches / max(len(na), len(nb), 1)
    return 0.6 * overlap + 0.4 * char_score


def _tmdb_revenue_by_title_year(title: str, year, api_key: str, timeout: int = 15) -> Optional[int]:
    if not str(title).strip():
        return None

    params = {"api_key": api_key, "query": str(title).strip(), "page": 1, "include_adult": "false"}
    try:
        year_int = int(float(year))
        params["year"] = year_int
    except (TypeError, ValueError):
        year_int = None

    search_resp = requests.get(
        f"{TMDB_BASE}/search/movie",
        params=params,
        timeout=timeout,
    )
    search_resp.raise_for_status()
    results = search_resp.json().get("results", [])
    if not results:
        return None

    best = None
    best_score = -1.0
    for candidate in results[:8]:
        c_title = candidate.get("title", "")
        score = _title_similarity(title, c_title)
        c_date = candidate.get("release_date", "")
        c_year = None
        if c_date and len(c_date) >= 4 and c_date[:4].isdigit():
            c_year = int(c_date[:4])

        # Require strong title match. If year is available, require exact year match.
        if score < 0.78:
            continue
        if year_int is not None and c_year is not None and c_year != year_int:
            continue

        if score > best_score:
            best_score = score
            best = candidate

    if not best:
        return None

    tmdb_id = best.get("id")
    if not tmdb_id:
        return None

    detail_resp = requests.get(
        f"{TMDB_BASE}/movie/{tmdb_id}",
        params={"api_key": api_key},
        timeout=timeout,
    )
    detail_resp.raise_for_status()
    revenue = detail_resp.json().get("revenue")
    if revenue in (None, 0):
        return None
    return int(revenue)


def _read_csv_fallback(path: str) -> pd.DataFrame:
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path)


def enrich_box_office(input_csv: str, reference_csv: str, output_csv: str, tmdb_api_key: str = "") -> None:
    input_df = _read_csv_fallback(input_csv)
    ref_df = _read_csv_fallback(reference_csv)[["imdb_id", "box_office"]]

    # Keep the first non-missing value per IMDb ID in the reference source.
    ref_df = ref_df[~ref_df["box_office"].apply(_is_missing)].copy()
    ref_df = ref_df.drop_duplicates(subset=["imdb_id"], keep="first")

    input_df = input_df.copy()
    input_df["movie_id"] = input_df["movie_id"].astype(str).str.strip()

    ref_map = dict(zip(ref_df["imdb_id"], ref_df["box_office"]))
    input_df["box_office"] = input_df["movie_id"].map(ref_map)
    input_df["box_office_source"] = input_df["box_office"].apply(
        lambda x: "reference" if not _is_missing(x) else "missing"
    )

    if tmdb_api_key:
        # Pass 1: TMDB by IMDb ID for rows still missing.
        missing_indices = input_df.index[input_df["box_office"].apply(_is_missing)].tolist()
        for idx in missing_indices:
            imdb_id = str(input_df.at[idx, "movie_id"]).strip()
            try:
                revenue = _tmdb_revenue_by_imdb(imdb_id, tmdb_api_key)
            except requests.RequestException:
                revenue = None

            if revenue is not None:
                input_df.at[idx, "box_office"] = revenue
                input_df.at[idx, "box_office_source"] = "tmdb_api_imdb"

        # Pass 2: TMDB by title+year (or title-only when year missing).
        year_col = "year" if "year" in input_df.columns else None
        missing_indices = input_df.index[input_df["box_office"].apply(_is_missing)].tolist()
        for idx in missing_indices:
            title = input_df.at[idx, "movie_name"] if "movie_name" in input_df.columns else ""
            year_val = input_df.at[idx, year_col] if year_col else None

            try:
                revenue = _tmdb_revenue_by_title_year(title, year_val, tmdb_api_key)
            except requests.RequestException:
                revenue = None

            if revenue is not None:
                input_df.at[idx, "box_office"] = revenue
                input_df.at[idx, "box_office_source"] = "tmdb_api_title_year"

    input_df.to_csv(output_csv, index=False)

    total = len(input_df)
    filled = (~input_df["box_office"].apply(_is_missing)).sum()
    ref_filled = (input_df["box_office_source"] == "reference").sum()
    api_imdb_filled = (input_df["box_office_source"] == "tmdb_api_imdb").sum()
    api_title_filled = (input_df["box_office_source"] == "tmdb_api_title_year").sum()

    print(f"Saved: {output_csv}")
    print(f"Total rows: {total}")
    print(f"Rows with box office: {filled}")
    print(f"Filled from reference: {ref_filled}")
    print(f"Filled from TMDB API (IMDb ID): {api_imdb_filled}")
    print(f"Filled from TMDB API (Title/Year): {api_title_filled}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill box office using reference CSV and optional TMDB fallback")
    parser.add_argument("--input", default="api_usage_input.csv", help="Target CSV to enrich")
    parser.add_argument("--reference", default="project_2_data.xlsx.csv", help="Reference CSV with imdb_id and box_office")
    parser.add_argument("--output", default="api_usage_with_box_office.csv", help="Output CSV path")
    parser.add_argument("--tmdb-api-key", default=os.getenv("TMDB_API_KEY", ""), help="Optional TMDB API key fallback")
    args = parser.parse_args()

    enrich_box_office(
        input_csv=args.input,
        reference_csv=args.reference,
        output_csv=args.output,
        tmdb_api_key=args.tmdb_api_key,
    )


if __name__ == "__main__":
    main()
