"""Offline tests for connectors/gemini-cv — the Gemini CV route of the Automated Highlights Agent.

No network: the model transport is injected. The tests pin the fail-closed contract
(schema violations, unknown candidates, refusals, unavailable modes → degraded + PBP fallback).
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONNECTOR = ROOT / "connectors" / "gemini-cv" / "gemini-cv.py"


def load_connector():
    spec = importlib.util.spec_from_file_location("gemini_cv", CONNECTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def cv():
    return load_connector()


def manifest():
    windows = [
        ("act-001-goal-1", "Goal! 1-0", "goal", 100, 20, 12, 32),
        ("act-002-goal-kick", "Goal kick", "other", 20, 30, 22, 42),
        ("act-003-shot-saved", "Shot on target, saved", "shot", 80, 45, 37, 57),
        ("act-004-var-disallowed", "Goal disallowed by VAR", "var", 70, 60, 52, 72),
        ("act-005-goal-2", "Goal! 2-0", "goal", 100, 70, 62, 82),
    ]
    return {
        "version": 1,
        "state": "succeeded",
        "event": {"provider": "synthetic-cues", "sport": "soccer", "eventId": "synthetic-match-cues"},
        "rights": {"rightsHolder": "Machina Sports (synthetic)", "licenseRef": "synthetic-fixture", "clearedForClipping": True},
        "source": {"kind": "local-file", "path": "/data/media/synthetic.mp4", "ffprobe": {"durationSec": 90.0, "formatName": "mov,mp4"}},
        "syncAnchor": {"videoSec": 5, "clockSec": 0},
        "window": {"preRollSec": 8, "postRollSec": 12, "maxCandidates": 5},
        "windows": [
            {"actionId": a, "provider": "synthetic-cues", "provenance": f"synthetic-cues#{a}", "label": l, "type": t,
             "period": 1, "importance": imp, "actionVideoSec": av, "startSec": s, "endSec": e}
            for a, l, t, imp, av, s, e in windows
        ],
        "clips": [],
    }


def oracle_output():
    def entry(cid, start, end, rel, hype, safe, verdict, text):
        return {"candidate_id": cid, "refined_start_sec": start, "refined_end_sec": end, "relevance": rel, "hype": hype,
                "editorial_safety": safe, "confidence": 0.95, "verdict": verdict, "description": text}
    return {
        "candidates": [
            entry("act-001-goal-1", 18, 25, 95, 90, 95, "keep", "Opening goal."),
            entry("act-002-goal-kick", 28, 35, 15, 10, 20, "reject", "Routine goal kick."),
            entry("act-003-shot-saved", 43, 50, 75, 70, 90, "keep", "Shot saved."),
            entry("act-004-var-disallowed", 58, 65, 30, 40, 15, "reject", "Disallowed goal."),
            entry("act-005-goal-2", 68, 75, 95, 92, 95, "keep", "Second goal."),
        ],
        "discovered_moments": [{"approx_sec": 80, "label": "Replay of earlier action", "confidence": 0.9}],
    }


def transport_returning(payload, usage=None):
    def run(config, secrets, context, prompt):
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        return raw, usage or {"total_tokens": 1234}, {"latency_ms": 42, "finish_reason": "STOP"}
    return run


def request(video="gs://bucket/synthetic.mp4", **overrides):
    params = {"provider": "vertex_ai", "project_id": "demo", "credential": "{}", "manifest": manifest(), "video": video}
    params.update(overrides)
    return {"params": params, "headers": {}}


def test_oracle_output_ranks_keep_first_and_is_not_degraded(cv):
    result = cv.rank_highlight_candidates(request(), transport=transport_returning(oracle_output()))
    data = result["data"]
    assert result["status"] is True and data["degraded"] is False and data["fallback_mode"] == "none"
    assert [e["candidate_id"] for e in data["ranking"]] == [
        "act-005-goal-2", "act-001-goal-1", "act-003-shot-saved", "act-004-var-disallowed", "act-002-goal-kick"]
    assert [e["rank"] for e in data["ranking"]] == [1, 2, 3, 4, 5]
    assert all(e["source"] == "gemini-cv" for e in data["ranking"])
    assert data["ranking"][3]["editorial_safety"] == 15 and data["ranking"][3]["verdict"] == "reject"
    assert data["discovered_moments"][0]["label"].startswith("Replay")
    assert data["usage"] == {"total_tokens": 1234} and data["latency_ms"] == 42
    assert data["route"] == "gemini-cv/rank_highlight_candidates" and data["provider"] == "vertex_ai"
    assert "credential" not in json.dumps(data) and "api_key" not in json.dumps(data)


def test_unknown_candidate_id_fails_closed_to_pbp_importance(cv):
    payload = oracle_output()
    payload["candidates"].append({**payload["candidates"][0], "candidate_id": "act-999-invented"})
    result = cv.rank_highlight_candidates(request(), transport=transport_returning(payload))
    data = result["data"]
    assert data["degraded"] is True and data["fallback_mode"] == "pbp-importance"
    assert any("unknown candidate_id 'act-999-invented'" in r for r in data["degraded_reasons"])
    # deterministic baseline: importance desc, then timeline
    assert [e["candidate_id"] for e in data["ranking"]] == [
        "act-001-goal-1", "act-005-goal-2", "act-003-shot-saved", "act-004-var-disallowed", "act-002-goal-kick"]
    assert all(e["verdict"] == "hold" and e["source"] == "pbp-importance" and e["relevance"] is None for e in data["ranking"])


@pytest.mark.parametrize("mutate, expected", [
    (lambda p: p["candidates"].pop(), "candidates missing from output"),
    (lambda p: p["candidates"][0].__setitem__("relevance", 140), "relevance out of range"),
    (lambda p: p["candidates"][0].__setitem__("verdict", "air"), "verdict invalid"),
    (lambda p: p["candidates"][0].__setitem__("refined_start_sec", 0.5), "drifts more than 10s"),
    (lambda p: p["candidates"][0].__setitem__("refined_end_sec", 1), "refined window invalid"),
    (lambda p: p.pop("discovered_moments"), "discovered_moments[] missing"),
])
def test_schema_violations_degrade(cv, mutate, expected):
    payload = oracle_output()
    mutate(payload)
    data = cv.rank_highlight_candidates(request(), transport=transport_returning(payload))["data"]
    assert data["degraded"] is True and data["fallback_mode"] == "pbp-importance"
    assert any(expected in reason for reason in data["degraded_reasons"]), data["degraded_reasons"]


def test_non_json_output_degrades_and_keeps_an_excerpt(cv):
    data = cv.rank_highlight_candidates(request(), transport=transport_returning('{"candidates": [{"cand'))["data"]
    assert data["degraded"] is True
    assert data["degraded_reasons"][0].startswith("schema-violation: model output is not JSON")
    assert data["raw_output_excerpt"].startswith('{"candidates"')


def test_model_refusal_is_degraded_not_silently_ranked(cv):
    payload = oracle_output()
    for entry in payload["candidates"]:
        entry["verdict"] = "hold"
    payload["refusal"] = "The video is synthetic test graphics."
    data = cv.rank_highlight_candidates(request(), transport=transport_returning(payload))["data"]
    assert data["degraded"] is True and data["refusal"] == "The video is synthetic test graphics."
    assert data["degraded_reasons"] == ["model-refusal: The video is synthetic test graphics."]
    assert data["fallback_mode"] == "pbp-importance"


def test_provider_error_degrades_with_reason(cv):
    def failing(config, secrets, context, prompt):
        raise TimeoutError("deadline exceeded")
    data = cv.rank_highlight_candidates(request(), transport=failing)["data"]
    assert data["degraded"] is True and data["degraded_reasons"] == ["provider-error: TimeoutError: deadline exceeded"]
    assert len(data["ranking"]) == 5


def test_agentic_on_vertex_is_unavailable_and_never_substitutes_static(cv):
    result = cv.rank_highlight_candidates(request(processing="agentic"))
    data = result["data"]
    assert data["processing"] == "agentic" and data["degraded"] is True
    assert data["degraded_reasons"][0].startswith("agentic-unavailable")
    assert "static was NOT substituted" in data["degraded_reasons"][0]


def test_rights_not_cleared_is_refused_before_any_model_call(cv):
    bad = manifest()
    bad["rights"]["clearedForClipping"] = False
    called = []
    def spy(*args):
        called.append(True)
        return json.dumps(oracle_output()), {}, {}
    result = cv.rank_highlight_candidates(request(manifest=bad), transport=spy)
    assert result["status"] is False and result["error"]["code"] == 400
    assert "refused" in result["error"]["message"] and called == []


def test_invalid_inputs_are_400(cv):
    assert cv.rank_highlight_candidates({"params": {"video": "gs://x/y.mp4"}})["error"]["code"] == 400
    assert cv.rank_highlight_candidates(request(provider="openai"))["error"]["code"] == 400
    assert cv.rank_highlight_candidates(request(processing="turbo"))["error"]["code"] == 400
    assert cv.rank_highlight_candidates(request(video=None))["error"]["code"] == 400


def test_explicit_candidates_without_manifest(cv):
    params = {
        "provider": "ai_studio", "api_key": "k", "video": "gs://bucket/v.mp4",
        "sync_anchor": {"video_sec": 5, "clock_sec": 0}, "duration_sec": 90,
        "candidates": [
            {"candidate_id": "c1", "label": "Goal", "type": "goal", "importance": 100, "action_video_sec": 20, "window_start_sec": 12, "window_end_sec": 32},
            {"candidate_id": "c2", "label": "Goal kick", "type": "other", "importance": 20, "action_video_sec": 30, "window_start_sec": 22, "window_end_sec": 42},
        ],
    }
    payload = {"candidates": [
        {"candidate_id": "c1", "refined_start_sec": 18, "refined_end_sec": 25, "relevance": 90, "hype": 80, "editorial_safety": 90, "confidence": 0.9, "verdict": "keep", "description": "Goal."},
        {"candidate_id": "c2", "refined_start_sec": 28, "refined_end_sec": 35, "relevance": 10, "hype": 10, "editorial_safety": 20, "confidence": 0.9, "verdict": "reject", "description": "Restart."},
    ], "discovered_moments": []}
    data = cv.rank_highlight_candidates({"params": params}, transport=transport_returning(payload))["data"]
    assert data["degraded"] is False and [e["candidate_id"] for e in data["ranking"]] == ["c1", "c2"]
    assert "Sync anchor: video second 5.0 equals match clock 0.0s." in cv.build_prompt(cv.build_context(params))


def test_route_capabilities_is_offline_and_gates_agentic(cv):
    data = cv.route_capabilities({})["data"]
    assert data["route"] == "gemini-cv/rank_highlight_candidates"
    assert data["agentic_available"]["ai_studio"] is True
    assert data["agentic_available"]["vertex_ai"] in (True, False)
    assert set(data["processing"]) == {"static", "agentic"}


def test_request_hash_ignores_video_bytes_but_pins_prompt_and_candidates(cv):
    context = cv.build_context(request()["params"])
    a = cv._config({**request()["params"]}, context)["request_sha256"]
    b = cv._config({**request()["params"], "video": "gs://other/video.mp4"}, context)["request_sha256"]
    c = cv._config({**request()["params"], "thinking_level": "high"}, context)["request_sha256"]
    assert a == b and a != c
