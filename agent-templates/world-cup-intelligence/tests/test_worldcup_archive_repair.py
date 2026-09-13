"""Offline archive-repair tests. All payloads in this module are synthetic test-only data."""

import copy
import importlib.util
import json
from pathlib import Path

import yaml


TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = TEMPLATE_ROOT / "workflows"
MODULE_PATH = TEMPLATE_ROOT / "worldcup-market-intelligence.py"
SPEC = importlib.util.spec_from_file_location("worldcup_archive_repair", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
BACKFILL_NAMES = (
    "worldcup-backfill-crosswalks",
    "worldcup-backfill-model-forecasts",
    "worldcup-backfill-market-sources",
    "worldcup-backfill-historical-data",
    "worldcup-backfill-editorial-content",
    "worldcup-backfill-master",
)
MODE_BY_WORKFLOW = {
    "worldcup-backfill-crosswalks": "crosswalks",
    "worldcup-backfill-model-forecasts": "forecasts",
    "worldcup-backfill-market-sources": "markets",
    "worldcup-backfill-historical-data": "historical",
    "worldcup-backfill-editorial-content": "editorial",
    "worldcup-backfill-master": "master",
}


def test_compacted_fixture_pagination_never_skips_unreturned_rows():
    evidence = [synthetic_event(number) for number in range(104)]
    original = copy.deepcopy(evidence)
    seen = []
    offset = 0
    compacted = False
    while True:
        result = plan("forecasts", evidence, batch_size=100, offset=offset)
        fixtures = result["fixtures"]
        compacted |= result["report_compaction"]["applied"]
        assert result["batch"]["returned"] == len(fixtures)
        assert result["array_metadata"]["fixtures"]["oversized_omitted"] == 0
        seen.extend(item["event_urn"] for item in fixtures)
        next_offset = result["batch"]["next_offset"]
        if next_offset is None:
            break
        assert next_offset == offset + len(fixtures)
        assert next_offset > offset
        offset = next_offset
    assert compacted
    assert len(seen) == len(set(seen)) == len(evidence)
    assert set(seen) == {item["value"]["_id"] for item in evidence}
    assert evidence == original


def load_workflow(name):
    return yaml.safe_load((WORKFLOW_DIR / f"{name}.yml").read_text(encoding="utf-8"))["workflow"]


def evaluate(expression, context):
    namespace = {
        "__builtins__": {},
        "context": context,
        "dict": dict,
        "isinstance": isinstance,
        "len": len,
        "str": str,
    }
    return eval(expression.replace("$.get", "context.get"), namespace, namespace)


def synthetic_event(number, *, status="FT", start="2026-07-01T12:00:00Z"):
    event_urn = f"urn:machina:sport:soccer:event:team-{number}-vs-opponent-{number}:20260701:wor"
    home_urn = f"urn:machina:sport:soccer:team:team-{number}:t{number:02d}"
    away_urn = f"urn:machina:sport:soccer:team:opponent-{number}:o{number:02d}"
    return {
        "document_id": f"event-doc-{number}",
        "name": "worldcup:event",
        "value": {
            "_id": event_urn,
            "machina_competition_slug": "world-cup-2026",
            "schema:startDate": start,
            "sport:status": status,
            "provider_ids": {"api_football": str(1000 + number)},
            "sport:competitors": [
                {"@id": home_urn, "name": f"Team {number}"},
                {"@id": away_urn, "name": f"Opponent {number}"},
            ],
        },
    }


def plan(mode, evidence, **overrides):
    params = {
        "mode": mode,
        "evidence": evidence,
        "expected_fixture_count": overrides.pop("expected_fixture_count", len([item for item in evidence if item.get("name") == "worldcup:event"])),
        **overrides,
    }
    return MODULE.plan_archive_repair({"params": params})["data"]


def test_six_workflows_use_only_supported_read_only_dataflow_and_are_installed_once():
    install = yaml.safe_load((TEMPLATE_ROOT / "_install.yml").read_text(encoding="utf-8"))
    installed_paths = [item.get("path") for item in install["datasets"] if item.get("type") == "workflow"]

    for name in BACKFILL_NAMES:
        workflow = load_workflow(name)
        assert "context-variables" not in workflow
        assert [item["type"] for item in workflow["tasks"]] == ["document", "connector"]
        search, assessment = workflow["tasks"]
        assert search["config"] == {
            "action": "search",
            "search-limit": 5000,
            "search-vector": False,
            "search-sorters": ["_id", 1],
        }
        assert assessment["connector"] == {
            "name": "worldcup-market-intelligence",
            "command": "plan_archive_repair",
        }
        assert evaluate(assessment["inputs"]["mode"], {}) == MODE_BY_WORKFLOW[name]
        assert assessment["inputs"]["evidence"] == "$.get('archive_evidence', [])"
        assert installed_paths.count(f"workflows/{name}.yml") == 1


def test_yaml_search_output_feeds_planner_without_losing_document_identity():
    workflow = load_workflow("worldcup-backfill-market-sources")
    expression = workflow["tasks"][0]["outputs"]["archive_evidence"]
    event = synthetic_event(1)
    raw_documents = [
        {"_id": event["document_id"], "name": event["name"], "value": event["value"], "created": "2026-06-01T00:00:00Z"},
        {
            "_id": "market-doc-1",
            "name": "worldcup:market-cache",
            "value": {
                "cache_id": "kalshi:test-market",
                "competition_urn": "urn:machina:sport:soccer:competition:fifa-world-cup-2026:wor",
                "related_team_urns": [item["@id"] for item in event["value"]["sport:competitors"]],
                "outcomes": [{"name": "Team 1", "price": 0.55}],
                "fetched_at": "2026-06-30T12:00:00Z",
            },
        },
    ]

    evidence = evaluate(expression, {"documents": raw_documents})
    result = plan("markets", evidence, expected_fixture_count=1)

    assert evidence[0]["document_id"] == "event-doc-1"
    assert result["fixtures"][0]["event_evidence"][0]["document_id"] == "event-doc-1"
    assert result["fixtures"][0]["markets"]["records"] == [{
        "collection": "worldcup:market-cache",
        "evidence_id": "kalshi:test-market",
        "snapshot_as_of": "2026-06-30T12:00:00Z",
        "document_id": "market-doc-1",
        "join": "related_team_urns",
    }]


def test_batches_have_stable_offsets_independent_of_input_order():
    evidence = [synthetic_event(number) for number in (4, 1, 3, 2)]
    forward = plan("markets", evidence, expected_fixture_count=4, offset=1, batch_size=2)
    reverse = plan("markets", list(reversed(evidence)), expected_fixture_count=4, offset=1, batch_size=2)

    assert [item["fixture_key"] for item in forward["fixtures"]] == [item["fixture_key"] for item in reverse["fixtures"]]
    assert forward["batch"] == {"offset": 1, "size": 2, "returned": 2, "total": 4, "next_offset": 3}


def test_forecasts_join_per_fixture_and_are_never_regenerated_or_overwritten():
    events = [
        synthetic_event(1, start="2026-07-01T12:00:00Z"),
        synthetic_event(2, start="2026-07-02T12:00:00Z"),
        synthetic_event(3, start="2026-07-03T12:00:00Z"),
    ]
    forecasts = [
        {
            "document_id": "forecast-before",
            "name": "worldcup:model-forecast",
            "value": {
                "_id": "preserved-forecast-a",
                "provider_ids": {"api_football": "1001"},
                "probabilities": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2},
                "model": {"computed_at": "2026-06-30T12:00:00Z"},
            },
        },
        {
            "document_id": "forecast-after",
            "name": "worldcup:model-forecast",
            "value": {
                "_id": "preserved-forecast-b",
                "provider_ids": {"api_football": "1002"},
                "probabilities": {"home_win": 0.5, "draw": 0.3, "away_win": 0.2},
                "model": {"computed_at": "2026-07-02T13:00:00Z"},
            },
        },
    ]
    evidence = events + forecasts
    original = copy.deepcopy(evidence)

    result = plan("forecasts", evidence, expected_fixture_count=3, batch_size=3)
    by_fixture = {item["provider_ids"]["api_football"]: item for item in result["fixtures"]}

    assert evidence == original
    assert by_fixture["1001"]["forecasts"]["records"][0]["state"] == "historical_model"
    assert by_fixture["1002"]["forecasts"]["records"][0]["state"] == "unsafe_post_kickoff"
    assert by_fixture["1003"]["forecasts"] == {"state": "missing", "records": []}
    assert result["outcomes"] == {"provider_calls": 0, "forecast_computations": 0, "documents_created": 0, "documents_updated": 0}
    assert any(item["entity_id"] == by_fixture["1003"]["fixture_key"] and "prohibited" in item["reason"] for item in result["missing_work"])
    assert result["mutation_capability"] == "disabled"


