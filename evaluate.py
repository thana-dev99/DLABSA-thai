"""
Reproduces Table I of the paper from the released files only (no review text needed).

    python evaluate.py                 # primary labels (signature-menu items = POS)
    python evaluate.py --alt-neu       # alternative convention (uncommented items = NEU)

Dish matching: a predicted dish matches a gold dish if their lowercased, stripped names are
substrings of one another or have Levenshtein ratio >= 0.7; one-to-one greedy assignment
within each review, highest similarity first. Sentiment is scored on matched pairs only.
"""
import argparse
import csv
import json
import os
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
CLASSES = ["POS", "NEG", "NEU", "MIX"]
MODELS = ["typhoon", "gemini", "groq"]
SIM_THRESHOLD = 0.7


def levenshtein_ratio(a, b):
    if not a or not b:
        return 0.0
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    return 1 - prev[-1] / max(len(a), len(b))


def similarity(p, g):
    p, g = p.strip().lower(), g.strip().lower()
    if not p or not g:
        return 0.0
    if p in g or g in p:
        return 1.0
    r = levenshtein_ratio(p, g)
    return r if r >= SIM_THRESHOLD else 0.0


def match(gold, pred):
    cands = sorted(((similarity(pn, gn), pi, gi) for pi, (pn, _) in enumerate(pred)
                    for gi, (gn, _) in enumerate(gold)), reverse=True)
    used_p, used_g, pairs = set(), set(), []
    for s, pi, gi in cands:
        if s == 0.0 or pi in used_p or gi in used_g:
            continue
        used_p.add(pi)
        used_g.add(gi)
        pairs.append((gold[gi][1], pred[pi][1]))
    return pairs, len(pred) - len(used_p), len(gold) - len(used_g)


def macro_f1(pairs):
    f1s = []
    for c in CLASSES:
        support = sum(g == c for g, _ in pairs)
        if not support:
            continue
        tp = sum(g == c and p == c for g, p in pairs)
        fp = sum(g != c and p == c for g, p in pairs)
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / support
        f1s.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    return sum(f1s) / len(f1s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--alt-neu", action="store_true",
                    help="use the alternative signature-menu convention (uncommented -> NEU)")
    args = ap.parse_args()
    col = "sentiment_alt_neu" if args.alt_neu else "sentiment"

    reviews = {}
    with open(os.path.join(HERE, "data", "reviews.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            reviews[r["review_id"]] = []
    with open(os.path.join(HERE, "data", "dish_sentiment.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            reviews[r["review_id"]].append((r["dish"], r[col]))

    preds = defaultdict(dict)
    with open(os.path.join(HERE, "data", "model_predictions.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dishes = json.loads(r["dishes_json"]) if r["parse_success"] == "True" else []
            preds[r["model"]][r["review_id"]] = [
                (d.get("name", ""), str(d.get("sentiment", "")).upper()) for d in dishes if d.get("name")]

    gold_all = [s for g in reviews.values() for _, s in g]
    maj = [(g, "POS") for g in gold_all]
    print(f"labels: {col}  gold pairs: {len(gold_all)}")
    print(f"{'model':8s} {'dish_P':>7s} {'dish_R':>7s} {'dish_F1':>8s} {'acc':>6s} {'macroF1':>8s}")
    for m in MODELS:
        tp = fp = fn = 0
        pairs = []
        for rid, gold in reviews.items():
            ps, f_p, f_n = match(gold, preds[m].get(rid, []))
            tp, fp, fn = tp + len(ps), fp + f_p, fn + f_n
            pairs += [(g, p) for g, p in ps if g in CLASSES and p in CLASSES]
        P, R = tp / (tp + fp), tp / (tp + fn)
        acc = sum(g == p for g, p in pairs) / len(pairs)
        print(f"{m:8s} {P:7.3f} {R:7.3f} {2 * P * R / (P + R):8.3f} {acc:6.3f} {macro_f1(pairs):8.3f}")
    print(f"{'majority':8s} {'':>7s} {'':>7s} {'':>8s} "
          f"{sum(g == 'POS' for g in gold_all) / len(gold_all):6.3f} {macro_f1(maj):8.3f}")


if __name__ == "__main__":
    main()
