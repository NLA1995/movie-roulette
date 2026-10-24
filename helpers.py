import os
import random
import requests
import xml.etree.ElementTree as ET
import re
from datetime import datetime
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import render_template, request

TMDB_API_KEY = os.environ.get("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w500"

TMDB_GENRES = {
    "Action": 28, "Comedy": 35, "Drama": 18, "Horror": 27,
    "Romance": 10749, "Sci-Fi": 878, "Thriller": 53,
    "Animation": 16, "Documentary": 99, "Fantasy": 14,
}

TMDB_TV_GENRES = {
    "Action & Adventure": 10759, "Animation": 16, "Comedy": 35,
    "Crime": 80, "Documentary": 99, "Drama": 18,
    "Family": 10751, "Kids": 10762, "Mystery": 9648,
    "Reality": 10764, "Sci-Fi & Fantasy": 10765,
    "Thriller": 9648, "War & Politics": 10768,
}


def apology(message, code=400):
    """Render an error page with a numeric code and a message."""
    def escape(s):
        for old, new in [("-", "--"), (" ", "-"), ("_", "__"), ("?", "~q"),
                         ("%", "~p"), ("#", "~h"), ("/", "~s"), ("\"", "''")]:
            s = s.replace(old, new)
        return s
    return render_template("apology.html", top=code, bottom=escape(message)), code



# ── TMDB: search movie ─────────────────────────────────────────────────────
def tmdb_search(title, year=None):
    """Search TMDB for a single movie by title and optional release year.

    Returns a dict with title, year, overview, rating, poster URL, and tmdb_id,
    or None if no results are found or the request fails.
    """
    try:
        params = {"api_key": TMDB_API_KEY, "query": title, "language": "en-US"}
        if year:
            params["year"] = year
        r = requests.get(f"{TMDB_BASE_URL}/search/movie", params=params, timeout=5)
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return None
        m = results[0]
        return {
            "title":    m.get("title"),
            "year":     m.get("release_date", "")[:4],
            "overview": m.get("overview"),
            "rating":   m.get("vote_average"),
            "poster":   TMDB_IMG_BASE + m["poster_path"] if m.get("poster_path") else None,
            "tmdb_id":  m.get("id"),
        }
    except requests.RequestException:
        return None


# ── TMDB: search movies by popularity ─────────────────────────────────────
def tmdb_search_popular(query):
    """Search movies ordered by popularity. Fetches up to 5 pages (~100 results).

    Results are re-ranked so exact title matches appear first, followed by
    partial matches, then all others — each group sorted by popularity × rating.
    Returns a list of dicts with title, year, rating, poster, tmdb_id, and media type.
    """
    try:
        all_results = []
        for page in range(1, 6):
            params = {"api_key": TMDB_API_KEY, "query": query, "language": "en-US", "page": page}
            r = requests.get(f"{TMDB_BASE_URL}/search/movie", params=params, timeout=5)
            r.raise_for_status()
            page_results = r.json().get("results", [])
            if not page_results:
                break
            all_results.extend(page_results)

        q = query.lower().strip()
        def movie_rank(m):
            title     = (m.get("title") or "").lower().strip()
            pop_score = m.get("popularity", 0) * m.get("vote_average", 0)
            if title == q:
                return (2, pop_score)
            elif title.startswith(q) or q in title:
                return (1, pop_score)
            else:
                return (0, pop_score)
        all_results.sort(key=movie_rank, reverse=True)

        return [{
            "title":    m.get("title"),
            "year":     m.get("release_date", "")[:4],
            "rating":   round(m.get("vote_average", 0), 1),
            "poster":   TMDB_IMG_BASE + m["poster_path"] if m.get("poster_path") else None,
            "tmdb_id":  m.get("id"),
            "media":    "movie",
        } for m in all_results]
    except requests.RequestException:
        return []


# ── TMDB: search TV shows by popularity ───────────────────────────────────
def tmdb_search_tv(query):
    """Search TV shows ordered by popularity. Fetches up to 5 pages (~100 results).

    Applies the same three-tier ranking as tmdb_search_popular (exact match →
    partial match → everything else), each tier sorted by popularity × rating.
    Returns a list of dicts with title, year, rating, poster, tmdb_id, and media type.
    """
    try:
        all_results = []
        for page in range(1, 6):
            params = {"api_key": TMDB_API_KEY, "query": query, "language": "en-US", "page": page}
            r = requests.get(f"{TMDB_BASE_URL}/search/tv", params=params, timeout=5)
            r.raise_for_status()
            page_results = r.json().get("results", [])
            if not page_results:
                break
            all_results.extend(page_results)

        q = query.lower().strip()
        def tv_rank(m):
            title     = (m.get("name") or "").lower().strip()
            pop_score = m.get("popularity", 0) * m.get("vote_average", 0)
            if title == q:
                return (2, pop_score)
            elif title.startswith(q) or q in title:
                return (1, pop_score)
            else:
                return (0, pop_score)
        all_results.sort(key=tv_rank, reverse=True)

        return [{
            "title":   m.get("name"),
            "year":    m.get("first_air_date", "")[:4],
            "rating":  round(m.get("vote_average", 0), 1),
            "poster":  TMDB_IMG_BASE + m["poster_path"] if m.get("poster_path") else None,
            "tmdb_id": m.get("id"),
            "media":   "tv",
        } for m in all_results]
    except requests.RequestException:
        return []


# ── TMDB: search movie with country of origin ──────────────────────────────
def tmdb_search_with_country(title, year=None):
    """Like tmdb_search, but also resolves the first production country.

    Makes a second request to the movie detail endpoint to fetch
    production_countries. Returns the same dict as tmdb_search plus a
    'country' key, or None on failure.
    """
    try:
        params = {"api_key": TMDB_API_KEY, "query": title, "language": "en-US"}
        if year:
            params["year"] = year
        r = requests.get(f"{TMDB_BASE_URL}/search/movie", params=params, timeout=5)
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return None
        m = results[0]

        country = None
        detail_r = requests.get(
            f"{TMDB_BASE_URL}/movie/{m['id']}",
            params={"api_key": TMDB_API_KEY, "language": "en-US"},
            timeout=5
        )
        if detail_r.ok:
            countries = detail_r.json().get("production_countries", [])
            if countries:
                country = countries[0].get("name")

        return {
            "title":    m.get("title"),
            "year":     m.get("release_date", "")[:4],
            "overview": m.get("overview"),
            "rating":   m.get("vote_average"),
            "poster":   TMDB_IMG_BASE + m["poster_path"] if m.get("poster_path") else None,
            "tmdb_id":  m.get("id"),
            "country":  country,
        }
    except requests.RequestException:
        return None


# ── TMDB: top movies by genre ──────────────────────────────────────────────
def tmdb_by_genre(genre_name, pages=1):
    """Return the top-rated movies for a given genre name (up to 50 results).

    Uses TMDB /discover/movie sorted by vote_average descending, filtered to
    titles with at least 500 votes. genre_name must be a key in TMDB_GENRES.
    """
    genre_id = TMDB_GENRES.get(genre_name)
    if not genre_id:
        return []
    try:
        movies = []
        for page in range(1, pages + 1):
            params = {
                "api_key": TMDB_API_KEY, "language": "en-US",
                "with_genres": genre_id, "sort_by": "vote_average.desc",
                "vote_count.gte": 500, "page": page,
            }
            r = requests.get(f"{TMDB_BASE_URL}/discover/movie", params=params, timeout=5)
            r.raise_for_status()
            for item in r.json().get("results", []):
                movies.append({
                    "title":    item.get("title"),
                    "year":     item.get("release_date", "")[:4],
                    "overview": item.get("overview"),
                    "rating":   round(item.get("vote_average", 0), 2),
                    "poster":   TMDB_IMG_BASE + item["poster_path"] if item.get("poster_path") else None,
                    "tmdb_id":  item.get("id"),
                })
        return movies[:50]
    except requests.RequestException:
        return []


# ── TMDB: top TV shows by genre ────────────────────────────────────────────
def tmdb_tv_by_genre(genre_name, pages=1):
    """Return the top-rated TV shows for a given genre name (up to 50 results).

    Uses TMDB /discover/tv sorted by vote_average descending, filtered to
    titles with at least 200 votes. genre_name must be a key in TMDB_TV_GENRES.
    """
    genre_id = TMDB_TV_GENRES.get(genre_name)
    if not genre_id:
        return []
    try:
        shows = []
        for page in range(1, pages + 1):
            params = {
                "api_key": TMDB_API_KEY, "language": "en-US",
                "with_genres": genre_id, "sort_by": "vote_average.desc",
                "vote_count.gte": 200, "page": page,
            }
            r = requests.get(f"{TMDB_BASE_URL}/discover/tv", params=params, timeout=5)
            r.raise_for_status()
            for item in r.json().get("results", []):
                shows.append({
                    "title":    item.get("name"),
                    "year":     item.get("first_air_date", "")[:4],
                    "overview": item.get("overview"),
                    "rating":   round(item.get("vote_average", 0), 2),
                    "poster":   TMDB_IMG_BASE + item["poster_path"] if item.get("poster_path") else None,
                    "tmdb_id":  item.get("id"),
                })
        return shows[:50]
    except requests.RequestException:
        return []


# TMDB genre ID → human-readable name map
GENRE_MAP = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Sci-Fi", 10770: "TV Movie",
    53: "Thriller", 10752: "War", 37: "Western"
}