def test_forecast_requires_parseable_model_time_and_complete_probabilities():
    event = synthetic_event(1)
    forecast = {
        "document_id": "forecast-malformed",
        "name": "worldcup:model-forecast",
        "created": "2026-06-01T00:00:00Z",
        "value": {
            "provider_ids": {"api_football": "1001"},
            "probabilities": {"home_win": 0.5},
            "model": {"computed_at": "not-a-timestamp"},
        },
    }

    result = plan("forecasts", [event, forecast], expected_fixture_count=1)
    record = result["fixtures"][0]["forecasts"]["records"][0]

    assert record["state"] == "partial_unverified_model_time"
    assert record["computed_at"] == "not-a-timestamp"
    assert result["assessment_status"] == "blocked"
    assert any(item["capability"] == "prematch_forecast" for item in result["missing_work"])

    forecast["value"]["model"]["computed_at"] = "2026-06-30T12:00:00Z"
    invalid_probabilities = plan("forecasts", [event, forecast], expected_fixture_count=1)
    assert invalid_probabilities["fixtures"][0]["forecasts"]["records"][0]["state"] == "partial_missing_probabilities"


def test_global_status_assesses_all_fixtures_not_only_returned_batch():
    events = [synthetic_event(number) for number in (1, 2, 3)]
    market = {
        "document_id": "market-first-only",
        "name": "worldcup:market-cache",
        "value": {
            "cache_id": "kalshi:first-only",
            "event_urn": events[0]["value"]["_id"],
            "outcomes": [{"name": "Team 1", "price": 0.55}],
        },
    }

    result = plan("markets", events + [market], expected_fixture_count=3, offset=0, batch_size=1)

    assert len(result["fixtures"]) == 1
    assert result["fixtures"][0]["markets"]["state"] == "present"
    assert result["assessment_status"] == "blocked"
    missing_ids = {item["entity_id"] for item in result["missing_work"] if item["capability"] == "fixture_market_evidence"}
    assert missing_ids == {events[1]["value"]["_id"], events[2]["value"]["_id"]}


