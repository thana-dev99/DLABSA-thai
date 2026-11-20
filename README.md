# DLABSA-thai: Thai Dish-Level Sentiment Benchmark

Annotations, model outputs, and code for the paper "Comparing Free and Open Large Language
Models for Dish-Level Aspect-Based Sentiment Analysis on Thai Restaurant Reviews"
(T. Wongabut, W. Krathu, and S. Chinwicha).

## Contents

| Path | Description |
|---|---|
| `data/reviews.csv` | 300 reviews: `review_id`, `platform` (wongnai / google), `has_dish` (Y/N) |
| `data/dish_sentiment.csv` | 526 gold dish-sentiment pairs for the 191 dish-bearing reviews |
| `data/model_predictions.csv` | Parsed outputs of the three models for all 300 reviews |
| `annotation_guideline.md` | The labeling guideline |
| `run_inference.py` | Prompt and API settings used for inference |
| `evaluate.py` | Reproduces Table I from the files above (`python evaluate.py`) |

### `data/dish_sentiment.csv` columns

- `dish`: dish name exactly as written in the review
- `sentiment`: final label used in the paper (POS / NEG / NEU / MIX)
- `sentiment_alt_neu`: label under the alternative signature-menu convention
  (dishes named only in a "เมนูเด็ด" line without a dish-specific comment = NEU)
- `signature_menu_only`: 1 if the dish appears only in a signature-menu summary line
  (the 103 pairs re-annotated in Section 3.3 of the paper), else 0

### `data/model_predictions.csv` columns

`review_id`, `model` (typhoon = typhoon-v2.5-30b-a3b-instruct, gemini = gemini-3.5-flash-lite, groq = openai/gpt-oss-120b via Groq),
`parse_success`, `has_dish`, `dishes_json` (list of {name, sentiment}), `latency_sec`.

## Review texts

Review texts are not redistributed because they come from Wongnai and Google Maps. They are
available from the authors on request for research use, subject to the platforms' terms of
service. `run_inference.py` expects them in `annotation_sample.xlsx` (columns `review_id`,
`source`, `review_text`).

## Reproducing Table I

```
python evaluate.py            # primary labels
python evaluate.py --alt-neu  # alternative signature-menu convention (Section 5.2)
```

Only the Python standard library is needed.

## License

Annotations, guideline, and model outputs: CC BY 4.0 (`LICENSE-DATA.md`). Code: MIT (`LICENSE`).

## Citation

T. Wongabut and S. Chinwicha, "Comparing Free and Open Large Language Models for Dish-Level
Aspect-Based Sentiment Analysis on Thai Restaurant Reviews."
