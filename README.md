# Movie Roulette

Movie Roulette is a full-stack streaming discovery web app powered by the TMDB API, built with Python/Flask on the backend and Bootstrap + custom CSS on the frontend.
The name comes from its core feature: every time you hit the home page you get 15 completely different movies pulled from different decades — like spinning a roulette wheel.

---

## Features

### 🎬 Index — Movie Roulette
The home page randomly picks 15 films from different release years between 1940 and 2024, ensuring every title has a decent rating and enough votes so you never get obscure low-quality films. All 15 TMDB enrichments (poster, overview, country) are fetched concurrently using `ThreadPoolExecutor` to keep load times fast.

### 🔥 Trending
Shows what is currently playing in cinemas and what is coming up soon, sorted by popularity. Filters out TV specials and duplicate entries the API sometimes returns.

### 🎬 Movies
Pick a genre from a visual image grid and get the top-rated films for that category — up to 50 results from TMDB, each with enough votes to be meaningful. Clicking any card opens a full detail page.

### 📺 TV Shows
Same experience as Movies but for series, with its own genre set (Crime, Mystery, Reality, War & Politics, Kids, and others that don't exist on the movie side). Each genre button shows a custom background image. Clicking a show opens its own detail page.

### 🔍 Detail pages
Both movies and TV shows have dedicated detail pages with:
- Hero section with blurred backdrop, poster, rating pills and genre tags
- Full synopsis
- Stats grid (year, runtime/seasons/episodes, budget)
- Director / Created By
- Top 5 cast members
- Streaming platforms available in the US (via TMDB Watch Providers)
- Watch Trailer and IMDb buttons
- **More Like This** — content-based recommendations (see below)

### 🤖 More Like This — content-based recommender
Every movie page suggests 10 similar films with a short reason ("Dir. Christopher Nolan · time travel · Science Fiction").

- **Features:** two TF-IDF blocks per film — the plot overview (unigrams + bigrams, English stop words removed) and tagged metadata tokens for genres, TMDB keywords, director and top-5 cast.
- **Similarity:** each block is L2-normalised and scaled by √weight, so the score between two films is exactly `w_text · cos(overview) + (1 − w_text) · cos(metadata)`.
- **Catalogue:** the ~5,000 most-voted films on TMDB, stored in `data/rec_corpus.json.gz` and fitted at first request (~2 s). Films outside the catalogue are vectorised on the fly from their TMDB metadata (cold start).
- **Evaluation:** `evaluate_recommender.py` uses TMDB's behaviour-based recommendations as held-out ground truth, tunes `w_text` on half of a random sample and reports precision@10, recall@10 and hit-rate@10 on the other half against random and popularity baselines, plus catalogue coverage. The app reads the tuned weight from `data/rec_eval.json`.

### 🔎 Search
Searches movies and TV shows simultaneously via TMDB. Results are re-ranked so exact title matches appear first, then partial matches, all sorted by popularity × rating so the most relevant result is always at the top.

### 📰 News
Fetches live headlines from Deadline and The Hollywood Reporter via RSS. Each article shows a cover image, date, summary and a link to the full article. Image extraction tries multiple RSS locations (media:content, enclosure, og:image) before giving up.

### 📊 Dashboard
Analytics section with three interactive Plotly charts:
- **Genre Heatmap** — each genre's share of the films released per decade (1970s–2020s), normalised by the decade total so the chart shows which genres grew rather than overall industry growth; a toggle switches to raw counts
- **Budget vs Rating scatter** — popular films plotted by inflation-adjusted budget (US CPI-U, 2025 dollars, log scale) against their TMDB rating, color-encoded by vote count; reports Spearman's ρ with a permutation-test p-value and the R² of a log-linear fit
- **Median ROI by Genre** — median return on investment per genre with 95% percentile-bootstrap confidence intervals, so overlapping genres are visibly indistinguishable; bars are color-coded (yellow = positive ROI, red = negative)

The statistics (CPI adjustment, ranks, Spearman, permutation test, bootstrap) live in `analytics.py` as dependency-free, unit-tested functions.

All charts are loaded asynchronously via AJAX to keep the initial page render fast.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask |
| Database | SQLite via cs50 SQL |
| External API | TMDB (The Movie Database) |
| Data source | IMDb open datasets |
| Charts | Plotly |
| Recommender | scikit-learn (TF-IDF, cosine similarity) |
| Tests | pytest |
| Frontend | Bootstrap 5, custom CSS, Lucide icons |
| Concurrency | `concurrent.futures.ThreadPoolExecutor` |

---

## Project structure

```
project_V02/
├── app.py               # Flask routes
├── helpers.py           # TMDB API calls, RSS parser, data helpers
├── analytics.py         # Dashboard statistics (CPI, Spearman, bootstrap…)
├── recommender.py       # Content-based recommender (TF-IDF)
├── build_rec_corpus.py  # Builds data/rec_corpus.json.gz from TMDB
├── evaluate_recommender.py  # Offline evaluation + weight tuning
├── update_movies_db.py  # Script to refresh movies.db from IMDb dumps
├── data/                # Recommender corpus and evaluation results
├── tests/               # pytest suite (TMDB calls are mocked)
├── movies.db            # SQLite database (titles, years, ratings)
├── requirements.txt
├── static/              # Genre images (movies + TV shows)
└── templates/
    ├── layout.html      # Base template (navbar, footer)
    ├── index.html       # Home — random movie roulette
    ├── apology.html     # Error page
    ├── recomendations.html
    ├── tvshows.html
    ├── movie_detail.html
    ├── tv_detail.html
    ├── trending.html
    ├── search.html
    ├── news.html
    └── dashboard.html
```

---

## Running locally

**1. Clone the repo and install dependencies**
```bash
git clone https://github.com/NLA1995/movie-roulette.git
cd movie-roulette
pip install -r requirements.txt
```

**2. Get a TMDB API key**

Create a free account at [themoviedb.org](https://www.themoviedb.org/), go to **Settings → API**, and request a key.

**3. Create a `.env` file in the project root**
```
TMDB_API_KEY=your-tmdb-api-key-here
```

**4. Run the development server**
```bash
flask run
```

Open `http://127.0.0.1:5000` in your browser.

---

## Refreshing the movie database

`movies.db` ships pre-populated. To update it with newer IMDb data:

1. Download the latest dumps from [datasets.imdbws.com](https://datasets.imdbws.com/):
   - `title.basics.tsv.gz`
   - `title.ratings.tsv.gz`
2. Place both files in the project root (`name.basics.tsv.gz` is **not** needed)
3. Run:
```bash
python update_movies_db.py
```

> Note: the `.tsv.gz` files are several hundred MB and are excluded from the repository via `.gitignore`.

---

## Building the recommender

```bash
python build_rec_corpus.py        # ~5,000 films, a few minutes
python evaluate_recommender.py    # tunes w_text, writes data/rec_eval.json
```

Commit both files in `data/`. Without the corpus the app still runs; the "More Like This" section simply stays hidden.

## Running the tests

```bash
pytest
```

---

## Environment variables

| Variable | Description |
|---|---|
| `TMDB_API_KEY` | Your TMDB API key — get one free at [themoviedb.org](https://www.themoviedb.org/) |

Loaded from a `.env` file locally (via `python-dotenv`) and from the environment in production.

---

## Deployment (Render)

1. Push the repo to GitHub (`.tsv.gz` files and `.env` excluded via `.gitignore`)
2. Create a new **Web Service** on [Render](https://render.com)
3. Set **Build Command**: `pip install -r requirements.txt`
4. Set **Start Command**: `gunicorn app:app`
5. Add `TMDB_API_KEY` in the Render environment variables panel
6. Deploy

---

## Design decisions

The UI is dark and minimal by design — keeping focus on the posters and content rather than the interface itself. Bootstrap handles the responsive layout and navbar; custom CSS takes over for the detail pages, genre grids and card hover effects. Genre buttons use real background images with brightness and zoom effects for a more cinematic feel, matching what you'd find on a proper streaming platform.

The app requires no login — anyone can browse immediately, keeping the focus on content discovery.
