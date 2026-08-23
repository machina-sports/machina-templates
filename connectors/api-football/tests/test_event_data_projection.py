"""Contract tests for connector-owned API-Football event-data projections."""

from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re

import yaml


CONNECTOR_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "event-data.json"
MODULE_PATH = CONNECTOR_ROOT / "api-football-event-data.py"
EVENT_CODE = "urn:machina:sports:event:canonical-7001"
HOME_TEAM_ID = "urn:machina:sports:team:canonical-home"
AWAY_TEAM_ID = "urn:machina:sports:team:canonical-away"
DOCUMENT_NAMES = {
    "api-football-event-actions",
    "api-football-event-lineups",
    "api-football-event-team-statistics",
    "api-football-event-player-statistics",
    "api-football-event-head-to-head",
}
ENDPOINTS = {
    "api-football-event-actions": "api-football/fixtures/events",
    "api-football-event-lineups": "api-football/fixtures/lineups",
    "api-football-event-team-statistics": "api-football/fixtures/statistics",
    "api-football-event-player-statistics": "api-football/fixtures/players",
    "api-football-event-head-to-head": "api-football/fixtures/headtohead",
}
OBSERVED_AT = {
    "events": "2026-08-22T20:01:01+00:00",
    "lineups": "2026-08-22T20:01:02+00:00",
    "team_statistics": "2026-08-22T20:01:03+00:00",
    "player_statistics": "2026-08-22T20:01:04+00:00",
    "head_to_head": "2026-08-22T20:01:05+00:00",
}
REQUEST_CONTEXTS = {
    "fixture": {"id": "7001"},
    "events": {"fixture": "7001"},
    "lineups": {"fixture": "7001"},
    "team_statistics": {"fixture": "7001"},
    "player_statistics": {"fixture": "7001"},
    "head_to_head": {"h2h": "40-47", "last": 5},
}
LOCAL_URN_RE = re.compile(
    r"^urn:machina:sports:[a-z][a-z0-9_-]*:x[0-9a-f]{32}$"
)
METADATA = {
    "source_event_document_id": "document-7001",
    "provider_fixture_id": "7001",
    "event_view": {
        "event_id": EVENT_CODE,
        "participants": [
            {"id": HOME_TEAM_ID, "role": "home", "name": "Home FC"},
            {"id": AWAY_TEAM_ID, "role": "away", "name": "Away FC"},
        ],
    },
    "provider_ids": [
        {
            "entity_type": "event",
            "provider_namespace": "api-football",
            "provider_id": "7001",
            "machina_id": EVENT_CODE,
        },
        {
            "entity_type": "team",
            "provider_namespace": "api-football",
            "provider_id": "40",
            "machina_id": HOME_TEAM_ID,
        },
        {
            "entity_type": "team",
            "provider_namespace": "api-football",
            "provider_id": "47",
            "machina_id": AWAY_TEAM_ID,
        },
    ],
    "source_event_rights": {
        "data_class": "licensed-provider-data",
        "commercial_use": True,
    },
    "source_event_provenance": {
        "provider": {"namespace": "api-football", "family": "licensed"},
        "source_refs": [{"kind": "endpoint-class", "value": "api-football/fixtures"}],
    },
    "endpoint_observed_at": OBSERVED_AT,
    "request_contexts": REQUEST_CONTEXTS,
}


