"""Contract tests for the World Cup 2026 final archive metadata."""

from pathlib import Path

import yaml


TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = TEMPLATE_ROOT / "workflows"
ARCHIVE_WORKFLOWS = {
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
}
REQUIRED_FIELDS = {
    "mode",
    "competition",
    "competition_status",
    "live",
    "snapshot_as_of",
    "capability_status",
    "provenance",
    "missing_capabilities",
    "notes",
}
LEGACY_OUTPUTS = {
    "worldcup-resolve": {"entity", "entities", "count", "warnings", "workflow-status"},
    "worldcup-get-schedule": {"schedule", "workflow-status"},
    "worldcup-get-event-context": {"event_context", "event_urn", "resolved_fixture", "warnings", "workflow-status"},
    "worldcup-get-standings": {"standings", "workflow-status"},
    "worldcup-get-squads": {"squads", "workflow-status"},
    "worldcup-get-injuries": {"injuries", "workflow-status"},
    "worldcup-get-player-performance-context": {"player_performance_context", "status", "warnings", "workflow-status"},
    "worldcup-get-match-forecast": {"forecast", "model_vs_market", "analysis", "warnings", "workflow-status"},
    "worldcup-backtest-forecasts": {"finished_fixtures", "status", "provenance", "warnings", "audited_count", "track_record", "clv_settled_count", "clv_report", "workflow-status"},
    "worldcup-match-recap": {"skill_card", "event_urn", "resolved_fixture", "served_from", "warnings", "workflow-status"},
    "worldcup-player-spotlight": {"skill_card", "player_urn", "resolved_player", "candidates", "served_from", "warnings", "workflow-status"},
}
SAFE_BUILTINS = {
    "dict": dict,
    "len": len,
    "list": list,
    "max": max,
    "str": str,
}


def load_workflow(name):
    path = WORKFLOW_DIR / f"{name}.yml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))["workflow"]


def task(workflow, name):
    return next(item for item in workflow["tasks"] if item["name"] == name)


def evaluate(expression, context):
    namespace = {"__builtins__": {}, **SAFE_BUILTINS, "context": context}
    return eval(expression.replace("$.get", "context.get"), namespace, namespace)


def archive(name, context):
    return evaluate(load_workflow(name)["outputs"]["archive"], context)


def test_exactly_the_requested_workflows_expose_archive_metadata():
    workflows_with_archive = {
        yaml.safe_load(path.read_text(encoding="utf-8"))["workflow"]["name"]
        for path in WORKFLOW_DIR.glob("*.yml")
        if "archive" in yaml.safe_load(path.read_text(encoding="utf-8"))["workflow"].get("outputs", {})
    }

    assert workflows_with_archive == ARCHIVE_WORKFLOWS


def test_archive_output_is_additive_to_existing_contracts():
    for name, legacy_fields in LEGACY_OUTPUTS.items():
        assert legacy_fields <= load_workflow(name)["outputs"].keys(), name


def test_all_archive_outputs_parse_and_evaluate_with_required_constants():
    contexts = {
        "worldcup-resolve": {"entities": [{"_id": "team"}], "resolution_provenance": ["worldcup:identity-crosswalk"]},
        "worldcup-get-schedule": {"schedule": {"events": [{"event_urn": "event"}]}, "events": [{}]},
        "worldcup-get-event-context": {"event_context": {"event": {"event_urn": "event"}, "sports_context": {"score": "2-1"}}},
        "worldcup-get-standings": {"standings": {"groups": [{"group": "A"}], "source": "api-football"}},
        "worldcup-get-squads": {"squads": {"teams": [{"source": "api-football"}]}},
        "worldcup-get-injuries": {"injuries": {"teams": [], "source": "api-football"}},
        "worldcup-get-player-performance-context": {"normalized_players": [{"eligible_for_power_ranking": True}], "resolved_official_fifa_power_ranking": {"status": "available", "as_of": "2026-07-19T23:00:00Z"}},
        "worldcup-get-match-forecast": {"forecast": {"data_source": "seed", "model": {"computed_at": "2026-07-19T12:00:00Z"}}},
        "worldcup-backtest-forecasts": {"backtesting_report": {"sample_size": 104, "sample_size_sufficient": True}, "audits": [{"audited_at": "2026-07-20T01:00:00Z"}], "fixture_provenance": "api-football-live", "forecasts": [{}]},
        "worldcup-match-recap": {"cached": {"body": {}, "generated_at": "2026-07-20T02:00:00Z"}},
        "worldcup-player-spotlight": {"cached": {"body": {}, "generated_at": "2026-07-20T03:00:00Z"}},
    }

    for name, context in contexts.items():
        result = archive(name, context)
        assert REQUIRED_FIELDS <= result.keys(), name
        assert result["mode"] == "final_archive", name
        assert result["competition"] == "FIFA World Cup 2026", name
        assert result["competition_status"] == "completed", name
        assert result["live"] is False, name
        assert isinstance(result["provenance"], list), name
        assert isinstance(result["missing_capabilities"], list), name
        assert isinstance(result["notes"], list), name