def test_team_pair_market_fallback_fails_closed_when_pair_is_not_unique():
    first = synthetic_event(1, start="2026-06-01T12:00:00Z")
    second = synthetic_event(2, start="2026-07-01T12:00:00Z")
    second["value"]["sport:competitors"] = copy.deepcopy(first["value"]["sport:competitors"])
    market = {
        "document_id": "ambiguous-market",
        "name": "worldcup:market-cache",
        "value": {
            "cache_id": "kalshi:ambiguous-pair",
            "competition_urn": "urn:machina:sport:soccer:competition:fifa-world-cup-2026:wor",
            "related_team_urns": [item["@id"] for item in first["value"]["sport:competitors"]],
            "outcomes": [{"name": "Team 1", "price": 0.55}],
        },
    }

    result = plan("markets", [first, second, market], expected_fixture_count=2, batch_size=2)

    assert [item["markets"]["state"] for item in result["fixtures"]] == ["missing", "missing"]
    assert all(item["evidence_id"] != "kalshi:ambiguous-pair" for row in result["fixtures"] for item in row["markets"]["records"])


def test_partial_market_and_historical_records_cannot_report_complete():
    event = synthetic_event(1)
    event_urn = event["value"]["_id"]
    market = {
        "document_id": "market-no-outcomes",
        "name": "worldcup:market-cache",
        "value": {"cache_id": "kalshi:no-outcomes", "event_urn": event_urn, "outcomes": []},
    }
    historical = [
        {
            "document_id": "squad-duplicate-home",
            "name": "worldcup:squads",
            "value": {
                "event_urn": event_urn,
                "scope": "world-cup-2026-tournament",
                "teams": [
                    {"side": "home", "players": [{"id": "p1"}]},
                    {"side": "home", "players": [{"id": "p2"}]},
                ],
            },
        },
        {
            "document_id": "performance-one-row",
            "name": "worldcup:player-performance-context",
            "value": {"event_urn": event_urn, "players": [{"player_id": "p1"}]},
        },
    ]

    market_result = plan("markets", [event, market], expected_fixture_count=1)
    history_result = plan("historical", [event, *historical], expected_fixture_count=1)

    assert market_result["fixtures"][0]["markets"]["state"] == "partial"
    assert market_result["assessment_status"] == "blocked"
    states = history_result["fixtures"][0]["historical"]
    assert states["worldcup:squads"]["state"] == "partial"
    assert states["worldcup:player-performance-context"]["state"] == "partial"
    assert history_result["assessment_status"] == "blocked"


