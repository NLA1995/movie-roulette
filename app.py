import math
import os
from dotenv import load_dotenv
load_dotenv()
import random
import json
import plotly.graph_objects as go
from plotly.utils import PlotlyJSONEncoder
from concurrent.futures import ThreadPoolExecutor, as_completed

from cs50 import SQL
from flask import Flask, jsonify, redirect, render_template, request

from helpers import (
    apology,
    tmdb_search, tmdb_search_popular, tmdb_search_tv,
    tmdb_search_with_country, tmdb_by_genre, tmdb_detail,
    tmdb_now_playing, tmdb_upcoming,
    tmdb_tv_by_genre, tmdb_tv_detail, tmdb_rec_features, get_news_articles,
    TMDB_IMG_BASE,
    get_genres_by_decade, get_budget_vs_rating, get_roi_by_genre, DECADES,
)
from recommender import get_recommender
from analytics import (
    CPI_BASE_YEAR, bootstrap_ci, linear_regression, median,
    permutation_pvalue, share_by_column, spearman,
)

app = Flask(__name__)

db = SQL("sqlite:///movies.db")

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
    """Render the home page shell instantly; movie data loads via AJAX."""
    return render_template("index.html")


@app.route("/movies-data")
def movies_data():
    """Return 15 random well-rated films as JSON for the homepage AJAX call.

    Picks 15 random years between 1940 and 2024, queries the local database for
    one highly rated film per year (rating >= 5.0, votes >= 1000), then enriches
    each result with poster, overview, and country of origin from TMDB.
    Falls back to random well-rated films for any year that returns no results.
    """
    years = random.sample(range(1940, 2025), 15)

    placeholders = ",".join("?" * len(years))
    rows = db.execute(
        f"""SELECT title, year, rating FROM movies
            INNER JOIN ratings ON id = movie_id
            WHERE year IN ({placeholders}) AND rating >= 5.0 AND votes >= 1000
            ORDER BY RANDOM()""",
        *years
    )
    seen_years, mov = set(), []
    for row in rows:
        if row["year"] not in seen_years:
            seen_years.add(row["year"])
            mov.append(row)
            if len(mov) == 15:
                break

    if len(mov) < 15:
        extras = db.execute(
            """SELECT title, year, rating FROM movies
               INNER JOIN ratings ON id = movie_id
               WHERE rating >= 5.0 AND votes >= 1000
               ORDER BY RANDOM()
               LIMIT ?""",
            15 - len(mov)
        )
        mov.extend(extras)

    mov = sorted(mov[:15], key=lambda x: x["rating"], reverse=True)

    def enrich(film):
        tmdb = tmdb_search_with_country(film["title"], year=film["year"])
        return {
            "title":    film["title"],
            "year":     film["year"],
            "rating":   film["rating"],
            "poster":   tmdb["poster"]   if tmdb else None,
            "overview": tmdb["overview"] if tmdb else "No description available.",
            "country":  tmdb["country"]  if tmdb else None,
            "tmdb_id":  tmdb["tmdb_id"]  if tmdb else None,
        }

    result = [None] * len(mov)
    with ThreadPoolExecutor(max_workers=15) as ex:
        futures = {ex.submit(enrich, film): idx for idx, film in enumerate(mov)}
        for future in as_completed(futures):
            result[futures[future]] = future.result()

    return jsonify(result)


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
    return render_template("movie_detail.html", movie=movie, tmdb_id=tmdb_id)


@app.route("/movie/<int:tmdb_id>/similar")
def movie_similar(tmdb_id):
    """Return up to 10 content-based recommendations for a movie as JSON.

    Films in the precomputed corpus use their stored vector; any other film is
    vectorised on the fly from its TMDB metadata (cold start). Returns [] when
    the corpus has not been built yet.
    """
    model = get_recommender()
    if model is None:
        return jsonify([])

    source = model.films[model.index[tmdb_id]] if tmdb_id in model.index else tmdb_rec_features(tmdb_id)
    if not source:
        return jsonify([])

    results = []
    for j, score in model.recommend(tmdb_id, k=10, film=source):
        f = model.films[j]
        results.append({
            "tmdb_id": f["id"],
            "title":   f["title"],
            "year":    f["year"],
            "rating":  round(f["rating"], 1),
            "poster":  TMDB_IMG_BASE + f["poster_path"] if f.get("poster_path") else None,
            "score":   round(score, 3),
            "why":     model.explain(source, f),
        })
    return jsonify(results)


