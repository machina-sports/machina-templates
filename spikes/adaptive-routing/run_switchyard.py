#!/usr/bin/env python3
"""Adaptive-routing spike — Option C: NVIDIA NeMo Switchyard libsy, decision-only (offline).

RESEARCH ONLY (ClickUp 86ajz5tdp / RFC 003). Switchyard is pre-alpha upstream:
"Experimental software. Not for production use." (README). This script exists to
measure the DECISION layer in isolation — it must never be wired to a workflow,
template install, or production path.

Integration shape under test — the only one compatible with machina-ai:
libsy algorithms decide the target and hand every model call back to the host.
Here the host clients are fakes (canned neutral responses, zero network, zero
provider spend), so the measured latency isolates Switchyard's decision
overhead through the real Rust algorithm code, and the recorded decisions
({selected_model_id, reasoning, is_answer_call}) are real Switchyard output.

What it measures:
  1. decision latency per call for `random` (no judge) and `llm_task_classifier`
     (fake judge with schema-valid verdicts)
  2. threshold behavior: p_solve above/below base_threshold routes
     efficient/capable
  3. session affinity: second call with the same x-switchyard-session-id skips
     the judge
  4. compat gaps for machina-ai parity (no embeddings; chat-only in this spike)

Requires: pip install nemo-switchyard==0.2.0  (pin: repo commit b256d936f1d7,
observed 2026-08-13). Exits with SKIPPED status when the package is missing.

Usage:
  python3 spikes/adaptive-routing/run_switchyard.py \
      [--iterations 200] [--out spikes/adaptive-routing/results/switchyard.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent

PINNED = {
    "package": "nemo-switchyard",
    "version_expected": "0.2.0",
    "repo": "https://github.com/NVIDIA-NeMo/Switchyard",
    "commit_observed": "b256d936f1d77bf13ec9bec399ea0a253e07ca05",
    "observed_on": "2026-08-13",
    "maturity": "pre-alpha — 'Experimental software. Not for production use.' (upstream README)",
}


def neutral_request(text: str) -> dict:
    return {
        "model": "auto",
        "messages": [{"role": "user", "content": [{"type": "text", "text": text}]}],
    }


def percentile(values, pct):
    ordered = sorted(values)
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def stats_us(timings):
    return {
        "mean": round(statistics.mean(timings), 1),
        "p50": round(percentile(timings, 50), 1),
        "p95": round(percentile(timings, 95), 1),
        "iterations": len(timings),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--out", default=str(SPIKE_DIR / "results" / "switchyard.json"))
    args = parser.parse_args()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        import switchyard  # noqa: F401
        from switchyard.libsy import LlmTarget, TaskClassifierConfig, algorithms
    except ImportError as error:
        report = {
            "option": "C-switchyard-libsy",
            "status": "SKIPPED",
            "reason": f"nemo-switchyard not installed ({error}); pip install nemo-switchyard==0.2.0",
            "pinned": PINNED,
        }
        out_path.write_text(json.dumps(report, indent=2) + "\n")
        print("SKIPPED: nemo-switchyard not installed — no numbers produced.")
        return 0

    installed_version = getattr(switchyard, "__version__", None)

    class FakeModelClient:
        """Host-owned model client: canned neutral response, zero network."""

        def __init__(self, model: str):
            self.model = model
            self.calls = 0

        async def call(self, request):
            self.calls += 1
            return {
                "model": self.model,
                "outputs": [
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": f"answer-from-{self.model}"}],
                        "stop_reason": "end_turn",
                    }
                ],
            }

    class FakeJudgeClient(FakeModelClient):
        """Judge returning a schema-valid capability verdict with a fixed p_solve."""

        def __init__(self, model: str, p_solve: float):
            super().__init__(model)
            self.p_solve = p_solve

        async def call(self, request):
            self.calls += 1
            verdict = json.dumps(
                {
                    "crux": "bounded task",
                    "primary_rule": "SUP-1",
                    "capability_boundary": "supported",
                    "p_solve": self.p_solve,
                }
            )
            return {
                "model": self.model,
                "outputs": [
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": verdict}],
                        "stop_reason": "end_turn",
                    }
                ],
            }

    workloads = [
        json.loads(line)
        for line in (SPIKE_DIR / "workloads.jsonl").read_text().splitlines()
        if line.strip()
    ]
    chat_workloads = [w for w in workloads if w["capability"] == "chat"]
    skipped_workloads = [
        {"workload": w["id"], "capability": w["capability"], "reason": "Switchyard has no embeddings/search surface (no /v1/embeddings; chat protocols only)."}
        for w in workloads
        if w["capability"] != "chat"
    ]

    def workload_text(workload):
        params = workload["params"]
        if "prompt" in params:
            return params["prompt"]
        return params["messages"][0]["content"]

    async def run_random():
        efficient = FakeModelClient("efficient-model")
        capable = FakeModelClient("capable-model")
        algorithm = algorithms.random([LlmTarget("efficient-model", efficient), LlmTarget("capable-model", capable)])
        rows = []
        for workload in chat_workloads:
            request = neutral_request(workload_text(workload))
            timings = []
            decisions = None
            for _ in range(args.iterations):
                started = time.perf_counter()
                decisions, _response = await algorithm.run(request)
                timings.append((time.perf_counter() - started) * 1_000_000)
            rows.append(
                {
                    "workload": workload["id"],
                    "last_decision": decisions[-1] if decisions else None,
                    "decision_overhead_us": stats_us(timings),
                }
            )
        return rows

    async def run_classifier(p_solve: float, label: str):
        judge = FakeJudgeClient("judge-model", p_solve=p_solve)
        efficient = FakeModelClient("efficient-model")
        capable = FakeModelClient("capable-model")
        algorithm = algorithms.llm_task_classifier(
            LlmTarget("judge-model", judge),
            LlmTarget("efficient-model", efficient),
            LlmTarget("capable-model", capable),
            config=TaskClassifierConfig(0.5),
        )
        request = neutral_request(workload_text(chat_workloads[0]))
        timings = []
        decisions = None
        for _ in range(args.iterations):
            started = time.perf_counter()
            decisions, _response = await algorithm.run(request)
            timings.append((time.perf_counter() - started) * 1_000_000)
        return {
            "scenario": label,
            "judge_p_solve": p_solve,
            "base_threshold": 0.5,
            "decisions": decisions,
            "judge_calls": judge.calls,
            "efficient_calls": efficient.calls,
            "capable_calls": capable.calls,
            "decision_overhead_us_with_fake_judge": stats_us(timings),
            "note": "Judge round-trip is faked (~0); with a real judge LLM this adds one full model call of latency+tokens per unlatched turn.",
        }

    async def run_session_affinity():
        judge = FakeJudgeClient("judge-model", p_solve=0.9)
        efficient = FakeModelClient("efficient-model")
        capable = FakeModelClient("capable-model")
        algorithm = algorithms.llm_task_classifier(
            LlmTarget("judge-model", judge),
            LlmTarget("efficient-model", efficient),
            LlmTarget("capable-model", capable),
            config=TaskClassifierConfig(0.5, session_affinity=True),
        )
        headers = {"x-switchyard-session-id": "spike-session-1"}
        request = neutral_request("first turn")
        first_decisions, _ = await algorithm.run(request, headers)
        judge_calls_after_first = judge.calls
        second_decisions, _ = await algorithm.run(neutral_request("second turn"), headers)
        return {
            "first_call_decisions": first_decisions,
            "second_call_decisions": second_decisions,
            "judge_calls_after_first": judge_calls_after_first,
            "judge_calls_after_second": judge.calls,
            "judge_skipped_on_second_call": judge.calls == judge_calls_after_first,
            "note": "Affinity is process-local (in-memory, lifetime of the process) — no external store.",
        }

    async def run_all():
        return {
            "random": await run_random(),
            "classifier_low_confidence": await run_classifier(0.2, "p_solve below threshold -> capable"),
            "classifier_high_confidence": await run_classifier(0.9, "p_solve above threshold -> efficient"),
            "session_affinity": await run_session_affinity(),
        }

    measurements = asyncio.run(run_all())

    report = {
        "option": "C-switchyard-libsy",
        "status": "RAN",
        "mode": "offline-decision-only-fake-host-clients",
        "runnable_without_credentials": True,
        "installed_version": installed_version,
        "pinned": PINNED,
        "measurements": measurements,
        "skipped_workloads": skipped_workloads,
        "caveats": [
            "Model and judge calls are faked; numbers isolate Switchyard decision overhead, not provider latency.",
            "Output quality is NOT measured; classifier/escalation quality requires a real judge LLM and evals.",
            "Known issues 0.2.0 (upstream docs/known_issues.md) remain open, incl. post-disconnect provider spend and incomplete tier attribution in stats.",
            "API drift observed live: the released 0.2.0 wheel emits decision key 'selected_model', while repo HEAD (b256d936, 2 days after the release) already renamed it to 'selected_model_id' — concrete pre-alpha churn.",
        ],
    }
    out_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {out_path}")
    print(
        json.dumps(
            {
                "random_p50_us": [row["decision_overhead_us"]["p50"] for row in measurements["random"]],
                "low_conf_selected": [d.get("selected_model_id") or d.get("selected_model") for d in measurements["classifier_low_confidence"]["decisions"]],
                "high_conf_selected": [d.get("selected_model_id") or d.get("selected_model") for d in measurements["classifier_high_confidence"]["decisions"]],
                "affinity_judge_skipped": measurements["session_affinity"]["judge_skipped_on_second_call"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