def test_malformed_market_outcomes_and_split_performance_evidence_stay_partial():
    event = synthetic_event(1)
    event_urn = event["value"]["_id"]
    market = {
        "document_id": "market-malformed-outcome",
        "name": "worldcup:market-cache",
        "value": {"cache_id": "kalshi:malformed", "event_urn": event_urn, "outcomes": [{}]},
    }
    performance = [
        {
            "document_id": "performance-players",
            "name": "worldcup:player-performance-context",
            "value": {"event_urn": event_urn, "players": [{"player_id": "p1"}]},
        },
        {
            "document_id": "performance-empty-complete",
            "name": "worldcup:player-performance-context",
            "value": {"event_urn": event_urn, "players": [], "coverage_complete": True},
        },
    ]

    market_result = plan("markets", [event, market], expected_fixture_count=1)
    history_result = plan("historical", [event, *performance], expected_fixture_count=1)

    assert market_result["fixtures"][0]["markets"]["state"] == "partial"
    assert history_result["fixtures"][0]["historical"]["worldcup:player-performance-context"]["state"] == "partial"


def test_missing_empty_partial_and_current_squads_are_reported_truthfully():
    event = synthetic_event(1)
    event_urn = event["value"]["_id"]
    evidence = [
        event,
        {
            "document_id": "injuries-empty",
            "name": "worldcup:injuries",
            "value": {"event_urn": event_urn, "teams": [{"side": "home", "count": 0, "missing": []}]},
        },
        {
            "document_id": "squad-current",
            "name": "worldcup:squads",
            "value": {"event_urn": event_urn, "teams": [{"side": "home", "players": [{"id": "p1"}]}]},
        },
        {
            "document_id": "performance-empty",
            "name": "worldcup:player-performance-context",
            "value": {"event_urn": event_urn, "players": []},
        },
    ]

    result = plan("historical", evidence, expected_fixture_count=1)
    historical = result["fixtures"][0]["historical"]

    assert historical["worldcup:injuries"]["state"] == "empty_unverified"
    assert historical["worldcup:squads"]["state"] == "unverified_temporal_scope"
    assert historical["worldcup:player-performance-context"]["state"] == "empty_unverified"
    reasons = " ".join(item["reason"] for item in result["missing_work"])
    assert "provider unavailability" not in reasons.lower()
    assert "may represent a current roster" in reasons


