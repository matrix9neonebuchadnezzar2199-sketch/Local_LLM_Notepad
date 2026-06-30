"""Headless smoke test: load Gemma 4 E2B and run one Japanese prompt."""
from __future__ import annotations

import os
import sys
import time

import psutil

# Notepad package imports
sys.path.insert(0, os.path.dirname(__file__))
from llm_utils import DEFAULT_MODEL_FILENAME, respond

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", DEFAULT_MODEL_FILENAME)


def main() -> int:
    if not os.path.isfile(MODEL_PATH):
        print(f"FAIL: model not found: {MODEL_PATH}")
        return 1

    proc = psutil.Process(os.getpid())
    rss_before_mb = proc.memory_info().rss / (1024 * 1024)
    print(f"RSS before load: {rss_before_mb:.0f} MB")

    prompt = "日本について簡潔に解説してください。"
    print(f"Prompt: {prompt}")

    t0 = time.perf_counter()
    last = ""
    try:
        for chunk in respond(prompt, [], model=MODEL_PATH, max_tokens=256):
            last = chunk
    except Exception as exc:
        print(f"FAIL: inference error: {exc}")
        return 2

    elapsed = time.perf_counter() - t0
    rss_after_mb = proc.memory_info().rss / (1024 * 1024)
    print(f"RSS after inference: {rss_after_mb:.0f} MB")
    print(f"Elapsed: {elapsed:.1f}s")
    print("--- response ---")
    print(last[:800] if last else "(empty)")

    if not last or last.startswith("[Error]"):
        print("FAIL: empty or error response")
        return 3

    if rss_after_mb > 3500:
        print(f"WARN: RSS {rss_after_mb:.0f} MB exceeds ~3 GB target")

    print("OK: model loaded and responded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
