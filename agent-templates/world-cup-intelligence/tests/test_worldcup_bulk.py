"""Bulk World Cup finalization, closure, and fixture-pack tests."""

from __future__ import annotations

import asyncio
import argparse
import copy
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from test_worldcup_archive_serving import (
    CONNECTOR,
    ENDPOINTS,
    EVENT,
    EVENT_URN,
    PLAYER,
    PLAYER_URN,
    _document,
    _operator_manifest,
    _request,
    execute_yaml,
)


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def _load_bulk():
    spec = importlib.util.spec_from_file_location("worldcup_bulk_test_tool", ROOT / "tools" / "worldcup_bulk.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


BULK = _load_bulk()


def _closure_document(*, valid=True):
    urns = [EVENT_URN] + [f"urn:event:synthetic:{index}" for index in range(103)]
    coverage = {
        urn: {
            "worldcup-get-event-context": "partial",
            "worldcup-get-squads": "partial",
            "worldcup-get-injuries": "unavailable",
            "worldcup-get-player-performance-context": "unavailable",
            "worldcup-get-match-forecast": "historical_model",
            "worldcup-match-recap": "evergreen_editorial",
        }
        for urn in urns
    }
    row = CONNECTOR.build_final_archive_manifest({"params": {
        "fixture_urns": urns,
        "fixture_coverage": coverage,
        "grounded_recap_fixture_urns": urns,
        "fixture_player_urns": {urn: [] for urn in urns},
        "spotlight_targets": [PLAYER_URN],
        "archive_document_ids": ["archive:1"],
        "expected_archive_count": 1,
        "forecast_baseline_sha256": "a" * 64,
        "forecast_readback_sha256": "a" * 64,
        "closed_at": "2026-09-13T00:00:00Z",
    }})
    if not valid:
        row["value"]["fixture_urns"][0] = "tampered"
    return row


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_closed_catalog_misses_are_explicit_and_never_run_legacy_tasks(endpoint):
    outputs, store, connectors = execute_yaml(endpoint, _request(endpoint), [_closure_document()])
    assert outputs["archive"]["status"] == "unavailable"
    assert outputs["workflow-status"] == "skipped"
    assert store.writes == 0
    assert connectors.external_calls == []
    assert connectors.internal_calls[-1] == "serve_final_archive"


@pytest.mark.parametrize("query", [{"league": "39", "season": "2026"}, {"league": "1", "season": "2022"}])
def test_worldcup_closure_preserves_other_league_or_season_standings(query):
    _, _, connectors = execute_yaml("worldcup-get-standings", query, [_closure_document()])
    assert "api-football" in connectors.external_calls


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_closed_catalog_hits_keep_all_eleven_workflows_read_only(endpoint):
    outputs, store, connectors = execute_yaml(endpoint, _request(endpoint), [_closure_document(), _document(endpoint)])
    assert outputs["archive"]["status"] == "hit"
    assert outputs["workflow-status"] == "executed"
    assert store.writes == 0
    assert connectors.external_calls == []


def test_fixture_workflows_scope_archive_lookup_after_canonical_resolution():
    for endpoint in CONNECTOR.FINAL_ARCHIVE_FIXTURE_ENDPOINTS:
        workflow = yaml.safe_load((ROOT / "workflows" / f"{endpoint}.yml").read_text(encoding="utf-8"))["workflow"]
        names = [task["name"] for task in workflow["tasks"]]
        assert names.index("resolve-final-archive-scope") < names.index("load-final-archive")
        archive_load = next(task for task in workflow["tasks"] if task["name"] == "load-final-archive")
        assert archive_load["filters"]["value.subject.event_urn"] == "$.get('archive_resolved_event_urn', '')"
        assert archive_load["config"]["search-limit"] == 10


def test_invalid_closure_fails_closed_and_non_world_cup_backtest_stays_legacy():
    result = CONNECTOR.serve_final_archive({"params": {
        "endpoint": "worldcup-get-schedule", "request": {}, "documents": [],
        "archive_manifest": [_closure_document(valid=False)],
    }})["data"]
    assert result["archive_status"] == "error"

    _, _, connectors = execute_yaml(
        "worldcup-backtest-forecasts",
        {"competition": "brasileirao-2026", "league": "71", "season": "2026"},
        [_closure_document()],
    )
    assert "api-football" in connectors.external_calls


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_invalid_closure_state_blocks_all_eleven_workflows(endpoint):
    outputs, store, connectors = execute_yaml(endpoint, _request(endpoint), [_closure_document(valid=False)])
    assert outputs["archive"]["status"] == "error"
    assert outputs["workflow-status"] == "skipped"
    assert store.writes == 0
    assert connectors.external_calls == []


@pytest.mark.parametrize("status", ["FT", "AET", "PEN"])
def test_grounded_recap_uses_only_final_event_and_original_forecast(status):
    event = copy.deepcopy(EVENT)
    event["sport:status"] = status
    built = CONNECTOR.build_grounded_match_recap({"params": {
        "event": event,
        "forecast": {"most_likely_score": "1-1", "probabilities": {"home_win": 0.4, "draw": 0.35, "away_win": 0.25}},
        "generated_at": "2026-09-13T00:00:00Z",
    }})["data"]
    assert built["validation"]["valid"] is True
    assert built["body"]["grounding"]["unsupported_claims_included"] is False
    assert built["body"]["turning_points"] == []
    assert status in built["body"]["what_it_means"]
    if status == "FT":
        assert built["body"]["forecast_scorecard"]["regulation_outcome_status"] == "available"
    else:
        assert "result_details" not in built["body"]
        assert built["body"]["forecast_scorecard"]["regulation_outcome_status"] == "unavailable"
        assert built["body"]["forecast_scorecard"]["hit"] is None


def test_recap_validation_rejects_wrong_score_opponents_and_unscoped_claims():
    built = CONNECTOR.build_grounded_match_recap({"params": {
        "event": EVENT, "forecast": {}, "generated_at": "2026-09-13T00:00:00Z",
    }})["data"]["body"]
    built["final_score"] = "Brazil 9-0 Argentina"
    built["grounding"]["claims_scope"] = "news_and_result"
    result = CONNECTOR.validate_grounded_match_recap({"params": {"event": EVENT, "recap": built}})["data"]
    assert result["valid"] is False
    assert {"final_score", "claims_scope"} <= set(result["failures"])


def test_raw_fixture_stats_become_one_pack_and_select_one_public_player():
    raw = {"response": [{"team": {"id": 6, "name": "Brazil"}, "players": [{
        "player": {"id": 77, "name": "Archive Player"},
        "statistics": [{"games": {"minutes": 90, "position": "M", "rating": "7.2"}, "goals": {"total": 1, "assists": 0}}],
    }, {
        "player": {"id": 88, "name": "Second Player"},
        "statistics": [{"games": {"minutes": 20, "position": "D", "rating": "6.0"}}],
    }]}]}
    identity = copy.deepcopy(PLAYER)
    identity["aliases"] = ["Exact Alias"]
    pack = CONNECTOR.build_fixture_player_pack({"params": {
        "event": EVENT, "player_stats": raw, "identities": [identity], "rankings": [],
    }})["data"]["fixture_player_pack"]
    assert pack["raw_player_count"] == 2
    assert pack["player_count"] == 2

    response = {
        "fixture_player_pack": pack,
        "status": "complete",
        "warnings": [],
        "archive": {
            "mode": "final_archive", "competition": "FIFA World Cup 2026", "competition_status": "completed",
            "live": False, "snapshot_as_of": "2026-09-13T00:00:00Z", "capability_status": "complete",
            "provenance": ["api-football"], "missing_capabilities": [], "notes": [],
        },
    }
    row = {"name": CONNECTOR.FINAL_ARCHIVE_DOCUMENT, "value": CONNECTOR.build_final_archive_document(
        "worldcup-get-player-performance-context",
        {"key": EVENT_URN, "event_urn": EVENT_URN, "event": EVENT}, {}, response,
        [{"document_name": "api-football", "source_sha256": "a" * 64}],
    )}
    result = CONNECTOR.serve_final_archive({"params": {
        "endpoint": "worldcup-get-player-performance-context", "documents": [row],
        "canonical_events": [{"value": EVENT}], "canonical_identities": [{"value": identity}],
        "archive_manifest": [_closure_document()],
        "request": {"event_urn": EVENT_URN, "player": "Exact Alias", "team": "Brazil", "team_id": "6"},
    }})["data"]
    assert result["archive_status"] == "hit"
    assert result["response"]["player_performance_context"]["player"]["player_id"] == "77"
    assert "players" not in result["response"]["fixture_player_pack"]


def test_real_operator_player_shape_builds_pack_offline():
    execution = _read(REPO / ".local" / "worldcup-bulk" / "captures" / "1539000" / "worldcup-archive-capture-players.json")
    stats = execution["workflow_output"]["outputs"]["player_stats"]
    assert set(stats) == {"errors", "get", "paging", "parameters", "response", "results"}
    event = next(
        row["value"] for row in _read(REPO / ".local" / "worldcup-bulk" / "baseline" / "worldcup-event.json")
        if row["value"]["provider_ids"]["api_football"] == "1539000"
    )
    identities = [row["value"] for row in _read(REPO / ".local" / "worldcup-bulk" / "baseline" / "worldcup-identity-crosswalk.json")]
    rankings = _read(REPO / ".local" / "worldcup-bulk" / "baseline" / "worldcup-final-fifa-player-power-ranking.json")
    pack = CONNECTOR.build_fixture_player_pack({"params": {
        "event": event, "player_stats": stats, "identities": identities, "rankings": rankings,
    }})["data"]["fixture_player_pack"]
    assert pack["fixture_id"] == "1539000"
    assert pack["event_urn"] == event["_id"]
    assert pack["raw_player_count"] > 0
    assert pack["player_count"] == pack["raw_player_count"]


def _load_real_result_evidence():
    baseline = REPO / ".local" / "worldcup-bulk" / "baseline"
    sources = BULK.load_bulk_sources(
        REPO / ".local" / "worldcup-bulk" / "match-checklist.json",
        baseline,
    )
    evidence = BULK.load_result_details(
        REPO / ".local" / "worldcup-bulk" / "provider-results-compact.json",
        sources["events"],
    )
    return evidence, sources


def test_real_result_details_cover_all_four_shootouts_and_aet_regulation_scoring():
    evidence, sources = _load_real_result_evidence()
    events = {str((event.get("provider_ids") or {}).get("api_football")): event for event in sources["events"]}
    forecasts = {
        str((row["value"].get("provider_ids") or {}).get("api_football")): row["value"]
        for row in sources["collections"]["worldcup:model-forecast"]["rows"]
    }
    penalty_ids = {fixture_id for fixture_id, detail in evidence["details_by_id"].items() if detail["status"] == "PEN"}
    assert penalty_ids == {"1565176", "1562345", "1565178", "1576805"}
    for fixture_id in penalty_ids:
        detail = evidence["details_by_id"][fixture_id]
        built = CONNECTOR.build_grounded_match_recap({"params": {
            "event": events[fixture_id],
            "forecast": forecasts[fixture_id],
            "result_details": detail,
            "generated_at": "2026-09-13T00:00:00Z",
        }})["data"]["body"]
        winner = detail["winner"]["name"]
        shootout = detail["shootout_score"]
        winner_score = shootout[detail["winner"]["qualifier"]]
        loser_score = shootout["away" if detail["winner"]["qualifier"] == "home" else "home"]
        assert winner in built["headline"] and winner in built["summary"]
        assert f"{winner_score}-{loser_score}" in built["headline"]
        assert built["shootout_score"]
        assert built["winner"] == detail["winner"]
        assert "Draw" == built["forecast_scorecard"]["actual_outcome"]
        assert built["forecast_scorecard"]["regulation_outcome_status"] == "available"

    aet_id = "1567308"
    aet = CONNECTOR.build_grounded_match_recap({"params": {
        "event": events[aet_id],
        "forecast": forecasts[aet_id],
        "result_details": evidence["details_by_id"][aet_id],
        "generated_at": "2026-09-13T00:00:00Z",
    }})["data"]["body"]
    assert aet["final_score"] == "Belgium 3-2 Senegal"
    assert aet["forecast_scorecard"]["actual_outcome"] == "Draw"
    assert aet["forecast_scorecard"]["regulation_outcome_status"] == "available"
    assert evidence["details_by_id"][aet_id]["regulation_time_score"] == {"home": 2, "away": 2}
    assert evidence["details_by_id"][aet_id]["extra_time_score_contribution"] == {"home": 1, "away": 0}


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda capture: capture["workflow_output"]["outputs"]["fixture_results"]["response"][0]["goals"].__setitem__("home", 99), "goals mismatch"),
        (lambda capture: capture["workflow_output"]["outputs"]["fixture_results"]["response"][0]["fixture"].__setitem__("id", 999999), "IDs/count"),
        (lambda capture: capture["workflow_output"]["outputs"]["fixture_results"]["response"][0]["fixture"]["status"].__setitem__("short", "AET"), "status mismatch"),
        (lambda capture: capture["workflow_output"]["outputs"]["fixture_results"].__setitem__("results", 103), "count mismatch"),
        (lambda capture: capture["workflow_output"]["outputs"]["fixture_results"].pop("paging"), "truncated"),
        (lambda capture: capture["workflow_output"]["outputs"]["fixture_results"]["paging"].__setitem__("total", 2), "pagination"),
        (lambda capture: capture["workflow_output"]["outputs"]["fixture_results"]["response"][0]["teams"]["home"].__setitem__("id", 999999), "team identity"),
    ],
)
def test_result_details_reject_disagreement_and_truncation(tmp_path, mutation, message):
    evidence_path = REPO / ".local" / "worldcup-bulk" / "provider-results-compact.json"
    capture = copy.deepcopy(_read(evidence_path))
    mutation(capture)
    mutated = tmp_path / "result-details.json"
    mutated.write_text(json.dumps(capture), encoding="utf-8")
    _, sources = _load_real_result_evidence()
    with pytest.raises(BULK.ARCHIVE.ArchivePreparationError, match=message):
        BULK.load_result_details(mutated, sources["events"])


