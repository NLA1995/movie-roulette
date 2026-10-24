"""Offline evaluation of the content-based recommender.

Ground truth: TMDB's own /movie/{id}/recommendations list for a random sample
of corpus films, restricted to films that are also in the corpus. TMDB builds
that list from audience behaviour, which makes it an independent (if imperfect)
proxy for "people who liked A also liked B" — our model never sees it.

Protocol
  1. Split the sampled films 50/50 into a tuning set and a test set (seeded).
  2. On the tuning set, grid-search the text weight w_text ∈ {0, .25, .5, .75, 1}
     (0 = metadata only, 1 = overview only).
  3. Report precision@10, recall@10 and hit-rate@10 on the test set for the
     tuned model and for two baselines: random films and most-voted films.
  4. Report catalogue coverage: share of the corpus that appears in at least
     one top-10 list (a recommender that always suggests the same blockbusters
     scores low).

Usage (needs TMDB_API_KEY and data/rec_corpus.json.gz):
    python evaluate_recommender.py            # 400 sampled films
    python evaluate_recommender.py --sample 800

Ground truth is cached in data/rec_ground_truth.json, so re-runs are offline.
Results are written to data/rec_eval.json; the app reads best_text_weight from it.
"""
import argparse
import json
import os
import random
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv()

from build_rec_corpus import get                                   # noqa: E402
from recommender import (ContentRecommender, DATA_DIR, EVAL_PATH,  # noqa: E402
                         load_corpus)

GT_PATH = os.path.join(DATA_DIR, "rec_ground_truth.json")
K       = 10
WEIGHTS = [0.0, 0.25, 0.5, 0.75, 1.0]


def fetch_ground_truth(ids, corpus_ids, workers=8):
    """{tmdb_id: [recommended ids that are in the corpus]} from TMDB, cached on disk."""
    cache = {}
    if os.path.exists(GT_PATH):
        with open(GT_PATH) as fh:
            cache = {int(k): v for k, v in json.load(fh).items()}
    missing = [i for i in ids if i not in cache]

    def one(i):
        data = get(f"/movie/{i}/recommendations", {"page": 1})
        return i, [m["id"] for m in (data or {}).get("results", [])]

    if missing:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for i, recs in ex.map(one, missing):
                cache[i] = recs
        with open(GT_PATH, "w") as fh:
            json.dump(cache, fh)

    return {i: [r for r in cache[i] if r in corpus_ids and r != i] for i in ids}


def metrics(rec_lists, truth):
    """Mean precision@K, recall@K and hit-rate@K over films with ground truth."""
    p = r = h = 0.0
    for i, recs in rec_lists.items():
        rel = set(truth[i])
        hits = len(rel & set(recs[:K]))
        p += hits / K
        r += hits / len(rel)
        h += 1.0 if hits else 0.0
    n = len(rec_lists)
    return {"precision@10": p / n, "recall@10": r / n, "hit_rate@10": h / n}


def model_lists(model, ids):
    return {i: [model.films[j]["id"] for j, _ in model.recommend(i, k=K)] for i in ids}


def main():
    parser = argparse.ArgumentParser(description="Evaluate the content-based recommender")
    parser.add_argument("--sample", type=int, default=400)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    films = load_corpus()
    corpus_ids = {f["id"] for f in films}
    rng = random.Random(args.seed)
    sample = rng.sample(sorted(corpus_ids), min(args.sample, len(films)))

    truth = fetch_ground_truth(sample, corpus_ids)
    usable = [i for i in sample if len(truth[i]) >= 3]   # need some relevant items
    rng.shuffle(usable)
    tune, test = usable[: len(usable) // 2], usable[len(usable) // 2:]
    print(f"{len(usable)} films with ≥3 in-corpus TMDB recommendations "
          f"(tune {len(tune)}, test {len(test)})\n")

    # 1. tune w_text on the tuning half
    tuning = {}
    for w in WEIGHTS:
        m = ContentRecommender(films, text_weight=w)
        tuning[w] = metrics(model_lists(m, tune), truth)["precision@10"]
        print(f"  w_text={w:<4}  tune precision@10 = {tuning[w]:.3f}")
    best_w = max(tuning, key=tuning.get)
    print(f"\nBest w_text on tuning set: {best_w}\n")

    # 2. report on the held-out test half
    model = ContentRecommender(films, text_weight=best_w)
    by_votes = [f["id"] for f in sorted(films, key=lambda f: -f["votes"])]
    all_ids = sorted(corpus_ids)
    rows = {
        f"content-based (w_text={best_w})": model_lists(model, test),
        "random baseline": {i: rng.sample([x for x in all_ids if x != i], K) for i in test},
        "popularity baseline": {i: [x for x in by_votes if x != i][:K] for i in test},
    }
    results = {name: metrics(lists, truth) for name, lists in rows.items()}

    # 3. catalogue coverage over the whole corpus
    seen = set()
    for f in films:
        seen.update(j for j, _ in model.recommend(f["id"], k=K))
    coverage = len(seen) / len(films)

    print(f"{'model':<34}{'P@10':>8}{'R@10':>8}{'HR@10':>8}")
    for name, m in results.items():
        print(f"{name:<34}{m['precision@10']:>8.3f}{m['recall@10']:>8.3f}{m['hit_rate@10']:>8.3f}")
    print(f"\nCatalogue coverage (content-based): {coverage:.1%}")

    with open(EVAL_PATH, "w") as fh:
        json.dump({
            "best_text_weight": best_w,
            "tuning_precision@10": {str(k): v for k, v in tuning.items()},
            "test_metrics": results,
            "catalogue_coverage": coverage,
            "n_tune": len(tune), "n_test": len(test), "corpus_size": len(films),
            "seed": args.seed,
        }, fh, indent=2)
    print(f"Saved to {EVAL_PATH}")


if __name__ == "__main__":
    main()
