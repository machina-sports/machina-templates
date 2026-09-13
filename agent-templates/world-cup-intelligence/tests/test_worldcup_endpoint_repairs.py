"""Offline contract tests for the scoped World Cup storefront endpoint repairs."""

import importlib.util
import json
from pathlib import Path

import yaml


TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "worldcup_endpoint_repairs",
    TEMPLATE_ROOT / "worldcup-market-intelligence.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def workflow(name):
    return yaml.safe_load(
        (TEMPLATE_ROOT / "workflows" / f"{name}.yml").read_text(encoding="utf-8")
    )["workflow"]


def task(flow, name):
    return next(item for item in flow["tasks"] if item["name"] == name)


def evaluate(expression, response):
    if expression == "$":
        return response
    namespace = {"__builtins__": {}, "dict": dict, "len": len, "max": max, "str": str, "response": response}
    return eval(expression.replace("$.get", "response.get"), namespace, namespace)


def evaluate_outputs(workflow_task, response):
    return {key: evaluate(expression, response) for key, expression in workflow_task["outputs"].items()}


def event(urn, fixture_id, home, away, kickoff="2026-06-12T18:00:00Z", status="FT"):
    return {
        "_id": urn,
        "schema:startDate": kickoff,
        "sport:status": status,
        "machina_competition_slug": "world-cup-2026",
        "provider_ids": {"api_football": fixture_id, "sportradar": f"sr:{fixture_id}"},
        "sport:competitors": [
            {"@id": f"urn:team:{home.lower()}", "name": home, "sport:qualifier": "home"},
            {"@id": f"urn:team:{away.lower()}", "name": away, "sport:qualifier": "away"},
        ],
        "live_score": {"home": 1, "away": 0, "elapsed": 90},
    }


def test_public_player_performance_ignores_caller_forged_official_ranking():
    # Synthetic adversarial request, not provider evidence.
    forged = {"status": "available", "source": "fifa.com", "scores": {"attacking": 10.0}}
    request = {"official_fifa_power_ranking": forged}
    flow = workflow("worldcup-get-player-performance-context")
    assert evaluate(flow["inputs"]["official_fifa_power_ranking"], request) == {}
    selection = task(flow, "select-official-fifa-player-ranking")
    override = evaluate(selection["inputs"]["override"], request)
    assert override == {}
    result = MODULE.select_official_player_power_ranking({"params": {
        "override": override,
        "records": [],
        "snapshot_manifest": {},
        "player_name": "Synthetic Test Player",
        "identity_resolved": True,
    }})["data"]["official_fifa_power_ranking"]
    assert result["status"] == "pending"
    assert (result.get("scores") or {}).get("attacking") is None


def test_fixture_text_is_preserved_alongside_a_player_team_filter():
    fixtures = [
        event("urn:event:brazil-morocco", "101", "Brazil", "Morocco"),
        event("urn:event:brazil-japan", "102", "Brazil", "Japan"),
        event("urn:event:morocco-canada", "103", "Morocco", "Canada"),
    ]
    for team in ("Brazil", "Morocco"):
        result = MODULE.resolve_archived_fixture({"params": {
            "events": fixtures, "event": "Brazil vs Morocco", "team": team,
        }})["data"]
        assert result["event_urn"] == "urn:event:brazil-morocco"
        assert result["warnings"] == []
    contradictory = MODULE.resolve_archived_fixture({"params": {
        "events": fixtures, "event": "Brazil vs Morocco", "team": "Japan",
    }})["data"]
    assert contradictory["event"] == {}
    assert contradictory["warnings"]


