"""Build the corpus for the content-based recommender.

Downloads the N most-voted movies from TMDB together with the metadata the
recommender uses (overview, genres, keywords, director, top cast) and writes
them to data/rec_corpus.json.gz. Run it locally once, commit the output, and
re-run whenever you want a fresher catalogue:

    python build_rec_corpus.py              # default: 5,000 films
    python build_rec_corpus.py --n 8000

Needs TMDB_API_KEY in .env. Takes a few minutes (one detail request per film).
"""
import argparse
import gzip
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY  = os.environ.get("TMDB_API_KEY")
BASE_URL = "https://api.themoviedb.org/3"
OUT_PATH = os.path.join(os.path.dirname(__file__), "data", "rec_corpus.json.gz")


def get(path, params, retries=4):
    """GET with retry and back-off on 429 / transient errors."""
    params = {"api_key": API_KEY, "language": "en-US", **params}
    for attempt in range(retries):
        try:
            r = requests.get(f"{BASE_URL}{path}", params=params, timeout=10)
            if r.status_code == 429:
                time.sleep(float(r.headers.get("Retry-After", 2)))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            time.sleep(1.5 * (attempt + 1))
    return None


def discover_ids(n, min_votes):
    """IDs of the n most-voted films (20 per page, TMDB caps discover at 500 pages)."""
    ids = []
    for page in range(1, min(500, -(-n // 20)) + 1):
        data = get("/discover/movie", {
            "sort_by": "vote_count.desc",
            "vote_count.gte": min_votes,
            "include_adult": "false",
            "page": page,
        })
        if not data or not data.get("results"):
            break
        ids.extend(m["id"] for m in data["results"])
        print(f"\rdiscover: {len(ids)} ids", end="", flush=True)
    print()
    return ids[:n]


def film_features(tmdb_id):
    """Fetch one film's detail + keywords + credits and keep only what we need."""
    d = get(f"/movie/{tmdb_id}", {"append_to_response": "keywords,credits"})
    if not d:
        return None
    credits = d.get("credits", {})
    return {
        "id":          d["id"],
        "title":       d.get("title", ""),
        "year":        (d.get("release_date") or "")[:4],
        "poster_path": d.get("poster_path"),
        "overview":    d.get("overview") or "",
        "genres":      [g["name"] for g in d.get("genres", [])],
        "keywords":    [k["name"] for k in d.get("keywords", {}).get("keywords", [])],
        "director":    [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"],
        "cast":        [c["name"] for c in credits.get("cast", [])[:5]],
        "rating":      d.get("vote_average") or 0,
        "votes":       d.get("vote_count") or 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--n", type=int, default=5000, help="number of films (max 10,000)")
    parser.add_argument("--min-votes", type=int, default=200)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    if not API_KEY:
        raise SystemExit("TMDB_API_KEY is not set (add it to .env)")

    ids = discover_ids(args.n, args.min_votes)
    films = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(film_features, i) for i in ids]
        for k, fut in enumerate(as_completed(futures), 1):
            f = fut.result()
            if f and (f["overview"] or f["keywords"]):
                films.append(f)
            if k % 100 == 0:
                print(f"\rdetails: {k}/{len(ids)}", end="", flush=True)
    print()

    films.sort(key=lambda f: f["votes"], reverse=True)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with gzip.open(OUT_PATH, "wt", encoding="utf-8") as fh:
        json.dump(films, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"Wrote {len(films)} films to {OUT_PATH} "
          f"({os.path.getsize(OUT_PATH) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