def test_capture_plan_is_exactly_five_existing_workflows_for_all_104():
    sources = BULK.load_bulk_sources(
        REPO / ".local" / "worldcup-bulk" / "match-checklist.json",
        REPO / ".local" / "worldcup-bulk" / "baseline",
    )
    plan = BULK.build_capture_plan(sources, REPO / ".local" / "worldcup-bulk" / "captures")
    assert plan["item_count"] == 520
    assert {item["workflow"] for item in plan["items"]} == set(BULK.CAPTURE_WORKFLOWS)
    player = next(item for item in plan["items"] if item["workflow"] == "worldcup-archive-capture-players")
    forecast = next(item for item in plan["items"] if item["workflow"] == "worldcup-get-match-forecast")
    assert player["request"] == {"provider_event_id": player["fixture_id"]}
    assert forecast["request"]["include_reasoning"] is False
    assert all("capture_all_players" not in item["request"] for item in plan["items"])


def test_operator_player_capture_definition_is_installed_verbatim():
    expected = _read(REPO / ".local" / "worldcup-bulk" / "capture-players.workflow.json")
    actual = yaml.safe_load((ROOT / "workflows" / "worldcup-archive-capture-players.yml").read_text(encoding="utf-8"))["workflow"]
    assert actual == expected
    installer = yaml.safe_load((ROOT / "_install.yml").read_text(encoding="utf-8"))
    assert {item.get("path") for item in installer["datasets"]} >= {"workflows/worldcup-archive-capture-players.yml"}


