import pytest

from recommender import ContentRecommender, meta_tokens

FILMS = [
    {"id": 1, "title": "Space Odyssey", "year": "1968", "overview": "astronauts travel through space to a distant planet",
     "genres": ["Science Fiction"], "keywords": ["space travel", "artificial intelligence"],
     "director": ["Stanley Kubrick"], "cast": ["Keir Dullea"], "rating": 8.1, "votes": 10000},
    {"id": 2, "title": "Interstellar", "year": "2014", "overview": "astronauts travel through a wormhole in space to save humanity",
     "genres": ["Science Fiction", "Drama"], "keywords": ["space travel", "wormhole"],
     "director": ["Christopher Nolan"], "cast": ["Matthew McConaughey"], "rating": 8.4, "votes": 30000},
    {"id": 3, "title": "Love Actually", "year": "2003", "overview": "intertwined love stories in london at christmas",
     "genres": ["Romance", "Comedy"], "keywords": ["christmas", "london"],
     "director": ["Richard Curtis"], "cast": ["Hugh Grant"], "rating": 7.0, "votes": 8000},
    {"id": 4, "title": "Notting Hill", "year": "1999", "overview": "a london bookseller falls in love with a movie star",
     "genres": ["Romance", "Comedy"], "keywords": ["london", "bookshop"],
     "director": ["Roger Michell"], "cast": ["Hugh Grant"], "rating": 7.2, "votes": 6000},
    {"id": 5, "title": "Inception", "year": "2010", "overview": "a thief enters dreams to plant an idea",
     "genres": ["Action", "Science Fiction"], "keywords": ["dream", "heist"],
     "director": ["Christopher Nolan"], "cast": ["Leonardo DiCaprio"], "rating": 8.4, "votes": 35000},
]


@pytest.fixture(scope="module")
def model():
    return ContentRecommender(FILMS, text_weight=0.5)


def test_meta_tokens_are_prefixed_and_slugged():
    toks = meta_tokens(FILMS[1])
    assert "g:science_fiction" in toks and "d:christopher_nolan" in toks and "k:space_travel" in toks


def test_recommend_finds_obvious_neighbour_and_excludes_self(model):
    ids = [model.films[j]["id"] for j, _ in model.recommend(1, k=3)]
    assert ids[0] == 2
    assert 1 not in ids


def test_romcoms_recommend_each_other(model):
    assert model.films[model.recommend(3, k=1)[0][0]]["id"] == 4


def test_scores_are_sorted_and_bounded(model):
    scores = [s for _, s in model.recommend(2, k=4)]
    assert scores == sorted(scores, reverse=True)
    assert all(0 < s <= 1.0 + 1e-9 for s in scores)


def test_cold_start_uses_features(model):
    new_film = {"overview": "a crew of astronauts travel into deep space",
                "genres": ["Science Fiction"], "keywords": ["space travel"], "director": [], "cast": []}
    top = model.films[model.recommend(999, k=1, film=new_film)[0][0]]["id"]
    assert top in (1, 2)


def test_unknown_id_without_features_returns_empty(model):
    assert model.recommend(999) == []


def test_explain_lists_shared_director_first(model):
    reasons = model.explain(FILMS[1], FILMS[4])
    assert reasons[0] == "Dir. Christopher Nolan"
    assert "Science Fiction" in reasons


@pytest.mark.parametrize("w", [0.0, 1.0])
def test_extreme_weights_work(w):
    m = ContentRecommender(FILMS, text_weight=w)
    assert m.recommend(1, k=2)
