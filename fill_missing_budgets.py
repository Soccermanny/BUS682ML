import argparse
import os
import re
from typing import Optional

import pandas as pd
import requests

TMDB_BASE = "https://api.themoviedb.org/3"
SEARCH_SCORE_THRESHOLD = 0.78


def _is_missing(value) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    return text in {"", "na", "n/a", "nan", "none", "not found"}


def _read_csv_fallback(path: str) -> pd.DataFrame:
    for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(path)


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


def _tmdb_movie_details(tmdb_id: int, api_key: str, timeout: int = 20) -> dict:
    response = requests.get(
        f"{TMDB_BASE}/movie/{tmdb_id}",
        params={"api_key": api_key},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.json()


def _tmdb_budget_by_imdb(imdb_id: str, api_key: str, timeout: int = 20) -> Optional[int]:
    if not imdb_id or not str(imdb_id).startswith("tt"):
        return None

    response = requests.get(
        f"{TMDB_BASE}/find/{imdb_id}",
        params={"api_key": api_key, "external_source": "imdb_id"},
        timeout=timeout,
    )
    response.raise_for_status()
    matches = response.json().get("movie_results", [])
    if not matches:
        return None

    tmdb_id = matches[0].get("id")
    if not tmdb_id:
        return None

    details = _tmdb_movie_details(tmdb_id, api_key, timeout=timeout)
    budget = details.get("budget")
    if budget in (None, 0):
        return None
    return int(budget)


def _tmdb_budget_by_title_year(title: str, year, api_key: str, timeout: int = 20) -> Optional[int]:
    if not str(title).strip():
        return None

    params = {"api_key": api_key, "query": str(title).strip(), "page": 1, "include_adult": "false"}
    year_int = None
    try:
        year_int = int(float(year))
        params["year"] = year_int
    except (TypeError, ValueError):
        year_int = None

    response = requests.get(
        f"{TMDB_BASE}/search/movie",
        params=params,
        timeout=timeout,
    )
    response.raise_for_status()
    results = response.json().get("results", [])
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

        if score < SEARCH_SCORE_THRESHOLD:
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

    details = _tmdb_movie_details(tmdb_id, api_key, timeout=timeout)
    budget = details.get("budget")
    if budget in (None, 0):
        return None
    return int(budget)


def fill_missing_budgets(input_csv: str, output_csv: str, tmdb_api_key: str = "") -> None:
    df = _read_csv_fallback(input_csv)
    df = df.copy()

    if "imdb_id" not in df.columns:
        raise ValueError("Input CSV must contain imdb_id")
    if "production_budget" not in df.columns:
        raise ValueError("Input CSV must contain production_budget")

    df["imdb_id"] = df["imdb_id"].astype(str).str.strip()
    if "title" in df.columns:
        title_col = "title"
    elif "movie_name" in df.columns:
        title_col = "movie_name"
    else:
        title_col = None

    if "release_year" in df.columns:
        year_col = "release_year"
    elif "year" in df.columns:
        year_col = "year"
    else:
        year_col = None

    if "production_budget_source" not in df.columns:
        df["production_budget_source"] = df["production_budget"].apply(
            lambda value: "project_2_data" if not _is_missing(value) else "missing_from_source"
        )
    else:
        df["production_budget_source"] = df["production_budget_source"].fillna(
            df["production_budget"].apply(lambda value: "project_2_data" if not _is_missing(value) else "missing_from_source")
        )

    df["budget_available"] = ~df["production_budget"].apply(_is_missing)
    budget_filled_imdb = 0
    budget_filled_title = 0

    if tmdb_api_key:
        missing_indices = df.index[df["production_budget"].apply(_is_missing)].tolist()
        for idx in missing_indices:
            imdb_id = str(df.at[idx, "imdb_id"]).strip()
            budget = None
            try:
                budget = _tmdb_budget_by_imdb(imdb_id, tmdb_api_key)
            except requests.RequestException:
                budget = None

            if budget is not None:
                df.at[idx, "production_budget"] = budget
                df.at[idx, "production_budget_source"] = "tmdb_api_imdb"
                df.at[idx, "budget_available"] = True
                budget_filled_imdb += 1
                continue

            if title_col is not None:
                title = df.at[idx, title_col]
                year_val = df.at[idx, year_col] if year_col is not None else None
                try:
                    budget = _tmdb_budget_by_title_year(title, year_val, tmdb_api_key)
                except requests.RequestException:
                    budget = None

                if budget is not None:
                    df.at[idx, "production_budget"] = budget
                    df.at[idx, "production_budget_source"] = "tmdb_api_title_year"
                    df.at[idx, "budget_available"] = True
                    budget_filled_title += 1

    budget = pd.to_numeric(df["production_budget"], errors="coerce")
    revenue = pd.to_numeric(df["box_office"], errors="coerce") if "box_office" in df.columns else pd.Series(index=df.index, dtype="float64")

    df["money_success_ratio"] = revenue / budget if "box_office" in df.columns else pd.NA
    df["money_success_score"] = revenue - budget if "box_office" in df.columns else pd.NA
    df["budget_efficiency_ratio"] = revenue / budget if "box_office" in df.columns else pd.NA
    df["budget_efficiency_percent"] = df["budget_efficiency_ratio"] * 100

    zero_budget = budget == 0
    df.loc[zero_budget, ["money_success_ratio", "money_success_score", "budget_efficiency_ratio", "budget_efficiency_percent"]] = pd.NA

    df.to_csv(output_csv, index=False, encoding="utf-8")

    total = len(df)
    filled = int(df["budget_available"].sum())
    missing = int((~df["budget_available"]).sum())

    print(f"Saved: {output_csv}")
    print(f"Total rows: {total}")
    print(f"Rows with production budget: {filled}")
    print(f"Rows still missing production budget: {missing}")
    print(f"Filled from TMDB API (IMDb ID): {budget_filled_imdb}")
    print(f"Filled from TMDB API (Title/Year): {budget_filled_title}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill missing production budgets using TMDB API")
    parser.add_argument("--input", default="project_2_data_filled_with_api.csv", help="Input CSV path")
    parser.add_argument("--output", default="project_2_data_filled_with_api_budget_filled.csv", help="Output CSV path")
    parser.add_argument("--tmdb-api-key", default=os.getenv("TMDB_API_KEY", ""), help="TMDB API key fallback")
    args = parser.parse_args()

    fill_missing_budgets(args.input, args.output, args.tmdb_api_key)


if __name__ == "__main__":
    main()