def test_backtest_uses_the_three_outcome_mean_brier_uniform_baseline():
    # Synthetic audit: 0.23 loses to uniform 1X2 but would beat the wrong 0.25 threshold.
    row = {"fixture_id": "synthetic-fixture", "brier_scores": {"combined_1x2": 0.23, "over_2_5": 0.2}}
    result = MODULE._aggregate_audit([row])
    scores = result["brier_scores"]
    assert scores["baseline_random"] == round(2 / 9, 4)
    assert scores["baseline_random_1x2"] == round(2 / 9, 4)
    assert scores["baseline_random_over_2_5"] == 0.25
    assert scores["is_better_than_random"] is False
    row["brier_scores"]["combined_1x2"] = round(2 / 9, 4)
    assert MODULE._aggregate_audit([row])["brier_scores"]["is_better_than_random"] is False


def test_standings_recognizes_unlabelled_third_place_table_by_exact_membership():
    # Synthetic tables shaped like the observed provider's Group Stage aggregate.
    def group(name, team_ids):
        return {"name": name, "entries": [
            {"position": rank, "team": {"id": team_id, "name": f"Team {team_id}"}}
            for rank, team_id in enumerate(team_ids, 1)
        ]}
    groups = [group("Group A", [1, 2, 3, 4]), group("Group B", [5, 6, 7, 8]), group("Group Stage", [7, 3])]
    result = MODULE.normalize_standings({"params": {"ss": {"standings": groups}}})["data"]
    assert result["group_count"] == 2
    assert [row["team_id"] for row in result["third_place_ranking"]] == [7, 3]
    groups[-1] = group("Group Stage", [1, 5])  # Not the third-place teams: don't guess.
    unrelated = MODULE.normalize_standings({"params": {"ss": {"standings": groups}}})["data"]
    assert unrelated["group_count"] == 3
    assert unrelated["third_place_ranking"] == []


def test_fixture_resolution_is_exact_unique_and_never_chooses_first_ambiguity():
    events = [
        event("urn:event:brazil-morocco", "101", "Brazil", "Morocco"),
        event("urn:event:brazil-japan", "102", "Brazil", "Japan", "2026-06-20T18:00:00Z"),
    ]

    wrapped_events = [{"date": "2026-07-20T00:00:00Z", "value": item} for item in events]
    exact = MODULE.resolve_archived_fixture({"params": {"events": wrapped_events, "provider_event_id": "101"}})["data"]
    assert exact["event_urn"] == "urn:event:brazil-morocco"
    assert exact["provider_event_id"] == "101"
    assert exact["event"]["provider_ids"]["sportradar"] == "sr:101"
    assert exact["snapshot_as_of"] == "2026-07-20T00:00:00Z"
    assert exact["sources"][0]["source_timestamp"] == "2026-07-20T00:00:00Z"

    named = MODULE.resolve_archived_fixture({"params": {
        "events": events, "team": "morocco", "opponent": "Brazil", "date": "2026-06-12",
    }})["data"]
    assert named["event_urn"] == "urn:event:brazil-morocco"

    ambiguous = MODULE.resolve_archived_fixture({"params": {"events": events, "team": "Brazil"}})["data"]
    assert ambiguous["event"] == {}
    assert ambiguous["event_urn"] == ""
    assert len(ambiguous["candidates"]) == 2
    assert "ambiguous" in ambiguous["warnings"][0].lower()

    for params in ({}, {"team": "Atlantis"}):
        unresolved = MODULE.resolve_archived_fixture({"params": {"events": events, **params}})["data"]
        assert unresolved["event_urn"] == ""
        assert unresolved["provider_event_id"] == ""
        assert unresolved["warnings"]


def test_fixture_scoped_workflows_use_the_safe_resolver_before_provider_calls():
    names = (
        "worldcup-get-event-context",
        "worldcup-get-injuries",
        "worldcup-get-squads",
        "worldcup-get-match-forecast",
        "worldcup-get-player-performance-context",
        "worldcup-match-recap",
    )
    for name in names:
        flow = workflow(name)
        resolver = task(flow, "resolve-fixture")
        assert resolver["connector"]["command"] == "resolve_archived_fixture"
        assert resolver["inputs"]["events"] == "$.get('resolve_events', [])"
        assert "condition" not in resolver
        assert "candidates" in flow["outputs"]
        assert "resolution_warnings" in flow["outputs"]["warnings"]

        helper_data = MODULE.resolve_archived_fixture({"params": {
            "events": [event("urn:event:one", "101", "Brazil", "Morocco")],
            "provider_event_id": "101",
        }})["data"]
        wired = evaluate_outputs(resolver, helper_data)
        assert wired["event_urn"] == "urn:event:one"
        assert wired["resolved_fixture"]["fixture_id"] == "101"

    injuries = workflow("worldcup-get-injuries")
    assert "provider_event_id" in task(injuries, "fetch-injuries-af")["condition"]
    assert "not in (None, '')" in task(injuries, "fetch-injuries-af")["condition"]