def test_crosswalk_assessment_preserves_entity_ids_and_reports_exact_gaps():
    event = synthetic_event(1)
    home, away = [item["@id"] for item in event["value"]["sport:competitors"]]
    evidence = [
        event,
        {
            "document_id": "team-home",
            "name": "worldcup:identity-crosswalk",
            "value": {"_id": home, "name": "Team 1", "provider_ids": {"api_football": "11", "espn": "12"}},
        },
        {
            "document_id": "player-one",
            "name": "worldcup:identity-crosswalk",
            "value": {
                "_id": "urn:machina:sport:soccer:player:test:20000101:t01",
                "machina_competition_slug": "world-cup-2026",
                "provider_ids": {"api_football": "21"},
            },
        },
    ]

    result = plan("crosswalks", evidence, expected_fixture_count=1)
    team_rows = result["fixtures"][0]["crosswalks"]["teams"]

    assert [item["team_urn"] for item in team_rows] == sorted([home, away])
    assert next(item for item in team_rows if item["team_urn"] == home)["evidence"][0]["evidence_id"] == home
    assert any(item["entity_id"] == away and item["capability"] == "team_identity" for item in result["missing_work"])
    assert result["entity_coverage"]["players"][0]["player_urn"].startswith("urn:machina:sport:soccer:player:")
    assert result["entity_coverage"]["player_population_status"] == "not_assessed"
    assert any(item["capability"] == "player_crosswalk_population" for item in result["missing_work"])


def test_crosswalk_player_population_uses_explicit_expected_manifest():
    event = synthetic_event(1)
    player_urn = "urn:machina:sport:soccer:player:test:20000101:t01"
    result = plan(
        "crosswalks",
        [event],
        expected_fixture_count=1,
        expected_player_urns=[player_urn],
    )

    assert result["entity_coverage"]["player_population_status"] == "assessed"
    assert any(item["entity_id"] == player_urn and item["capability"] == "player_identity" for item in result["missing_work"])


def test_duplicate_event_and_team_evidence_conflicts_fail_closed():
    event = synthetic_event(1)
    duplicate = copy.deepcopy(event)
    duplicate["document_id"] = "event-conflict"
    duplicate["value"]["schema:startDate"] = "2026-07-01T13:00:00Z"
    duplicate["value"]["provider_ids"]["api_football"] = "different-fixture"
    home = event["value"]["sport:competitors"][0]["@id"]
    team_a = {
        "document_id": "team-a",
        "name": "worldcup:identity-crosswalk",
        "value": {"_id": home, "machina_competition_slug": "world-cup-2026", "provider_ids": {"api_football": "11"}},
    }
    team_b = copy.deepcopy(team_a)
    team_b["document_id"] = "team-b"
    team_b["value"]["provider_ids"]["api_football"] = "12"

    result = plan("crosswalks", [event, duplicate, team_a, team_b], expected_fixture_count=1, expected_player_urns=[])
    capabilities = {item["capability"] for item in result["missing_work"]}

    assert result["fixtures"][0]["start_time"] is None
    assert result["fixtures"][0]["event_conflicts"] == ["provider_ids.api_football", "start_time"]
    assert "consistent_event_evidence" in capabilities
    assert "consistent_team_provider_ids" in capabilities
    assert result["assessment_status"] == "blocked"


def test_corrected_event_urn_with_same_fixture_id_stays_one_conflicted_fixture():
    event = synthetic_event(1)
    corrected = copy.deepcopy(event)
    corrected["document_id"] = "corrected-event-urn"
    corrected["value"]["_id"] = "urn:machina:sport:soccer:event:corrected-vs-opponent:20260701:wor"

    result = plan("forecasts", [event, corrected], expected_fixture_count=1)

    assert result["batch"]["total"] == 1
    assert "event_urn" in result["fixtures"][0]["event_conflicts"]
    assert any(item["capability"] == "consistent_event_evidence" for item in result["missing_work"])