def get_genres(genre_ids):
    """Convert a list of TMDB genre IDs to genre name strings (max 3)."""
    return [GENRE_MAP[g] for g in (genre_ids or []) if g in GENRE_MAP][:3]


# ── TMDB: movies currently in theaters ────────────────────────────────────
def tmdb_now_playing():
    """Return up to 20 movies currently in theaters, sorted by popularity.

    Fetches two pages of /movie/now_playing and filters to titles released
    in the current or previous year. TV Movies (genre 10770) and obvious
    TV specials are excluded. Deduplication is done by tmdb_id.
    """
    try:
        current_year = str(datetime.today().year)
        movies   = []
        seen_ids = set()
        for page in range(1, 3):
            r = requests.get(f"{TMDB_BASE_URL}/movie/now_playing",
                             params={"api_key": TMDB_API_KEY, "language": "en-US", "page": page},
                             timeout=5)
            r.raise_for_status()
            results = r.json().get("results", [])
            results.sort(key=lambda x: x.get("popularity", 0), reverse=True)
            for item in results:
                tid       = item.get("id")
                release   = item.get("release_date", "")
                genre_ids = item.get("genre_ids", [])
                if 10770 in genre_ids:
                    continue
                title = item.get("title", "")
                if any(kw in title.lower() for kw in ["special presentation", "television special", ": special"]):
                    continue
                if item.get("vote_count", 0) < 50 or item.get("vote_average", 0) < 5.0:
                    continue
                release_year = release[:4] if release else ""
                if tid not in seen_ids and release_year in [current_year, str(int(current_year) - 1)]:
                    seen_ids.add(tid)
                    movies.append({
                        "title":      item.get("title"),
                        "year":       release[:4],
                        "genres":     get_genres(item.get("genre_ids", [])),
                        "rating":     round(item.get("vote_average", 0), 1),
                        "poster":     TMDB_IMG_BASE + item["poster_path"] if item.get("poster_path") else None,
                        "popularity": item.get("popularity", 0),
                        "tmdb_id":    tid,
                    })
        movies.sort(key=lambda x: x["popularity"], reverse=True)
        for m in movies:
            m.pop("popularity", None)
        return movies[:20]
    except requests.RequestException:
        return []