def test_archived_squads_join_players_to_both_team_identities_and_preserve_timestamps():
    teams = [
        {"date": "2026-06-05T04:22:08Z", "value": {
            "@id": "urn:team:brazil", "@type": ["sport:IdentityCrosswalk", "sport:Team"],
            "name": "Brazil", "provider_ids": {"api_football": "6"},
            "machina_competition_slug": "world-cup-2026",
        }},
        {"date": "2026-06-05T04:22:08Z", "value": {
            "@id": "urn:team:morocco", "@type": ["sport:IdentityCrosswalk", "sport:Team"],
            "name": "Morocco", "provider_ids": {"api_football": "31"},
            "machina_competition_slug": "world-cup-2026",
        }},
    ]
    players = [
        {"date": "2026-06-05T17:34:27Z", "value": {
            "@id": "urn:player:one", "@type": ["sport:IdentityCrosswalk", "sport:Player"],
            "name": "Player One", "team": {"@id": "urn:team:brazil", "name": "Brazil"},
            "provider_ids": {"api_football": "10"}, "tournament_position": "Forward",
            "machina_competition_slug": "world-cup-2026",
        }},
        {"date": "2026-06-05T17:34:28Z", "value": {
            "@id": "urn:player:two", "@type": ["sport:IdentityCrosswalk", "sport:Player"],
            "name": "Player Two", "team": {"@id": "urn:team:morocco", "name": "Morocco"},
            "provider_ids": None, "position": None,
            "machina_competition_slug": "world-cup-2026",
        }},
        {"date": "2026-09-01T00:00:00Z", "value": {
            "@id": "urn:player:club", "@type": "sport:Player", "name": "Current Club Player",
            "team": {"@id": "urn:team:brazil"}, "machina_competition_slug": "club-2026",
        }},
    ]

    result = MODULE.build_archived_tournament_squads({"params": {
        "player_documents": players,
        "team_documents": teams,
        "home_team_urn": "urn:team:brazil",
        "away_team_urn": "urn:team:morocco",
    }})["data"]

    assert result["snapshot_type"] == "archived_tournament_identity_snapshot"
    assert result["evidence_status"] == "partial"
    assert [team["side"] for team in result["teams"]] == ["home", "away"]
    assert result["teams"][0]["team_identity"]["provider_ids"] == {"api_football": "6"}
    assert result["teams"][0]["players"][0]["source_timestamp"] == "2026-06-05T17:34:27Z"
    assert result["teams"][1]["players"][0]["provider_ids"] == {}
    assert all(player["name"] != "Current Club Player" for team in result["teams"] for player in team["players"])

    flow = workflow("worldcup-get-squads")
    connectors = {(item.get("connector") or {}).get("command") for item in flow["tasks"]}
    assert "get-players/squads" not in connectors
    assert "invoke_football" not in connectors
    assert evaluate_outputs(task(flow, "normalize-squads"), result)["squads"] == result