def test_missing_competitors_and_nonfinal_status_are_archive_gaps():
    event = synthetic_event(1, status="NS")
    event["value"]["sport:competitors"] = []

    result = plan("crosswalks", [event], expected_fixture_count=1, expected_player_urns=[])
    capabilities = {item["capability"] for item in result["missing_work"]}

    assert "fixture_competitors" in capabilities
    assert "final_result_status" in capabilities
    assert result["assessment_status"] == "blocked"


def test_unscoped_evidence_cannot_satisfy_archive_coverage():
    event = synthetic_event(1)
    unscoped_event = copy.deepcopy(event)
    unscoped_event["value"].pop("machina_competition_slug")
    unscoped_market = {
        "document_id": "unscoped-market",
        "name": "worldcup:market-cache",
        "value": {
            "cache_id": "kalshi:unscoped",
            "related_team_urns": [item["@id"] for item in event["value"]["sport:competitors"]],
            "outcomes": [{"name": "Team 1", "price": 0.55}],
        },
    }
    contradictory_market = {
        "document_id": "other-competition-market",
        "name": "worldcup:market-cache",
        "value": {
            "cache_id": "kalshi:other-competition",
            "event_urn": event["value"]["_id"],
            "competition_urn": "urn:machina:sport:soccer:competition:other:oth",
            "outcomes": [{"name": "Team 1", "price": 0.55}],
        },
    }

    rejected = plan("markets", [unscoped_event], expected_fixture_count=1)
    market_result = plan("markets", [event, unscoped_market], expected_fixture_count=1)
    contradictory_result = plan("markets", [event, contradictory_market], expected_fixture_count=1)

    assert rejected["fixtures"] == []
    assert rejected["evidence"]["rejected_events"][0]["evidence_id"] == event["value"]["_id"]
    assert market_result["fixtures"][0]["markets"]["state"] == "missing"
    assert contradictory_result["fixtures"][0]["markets"]["state"] == "missing"


def test_in_scope_event_without_stable_identity_blocks_completion():
    event = synthetic_event(1)
    malformed = {
        "document_id": "malformed-event",
        "name": "worldcup:event",
        "value": {"machina_competition_slug": "world-cup-2026", "sport:status": "FT"},
    }

    result = plan("markets", [event, malformed], expected_fixture_count=1)

    assert result["evidence"]["invalid_events"][0]["document_id"] == "malformed-event"
    assert any(item["capability"] == "stable_event_identity" for item in result["missing_work"])
    assert result["assessment_status"] == "blocked"


def test_empty_or_unscoped_editorial_documents_remain_missing():
    event = synthetic_event(1)
    event_urn = event["value"]["_id"]
    player_urn = "urn:machina:sport:soccer:player:test:20000101:t01"
    recap = {
        "document_id": "empty-recap",
        "name": "worldcup:skill-match-recap",
        "value": {"subject_urn": event_urn, "body": {}},
    }
    spotlight = {
        "document_id": "current-spotlight",
        "name": "worldcup:skill-player-spotlight",
        "value": {"subject_urn": player_urn, "scope": "current", "body": {"headline": "Current"}},
    }

    result = plan("editorial", [event, recap, spotlight], expected_fixture_count=1, target_player_urns=[player_urn])

    assert result["fixtures"][0]["editorial"]["recap_state"] == "empty_unverified"
    assert result["entity_coverage"]["spotlights"][0]["state"] == "missing"
    assert {item["capability"] for item in result["missing_work"]} >= {"evergreen_match_recap", "archived_player_spotlight"}


def test_nonfinite_numeric_inputs_use_safe_defaults_and_block_completion():
    event = synthetic_event(1)
    result = MODULE.plan_archive_repair({
        "params": {
            "mode": "markets",
            "evidence": [event],
            "offset": float("nan"),
            "batch_size": float("inf"),
            "expected_fixture_count": 1,
        }
    })["data"]

    assert result["batch"]["offset"] == 0
    assert result["batch"]["size"] == 20
    assert result["assessment_status"] == "blocked"
    assert any(item["capability"] == "valid_bounded_inputs" for item in result["missing_work"])

    huge = MODULE.plan_archive_repair({
        "params": {"mode": "markets", "evidence": [event], "offset": 10**10000, "expected_fixture_count": 1}
    })["data"]
    assert huge["batch"]["offset"] == 0
    assert any(item["capability"] == "valid_bounded_inputs" for item in huge["missing_work"])


