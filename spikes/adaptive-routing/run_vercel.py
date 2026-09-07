#!/usr/bin/env python3
"""Adaptive-routing spike — Option B: Vercel AI Gateway as mechanics layer (live, gated).

RESEARCH ONLY (ClickUp 86ajz5tdp / RFC 003). Not wired to any workflow, template
install, or production path.

This runner is LIVE: with a key set it makes real HTTP calls to the Vercel AI
Gateway and consumes AI Gateway Credits (paid tier) or free-tier quota. Without
AI_GATEWAY_API_KEY in the environment it SKIPS cleanly and produces no numbers —
never fabricate results for this option.

What it measures when run live (same workloads as the other options):
  1. end-to-end latency per call through the gateway (chat + embeddings)
  2. token usage as reported by the gateway
  3. provider actually resolved per call (gateway picks by uptime/latency
     unless `only`/`order`/`sort` are set)
  4. static model-fallback behavior via the `models` array (ordered list —
     the gateway exhausts a model's providers before trying the next model)

What it deliberately does NOT do:
  - no BYOK (the documented BYOK failure path silently falls back to system
    credentials and bills credits; that behavior must be validated in a
    controlled account before any adoption — see RFC 003)
  - no adaptive decision: per Vercel's own guidance, classifier/escalation
    logic is app-owned; the gateway only executes the model string it is given.

Usage:
  AI_GATEWAY_API_KEY=... python3 spikes/adaptive-routing/run_vercel.py \
      [--iterations 1] [--only vertex] \
      [--out spikes/adaptive-routing/results/vercel.json]

Endpoints (docs): https://ai-gateway.vercel.sh/v1/chat/completions and /v1/embeddings.
Model slugs use the `creator/model-name` format (e.g. google/gemini-2.5-flash).
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
BASE_URL = "https://ai-gateway.vercel.sh/v1"

DEFAULT_CHAT_MODEL = "google/gemini-2.5-flash"
DEFAULT_EMBEDDING_MODEL = "google/text-embedding-004"
FALLBACK_CHAIN = ["google/gemini-2.5-flash", "google/gemini-2.5-flash-lite"]


def percentile(values, pct):
    ordered = sorted(values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def call_gateway(path: str, payload: dict, api_key: str, timeout_s: int = 60):
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            body = json.loads(response.read().decode("utf-8"))
            latency_ms = (time.perf_counter() - started) * 1000
            return {"ok": True, "latency_ms": round(latency_ms, 1), "body": body}
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        return {"ok": False, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "status": error.code, "error": detail}
    except Exception as error:  # noqa: BLE001 - spike runner surfaces everything
        return {"ok": False, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "error": str(error)}


def strip_content(body: dict) -> dict:
    """Keep receipts (usage, model, provider metadata), drop generated content."""
    kept = {key: body.get(key) for key in ("model", "usage", "id", "provider", "gateway") if key in body}
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        kept["finish_reason"] = choices[0].get("finish_reason")
    data = body.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict) and "embedding" in data[0]:
        kept["embedding_dimensions"] = len(data[0]["embedding"])
    return kept


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=1, help="repetitions per workload (keep low: live spend)")
    parser.add_argument("--only", default=None, help="restrict provider via providerOptions gateway.only (e.g. vertex)")
    parser.add_argument("--out", default=str(SPIKE_DIR / "results" / "vercel.json"))
    args = parser.parse_args()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    api_key = os.getenv("AI_GATEWAY_API_KEY")
    if not api_key:
        report = {
            "option": "B-vercel-ai-gateway",
            "status": "SKIPPED",
            "reason": "AI_GATEWAY_API_KEY not set — live gateway calls cost credits and must be an explicit operator action.",
            "how_to_run": "Create a gateway API key in the Vercel dashboard (paid tier for full catalog/BYOK) and export AI_GATEWAY_API_KEY.",
        }
        out_path.write_text(json.dumps(report, indent=2) + "\n")
        print("SKIPPED: AI_GATEWAY_API_KEY not set — no numbers produced.")
        return 0

    workloads = [
        json.loads(line)
        for line in (SPIKE_DIR / "workloads.jsonl").read_text().splitlines()
        if line.strip()
    ]

    gateway_options = {}
    if args.only:
        gateway_options = {"gateway": {"only": [args.only]}}

    cases = []
    for workload in workloads:
        capability = workload["capability"]
        params = workload["params"]
        if capability == "chat" or capability == "search_answer":
            messages = params.get("messages") or [{"role": "user", "content": params.get("prompt", "")}]
            payload = {"model": DEFAULT_CHAT_MODEL, "messages": messages, "max_tokens": 256}
            if gateway_options:
                payload["providerOptions"] = gateway_options
            path = "/chat/completions"
        elif capability == "embedding":
            payload = {"model": DEFAULT_EMBEDDING_MODEL, "input": params.get("input", "")}
            path = "/embeddings"
        else:
            cases.append({"workload": workload["id"], "status": "SKIPPED", "reason": f"capability {capability} not exercised in this spike"})
            continue

        timings = []
        last = None
        for _ in range(max(1, args.iterations)):
            last = call_gateway(path, payload, api_key)
            timings.append(last["latency_ms"])
        entry = {
            "workload": workload["id"],
            "endpoint": path,
            "model_requested": payload["model"],
            "ok": last["ok"],
            "latency_ms": {
                "mean": round(statistics.mean(timings), 1),
                "p50": round(percentile(timings, 50), 1),
                "iterations": len(timings),
            },
        }
        if last["ok"]:
            entry["receipt"] = strip_content(last["body"])
        else:
            entry["error"] = {key: last.get(key) for key in ("status", "error")}
        cases.append(entry)

    fallback_payload = {
        "model": FALLBACK_CHAIN[0],
        "models": FALLBACK_CHAIN,
        "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
        "max_tokens": 8,
    }
    fallback_result = call_gateway("/chat/completions", fallback_payload, api_key)
    fallback_case = {
        "scenario": "static-ordered-model-fallback (models array)",
        "chain": FALLBACK_CHAIN,
        "ok": fallback_result["ok"],
        "latency_ms": fallback_result["latency_ms"],
        "receipt": strip_content(fallback_result["body"]) if fallback_result["ok"] else fallback_result.get("error"),
        "note": "Fallback triggers on failure/unavailability only — never on task difficulty or output quality.",
    }

    report = {
        "option": "B-vercel-ai-gateway",
        "status": "RAN",
        "mode": "live-gateway-calls",
        "base_url": BASE_URL,
        "provider_restriction": args.only,
        "cases": cases,
        "fallback_probe": fallback_case,
        "caveats": [
            "Live numbers depend on gateway + provider load at run time; rerun for distributions.",
            "Adaptive routing (difficulty/quality-based) is app-owned per Vercel's own guidance; the gateway executes a static model string / ordered fallback list.",
            "BYOK behavior (failure -> silent system-credential fallback billed to credits) is NOT exercised here and must be validated in a controlled account.",
        ],
    }
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {out_path}")
    print(json.dumps({"cases_ok": [c.get("ok") for c in cases], "fallback_ok": fallback_case["ok"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