def test_forecast_integrity_and_market_timing_suppress_misleading_edges():
    forecast = {"model": {"computed_at": "2026-06-12T17:00:00Z"}, "probabilities": {"home_win": 0.6}}
    pre = MODULE.classify_archived_forecast({"params": {
        "forecast": forecast,
        "event": {"schema:startDate": "2026-06-12T18:00:00Z"},
        "markets": [{"fetched_at": "2026-06-12T17:30:00Z", "outcomes": [{"name": "Brazil", "price": 0.5}]}],
    }})["data"]
    assert pre["forecast_integrity"]["classification"] == "verified_pre_kickoff"
    assert pre["market_integrity"]["classification"] == "historical_prematch_quote"
    assert pre["market_outcomes"] == [{"name": "Brazil", "price": 0.5}]
    wired = evaluate_outputs(task(workflow("worldcup-get-match-forecast"), "classify-archive-evidence"), pre)
    assert wired["forecast_integrity"]["verified_pre_kickoff"] is True

    late = MODULE.classify_archived_forecast({"params": {
        "forecast": {"model": {"computed_at": "2026-06-12T18:00:01Z"}},
        "event": {"schema:startDate": "2026-06-12T18:00:00Z"},
        "markets": [{"fetched_at": "2026-06-12T20:00:00Z", "outcomes": [{"name": "Brazil", "price": 0.99}]}],
    }})["data"]
    assert late["forecast_integrity"]["classification"] == "at_or_after_kickoff"
    assert late["market_integrity"]["classification"] == "settled_or_late_cache"

    edge = MODULE.compute_model_vs_market_edge({"params": {
        "model_probabilities": {"home_win": 0.6},
        "market_outcomes": late["market_outcomes"],
        "home_team": "Brazil",
        "market_integrity": late["market_integrity"],
    }})["data"]
    assert edge["gaps"] == []
    assert edge["comparison_status"] == "suppressed_invalid_snapshot_timing"

    late_model = MODULE.compute_model_vs_market_edge({"params": {
        "model_probabilities": {"home_win": 0.6},
        "market_outcomes": pre["market_outcomes"],
        "home_team": "Brazil",
        "market_integrity": pre["market_integrity"],
        "forecast_integrity": late["forecast_integrity"],
    }})["data"]
    assert late_model["gaps"] == []
    assert late_model["comparison_status"] == "suppressed_invalid_snapshot_timing"