def test_real_baseline_assembles_all_104_with_exact_forecasts_and_grounded_recaps():
    baseline = REPO / ".local" / "worldcup-bulk" / "baseline"
    checklist = REPO / ".local" / "worldcup-bulk" / "match-checklist.json"
    executions = REPO / ".local" / "worldcup-archive" / "executions"
    manifest = BULK.assemble_bulk_manifest(
        checklist, baseline, REPO / ".local" / "worldcup-bulk" / "captures", executions,
        generated_at="2026-09-13T00:00:00Z",
        result_details_path=REPO / ".local" / "worldcup-bulk" / "provider-results-compact.json",
    )
    assert len(manifest["fixture_urns"]) == 104
    assert set(manifest["grounded_recap_fixture_urns"]) == set(manifest["fixture_urns"])
    assert set(manifest["fixture_coverage"]) == set(manifest["fixture_urns"])
    assert all(set(states) == CONNECTOR.FINAL_ARCHIVE_FIXTURE_ENDPOINTS for states in manifest["fixture_coverage"].values())
    assert len(manifest["legacy_recap_audit"]) == 13
    assert manifest["result_details_count"] == 104
    assert manifest["recap_modes"] == {
        "captured_pilot": 1,
        "deterministic_source_only": 90,
        "legacy_original_copy": 13,
    }
    assert all("raw_source_sha256" in row and "failures" in row for row in manifest["legacy_recap_audit"])
    recap_entries = [entry for entry in manifest["entries"] if entry["endpoint"] == "worldcup-match-recap"]
    assert len(recap_entries) == 104
    assert all(row["factually_valid"] for row in manifest["legacy_recap_audit"])
    assert all(row["format"] == "legacy_original_copy" for row in manifest["legacy_recap_audit"])
    reused = [entry for entry in recap_entries if entry["response"]["skill_card"]["historical_perspective"] == "original_cached_matchday_copy"]
    deterministic = [entry for entry in recap_entries if entry["response"]["skill_card"].get("generation_method") == "deterministic_source_only"]
    pilots = [entry for entry in recap_entries if any(source["document_name"] == "capture:worldcup-match-recap" for source in entry["source_manifest"])]
    assert len(reused) == 13
    assert len(deterministic) == 90
    assert len(pilots) == 1
    schedule = next(entry for entry in manifest["entries"] if entry["endpoint"] == "worldcup-get-schedule")
    assert len([row for row in schedule["response"]["schedule"]["events"] if row.get("result_details")]) == 104
    contexts = [entry for entry in manifest["entries"] if entry["endpoint"] == "worldcup-get-event-context"]
    assert len([entry for entry in contexts if entry["response"]["event_context"].get("result_details")]) == 104
    penalty_recaps = [entry for entry in recap_entries if entry["subject"]["event"]["sport:status"] == "PEN"]
    assert len(penalty_recaps) == 4
    assert all(entry["response"]["skill_card"].get("winner") for entry in penalty_recaps)
    assert all(entry["response"]["skill_card"].get("shootout_score") for entry in penalty_recaps)
    for entry in recap_entries:
        status = entry["subject"]["event"]["sport:status"]
        if status in {"AET", "PEN"}:
            assert entry["response"]["skill_card"]["forecast_scorecard"]["regulation_outcome_status"] == "available"
    original = {_value(row)["_id"]: _value(row) for row in _read(baseline / "worldcup-model-forecast.json")}
    archived = {entry["subject"]["key"]: entry["response"]["forecast"] for entry in manifest["entries"] if entry["endpoint"] == "worldcup-get-match-forecast"}
    assert archived == original
    captured_forecast = _read(REPO / ".local" / "worldcup-bulk" / "captures" / "1539000" / "worldcup-get-match-forecast.json")["workflow_output"]["outputs"]
    archived_forecast = next(entry["response"] for entry in manifest["entries"] if entry["endpoint"] == "worldcup-get-match-forecast" and entry["subject"]["provider_event_id"] == "1539000")
    assert archived_forecast == {key: value for key, value in captured_forecast.items() if key != "workflow-status"}

    documents = BULK.ARCHIVE.prepare_manifest(manifest)
    readback = {
        "documents": documents,
        "count": len(documents),
        "unique_identity_count": len(documents),
        "total_count": len(documents),
        "offset": 0,
    }
    forecast_export = baseline / "worldcup-model-forecast.json"
    closure = BULK.prepare_closure(manifest, readback, forecast_export, closed_at="2026-09-13T00:00:00Z")
    assert CONNECTOR.validate_final_archive_manifest(closure["documents"])[0] == "closed"
    changed_export = copy.deepcopy(_read(forecast_export))
    changed_export[0]["value"]["confidence"] = -1
    with pytest.raises(BULK.ARCHIVE.ArchivePreparationError, match="differs from the assembly baseline"):
        BULK.prepare_closure(manifest, readback, changed_export, closed_at="2026-09-13T00:00:00Z")


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _value(row):
    return row["value"]


