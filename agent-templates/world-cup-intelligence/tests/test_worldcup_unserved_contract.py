"""Unserved archive responses must say WHY (reason_code) and never masquerade
as a missing archive row when the request simply did not identify anything.

Background: on 2026-09-16 ZeroClick called get-squads / get-injuries /
get-player-performance-context with an empty body (the published spec listed
no request fields). The workflows answered `capability_status: unavailable`,
`missing_capabilities: ["archived_response"]` and "No world-cup-2026-final-v3
archive row is available…" — and the gateway billed it. These tests pin the
corrected contract; the gateway maps reason_code -> HTTP 400/404/503.
"""

from __future__ import annotations

import copy

import pytest

from test_worldcup_archive_serving import (
    CONNECTOR,
    EVENT,
    EVENT_URN,
    _document,
    _request,
    execute_yaml,
)

V3 = CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION
SECOND_EVENT = copy.deepcopy(EVENT)
SECOND_EVENT.update({
    "_id": "urn:machina:sport:soccer:event:brazil-vs-scotland:20260619:wor",
    "name": "Brazil vs Scotland - FIFA World Cup 2026",
    "schema:startDate": "2026-06-19T18:00:00Z",
    "provider_ids": {"api_football": "1489430"},
})
SECOND_EVENT["sport:competitors"] = [
    {"@id": "urn:machina:sport:soccer:team:brazil:bra", "name": "Brazil", "sport:qualifier": "home"},
    {"@id": "urn:machina:sport:soccer:team:scotland:sco", "name": "Scotland", "sport:qualifier": "away"},
]
CANONICAL_EVENTS = [{"name": "worldcup:event", "value": EVENT}, {"name": "worldcup:event", "value": SECOND_EVENT}]


def _serve(endpoint, request, *, documents=(), manifest=(), version=V3, events=CANONICAL_EVENTS):
    return CONNECTOR.serve_final_archive({"params": {
        "endpoint": endpoint,
        "archive_version": version,
        "request": request,
        "documents": list(documents),
        "canonical_events": events,
        "canonical_identities": [],
        "archive_manifest": list(manifest),
    }})["data"]


def _closed(monkeypatch):
    """Pretend the v3 closure is active without rebuilding its hashes."""
    monkeypatch.setattr(
        CONNECTOR, "validate_final_archive_manifest",
        lambda manifest, *, archive_version=V3: ("closed", {"fixture_urns": [EVENT_URN, SECOND_EVENT["_id"]], "archive_document_commitments": {}}, []),
    )


@pytest.mark.parametrize("endpoint", sorted(CONNECTOR.FINAL_ARCHIVE_FIXTURE_ENDPOINTS))
def test_empty_request_is_a_selector_error_not_a_missing_archive_row(monkeypatch, endpoint):
    _closed(monkeypatch)
    result = _serve(endpoint, {})
    assert result["archive_hit"] is False
    assert result["archive_status"] == "unavailable"
    assert result["reason_code"] == "fixture_selector_required"
    coverage = result["response"]["coverage"]
    assert coverage["status"] == "unavailable"
    assert coverage["reason_code"] == "fixture_selector_required"
    assert coverage["accepted_fields"][:3] == ["event_urn", "provider_event_id", "event"]
    assert "fixture selector is required" in coverage["reason"]
    assert "archive row" not in coverage["reason"]
    # A request the caller can fix is not a missing capability of the archive.
    assert result["archive"]["missing_capabilities"] == []
    assert result["archive"]["reason_code"] == "fixture_selector_required"


def test_ambiguous_team_returns_candidates(monkeypatch):
    _closed(monkeypatch)
    result = _serve("worldcup-get-injuries", {"team": "Brazil"})
    assert result["reason_code"] == "fixture_ambiguous"
    urns = sorted(c["event_urn"] for c in result["response"]["candidates"])
    assert urns == sorted([EVENT_URN, SECOND_EVENT["_id"]])
    assert "ambiguous" in result["response"]["coverage"]["reason"]