def test_complete_collection_endpoints_require_data():
    cases = {
        "worldcup-resolve": ({"entities": [{}]}, {"entities": []}),
        "worldcup-get-schedule": ({"schedule": {"events": [{}]}}, {"schedule": {"events": []}}),
        "worldcup-get-standings": ({"standings": {"groups": [{}]}}, {"standings": {"groups": []}}),
        "worldcup-get-squads": ({"squads": {"teams": [{}]}}, {"squads": {"teams": []}}),
    }

    for name, (populated, empty) in cases.items():
        assert archive(name, populated)["capability_status"] == "complete"
        assert archive(name, empty)["capability_status"] == "unavailable"


def test_event_context_is_partial_without_optional_enrichment():
    bare = archive("worldcup-get-event-context", {"event_context": {"event": {"event_urn": "event"}}})
    enriched = archive("worldcup-get-event-context", {"event_context": {"event": {"event_urn": "event"}, "prematch_research": {"summary": "stored"}}})
    absent = archive("worldcup-get-event-context", {"event_context": {"event": {}}})

    assert bare["capability_status"] == "partial"
    assert bare["missing_capabilities"] == ["event_enrichment"]
    assert enriched["capability_status"] == "complete"
    assert enriched["provenance"] == ["worldcup:event", "google-genai-grounded-search"]
    assert absent["capability_status"] == "unavailable"


def test_injuries_do_not_infer_complete_coverage_from_an_empty_feed():
    empty = archive("worldcup-get-injuries", {"injuries": {"source": "api-football", "teams": [{"count": 0}]}})
    explicit = archive("worldcup-get-injuries", {"injuries": {"source": "api-football", "teams": [], "coverage_complete": True}})

    assert empty["capability_status"] == "partial"
    assert empty["missing_capabilities"] == ["verified_complete_injury_coverage"]
    assert explicit["capability_status"] == "complete"
    assert explicit["missing_capabilities"] == []


def test_performance_exposes_completed_fifa_final_states():
    not_ranked = archive("worldcup-get-player-performance-context", {
        "normalized_players": [{"eligible_for_power_ranking": True}],
        "resolved_official_fifa_power_ranking": {"status": "not_ranked"},
    })
    ineligible = archive("worldcup-get-player-performance-context", {
        "normalized_players": [{"eligible_for_power_ranking": False}],
        "resolved_official_fifa_power_ranking": {"status": "not_eligible"},
    })
    official_only = archive("worldcup-get-player-performance-context", {
        "normalized_players": [],
        "resolved_official_fifa_power_ranking": {"status": "available"},
    })

    assert not_ranked["capability_status"] == "complete"
    assert not_ranked["missing_capabilities"] == []
    assert ineligible["capability_status"] == "complete"
    assert ineligible["missing_capabilities"] == []
    assert official_only["capability_status"] == "partial"
    assert "provider_player_statistics" in official_only["missing_capabilities"]

    no_player = archive("worldcup-get-player-performance-context", {
        "normalized_players": [],
        "resolved_official_fifa_power_ranking": {"status": "pending"},
    })
    assert no_player["capability_status"] == "unavailable"


def test_forecast_is_historical_and_uses_only_stored_model_time():
    stored = archive("worldcup-get-match-forecast", {
        "forecast": {"data_source": "blend", "model": {"computed_at": "2026-07-18T08:00:00Z"}},
        "model_vs_market": {"gaps": []},
        "market_outcomes": [{"name": "Brazil", "price": 0.6}],
    })
    missing = archive("worldcup-get-match-forecast", {})
    workflow_text = (WORKFLOW_DIR / "worldcup-get-match-forecast.yml").read_text(encoding="utf-8").lower()
    prompt_text = (TEMPLATE_ROOT / "prompts/worldcup-match-forecast-explain.yml").read_text(encoding="utf-8").lower()

    assert stored["capability_status"] == "historical_model"
    assert stored["snapshot_as_of"] == "2026-07-18T08:00:00Z"
    assert stored["provenance"] == ["worldcup:model-forecast", "api-football", "fifa-ranking-seed", "worldcup:market-cache"]
    assert missing["capability_status"] == "unavailable"
    assert missing["snapshot_as_of"] is None
    assert "live model-vs-market" not in workflow_text
    assert "current market price" not in workflow_text + prompt_text


