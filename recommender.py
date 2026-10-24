"""Content-based movie recommender ("More like this").

Each film is represented by two TF-IDF vectors:

* text  — the plot overview (English stop words removed, unigrams + bigrams)
* meta  — tagged tokens for genres, TMDB keywords, director and top-5 cast,
          e.g. "g:science_fiction", "k:time_travel", "d:christopher_nolan"

Both blocks are L2-normalised and scaled by the square root of their weight,
so the dot product of two films is exactly

    score = w_text · cos(text_a, text_b) + w_meta · cos(meta_a, meta_b)

which keeps the score interpretable (a weighted average of two cosine
similarities in [0, 1]). The weight is tuned offline by evaluate_recommender.py.

The model is fitted from data/rec_corpus.json.gz at first use (~1 s for 5,000
films); nothing is pickled, so there are no scikit-learn version mismatches
between the machine that built the corpus and Render.
"""
import gzip
import json
import os
import re
import threading

import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

DATA_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CORPUS_PATH  = os.path.join(DATA_DIR, "rec_corpus.json.gz")
EVAL_PATH    = os.path.join(DATA_DIR, "rec_eval.json")
DEFAULT_TEXT_WEIGHT = 0.5


def _slug(name):
    return re.sub(r"\W+", "_", name.lower()).strip("_")


def meta_tokens(film):
    """Tagged metadata tokens for one film (prefix keeps vocabularies apart)."""
    return ([f"g:{_slug(x)}" for x in film.get("genres", [])]
            + [f"k:{_slug(x)}" for x in film.get("keywords", [])]
            + [f"d:{_slug(x)}" for x in film.get("director", [])]
            + [f"c:{_slug(x)}" for x in film.get("cast", [])])


def _identity(tokens):
    return tokens


class ContentRecommender:
    def __init__(self, films, text_weight=DEFAULT_TEXT_WEIGHT):
        if not films:
            raise ValueError("empty corpus")
        self.films  = films
        self.index  = {f["id"]: i for i, f in enumerate(films)}
        self.w_text = float(text_weight)

        small = len(films) < 50          # keeps unit tests on tiny corpora working
        self.text_vec = TfidfVectorizer(
            stop_words="english", sublinear_tf=True, ngram_range=(1, 2),
            min_df=1 if small else 2, max_df=1.0 if small else 0.5,
        )
        self.meta_vec = TfidfVectorizer(
            analyzer=_identity, sublinear_tf=True, min_df=1 if small else 2,
        )
        text_m = self.text_vec.fit_transform(f.get("overview", "") for f in films)
        meta_m = self.meta_vec.fit_transform(meta_tokens(f) for f in films)
        self.X = self._combine(text_m, meta_m)

    # ── vectors ────────────────────────────────────────────────────────────
    def _combine(self, text_m, meta_m):
        a = np.sqrt(self.w_text)
        b = np.sqrt(1.0 - self.w_text)
        return hstack([a * normalize(text_m), b * normalize(meta_m)]).tocsr()

    def vectorize(self, film):
        """Vector for a film that may not be in the corpus (cold start)."""
        return self._combine(self.text_vec.transform([film.get("overview", "")]),
                             self.meta_vec.transform([meta_tokens(film)]))

    # ── queries ────────────────────────────────────────────────────────────
    def scores_for(self, vec):
        return (self.X @ vec.T).toarray().ravel()

    def top_k(self, scores, k=10, exclude=()):
        scores = scores.copy()
        for i in exclude:
            scores[i] = -1.0
        k = min(k, len(scores))
        idx = np.argpartition(-scores, k - 1)[:k]
        idx = idx[np.argsort(-scores[idx])]
        return [int(i) for i in idx if scores[i] > 0]

    def recommend(self, tmdb_id, k=10, film=None):
        """Top-k similar films as (corpus_index, score) pairs.

        Uses the stored vector when tmdb_id is in the corpus, otherwise
        vectorises `film` (a feature dict like the corpus entries). Returns []
        when neither is available.
        """
        if tmdb_id in self.index:
            i = self.index[tmdb_id]
            scores = self.scores_for(self.X[i])
            exclude = [i]
        elif film:
            scores = self.scores_for(self.vectorize(film))
            exclude = []
        else:
            return []
        return [(j, float(scores[j])) for j in self.top_k(scores, k, exclude)]

    def explain(self, source, target, limit=3):
        """Human-readable reasons two films match (shared director, cast, keywords, genres)."""
        reasons = []
        for name in set(source.get("director", [])) & set(target.get("director", [])):
            reasons.append(f"Dir. {name}")
        for name in [c for c in target.get("cast", []) if c in set(source.get("cast", []))][:1]:
            reasons.append(name)
        shared_kw = set(source.get("keywords", [])) & set(target.get("keywords", []))
        # Rarest shared keywords first: they say more than "based on novel"
        vocab, idf = self.meta_vec.vocabulary_, self.meta_vec.idf_
        shared_kw = sorted(shared_kw, key=lambda k: -idf[vocab[f"k:{_slug(k)}"]]
                           if f"k:{_slug(k)}" in vocab else 0)
        reasons.extend(shared_kw[:2])
        shared_g = [g for g in target.get("genres", []) if g in set(source.get("genres", []))]
        reasons.extend(shared_g[:1])
        return reasons[:limit]


# ── lazy singleton used by the Flask app ──────────────────────────────────
_model = None
_lock  = threading.Lock()


def load_corpus(path=CORPUS_PATH):
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def tuned_text_weight(path=EVAL_PATH):
    """Text weight chosen by evaluate_recommender.py, or the default if not run yet."""
    try:
        with open(path) as fh:
            return float(json.load(fh)["best_text_weight"])
    except (OSError, KeyError, ValueError):
        return DEFAULT_TEXT_WEIGHT


def get_recommender():
    """Return the shared ContentRecommender, or None if the corpus file is missing."""
    global _model
    if _model is None:
        with _lock:
            if _model is None and os.path.exists(CORPUS_PATH):
                _model = ContentRecommender(load_corpus(), tuned_text_weight())
    return _model
