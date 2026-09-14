"""Offline corpus proof for the World Cup storefront v3 candidate."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError

from test_worldcup_archive_serving import LEGACY_TASKS, execute_yaml


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
ARTIFACTS = REPO / ".local" / "worldcup-storefront-readiness"


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


CONNECTOR = _module("worldcup_storefront_test_connector", ROOT / "worldcup-market-intelligence.py")
ARCHIVE = _module("worldcup_storefront_test_archive", ROOT / "tools" / "worldcup_archive.py")
FIFA = _module("worldcup_storefront_test_fifa", ROOT / "tools" / "worldcup_fifa_reconciliation.py")


@pytest.fixture(scope="module")
def corpus():
    bundle = json.loads((ARTIFACTS / "candidate-bundle-v3.json").read_text(encoding="utf-8"))
    closure = json.loads((ARTIFACTS / "closure-candidate-v3.json").read_text(encoding="utf-8"))
    report = json.loads((ARTIFACTS / "readiness-report.json").read_text(encoding="utf-8"))
    by_endpoint = {endpoint: [] for endpoint in CONNECTOR.FINAL_ARCHIVE_ENDPOINTS}
    for row in bundle["documents"]:
        by_endpoint[row["value"]["endpoint"]].append(row)
    events = {}
    identities = {}
    for rows in by_endpoint.values():
        for row in rows:
            subject = row["value"].get("subject") or {}
            event = subject.get("event") if isinstance(subject.get("event"), dict) else {}
            if event.get("_id"):
                events[event["_id"]] = {"name": "worldcup:event", "value": event}
            entity = subject.get("entity") if isinstance(subject.get("entity"), dict) else {}
            if entity.get("_id"):
                identities[entity["_id"]] = {"name": "worldcup:identity-crosswalk", "value": entity}
            player = subject.get("player") if isinstance(subject.get("player"), dict) else {}
            if player.get("_id"):
                identities[player["_id"]] = {"name": "worldcup:identity-crosswalk", "value": player}
    return {
        "bundle": bundle,
        "closure": closure,
        "report": report,
        "by_endpoint": by_endpoint,
        "events": list(events.values()),
        "identities": list(identities.values()),
        "source_events": json.loads((REPO / ".local/worldcup-bulk/baseline/worldcup-event.json").read_text(encoding="utf-8")),
        "source_identities": json.loads((REPO / ".local/worldcup-bulk/baseline/worldcup-identity-crosswalk.json").read_text(encoding="utf-8")),
    }


def _request(endpoint: str, row: dict) -> dict:
    value = row["value"]
    subject = value["subject"]
    if endpoint == "worldcup-resolve":
        return {"id": subject["key"]}
    if endpoint == "worldcup-get-schedule":
        return {}
    if endpoint in {"worldcup-get-standings", "worldcup-backtest-forecasts"}:
        return {}
    if endpoint == "worldcup-player-spotlight":
        return {"player_id": str(((subject.get("player") or {}).get("provider_ids") or {})["api_football"])}
    if endpoint == "worldcup-get-player-performance-context":
        player = value["response"]["fixture_player_pack"]["players"][0]["player"]
        return {"event_urn": subject["event_urn"], "player_id": str(player["provider_ids"]["api_football"])}
    return {"event_urn": subject["event_urn"]}


def _serve(corpus: dict, endpoint: str, row: dict, request: dict | None = None) -> dict:
    result = CONNECTOR.serve_final_archive({"params": {
        "endpoint": endpoint,
        "archive_version": CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION,
        "request": request if request is not None else _request(endpoint, row),
        "documents": [row],
        "canonical_events": corpus["events"],
        "canonical_identities": corpus["identities"],
        "archive_manifest": corpus["closure"]["documents"],
    }})["data"]
    return result


def _graph_documents(corpus: dict, archive_rows=None) -> tuple:
    rows = corpus["bundle"]["documents"] if archive_rows is None else archive_rows
    return tuple(rows) + tuple(corpus["closure"]["documents"]) + tuple(corpus["source_events"]) + tuple(corpus["source_identities"])


def _execute_v3_graph(corpus: dict, endpoint: str, request: dict, archive_rows=None):
    return execute_yaml(
        endpoint,
        request,
        _graph_documents(corpus, archive_rows),
        include_canonical=False,
        archive_version=CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION,
    )


def _archive_query(store):
    return next(query for query in store.queries if query["name"] == "load-final-archive")


def _schema_validator(spec: dict, schema: dict) -> Draft202012Validator:
    return Draft202012Validator({
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "components": spec["components"],
        **schema,
    })


def test_candidate_counts_hashes_and_v2_compatibility(corpus):
    report = corpus["report"]
    assert report["status"] == "local_candidate_ready_not_published"
    assert report["counts"] == {
        "archive_records": 3296,
        "archived_player_fixture_observations": 5323,
        "backtest_eligible": 98,
        "backtest_excluded_late": 6,
        "backtest_population": 104,
        "distinct_people": 1248,
        "distinct_provider_ids": 1249,
        "endpoints": 11,
        "fixtures": 104,
        "forecast_timing": {"at_or_after_kickoff": 6, "verified_pre_kickoff": 98},
        "injury_evidence": {"recorded_absences": 51, "unavailable": 53},
        "market_timing": {"historical_prematch_quote": 5, "settled_or_late_cache": 96, "unavailable": 3},
        "identity_reconciliation": {
            "accepted_provider_ids": 1249,
            "ambiguous_provider_ids": 0,
            "canonical_birth_date_conflicts": 14,
            "duplicate_provider_aliases": 1,
            "official_people": 1248,
            "provider_ids": 1249,
            "quarantined_identity_mappings": 1,
        },
        "new_reconciled_resolve_rows": 36,
        "observed_squad_teams": 48,
        "official_registration_font_warnings": 15,
        "official_registration_players": 1248,
        "official_registration_teams": 48,
        "official_registration_unknown_clubs": 1,
        "provider_only_players": 0,
        "provider_only_resolve_rows": 0,
        "raw_player_capture_files": 104,
        "raw_player_fixture_observations": 5323,
        "restored_marco_fixtures": ["1489384", "1489403", "1489420", "1567309"],
        "retained_original_editorial_spotlights": 2,
        "spotlights": 1248,
    }
    assert ARCHIVE.verify_bundle(corpus["bundle"])["count"] == 3296
    assert CONNECTOR.validate_final_archive_manifest(
        corpus["closure"]["documents"], archive_version=CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION,
    )[0] == "closed"
    assert corpus["report"]["integrity"]["closure_commitment_count"] == 3296
    assert corpus["report"]["integrity"]["closure_mcp_envelope_bytes"] < 1024 * 1024
    assert CONNECTOR.FINAL_ARCHIVE_VERSION == "world-cup-2026-final-v2"
    assert CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION == "world-cup-2026-final-v3"
    schedule = corpus["by_endpoint"]["worldcup-get-schedule"][0]["value"]
    v2 = CONNECTOR.build_final_archive_document(
        schedule["endpoint"], schedule["subject"], schedule["parameter_identity"],
        schedule["response"], schedule["source_manifest"],
    )
    assert v2["archive_version"] == CONNECTOR.FINAL_ARCHIVE_VERSION


def test_source_files_and_candidate_artifact_hashes_are_exact(corpus):
    report = corpus["report"]
    assert report["source_evidence"]["unchanged"] is True
    assert report["source_evidence"]["file_count"] == 537
    for relative, expected in report["source_evidence"]["sha256"].items():
        if relative == "agent-templates/world-cup-intelligence/docs/openapi.json":
            continue
        assert hashlib.sha256((REPO / relative).read_bytes()).hexdigest() == expected
    for name, expected in report["artifact_sha256"].items():
        if name == "import_openapi":
            continue
        assert hashlib.sha256((REPO / report["artifacts"][name]).read_bytes()).hexdigest() == expected
    assert report["integrity"]["provider_calls"] == 0
    assert report["integrity"]["model_calls"] == 0
    assert report["integrity"]["document_writes"] == 0


def test_all_eleven_candidate_routes_serve_real_rows_with_coverage(corpus):
    assert set(corpus["by_endpoint"]) == CONNECTOR.FINAL_ARCHIVE_ENDPOINTS
    for endpoint, rows in corpus["by_endpoint"].items():
        served = _serve(corpus, endpoint, rows[0])
        assert served["archive_status"] == "hit", (endpoint, served["warnings"])
        coverage = served["response"]["coverage"]
        assert coverage["schema_version"] == "worldcup-storefront-coverage-v1"
        assert coverage["scope"] == "completed_tournament_archive"
        assert coverage["mode"] == "historical"
        assert served["archive"]["version"] == CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION


def test_released_v3_graph_serves_all_routes_and_fails_closed(corpus):
    for endpoint, rows in corpus["by_endpoint"].items():
        request = _request(endpoint, rows[0])
        outputs, store, connectors = _execute_v3_graph(corpus, endpoint, request)
        assert outputs["archive"]["status"] == "hit", (endpoint, outputs["warnings"])
        assert outputs["archive"]["version"] == CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION
        assert store.writes == 0 and connectors.external_calls == []
        query = _archive_query(store)
        assert query["returned"] < query["limit"]
        if endpoint in {"worldcup-resolve", "worldcup-player-spotlight"}:
            assert "value.subject.lookup_keys" in query["filters"]
            assert query["returned"] == 1
            assert sum(len(json.dumps(row, ensure_ascii=False)) for row in query["documents"]) < 1_000_000

        missing, missing_store, missing_connectors = _execute_v3_graph(corpus, endpoint, request, [])
        assert missing["archive"]["status"] == "unavailable"
        assert missing_store.writes == 0 and missing_connectors.external_calls == []

        tampered = copy.deepcopy(rows[0])
        tampered["value"]["response"]["runtime_gate_tamper"] = True
        invalid, invalid_store, invalid_connectors = _execute_v3_graph(corpus, endpoint, request, [tampered])
        assert invalid["archive"]["status"] == "error"
        assert invalid_store.writes == 0 and invalid_connectors.external_calls == []

    standings, store, connectors = _execute_v3_graph(
        corpus, "worldcup-get-standings", {"league": "39", "season": "2026"},
    )
    assert standings["archive"]["status"] == "unavailable"
    assert store.writes == 0 and connectors.external_calls == []
    backtest, store, connectors = _execute_v3_graph(
        corpus, "worldcup-backtest-forecasts", {"competition": "premier-league"},
    )
    assert backtest["archive"]["status"] == "unavailable"
    assert store.writes == 0 and connectors.external_calls == []


def test_released_v3_graph_replays_all_104_fixture_routes(corpus):
    fixture_endpoints = sorted(CONNECTOR.FINAL_ARCHIVE_FIXTURE_ENDPOINTS)
    by_event = {
        endpoint: {row["value"]["subject"]["event_urn"]: row for row in corpus["by_endpoint"][endpoint]}
        for endpoint in fixture_endpoints
    }
    fixture_urns = corpus["closure"]["documents"][0]["value"]["fixture_urns"]
    assert len(fixture_urns) == 104
    for event_urn in fixture_urns:
        for endpoint in fixture_endpoints:
            row = by_event[endpoint][event_urn]
            request = {"event_urn": event_urn}
            if endpoint == "worldcup-get-player-performance-context":
                player = row["value"]["response"]["fixture_player_pack"]["players"][0]["player"]
                request["player_id"] = str(player["provider_ids"]["api_football"])
            outputs, store, connectors = _execute_v3_graph(corpus, endpoint, request)
            assert outputs["archive"]["status"] == "hit", (endpoint, event_urn, outputs["warnings"])
            assert _archive_query(store)["returned"] == 1
            assert store.writes == 0 and connectors.external_calls == []
            if endpoint == "worldcup-get-squads":
                official = outputs["squads"]["official_registration_snapshot"]
                assert len(official["teams"]) == 2
                assert all(len(team["players"]) == 26 for team in official["teams"])


def test_released_v3_graph_uses_corrected_archive_identities_not_legacy_store(corpus):
    qatar_urn = "urn:machina:sport:soccer:player:al-hashmi-al-hussain:20030815:qat"
    mario_urn = "urn:machina:sport:soccer:player:mario-pasalic:19950209:hrv"
    special_ids = (("260865", FIFA.MARCO_URN), ("2763", mario_urn), ("339795", qatar_urn), ("542542", qatar_urn))
    for provider_id, expected_urn in special_ids:
        resolved, store, connectors = _execute_v3_graph(corpus, "worldcup-resolve", {"id": provider_id})
        assert resolved["entity"]["_id"] == expected_urn
        assert _archive_query(store)["returned"] == 1
        assert not any(query["name"] == "load-final-archive-identities" for query in store.queries)
        assert store.writes == 0 and connectors.external_calls == []
        spotlight, store, connectors = _execute_v3_graph(corpus, "worldcup-player-spotlight", {"player_id": provider_id})
        assert spotlight["player_urn"] == expected_urn
        assert _archive_query(store)["returned"] == 1
        assert store.writes == 0 and connectors.external_calls == []

    quarantined, _, connectors = _execute_v3_graph(corpus, "worldcup-resolve", {"id": FIFA.QUARANTINED_MARIO_URN})
    assert quarantined["entity"]["identity_mapping_status"] == "quarantined"
    assert connectors.external_calls == []

    baseline_urns = {
        str(row["value"].get("_id") or row["value"].get("@id") or "")
        for row in corpus["source_identities"]
    }
    new_players = [
        row for row in corpus["by_endpoint"]["worldcup-resolve"]
        if "sport:Player" in (row["value"]["subject"].get("entity", {}).get("@type") or [])
        and row["value"]["subject"]["key"] not in baseline_urns
    ]
    assert len(new_players) == 36
    for row in new_players:
        player_urn = row["value"]["subject"]["key"]
        output, _, connectors = _execute_v3_graph(corpus, "worldcup-resolve", {"id": player_urn})
        assert output["entity"]["_id"] == player_urn
        assert connectors.external_calls == []


def test_released_v3_graph_preserves_player_selector_semantics(corpus):
    spotlights = corpus["by_endpoint"]["worldcup-player-spotlight"]
    selected = spotlights[0]["value"]["subject"]["player"]
    provider_id = str(selected["provider_ids"]["api_football"])
    request = {
        "player_urn": selected["_id"], "player_id": provider_id,
        "player": selected["name"], "team": selected["team"]["name"], "team_id": selected["team_id"],
    }
    output, store, connectors = _execute_v3_graph(corpus, "worldcup-player-spotlight", request)
    assert output["archive"]["status"] == "hit"
    assert 1 <= _archive_query(store)["returned"] < 100
    assert store.writes == 0 and connectors.external_calls == []

    conflicting = dict(request, team="Brazil" if selected["team"]["name"] != "Brazil" else "Morocco")
    output, store, connectors = _execute_v3_graph(corpus, "worldcup-player-spotlight", conflicting)
    assert output["archive"]["status"] == "error"
    assert store.writes == 0 and connectors.external_calls == []

    by_name = {}
    for row in spotlights:
        player = row["value"]["subject"]["player"]
        by_name.setdefault(CONNECTOR._slugify(player["name"]), []).append(player)
    ambiguous_name, players = next((name, players) for name, players in by_name.items() if len(players) > 1)
    output, store, connectors = _execute_v3_graph(
        corpus, "worldcup-player-spotlight", {"player": ambiguous_name.replace("-", " ")},
    )
    assert output["archive"]["status"] == "unavailable"
    assert 1 < _archive_query(store)["returned"] < 100
    assert store.writes == 0 and connectors.external_calls == []


def test_closed_v3_rejects_uncommitted_or_rewritten_rows(corpus):
    original = corpus["by_endpoint"]["worldcup-resolve"][0]["value"]
    entity = copy.deepcopy(original["subject"].get("entity") or original["response"]["entity"])
    entity["_id"] = entity["@id"] = "urn:review:not-in-closure"
    entity["provider_ids"] = {"api_football": "review-not-committed"}
    response = copy.deepcopy(original["response"])
    response.update({"entity": entity, "entities": [entity]})
    extra = {"name": CONNECTOR.FINAL_ARCHIVE_DOCUMENT, "value": CONNECTOR.build_final_archive_document(
        "worldcup-resolve",
        {"key": entity["_id"], "entity": entity, "aliases": ["review-not-committed"]},
        {}, response, original["source_manifest"], archive_version=CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION,
    )}
    result = CONNECTOR.serve_final_archive({"params": {
        "endpoint": "worldcup-resolve", "archive_version": CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION,
        "request": {"id": "review-not-committed"}, "documents": [extra],
        "archive_manifest": corpus["closure"]["documents"],
    }})["data"]
    assert result["archive_status"] == "error"
    assert "not committed" in result["warnings"][0]

    rewritten_response = copy.deepcopy(original["response"])
    rewritten_response["warnings"] = ["self-consistent but not closure-committed"]
    rewritten = {"name": CONNECTOR.FINAL_ARCHIVE_DOCUMENT, "value": CONNECTOR.build_final_archive_document(
        "worldcup-resolve", original["subject"], original["parameter_identity"], rewritten_response,
        original["source_manifest"], archive_version=CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION,
    )}
    assert rewritten["value"]["_id"] == original["_id"]
    result = CONNECTOR.serve_final_archive({"params": {
        "endpoint": "worldcup-resolve", "archive_version": CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION,
        "request": {"id": original["subject"]["key"]}, "documents": [rewritten],
        "archive_manifest": corpus["closure"]["documents"],
    }})["data"]
    assert result["archive_status"] == "error"
    assert "not committed" in result["warnings"][0]


def test_player_request_lookup_is_constant_size_and_aliases_still_resolve(corpus):
    oversized = " ".join(f"word{index}" for index in range(40))
    lookup = CONNECTOR.build_final_archive_lookup({"params": {
        "endpoint": "worldcup-player-spotlight", "request": {"player": oversized},
    }})["data"]
    assert lookup["lookup_keys"] == []
    assert "16-token" in lookup["lookup_error"]
    output, store, connectors = _execute_v3_graph(corpus, "worldcup-player-spotlight", {"player": oversized})
    assert output["archive"]["status"] == "error"
    assert not any(query["name"] == "load-final-archive" for query in store.queries)
    assert store.writes == 0 and connectors.external_calls == []

    multiword = next(
        row["value"]["subject"]["player"] for row in corpus["by_endpoint"]["worldcup-player-spotlight"]
        if len(CONNECTOR._slugify(row["value"]["subject"]["player"]["name"]).split("-")) >= 3
    )
    output, _, connectors = _execute_v3_graph(corpus, "worldcup-player-spotlight", {"player": multiword["name"]})
    assert output["player_urn"] == multiword["_id"]
    assert connectors.external_calls == []

    original = corpus["by_endpoint"]["worldcup-player-spotlight"][0]["value"]
    aliased_player = copy.deepcopy(original["subject"]["player"])
    aliased_player["aliases"] = ["Known Multiword Alias"]
    aliased_subject = {**original["subject"], "player": aliased_player}
    aliased_row = {"name": CONNECTOR.FINAL_ARCHIVE_DOCUMENT, "value": CONNECTOR.build_final_archive_document(
        "worldcup-player-spotlight", aliased_subject, {}, original["response"], original["source_manifest"],
        archive_version=CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION,
    )}
    output = CONNECTOR.serve_final_archive({"params": {
        "endpoint": "worldcup-player-spotlight", "archive_version": CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION,
        "request": {"player": "Known Multiword Alias"}, "documents": [aliased_row],
    }})["data"]
    assert output["archive_status"] == "hit"
    assert output["response"]["player_urn"] == aliased_player["_id"]


@pytest.mark.parametrize(
    ("endpoint", "request_data", "expected_status"),
    [
        ("worldcup-player-spotlight", {"player": " ".join(f"word{index}" for index in range(40))}, "error"),
        ("worldcup-player-spotlight", {}, "unavailable"),
        ("worldcup-match-recap", {}, "unavailable"),
        ("worldcup-match-recap", {"event_urn": "urn:machina:sport:soccer:event:not-in-archive"}, "unavailable"),
    ],
)
def test_editorial_graph_refusals_never_fabricate_or_claim_generation(corpus, endpoint, request_data, expected_status):
    outputs, store, connectors = _execute_v3_graph(corpus, endpoint, request_data)
    assert outputs["archive"]["status"] == expected_status
    assert outputs["coverage"]["status"] == expected_status
    assert outputs["skill_card"] == {}
    assert outputs["served_from"] == "unavailable"
    assert outputs["workflow-status"] == "skipped"
    assert not set(LEGACY_TASKS[endpoint]) & set(store.executed)
    assert store.writes == 0 and connectors.external_calls == []
    if endpoint == "worldcup-player-spotlight":
        assert outputs["content_type"] == "unavailable"
        assert outputs["structured_retrospective"] == {}
        assert outputs["original_editorial"] is None
        assert outputs["resolved_player"] == {}
        assert outputs["player_overview"] == {}
        assert outputs["player_urn"] is None
    else:
        assert outputs["resolved_fixture"] == {}
        assert outputs["event_urn"] == ""
    assert outputs["candidates"] == []


def test_released_v3_graph_schedule_pagination_backtest_and_marco(corpus):
    schedule, store, connectors = _execute_v3_graph(corpus, "worldcup-get-schedule", {})
    assert schedule["schedule"]["count"] == schedule["schedule"]["total_count"] == 104
    assert store.writes == 0 and connectors.external_calls == []
    page, _, connectors = _execute_v3_graph(corpus, "worldcup-get-schedule", {"limit": 25, "offset": 25})
    assert page["schedule"]["count"] == 25 and page["schedule"]["total_count"] == 104
    assert page["schedule"]["has_more"] is True and connectors.external_calls == []

    backtest, _, connectors = _execute_v3_graph(corpus, "worldcup-backtest-forecasts", {})
    assert backtest["track_record"]["sample_size"] == 98
    assert backtest["excluded_count"] == 6 and connectors.external_calls == []

    performance = corpus["by_endpoint"]["worldcup-get-player-performance-context"]
    by_fixture = {row["value"]["response"]["fixture_player_pack"]["fixture_id"]: row for row in performance}
    for fixture_id in corpus["report"]["counts"]["restored_marco_fixtures"]:
        row = by_fixture[fixture_id]
        output, store, connectors = _execute_v3_graph(corpus, "worldcup-get-player-performance-context", {
            "event_urn": row["value"]["subject"]["event_urn"], "player_id": "260865",
        })
        assert output["player_performance_context"]["player"]["player_id"] == "260865"
        assert _archive_query(store)["returned"] == 1
        assert store.writes == 0 and connectors.external_calls == []


def test_full_104_fixture_replay_and_recap_facts(corpus):
    fixture_endpoints = CONNECTOR.FINAL_ARCHIVE_FIXTURE_ENDPOINTS
    for endpoint in fixture_endpoints:
        rows = corpus["by_endpoint"][endpoint]
        assert len(rows) == 104
        for row in rows:
            served = _serve(corpus, endpoint, row)
            assert served["archive_status"] == "hit", (endpoint, row["value"]["subject"]["key"])
            if endpoint == "worldcup-match-recap":
                validation = CONNECTOR.validate_grounded_match_recap({"params": {
                    "event": row["value"]["subject"]["event"],
                    "recap": served["response"]["skill_card"],
                }})["data"]
                assert validation["factually_valid"] is True
                assert served["response"]["skill_card"]["content_depth"]["unsupported_narrative"]


def test_backtest_is_recomputed_from_regulation_results(corpus):
    response = corpus["by_endpoint"]["worldcup-backtest-forecasts"][0]["value"]["response"]
    assert response["total_count"] == 104
    assert response["included_count"] == response["audited_count"] == response["track_record"]["sample_size"] == 98
    assert response["excluded_count"] == 6
    assert response["exclusion_reasons"] == {"forecast_at_or_after_kickoff": 6}
    assert response["track_record"]["accuracy"] == {"correct": 52, "total": 98, "accuracy_percent": 53.06}
    assert response["track_record"]["brier_scores"]["avg_1x2"] == 0.1913
    assert len(response["finished_fixtures"]) == 104
    assert response["clv_report"] == response["calibration_report"] == {}
    assert {"closing_line_value", "market_calibration"} <= set(response["coverage"]["unsupported_fields"])


def test_forecast_market_injury_squad_and_timestamp_semantics_are_honest(corpus):
    report = corpus["report"]
    assert report["counts"]["forecast_timing"] == {"at_or_after_kickoff": 6, "verified_pre_kickoff": 98}
    assert report["counts"]["market_timing"] == {"historical_prematch_quote": 5, "settled_or_late_cache": 96, "unavailable": 3}
    assert report["counts"]["injury_evidence"] == {"recorded_absences": 51, "unavailable": 53}
    assert report["counts"]["observed_squad_teams"] == 48
    assert report["integrity"]["forecast_candidate_payload_sha256"] == report["integrity"]["forecast_baseline_sha256"]

    for rows in corpus["by_endpoint"].values():
        for row in rows:
            response = row["value"]["response"]
            assert set(response["coverage"]) == {
                "schema_version", "status", "reason", "scope", "mode", "source_provenance",
                "population_count", "eligible_count", "included_count", "excluded_count",
                "exclusion_reasons", "unsupported_fields",
            }
            archive = response["archive"]
            assert archive["timestamp_semantics"] in {
                "original_model_computation", "original_editorial_generation",
                "derived_content_creation_not_source_freshness", "source_capture_observation", "unavailable",
            }
            if archive["timestamp_semantics"] in {"derived_content_creation_not_source_freshness", "unavailable"}:
                assert archive["snapshot_as_of"] is None

    for row in corpus["by_endpoint"]["worldcup-get-injuries"]:
        injury = row["value"]["response"]["injuries"]
        if injury["evidence_status"] == "unavailable":
            assert injury["observed_record_count"] == 0
            assert injury["historical_completeness_verified"] is False
    for row in corpus["by_endpoint"]["worldcup-get-squads"]:
        squads = row["value"]["response"]["squads"]
        assert squads["official_registration_status"] == "verified_final_published_snapshot"
        official = squads["official_registration_snapshot"]
        assert official["completeness"] == {
            "included_teams": 2, "requested_teams": 2,
            "status": "complete_for_published_snapshot",
        }
        assert len(official["teams"]) == 2
        assert all(len(team["players"]) == 26 for team in official["teams"])
        assert all(team["source"]["url"] == FIFA.FIFA_SOURCE_URL for team in official["teams"])


def test_schedule_defaults_paginates_filters_and_rejects_invalid_values(corpus):
    row = corpus["by_endpoint"]["worldcup-get-schedule"][0]
    full = _serve(corpus, "worldcup-get-schedule", row)
    assert full["response"]["schedule"]["count"] == 104
    assert full["response"]["schedule"]["total_count"] == 104
    assert full["response"]["schedule"]["has_more"] is False

    page = _serve(corpus, "worldcup-get-schedule", row, {"limit": 25, "offset": 25})
    assert page["response"]["schedule"]["count"] == 25
    assert page["response"]["schedule"]["total_count"] == 104
    assert page["response"]["schedule"]["offset"] == 25
    assert page["response"]["schedule"]["has_more"] is True

    filtered = _serve(corpus, "worldcup-get-schedule", row, {"team": "Brazil"})
    assert 0 < filtered["response"]["schedule"]["count"] < 104
    invalid = _serve(corpus, "worldcup-get-schedule", row, {"status": "playing-later"})
    assert invalid["archive_status"] == "error"
    assert invalid["response"]["coverage"]["status"] == "error"


def test_every_provider_player_has_spotlight_and_provider_only_resolution(corpus):
    spotlights = corpus["by_endpoint"]["worldcup-player-spotlight"]
    assert len(spotlights) == 1248
    observed_ids = {
        provider_id
        for row in spotlights
        for provider_id in row["value"]["response"]["resolved_player"]["observed_provider_ids"]
    }
    assert len(observed_ids) == 1249
    assert sum(row["value"]["response"]["original_editorial"] is not None for row in spotlights) == 2
    provider_only = [row for row in spotlights if row["value"]["response"]["player_urn"] is None]
    assert provider_only == []
    for row in spotlights:
        served = _serve(corpus, "worldcup-player-spotlight", row)
        assert served["archive_status"] == "hit"
        assert served["response"]["structured_retrospective"]["observed_appearance_count"] >= 1


def test_fifa_pdf_snapshot_and_reconciliation_ledger_are_exact(tmp_path):
    evidence = ARTIFACTS / "evidence"
    snapshot = FIFA.load_official_registration(
        evidence / "SquadLists-English.pdf",
        evidence / "fifa-official-registration-snapshot.json",
        evidence / "fifa-roster-raw-cells.json",
    )
    assert snapshot["validation"] == {
        "all_birth_dates_valid": True,
        "club_not_reported_count": 1,
        "font_artifact_warning_count": 15,
        "jersey_numbers_geometry_verified": True,
        "pdf_page_count": 48,
        "pdf_sha256_verified": True,
        "players_per_team": 26,
        "team_label_count": 48,
        "unique_registration_count": 1248,
    }
    jayden = next(row for row in snapshot["records"] if row["team_name"] == "South Africa" and row["jersey_number"] == 23)
    assert jayden["player_name_raw"] == "ADAMS Jayden"
    assert jayden["club_raw"] is None
    assert jayden["warnings"] == ["club_not_reported"]

    ledger = json.loads((ARTIFACTS / "identity-reconciliation-v3.json").read_text(encoding="utf-8"))
    assert ledger["counts"]["accepted_provider_ids"] == 1249
    assert ledger["counts"]["official_people"] == 1248
    assert ledger["counts"]["ambiguous_provider_ids"] == 0
    assert ledger["counts"]["canonical_birth_date_conflicts"] == 14
    assert ledger["counts"]["quarantined_identity_mappings"] == 1

    bad = copy.deepcopy(snapshot)
    bad["records"][0]["player_name_raw"] = "Wrong Player"
    bad_path = tmp_path / "bad-name.json"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(FIFA.FifaReconciliationError, match="raw cells"):
        FIFA.load_official_registration(
            evidence / "SquadLists-English.pdf", bad_path, evidence / "fifa-roster-raw-cells.json",
        )
    bad = copy.deepcopy(snapshot)
    bad.pop("validation")
    bad["records"][0]["birth_date"] = "2000-99-99"
    bad_path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(FIFA.FifaReconciliationError, match="birth date"):
        FIFA.load_official_registration(
            evidence / "SquadLists-English.pdf", bad_path, evidence / "fifa-roster-raw-cells.json",
        )


def test_raw_player_corpus_marco_qatar_and_identity_collisions(corpus):
    performance = corpus["by_endpoint"]["worldcup-get-player-performance-context"]
    assert sum(row["value"]["response"]["fixture_player_pack"]["raw_player_count"] for row in performance) == 5323
    assert sum(row["value"]["response"]["fixture_player_pack"]["player_count"] for row in performance) == 5323
    marco_fixtures = []
    for row in performance:
        pack = row["value"]["response"]["fixture_player_pack"]
        assert len({item["player"]["_id"] for item in pack["players"]}) == pack["player_count"]
        for item in pack["players"]:
            served = _serve(corpus, "worldcup-get-player-performance-context", row, {
                "event_urn": row["value"]["subject"]["event_urn"],
                "player_id": item["provider_observation"]["player_id"],
            })
            assert served["archive_status"] == "hit"
            if item["provider_observation"]["player_id"] == "260865":
                marco_fixtures.append(pack["fixture_id"])
                assert item["player"]["_id"] == FIFA.MARCO_URN
    assert sorted(marco_fixtures) == ["1489384", "1489403", "1489420", "1567309"]

    qatar_key = "urn:machina:sport:soccer:player:al-hashmi-al-hussain:20030815:qat"
    qatar_spotlight = next(row for row in corpus["by_endpoint"]["worldcup-player-spotlight"] if row["value"]["subject"]["key"] == qatar_key)
    assert qatar_spotlight["value"]["subject"]["aliases"] == ["339795", "542542"]
    for provider_id in ("339795", "542542"):
        served = _serve(corpus, "worldcup-player-spotlight", qatar_spotlight, {"player_id": provider_id})
        assert served["archive_status"] == "hit"
    qatar_resolve = next(row for row in corpus["by_endpoint"]["worldcup-resolve"] if row["value"]["subject"]["key"] == qatar_key)
    for provider_id in ("339795", "542542"):
        served = _serve(corpus, "worldcup-resolve", qatar_resolve, {"id": provider_id})
        assert served["archive_status"] == "hit"
        assert served["response"]["entity"]["_id"] == qatar_key

    resolve_rows = corpus["by_endpoint"]["worldcup-resolve"]
    bad = next(row for row in resolve_rows if row["value"]["subject"]["key"] == FIFA.QUARANTINED_MARIO_URN)
    served_bad = _serve(corpus, "worldcup-resolve", bad, {"id": FIFA.QUARANTINED_MARIO_URN})
    assert served_bad["response"]["identity_status"] == "quarantined"
    assert served_bad["response"]["entity"]["provider_ids"] == {}
    for provider_id, expected in (("260865", FIFA.MARCO_URN), ("2763", "urn:machina:sport:soccer:player:mario-pasalic:19950209:hrv")):
        row = next(item for item in resolve_rows if item["value"]["subject"]["key"] == expected)
        assert _serve(corpus, "worldcup-resolve", row, {"id": provider_id})["response"]["entity"]["_id"] == expected


def test_dob_conflicts_and_public_provenance_are_explicit(corpus):
    ledger = json.loads((ARTIFACTS / "identity-reconciliation-v3.json").read_text(encoding="utf-8"))
    conflicts = [row for row in ledger["conflicting"] if row["type"] == "canonical_birth_date_conflict"]
    assert len(conflicts) == 14
    for conflict in conflicts:
        row = next(item for item in corpus["by_endpoint"]["worldcup-resolve"] if item["value"]["subject"]["key"] == conflict["canonical_urn"])
        registration = row["value"]["response"]["entity"]["official_registration"]
        assert registration["canonical_birth_date_conflict"] is True
        assert registration["birth_date"] == conflict["official_birth_date"]
    for rows in corpus["by_endpoint"].values():
        for row in rows:
            public_json = json.dumps(row["value"]["response"], ensure_ascii=False)
            assert ".local/" not in public_json
            assert "capture_file" not in public_json
    schedule = corpus["by_endpoint"]["worldcup-get-schedule"][0]["value"]["response"]["schedule"]
    for event in schedule["events"]:
        provenance = event["result_details"]["provenance"]
        assert provenance["source_url"] == "https://www.api-football.com/"
        assert provenance["observed_at"]
        assert len(provenance["provider_result_sha256"]) == 64


def test_v3_out_of_catalog_requests_never_fall_back(corpus):
    backtest = corpus["by_endpoint"]["worldcup-backtest-forecasts"][0]
    result = _serve(corpus, "worldcup-backtest-forecasts", backtest, {"competition": "premier-league"})
    assert result["archive_status"] == "unavailable"
    standings = corpus["by_endpoint"]["worldcup-get-standings"][0]
    for request in ({"league": "39", "season": "2026"}, {"league": "1", "season": "2022"}):
        result = _serve(corpus, "worldcup-get-standings", standings, request)
        assert result["archive_status"] == "unavailable"
        assert result["response"]["coverage"]["population_count"] is None


def test_import_openapi_is_upstream_only_and_preserves_catalog_contract():
    buyer = json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8"))
    imported = json.loads((ROOT / "docs/openapi-import-source.json").read_text(encoding="utf-8"))
    assert buyer["servers"][0]["url"] == "https://agents.machina.gg/zcj/ajgpivnid8bn"
    assert imported["servers"][0]["url"] == "https://api.machina.gg"
    assert imported["paths"] == buyer["paths"]
    assert imported["components"] == buyer["components"]
    assert imported["x-publication"]["openApiUrl"].startswith(
        "https://raw.githubusercontent.com/machina-sports/machina-templates/"
    )
    assert "manual_gate" in imported["x-publication"]


def test_spotlight_schema_accepts_native_omission_only_for_source_only_cards(corpus):
    spec = json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8"))
    validator = _schema_validator(spec, {"$ref": "#/components/schemas/SpotlightResponse"})
    rows = corpus["by_endpoint"]["worldcup-player-spotlight"]

    source_only = next(row for row in rows if row["value"]["response"]["original_editorial"] is None)
    source_output, _, _ = _execute_v3_graph(corpus, "worldcup-player-spotlight", _request("worldcup-player-spotlight", source_only))
    assert source_output["content_type"] == "structured_retrospective"
    assert source_output["original_editorial"] is None
    validator.validate(source_output)
    native_source_output = {key: value for key, value in source_output.items() if value is not None}
    assert "original_editorial" not in native_source_output
    validator.validate(native_source_output)

    retained = next(row for row in rows if row["value"]["response"]["original_editorial"] is not None)
    retained_output, _, _ = _execute_v3_graph(corpus, "worldcup-player-spotlight", _request("worldcup-player-spotlight", retained))
    assert retained_output["content_type"] == "original_editorial_with_structured_retrospective"
    assert retained_output["original_editorial"]
    validator.validate(retained_output)

    missing_original = dict(retained_output)
    missing_original.pop("original_editorial")
    with pytest.raises(ValidationError):
        validator.validate(missing_original)
    for invalid_original in (None, {}, "not-an-editorial-object"):
        invalid = dict(retained_output, original_editorial=invalid_original)
        with pytest.raises(ValidationError):
            validator.validate(invalid)
    with pytest.raises(ValidationError):
        validator.validate({**native_source_output, "original_editorial": "wrong-type"})
    missing_required = dict(native_source_output)
    missing_required.pop("skill_card")
    with pytest.raises(ValidationError):
        validator.validate(missing_required)


def test_integrity_force_regen_and_ambiguous_or_unknown_selectors_fail_closed(corpus):
    recap = corpus["by_endpoint"]["worldcup-match-recap"][0]
    assert _serve(corpus, "worldcup-match-recap", recap, {
        "event_urn": recap["value"]["subject"]["event_urn"], "force_regen": True,
    })["archive_status"] == "hit"
    duplicate = _serve(corpus, "worldcup-match-recap", recap, request={"event_urn": recap["value"]["subject"]["event_urn"]})
    assert duplicate["archive_status"] == "hit"
    params = {
        "endpoint": "worldcup-match-recap", "archive_version": CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION,
        "request": {"event_urn": recap["value"]["subject"]["event_urn"]},
        "documents": [recap, recap], "canonical_events": corpus["events"],
        "canonical_identities": corpus["identities"], "archive_manifest": corpus["closure"]["documents"],
    }
    assert CONNECTOR.serve_final_archive({"params": params})["data"]["archive_status"] == "error"
    spotlight = corpus["by_endpoint"]["worldcup-player-spotlight"][0]
    unavailable = _serve(corpus, "worldcup-player-spotlight", spotlight, {"player_id": "not-in-archive"})
    assert unavailable["archive_status"] == "unavailable"


def test_openapi_validates_real_served_normal_partial_and_error_responses(corpus):
    spec = json.loads((ROOT / "docs/openapi.json").read_text(encoding="utf-8"))
    path_by_endpoint = {
        "worldcup-resolve": "/world-cup/v1/resolve",
        "worldcup-get-schedule": "/world-cup/v1/get-schedule",
        "worldcup-get-event-context": "/world-cup/v1/get-event-context",
        "worldcup-get-standings": "/world-cup/v1/get-standings",
        "worldcup-get-squads": "/world-cup/v1/get-squads",
        "worldcup-get-injuries": "/world-cup/v1/get-injuries",
        "worldcup-get-player-performance-context": "/world-cup/v1/get-player-performance-context",
        "worldcup-get-match-forecast": "/world-cup/v1/get-match-forecast",
        "worldcup-backtest-forecasts": "/world-cup/v1/backtest-forecasts",
        "worldcup-match-recap": "/world-cup/v1/skills/match-recap",
        "worldcup-player-spotlight": "/world-cup/v1/skills/player-spotlight",
    }
    Draft202012Validator.check_schema(spec)
    for endpoint, path in path_by_endpoint.items():
        operation = spec["paths"][path]["post"]
        assert operation["requestBody"]["content"]["application/json"]["schema"]
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        validator = _schema_validator(spec, schema)
        served = _serve(corpus, endpoint, corpus["by_endpoint"][endpoint][0])
        validator.validate(served["response"])

    schedule_schema = spec["paths"]["/world-cup/v1/get-schedule"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]
    error = _serve(corpus, "worldcup-get-schedule", corpus["by_endpoint"]["worldcup-get-schedule"][0], {"offset": -1})
    _schema_validator(spec, schedule_schema).validate(error["response"])
    assert spec["x-transport-contract"].startswith("The 200 schemas describe the workflow's public source response")


def test_all_public_workflow_wrappers_forward_candidate_contract_fields():
    for endpoint in CONNECTOR.FINAL_ARCHIVE_ENDPOINTS:
        workflow = yaml.safe_load((ROOT / "workflows" / f"{endpoint}.yml").read_text(encoding="utf-8"))["workflow"]
        assert "coverage" in workflow["outputs"]
        assert "archive_version" not in workflow.get("inputs", {})
        fallback = workflow["outputs"]["coverage"]
        assert "'population_count': None" in fallback
        assert "'eligible_count': None" in fallback
    schedule = yaml.safe_load((ROOT / "workflows/worldcup-get-schedule.yml").read_text(encoding="utf-8"))["workflow"]
    assert {"warnings", "coverage"} <= set(schedule["outputs"])
    assert schedule["inputs"]["limit"] == "$.get('limit', 104)"
    assert schedule["inputs"]["offset"] == "$.get('offset', 0)"
    spotlight = yaml.safe_load((ROOT / "workflows/worldcup-player-spotlight.yml").read_text(encoding="utf-8"))["workflow"]
    assert {"player_key", "structured_retrospective", "original_editorial", "content_type"} <= set(spotlight["outputs"])