def test_unknown_fixture_is_not_found(monkeypatch):
    _closed(monkeypatch)
    result = _serve("worldcup-get-squads", {"event": "Brazil vs Narnia"})
    assert result["reason_code"] == "fixture_not_found"
    assert result["response"]["candidates"] == []
    assert result["archive"]["missing_capabilities"] == []


def test_resolved_fixture_without_rows_is_a_genuine_archive_gap(monkeypatch):
    _closed(monkeypatch)
    result = _serve("worldcup-get-injuries", {"event": "Brazil vs Morocco"})
    assert result["archive_status"] == "unavailable"
    assert result["reason_code"] == "archive_row_missing"
    assert result["archive"]["missing_capabilities"] == ["archived_response"]
    assert result["response"]["coverage"]["reason"].startswith(f"No {V3} archive row is available")


def test_migration_mode_keeps_clean_miss_but_labels_it():
    # No closure manifest -> "migration": the legacy task graph may still run,
    # and the label tells the gateway/agent what was wrong with the request.
    result = _serve("worldcup-get-injuries", {}, manifest=[])
    assert result["archive_status"] == "miss"
    assert result["reason_code"] == "fixture_selector_required"


def test_player_performance_requires_a_player_selector():
    endpoint = "worldcup-get-player-performance-context"
    outputs, store, connectors = execute_yaml(endpoint, {"event": "Brazil vs Morocco"}, [_document(endpoint)])
    assert outputs["coverage"]["reason_code"] == "player_selector_required"
    assert "player" in outputs["coverage"]["accepted_fields"]
    # v2 default = migration mode: the legacy graph still answers the clean
    # miss, so `archive` here is the legacy block; the closed-mode shape is
    # covered by the unit tests above.
    assert connectors.external_calls == []


def test_standings_outside_catalog_is_unsupported_parameter():
    result = _serve("worldcup-get-standings", {"league": "39", "season": "2026"})
    assert result["archive_status"] == "unavailable"
    assert result["reason_code"] == "unsupported_parameter"
    assert result["response"]["coverage"]["accepted_fields"] == ["league", "season", "event_urn", "provider_event_id"]


def test_resolve_requires_an_id(monkeypatch):
    _closed(monkeypatch)
    result = _serve("worldcup-resolve", {})
    assert result["reason_code"] == "entity_selector_required"
    assert result["response"]["coverage"]["accepted_fields"] == ["id"]


def test_spotlight_requires_a_player_selector(monkeypatch):
    _closed(monkeypatch)
    result = _serve("worldcup-player-spotlight", {})
    assert result["reason_code"] == "player_selector_required"


@pytest.mark.parametrize(
    ("data_source", "fragment"),
    [("seed", "FIFA-ranking seed prior"), ("blend", "blending"), ("results", "results only")],
)
def test_forecast_hits_explain_data_source(data_source, fragment):
    result = CONNECTOR._final_archive_result(
        "hit",
        response={"forecast": {"data_source": data_source, "confidence": 0.15}},
        row={"response_sha256": "x", "source_manifest_sha256": "y"},
        request_identity={},
        version=V3,
    )["data"]
    notes = result["archive"]["notes"]
    assert any(note.startswith(f"data_source={data_source}") and fragment in note for note in notes)
    assert result["reason_code"] is None


def test_yaml_workflow_surfaces_candidates_and_reason_code_on_ambiguity():
    endpoint = "worldcup-get-injuries"
    outputs, store, connectors = execute_yaml(
        endpoint, {"team": "Brazil"},
        [_document(endpoint), {"name": "worldcup:event", "value": SECOND_EVENT}],
    )
    # v2 default (migration): the miss is clean, but the label and candidates travel with it.
    assert outputs["coverage"]["reason_code"] == "fixture_ambiguous"
    assert len(outputs["candidates"]) == 2
    assert connectors.external_calls == []


def test_yaml_workflow_empty_body_is_labelled():
    endpoint = "worldcup-get-squads"
    outputs, store, connectors = execute_yaml(endpoint, {}, [_document(endpoint)])
    assert outputs["coverage"]["reason_code"] == "fixture_selector_required"
    assert outputs["coverage"]["accepted_fields"][0] == "event_urn"
    assert connectors.external_calls == []
