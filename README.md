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

### 🔎 Search
Searches movies and TV shows simultaneously via TMDB. Results are re-ranked so exact title matches appear first, then partial matches, all sorted by popularity × rating so the most relevant result is always at the top.

### 📰 News
Fetches live headlines from Deadline and The Hollywood Reporter via RSS. Each article shows a cover image, date, summary and a link to the full article. Image extraction tries multiple RSS locations (media:content, enclosure, og:image) before giving up.

### 📊 Dashboard
Analytics section with three interactive Plotly charts:
- **Genre Heatmap** — film counts per genre per decade (1970s–2020s), color-scaled by volume
- **Budget vs Rating scatter** — popular films plotted by production budget against their TMDB rating, color-encoded by vote count
- **Median ROI by Genre** — bar chart showing median return on investment per genre, based on budget vs. revenue data from TMDB; bars are color-coded (yellow = positive ROI, red = negative)

All charts are loaded asynchronously via AJAX to keep the initial page render fast.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3, Flask, Flask-Session |
| Database | SQLite via cs50 SQL |
| External API | TMDB (The Movie Database) |
| Data source | IMDb open datasets |
| Charts | Plotly |
| Frontend | Bootstrap 5, custom CSS, Lucide icons |
| Auth | Werkzeug password hashing (pbkdf2:sha256) |
| Concurrency | `concurrent.futures.ThreadPoolExecutor` |

---

## Project structure

```
project_V02/
├── app.py               # Flask routes
├── helpers.py           # TMDB API calls, RSS parser, auth helpers
├── update_movies_db.py  # Script to refresh movies.db from IMDb dumps
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
    ├── dashboard.html
    ├── login.html
    └── register.html
```

---

## Running locally

**1. Clone the repo and install dependencies**
```bash
git clone <your-repo-url>
cd project_V02
pip install -r requirements.txt
```

**2. Get a TMDB API key**

Create a free account at [themoviedb.org](https://www.themoviedb.org/), go to **Settings → API**, and request a key.

**3. Create a `.env` file in the project root**
```
TMDB_API_KEY=your-tmdb-api-key-here
SECRET_KEY=any-random-string-here
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

## Environment variables

| Variable | Description |
|---|---|
| `TMDB_API_KEY` | Your TMDB API key — get one free at [themoviedb.org](https://www.themoviedb.org/) |
| `SECRET_KEY` | Flask session secret — any random string works for local dev |

Both variables are loaded from a `.env` file locally (via `python-dotenv`) and from the environment in production.

---

## Deployment (Render)

1. Push the repo to GitHub (`.tsv.gz` files and `.env` excluded via `.gitignore`)
2. Create a new **Web Service** on [Render](https://render.com)
3. Set **Build Command**: `pip install -r requirements.txt`
4. Set **Start Command**: `gunicorn app:app`
5. Add `TMDB_API_KEY` and `SECRET_KEY` in the Render environment variables panel
6. Deploy

---

## Design decisions

The UI is dark and minimal by design — keeping focus on the posters and content rather than the interface itself. Bootstrap handles the responsive layout and navbar; custom CSS takes over for the detail pages, genre grids and card hover effects. Genre buttons use real background images with brightness and zoom effects for a more cinematic feel, matching what you'd find on a proper streaming platform.

Password validation requires a minimum of 6 characters. Sessions are server-side (filesystem) via Flask-Session.