def test_closure_rejects_errors_missing_recaps_and_forecast_drift():
    row = _closure_document()["value"]
    coverage = copy.deepcopy(row["fixture_coverage"])
    fixture_urns = row["fixture_urns"]
    common = {
        "fixture_urns": fixture_urns, "fixture_coverage": coverage,
        "grounded_recap_fixture_urns": fixture_urns, "fixture_player_urns": {urn: [] for urn in fixture_urns},
        "archive_document_ids": ["one"], "expected_archive_count": 1,
        "forecast_baseline_sha256": "a", "forecast_readback_sha256": "a", "closed_at": "2026-09-13T00:00:00Z",
    }
    broken = copy.deepcopy(common)
    broken["fixture_coverage"][fixture_urns[0]]["worldcup-get-injuries"] = "error"
    with pytest.raises(ValueError, match="error state"):
        CONNECTOR.build_final_archive_manifest({"params": broken})
    broken = {**common, "grounded_recap_fixture_urns": fixture_urns[:-1]}
    with pytest.raises(ValueError, match="grounded recap"):
        CONNECTOR.build_final_archive_manifest({"params": broken})
    broken = {**common, "forecast_readback_sha256": "b"}
    with pytest.raises(ValueError, match="forecast baseline changed"):
        CONNECTOR.build_final_archive_manifest({"params": broken})
    broken = {**common, "fixture_urns": fixture_urns[:-1] + [fixture_urns[0]]}
    with pytest.raises(ValueError, match="104 unique"):
        CONNECTOR.build_final_archive_manifest({"params": broken})

    closure_bundle = {"documents": [_closure_document()]}
    assert BULK.verify_import_bundle(closure_bundle) == {"verified": True, "count": 1, "kind": "closure"}