# ── TMDB: upcoming releases ────────────────────────────────────────────────
def tmdb_upcoming():
    """Return up to 12 future releases sorted by release date ascending.

    Fetches two pages of /movie/upcoming and keeps only titles whose
    release_date is strictly after today. Deduplication is done by tmdb_id.
    """
    try:
        today = datetime.today().strftime("%Y-%m-%d")
        movies   = []
        seen_ids = set()

        for page in range(1, 3):
            r = requests.get(f"{TMDB_BASE_URL}/movie/upcoming",
                             params={"api_key": TMDB_API_KEY, "language": "en-US", "page": page},
                             timeout=5)
            r.raise_for_status()
            for item in r.json().get("results", []):
                release = item.get("release_date", "")
                tmdb_id = item.get("id")
                if release and release > today and tmdb_id not in seen_ids:
                    seen_ids.add(tmdb_id)
                    movies.append({
                        "title":   item.get("title"),
                        "year":    release,
                        "genres":  get_genres(item.get("genre_ids", [])),
                        "rating":  round(item.get("vote_average", 0), 1),
                        "poster":  TMDB_IMG_BASE + item["poster_path"] if item.get("poster_path") else None,
                        "tmdb_id": tmdb_id,
                    })

        movies.sort(key=lambda x: x["year"])
        return movies[:12]
    except requests.RequestException:
        return []


