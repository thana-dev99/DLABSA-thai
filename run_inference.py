"""
Runs the shared zero-shot dish-level sentiment extraction prompt (Methodology Section 4.2)
against one of the three compared LLMs over all 300 labeled reviews (has_dish=Y and N both
-- the N rows are hallucination negative controls, see Section 4.4).

Usage:
    set TYPHOON_API_KEY=...    (or GEMINI_API_KEY= / GROQ_API_KEY=)
    py run_inference.py --model typhoon
    py run_inference.py --model gemini
    py run_inference.py --model groq

Resumable: re-running the same --model skips review_ids already present in its output
CSV, so an interrupted run (e.g. Groq's daily cap) can continue tomorrow without re-billing
already-completed reviews against the quota.

Output: results/<model>_results.csv, one row per review, columns:
    review_id, source, model, has_dish, dishes_json, raw_response,
    parse_success, attempts, latency_sec, error, timestamp
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import openpyxl
import requests

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
ANNOTATION_XLSX = os.path.join(PROJECT_DIR, "annotation_sample.xlsx")
RESULTS_DIR = os.path.join(PROJECT_DIR, "results")

SYSTEM_PROMPT = """You are a precise information-extraction assistant for Thai-language restaurant reviews. You will be given one review. Follow these rules exactly.

TASK: Determine whether the review names at least one specific menu item (a dish). Generic words like "food" or "dessert" with no named item do NOT count as a dish. Drinks do NOT count.

If no specific dish is named, output: {"has_dish": false, "dishes": []}

If one or more specific dishes are named, output has_dish: true and a "dishes" array. For each dish include:
- "name": the dish name exactly as written in the review (do not translate, correct spelling, or normalize it).
- "sentiment": one of "POS", "NEG", "NEU", "MIX", judged ONLY about that specific dish's taste, texture, freshness, portion, or temperature -- ignore any opinion about service, price, waiting time, or atmosphere expressed elsewhere in the same review.

Sentiment rules:
- POS: a clear positive opinion about that dish.
- NEG: a clear negative opinion about that dish.
- NEU: the dish is mentioned/ordered but no clear opinion is stated, OR the only description is a hedge word such as งั้นๆ, กลางๆ, พอใช้, ธรรมดา, ปกติ, เฉยๆ, โอเค, OR a bare taste-attribute word (เผ็ด, หวาน, เค็ม, เปรี้ยว, มัน, etc.) with no evaluative qualifier.
- MIX: both a positive and a negative point are made about the same dish.