def test_backtest_exposes_historical_sample_without_fabricating_cutoff():
    result = archive("worldcup-backtest-forecasts", {
        "backtesting_report": {"sample_size": 2, "sample_size_sufficient": False},
        "audits": [
            {"audited_at": "2026-07-19T10:00:00Z"},
            {"audited_at": "2026-07-20T10:00:00Z"},
        ],
        "fixture_provenance": "worldcup-event-cache",
        "forecasts": [{}],
    })

    assert result["capability_status"] == "historical_aggregate"
    assert result["sample_size"] == 2
    assert result["cutoff"] is None
    assert result["snapshot_as_of"] is None
    assert result["missing_capabilities"] == ["statistically_sufficient_sample"]

    stored = archive("worldcup-backtest-forecasts", {
        "backtesting_report": {
            "sample_size": 2,
            "sample_size_sufficient": False,
            "cutoff": "2026-07-20T10:00:00Z",
        },
        "audits": [{"audited_at": "2026-08-31T23:59:59Z"}],
    })
    assert stored["cutoff"] == "2026-07-20T10:00:00Z"
    assert stored["snapshot_as_of"] == stored["cutoff"]


def test_document_snapshot_outputs_use_stored_evidence_and_never_request_time():
    resolve_workflow = load_workflow("worldcup-resolve")
    schedule_workflow = load_workflow("worldcup-get-schedule")
    documents = [
        {"name": "worldcup:event", "value": {"updated_at": "2026-07-19T20:00:00Z"}},
        {"name": "worldcup:identity-crosswalk", "created": "2026-06-01T00:00:00Z", "value": {}},
    ]

    resolve_task = task(resolve_workflow, "resolve-entity")
    schedule_task = task(schedule_workflow, "load-events")
    assert evaluate(resolve_task["outputs"]["resolution_snapshot_as_of"], {"documents": documents}) == "2026-07-19T20:00:00Z"
    assert evaluate(resolve_task["outputs"]["resolution_provenance"], {"documents": documents}) == ["worldcup:identity-crosswalk", "worldcup:event"]
    assert evaluate(schedule_task["outputs"]["schedule_snapshot_as_of"], {"documents": []}) is None


def test_cached_editorial_statuses_expose_generated_at_without_fabrication():
    recap = archive("worldcup-match-recap", {"cached": {"generated_at": "2026-07-20T02:00:00Z"}})
    spotlight = archive("worldcup-player-spotlight", {"cached": {"generated_at": "2026-07-20T03:00:00Z"}})
    generated_recap = archive("worldcup-match-recap", {"recap": {"headline": "Final"}})
    generated_spotlight = archive("worldcup-player-spotlight", {"spotlight": {"headline": "Player"}})

    assert recap["capability_status"] == "evergreen_editorial"
    assert recap["snapshot_as_of"] == "2026-07-20T02:00:00Z"
    assert spotlight["capability_status"] == "archived_editorial"
    assert spotlight["snapshot_as_of"] == "2026-07-20T03:00:00Z"
    assert generated_recap["snapshot_as_of"] is None
    assert generated_spotlight["snapshot_as_of"] is None


def test_final_player_ranking_import_is_source_backed_and_atomic():
    workflow = yaml.safe_load(
        (WORKFLOW_DIR / "worldcup-import-final-fifa-player-rankings.yml").read_text(encoding="utf-8")
    )["workflow"]
    prepare = task(workflow, "prepare-final-player-rankings")
    save = task(workflow, "import-final-player-rankings")

    assert prepare["connector"]["command"] == "import_final_fifa_player_power_rankings"
    assert prepare["inputs"]["source_url"] == "'https://fdh-api.fifa.com/v1/powerranking/season/285023.json'"
    assert save["documents"]["items"] == "$.get('final_ranking_documents', [])"
    assert "published_count" in save["condition"]
    assert "231" in save["condition"]


def test_spotlight_adds_tournament_overview_without_removing_legacy_outputs():
    workflow = load_workflow("worldcup-player-spotlight")
    assert "player_overview" in workflow["outputs"]
    assert LEGACY_OUTPUTS["worldcup-player-spotlight"] <= workflow["outputs"].keys()