def test_capture_journal_polls_existing_run_before_dispatch_and_never_redispatches(tmp_path):
    class FakeOperator:
        def __init__(self):
            self.dispatched = []
            self.polled = []

        async def execute_workflow(self, name, request):
            self.dispatched.append((name, request))
            return "new-run"

        async def get_execution(self, run_id):
            self.polled.append(run_id)
            return {"_id": run_id, "name": "workflow", "status": "running", "workflow_output": {"outputs": {}}}

    output = tmp_path / "capture.json"
    journal_path = tmp_path / "journal.json"
    journal_path.write_text(json.dumps({"schema_version": 1, "items": {"one": {"status": "dispatched", "workflow_run_id": "existing-run", "attempts": 1}}}))
    plan = {"items": [{"key": "one", "workflow": "workflow", "request": {}, "output": str(output)}]}
    operator = FakeOperator()
    asyncio.run(BULK.capture_with_operator(operator, plan, journal_path))
    assert operator.polled == ["existing-run"]
    assert operator.dispatched == []
    assert json.loads(journal_path.read_text())["items"]["one"]["status"] == "dispatched"


def test_mcp_execution_contract_and_failed_envelopes_are_exact():
    class Result:
        def __init__(self, wire):
            self.wire = wire

        def model_dump(self, by_alias=False):
            assert by_alias is True
            return self.wire

    execution = {"_id": "run-1", "name": "workflow", "status": "executed", "date": "now", "workflow_output": {}, "request_data": {}, "tasks": []}

    class Session:
        def __init__(self):
            self.calls = []

        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            return Result({"content": [{"type": "text", "text": json.dumps({"status": "success", "data": {"data": execution}})}], "isError": False})

    session = Session()
    assert asyncio.run(BULK.McpOperator(session).get_execution("run-1")) == execution
    assert session.calls == [("get_workflow_execution", {
        "workflow_id": "run-1",
        "compact": False,
        "fields": ["_id", "name", "status", "date", "workflow_output", "request_data", "tasks"],
    })]
    assert BULK._sse_headers("token") == {"X-Api-Token": "token"}
    assert "Authorization" not in BULK._sse_headers("token")
    with pytest.raises(BULK.ARCHIVE.ArchivePreparationError, match="isError"):
        BULK._decode_tool_result(Result({"isError": True, "content": []}))
    with pytest.raises(BULK.ARCHIVE.ArchivePreparationError, match="failed envelope"):
        BULK._decode_tool_result(Result({"isError": False, "content": [{"type": "text", "text": json.dumps({"status": "failed", "error": "nope"})}]}))


