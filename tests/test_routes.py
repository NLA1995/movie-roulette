import json

import pytest

import app as app_module

GENRES_DATA = {
    "counts": {"Drama": {"1970s": 100, "1980s": 200, "1990s": 300, "2000s": 400, "2010s": 500, "2020s": 300},
               "Horror": {"1970s": 10, "1980s": 30, "1990s": 30, "2000s": 80}},   # missing decades
    "totals": {"1970s": 250, "1980s": 400, "1990s": 600, "2000s": 900, "2010s": 1200, "2020s": 700},
}
BUDGET_DATA = [
    {"title": f"Film {i}", "year": str(1980 + i), "genres": "Drama", "votes": 1000 + i,
     "budget_m": 5.0 * (i + 1), "budget_real_m": 8.0 * (i + 1), "rating": 6 + (i % 5) * 0.4}
    for i in range(12)
]
ROI_DATA = {"Horror": [400, 900, 1500, 250, 60], "Action": [50, 120, -20, 200], "Drama": [-40, 10, 30]}


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_genres_heatmap_defaults_to_share(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_genres_by_decade", lambda: GENRES_DATA)
    fig = json.loads(client.get("/dashboard/genres-data").data)
    z = fig["data"][0]["z"]
    y = fig["data"][0]["y"]
    drama = z[y.index("Drama")]
    assert drama[0] == pytest.approx(40.0)          # 100 / 250
    assert z[y.index("Horror")][-1] == 0             # missing decade -> 0, no KeyError
    assert [b["label"] for b in fig["layout"]["updatemenus"][0]["buttons"]] == ["Share (%)", "Film count"]


def test_budget_chart_uses_log_axis_and_reports_spearman(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_budget_vs_rating", lambda: BUDGET_DATA)
    fig = json.loads(client.get("/dashboard/budget-data").data)
    assert fig["layout"]["xaxis"]["type"] == "log"
    assert "Spearman" in fig["layout"]["title"]["text"]
    assert len(fig["data"][0]["x"]) == len(BUDGET_DATA)


def test_roi_chart_has_asymmetric_ci(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_roi_by_genre", lambda: ROI_DATA)
    fig = json.loads(client.get("/dashboard/roi-data").data)
    bar = fig["data"][0]
    assert bar["x"][0] == "Horror"                   # sorted by median desc
    assert bar["error_y"]["symmetric"] is False
    assert all(v >= 0 for v in bar["error_y"]["array"] + bar["error_y"]["arrayminus"])


@pytest.mark.parametrize("endpoint, helper, empty", [
    ("/dashboard/genres-data", "get_genres_by_decade", None),
    ("/dashboard/budget-data", "get_budget_vs_rating", []),
    ("/dashboard/roi-data", "get_roi_by_genre", {}),
])
def test_empty_data_returns_empty_json_not_500(client, monkeypatch, endpoint, helper, empty):
    monkeypatch.setattr(app_module, helper, lambda: empty)
    r = client.get(endpoint)
    assert r.status_code == 200 and json.loads(r.data) == {}


def test_similar_returns_empty_list_without_corpus(client, monkeypatch):
    monkeypatch.setattr(app_module, "get_recommender", lambda: None)
    assert json.loads(client.get("/movie/27205/similar").data) == []


def test_similar_returns_cards(client, monkeypatch):
    from recommender import ContentRecommender
    from tests.test_recommender import FILMS
    model = ContentRecommender(FILMS)
    monkeypatch.setattr(app_module, "get_recommender", lambda: model)
    items = json.loads(client.get("/movie/2/similar").data)
    assert items and {"tmdb_id", "title", "poster", "score", "why"} <= set(items[0])