# ── DASHBOARD ────────────────────────────────────────────────────────────────
@app.route("/dashboard")
def dashboard():
    """Render the analytics dashboard shell; chart data is loaded via AJAX."""
    return render_template("dashboard.html")


def _empty_chart():
    """JSON response the dashboard JS treats as 'no data' (renders an error note)."""
    return app.response_class(json.dumps({}), mimetype="application/json")


def _figure_response(fig):
    return app.response_class(
        json.dumps(fig, cls=PlotlyJSONEncoder),
        mimetype="application/json"
    )


@app.route("/dashboard/genres-data")
def dashboard_genres_data():
    """Return a Plotly heatmap (JSON) of genres per decade.

    Default view is each genre's share of the decade's films (normalised by
    the decade total), so the chart shows which genres grew rather than the fact
    that more films are made every decade. A button toggles back to raw counts.
    """
    data = get_genres_by_decade()
    if not data:
        return _empty_chart()

    decades = list(DECADES)
    counts  = data["counts"]
    totals  = data["totals"]
    shares  = share_by_column(counts, totals)
    # Sort genres by their latest share so the heatmap reads top-to-bottom
    genres  = sorted(counts, key=lambda g: shares[g][decades[-1]])

    z_share = [[round(shares[g][d], 1) for d in decades] for g in genres]
    z_count = [[counts[g].get(d, 0) for d in decades] for g in genres]
    x_labels = [f"{d}<br><sub>n={totals.get(d, 0):,}</sub>" for d in decades]

    share_hover = "<b>%{y}</b><br>%{x}: %{z:.1f}% of the decade's films<extra></extra>"
    count_hover = "<b>%{y}</b><br>%{x}: %{z:,} films<extra></extra>"

    fig = go.Figure(data=go.Heatmap(
        z=z_share, x=decades, y=genres,
        colorscale="YlOrRd",
        colorbar=dict(title=dict(text="% of decade"), ticksuffix="%"),
        hovertemplate=share_hover,
    ))
    fig.update_layout(
        paper_bgcolor="#141414", plot_bgcolor="#141414",
        font=dict(color="white", family="Inter"),
        title=dict(text="Genre share by decade (% of films with 50+ votes)",
                   font=dict(size=18)),
        margin=dict(l=110, r=20, t=100, b=40),
        xaxis=dict(side="bottom", tickmode="array", tickvals=decades, ticktext=x_labels),
        updatemenus=[dict(
            type="buttons", direction="right",
            x=1, xanchor="right", y=1.18, yanchor="top",
            bgcolor="#bdbdbd", bordercolor="#555", font=dict(color="#141414"),
            showactive=True, active=0,
            buttons=[
                dict(label="Share (%)", method="update", args=[
                    {"z": [z_share], "hovertemplate": [share_hover],
                     "colorbar.title.text": ["% of decade"], "colorbar.ticksuffix": ["%"]},
                    {"title.text": "Genre share by decade (% of films with 50+ votes)"},
                ]),
                dict(label="Film count", method="update", args=[
                    {"z": [z_count], "hovertemplate": [count_hover],
                     "colorbar.title.text": ["Films"], "colorbar.ticksuffix": [""]},
                    {"title.text": "Films per genre by decade (raw count)"},
                ]),
            ],
        )],
    )
    return _figure_response(fig)


