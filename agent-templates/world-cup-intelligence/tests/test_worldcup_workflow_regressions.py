"""Regression tests for public World Cup Intelligence workflow contracts."""

import importlib.util
from pathlib import Path

import yaml


TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = TEMPLATE_ROOT / "worldcup-market-intelligence.py"
SPEC = importlib.util.spec_from_file_location("worldcup_workflow_regressions", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SAFE_BUILTINS = {
    "dict": dict,
    "isinstance": isinstance,
    "len": len,
    "str": str,
}


def load_yaml(relative_path):
    return yaml.safe_load(
        (TEMPLATE_ROOT / relative_path).read_text(encoding="utf-8")
    )


def task(workflow, name):
    return next(item for item in workflow["tasks"] if item["name"] == name)


def evaluate(expression, response):
    namespace = {
        "__builtins__": {},
        **SAFE_BUILTINS,
        "response": response,
    }
    expression = expression.replace("$.get", "response.get")
    return eval(expression, namespace, namespace)


def nested_mappings(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from nested_mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from nested_mappings(child)


def test_market_connector_declares_workflow_commands():
    connector = load_yaml("worldcup-market-intelligence.yml")["connector"]
    registered_commands = {command["value"] for command in connector["commands"]}
    workflow_paths = sorted((TEMPLATE_ROOT / "workflows").rglob("*.yml"))
    workflow_paths += sorted((TEMPLATE_ROOT / "workflows").rglob("*.yaml"))
    referenced_commands = {
        mapping["command"]
        for workflow_path in workflow_paths
        for mapping in nested_mappings(yaml.safe_load(workflow_path.read_text(encoding="utf-8")))
        if mapping.get("name") == connector["name"] and "command" in mapping
    }
    invalid_commands = {
        command: {
            "declared": command in registered_commands,
            "callable": callable(getattr(MODULE, command, None)),
        }
        for command in referenced_commands
        if command not in registered_commands or not callable(getattr(MODULE, command, None))
    }

    assert referenced_commands
    assert invalid_commands == {}


def test_backtest_uses_scoped_cached_final_events_when_live_provider_is_unavailable():
    workflow = load_yaml("workflows/worldcup-backtest-forecasts.yml")["workflow"]
    fetch = task(workflow, "fetch-finished-fixtures")
    cached = task(workflow, "load-cached-final-events")
    select = task(workflow, "select-finished-fixtures")
    documents = [
        {
            "value": {
                "machina_competition_slug": "world-cup-2026",
                "provider_ids": {"api_football": "101"},
                "sport:status": "FT",
                "final_data_status": "provider_confirmed",
                "live_score": {"home": 0, "away": 2},
            }
        },
        {
            "value": {
                "machina_competition_slug": "world-cup-2026",
                "provider_ids": {"api_football": "102"},
                "sport:status": "AET",
                "final_data_status": "provider_confirmed",
                "score": {
                    "fulltime": {"home": 1, "away": 1},
                    "extratime": {"home": 2, "away": 1},
                },
            }
        },
        {
            "value": {
                "machina_competition_slug": "world-cup-2026",
                "provider_ids": {"api_football": "103"},
                "sport:status": "PEN",
                "final_data_status": "provider_confirmed",
                "score": {
                    "fulltime": {"home": 1, "away": 1},
                    "extratime": {"home": 2, "away": 2},
                    "penalty": {"home": 5, "away": 4},
                },
            }
        },
        {
            "value": {
                "machina_competition_slug": "club-world-cup-2025",
                "provider_ids": {"api_football": "999"},
                "sport:status": "FT",
                "live_score": {"home": 9, "away": 0},
            }
        },
    ]

    assert fetch["continue_on_error"] is True
    assert cached["filters"]["name"] == "'worldcup:event'"
    assert cached["filters"]["value.machina_competition_slug"] == "'world-cup-2026'"
    assert "condition" not in cached
    assert "$.context" not in str(workflow)
    cached_events = evaluate(cached["outputs"]["cached_events"], {"documents": documents})
    result = MODULE.select_backtest_finished_fixtures({
        "params": {
            "live_fixtures": [],
            "cached_events": cached_events,
            "cached_search_limit_reached": False,
        }
    })["data"]
    adapted = result["finished_fixtures"]

    expected = [
        {
            "fixture": {"id": "101", "status": {"short": "FT"}},
            "goals": {"home": 0, "away": 2},
        },
        {
            "fixture": {"id": "102", "status": {"short": "AET"}},
            "goals": {"home": 2, "away": 1},
        },
        {
            "fixture": {"id": "103", "status": {"short": "PEN"}},
            "goals": {"home": 2, "away": 2},
            "score": {"penalty": {"home": 5, "away": 4}},
        },
    ]
    assert adapted == expected
    assert result["fixture_status"] == "partial"
    assert result["provenance"] == "worldcup-event-cache"
    assert "using cached World Cup 2026 final events" in result["warnings"][0]
    assert select["connector"]["command"] == "select_backtest_finished_fixtures"

    audit = MODULE.compute_forecast_audit(
        {
            "params": {
                "mode": "batch",
                "forecasts": [
                    {
                        "_id": "event-101",
                        "provider_ids": {"api_football": 101},
                        "probabilities": {
                            "home_win": 0.2,
                            "draw": 0.2,
                            "away_win": 0.6,
                        },
                    }
                ],
                "finished_fixtures": adapted,
            }
        }
    )["data"]
    assert audit["count"] == 1
    cached_context = {
        "fixture_provenance": result["provenance"],
        "audits": audit["audits"],
        "backtesting_report": {"sample_size": 1},
        "ledger_rows": [{}],
        "clv_settled": [{}],
        "clv_ledger": [{}],
        "clv_report": {"sample_size": 1},
    }
    for task_name in ("save-audits", "aggregate-audit", "save-aggregate"):
        assert evaluate(task(workflow, task_name)["condition"], cached_context) is True
    for task_name in ("settle-clv", "save-clv-settled", "aggregate-clv", "save-clv-report"):
        assert evaluate(task(workflow, task_name)["condition"], cached_context) is True


def test_cached_final_events_dedupe_same_score_to_richest_final_state():
    events = [
        {
            "machina_competition_slug": "world-cup-2026",
            "provider_ids": {"api_football": 201},
            "sport:status": "FT",
            "final_data_status": "provider_confirmed",
            "live_score": {"home": "2", "away": "2"},
        },
        {
            "machina_competition_slug": "world-cup-2026",
            "provider_ids": {"api_football": "201"},
            "sport:status": "AET",
            "final_data_status": "provider_confirmed",
            "score": {
                "fulltime": {"home": 1, "away": 1},
                "extratime": {"home": 2, "away": 2},
            },
        },
        {
            "machina_competition_slug": "world-cup-2026",
            "provider_ids": {"api_football": "201"},
            "sport:status": "PEN",
            "final_data_status": "provider_confirmed",
            "score": {
                "fulltime": {"home": 1, "away": 1},
                "extratime": {"home": "2", "away": "2"},
                "penalty": {"home": "10", "away": "9"},
            },
        },
        {
            "machina_competition_slug": "world-cup-2026",
            "provider_ids": {"api_football": "201"},
            "sport:status": "PEN",
            "final_data_status": "provider_confirmed",
            "score": {
                "extratime": {"home": 2, "away": 2},
                "penalty": {"home": 10, "away": 9},
            },
        },
    ]

    expected = [{
        "fixture": {"id": "201", "status": {"short": "PEN"}},
        "goals": {"home": 2, "away": 2},
        "score": {"penalty": {"home": 10, "away": 9}},
    }]
    forward = MODULE.select_backtest_finished_fixtures({
        "params": {"live_fixtures": [], "cached_events": events}
    })["data"]
    reverse = MODULE.select_backtest_finished_fixtures({
        "params": {"live_fixtures": [], "cached_events": list(reversed(events))}
    })["data"]

    assert forward["finished_fixtures"] == expected
    assert reverse["finished_fixtures"] == expected


def test_cached_aet_prefers_authoritative_extratime_over_stale_live_score():
    result = MODULE.select_backtest_finished_fixtures({
        "params": {
            "live_fixtures": [],
            "cached_events": [{
                "machina_competition_slug": "world-cup-2026",
                "provider_ids": {"api_football": "204"},
                "sport:status": "AET",
                "final_data_status": "provider_confirmed",
                "live_score": {"home": 1, "away": 1},
                "score": {
                    "fulltime": {"home": 1, "away": 1},
                    "extratime": {"home": 2, "away": 1},
                },
            }],
        }
    })["data"]

    assert result["finished_fixtures"][0]["goals"] == {"home": 2, "away": 1}


def test_cached_ft_prefers_fulltime_and_does_not_emit_penalties_as_goals():
    result = MODULE.select_backtest_finished_fixtures({
        "params": {
            "live_fixtures": [],
            "cached_events": [{
                "machina_competition_slug": "world-cup-2026",
                "provider_ids": {"api_football": "206"},
                "sport:status": "FT",
                "final_data_status": "provider_confirmed",
                "live_score": {"home": 1, "away": 0},
                "score": {
                    "fulltime": {"home": "2", "away": "0"},
                    "penalty": {"home": "5", "away": "4"},
                },
            }],
        }
    })["data"]

    assert result["finished_fixtures"] == [{
        "fixture": {"id": "206", "status": {"short": "FT"}},
        "goals": {"home": 2, "away": 0},
    }]


def test_cached_final_events_fail_closed_on_nonnumeric_scores():
    result = MODULE.select_backtest_finished_fixtures({
        "params": {
            "live_fixtures": [],
            "cached_events": [{
                "machina_competition_slug": "world-cup-2026",
                "provider_ids": {"api_football": "205"},
                "sport:status": "PEN",
                "final_data_status": "provider_confirmed",
                "score": {
                    "extratime": {"home": "two", "away": 1},
                    "penalty": {"home": "5", "away": "4"},
                },
            }],
        }
    })["data"]

    assert result["finished_fixtures"] == []


def test_cached_final_events_fail_closed_on_conflicting_scores_without_freshness():
    events = [
        {
            "machina_competition_slug": "world-cup-2026",
            "provider_ids": {"api_football": "202"},
            "sport:status": "FT",
            "final_data_status": "provider_confirmed",
            "live_score": {"home": 1, "away": 0},
        },
        {
            "machina_competition_slug": "world-cup-2026",
            "provider_ids": {"api_football": "202"},
            "sport:status": "FT",
            "final_data_status": "provider_confirmed",
            "score": {"home": 2, "away": 0},
        },
    ]

    forward = MODULE.select_backtest_finished_fixtures({
        "params": {"live_fixtures": [], "cached_events": events}
    })["data"]
    reverse = MODULE.select_backtest_finished_fixtures({
        "params": {"live_fixtures": [], "cached_events": list(reversed(events))}
    })["data"]

    assert forward["finished_fixtures"] == []
    assert reverse["finished_fixtures"] == []
    assert any("202" in warning and "conflicting final scores" in warning for warning in forward["warnings"])


def test_cached_final_events_prefer_provably_newer_elapsed_score():
    events = [
        {
            "machina_competition_slug": "world-cup-2026",
            "provider_ids": {"api_football": "203"},
            "sport:status": "FT",
            "final_data_status": "provider_confirmed",
            "live_score": {"home": 1, "away": 1, "elapsed": 90},
        },
        {
            "machina_competition_slug": "world-cup-2026",
            "provider_ids": {"api_football": "203"},
            "sport:status": "AET",
            "final_data_status": "provider_confirmed",
            "live_score": {"home": 2, "away": 1, "elapsed": 120},
        },
    ]

    result = MODULE.select_backtest_finished_fixtures({
        "params": {"live_fixtures": [], "cached_events": events}
    })["data"]
    reversed_result = MODULE.select_backtest_finished_fixtures({
        "params": {"live_fixtures": [], "cached_events": list(reversed(events))}
    })["data"]

    expected = [{
        "fixture": {"id": "203", "status": {"short": "AET"}},
        "goals": {"home": 2, "away": 1},
    }]
    assert result["finished_fixtures"] == expected
    assert reversed_result["finished_fixtures"] == expected


def test_cached_final_events_ignore_unproduced_sport_score_shape():
    result = MODULE.select_backtest_finished_fixtures({
        "params": {
            "live_fixtures": [],
            "cached_events": [{
                "machina_competition_slug": "world-cup-2026",
                "provider_ids": {"api_football": "999"},
                "sport:status": "FT",
                "final_data_status": "provider_confirmed",
                "sport:score": {"sport:homeScore": 3, "sport:awayScore": 0},
            }],
        }
    })["data"]

    assert result["finished_fixtures"] == []


def test_stale_inferred_cached_final_cannot_persist_audit_or_drive_clv():
    stale = MODULE.finalize_stale_live_events({
        "params": {
            "events": [{
                "_id": "urn:event:204",
                "schema:startDate": "2020-01-01T00:00:00+00:00",
                "sport:status": "2H",
                "live_score": {"home": 1, "away": 0, "elapsed": 90},
                "provider_ids": {"api_football": "204"},
                "machina_competition_slug": "world-cup-2026",
            }]
        }
    })["data"]["normalized_items"][0]
    selected = MODULE.select_backtest_finished_fixtures({
        "params": {"live_fixtures": [], "cached_events": [stale]}
    })["data"]
    workflow = load_yaml("workflows/worldcup-backtest-forecasts.yml")["workflow"]

    assert selected["finished_fixtures"] == []
    assert selected["fixture_status"] == "unavailable"
    assert selected["provenance"] == "none"
    assert any("provider-confirmed" in warning for warning in selected["warnings"])
    audit = MODULE.compute_forecast_audit({
        "params": {
            "mode": "batch",
            "forecasts": [{
                "_id": "event-204",
                "provider_ids": {"api_football": "204"},
                "probabilities": {"home_win": 0.7, "draw": 0.2, "away_win": 0.1},
            }],
            "finished_fixtures": selected["finished_fixtures"],
        }
    })["data"]
    assert audit["count"] == 0
    cached_context = {
        "fixture_provenance": selected["provenance"],
        "audits": audit["audits"],
        "backtesting_report": {"sample_size": 1},
        "ledger_rows": [{}],
        "clv_settled": [{}],
        "clv_ledger": [{}],
        "clv_report": {"sample_size": 1},
    }
    for task_name in ("save-audits", "aggregate-audit", "save-aggregate"):
        assert evaluate(task(workflow, task_name)["condition"], cached_context) is False
    for task_name in ("settle-clv", "save-clv-settled", "aggregate-clv", "save-clv-report"):
        assert evaluate(task(workflow, task_name)["condition"], cached_context) is False


def test_backtest_excludes_pending_and_legacy_unconfirmed_cached_finals():
    events = [
        {
            "machina_competition_slug": "world-cup-2026",
            "provider_ids": {"api_football": "301"},
            "sport:status": "FT",
            "final_data_status": "pending_confirmation",
            "live_score": {"home": 2, "away": 0},
        },
        {
            "machina_competition_slug": "world-cup-2026",
            "provider_ids": {"api_football": "302"},
            "sport:status": "FT",
            "live_score": {"home": 1, "away": 0},
        },
    ]

    result = MODULE.select_backtest_finished_fixtures({
        "params": {"live_fixtures": [], "cached_events": events}
    })["data"]

    assert result["finished_fixtures"] == []
    assert result["fixture_status"] == "unavailable"
    assert any("provider-confirmed" in warning for warning in result["warnings"])


def test_backtest_uses_confirmed_cache_when_live_final_score_is_incomplete():
    cached = {
        "machina_competition_slug": "world-cup-2026",
        "provider_ids": {"api_football": "401"},
        "sport:status": "FT",
        "final_data_status": "provider_confirmed",
        "score": {"fulltime": {"home": 2, "away": 1}},
    }
    live = [{
        "fixture": {"id": 400, "status": {"short": "FT"}},
        "goals": {"home": 1, "away": None},
    }]

    result = MODULE.select_backtest_finished_fixtures({
        "params": {"live_fixtures": live, "cached_events": [cached]}
    })["data"]

    assert result["finished_fixtures"] == [{
        "fixture": {"id": "401", "status": {"short": "FT"}},
        "goals": {"home": 2, "away": 1},
    }]
    assert result["fixture_status"] == "partial"
    assert result["provenance"] == "worldcup-event-cache"
    assert any("incomplete score evidence" in warning for warning in result["warnings"])


def test_backtest_prefers_live_final_fixtures_and_reuses_selection_downstream():
    workflow = load_yaml("workflows/worldcup-backtest-forecasts.yml")["workflow"]
    live = [
        {
            "fixture": {"id": 101, "status": {"short": "FT"}},
            "goals": {"home": 3, "away": 1},
        }
    ]

    result = MODULE.select_backtest_finished_fixtures({
        "params": {"live_fixtures": live, "cached_events": []}
    })["data"]

    assert result["finished_fixtures"] == live
    assert result["fixture_status"] == "available"
    assert result["provenance"] == "api-football-live"
    assert result["warnings"] == []
    assert task(workflow, "build-audits")["inputs"]["finished_fixtures"] == "$.get('finished_fixtures', [])"
    assert task(workflow, "settle-clv")["inputs"]["finished_fixtures"] == "$.get('finished_fixtures', [])"
    assert task(workflow, "settle-clv")["outputs"]["clv_ledger"] == "$.get('ledger', [])"
    assert task(workflow, "aggregate-clv")["inputs"]["clv_rows"] == "$.get('clv_ledger', [])"
    live_context = {
        "fixture_provenance": result["provenance"],
        "audits": [{}],
        "backtesting_report": {"sample_size": 1},
        "ledger_rows": [{}],
        "clv_settled": [{}],
        "clv_ledger": [{}],
        "clv_report": {"sample_size": 1},
    }
    for task_name in ("save-audits", "aggregate-audit", "save-aggregate"):
        assert evaluate(task(workflow, task_name)["condition"], live_context) is True
    for task_name in ("settle-clv", "save-clv-settled", "aggregate-clv", "save-clv-report"):
        assert evaluate(task(workflow, task_name)["condition"], live_context) is True


def test_backtest_warns_when_cached_event_search_may_be_truncated():
    result = MODULE.select_backtest_finished_fixtures({
        "params": {"live_fixtures": [], "cached_events": [], "cached_search_limit_reached": True}
    })["data"]

    assert result["fixture_status"] == "unavailable"
    assert any("may be incomplete" in warning for warning in result["warnings"])


def _player_workflow():
    return load_yaml("workflows/worldcup-get-player-performance-context.yml")["workflow"]


def test_player_stats_provider_uses_supported_inputs_and_filters_player_locally():
    workflow = _player_workflow()
    fetch = task(workflow, "fetch-player-stats-af")
    normalize = task(workflow, "normalize-player-match-stats")

    assert set(fetch["inputs"]) == {"fixture", "team"}
    assert normalize["inputs"]["player_id"] == "$.get('player_id')"


def test_player_context_returns_structured_unavailable_status_and_warnings():
    workflow = _player_workflow()
    merge = task(workflow, "merge-player-performance-context")
    event_document = {"_id": "urn:event:player-test", "name": "Brazil vs Spain"}
    context = {
        "event_document": event_document,
        "normalized_players": [],
        "normalize_warnings": ["No provider player match statistics supplied."],
        "official_fifa_power_ranking": {},
    }

    assert merge["condition"] == "len($.get('normalized_players', [])) > 0"
    assert merge["inputs"]["fallback_path"] == "['api-football']"
    assert evaluate(workflow["outputs"]["status"], context) == "unavailable"
    safe_context = evaluate(workflow["outputs"]["player_performance_context"], context)
    assert safe_context["event"] == event_document
    assert safe_context["player"] == {}
    assert safe_context["machina_provisional_performance_signal"]["status"] == "unavailable"
    warnings = evaluate(workflow["outputs"]["warnings"], context)
    assert "No provider player match statistics supplied." in warnings
    assert any("Official FIFA Power Ranking" in warning for warning in warnings)


def test_player_context_returns_partial_status_from_normalized_players():
    workflow = _player_workflow()
    context = {
        "normalized_players": [{"player_id": "10", "eligible_for_power_ranking": True, "warnings": []}],
        "normalize_warnings": [],
        "official_fifa_power_ranking": {},
    }

    assert evaluate(workflow["outputs"]["status"], context) == "partial"
    assert any("Official FIFA Power Ranking" in warning for warning in evaluate(workflow["outputs"]["warnings"], context))


def test_player_context_returns_available_status_from_normalized_players():
    workflow = _player_workflow()
    context = {
        "normalized_players": [{"player_id": "10", "eligible_for_power_ranking": True, "warnings": []}],
        "normalize_warnings": [],
        "official_fifa_power_ranking": {"status": "available"},
    }

    assert evaluate(workflow["outputs"]["status"], context) == "available"
    assert evaluate(workflow["outputs"]["warnings"], context) == []


def test_match_preview_cache_hit_loads_event_without_regeneration():
    workflow = load_yaml("workflows/worldcup-match-preview.yml")["workflow"]
    context = {
        "cached": {"body": {"headline": "Cached preview"}},
        "event_urn": "urn:event:cached-preview",
        "event": {},
    }

    assert evaluate(task(workflow, "load-event")["condition"], context) is True
    assert evaluate(task(workflow, "grounded-preview-research")["condition"], context) is False
    assert evaluate(task(workflow, "worldcup-match-preview")["condition"], context) is False
    assert evaluate(task(workflow, "save-candidate")["condition"], context) is False


def test_fan_sentiment_reports_grok_unavailability_in_successful_response():
    workflow = load_yaml("workflows/worldcup-fan-sentiment-context.yml")["workflow"]
    search = task(workflow, "social-search")

    assert search["continue_on_error"] is True
    assert evaluate(workflow["outputs"]["status"], {}) == "unavailable"
    warnings = evaluate(workflow["outputs"]["warnings"], {})
    assert warnings
    assert "live search returned no usable data" in warnings[0]
    assert "Possible causes include" in warnings[0]
    assert "authorization" not in warnings[0].lower()
    assert evaluate(
        workflow["outputs"]["status"], {"fan_sentiment": {"buzz_level": 4}}
    ) == "available"
    assert evaluate(
        workflow["outputs"]["warnings"], {"fan_sentiment": {"buzz_level": 4}}
    ) == []