def test_replay_plan_uses_manifest_subjects_for_all_eleven_workflows(tmp_path):
    plan = BULK.build_replay_plan(_operator_manifest(), tmp_path)
    assert {item["workflow"] for item in plan["items"]} == set(ENDPOINTS)
    fixture_request = next(item["request"] for item in plan["items"] if item["workflow"] == "worldcup-get-event-context")
    resolve_request = next(item["request"] for item in plan["items"] if item["workflow"] == "worldcup-resolve")
    assert fixture_request == {"event_urn": EVENT_URN}
    assert resolve_request == {"id": "urn:machina:sport:soccer:team:brazil:bra"}
    assert next(item["request"] for item in plan["items"] if item["workflow"] == "worldcup-get-schedule") == {"limit": 500}
    assert all(len(item["expected_response_sha256"]) == 64 for item in plan["items"])


def test_replay_requires_hit_pure_trace_and_explicit_zero_tokens(tmp_path):
    item = {
        "key": "replay:test",
        "workflow": "worldcup-get-schedule",
        "expected_response": {"schedule": {"events": [], "count": 0}},
    }
    execution = {
        "name": item["workflow"],
        "status": "executed",
        "workflow_output": {
            "audit": {"execution_tokens": {"total_tokens": 0}},
            "outputs": {
                "schedule": {"events": [], "count": 0},
                "archive": {"status": "hit", "version": CONNECTOR.FINAL_ARCHIVE_VERSION},
                "workflow-status": "executed",
            },
        },
        "tasks": [
            {"name": "load", "type": "document", "status": "task-executed", "task_context": {"config": {"action": "search"}}},
            {"name": "serve", "type": "connector", "status": "task-executed", "task_context": {"connector": {"name": "worldcup-market-intelligence"}}},
            {"name": "legacy", "type": "connector", "status": "task-skipped", "task_context": {"connector": {"name": "api-football"}}},
        ],
    }
    BULK._validate_replay_execution(item, execution)
    transported_item = copy.deepcopy(item)
    transported_item["expected_response"]["archive"] = {
        "version": "world-cup-2026-final-v1", "status": "hit",
        "response_sha256": "original-capture-hash", "capability_status": "complete",
    }
    transported_item["expected_response_sha256"] = "a" * 64
    transported = copy.deepcopy(execution)
    transported["workflow_output"]["outputs"]["archive"].update({"response_sha256": "a" * 64, "capability_status": "complete"})
    BULK._validate_replay_execution(transported_item, transported)
    transported["workflow_output"]["outputs"]["archive"]["response_sha256"] = "b" * 64
    with pytest.raises(BULK.ARCHIVE.ArchivePreparationError, match="snapshot hash mismatch"):
        BULK._validate_replay_execution(transported_item, transported)
    transported["workflow_output"]["outputs"]["archive"].update({"response_sha256": "a" * 64, "capability_status": "partial"})
    with pytest.raises(BULK.ARCHIVE.ArchivePreparationError, match="archive metadata mismatch"):
        BULK._validate_replay_execution(transported_item, transported)
    missing_tokens = copy.deepcopy(execution)
    missing_tokens["workflow_output"]["audit"]["execution_tokens"] = {}
    with pytest.raises(BULK.ARCHIVE.ArchivePreparationError, match="zero token"):
        BULK._validate_replay_execution(item, missing_tokens)
    impure = copy.deepcopy(execution)
    impure["tasks"][1]["task_context"]["connector"]["name"] = "api-football"
    with pytest.raises(BULK.ARCHIVE.ArchivePreparationError, match="non-pure"):
        BULK._validate_replay_execution(item, impure)