@app.route("/dashboard/budget-data")
def dashboard_budget_data():
    """Return a Plotly scatter of inflation-adjusted budget vs. TMDB rating.

    Budgets are converted to CPI_BASE_YEAR dollars and plotted on a log axis
    (budgets span two orders of magnitude and are right-skewed). The trend line
    is OLS of rating on log10(budget). The title reports Spearman's ρ with a
    permutation p-value, which is robust to the skew and to outliers, plus the
    R² of the log-linear fit.
    """
    data = get_budget_vs_rating()
    if not data or len(data) < 3:
        return _empty_chart()

    x     = [m["budget_real_m"] for m in data]
    y     = [m["rating"]        for m in data]
    log_x = [math.log10(v) for v in x]

    rho   = spearman(x, y)
    p_val = permutation_pvalue(x, y, stat=spearman)
    slope, intercept, r2 = linear_regression(log_x, y)

    x_line = [min(x), max(x)]
    y_line = [intercept + slope * math.log10(v) for v in x_line]

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
            f"Budget: ${m['budget_m']}M nominal · ${m['budget_real_m']}M in {CPI_BASE_YEAR} USD<br>"
            f"Rating: {m['rating']} ⭐"
            for m in data
        ],
        hovertemplate="%{text}<extra></extra>",
    )

    reg_line = go.Scatter(
        x=x_line, y=y_line,
        mode="lines",
        name=f"OLS on log budget (R² = {r2:.3f})",
        line=dict(color="#f5c518", width=2, dash="dash"),
        hoverinfo="skip",
    )

    p_txt = "p < 0.001" if p_val < 0.001 else f"p = {p_val:.3f}"
    fig = go.Figure(data=[scatter, reg_line])
    fig.update_layout(
        paper_bgcolor="#141414", plot_bgcolor="#1e1e1e",
        font=dict(color="white", family="Inter"),
        title=dict(
            text=(f"Budget vs. Rating — n = {len(data)}  |  "
                  f"Spearman ρ = {rho:+.2f} ({p_txt})"),
            font=dict(size=18),
        ),
        xaxis=dict(title=f"Budget (millions of {CPI_BASE_YEAR} USD, log scale)",
                   type="log", gridcolor="#333", zeroline=False),
        yaxis=dict(title="TMDB Rating", gridcolor="#333", zeroline=False),
        legend=dict(
            font=dict(color="white"),
            orientation="h",
            x=0, y=-0.2,
        ),
        margin=dict(l=60, r=20, t=60, b=80),
    )
    return _figure_response(fig)


@app.route("/dashboard/roi-data")
def dashboard_roi_data():
    """Return a Plotly bar chart of median ROI by genre with 95% bootstrap CIs.

    The error bars are percentile-bootstrap intervals for the median (2,000
    resamples, fixed seed). With n ≤ 20 per genre the intervals are wide and
    often overlap — that overlap is the honest answer to "which genre is best".
    """
    rois_by_genre = get_roi_by_genre()
    if not rois_by_genre:
        return _empty_chart()

    data = []
    for genre, rois in rois_by_genre.items():
        lo, hi = bootstrap_ci(rois, stat=median)
        data.append({"genre": genre, "roi": median(rois),
                     "lo": lo, "hi": hi, "n": len(rois)})
    data.sort(key=lambda d: d["roi"], reverse=True)

    colors = ["#f5c518" if d["roi"] >= 0 else "#e05c5c" for d in data]
    y_min  = min(min(d["lo"] for d in data) * 1.1, 0)
    y_max  = max(max(d["hi"] for d in data) * 1.1, 0)

    fig = go.Figure(data=go.Bar(
        x=[d["genre"] for d in data],
        y=[d["roi"] for d in data],
        marker_color=colors,
        error_y=dict(
            type="data", symmetric=False,
            array=[d["hi"] - d["roi"] for d in data],
            arrayminus=[d["roi"] - d["lo"] for d in data],
            color="#bbbbbb", thickness=1.5, width=6,
        ),
        customdata=[[d["lo"], d["hi"], d["n"]] for d in data],
        hovertemplate=(
            "<b>%{x}</b><br>"
            "Median ROI: %{y:,.0f}%<br>"
            "95% CI: %{customdata[0]:,.0f}% to %{customdata[1]:,.0f}%<br>"
            "Films: %{customdata[2]}"
            "<extra></extra>"
        ),
    ))
    fig.update_layout(
        paper_bgcolor="#141414", plot_bgcolor="#1e1e1e",
        font=dict(color="white", family="Inter"),
        title=dict(text="Median ROI by Genre with 95% bootstrap CI",
                   font=dict(size=18)),
        xaxis=dict(title="Genre", gridcolor="#333", zeroline=False, tickmode="array",
                   tickvals=[d["genre"] for d in data],
                   ticktext=[f"{d['genre']}<br><sub>n={d['n']}</sub>" for d in data]),
        yaxis=dict(title="Median ROI (%)", gridcolor="#333", zeroline=True,
                   zerolinecolor="#555", zerolinewidth=1,
                   range=[y_min, y_max]),
        margin=dict(l=60, r=20, t=80, b=80),
        showlegend=False,
    )
    return _figure_response(fig)