Output ONLY a single JSON object with exactly this shape -- no other text, no markdown code fences, no explanation:
{"has_dish": true, "dishes": [{"name": "...", "sentiment": "POS"}]}"""

MODELS = {
    "typhoon": {
        "api_key_env": "TYPHOON_API_KEY",
        "endpoint": "https://api.opentyphoon.ai/v1/chat/completions",
        "model_id": "typhoon-v2.5-30b-a3b-instruct",
        "kind": "openai_compatible",
        "rpm": 200,
        "daily_cap": None,
    },
    "gemini": {
        "api_key_env": "GEMINI_API_KEY",
        "endpoint": "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        "model_id": "gemini-3.5-flash-lite",
        "kind": "gemini",
        "rpm": 15,
        "daily_cap": 500,
    },
    "groq": {
        # llama-3.3-70b-versatile was deprecated/removed by Groq (confirmed via live
        # 404 test 2026-08-30) -- replaced with openai/gpt-oss-120b (open-weight,
        # general-purpose, still a large model). Also a reasoning model by default;
        # reasoning_effort=low minimizes (does not fully disable) internal reasoning,
        # same disclosed-limitation treatment as Gemini's thinkingLevel.
        "api_key_env": "GROQ_API_KEY",
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "model_id": "openai/gpt-oss-120b",
        "kind": "openai_compatible",
        "extra_body": {"reasoning_effort": "low"},
        "rpm": 30,
        "daily_cap": 1000,
    },
}

MAX_JSON_RETRIES = 3
MAX_RATE_LIMIT_RETRIES = 6


def load_reviews():
    wb = openpyxl.load_workbook(ANNOTATION_XLSX, data_only=True)
    ws = wb.active
    headers = [c.value for c in ws[1]]
    idx = {h: i for i, h in enumerate(headers)}
    reviews = []
    for row in ws.iter_rows(min_row=2, max_row=301, values_only=True):
        reviews.append({
            "review_id": row[idx["review_id"]],
            "source": row[idx["source"]],
            "review_text": row[idx["review_text"]],
        })
    return reviews


def load_done_ids(out_path):
    """Only counts a review as done if it actually succeeded -- rows left over from a
    failed run (parse_success == False, e.g. a wrong model ID) must be retried, not
    silently skipped."""
    if not os.path.exists(out_path):
        return set()
    with open(out_path, encoding="utf-8-sig") as f:
        return {row["review_id"] for row in csv.DictReader(f)
                if row.get("parse_success") == "True"}


def extract_json(text):
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        text = m.group(1)
    else:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            text = m.group(0)
    obj = json.loads(text)
    if "has_dish" not in obj or "dishes" not in obj:
        raise ValueError("missing required keys")
    return obj


def call_openai_compatible(cfg, api_key, review_text):
    body = {
        "model": cfg["model_id"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Review:\n{review_text}"},
        ],
        "temperature": 0,
    }
    body.update(cfg.get("extra_body", {}))
    resp = requests.post(
        cfg["endpoint"],
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    if resp.status_code == 429:
        return None, resp
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"], resp


def call_gemini(cfg, api_key, review_text):
    url = cfg["endpoint"].format(model=cfg["model_id"]) + f"?key={api_key}"
    resp = requests.post(
        url,
        headers={"Content-Type": "application/json"},
        json={
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": f"Review:\n{review_text}"}]}],
            "generationConfig": {
                "temperature": 0,
                # Gemini 3 Flash cannot fully disable internal reasoning (no
                # thinkingBudget: 0 support) -- "low" minimizes it to keep this as close
                # to the other two models' plain zero-shot calls as the API allows.
                # Disclosed as a limitation in Methodology 4.2.
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        },
        timeout=60,
    )
    if resp.status_code == 429:
        return None, resp
    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        block_reason = (data.get("promptFeedback") or {}).get("blockReason")
        raise ValueError(f"no candidates in response (blockReason={block_reason}): {json.dumps(data)[:300]}")
    parts = candidates[0].get("content", {}).get("parts") or []
    text_parts = [p["text"] for p in parts if "text" in p]
    if not text_parts:
        finish_reason = candidates[0].get("finishReason")
        raise ValueError(f"no text in candidate parts (finishReason={finish_reason}): {json.dumps(data)[:300]}")
    return "".join(text_parts), resp


def call_model(model_name, cfg, api_key, review_text):
    if cfg["kind"] == "gemini":
        return call_gemini(cfg, api_key, review_text)
    return call_openai_compatible(cfg, api_key, review_text)


def run(model_name):
    cfg = MODELS[model_name]
    api_key = os.environ.get(cfg["api_key_env"])
    if not api_key:
        sys.exit(f"Set {cfg['api_key_env']} in your environment first.")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, f"{model_name}_results.csv")
    done_ids = load_done_ids(out_path)
    reviews = load_reviews()
    todo = [r for r in reviews if r["review_id"] not in done_ids]
    print(f"[{model_name}] {len(done_ids)} already done, {len(todo)} remaining.")

    if cfg["daily_cap"] and len(todo) > cfg["daily_cap"]:
        print(f"[{model_name}] WARNING: {len(todo)} remaining exceeds the "
              f"{cfg['daily_cap']}/day free-tier cap -- this run will stop partway "
              f"and need to be resumed (re-run the same command) on a later day.")

    min_interval = 60.0 / cfg["rpm"]
    is_new_file = not os.path.exists(out_path)
    with open(out_path, "a", newline="", encoding="utf-8-sig") as f:
        fieldnames = ["review_id", "source", "model", "has_dish", "dishes_json",
                      "raw_response", "parse_success", "attempts", "latency_sec",
                      "error", "timestamp"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if is_new_file:
            writer.writeheader()

        calls_today = 0
        for review in todo:
            if cfg["daily_cap"] and calls_today >= cfg["daily_cap"]:
                print(f"[{model_name}] Hit daily cap ({cfg['daily_cap']}) for this run. "
                      f"Resume by re-running this command later.")
                break

            t0 = time.time()
            parsed = None
            raw_text = ""
            error = ""
            attempts = 0
            rate_limit_wait = 1.0

            while attempts < MAX_JSON_RETRIES and parsed is None:
                attempts += 1
                rl_attempts = 0
                while True:
                    try:
                        raw_text, resp = call_model(model_name, cfg, api_key, review["review_text"])
                    except (requests.RequestException, ValueError) as e:
                        error = f"request_error: {e}"
                        raw_text = None
                        break
                    if raw_text is None:  # 429
                        rl_attempts += 1
                        if rl_attempts > MAX_RATE_LIMIT_RETRIES:
                            error = "rate_limited: exceeded retry budget"
                            break
                        retry_after = float(resp.headers.get("Retry-After", rate_limit_wait))
                        print(f"[{model_name}] {review['review_id']}: rate limited, "
                              f"waiting {retry_after:.0f}s (attempt {rl_attempts})")
                        time.sleep(retry_after)
                        rate_limit_wait = min(rate_limit_wait * 2, 60)
                        continue
                    break

                if raw_text:
                    try:
                        parsed = extract_json(raw_text)
                        error = ""
                    except (json.JSONDecodeError, ValueError) as e:
                        error = f"parse_error: {e}"
                        parsed = None
                        time.sleep(2 ** attempts)

            latency = time.time() - t0
            calls_today += 1

            writer.writerow({
                "review_id": review["review_id"],
                "source": review["source"],
                "model": model_name,
                "has_dish": parsed.get("has_dish") if parsed else "",
                "dishes_json": json.dumps(parsed.get("dishes", []), ensure_ascii=False) if parsed else "",
                "raw_response": raw_text,
                "parse_success": parsed is not None,
                "attempts": attempts,
                "latency_sec": round(latency, 3),
                "error": error,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            f.flush()

            elapsed = time.time() - t0
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)

    print(f"[{model_name}] Done this run. Output: {out_path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=list(MODELS.keys()))
    args = ap.parse_args()
    run(args.model)