def test_none_empty_and_bounded_paths_fail_closed_without_simulated_success():
    empty = MODULE.plan_archive_repair({"params": {"mode": "master", "evidence": None}})["data"]
    bounded = plan("master", [synthetic_event(1), synthetic_event(2)], expected_fixture_count=2, max_evidence=1)

    assert empty["assessment_status"] == "unavailable"
    assert empty["fixtures"] == []
    assert empty["outcomes"]["documents_updated"] == 0
    assert bounded["evidence"]["truncated"] is True
    assert bounded["assessment_status"] == "blocked"
    assert bounded["stages"] == [
        {"name": "crosswalks", "action": "assess_only"},
        {"name": "forecasts", "action": "assess_only"},
        {"name": "markets", "action": "assess_only"},
        {"name": "historical", "action": "assess_only"},
        {"name": "editorial", "action": "assess_only"},
    ]


def test_editorial_requires_an_explicit_spotlight_target_set():
    event = synthetic_event(1)
    without_targets = plan("editorial", [event], expected_fixture_count=1)
    with_targets = plan(
        "editorial",
        [event],
        expected_fixture_count=1,
        target_player_urns=["urn:machina:sport:soccer:player:test:20000101:t01"],
    )

    assert without_targets["entity_coverage"]["spotlight_target_status"] == "not_assessed"
    assert any("no source-backed target_player_urns" in warning for warning in without_targets["warnings"])
    assert with_targets["entity_coverage"]["spotlights"][0]["state"] == "missing"
    assert any(item["capability"] == "archived_player_spotlight" for item in with_targets["missing_work"])


def test_large_master_report_is_bounded_with_truthful_global_counts_and_exact_returned_identity():
    event = synthetic_event(1)
    players = []
    for number in range(4999):
        provider_id = "x" * 100_000 if number == 0 else ([f"provider-{item}" for item in range(2000)] if number == 1 else str(number))
        players.append({
            "document_id": f"player-doc-{number:04d}",
            "name": "worldcup:identity-crosswalk",
            "value": {
                "_id": f"urn:machina:sport:soccer:player:player-{number:04d}:20000101:t01",
                "machina_competition_slug": "world-cup-2026",
                "provider_ids": {"api_football": provider_id},
            },
        })
    evidence = [event, *players]
    original = copy.deepcopy(evidence)

    result = plan("master", evidence, expected_fixture_count=1, batch_size=1)
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":")).encode("utf-8")

    assert evidence == original
    assert len(encoded) < 40_000
    assert result["assessment_status"] == "blocked"
    assert result["batch"] == {"offset": 0, "size": 1, "returned": 1, "total": 1, "next_offset": None}
    assert result["entity_coverage"]["player_count"] == 4999
    assert result["array_metadata"]["fixtures"] == {"total": 1, "returned": 1, "truncated": False, "consumed": 1, "oversized_omitted": 0}
    assert result["array_metadata"]["entity_coverage.players"]["total"] == 4999
    assert result["array_metadata"]["entity_coverage.players"]["truncated"] is True
    assert result["array_metadata"]["missing_work"]["total"] >= 4999
    assert result["array_metadata"]["missing_work"]["truncated"] is True
    assert result["entity_coverage"]["players"][0]["evidence"][0]["document_id"] == "player-doc-0000"
    assert result["array_metadata"]["entity_coverage.players[0].provider_id_evidence.api_football"] == {
        "total": 1,
        "returned": 0,
        "truncated": True,
    }
    assert any("global counts" in warning and "pagination remain complete" in warning for warning in result["warnings"])