# ── TMDB: full movie detail ────────────────────────────────────────────────
def tmdb_detail(tmdb_id):
    """Fetch complete detail for a single movie including cast, crew, and streaming providers.

    Appends watch/providers and credits in a single TMDB request.
    Streaming platforms are filtered to US flatrate offers only.
    Returns a dict or None on failure.
    """
    try:
        params = {
            "api_key": TMDB_API_KEY, "language": "en-US",
            "append_to_response": "watch/providers,credits",
        }
        r    = requests.get(f"{TMDB_BASE_URL}/movie/{tmdb_id}", params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        providers = [p.get("provider_name") for p in
                     data.get("watch/providers", {}).get("results", {}).get("US", {}).get("flatrate", [])]
        return {
            "title":     data.get("title"),
            "year":      data.get("release_date", "")[:4],
            "overview":  data.get("overview"),
            "rating":    data.get("vote_average"),
            "poster":    TMDB_IMG_BASE + data["poster_path"] if data.get("poster_path") else None,
            "genres":    [g["name"] for g in data.get("genres", [])],
            "budget":    data.get("budget"),
            "runtime":   data.get("runtime"),
            "platforms": providers,
            "cast":      [c["name"] for c in data.get("credits", {}).get("cast", [])[:5]],
            "director":  next((c["name"] for c in data.get("credits", {}).get("crew", [])
                               if c["job"] == "Director"), "Unknown"),
        }
    except requests.RequestException:
        return None


def tmdb_rec_features(tmdb_id):
    """Fetch the recommender features (overview, genres, keywords, director, cast)
    for a film that is not in the precomputed corpus. Returns None on failure."""
    try:
        r = requests.get(
            f"{TMDB_BASE_URL}/movie/{tmdb_id}",
            params={"api_key": TMDB_API_KEY, "language": "en-US",
                    "append_to_response": "keywords,credits"},
            timeout=5,
        )
        r.raise_for_status()
        d = r.json()
    except requests.RequestException:
        return None
    credits = d.get("credits", {})
    return {
        "id":       d.get("id"),
        "overview": d.get("overview") or "",
        "genres":   [g["name"] for g in d.get("genres", [])],
        "keywords": [k["name"] for k in d.get("keywords", {}).get("keywords", [])],
        "director": [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"],
        "cast":     [c["name"] for c in credits.get("cast", [])[:5]],
    }


# ── TMDB: full TV show detail ─────────────────────────────────────────────
def tmdb_tv_detail(tmdb_id):
    """Fetch complete detail for a single TV show including cast and streaming providers."""
    try:
        params = {
            "api_key": TMDB_API_KEY, "language": "en-US",
            "append_to_response": "watch/providers,credits",
        }
        r    = requests.get(f"{TMDB_BASE_URL}/tv/{tmdb_id}", params=params, timeout=5)
        r.raise_for_status()
        data = r.json()
        providers = [p.get("provider_name") for p in
                     data.get("watch/providers", {}).get("results", {}).get("US", {}).get("flatrate", [])]
        creators = [c["name"] for c in data.get("created_by", [])]
        return {
            "title":    data.get("name"),
            "year":     data.get("first_air_date", "")[:4],
            "overview": data.get("overview"),
            "rating":   data.get("vote_average"),
            "poster":   TMDB_IMG_BASE + data["poster_path"] if data.get("poster_path") else None,
            "genres":   [g["name"] for g in data.get("genres", [])],
            "seasons":  data.get("number_of_seasons"),
            "episodes": data.get("number_of_episodes"),
            "creators": creators,
            "platforms": providers,
            "cast":     [c["name"] for c in data.get("credits", {}).get("cast", [])[:5]],
        }
    except requests.RequestException:
        return None


# ── RSS: film news ─────────────────────────────────────────────────────────
def fetch_rss(url, limit=6):
    """Parse an RSS feed and return up to `limit` article dicts.

    Image resolution priority per item:
      1. media:content url
      2. media:thumbnail url
      3. enclosure (type contains 'image')
      4. first <img> tag inside the HTML description
      5. og:image meta tag fetched from the article page (fallback for THR)

    Each dict contains: title, link, summary (plain text, max 300 chars), date, image.
    Returns an empty list on any network or parse error.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml, application/xml, text/xml, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        r = requests.get(url, headers=headers, timeout=8)
        r.raise_for_status()
        root    = ET.fromstring(r.content)
        channel = root.find("channel")
        if channel is None:
            return []

        articles = []
        media_ns = "{http://search.yahoo.com/mrss/}"

        for item in channel.findall("item")[:limit]:
            title   = item.findtext("title", "").strip()
            link    = item.findtext("link", "").strip()
            summary = re.sub(r"<[^>]+>", "", item.findtext("description", "")).strip()[:300]
            date    = item.findtext("pubDate", "").strip()
            try:
                date = parsedate_to_datetime(date).strftime("%b %d, %Y")
            except Exception:
                date = ""

            image = None

            media = item.find(f"{media_ns}content")
            if media is not None:
                image = media.get("url")

            if not image:
                thumb = item.find(f"{media_ns}thumbnail")
                if thumb is not None:
                    image = thumb.get("url")

            if not image:
                enc = item.find("enclosure")
                if enc is not None and "image" in enc.get("type", ""):
                    image = enc.get("url")

            if not image:
                desc_html = item.findtext("description", "")
                img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', desc_html)
                if img_match:
                    image = img_match.group(1)

            articles.append({
                "title":   title,
                "link":    link,
                "summary": summary,
                "date":    date,
                "image":   image,
            })

        # Fetch og:image for all articles that still lack an image — concurrently
        def _fetch_og(link):
            try:
                page = requests.get(link, headers=headers, timeout=5)
                og = re.search(
                    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', page.text
                )
                if not og:
                    og = re.search(
                        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', page.text
                    )
                return og.group(1) if og else None
            except Exception:
                return None

        needs_og = [(i, a["link"]) for i, a in enumerate(articles) if not a["image"] and a["link"]]
        if needs_og:
            with ThreadPoolExecutor(max_workers=len(needs_og)) as ex:
                futures = {ex.submit(_fetch_og, link): i for i, link in needs_og}
                for future in as_completed(futures):
                    articles[futures[future]]["image"] = future.result()

        return articles
    except Exception:
        return []


def get_news_articles():
    """Fetch articles from Deadline and The Hollywood Reporter RSS feeds.

    Returns a tuple (deadline_articles, thr_articles), each a list of up to
    6 article dicts as returned by fetch_rss.
    """
    deadline = fetch_rss("https://deadline.com/feed/", limit=6)
    thr      = fetch_rss("https://www.hollywoodreporter.com/feed/", limit=6)
    return deadline, thr


def usd(value):
    """Format a numeric value as a USD currency string (e.g. 1234.5 → '$1,234.50')."""
    return f"${value:,.2f}"


# ── Dashboard data helpers ─────────────────────────────────────────────────
import time

from analytics import to_real_dollars

_dash_cache = {}
_CACHE_TTL  = 43200  # 12 hours

DECADES = {
    "1970s": ("1970-01-01", "1979-12-31"),
    "1980s": ("1980-01-01", "1989-12-31"),
    "1990s": ("1990-01-01", "1999-12-31"),
    "2000s": ("2000-01-01", "2009-12-31"),
    "2010s": ("2010-01-01", "2019-12-31"),
    "2020s": ("2020-01-01", "2029-12-31"),
}


def _get_cached(key, fn):
    """Return cached data for `key` if fresh, otherwise call fn() to refresh.

    Cache entries expire after _CACHE_TTL seconds (default 12 hours).
    Empty results are not cached so a transient TMDB failure is retried.
    """
    now = time.time()
    if key in _dash_cache and now - _dash_cache[key]["ts"] < _CACHE_TTL:
        return _dash_cache[key]["data"]
    data = fn()
    if data:
        _dash_cache[key] = {"data": data, "ts": now}
    return data


def _discover_total(gte, lte, genre_id=None):
    """Return TMDB's total_results for /discover/movie in a date range (0 on error)."""
    params = {
        "api_key": TMDB_API_KEY,
        "primary_release_date.gte": gte,
        "primary_release_date.lte": lte,
        "vote_count.gte": 50,
        "page": 1,
    }
    if genre_id is not None:
        params["with_genres"] = genre_id
    try:
        r = requests.get(f"{TMDB_BASE_URL}/discover/movie", params=params, timeout=6)
        r.raise_for_status()
        return r.json().get("total_results", 0)
    except Exception:
        return 0


def get_genres_by_decade():
    """Return {"counts": {genre: {decade: n}}, "totals": {decade: n}}.

    `counts` is the number of films tagged with each genre per decade and
    `totals` is the number of films in that decade regardless of genre (both
    restricted to titles with 50+ votes). The totals are the denominator used to
    normalise the heatmap: raw counts mostly reflect that every decade releases
    more films than the last, while genre share shows which genres actually grew.

    A film can carry several genres, so shares within a decade add up to more
    than 100%. All 66 requests (60 genre×decade + 6 totals) run concurrently.
    Results are cached for 12 hours.
    """
    def fetch():
        jobs = [(g, gid, d) for g, gid in TMDB_GENRES.items() for d in DECADES]
        jobs += [(None, None, d) for d in DECADES]

        counts = {g: {} for g in TMDB_GENRES}
        totals = {}
        with ThreadPoolExecutor(max_workers=20) as ex:
            futures = {ex.submit(_discover_total, *DECADES[d], gid): (g, d)
                       for g, gid, d in jobs}
            for future in as_completed(futures):
                genre_name, decade = futures[future]
                n = future.result()
                if genre_name is None:
                    totals[decade] = n
                else:
                    counts[genre_name][decade] = n

        if not any(totals.values()):
            return None
        return {"counts": counts, "totals": totals}
    return _get_cached("genres_by_decade_v2", fetch)


def _fetch_detail_for_dash(tmdb_id):
    """Fetch raw TMDB movie detail JSON for a single tmdb_id.

    Used concurrently by the dashboard helpers. Returns the parsed JSON dict
    or None on any request error.
    """
    try:
        r = requests.get(
            f"{TMDB_BASE_URL}/movie/{tmdb_id}",
            params={"api_key": TMDB_API_KEY, "language": "en-US"},
            timeout=6,
        )
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def get_budget_vs_rating():
    """Return a list of film dicts for the budget-vs-rating scatter plot.

    Each dict has title, year, genres, rating, votes, budget_m (nominal
    millions USD) and budget_real_m (millions of CPI_BASE_YEAR USD, adjusted
    with US CPI-U so a 1977 budget is comparable to a 2019 one).

    Fetches the 80 most popular films with 1,000+ votes, then resolves each
    movie's full detail concurrently (10 workers) to obtain budget information.
    Only films with a known budget > $1M, a rating > 0, 500+ votes and a release
    year are included. Results are sorted by real budget and cached for 12 hours.
    """
    def fetch():
        ids = []
        for page in range(1, 5):
            try:
                r = requests.get(
                    f"{TMDB_BASE_URL}/discover/movie",
                    params={
                        "api_key": TMDB_API_KEY,
                        "language": "en-US",
                        "sort_by": "popularity.desc",
                        "vote_count.gte": 1000,
                        "page": page,
                    },
                    timeout=6,
                )
                r.raise_for_status()
                ids.extend([m["id"] for m in r.json().get("results", [])])
            except Exception:
                pass

        results = []
        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(_fetch_detail_for_dash, tid) for tid in ids[:80]]
            for future in as_completed(futures):
                d = future.result()
                if not d:
                    continue
                budget = d.get("budget") or 0
                rating = d.get("vote_average") or 0
                votes  = d.get("vote_count") or 0
                year   = (d.get("release_date") or "")[:4]
                real   = to_real_dollars(budget, year)
                if budget > 1_000_000 and rating > 0 and votes >= 500 and real:
                    genres = [g["name"] for g in d.get("genres", [])[:2]]
                    results.append({
                        "title":         d.get("title", ""),
                        "budget_m":      round(budget / 1_000_000, 1),
                        "budget_real_m": round(real / 1_000_000, 1),
                        "rating":        round(rating, 1),
                        "votes":         votes,
                        "genres":        ", ".join(genres),
                        "year":          year,
                    })
        return sorted(results, key=lambda x: x["budget_real_m"])
    return _get_cached("budget_vs_rating_v2", fetch)


def get_roi_by_genre():
    """Return {genre: [roi, ...]} — the individual film ROIs (%) per genre.

    For each genre in TMDB_GENRES, fetches the 20 most-voted films (one TMDB
    page) via /discover/movie, then resolves each film's budget and revenue
    concurrently. Only films with budget > $5M and revenue > $1M are kept to
    drop unreported or placeholder values. ROI = (revenue - budget) / budget × 100.

    A film tagged with several genres can appear in several genre lists — it is
    counted in every genre whose top-20 it lands in. Budget and revenue are both
    nominal dollars of the same release, so the ratio needs no inflation
    adjustment. Aggregation (median + bootstrap CI) happens in the route so the
    raw distribution stays available. Results are cached for 12 hours.
    """
    def _fetch_genre_ids(genre_name, genre_id):
        try:
            r = requests.get(
                f"{TMDB_BASE_URL}/discover/movie",
                params={
                    "api_key": TMDB_API_KEY, "language": "en-US",
                    "with_genres": genre_id,
                    "sort_by": "vote_count.desc",
                    "vote_count.gte": 500, "page": 1,
                },
                timeout=6,
            )
            r.raise_for_status()
            return (genre_name, [m["id"] for m in r.json().get("results", [])[:20]])
        except Exception:
            return (genre_name, [])

    def fetch():
        # Step 1: fetch all genre ID lists concurrently
        genre_ids = {}
        with ThreadPoolExecutor(max_workers=len(TMDB_GENRES)) as ex:
            futs = [ex.submit(_fetch_genre_ids, name, gid)
                    for name, gid in TMDB_GENRES.items()]
            for fut in as_completed(futs):
                genre_name, ids = fut.result()
                if ids:
                    genre_ids[genre_name] = ids

        # Step 2: fetch each distinct movie once (films repeat across genres)
        unique_ids = {tid for ids in genre_ids.values() for tid in ids}
        detail_map = {}
        with ThreadPoolExecutor(max_workers=20) as ex:
            futs = {ex.submit(_fetch_detail_for_dash, tid): tid for tid in unique_ids}
            for fut in as_completed(futs):
                d = fut.result()
                if d:
                    detail_map[futs[fut]] = d

        # Step 3: individual ROIs per genre
        genre_rois = {}
        for genre, ids in genre_ids.items():
            rois = []
            for tid in ids:
                d = detail_map.get(tid)
                if not d:
                    continue
                budget  = d.get("budget") or 0
                revenue = d.get("revenue") or 0
                if budget > 5_000_000 and revenue > 1_000_000:
                    rois.append((revenue - budget) / budget * 100)
            if len(rois) >= 3:
                genre_rois[genre] = rois
        return genre_rois

    return _get_cached("roi_by_genre_v2", fetch)