def load_payload():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def load_projector():
    spec = importlib.util.spec_from_file_location("api_football_event_data", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resolve_provider_fixture_id(event_value):
    return load_projector().resolve_provider_fixture_id(
        {"params": {"event_document_value": event_value}}
    )


def canonical_event_value(provider_ids=None):
    return {
        "@id": EVENT_CODE,
        "machina_sports_schema": {
            "event_view": {"event_id": EVENT_CODE},
            "provider_ids": deepcopy(
                METADATA["provider_ids"] if provider_ids is None else provider_ids
            ),
        },
    }


def project(payload=None, **overrides):
    source = deepcopy(payload or load_payload())
    fixture = source.pop("fixture")
    fixture_envelope = {
        "get": "fixtures",
        "parameters": {"id": "7001"},
        "errors": [],
        "results": 1,
        "paging": {"current": 1, "total": 1},
        "response": [fixture],
    }
    params = {
        **source,
        "fixture_envelope": fixture_envelope,
        **deepcopy(METADATA),
        **overrides,
    }
    return load_projector().project_event_data({"params": params})


def documents_by_name(result):
    return {document["name"]: document for document in result["data"]["documents"]}


def contains_jsonld_type(value):
    if isinstance(value, dict):
        return "@type" in value or any(contains_jsonld_type(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_jsonld_type(item) for item in value)
    return False


def machina_urns(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from machina_urns(item)
    elif isinstance(value, list):
        for item in value:
            yield from machina_urns(item)
    elif isinstance(value, str) and value.startswith("urn:machina:sports:"):
        yield value


def test_local_urn_uses_canonical_provider_scoped_bytes_and_tuple_boundaries():
    projector = load_projector()

    api_football_id = projector._urn("action", "provider-event", "provider-action-a")
    assert api_football_id == (
        "urn:machina:sports:action:x192c7d20a468c4ac36233abd075a5df0"
    )
    assert projector._urn("participation", EVENT_CODE, HOME_TEAM_ID, 101) == (
        "urn:machina:sports:participation:xab3d84005871fc26254872d7d93a1a27"
    )
    assert projector._urn("test", "a", "b\x1fc") != projector._urn(
        "test", "a\x1fb", "c"
    )
    projector.PROVIDER = "other-provider"
    assert projector._urn("action", "provider-event", "provider-action-a") != (
        api_football_id
    )


def test_every_emitted_local_machina_urn_is_visibly_marked():
    result = project()
    durable_ids = {EVENT_CODE, HOME_TEAM_ID, AWAY_TEAM_ID}
    emitted_urns = set(machina_urns(result["data"]["documents"]))
    local_urns = emitted_urns - durable_ids

    assert durable_ids <= emitted_urns
    assert local_urns
    assert all(LOCAL_URN_RE.fullmatch(value) for value in local_urns)
    assert {value.split(":")[3] for value in local_urns} == {
        "action",
        "head-to-head-observation",
        "lineup",
        "participation",
        "player-statistics",
        "projection",
        "team-statistics",
    }


def test_resolves_provider_fixture_id_from_one_matching_canonical_crosswalk_entry():
    result = resolve_provider_fixture_id(canonical_event_value())

    assert result["status"] is True
    assert result["data"]["provider_fixture_id"] == 7001


def test_non_integer_canonical_event_provider_id_fails_closed():
    for provider_id in (EVENT_CODE, "7001.0", 0, -1, True):
        provider_ids = deepcopy(METADATA["provider_ids"])
        provider_ids[0]["provider_id"] = provider_id

        result = resolve_provider_fixture_id(canonical_event_value(provider_ids))

        assert result["status"] is False
        assert result["data"] == {}


def test_missing_canonical_event_crosswalk_entry_fails_closed():
    provider_ids = [
        entry
        for entry in METADATA["provider_ids"]
        if entry["entity_type"] != "event"
    ]
    result = resolve_provider_fixture_id(canonical_event_value(provider_ids))

    assert result["status"] is False
    assert result["data"] == {}


def test_duplicate_canonical_event_crosswalk_entries_fail_closed():
    provider_ids = deepcopy(METADATA["provider_ids"])
    provider_ids.append(deepcopy(provider_ids[0]))
    result = resolve_provider_fixture_id(canonical_event_value(provider_ids))

    assert result["status"] is False
    assert result["data"] == {}


def test_mismatched_canonical_event_crosswalk_entry_fails_closed():
    provider_ids = deepcopy(METADATA["provider_ids"])
    provider_ids[0]["machina_id"] = "urn:machina:sports:event:different"
    result = resolve_provider_fixture_id(canonical_event_value(provider_ids))

    assert result["status"] is False
    assert result["data"] == {}


def test_projects_stable_internal_documents_from_the_source_canonical_event():
    result = project()

    assert result["status"] is True
    assert result["data"]["valid"] is True
    assert result["data"]["event_id"] == EVENT_CODE
    documents = documents_by_name(result)
    assert set(documents) == DOCUMENT_NAMES
    assert len({document["key"] for document in documents.values()}) == 5
    for document in documents.values():
        value = document["value"]
        metadata = document["metadata"]
        assert document["_id"] == document["key"] == metadata["projection_key"]
        assert value["@id"] == document["key"]
        assert value["schema_version"] == "api-football-event-projection/2"
        assert value["event_code"] == value["event_id"] == EVENT_CODE
        assert value["source_event_document_id"] == "document-7001"
        assert value["provider_fixture_id"] == 7001
        assert not contains_jsonld_type(value)
        assert metadata["projection_capability"]["name"].startswith(
            "internal.api-football."
        )
        assert metadata["projection_capability"]["status"] == "available"
        assert "capability" not in metadata


def test_projection_identity_proves_rerun_replaces_one_document():
    first = documents_by_name(project())["api-football-event-actions"]
    changed_payload = load_payload()
    changed_payload["events"]["response"][0]["comments"] = "corrected"
    second = documents_by_name(project(changed_payload))["api-football-event-actions"]

    assert first["key"] == second["key"]
    def identity(doc):
        return (
            doc["metadata"]["projection_key"],
            doc["metadata"]["source_event_document_id"],
            doc["metadata"]["event_code"],
            doc["name"],
        )
    store = {}
    store[identity(first)] = first
    store[identity(second)] = second
    assert len(store) == 1
    assert next(iter(store.values()))["value"]["facts"][0]["provider_facts"][
        "comments"
    ] == "corrected"


def test_canonical_team_ids_are_selected_only_by_exact_provider_crosswalk():
    documents = documents_by_name(project())
    actions = documents["api-football-event-actions"]["value"]["facts"]
    lineups = documents["api-football-event-lineups"]["value"]["facts"]
    team_stats = documents["api-football-event-team-statistics"]["value"]["facts"]
    h2h = documents["api-football-event-head-to-head"]["value"]["facts"]

    assert {fact["team_id"] for fact in actions} == {HOME_TEAM_ID}
    assert [fact["team_id"] for fact in lineups] == [HOME_TEAM_ID, AWAY_TEAM_ID]
    assert [fact["team_id"] for fact in team_stats] == [HOME_TEAM_ID, AWAY_TEAM_ID]
    assert h2h[0]["home_team_id"] == HOME_TEAM_ID
    assert h2h[0]["away_team_id"] == AWAY_TEAM_ID

    bad_crosswalk = deepcopy(METADATA["provider_ids"])
    bad_crosswalk[1]["machina_id"] = AWAY_TEAM_ID
    assert project(provider_ids=bad_crosswalk)["status"] is False


def test_players_use_event_scoped_participation_without_claiming_durable_identity():
    document = documents_by_name(project())["api-football-event-player-statistics"]
    player = document["value"]["facts"][0]["players"][0]

    assert player["provider_player_id"] == 101
    assert player["identity_scope"] == "event-participation"
    assert player["participation_id"].startswith("urn:machina:sports:participation:")
    assert player["@id"] == player["participation_id"]
    assert "player_id" not in player
    assert "canonical_athlete_id" not in player

    crosswalk = deepcopy(METADATA["provider_ids"])
    crosswalk.append({
        "entity_type": "athlete",
        "provider_namespace": "api-football",
        "provider_id": "101",
        "machina_id": "urn:machina:sports:athlete:canonical-101",
    })
    mapped = documents_by_name(project(provider_ids=crosswalk))[
        "api-football-event-player-statistics"
    ]["value"]["facts"][0]["players"][0]
    assert mapped["canonical_athlete_id"] == "urn:machina:sports:athlete:canonical-101"
    assert mapped["participation_id"] == player["participation_id"]


def test_action_ids_use_provider_id_or_response_ordinal_and_keep_same_minute_actions():
    first = documents_by_name(project())["api-football-event-actions"]["value"]["facts"]
    assert len(first) == 2
    assert len({action["@id"] for action in first}) == 2
    assert [action["provider_response_ordinal"] for action in first] == [0, 1]

    relabeled = load_payload()
    relabeled["events"]["response"][0]["type"] = "VAR"
    relabeled["events"]["response"][0]["detail"] = "Label corrected"
    second = documents_by_name(project(relabeled))["api-football-event-actions"]["value"]["facts"]
    assert [action["@id"] for action in first] == [action["@id"] for action in second]

    with_provider_ids = load_payload()
    with_provider_ids["events"]["response"][0]["id"] = "provider-action-a"
    with_provider_ids["events"]["response"][1]["id"] = "provider-action-b"
    original = documents_by_name(project(with_provider_ids))[
        "api-football-event-actions"
    ]["value"]["facts"]
    with_provider_ids["events"]["response"].reverse()
    reordered = documents_by_name(project(with_provider_ids))[
        "api-football-event-actions"
    ]["value"]["facts"]
    assert {item["provider_event_id"]: item["@id"] for item in original} == {
        item["provider_event_id"]: item["@id"] for item in reordered
    }


def test_exact_connector_envelope_is_preserved_and_request_context_is_separate():
    payload = load_payload()
    payload["events"].pop("parameters")
    payload["events"]["provider_extension"] = {"unchanged": True}

    actions = documents_by_name(project(payload))["api-football-event-actions"]["value"]
    assert actions["provider_envelope"] == payload["events"]
    assert "parameters" not in actions["provider_envelope"]
    assert actions["request_context"] == {"fixture": "7001"}

    bad_contexts = deepcopy(REQUEST_CONTEXTS)
    bad_contexts["events"] = {"fixture": "9999"}
    unavailable = documents_by_name(project(payload, request_contexts=bad_contexts))[
        "api-football-event-actions"
    ]
    assert unavailable["value"]["facts"] == []
    assert unavailable["metadata"]["status"] == "unavailable"


def test_endpoint_provenance_rights_and_empty_endpoint_contracts_are_explicit():
    documents = documents_by_name(project())
    source_keys = {
        "api-football-event-actions": "events",
        "api-football-event-lineups": "lineups",
        "api-football-event-team-statistics": "team_statistics",
        "api-football-event-player-statistics": "player_statistics",
        "api-football-event-head-to-head": "head_to_head",
    }
    for name, document in documents.items():
        metadata = document["metadata"]
        refs = metadata["provenance"]["source_refs"]
        assert refs[0] == {"kind": "endpoint-class", "value": ENDPOINTS[name]}
        assert refs[1] == {"kind": "source-event-document", "value": "document-7001"}
        assert metadata["observed_at"] == OBSERVED_AT[source_keys[name]]
        assert metadata["provenance"]["observed_at"] == metadata["observed_at"]
        assert metadata["rights"]["terms"] == METADATA["source_event_rights"]
        assert metadata["rights"]["source_event_rights_ref"] == {
            "kind": "source-event-document",
            "value": "document-7001",
            "path": "value.machina_sports_schema.rights",
        }

    payload = load_payload()
    for key in ("events", "lineups", "team_statistics", "player_statistics", "head_to_head"):
        payload[key] = {
            "parameters": payload[key]["parameters"],
            "errors": [],
            "results": 0,
            "response": [],
        }
    result = project(payload)
    assert result["data"]["workflow_status"] == "unavailable"
    for document in documents_by_name(result).values():
        assert document["value"]["facts"] == []
        assert document["value"]["provider_envelope"]["response"] == []
        assert document["metadata"]["status"] == "unavailable"
        assert document["metadata"]["projection_capability"]["status"] == "unavailable"


def test_h2h_and_mismatched_endpoint_identity_fail_closed():
    payload = load_payload()
    payload["head_to_head"]["response"][1]["teams"]["away"]["id"] = 99
    h2h = documents_by_name(project(payload))["api-football-event-head-to-head"]
    assert h2h["value"]["facts"] == []
    assert "exact fixture team pair" in h2h["value"]["unavailable_reason"]

    payload = load_payload()
    payload["events"]["parameters"]["fixture"] = "9999"
    actions = documents_by_name(project(payload))["api-football-event-actions"]
    assert actions["value"]["facts"] == []
    assert actions["metadata"]["status"] == "unavailable"


def test_missing_canonical_inputs_and_mismatched_fixture_fail_closed():
    assert project(provider_fixture_id="9999")["status"] is False
    assert project(source_event_document_id=None)["status"] is False
    assert project(event_view={})["status"] is False
    assert project(provider_ids=[])["status"] is False


def test_connector_workflow_installer_and_upsert_contracts():
    declaration = yaml.safe_load(
        (CONNECTOR_ROOT / "api-football-event-data.yml").read_text(encoding="utf-8")
    )["connector"]
    workflow = yaml.safe_load(
        (CONNECTOR_ROOT / "api-football-enrich-event-data.yml").read_text(encoding="utf-8")
    )["workflow"]
    tasks = {task["name"]: task for task in workflow["tasks"]}

    assert declaration["filename"] == "api-football-event-data.py"
    assert {command["value"] for command in declaration["commands"]} == {
        "project_event_data",
        "resolve_provider_fixture_id",
    }
    resolver = tasks["resolve-provider-fixture-id"]
    assert resolver["type"] == "connector"
    assert resolver["connector"] == {
        "name": "api-football-event-data",
        "command": "resolve_provider_fixture_id",
    }
    assert resolver["inputs"] == {
        "event_document_value": "$.get('event-value', {})"
    }
    assert "iptc_schema_events" not in resolver["inputs"]
    assert tasks["fetch-fixture"]["connector"]["command"] == "get-fixtures"
    assert tasks["fetch-events"]["connector"]["command"] == "get-fixtures/events"
    assert tasks["fetch-lineups"]["connector"]["command"] == "get-fixtures/lineups"
    assert tasks["fetch-team-statistics"]["connector"]["command"] == "get-fixtures/statistics"
    assert tasks["fetch-player-statistics"]["connector"]["command"] == "get-fixtures/players"
    assert tasks["fetch-head-to-head"]["connector"]["command"] == "get-fixtures/headtohead"

    for task_name in (
        "fetch-fixture",
        "fetch-events",
        "fetch-lineups",
        "fetch-team-statistics",
        "fetch-player-statistics",
        "fetch-head-to-head",
    ):
        envelope_output = next(
            value
            for key, value in tasks[task_name]["outputs"].items()
            if key.endswith("envelope")
        )
        assert envelope_output == "dict($.items())"
        assert "parameters" not in envelope_output
        assert "errors" not in envelope_output
        assert "results" not in envelope_output

    projection_inputs = tasks["project-event-data"]["inputs"]
    assert projection_inputs["event_view"] == "$.get('event-view', {})"
    assert projection_inputs["provider_ids"] == "$.get('provider-crosswalk', [])"
    assert "request_contexts" in projection_inputs
    assert "source_event_rights" in projection_inputs

    saves = {
        "save-actions": "api-football-event-actions",
        "save-lineups": "api-football-event-lineups",
        "save-team-statistics": "api-football-event-team-statistics",
        "save-player-statistics": "api-football-event-player-statistics",
        "save-head-to-head": "api-football-event-head-to-head",
    }
    for task_name, document_name in saves.items():
        save = tasks[task_name]
        assert save["config"]["action"] == "update"
        assert set(save["filters"]) == {
            "name",
            "metadata.projection_key",
            "metadata.source_event_document_id",
            "metadata.event_code",
        }
        assert save["filters"]["name"] == repr(document_name)
        assert set(save["documents"]) == {document_name}
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