def test_archive_backtest_filters_late_forecasts_and_requires_regulation_scores():
    ft = event("urn:event:ft", "1", "A", "B")
    aet = event("urn:event:aet", "2", "C", "D", status="AET")
    aet["live_score"] = {"home": 2, "away": 1, "elapsed": 120}
    pen = event("urn:event:pen", "3", "E", "F", status="PEN")
    pen["live_score"] = {"home": 2, "away": 2, "elapsed": 120}
    pen["score"] = {"fulltime": {"home": 1, "away": 1}, "penalty": {"home": 5, "away": 4}}

    selected = MODULE.select_backtest_finished_fixtures({"params": {
        "competition": "world-cup-2026",
        "live_fixtures": [{"fixture": {"id": "999", "status": {"short": "FT"}}, "goals": {"home": 9, "away": 0}}],
        "cached_events": [ft, aet, pen],
    }})["data"]
    assert [row["fixture"]["id"] for row in selected["finished_fixtures"]] == ["1", "3"]
    assert selected["finished_fixtures"][1]["goals"] == {"home": 1, "away": 1}
    assert selected["excluded_count"] == 1
    assert selected["exclusion_reasons"] == {"missing_regulation_score": 1}
    assert selected["provenance"] == "worldcup-event-cache"

    forecasts = [
        {"_id": "urn:event:ft", "provider_ids": {"api_football": "1"},
         "model": {"computed_at": "2026-06-12T17:00:00Z"},
         "probabilities": {"home_win": 0.6, "draw": 0.2, "away_win": 0.2, "over_2_5": 0.4, "under_2_5": 0.6}},
        {"_id": "urn:event:pen", "provider_ids": {"api_football": "3"},
         "model": {"computed_at": "2026-06-12T18:00:00Z"},
         "probabilities": {"home_win": 0.3, "draw": 0.4, "away_win": 0.3, "over_2_5": 0.5, "under_2_5": 0.5}},
        {"_id": "urn:event:missing", "provider_ids": {"api_football": "4"},
         "model": {"computed_at": "not-a-time"},
         "probabilities": {"home_win": 0.3, "draw": 0.4, "away_win": 0.3, "over_2_5": 0.5, "under_2_5": 0.5}},
    ]
    audited = MODULE.compute_forecast_audit({"params": {
        "mode": "batch",
        "forecasts": forecasts,
        "finished_fixtures": selected["finished_fixtures"],
        "events": [ft, pen, event("urn:event:missing", "4", "G", "H")],
        "require_pre_kickoff": True,
    }})["data"]
    assert audited["total_count"] == 3
    assert audited["included_count"] == 1
    assert audited["excluded_count"] == 2
    assert audited["exclusion_reasons"] == {"forecast_at_or_after_kickoff": 1, "unparseable_forecast_timestamp": 1}
    assert audited["sources"] == ["worldcup:event", "worldcup:model-forecast"]

    malformed = MODULE.compute_forecast_audit({"params": {
        "mode": "batch",
        "forecasts": [{"_id": "no-provider-id", "model": {"computed_at": "2026-06-12T17:00:00Z"}}],
        "finished_fixtures": [],
        "events": [],
        "require_pre_kickoff": True,
    }})["data"]
    assert malformed["total_count"] == 1
    assert malformed["excluded_count"] == 1
    assert malformed["exclusion_reasons"] == {"missing_provider_fixture_id": 1}

    invalid_distribution = MODULE.compute_forecast_audit({"params": {
        "mode": "batch",
        "forecasts": [{"_id": "bad", "provider_ids": {"api_football": "1"},
                       "model": {"computed_at": "2026-06-12T17:00:00Z"},
                       "probabilities": {"home_win": 0.8, "draw": 0.8, "away_win": 0.2,
                                         "over_2_5": 0.4, "under_2_5": 0.4}}],
        "finished_fixtures": selected["finished_fixtures"],
        "events": [ft],
        "require_pre_kickoff": True,
    }})["data"]
    assert invalid_distribution["exclusion_reasons"] == {"invalid_probability_schema": 1}

    flow = workflow("worldcup-backtest-forecasts")
    assert "world-cup-2026" in task(flow, "fetch-finished-fixtures")["condition"]
    assert task(flow, "aggregate-audit")["condition"] == "len($.get('audits', [])) > 0"
    for item in flow["tasks"]:
        if item["name"].startswith("save-") or item["name"] in {"settle-clv", "settle-calibration", "compute-calibration"}:
            assert "api-football-live" in item.get("condition", "")


def test_recap_and_spotlight_cache_hits_still_return_archived_sources():
    recap = workflow("worldcup-match-recap")
    assert task(recap, "load-event")["condition"] == "$.get('event_urn', '') != ''"
    assert "historical_perspective" in recap["outputs"]["skill_card"]
    assert "event_sources" in recap["outputs"]["skill_card"]
    recap_prompt = yaml.safe_load((TEMPLATE_ROOT / "prompts/worldcup-match-recap.yml").read_text())["prompts"][0]
    assert "sources" in recap_prompt["schema"]["required"]
    assert "retrospective" in recap_prompt["instruction"].lower()
    cached_recap = evaluate(recap["outputs"]["skill_card"], {
        "cached": {"body": {"headline": "Original", "what_it_means": "Next match"}},
        "event_urn": "urn:event:one",
        "event_sources": [{"source": "worldcup:event", "provider_ids": {"api_football": "101"}}],
    })
    assert cached_recap["headline"] == "Original"
    assert cached_recap["what_it_means"] == "Next match"
    assert cached_recap["historical_perspective"] == "original_cached_matchday_copy"
    assert cached_recap["sources"][0]["provider_ids"]["api_football"] == "101"
    assert task(recap, "grounded-recap-research")["outputs"]["research_sources"] == "$.get('search_results', []) or []"
    assert recap["inputs"]["provider_event_id"] == "$.get('provider_event_id', '')"

    spotlight = workflow("worldcup-player-spotlight")
    assert task(spotlight, "load-player")["condition"] == "$.get('player_urn', '') != ''"
    ranking = task(spotlight, "load-final-fifa-performance")
    assert ranking["filters"]["value.player_urn"] == "$.get('player_urn', '')"
    assert "performance_context" in spotlight["outputs"]["skill_card"]
    assert "sources" in spotlight["outputs"]["skill_card"]
    missing = MODULE.build_tournament_player_overview({"params": {"player": {
        "@id": "urn:player:unranked", "name": "Unranked Player", "team": {"name": "Brazil"},
    }}})["data"]["player_overview"]
    assert missing["performance_context"]["status"] == "not_published"
    assert missing["sources"] == []