def test_capture_enforces_two_active_runs_and_uncertain_dispatches(tmp_path):
    class Operator:
        async def get_execution(self, run_id):
            return {"_id": run_id, "name": "workflow", "status": "running", "workflow_output": {"outputs": {}}}

        async def execute_workflow(self, name, request):
            raise AssertionError("active runs must prevent dispatch")

    items = [
        {"key": str(index), "workflow": "workflow", "request": {}, "output": str(tmp_path / f"{index}.json")}
        for index in range(3)
    ]
    journal = tmp_path / "journal.json"
    journal.write_text(json.dumps({"schema_version": 1, "items": {
        str(index): {"status": "dispatched", "workflow_run_id": f"run-{index}", "attempts": 1}
        for index in range(3)
    }}))
    with pytest.raises(BULK.ARCHIVE.ArchivePreparationError, match="maximum is 2"):
        asyncio.run(BULK.capture_with_operator(Operator(), {"items": items}, journal, batch_size=3))

    journal.write_text(json.dumps({"schema_version": 1, "items": {
        "0": {"status": "dispatched", "workflow_run_id": "run-0", "attempts": 1},
        "1": {"status": "dispatched", "workflow_run_id": "run-1", "attempts": 1},
    }}))
    result = asyncio.run(BULK.capture_with_operator(Operator(), {"items": items}, journal, batch_size=3))
    assert result["dispatched"] == 0

    journal.write_text(json.dumps({"schema_version": 1, "items": {"0": {"status": "dispatching", "attempts": 1}}}))
    with pytest.raises(BULK.ARCHIVE.ArchivePreparationError, match="uncertain dispatch"):
        asyncio.run(BULK.capture_with_operator(Operator(), {"items": items}, journal))


