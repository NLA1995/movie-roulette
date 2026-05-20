import os
from dotenv import load_dotenv
load_dotenv()
import random
import json
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder
from concurrent.futures import ThreadPoolExecutor, as_completed

from flask import Flask, redirect, render_template, request

from helpers import (
    apology,
    tmdb_search, tmdb_search_popular, tmdb_search_tv,
    tmdb_search_with_country, tmdb_by_genre, tmdb_detail,
    tmdb_now_playing, tmdb_upcoming,
    tmdb_tv_by_genre, tmdb_tv_detail, get_news_articles,
    TMDB_GENRES, TMDB_TV_GENRES, usd,
    get_genres_by_decade, get_budget_vs_rating, get_roi_by_genre,
    get_homepage_pool,
)

app = Flask(__name__)

@app.template_filter('format_budget')
def format_budget(value):
    """Jinja2 filter: format a numeric budget as a comma-separated USD string."""
    return f"${value:,.0f}"

@app.after_request
def after_request(response):
    """Disable caching on every response so fresh data is always served."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# ── INDEX ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    """Home page: display 15 randomly selected well-rated films.

    Draws from a cached pool of ~70 movies spread across decades (1950s–2020s).
    The pool is refreshed every hour via a single batch of TMDB requests; each
    visit picks a fresh random 15 from the pool — no TMDB calls per request.
    """
    pool = get_homepage_pool()
    mov  = random.sample(pool, min(15, len(pool))) if pool else []
    return render_template("index.html", mov=mov)


# ── NEWS ────────────────────────────────────────────────────────────────────
@app.route("/news")
def news():
    """Fetch and display the latest articles from Deadline and The Hollywood Reporter."""
    deadline_articles, thr_articles = get_news_articles()
    return render_template("news.html",
                           deadline_articles=deadline_articles,
                           thr_articles=thr_articles)


# ── TRENDING ────────────────────────────────────────────────────────────────
@app.route("/trending")
def trending():
    """Display movies currently in theaters and upcoming releases from TMDB."""
    now_playing = tmdb_now_playing()
    upcoming    = tmdb_upcoming()
    return render_template("trending.html", now_playing=now_playing, upcoming=upcoming)


# ── MOVIES ──────────────────────────────────────────────────────────────────
@app.route("/recomendations", methods=["GET", "POST"])
def recomendations():
    """Show movie recommendations filtered by genre.

    On GET renders an empty form. On POST fetches up to 3 pages of top-rated
    movies for the selected genre from TMDB and renders the results.
    """
    movies = []
    selected_genre = None
    if request.method == "POST":
        selected_genre = request.form.get("genre")
        if selected_genre:
            movies = tmdb_by_genre(selected_genre, pages=3)
    return render_template("recomendations.html", movies=movies, selected_genre=selected_genre)


# ── TV SHOWS ────────────────────────────────────────────────────────────────
@app.route("/tvshows", methods=["GET", "POST"])
def tvshows():
    """Show TV show recommendations filtered by genre.

    On GET renders an empty form. On POST fetches up to 3 pages of top-rated
    TV shows for the selected genre from TMDB and renders the results.
    """
    shows = []
    selected_genre = None
    if request.method == "POST":
        selected_genre = request.form.get("genre")
        if selected_genre:
            shows = tmdb_tv_by_genre(selected_genre, pages=3)
    return render_template("tvshows.html", shows=shows, selected_genre=selected_genre)


# ── SEARCH ──────────────────────────────────────────────────────────────────
@app.route("/search", methods=["GET", "POST"])
def search():
    """Search for movies and TV shows simultaneously via TMDB.

    On POST, queries both /search/movie and /search/tv with the user's query
    and returns results for both tabs. The active tab (movies or tv) is
    preserved across the form submission so the UI stays on the correct tab.
    """
    movie_results = []
    tv_results    = []
    query         = ""
    tab           = "movies"

    if request.method == "POST":
        query = request.form.get("query", "").strip()
        tab   = request.form.get("tab", "movies")
        if query:
            movie_results = tmdb_search_popular(query)
            tv_results    = tmdb_search_tv(query)

    return render_template("search.html",
                           movie_results=movie_results,
                           tv_results=tv_results,
                           query=query,
                           tab=tab)


# ── TV SHOW DETAIL ──────────────────────────────────────────────────────────
@app.route("/tv/<int:tmdb_id>")
def tv_detail(tmdb_id):
    """Render the full detail page for a single TV show identified by its TMDB ID."""
    show = tmdb_tv_detail(tmdb_id)
    if not show:
        return apology("TV show not found", 404)
    return render_template("tv_detail.html", show=show)


# ── MOVIE DETAIL ────────────────────────────────────────────────────────────
@app.route("/movie/<int:tmdb_id>")
def movie_detail(tmdb_id):
    """Render the full detail page for a single movie identified by its TMDB ID."""
    movie = tmdb_detail(tmdb_id)
    if not movie:
        return apology("Movie not found", 404)
    return render_template("movie_detail.html", movie=movie)


# ── DASHBOARD ────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    """Render the analytics dashboard shell; chart data is loaded via AJAX."""
    return render_template("dashboard.html")


@app.route("/dashboard/genres-data")
def dashboard_genres_data():
    """Return a Plotly heatmap figure (JSON) of film counts per genre per decade.

    Data is cached for 12 hours. The color scale runs from light yellow (low)
    to dark red (high) using the YlOrRd palette.
    """
    data    = get_genres_by_decade()
    decades = ["1970s", "1980s", "1990s", "2000s", "2010s", "2020s"]
    genres  = list(data.keys())
    z       = [[data[g][d] for d in decades] for g in genres]

    fig = go.Figure(data=go.Heatmap(
        z=z, x=decades, y=genres,
        colorscale="YlOrRd",
        hovertemplate="<b>%{y}</b><br>%{x}: %{z:,} films<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="#141414", plot_bgcolor="#141414",
        font=dict(color="white", family="Inter"),
        title=dict(text="Films per Genre by Decade", font=dict(size=18)),
        margin=dict(l=110, r=20, t=60, b=40),
        xaxis=dict(side="bottom"),
    )
    return app.response_class(
        json.dumps(fig, cls=PlotlyJSONEncoder),
        mimetype="application/json"
    )


@app.route("/dashboard/budget-data")
def dashboard_budget_data():
    """Return a Plotly scatter + regression line figure of budget vs. TMDB rating."""
    data = get_budget_vs_rating()

    x = [m["budget_m"] for m in data]
    y = [m["rating"]   for m in data]

    # Linear regression (pure Python — no numpy needed)
    n      = len(x)
    x_mean = sum(x) / n
    y_mean = sum(y) / n
    num    = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    den    = sum((xi - x_mean) ** 2 for xi in x)
    slope     = num / den if den else 0
    intercept = y_mean - slope * x_mean
    y_pred    = [slope * xi + intercept for xi in x]
    ss_res    = sum((yi - yp) ** 2 for yi, yp in zip(y, y_pred))
    ss_tot    = sum((yi - y_mean) ** 2 for yi in y)
    r2        = round(1 - ss_res / ss_tot, 3) if ss_tot else 0

    x_line = [min(x), max(x)]
    y_line = [slope * xi + intercept for xi in x_line]

    scatter = go.Scatter(
        x=x, y=y,
        mode="markers",
        name="Films",
        marker=dict(
            size=10,
            color=[m["votes"] for m in data],
            colorscale="Viridis",
            showscale=True,
            colorbar=dict(
                title=dict(text="Votes", font=dict(color="white")),
                tickfont=dict(color="white"),
            ),
            opacity=0.8,
        ),
        text=[
            f"<b>{m['title']}</b> ({m['year']})<br>"
            f"{m['genres']}<br>"
            f"Budget: ${m['budget_m']}M<br>"
            f"Rating: {m['rating']} ⭐"
            for m in data
        ],
        hovertemplate="%{text}<extra></extra>",
    )

    reg_line = go.Scatter(
        x=x_line, y=y_line,
        mode="lines",
        name="Trend line",
        line=dict(color="#f5c518", width=2, dash="dash"),
        hoverinfo="skip",
    )

    fig = go.Figure(data=[scatter, reg_line])
    fig.update_layout(
        paper_bgcolor="#141414", plot_bgcolor="#1e1e1e",
        font=dict(color="white", family="Inter"),
        title=dict(
            text=f"Budget vs. Rating — popular films with 1 000+ votes  |  R² = {r2}",
            font=dict(size=18),
        ),
        xaxis=dict(title="Budget (millions USD)", gridcolor="#333", zeroline=False),
        yaxis=dict(title="TMDB Rating", gridcolor="#333", zeroline=False),
        legend=dict(
            font=dict(color="white"),
            orientation="h",
            x=0, y=-0.15,
        ),
        margin=dict(l=60, r=20, t=60, b=60),
    )
    return app.response_class(
        json.dumps(fig, cls=PlotlyJSONEncoder),
        mimetype="application/json"
    )


@app.route("/dashboard/roi-data")
def dashboard_roi_data():
    """Return a Plotly bar chart of median ROI by genre."""
    data = get_roi_by_genre()

    if not data:
        return app.response_class(
            json.dumps({}), mimetype="application/json"
        )

    colors = ["#f5c518" if d["roi"] >= 0 else "#e05c5c" for d in data]

    all_rois = [d["roi"] for d in data]
    y_min = min(min(all_rois) * 1.25, 0)
    y_max = max(max(all_rois) * 1.25, 0)

    fig = go.Figure(data=go.Bar(
        x=[d["genre"] for d in data],
        y=[d["roi"]   for d in data],
        marker_color=colors,
        text=[f"{d['roi']:+.0f}%  (n={d['sample_size']})" for d in data],
        textposition="outside",
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Median ROI: %{y:.1f}%<br>"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        paper_bgcolor="#141414", plot_bgcolor="#1e1e1e",
        font=dict(color="white", family="Inter"),
        title=dict(text="Median ROI by Genre — does your genre make money?",
                   font=dict(size=18)),
        xaxis=dict(title="Genre", gridcolor="#333", zeroline=False),
        yaxis=dict(title="Median ROI (%)", gridcolor="#333", zeroline=True,
                   zerolinecolor="#555", zerolinewidth=1,
                   range=[y_min, y_max]),
        margin=dict(l=60, r=20, t=80, b=80),
        showlegend=False,
    )
    return app.response_class(
        json.dumps(fig, cls=PlotlyJSONEncoder),
        mimetype="application/json"
    )

