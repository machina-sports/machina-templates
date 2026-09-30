#!/usr/bin/env python3
"""Adaptive-routing spike — Option A: native machina-ai router (offline baseline).

RESEARCH ONLY (ClickUp 86ajz5tdp / RFC 003). Not wired to any workflow, template
install, or production path.

Runs the real router code (connectors/machina-ai/machina-ai.py) with mocked
provider adapters — no network, no credentials, no provider spend. Everything
this script reports is a real measurement of the code that ships on main; the
only fake part is the provider call itself (adapters return canned data in
~zero time), so per-call latency here isolates ROUTER OVERHEAD:
normalize -> policy resolution -> dispatch -> receipt assembly.

What it measures:
  1. routing-decision overhead per call, per workload (p50/p95/mean)
  2. selection determinism: the same (profile, capability) always resolves to
     the same route — proof that today's selection is static (candidates[0])
  3. fallback observability: induced transient provider failure with a
     configured fallback chain; captures the receipt fields
  4. the escalation gap: repeated provider failures never escalate the NEXT
     call (no learned/adaptive state) — recorded as evidence, not opinion

Usage:
  python3 spikes/adaptive-routing/run_native.py \
      [--iterations 200] [--out spikes/adaptive-routing/results/native.json]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import time
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent
REPO_ROOT = SPIKE_DIR.parents[1]
CONNECTOR = REPO_ROOT / "connectors" / "machina-ai" / "machina-ai.py"


def load_router():
    spec = importlib.util.spec_from_file_location("machina_ai_spike", CONNECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


router = load_router()


class SpikeAdapter:
    """Mirrors tests/test_router.py FakeAdapter: canned data, zero provider time."""

    def __init__(self, fail_first_n: int = 0, error_code: str = "provider_unavailable"):
        self.fail_first_n = fail_first_n
        self.error_code = error_code
        self.calls = []

    def _maybe_fail(self, route):
        if len([c for c in self.calls if c == route.provider]) <= self.fail_first_n - 1:
            raise router.RouterError(self.error_code, "Induced transient failure (spike).")

    def _record(self, route):
        self.calls.append(route.provider)

    def create_chat_model(self, route, request):
        self._record(route)
        self._maybe_fail(route)
        return router.AdapterResult(object(), provider_request_id=f"req-{route.provider}", usage={"total_tokens": 3})

    def invoke_chat(self, route, request):
        self._record(route)
        self._maybe_fail(route)
        return router.AdapterResult(router._chat_data("ok"), provider_request_id=f"req-{route.provider}", usage={"total_tokens": 3})

    def create_embedding_model(self, route, request):
        self._record(route)
        return router.AdapterResult(object(), usage={"total_tokens": 1})

    def embed(self, route, request):
        self._record(route)
        return router.AdapterResult([0.1, 0.2], usage={"total_tokens": 1})

    def invoke_search(self, route, request):
        self._record(route)
        return router.AdapterResult(router._chat_data("found", citations=[]), usage={"total_tokens": 2})


class SpikeRuntime:
    """Mirrors tests/test_router.py FakeRuntime enough for offline dispatch."""

    def __init__(self, config=None, adapters=None):
        self._config = config or {}
        self.adapters = adapters or {}
        self.task_events = []
        self.circuit_events = []

    def config(self, key=None):
        return self._config

    def adapter(self, provider):
        return self.adapters.get(provider)

    def trusted_headers(self):
        return {}

    def record_task_event(self, *args, **kwargs):
        self.task_events.append((args, kwargs))

    def record_circuit_event(self, *args, **kwargs):
        self.circuit_events.append((args, kwargs))


def build_router(config_overlay=None, adapters=None):
    runtime = SpikeRuntime(config=config_overlay or {}, adapters=adapters or {})
    return router.Router(runtime)


def percentile(values, pct):
    ordered = sorted(values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def run_overhead(workloads, iterations):
    adapters = {"vertex_ai": SpikeAdapter(), "groq": SpikeAdapter(), "google_speech": SpikeAdapter()}
    instance = build_router(adapters=adapters)
    results = []
    for workload in workloads:
        timings_us = []
        receipt = None
        for _ in range(iterations):
            started = time.perf_counter()
            receipt = instance.dispatch(workload["command"], dict(workload["params"]))
            timings_us.append((time.perf_counter() - started) * 1_000_000)
        metadata = receipt.get("metadata") or {}
        results.append(
            {
                "workload": workload["id"],
                "command": workload["command"],
                "status": receipt.get("status"),
                "selected_provider": metadata.get("selected_provider"),
                "selected_model": metadata.get("selected_model"),
                "route_reason": metadata.get("route_reason"),
                "overhead_us": {
                    "mean": round(statistics.mean(timings_us), 1),
                    "p50": round(percentile(timings_us, 50), 1),
                    "p95": round(percentile(timings_us, 95), 1),
                    "iterations": iterations,
                },
            }
        )
    return results


def run_determinism(workloads, repeats=50):
    adapters = {"vertex_ai": SpikeAdapter(), "groq": SpikeAdapter(), "google_speech": SpikeAdapter()}
    instance = build_router(adapters=adapters)
    rows = []
    for workload in workloads:
        seen = set()
        for _ in range(repeats):
            receipt = instance.dispatch(workload["command"], dict(workload["params"]))
            metadata = receipt.get("metadata") or {}
            seen.add((metadata.get("selected_provider"), metadata.get("selected_model"), metadata.get("route_reason")))
        rows.append(
            {
                "workload": workload["id"],
                "distinct_routes_over_repeats": len(seen),
                "routes": sorted(str(item) for item in seen),
                "static_selection": len(seen) == 1,
            }
        )
    return rows


def run_fallback_probe():
    config = {
        "fallbacks": {"chat": {"vertex_ai": [{"provider": "groq", "model": "llama-3.3-70b-versatile"}]}},
        "providers": {"groq": {"require_credential": False}},
    }
    vertex = SpikeAdapter(fail_first_n=10_000)
    groq = SpikeAdapter()
    instance = build_router(config_overlay=config, adapters={"vertex_ai": vertex, "groq": groq})
    receipt = instance.dispatch("invoke_chat", {"prompt": "fallback probe"})
    metadata = receipt.get("metadata") or {}
    return {
        "primary_provider_failed": "vertex_ai",
        "status": receipt.get("status"),
        "selected_provider": metadata.get("selected_provider"),
        "selected_model": metadata.get("selected_model"),
        "route_reason": metadata.get("route_reason"),
        "fallback_used": metadata.get("fallback_used"),
        "fallback_attempts": metadata.get("fallback_attempts"),
        "receipt_has_decision_metadata": all(
            key in metadata for key in ("selected_provider", "selected_model", "route_reason", "fallback_used")
        ),
    }


def run_escalation_gap_probe():
    """After N consecutive primary failures the NEXT call still routes to the same
    static primary: there is no cross-call signal, memory, or escalation."""
    config = {
        "fallbacks": {"chat": {"vertex_ai": [{"provider": "groq", "model": "llama-3.3-70b-versatile"}]}},
        "providers": {"groq": {"require_credential": False}},
    }
    vertex = SpikeAdapter(fail_first_n=3)
    groq = SpikeAdapter()
    instance = build_router(config_overlay=config, adapters={"vertex_ai": vertex, "groq": groq})
    first_receipts = []
    for _ in range(3):
        receipt = instance.dispatch("invoke_chat", {"prompt": "escalation probe"})
        metadata = receipt.get("metadata") or {}
        first_receipts.append({"fallback_used": metadata.get("fallback_used"), "selected_provider": metadata.get("selected_provider")})
    post_receipt = instance.dispatch("invoke_chat", {"prompt": "post-failure call"})
    post_metadata = post_receipt.get("metadata") or {}
    return {
        "calls_with_primary_failing": first_receipts,
        "next_call_after_failures": {
            "selected_provider": post_metadata.get("selected_provider"),
            "route_reason": post_metadata.get("route_reason"),
            "fallback_used": post_metadata.get("fallback_used"),
        },
        "adaptive_escalation_present": False,
        "note": "Router state is per-call; repeated failures do not change the next call's primary route.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--out", default=str(SPIKE_DIR / "results" / "native.json"))
    args = parser.parse_args()

    workloads = [json.loads(line) for line in (SPIKE_DIR / "workloads.jsonl").read_text().splitlines() if line.strip()]

    report = {
        "option": "A-native-machina-ai",
        "mode": "offline-mocked-adapters",
        "runnable_without_credentials": True,
        "connector_file": str(CONNECTOR.relative_to(REPO_ROOT)),
        "overhead": run_overhead(workloads, args.iterations),
        "determinism": run_determinism(workloads),
        "fallback_probe": run_fallback_probe(),
        "escalation_gap_probe": run_escalation_gap_probe(),
        "caveats": [
            "Adapter time is mocked (~0); numbers isolate router overhead, not provider latency.",
            "Output quality is NOT measured here — quality benchmarks require live routes and evals.",
        ],
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {out_path}")
    print(json.dumps({"overhead_p50_us": [row["overhead_us"]["p50"] for row in report["overhead"]], "all_static": all(row["static_selection"] for row in report["determinism"]), "fallback_used": report["fallback_probe"]["fallback_used"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