def test_import_reads_exact_id_before_and_after_write_then_journals(tmp_path, monkeypatch):
    row = _document("worldcup-get-schedule")
    bundle = {"documents": [row]}
    journal = tmp_path / "import-journal.json"

    class FakeOperator:
        def __init__(self):
            self.searches = 0
            self.created = []

        async def search_documents_exact(self, filters, page_size=100):
            self.searches += 1
            assert filters == {"name": row["name"], "value._id": row["value"]["_id"]}
            return [] if self.searches == 1 else [row]

        async def create_document(self, document):
            self.created.append(document)

    class Context:
        async def __aexit__(self, *args):
            return None

    operator = FakeOperator()

    async def open_operator(url, token):
        return operator, Context(), Context()

    monkeypatch.setenv("TEST_WC_URL", "https://example.invalid/mcp")
    monkeypatch.setenv("TEST_WC_TOKEN", "secret")
    monkeypatch.setattr(BULK, "_open_operator", open_operator)
    args = argparse.Namespace(url_env="TEST_WC_URL", token_env="TEST_WC_TOKEN", journal=journal)
    result = asyncio.run(BULK._import_apply(args, bundle))
    assert result == {"imported": 1, "already_imported": 0}
    assert operator.created == [row]
    assert operator.searches == 2
    assert json.loads(journal.read_text())["imported_document_ids"] == [row["value"]["_id"]]


def test_import_rereads_journaled_rows_and_rejects_exact_value_mismatch(tmp_path, monkeypatch):
    row = _document("worldcup-get-schedule")
    journal = tmp_path / "import-journal.json"
    journal.write_text(json.dumps({"schema_version": 1, "imported_document_ids": [row["value"]["_id"]]}))
    mismatched = copy.deepcopy(row)
    mismatched["value"]["response"]["warnings"] = ["changed"]

    class FakeOperator:
        async def search_documents_exact(self, filters, page_size=100):
            return [mismatched]

        async def create_document(self, document):
            raise AssertionError("journaled rows must be read, not recreated")

    class Context:
        async def __aexit__(self, *args):
            return None

    async def open_operator(url, token):
        return FakeOperator(), Context(), Context()

    monkeypatch.setenv("TEST_WC_URL", "https://example.invalid/mcp")
    monkeypatch.setenv("TEST_WC_TOKEN", "secret")
    monkeypatch.setattr(BULK, "_open_operator", open_operator)
    args = argparse.Namespace(url_env="TEST_WC_URL", token_env="TEST_WC_TOKEN", journal=journal)
    with pytest.raises(BULK.ARCHIVE.ArchivePreparationError, match="exact import readback mismatch"):
        asyncio.run(BULK._import_apply(args, {"documents": [row]}))