def test_player_name_resolution_is_explicit_and_ambiguous_names_do_not_select_first():
    players = [
        {"@type": ["sport:IdentityCrosswalk", "sport:Player"], "@id": "urn:p:1", "name": "Alex Smith",
         "team": {"@id": "urn:t:a", "name": "A"}, "provider_ids": {"api_football": "1"}},
        {"@type": ["sport:IdentityCrosswalk", "sport:Player"], "@id": "urn:p:2", "name": "Alex Smith",
         "team": {"@id": "urn:t:b", "name": "B"}, "provider_ids": {"api_football": "2"}},
    ]
    ambiguous = MODULE.resolve_player({"params": {"players": players, "player": "Alex Smith"}})["data"]
    assert ambiguous["player"] == {}
    assert len(ambiguous["candidates"]) == 2
    assert "ambiguous" in ambiguous["warnings"][0].lower()

    resolved = MODULE.resolve_player({"params": {"players": players, "player": "Alex Smith", "team": "B"}})["data"]
    assert resolved["player"]["player_urn"] == "urn:p:2"
    assert resolved["player"]["provider_ids"]["api_football"] == "2"

    flow = workflow("worldcup-get-player-performance-context")
    assert "player" in flow["inputs"] and "team" in flow["inputs"]
    assert task(flow, "score-provisional-performance")["inputs"]["player"] == "$.get('selected_player', {})"
    assert flow["inputs"]["provider_event_id"] == "$.get('provider_event_id', '')"
    fetch = task(flow, "fetch-player-stats-af")
    assert evaluate(fetch["condition"], {"fixture_id": "unknown", "resolved_fixture_id": "", "player_id": "10"}) is False


def test_canonical_openapi_has_exactly_eleven_complete_post_contracts():
    spec = json.loads((TEMPLATE_ROOT / "docs" / "openapi.json").read_text(encoding="utf-8"))
    assert spec["servers"] == [{
        "url": "https://agents.machina.gg/zcj/ajgpivnid8bn",
        "description": "Pay-per-use access to Machina Sports's API",
    }]
    assert len(spec["paths"]) == 11
    assert spec["components"]["schemas"]["FixtureSelector"]["anyOf"]
    assert all(set(methods) == {"post"} for methods in spec["paths"].values())
    for path, methods in spec["paths"].items():
        operation = methods["post"]
        schema = operation["requestBody"]["content"]["application/json"]["schema"]
        assert schema.get("type") == "object" or "$ref" in schema or "allOf" in schema or "anyOf" in schema, path
        assert operation["requestBody"]["content"]["application/json"].get("examples"), path
        assert "400" in operation["responses"], path
        assert operation["x-payment-info"], path
        expected_price = "0.400000" if "/skills/" in path else ("0.120000" if path.endswith(("backtest-forecasts", "get-match-forecast")) else "0.010000")
        assert operation["x-payment-info"]["price"] == {"mode": "fixed", "currency": "USD", "amount": expected_price}


def test_standings_no_body_defaults_remain_world_cup_2026():
    standings = workflow("worldcup-get-standings")
    fetch = task(standings, "fetch-standings-af")
    assert fetch["inputs"]["league"].endswith("or '1'")
    assert fetch["inputs"]["season"].endswith("or '2026'")
