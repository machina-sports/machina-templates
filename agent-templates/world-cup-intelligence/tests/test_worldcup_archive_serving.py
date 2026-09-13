"""Executable archive-first workflow and operator-tool tests."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONNECTOR = _load_module("worldcup_archive_serving_connector", ROOT / "worldcup-market-intelligence.py")
TOOL = _load_module("worldcup_archive_tool", ROOT / "tools" / "worldcup_archive.py")

ENDPOINTS = (
    "worldcup-resolve",
    "worldcup-get-schedule",
    "worldcup-get-event-context",
    "worldcup-get-standings",
    "worldcup-get-squads",
    "worldcup-get-injuries",
    "worldcup-get-player-performance-context",
    "worldcup-get-match-forecast",
    "worldcup-backtest-forecasts",
    "worldcup-match-recap",
    "worldcup-player-spotlight",
)
LEGACY_TASKS = {
    "worldcup-resolve": ["resolve-entity"],
    "worldcup-get-schedule": ["load-events", "normalize-schedule"],
    "worldcup-get-event-context": ["resolve-load-events", "resolve-fixture", "fetch-event-summary", "worldcup-iptc-event-to-api-response"],
    "worldcup-get-standings": ["lookup-event", "fetch-standings-af", "fetch-standings-ss", "normalize-standings"],
    "worldcup-get-squads": ["resolve-load-events", "resolve-fixture", "load-team-identities", "load-tournament-players", "normalize-squads"],
    "worldcup-get-injuries": ["resolve-load-events", "resolve-fixture", "lookup-teams", "fetch-injuries-af", "normalize-injuries"],
    "worldcup-get-player-performance-context": ["resolve-load-events", "resolve-fixture", "resolve-load-players", "resolve-player", "fetch-player-stats-af", "normalize-player-match-stats", "score-provisional-performance", "load-player-identity", "load-final-fifa-player-rankings", "select-official-fifa-player-ranking", "merge-player-performance-context"],
    "worldcup-get-match-forecast": ["resolve-load-events", "resolve-fixture", "load-forecast", "load-event-markets", "classify-archive-evidence", "compute-gap", "worldcup-match-forecast-explain"],
    "worldcup-backtest-forecasts": ["resolve-competition", "fetch-finished-fixtures", "load-cached-final-events", "select-finished-fixtures", "load-forecasts", "build-audits", "save-audits", "aggregate-audit", "save-aggregate", "load-signal-ledger", "load-snapshots", "settle-clv", "save-clv-settled", "aggregate-clv", "save-clv-report", "load-calibration-sample", "settle-calibration", "save-calibration-settled", "load-calibration-report", "compute-calibration", "save-calibration-report"],
    "worldcup-match-recap": ["resolve-load-events", "resolve-fixture", "load-cached", "load-event", "load-forecast", "grounded-recap-research", "worldcup-match-recap", "save-candidate"],
    "worldcup-player-spotlight": ["resolve-load-players", "resolve-player", "load-cached", "load-player", "load-final-fifa-performance", "build-player-overview", "worldcup-player-spotlight", "save-candidate"],
}
EVENT_URN = "urn:machina:sport:soccer:event:brazil-vs-morocco:20260613:wor"
PLAYER_URN = "urn:machina:sport:soccer:player:archive-player:20000101:bra"
TEAM_URN = "urn:machina:sport:soccer:team:brazil:bra"
EVENT = {
    "_id": EVENT_URN,
    "name": "Brazil vs Morocco - FIFA World Cup 2026",
    "machina_competition_slug": "world-cup-2026",
    "schema:startDate": "2026-06-13T18:00:00Z",
    "sport:status": "FT",
    "provider_ids": {"api_football": "1489417"},
    "sport:competitors": [
        {"@id": TEAM_URN, "name": "Brazil", "sport:qualifier": "home"},
        {"@id": "urn:machina:sport:soccer:team:morocco:mar", "name": "Morocco", "sport:qualifier": "away"},
    ],
    "live_score": {"home": 2, "away": 1, "elapsed": 90},
}
PLAYER = {
    "_id": PLAYER_URN,
    "@type": ["sport:IdentityCrosswalk", "sport:Player"],
    "name": "Archive Player",
    "machina_competition_slug": "world-cup-2026",
    "nationality": "Brazil",
    "team": {"@id": TEAM_URN, "name": "Brazil"},
    "provider_ids": {"api_football": "77"},
}


def _archive(capability, provenance, snapshot="2026-07-20T00:00:00Z", missing=None, notes=None):
    return {
        "mode": "final_archive",
        "competition": "FIFA World Cup 2026",
        "competition_status": "completed",
        "live": False,
        "snapshot_as_of": snapshot,
        "capability_status": capability,
        "provenance": provenance,
        "missing_capabilities": missing or [],
        "notes": notes or [],
    }


def _responses():
    resolved = {
        "event_urn": EVENT_URN,
        "name": EVENT["name"],
        "start_date": EVENT["schema:startDate"],
        "status": "ft",
        "teams": [
            {"team_urn": TEAM_URN, "name": "Brazil", "qualifier": "home", "crest": None},
            {"team_urn": "urn:machina:sport:soccer:team:morocco:mar", "name": "Morocco", "qualifier": "away", "crest": None},
        ],
        "fixture_id": "1489417",
    }
    forecast = {
        "_id": EVENT_URN,
        "data_source": "blend",
        "model": {"computed_at": "2026-06-13T10:00:00Z"},
        "probabilities": {"home_win": 0.55, "draw": 0.25, "away_win": 0.2},
    }
    player_context = {
        "event": EVENT,
        "player": {"player_id": "77", "name": "Archive Player"},
        "official_fifa_power_ranking": {"status": "available", "source": "fifa.com"},
        "machina_provisional_performance_signal": {"status": "available", "scores_0_10": {"attacking": 7.1}},
    }
    return {
        "worldcup-resolve": {
            "entity": {"_id": TEAM_URN, "name": "Brazil", "machina_competition_slug": "world-cup-2026", "provider_ids": {"api_football": "6"}},
            "entities": [{"_id": TEAM_URN, "name": "Brazil", "machina_competition_slug": "world-cup-2026", "provider_ids": {"api_football": "6"}}],
            "count": 1,
            "warnings": [],
            "archive": _archive("complete", ["worldcup:identity-crosswalk"]),
        },
        "worldcup-get-schedule": {
            "schedule": {"events": [EVENT], "count": 1, "warnings": []},
            "warnings": [],
            "archive": _archive("complete", ["worldcup:event"]),
        },
        "worldcup-get-event-context": {
            "event_context": {"event": EVENT, "sports_context": {"archived": True}},
            "event_urn": EVENT_URN,
            "resolved_fixture": resolved,
            "candidates": [resolved],
            "warnings": [],
            "archive": _archive("complete", ["worldcup:event", "sports-skills"]),
        },
        "worldcup-get-standings": {
            "standings": {"source": "api-football", "groups": [{"group": "A", "table": []}], "group_count": 1},
            "warnings": [],
            "archive": _archive("complete", ["api-football"]),
        },
        "worldcup-get-squads": {
            "squads": {"snapshot_type": "archived_tournament_identity_snapshot", "evidence_status": "partial", "teams": [{"side": "home"}, {"side": "away"}]},
            "candidates": [resolved],
            "warnings": ["Not proof of complete official registration."],
            "archive": _archive("partial", ["worldcup:identity-crosswalk"], missing=["verified_complete_official_squad_registration"]),
        },
        "worldcup-get-injuries": {
            "injuries": {"source": "api-football", "teams": [{"side": "home", "count": 0}, {"side": "away", "count": 0}]},
            "candidates": [resolved],
            "warnings": ["Empty evidence does not prove complete historical coverage."],
            "archive": _archive("partial", ["api-football"], missing=["verified_complete_injury_coverage"]),
        },
        "worldcup-get-player-performance-context": {
            "player_performance_context": player_context,
            "status": "available",
            "candidates": [resolved],
            "player_candidates": [{"player_urn": PLAYER_URN, "name": "Archive Player"}],
            "warnings": [],
            "archive": _archive("complete", ["api-football", "fifa.com"]),
        },
        "worldcup-get-match-forecast": {
            "forecast": forecast,
            "model_vs_market": {"comparison_status": "suppressed_no_historical_quote", "gaps": []},
            "analysis": {},
            "forecast_integrity": {"classification": "verified_pre_kickoff", "verified_pre_kickoff": True},
            "market_integrity": {"classification": "unavailable"},
            "candidates": [resolved],
            "warnings": [],
            "archive": _archive("historical_model", ["worldcup:model-forecast"], snapshot=forecast["model"]["computed_at"]),
        },
        "worldcup-backtest-forecasts": {
            "finished_fixtures": [{"fixture": {"id": "1489417"}, "goals": {"home": 2, "away": 1}}],
            "status": "available",
            "provenance": "worldcup-event-cache",
            "warnings": [],
            "audited_count": 1,
            "total_count": 1,
            "included_count": 1,
            "excluded_count": 0,
            "exclusion_reasons": {},
            "sources": ["worldcup:event", "worldcup:model-forecast"],
            "track_record": {"sample_size": 1, "sample_size_sufficient": False},
            "clv_settled_count": 0,
            "clv_report": {},
            "calibration_settled_count": 0,
            "calibration_report": {},
            "archive": _archive("historical_aggregate", ["worldcup:event", "worldcup:model-forecast"], missing=["statistically_sufficient_sample"]),
        },
        "worldcup-match-recap": {
            "skill_card": {"headline": "Original matchday recap", "historical_perspective": "original_cached_matchday_copy"},
            "event_urn": EVENT_URN,
            "resolved_fixture": resolved,
            "candidates": [resolved],
            "warnings": [],
            "archive": _archive("evergreen_editorial", ["worldcup:skill-match-recap"], snapshot="2026-06-14T01:00:00Z"),
        },
        "worldcup-player-spotlight": {
            "skill_card": {"headline": "Original tournament spotlight"},
            "player_urn": PLAYER_URN,
            "resolved_player": {"player_urn": PLAYER_URN, "name": "Archive Player"},
            "player_overview": {"player_urn": PLAYER_URN, "name": "Archive Player", "sources": [{"source": "fifa.com"}]},
            "candidates": [{"player_urn": PLAYER_URN, "name": "Archive Player"}],
            "warnings": [],
            "archive": _archive("archived_editorial", ["worldcup:skill-player-spotlight"], snapshot="2026-09-01T02:08:38Z"),
        },
    }


def _subject(endpoint):
    if endpoint == "worldcup-resolve":
        return {"key": TEAM_URN, "aliases": [TEAM_URN, "6"]}
    if endpoint == "worldcup-get-schedule":
        return {"key": "tournament"}
    if endpoint in {"worldcup-get-standings", "worldcup-backtest-forecasts"}:
        return {"key": "world-cup-2026"}
    if endpoint == "worldcup-player-spotlight":
        return {"key": PLAYER_URN, "player": PLAYER}
    if endpoint == "worldcup-get-player-performance-context":
        return {"key": f"{EVENT_URN}|{PLAYER_URN}", "event_urn": EVENT_URN, "event": EVENT, "player": PLAYER}
    return {"key": EVENT_URN, "event_urn": EVENT_URN, "provider_event_id": "1489417", "event": EVENT}


def _parameters(endpoint):
    return {
        "worldcup-get-event-context": {"include_prematch_research": True, "include_social_pulse": False},
        "worldcup-get-standings": {"league": "1", "season": "2026"},
        "worldcup-get-injuries": {"league": "1", "season": "2026"},
        "worldcup-get-player-performance-context": {"team_id": ""},
        "worldcup-get-match-forecast": {"include_reasoning": False, "min_gap_bps": 100},
        "worldcup-backtest-forecasts": {"competition": "world-cup-2026", "league": "", "season": "", "calibration_window_days": 90},
    }.get(endpoint, {})


def _request(endpoint):
    if endpoint == "worldcup-resolve":
        return {"id": "6"}
    if endpoint == "worldcup-get-schedule":
        return {}
    if endpoint in {"worldcup-get-standings", "worldcup-backtest-forecasts"}:
        return {}
    if endpoint == "worldcup-player-spotlight":
        return {"player": "Archive Player", "team": "Brazil"}
    if endpoint == "worldcup-get-player-performance-context":
        return {"event_urn": EVENT_URN, "player_id": "77"}
    return {"event": "Brazil vs Morocco"}


def _document(endpoint, invalidated=False):
    source = {"document_name": "observed:test", "source_sha256": "a" * 64, "temporal_scope": "world-cup-2026"}
    if endpoint in {"worldcup-match-recap", "worldcup-player-spotlight"}:
        source["generated_at"] = _responses()[endpoint]["archive"]["snapshot_as_of"]
    value = CONNECTOR.build_final_archive_document(
        endpoint,
        _subject(endpoint),
        _parameters(endpoint),
        _responses()[endpoint],
        [source],
        invalidated=invalidated,
    )
    return {"name": CONNECTOR.FINAL_ARCHIVE_DOCUMENT, "value": value}


def _eval(expression, context):
    if not isinstance(expression, str):
        return expression
    if expression == "$":
        return context
    namespace = {
        "__builtins__": {},
        "bool": bool,
        "dict": dict,
        "isinstance": isinstance,
        "len": len,
        "list": list,
        "max": max,
        "min": min,
        "repr": repr,
        "str": str,
        "context": context,
    }
    return eval(expression.replace("$.get", "context.get"), namespace, namespace)


class DocumentStoreAdapter:
    def __init__(self, documents):
        self.documents = documents
        self.searches = 0
        self.writes = 0
        self.executed = []

    def execute(self, task, context):
        action = task["config"]["action"]
        self.executed.append(task["name"])
        if action != "search":
            self.writes += 1
            return {}
        self.searches += 1
        matched = []
        for document in self.documents:
            keep = True
            for path, expression in task.get("filters", {}).items():
                expected = _eval(expression, context)
                value = document
                for part in path.split("."):
                    value = value.get(part) if isinstance(value, dict) else None
                if isinstance(expected, dict) and "$ne" in expected:
                    keep = value != expected["$ne"]
                else:
                    keep = value == expected
                if not keep:
                    break
            if keep:
                matched.append(document)
        matched.sort(key=lambda row: row.get("_id") or row.get("value", {}).get("_id", ""))
        return {"documents": matched[: task["config"]["search-limit"]]}


class ConnectorAdapter:
    def __init__(self):
        self.external_calls = []
        self.internal_calls = []

    def execute(self, task, inputs):
        connector = task["connector"]["name"]
        if connector != "worldcup-market-intelligence":
            self.external_calls.append(connector)
            return {}
        self.internal_calls.append(task["connector"]["command"])
        result = getattr(CONNECTOR, task["connector"]["command"])({"params": inputs})
        assert result["status"] is True
        return result["data"]


def _store_documents(endpoint, archive_documents):
    documents = list(archive_documents)
    if endpoint in {
        "worldcup-resolve", "worldcup-get-schedule", "worldcup-get-event-context", "worldcup-get-squads",
        "worldcup-get-injuries", "worldcup-get-player-performance-context", "worldcup-get-match-forecast",
        "worldcup-match-recap",
    }:
        documents.append({"name": "worldcup:event", "value": EVENT})
    if endpoint in {"worldcup-resolve", "worldcup-get-player-performance-context", "worldcup-player-spotlight"}:
        documents.extend([
            {"name": "worldcup:identity-crosswalk", "value": PLAYER},
            {"name": "worldcup:identity-crosswalk", "value": _responses()["worldcup-resolve"]["entity"]},
        ])
    return documents


def execute_yaml(endpoint, request, documents, *, include_canonical=True):
    workflow = yaml.safe_load((ROOT / "workflows" / f"{endpoint}.yml").read_text(encoding="utf-8"))["workflow"]
    context = dict(request)
    for key, expression in workflow.get("inputs", {}).items():
        context[key] = _eval(expression, context)
    store = DocumentStoreAdapter(_store_documents(endpoint, documents) if include_canonical else documents)
    connectors = ConnectorAdapter()
    for task in workflow["tasks"]:
        if task.get("condition") and not _eval(task["condition"], context):
            continue
        if task["type"] == "document":
            result = store.execute(task, context)
        elif task["type"] == "connector":
            inputs = {key: _eval(value, context) for key, value in task.get("inputs", {}).items()}
            result = connectors.execute(task, inputs)
        elif task["type"] == "prompt":
            connectors.external_calls.append((task.get("connector") or {}).get("name", "prompt"))
            result = {}
        elif task["type"] == "mapping":
            result = {}
        else:
            raise AssertionError(f"forbidden public task type: {task['type']}")
        for key, expression in task.get("outputs", {}).items():
            context[key] = _eval(expression, result)
    outputs = {key: _eval(expression, context) for key, expression in workflow["outputs"].items()}
    return outputs, store, connectors


def test_all_legacy_task_graphs_are_preserved_and_gated_only_after_archive_lookup():
    for endpoint, expected in LEGACY_TASKS.items():
        workflow = yaml.safe_load((ROOT / "workflows" / f"{endpoint}.yml").read_text(encoding="utf-8"))["workflow"]
        names = [task["name"] for task in workflow["tasks"]]
        assert names[-len(expected):] == expected
        for item in workflow["tasks"][-len(expected):]:
            assert item["condition"].startswith("$.get('archive_status', 'miss') == 'miss'")


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_all_eleven_yaml_workflows_serve_warmed_archive_without_external_calls(endpoint):
    outputs, store, connectors = execute_yaml(endpoint, _request(endpoint), [_document(endpoint)])
    assert outputs["archive"]["status"] == "hit"
    assert outputs["archive"]["version"] == CONNECTOR.FINAL_ARCHIVE_VERSION
    assert outputs["archive"]["response_sha256"]
    assert outputs["archive"]["request_identity_sha256"]
    assert outputs["workflow-status"] == "executed"
    assert store.writes == 0
    assert connectors.external_calls == []
    expected_internal = ["resolve_archived_fixture", "serve_final_archive"] if endpoint in CONNECTOR.FINAL_ARCHIVE_FIXTURE_ENDPOINTS else ["serve_final_archive"]
    assert connectors.internal_calls == expected_internal
    assert all(name.startswith("load-final-archive") for name in store.executed)


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_all_eleven_yaml_workflows_preserve_legacy_execution_on_clean_cold_miss(endpoint):
    outputs, store, connectors = execute_yaml(endpoint, _request(endpoint), [])
    assert "serve_final_archive" in connectors.internal_calls
    assert any(not name.startswith("load-final-archive") for name in store.executed) or len(connectors.internal_calls) > 1 or connectors.external_calls


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_v1_workflow_requests_cleanly_miss_during_v2_connector_handoff(endpoint):
    result = CONNECTOR.serve_final_archive({"params": {
        "endpoint": endpoint,
        "archive_version": CONNECTOR.LEGACY_FINAL_ARCHIVE_VERSION,
        "request": _request(endpoint),
        "documents": [_document(endpoint)],
        "archive_manifest": [_closure_document_for_handoff()],
    }})["data"]
    assert result["archive_status"] == "miss"
    assert result["archive_hit"] is False
    assert result["archive"]["version"] == CONNECTOR.LEGACY_FINAL_ARCHIVE_VERSION


def _closure_document_for_handoff():
    return {"name": CONNECTOR.FINAL_ARCHIVE_MANIFEST_DOCUMENT, "value": {"archive_version": CONNECTOR.FINAL_ARCHIVE_VERSION}}


def test_public_workflows_pin_v2_without_exposing_a_version_input():
    for endpoint in ENDPOINTS:
        workflow = yaml.safe_load((ROOT / "workflows" / f"{endpoint}.yml").read_text(encoding="utf-8"))["workflow"]
        assert "archive_version" not in workflow.get("inputs", {})
        serve = next(task for task in workflow["tasks"] if task["name"] == "serve-final-archive")
        assert serve["inputs"]["archive_version"] == f"'{CONNECTOR.FINAL_ARCHIVE_VERSION}'"


@pytest.mark.parametrize("endpoint", ENDPOINTS)
def test_all_eleven_yaml_workflows_reject_malformed_and_invalidated_rows(endpoint):
    malformed = _document(endpoint)
    malformed["value"]["response"]["tampered"] = True
    outputs, _, connectors = execute_yaml(endpoint, _request(endpoint), [malformed])
    assert outputs["archive"]["status"] == "error"
    assert outputs["workflow-status"] == "skipped"
    assert connectors.external_calls == []
    expected_internal = ["resolve_archived_fixture", "serve_final_archive"] if endpoint in CONNECTOR.FINAL_ARCHIVE_FIXTURE_ENDPOINTS else ["serve_final_archive"]
    assert connectors.internal_calls == expected_internal

    outputs, _, connectors = execute_yaml(endpoint, _request(endpoint), [_document(endpoint, invalidated=True)])
    assert outputs["archive"]["status"] == "error"
    assert outputs["workflow-status"] == "skipped"
    assert connectors.external_calls == []
    assert connectors.internal_calls == expected_internal


def test_parameter_variations_are_exact_except_schedule_local_filters_and_force_regen():
    schedule_row = _document("worldcup-get-schedule")
    all_outputs, _, _ = execute_yaml("worldcup-get-schedule", {}, [schedule_row])
    filtered, _, _ = execute_yaml("worldcup-get-schedule", {"team": "Brazil", "status": "FT", "limit": 1}, [schedule_row])
    assert filtered["schedule"]["count"] == 1
    assert filtered["archive"]["request_identity_sha256"] != all_outputs["archive"]["request_identity_sha256"]

    variations = {
        "worldcup-get-event-context": {"event_urn": EVENT_URN, "include_social_pulse": True},
        "worldcup-get-standings": {"season": "2025"},
        "worldcup-get-player-performance-context": {"event_urn": EVENT_URN, "player_id": "77", "team_id": "6"},
        "worldcup-get-match-forecast": {"event_urn": EVENT_URN, "min_gap_bps": 200},
        "worldcup-backtest-forecasts": {"calibration_window_days": 30},
    }
    for endpoint, request in variations.items():
        outputs, _, connectors = execute_yaml(endpoint, request, [_document(endpoint)])
        assert outputs["archive"].get("status") != "hit", endpoint
        assert "serve_final_archive" in connectors.internal_calls

    recap, _, _ = execute_yaml("worldcup-match-recap", {"event_urn": EVENT_URN, "force_regen": True}, [_document("worldcup-match-recap")])
    spotlight, _, _ = execute_yaml("worldcup-player-spotlight", {"player_urn": PLAYER_URN, "force_regen": True}, [_document("worldcup-player-spotlight")])
    assert recap["archive"]["status"] == spotlight["archive"]["status"] == "hit"
    assert recap["skill_card"]["historical_perspective"] == "original_cached_matchday_copy"


def test_schedule_filters_multiword_names_without_using_slugged_filter_values():
    multiword_events = [
        {**EVENT, "_id": "urn:event:korea", "name": "South Korea vs Uruguay", "sport:competitors": [
            {"@id": "urn:team:korea", "name": "South Korea", "sport:qualifier": "home"},
            {"@id": "urn:team:uruguay", "name": "Uruguay", "sport:qualifier": "away"},
        ]},
        {**EVENT, "_id": "urn:event:bosnia", "name": "Bosnia & Herzegovina vs Japan", "sport:competitors": [
            {"@id": "urn:team:bosnia", "name": "Bosnia & Herzegovina", "sport:qualifier": "home"},
            {"@id": "urn:team:japan", "name": "Japan", "sport:qualifier": "away"},
        ]},
    ]
    response = _responses()["worldcup-get-schedule"]
    response["schedule"] = CONNECTOR.normalize_schedule({"params": {"events": multiword_events, "limit": 500}})["data"]
    row = {"name": CONNECTOR.FINAL_ARCHIVE_DOCUMENT, "value": CONNECTOR.build_final_archive_document(
        "worldcup-get-schedule", {"key": "tournament"}, {}, response,
        [{"document_name": "worldcup:event", "source_sha256": "a" * 64}],
    )}
    for team in ("South Korea", "Bosnia & Herzegovina"):
        result = CONNECTOR.serve_final_archive({"params": {
            "endpoint": "worldcup-get-schedule", "documents": [row], "canonical_events": multiword_events,
            "request": {"team": team, "limit": 500},
        }})["data"]
        assert result["archive_status"] == "hit"
        assert result["response"]["schedule"]["count"] == 1


def test_subject_metadata_is_hashed_and_full_event_universe_controls_ambiguity():
    row = _document("worldcup-get-event-context")
    tampered = copy.deepcopy(row)
    tampered["value"]["subject"]["event"]["name"] = "Tampered"
    invalid = CONNECTOR.serve_final_archive({"params": {
        "endpoint": "worldcup-get-event-context", "documents": [tampered],
        "canonical_events": [{"value": EVENT}], "request": {"event_urn": EVENT_URN},
    }})["data"]
    assert invalid["archive_status"] == "error"
    assert any("subject_sha256" in warning for warning in invalid["warnings"])

    second = copy.deepcopy(EVENT)
    second["_id"] = "urn:event:brazil-japan"
    second["provider_ids"] = {"api_football": "2"}
    second["sport:competitors"][1] = {"@id": "urn:team:japan", "name": "Japan", "sport:qualifier": "away"}
    full_universe = [{"value": EVENT}, {"value": second}]
    for index in range(102):
        other = copy.deepcopy(EVENT)
        other["_id"] = f"urn:event:other:{index}"
        other["provider_ids"] = {"api_football": f"other-{index}"}
        other["sport:competitors"] = [
            {"@id": "urn:team:a", "name": "Team A", "sport:qualifier": "home"},
            {"@id": "urn:team:b", "name": "Team B", "sport:qualifier": "away"},
        ]
        full_universe.append({"value": other})
    ambiguous = CONNECTOR.serve_final_archive({"params": {
        "endpoint": "worldcup-get-event-context", "documents": [row],
        "canonical_events": full_universe, "request": {"team": "Brazil"},
    }})["data"]
    assert ambiguous["archive_status"] == "miss"
    assert len(ambiguous["response"]["candidates"]) == 2


def test_player_aliases_are_supported_but_all_supplied_selectors_must_agree():
    aliased = copy.deepcopy(PLAYER)
    aliased["aliases"] = ["Vini Jr"]
    row = _document("worldcup-player-spotlight")
    hit = CONNECTOR.serve_final_archive({"params": {
        "endpoint": "worldcup-player-spotlight", "documents": [row],
        "canonical_identities": [{"value": aliased}], "canonical_events": [{"value": EVENT}],
        "request": {"player": "Vini Jr", "team": "Brazil"},
    }})["data"]
    assert hit["archive_status"] == "hit"
    conflict = CONNECTOR.serve_final_archive({"params": {
        "endpoint": "worldcup-player-spotlight", "documents": [row],
        "canonical_identities": [{"value": aliased}], "canonical_events": [{"value": EVENT}],
        "request": {"player_urn": PLAYER_URN, "player": "Vini Jr", "team": "Morocco"},
    }})["data"]
    assert conflict["archive_status"] == "error"


def test_injury_identity_includes_normalized_league_and_season():
    assert CONNECTOR._archive_parameters("worldcup-get-injuries", {}) == {"league": "1", "season": "2026"}
    assert CONNECTOR._archive_parameters("worldcup-get-injuries", {"league": 1, "season": 2026}) == {"league": "1", "season": "2026"}
    assert CONNECTOR._archive_parameters("worldcup-get-injuries", {"season": "2025"}) != _parameters("worldcup-get-injuries")


def test_canary_does_not_suppress_legacy_noncanary_player_resolution():
    second = copy.deepcopy(EVENT)
    second["_id"] = "urn:event:other-fixture"
    second["provider_ids"] = {"api_football": "other-fixture"}
    docs = [_document("worldcup-get-player-performance-context"), {"name": "worldcup:event", "value": second}]
    _, _, connectors = execute_yaml("worldcup-get-player-performance-context", {
        "event_urn": second["_id"], "player": "Unknown Player", "team": "Brazil",
    }, docs)
    assert "resolve_archived_fixture" in connectors.internal_calls
    _, _, connectors = execute_yaml("worldcup-player-spotlight", {
        "player": "Unknown Player", "team": "Brazil",
    }, [_document("worldcup-player-spotlight")])
    assert "resolve_player" in connectors.internal_calls


def test_ambiguous_fixture_keeps_legacy_candidates_after_canary():
    second = copy.deepcopy(EVENT)
    second["_id"] = "urn:event:brazil-japan"
    second["provider_ids"] = {"api_football": "other-fixture"}
    second["sport:competitors"][1] = {"@id": "urn:team:japan", "name": "Japan", "sport:qualifier": "away"}
    output, _, connectors = execute_yaml("worldcup-get-event-context", {"team": "Brazil"}, [
        _document("worldcup-get-event-context"), {"name": "worldcup:event", "value": second},
    ])
    assert len(output["candidates"]) == 2
    assert "resolve_archived_fixture" in connectors.internal_calls
    assert not connectors.external_calls


def test_normalized_schedule_snapshot_preserves_every_public_event_field():
    endpoint = "worldcup-get-schedule"
    original = CONNECTOR.normalize_schedule({"params": {"events": [EVENT], "team": "Brazil", "limit": 100}})["data"]
    document = _document(endpoint)
    previous = document["value"]
    response = copy.deepcopy(previous["response"])
    response["schedule"] = original
    document["value"] = CONNECTOR.build_final_archive_document(
        endpoint, previous["subject"], previous["parameter_identity"], response, previous["source_manifest"],
    )
    output, store, connectors = execute_yaml(endpoint, {"team": "Brazil", "limit": 100}, [document])
    assert output["archive"]["status"] == "hit"
    assert output["schedule"] == original
    assert not connectors.external_calls and store.writes == 0


def test_non_world_cup_backtest_clean_miss_keeps_legacy_provider_path():
    _, _, connectors = execute_yaml(
        "worldcup-backtest-forecasts",
        {"competition": "brasileirao-2026", "league": "71", "season": "2026"},
        [_document("worldcup-backtest-forecasts")],
    )
    assert "serve_final_archive" in connectors.internal_calls
    assert "api-football" in connectors.external_calls


def test_conflicting_player_selectors_and_truncated_indexes_fail_closed():
    row = _document("worldcup-get-player-performance-context")
    common = {
        "endpoint": "worldcup-get-player-performance-context",
        "documents": [row],
        "canonical_events": [{"value": EVENT}],
        "canonical_identities": [{"value": PLAYER}],
        "request": {"event_urn": EVENT_URN, "player_urn": PLAYER_URN, "player_id": "999"},
    }
    conflict = CONNECTOR.serve_final_archive({"params": common})["data"]
    assert conflict["archive_status"] == "error"
    assert "Conflicting" in conflict["warnings"][0]

    for flag in ("archive_search_limit_reached", "event_search_limit_reached", "identity_search_limit_reached"):
        bounded = CONNECTOR.serve_final_archive({"params": {**common, flag: True}})["data"]
        assert bounded["archive_status"] == "error"
        assert "incomplete" in bounded["warnings"][0]


def test_labeled_observed_mcp_shapes_use_content_text_data_data_value():
    fixture = json.loads((ROOT / "tests" / "fixtures" / "archive-observed-shapes.json").read_text(encoding="utf-8"))
    expected_names = {
        "event": "worldcup:event",
        "identity": "worldcup:identity-crosswalk",
        "forecast": "worldcup:model-forecast",
        "ranking": "worldcup:final-fifa-player-power-ranking",
        "recap": "worldcup:skill-match-recap",
        "spotlight": "worldcup:skill-player-spotlight",
    }
    for label, case in fixture["labels"].items():
        rows, total = TOOL.extract_mcp_document_rows(case["payload"])
        assert total == case["expected_total"]
        assert rows[0]["name"] == expected_names[label]
        assert isinstance(rows[0]["value"], dict)
        if label == "event":
            normalized = CONNECTOR.normalize_schedule({"params": {
                "events": [rows[0]["value"]],
                "date_from": "2026-06-11",
                "date_to": "2026-06-11",
                "status": "FT",
            }})["data"]
            assert normalized["count"] == 1
            assert normalized["events"][0]["fixture_id"] == "1489369"


def _operator_manifest():
    targets = {}
    entries = []
    for endpoint in ENDPOINTS:
        subject = _subject(endpoint)
        parameters = _parameters(endpoint)
        targets[endpoint] = [{"subject_key": subject["key"], "parameters": parameters}]
        response = _responses()[endpoint]
        sources = []
        for provenance in response["archive"]["provenance"]:
            if endpoint == "worldcup-get-match-forecast" and provenance == "worldcup:model-forecast":
                source_payload = response["forecast"]
            elif endpoint == "worldcup-match-recap" and provenance == "worldcup:skill-match-recap":
                source_payload = {"body": response["skill_card"], "generated_at": response["archive"]["snapshot_as_of"]}
            elif endpoint == "worldcup-player-spotlight" and provenance == "worldcup:skill-player-spotlight":
                source_payload = {"body": response["skill_card"], "generated_at": response["archive"]["snapshot_as_of"]}
            else:
                source_payload = {"endpoint": endpoint, "subject_key": subject["key"], "provenance": provenance}
            source = {
                "document_name": provenance,
                "source": provenance,
                "source_payload": source_payload,
                "source_sha256": CONNECTOR._archive_sha256(source_payload),
                "temporal_scope": "world-cup-2026",
            }
            if endpoint in {"worldcup-match-recap", "worldcup-player-spotlight"}:
                source["generated_at"] = response["archive"]["snapshot_as_of"]
            sources.append(source)
        if endpoint == "worldcup-backtest-forecasts":
            source_payload = {"backtesting_report": response["track_record"]}
            sources.append({
                "document_name": "worldcup:forecast-audit",
                "source": "worldcup:forecast-audit",
                "source_payload": source_payload,
                "source_sha256": CONNECTOR._archive_sha256(source_payload),
                "temporal_scope": "world-cup-2026",
            })
        entries.append({
            "endpoint": endpoint,
            "subject": subject,
            "parameters": parameters,
            "response": response,
            "source_manifest": sources,
        })
    return {
        "schema_version": 1,
        "archive_version": CONNECTOR.FINAL_ARCHIVE_VERSION,
        "fixture_urns": [EVENT_URN],
        "recap_fixture_urns": [EVENT_URN],
        "fixture_player_targets": [{"event_urn": EVENT_URN, "player_urn": PLAYER_URN, "subject_key": f"{EVENT_URN}|{PLAYER_URN}"}],
        "spotlight_targets": [PLAYER_URN],
        "targets": targets,
        "entries": entries,
        "expected_archive_count": len(entries),
        "publication_ready": True,
    }


def test_operator_tool_dry_run_canary_verify_resume_and_fanout(tmp_path, capsys):
    manifest_path = tmp_path / "manifest.json"
    bundle_path = tmp_path / "canary.json"
    fanout_path = tmp_path / "fanout.json"
    state_path = tmp_path / "state.json"
    manifest_path.write_text(json.dumps(_operator_manifest()), encoding="utf-8")

    assert TOOL.main(["prepare", "--manifest", str(manifest_path)]) == 0
    assert not bundle_path.exists()
    assert json.loads(capsys.readouterr().out)["dry_run"] is True

    assert TOOL.main(["prepare", "--manifest", str(manifest_path), "--batch-size", "1", "--canary", "--write", "--output", str(bundle_path), "--resume-state", str(state_path)]) == 0
    capsys.readouterr()
    state = json.loads(state_path.read_text())
    assert state["next_offset"] == 0
    assert state["pending"]["next_offset"] == 1
    canary = json.loads(bundle_path.read_text())
    canary_readback = tmp_path / "canary-readback.json"
    canary_readback.write_text(json.dumps({
        "content": [{"type": "text", "text": json.dumps({
            "status": "success",
            "data": {"data": canary["documents"], "total_documents": 1},
        })}],
    }), encoding="utf-8")
    assert TOOL.main(["verify", "--bundle", str(canary_readback), "--manifest", str(manifest_path), "--resume-state", str(state_path)]) == 0
    capsys.readouterr()
    state = json.loads(state_path.read_text())
    assert state["canary_verified"] is True
    assert state["next_offset"] == 1

    assert TOOL.main(["prepare", "--manifest", str(manifest_path), "--batch-size", "100", "--fanout", "--write", "--output", str(fanout_path), "--resume-state", str(state_path)]) == 0
    capsys.readouterr()
    fanout = json.loads(fanout_path.read_text())
    assert fanout["offset"] == 1
    assert fanout["count"] == 10
    assert TOOL.verify_bundle(fanout, _operator_manifest())["verified"] is True
    assert json.loads(state_path.read_text())["next_offset"] == 1
    assert TOOL.main(["verify", "--bundle", str(fanout_path), "--manifest", str(manifest_path), "--resume-state", str(state_path)]) == 0
    capsys.readouterr()
    state = json.loads(state_path.read_text())
    assert state["canary_verified"] is True
    assert state["next_offset"] == 11


def test_operator_tool_rejects_count_dedupe_scope_and_manifest_drift(tmp_path):
    manifest = _operator_manifest()
    manifest["expected_archive_count"] += 1
    with pytest.raises(TOOL.ArchivePreparationError, match="expected_archive_count"):
        TOOL.prepare_manifest(manifest)

    manifest = _operator_manifest()
    manifest["entries"].append(copy.deepcopy(manifest["entries"][0]))
    with pytest.raises(TOOL.ArchivePreparationError, match="duplicate entry identity"):
        TOOL.prepare_manifest(manifest)

    manifest = _operator_manifest()
    injury = next(row for row in manifest["entries"] if row["endpoint"] == "worldcup-get-injuries")
    source_payload = {"current": True}
    injury["source_manifest"] = [{
        "document_name": "api-football-current",
        "source": "api-football",
        "source_payload": source_payload,
        "source_sha256": CONNECTOR._archive_sha256(source_payload),
    }]
    with pytest.raises(TOOL.ArchivePreparationError, match="unverified squad/injury temporal scope"):
        TOOL.prepare_manifest(manifest)

    manifest = _operator_manifest()
    manifest["entries"][0]["source_manifest"][0]["source_sha256"] = "0" * 64
    with pytest.raises(TOOL.ArchivePreparationError, match="source payload hash mismatch"):
        TOOL.prepare_manifest(manifest)


def test_capture_cli_builds_exact_labeled_synthetic_eleven_endpoint_bundle(tmp_path, capsys):
    executions_dir = tmp_path / "executions"
    exports_dir = tmp_path / "export"
    executions_dir.mkdir()
    exports_dir.mkdir()

    canary_event = copy.deepcopy(EVENT)
    canary_event["provider_ids"]["api_football"] = TOOL.CANARY_FIXTURE_ID
    canary_player = copy.deepcopy(PLAYER)
    canary_player["provider_ids"]["api_football"] = TOOL.CANARY_PLAYER_ID
    canary_team = copy.deepcopy(_responses()["worldcup-resolve"]["entity"])
    events = [{"name": "worldcup:event", "value": canary_event}]
    forecasts = [{"name": "worldcup:model-forecast", "value": copy.deepcopy(_responses()["worldcup-get-match-forecast"]["forecast"])}]
    forecasts[0]["value"]["provider_ids"] = {"api_football": TOOL.CANARY_FIXTURE_ID}
    identities = [
        {"name": "worldcup:identity-crosswalk", "value": canary_team},
        {"name": "worldcup:identity-crosswalk", "value": canary_player},
    ]
    rankings = [{"name": "worldcup:final-fifa-player-power-ranking", "value": {"player_urn": PLAYER_URN, "record_type": "player_power_ranking"}}]
    recaps = [{"name": "worldcup:skill-match-recap", "value": {"subject_urn": EVENT_URN, "body": {"headline": "Original matchday recap"}}}]
    spotlights = [{"name": "worldcup:skill-player-spotlight", "value": {"subject_urn": PLAYER_URN, "body": {"headline": "Original tournament spotlight"}}}]
    for index in range(1, 104):
        synthetic = copy.deepcopy(EVENT)
        synthetic["_id"] = f"urn:event:synthetic:{index}"
        synthetic["provider_ids"] = {"api_football": f"synthetic-{index}"}
        synthetic["schema:startDate"] = f"2026-07-{(index % 20) + 1:02d}T18:00:00Z"
        events.append({"name": "worldcup:event", "value": synthetic})
        forecast = copy.deepcopy(forecasts[0]["value"])
        forecast["_id"] = synthetic["_id"]
        forecast["@id"] = synthetic["_id"]
        forecast["provider_ids"] = synthetic["provider_ids"]
        forecasts.append({"name": "worldcup:model-forecast", "value": forecast})
    for index in range(2, 1281):
        identities.append({"name": "worldcup:identity-crosswalk", "value": {
            "_id": f"urn:player:synthetic:{index}", "@type": ["sport:IdentityCrosswalk", "sport:Player"],
            "name": f"Synthetic Player {index}", "machina_competition_slug": "world-cup-2026",
            "provider_ids": {"api_football": f"synthetic-{index}"},
        }})
    for index in range(1, 231):
        rankings.append({"name": "worldcup:final-fifa-player-power-ranking", "value": {"player_urn": f"urn:player:ranking:{index}", "record_type": "player_power_ranking"}})
    for index in range(1, 13):
        recaps.append({"name": "worldcup:skill-match-recap", "value": {"subject_urn": f"urn:event:recap:{index}", "body": {"headline": f"Recap {index}"}}})
    spotlights.append({"name": "worldcup:skill-player-spotlight", "value": {"subject_urn": "urn:player:other", "body": {"headline": "Other"}}})

    exports = {
        "worldcup:event": events,
        "worldcup:model-forecast": forecasts,
        "worldcup:identity-crosswalk": identities,
        "worldcup:final-fifa-player-power-ranking": rankings,
        "worldcup:skill-match-recap": recaps,
        "worldcup:skill-player-spotlight": spotlights,
    }
    export_manifest = {}
    for name, rows in exports.items():
        path = exports_dir / f"{name.replace(':', '-')}.json"
        path.write_text(json.dumps(rows), encoding="utf-8")
        export_manifest[name] = {"expected": len(rows), "collected": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (exports_dir / "manifest.json").write_text(json.dumps(export_manifest), encoding="utf-8")
    source_hashes_before = {name: metadata["sha256"] for name, metadata in export_manifest.items()}

    expected_responses = {}
    for endpoint in ENDPOINTS:
        outputs = copy.deepcopy(_responses()[endpoint])
        if endpoint == "worldcup-get-schedule":
            outputs["schedule"] = CONNECTOR.normalize_schedule({"params": {"events": [canary_event], "team": "Brazil", "limit": 100}})["data"]
        if endpoint == "worldcup-get-match-forecast":
            outputs["forecast"] = forecasts[0]["value"]
        if endpoint == "worldcup-get-player-performance-context":
            outputs["player_performance_context"]["player"]["player_id"] = TOOL.CANARY_PLAYER_ID
        if endpoint == "worldcup-get-standings":
            outputs["standings"] = {
                "group_count": 12,
                "groups": [
                    {"group": f"Group {index}", "table": [{"team_id": index * 4 + offset} for offset in range(4)]}
                    for index in range(12)
                ],
                "third_place_ranking": [{"team_id": index} for index in range(12)],
                "source": "api-football",
            }
        outputs["workflow-status"] = "executed"
        request = copy.deepcopy(_request(endpoint))
        execution = {
            "_id": f"execution:{endpoint}", "name": endpoint, "status": "executed",
            "date": "synthetic capture label, not temporal scope evidence",
            "request_data": {"context-workflow": request},
            "workflow_output": {"outputs": outputs},
        }
        (executions_dir / f"{endpoint}.json").write_text(json.dumps(execution), encoding="utf-8")
        expected_responses[endpoint] = {key: value for key, value in outputs.items() if key != "workflow-status"}

    manifest_path = tmp_path / "captured-manifest.json"
    bundle_path = tmp_path / "captured-bundle.json"
    assert TOOL.main([
        "capture", "--executions", str(executions_dir), "--exports", str(exports_dir),
        "--manifest-output", str(manifest_path), "--output", str(bundle_path), "--write",
    ]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["count"] == 11
    assert summary["canonical_event_count"] == 104
    assert summary["publication_ready"] is False
    manifest = json.loads(manifest_path.read_text())
    bundle = json.loads(bundle_path.read_text())
    assert TOOL.verify_bundle(bundle, manifest) == {"verified": True, "count": 11, "unique_identity_count": 11}
    by_endpoint = {row["value"]["endpoint"]: row["value"] for row in bundle["documents"]}
    for endpoint, expected in expected_responses.items():
        actual = by_endpoint[endpoint]
        if endpoint == "worldcup-get-schedule":
            assert actual["response"]["schedule"]["count"] == 104
        else:
            assert actual["response"] == expected
        assert actual["response_sha256"] == CONNECTOR._archive_sha256(actual["response"])
        assert actual["subject_sha256"] == CONNECTOR._archive_sha256(actual["subject"])
    assert {
        name: hashlib.sha256((exports_dir / f"{name.replace(':', '-')}.json").read_bytes()).hexdigest()
        for name in exports
    } == source_hashes_before
    assert all(
        source.get("temporal_scope") != "synthetic capture label, not temporal scope evidence"
        for entry in manifest["entries"]
        for source in entry["source_manifest"]
    )

    spotlight_path = executions_dir / "worldcup-player-spotlight.json"
    mismatched = json.loads(spotlight_path.read_text())
    mismatched["workflow_output"]["outputs"]["player_urn"] = "urn:player:mismatch"
    spotlight_path.write_text(json.dumps(mismatched), encoding="utf-8")
    with pytest.raises(TOOL.ArchivePreparationError, match="execution identity mismatch"):
        TOOL.capture_canary_manifest(executions_dir, exports_dir)
