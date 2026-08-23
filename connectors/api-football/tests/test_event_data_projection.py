"""Contract tests for connector-owned API-Football event-data projections."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import yaml


CONNECTOR_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "event-data.json"
MODULE_PATH = CONNECTOR_ROOT / "api-football-event-data.py"
DOCUMENT_NAMES = {
    "api-football-event-actions",
    "api-football-event-lineups",
    "api-football-event-team-statistics",
    "api-football-event-player-statistics",
    "api-football-event-head-to-head",
}
METADATA = {
    "event_code": "urn:machina:sports:event:test-7001",
    "source_event_id": "7001",
    "observed_at": "2026-08-22T20:01:02+00:00",
    "rights": {
        "data_class": "licensed-provider-data",
        "commercial_use": True,
    },
    "provenance": {
        "provider": {"namespace": "api-football", "family": "licensed"},
        "source_refs": [
            {"kind": "endpoint-class", "value": "api-football/fixtures"}
        ],
    },
}


def load_payload():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def load_projector():
    spec = importlib.util.spec_from_file_location("api_football_event_data", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project(payload=None, **overrides):
    source = deepcopy(payload or load_payload())
    params = {**source, **METADATA, **overrides}
    return load_projector().project_event_data({"params": params})


def documents_by_name(result):
    return {document["name"]: document for document in result["data"]["documents"]}


def test_projects_all_stable_documents_with_typed_values_and_metadata():
    result = project()

    assert result["status"] is True
    assert result["data"]["valid"] is True
    documents = documents_by_name(result)
    assert set(documents) == DOCUMENT_NAMES
    assert all(document["key"] == METADATA["event_code"] for document in documents.values())
    for document in documents.values():
        value = document["value"]
        assert value["@id"].startswith("urn:machina:sports:projection:")
        assert value["@type"].startswith("sport:")
        assert value["event_code"] == METADATA["event_code"]
        assert value["source_event_id"] == METADATA["source_event_id"]
        assert value["provider_fixture_id"] == 7001
        assert value["observed_at"] == METADATA["observed_at"]
        assert value["rights"] == METADATA["rights"]
        assert value["provenance"] == METADATA["provenance"]
        assert value["capability"]["status"] == "available"


def test_action_ids_are_deterministic_and_duplicate_provider_rows_are_idempotent():
    first = documents_by_name(project())["api-football-event-actions"]["value"]
    second = documents_by_name(project())["api-football-event-actions"]["value"]

    assert len(first["facts"]) == 1
    assert first["facts"] == second["facts"]
    action = first["facts"][0]
    assert first["event_id"] == (
        "urn:machina:sports:event:5043c6f7424d8349f1c23dccb9330f71"
    )
    assert action["@type"] == "sport:Action"
    assert action["@id"] == (
        "urn:machina:sports:action:a2fd5a2434548bcce25f82730c0b15b7"
    )
    assert action["event_id"] == first["event_id"]
    assert action["team_id"] == (
        "urn:machina:sports:team:4e3e02dd45a99f90e5947e30ff2ae6e5"
    )
    assert action["player_id"] == (
        "urn:machina:sports:player:be8b65b0fa28f9fca2dde6afe07286a7"
    )
    assert action["provider_assist_player_id"] == 102
    assert action["assist_player_id"].startswith("urn:machina:sports:player:")
    assert action["facts"]["time"] == {"elapsed": 25, "extra": None}


def test_real_lineups_bind_players_to_exact_fixture_teams():
    value = documents_by_name(project())["api-football-event-lineups"]["value"]

    assert value["capability"] == {"name": "event.lineups", "status": "available"}
    assert [lineup["provider_team_id"] for lineup in value["facts"]] == [40, 47]
    assert value["facts"][0]["starting"][0]["provider_player_id"] == 101
    assert value["facts"][0]["starting"][0]["player_id"].startswith(
        "urn:machina:sports:player:"
    )


def test_fixture_team_and_player_statistics_keep_provider_facts_and_canonical_ids():
    documents = documents_by_name(project())
    teams = documents["api-football-event-team-statistics"]["value"]["facts"]
    players = documents["api-football-event-player-statistics"]["value"]["facts"]

    assert [row["provider_team_id"] for row in teams] == [40, 47]
    assert teams[0]["statistics"] == [{"type": "Shots on Goal", "value": 3}]
    assert players[0]["players"][0]["provider_player_id"] == 101
    assert players[0]["players"][0]["statistics"] == [
        {"games": {"minutes": 31}, "goals": {"total": 1}}
    ]


def test_zero_results_and_provider_errors_are_explicitly_unavailable():
    payload = load_payload()
    for key in ("events", "lineups", "team_statistics", "player_statistics", "head_to_head"):
        payload[key] = {
            "parameters": payload[key]["parameters"],
            "errors": [],
            "results": 0,
            "response": [],
        }
    payload["events"]["errors"] = {"requests": "daily limit reached"}

    result = project(payload)

    assert result["status"] is True
    assert result["data"]["workflow_status"] == "unavailable"
    for document in documents_by_name(result).values():
        assert document["value"]["facts"] == []
        assert document["value"]["capability"]["status"] == "unavailable"
    assert "event.actions" in result["data"]["requirements_unavailable"]


def test_partial_coverage_never_reports_executed():
    payload = load_payload()
    payload["lineups"] = {
        "parameters": {"fixture": "7001"},
        "errors": [],
        "results": 0,
        "response": [],
    }

    result = project(payload)

    assert result["data"]["workflow_status"] == "partial"
    assert documents_by_name(result)["api-football-event-lineups"]["value"][
        "capability"
    ]["status"] == "unavailable"


def test_squad_rosters_never_create_lineup_facts_or_capability():
    payload = load_payload()
    payload["fixture"]["rosters"] = payload["lineups"]["response"]
    payload["lineups"] = {
        "parameters": {"fixture": "7001"},
        "errors": [],
        "results": 0,
        "response": [],
    }

    lineup = documents_by_name(project(payload))["api-football-event-lineups"]["value"]

    assert lineup["facts"] == []
    assert lineup["capability"] == {"name": "event.lineups", "status": "unavailable"}


def test_h2h_rejects_any_fixture_outside_the_exact_provider_team_pair():
    payload = load_payload()
    payload["head_to_head"]["response"][1]["teams"]["away"]["id"] = 99

    h2h = documents_by_name(project(payload))["api-football-event-head-to-head"]["value"]

    assert h2h["facts"] == []
    assert h2h["capability"]["status"] == "unavailable"
    assert "exact fixture team pair" in h2h["unavailable_reason"]


def test_mismatched_fixture_or_endpoint_identity_fails_closed():
    assert project(source_event_id="9999")["status"] is False
    assert project(provenance={})["status"] is False

    payload = load_payload()
    payload["events"]["parameters"]["fixture"] = "9999"
    result = project(payload)
    actions = documents_by_name(result)["api-football-event-actions"]["value"]
    assert actions["capability"]["status"] == "unavailable"
    assert actions["facts"] == []


def test_connector_workflow_installer_and_agent_orchestration_contracts():
    declaration = yaml.safe_load(
        (CONNECTOR_ROOT / "api-football-event-data.yml").read_text(encoding="utf-8")
    )["connector"]
    workflow = yaml.safe_load(
        (CONNECTOR_ROOT / "api-football-enrich-event-data.yml").read_text(encoding="utf-8")
    )["workflow"]
    tasks = {task["name"]: task for task in workflow["tasks"]}

    assert declaration["filename"] == "api-football-event-data.py"
    assert {command["value"] for command in declaration["commands"]} == {
        "project_event_data"
    }
    assert workflow["name"] == "api-football-enrich-event-data"
    assert tasks["fetch-fixture"]["connector"]["command"] == "get-fixtures"
    assert tasks["fetch-events"]["connector"]["command"] == "get-fixtures/events"
    assert tasks["fetch-lineups"]["connector"]["command"] == "get-fixtures/lineups"
    assert tasks["fetch-team-statistics"]["connector"]["command"] == "get-fixtures/statistics"
    assert tasks["fetch-player-statistics"]["connector"]["command"] == "get-fixtures/players"
    assert tasks["fetch-head-to-head"]["connector"]["command"] == "get-fixtures/headtohead"
    assert tasks["fetch-head-to-head"]["inputs"]["last"] == 5
    saves = {
        "save-actions": "api-football-event-actions",
        "save-lineups": "api-football-event-lineups",
        "save-team-statistics": "api-football-event-team-statistics",
        "save-player-statistics": "api-football-event-player-statistics",
        "save-head-to-head": "api-football-event-head-to-head",
    }
    for task_name, document_name in saves.items():
        save = tasks[task_name]
        assert save["config"]["action"] == "bulk-update"
        assert save["document_name"] == repr(document_name)
        assert document_name in save["documents"]["items"]
        assert "projection-valid" in save["condition"]

    install = yaml.safe_load((CONNECTOR_ROOT / "_install.yml").read_text(encoding="utf-8"))
    entries = {(item["type"], item["path"]) for item in install["datasets"]}
    assert ("connector", "api-football-event-data.yml") in entries
    assert ("workflow", "api-football-enrich-event-data.yml") in entries

    for path in ("agents/event-prelive-update.yml", "agents/event-live-update.yml"):
        agent = yaml.safe_load((CONNECTOR_ROOT / path).read_text(encoding="utf-8"))["agent"]
        names = [item["name"] for item in agent["workflows"]]
        assert names.count("api-football-enrich-event-data") == 1
        assert names.index("api-football-enrich-event-data") == names.index(
            "api-football-event-synchronize"
        ) + 1
        enrichment = next(
            item for item in agent["workflows"]
            if item["name"] == "api-football-enrich-event-data"
        )
        assert "event-synchronize-status" in enrichment["condition"]


def test_consumers_use_nested_sorter_arrays_and_legacy_workflows_do_not_false_execute():
    for path in ("workflows/event-consumer-prelive.yml", "workflows/event-consumer-live.yml"):
        workflow = yaml.safe_load((CONNECTOR_ROOT / path).read_text(encoding="utf-8"))["workflow"]
        schedule = next(task for task in workflow["tasks"] if task["name"] == "load-event-by-schedule")
        assert all(isinstance(sorter, list) and len(sorter) == 2 for sorter in schedule["config"]["search-sorters"])

    for path in (
        "sync-fixtures-events.yml",
        "sync-fixtures-teams-statistics.yml",
        "sync-fixtures-players-statistics.yml",
    ):
        workflow = yaml.safe_load((CONNECTOR_ROOT / path).read_text(encoding="utf-8"))["workflow"]
        assert workflow["outputs"]["workflow-status"] != "'executed'"
        fetch = next(task for task in workflow["tasks"] if task["type"] == "connector")
        assert any("provider-response-valid" in key for key in fetch["outputs"])

    team_stats = yaml.safe_load(
        (CONNECTOR_ROOT / "sync-fixtures-teams-statistics.yml").read_text(encoding="utf-8")
    )["workflow"]
    fetch = next(task for task in team_stats["tasks"] if task["type"] == "connector")
    assert "[0]" not in fetch["outputs"]["fixture-team-home-name"]
    assert "[1]" not in fetch["outputs"]["fixture-team-away-name"]
