"""Design Log 054 contracts for World Cup provider truth and API envelopes."""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml


TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = TEMPLATE_ROOT / "worldcup-market-intelligence.py"
SPEC = importlib.util.spec_from_file_location("worldcup_provider_contract", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def load_workflow(name):
    return yaml.safe_load(
        (TEMPLATE_ROOT / "workflows" / f"{name}.yml").read_text(encoding="utf-8")
    )["workflow"]


def task(workflow, name):
    return next(item for item in workflow["tasks"] if item["name"] == name)


def evaluate(expression, response):
    namespace = {
        "__builtins__": {},
        "all": all,
        "dict": dict,
        "isinstance": isinstance,
        "len": len,
        "list": list,
        "str": str,
        "response": response,
    }
    return eval(expression.replace("$.get", "response.get"), namespace, namespace)


def event(status="2H", **overrides):
    value = {
        "_id": "urn:machina:sport:soccer:event:brazil-vs-spain:20260620:wor",
        "schema:startDate": (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
        "sport:status": status,
        "provider_ids": {"api_football": "1489389"},
        "machina_competition_slug": "world-cup-2026",
        "live_score": {"home": 1, "away": 1, "elapsed": 90},
    }
    value.update(overrides)
    return value


def provider_fixture(status):
    return {
        "fixture": {
            "id": 1489389,
            "status": {"short": status, "elapsed": 120 if status != "FT" else 90},
        },
        "goals": {"home": 2, "away": 2 if status == "PEN" else 1},
        "score": {
            "halftime": {"home": 1, "away": 0},
            "fulltime": {"home": 1, "away": 1},
            "extratime": {"home": 2, "away": 2 if status == "PEN" else 1},
            "penalty": {"home": 5, "away": 4} if status == "PEN" else {"home": None, "away": None},
        },
    }


def incomplete_provider_fixture(status, goals=None, score=None):
    fixture = provider_fixture(status)
    fixture["goals"] = goals if goals is not None else {"home": None, "away": None}
    fixture["score"] = score if score is not None else {}
    return fixture


def test_api_football_terminal_status_set_is_exact():
    assert MODULE._TERMINAL_STATUS == {"FT", "AET", "PEN", "CANC", "ABD", "AWD", "WO"}


@pytest.mark.parametrize("terminal_status", ["FT", "AET", "PEN"])
def test_reconciliation_preserves_exact_terminal_status_and_score_phases(terminal_status):
    reconcile = getattr(MODULE, "reconcile_fixture_status", None)
    assert callable(reconcile)

    result = reconcile({
        "params": {
            "events": [event()],
            "terminal_fixtures": [{"response": [provider_fixture(terminal_status)]}],
            "attempted_fixture_ids": ["1489389"],
            "observed_at": "2026-06-20T22:15:00Z",
        }
    })["data"]

    assert result["count"] == 1
    reconciled = result["normalized_items"][0]
    assert reconciled["sport:status"] == terminal_status
    assert reconciled["score"] == provider_fixture(terminal_status)["score"]
    assert reconciled["final_data_status"] == "provider_confirmed"
    assert reconciled["terminal_observed_at"] == "2026-06-20T22:15:00Z"
    assert reconciled["version_control"]["terminal-retry-count"] == 0
    assert reconciled["version_control"]["terminal-retry-exhausted"] is False
    assert reconciled["version_control"]["terminal-reconciled"] is True
    assert reconciled["final_score_complete"] is True


@pytest.mark.parametrize(
    ("terminal_status", "provider_row"),
    [
        ("FT", incomplete_provider_fixture("FT", goals={"home": 2, "away": None})),
        ("PEN", incomplete_provider_fixture("PEN")),
    ],
)
def test_incomplete_terminal_observation_stays_pending_and_preserves_cached_scores(
    terminal_status, provider_row
):
    prior = event(
        status="2H",
        live_score={"home": 1, "away": 1, "elapsed": 90},
        score={"fulltime": {"home": 1, "away": 1}},
        version_control={"terminal-retry-count": 2, "terminal-retry-exhausted": False},
    )

    result = MODULE.reconcile_fixture_status({"params": {
        "events": [prior],
        "terminal_fixtures": [{"response": [provider_row]}],
        "attempted_fixture_ids": ["1489389"],
        "observed_at": "2026-06-20T22:15:00Z",
    }})["data"]["normalized_items"][0]

    assert result["sport:status"] == terminal_status
    assert result["final_data_status"] == "pending_confirmation"
    assert result["final_score_complete"] is False
    assert result["live_score"] == prior["live_score"]
    assert result["score"] == prior["score"]
    assert "terminal_observed_at" not in result
    assert result["version_control"]["terminal-retry-count"] == 3
    assert result["version_control"]["next_retry_at"] == "2026-06-20T22:25:00Z"


def test_complete_penalty_observation_is_provider_confirmed():
    result = MODULE.reconcile_fixture_status({"params": {
        "events": [event()],
        "terminal_fixtures": [{"response": [provider_fixture("PEN")]}],
        "attempted_fixture_ids": ["1489389"],
        "observed_at": "2026-06-20T22:15:00Z",
    }})["data"]["normalized_items"][0]

    assert result["final_data_status"] == "provider_confirmed"
    assert result["final_score_complete"] is True
    assert result["score"]["penalty"] == {"home": 5, "away": 4}


def test_incomplete_terminal_row_from_live_feed_enters_bounded_pending_retry():
    prior = event(
        status="2H",
        version_control={"terminal-retry-count": 1, "terminal-retry-exhausted": False},
    )
    result = MODULE.reconcile_fixture_status({"params": {
        "events": [prior],
        "live_fixtures": {"response": [incomplete_provider_fixture("FT")]},
        "observed_at": "2026-06-20T22:15:00Z",
    }})["data"]["normalized_items"][0]

    assert result["sport:status"] == "FT"
    assert result["final_data_status"] == "pending_confirmation"
    assert result["version_control"]["terminal-retry-count"] == 2
    assert result["version_control"]["next_retry_at"] == "2026-06-20T22:25:00Z"


def test_complete_live_terminal_row_beats_incomplete_exact_row():
    result = MODULE.reconcile_fixture_status({"params": {
        "events": [event()],
        "live_fixtures": {"response": [provider_fixture("PEN")]},
        "terminal_fixtures": [{"response": [incomplete_provider_fixture("PEN")]}],
        "attempted_fixture_ids": ["1489389"],
        "observed_at": "2026-06-20T22:15:00Z",
    }})["data"]["normalized_items"][0]

    assert result["sport:status"] == "PEN"
    assert result["final_data_status"] == "provider_confirmed"
    assert result["final_score_complete"] is True
    assert result["score"]["penalty"] == {"home": 5, "away": 4}


def test_stale_finalization_is_explicitly_inferred_and_retries_are_bounded():
    reconcile = getattr(MODULE, "reconcile_fixture_status", None)
    assert callable(reconcile)

    current = event(**{"schema:startDate": "2026-06-20T18:00:00Z"})
    for expected_attempt in range(1, 6):
        observed_at = f"2026-06-20T{21 + (expected_attempt - 1) // 6:02d}:{((expected_attempt - 1) % 6) * 10:02d}:00Z"
        result = reconcile({"params": {
            "events": [current],
            "terminal_fixtures": [{"response": []}],
            "attempted_fixture_ids": ["1489389"],
            "observed_at": observed_at,
        }})["data"]
        current = result["normalized_items"][0]
        assert current["sport:status"] == "FT"
        assert current["final_data_status"] == "inferred_stale"
        assert "terminal_observed_at" not in current
        assert current["version_control"]["terminal-retry-count"] == expected_attempt
        assert current["version_control"]["terminal-retry-exhausted"] is (expected_attempt == 5)
        assert current["version_control"]["terminal-reconciled"] is False
        assert current["version_control"]["next_retry_at"] == (
            datetime.fromisoformat(observed_at.replace("Z", "+00:00")) + timedelta(minutes=10)
        ).isoformat().replace("+00:00", "Z")

    exhausted = reconcile({"params": {
        "events": [current],
        "terminal_fixtures": [{"response": []}],
        "attempted_fixture_ids": ["1489389"],
        "observed_at": "2026-06-20T22:00:00Z",
    }})["data"]
    assert exhausted["normalized_items"] == []


def test_recent_unobserved_fixture_retries_without_inventing_a_final_status():
    recent = event(
        status="NS",
        live_score={},
        **{"schema:startDate": "2026-06-20T18:00:00Z"},
    )
    result = MODULE.reconcile_fixture_status({
        "params": {
            "events": [recent],
            "terminal_fixtures": [{"response": []}],
            "attempted_fixture_ids": ["1489389"],
            "observed_at": "2026-06-20T21:00:00Z",
        }
    })["data"]["normalized_items"][0]

    assert result["sport:status"] == "NS"
    assert result["final_data_status"] == "pending_confirmation"
    assert "terminal_observed_at" not in result
    assert result["version_control"]["terminal-retry-count"] == 1
    assert result["version_control"]["next_retry_at"] == "2026-06-20T21:10:00Z"


def test_stale_nonterminal_provider_row_uses_persisted_retry_state():
    stale = event(
        status="NS",
        live_score={"home": 0, "away": 0},
        version_control={
            "terminal-retry-count": 2,
            "terminal-retry-exhausted": False,
            "next_retry_at": "2026-06-20T21:10:00Z",
        },
        **{"schema:startDate": "2026-06-20T18:00:00Z"},
    )
    selected = MODULE.select_terminal_reconciliation({"params": {
        "events": [stale],
        "observed_at": "2026-06-21T01:00:00Z",
    }})["data"]
    assert selected["fixture_ids"] == ["1489389"]

    result = MODULE.reconcile_fixture_status({"params": {
        "events": [stale],
        "terminal_fixtures": [{"response": [incomplete_provider_fixture("NS")]}],
        "attempted_fixture_ids": ["1489389"],
        "observed_at": "2026-06-21T01:00:00Z",
    }})["data"]["normalized_items"][0]

    assert result["sport:status"] == "NS"
    assert result["final_data_status"] == "pending_confirmation"
    assert result["version_control"]["terminal-retry-count"] == 3
    assert result["version_control"]["next_retry_at"] == "2026-06-21T01:10:00Z"


def test_early_incomplete_terminal_row_does_not_reset_throttled_retry_state():
    pending = event(
        status="FT",
        final_data_status="pending_confirmation",
        final_score_complete=False,
        version_control={
            "terminal-retry-count": 2,
            "terminal-retry-exhausted": False,
            "next_retry_at": "2026-06-20T22:20:00Z",
        },
    )

    result = MODULE.reconcile_fixture_status({"params": {
        "events": [pending],
        "live_fixtures": {"response": [incomplete_provider_fixture("FT")]},
        "observed_at": "2026-06-20T22:15:00Z",
    }})["data"]

    assert result["normalized_items"] == []


def test_incomplete_terminal_row_cannot_downgrade_confirmed_final_truth():
    confirmed = event(
        status="PEN",
        final_data_status="provider_confirmed",
        final_score_complete=True,
        terminal_observed_at="2026-06-20T22:10:00Z",
        score=provider_fixture("PEN")["score"],
        version_control={"terminal-reconciled": True, "terminal-retry-count": 0},
    )

    result = MODULE.reconcile_fixture_status({"params": {
        "events": [confirmed],
        "terminal_fixtures": [{"response": [incomplete_provider_fixture("PEN")]}],
        "attempted_fixture_ids": ["1489389"],
        "observed_at": "2026-06-20T22:20:00Z",
    }})["data"]

    assert result["normalized_items"] == []


def test_terminal_reconciliation_selection_honors_due_time_and_max_attempts():
    select = getattr(MODULE, "select_terminal_reconciliation", None)
    assert callable(select)
    base = event(
        status="FT",
        final_data_status="inferred_stale",
        **{"schema:startDate": "2026-06-20T18:00:00Z"},
    )
    due = dict(base, version_control={
        "terminal-retry-count": 4,
        "terminal-retry-exhausted": False,
        "next_retry_at": "2026-06-20T21:00:00Z",
    })
    throttled = dict(base, _id="urn:throttled", provider_ids={"api_football": "2"}, version_control={
        "terminal-retry-count": 2,
        "terminal-retry-exhausted": False,
        "next_retry_at": "2026-06-20T21:10:01Z",
    })
    exhausted = dict(base, _id="urn:exhausted", provider_ids={"api_football": "3"}, version_control={
        "terminal-retry-count": 5,
        "terminal-retry-exhausted": True,
        "next_retry_at": "2026-06-20T20:00:00Z",
    })

    result = select({"params": {
        "events": [due, throttled, exhausted],
        "observed_at": "2026-06-20T21:10:00Z",
    }})["data"]

    assert result["fixture_ids"] == ["1489389"]
    assert result["count"] == 1


def test_reconciliation_only_consumes_a_due_exact_attempt():
    pending = event(
        status="FT",
        final_data_status="inferred_stale",
        version_control={
            "terminal-retry-count": 2,
            "terminal-retry-exhausted": False,
            "next_retry_at": "2026-06-20T21:10:00Z",
        },
        **{"schema:startDate": "2026-06-20T18:00:00Z"},
    )

    early = MODULE.reconcile_fixture_status({"params": {
        "events": [pending],
        "terminal_fixtures": [{"response": []}],
        "attempted_fixture_ids": ["1489389"],
        "observed_at": "2026-06-20T21:09:59Z",
    }})["data"]
    assert early["normalized_items"] == []

    due = MODULE.reconcile_fixture_status({"params": {
        "events": [pending],
        "terminal_fixtures": [{"response": []}],
        "attempted_fixture_ids": ["1489389"],
        "observed_at": "2026-06-20T21:10:00Z",
    }})["data"]["normalized_items"][0]
    assert due["version_control"]["terminal-retry-count"] == 3
    assert due["version_control"]["next_retry_at"] == "2026-06-20T21:20:00Z"


def test_coverage_signals_keep_only_terminal_reconciliation_retries_hot():
    pending = event(
        status="FT",
        final_data_status="inferred_stale",
        version_control={"terminal-retry-count": 2, "terminal-retry-exhausted": False},
    )
    exhausted = event(
        status="FT",
        final_data_status="inferred_stale",
        version_control={"terminal-retry-count": 5, "terminal-retry-exhausted": True},
        _id="urn:exhausted",
    )

    result = MODULE.compute_coverage_signals({"params": {"events": [pending, exhausted]}})["data"]

    assert result["terminal_reconciliation_pending"] is True
    assert result["terminal_reconciliation_count"] == 1


def test_hot_agent_runs_status_refresh_for_pending_reconciliation_without_market_refresh():
    agent = yaml.safe_load(
        (TEMPLATE_ROOT / "agents" / "worldcup-coverage-hot-agent.yml").read_text(encoding="utf-8")
    )["agent"]
    workflows = {item["name"]: item for item in agent["workflows"]}

    assert workflows["worldcup-sync-market-sources"]["condition"] == "$.get('has_live') is True"
    assert "terminal_reconciliation_pending" in workflows["worldcup-refresh-live-status"]["condition"]


def test_provider_confirmation_supersedes_an_inferred_stale_final():
    inferred = event(
        status="FT",
        final_data_status="inferred_stale",
        version_control={"terminal-retry-count": 3, "terminal-retry-exhausted": False},
    )
    result = MODULE.reconcile_fixture_status({
        "params": {
            "events": [inferred],
            "terminal_fixtures": [{"response": [provider_fixture("PEN")]}],
            "attempted_fixture_ids": ["1489389"],
            "observed_at": "2026-06-20T22:20:00Z",
        }
    })["data"]["normalized_items"][0]

    assert result["sport:status"] == "PEN"
    assert result["final_data_status"] == "provider_confirmed"
    assert result["score"]["penalty"] == {"home": 5, "away": 4}
    assert result["version_control"]["terminal-retry-count"] == 0


def test_terminal_observed_at_is_the_first_provider_confirmation_time():
    confirmed = event(
        status="FT",
        final_data_status="provider_confirmed",
        terminal_observed_at="2026-06-20T22:15:00Z",
    )
    result = MODULE.reconcile_fixture_status({
        "params": {
            "events": [confirmed],
            "terminal_fixtures": [{"response": [provider_fixture("FT")]}],
            "attempted_fixture_ids": ["1489389"],
            "observed_at": "2026-06-21T01:00:00Z",
        }
    })["data"]["normalized_items"][0]

    assert result["terminal_observed_at"] == "2026-06-20T22:15:00Z"


def test_nonterminal_provider_observation_clears_stale_final_inference():
    inferred = event(
        status="FT",
        final_data_status="inferred_stale",
        version_control={"terminal-retry-count": 2, "terminal-retry-exhausted": False},
    )
    observed = provider_fixture("HT")
    result = MODULE.reconcile_fixture_status({
        "params": {"events": [inferred], "live_fixtures": {"response": [observed]}}
    })["data"]["normalized_items"][0]

    assert result["sport:status"] == "HT"
    assert result["final_data_status"] == "not_final"
    assert "terminal_observed_at" not in result
    assert result["version_control"]["terminal-retry-count"] == 0


def test_live_refresh_loads_cache_then_fetches_only_exact_terminal_fixture_ids():
    workflow = load_workflow("worldcup-refresh-live-status")
    names = [item["name"] for item in workflow["tasks"]]

    assert names[:2] == ["load-events", "select-terminal-reconciliation"]
    assert "fetch-live-fixtures" in names
    assert "fetch-recent-fixtures" not in names
    exact = task(workflow, "fetch-terminal-fixtures")
    assert exact["continue_on_error"] is True
    assert "from" not in exact["inputs"]
    assert "to" not in exact["inputs"]
    assert exact["foreach"]["value"] == "$.get('terminal_fixture_ids', [])"
    assert exact["inputs"] == {"id": "$.get('terminal_fixture_id')"}
    assert "terminal_fixtures" in exact["outputs"]
    reconcile = task(workflow, "reconcile-fixture-status")
    assert reconcile["connector"]["command"] == "reconcile_fixture_status"
    assert reconcile["inputs"]["live_fixtures"] == "$.get('live_fixtures', {})"
    assert reconcile["inputs"]["terminal_fixtures"] == "$.get('terminal_fixtures', [])"
    assert reconcile["inputs"]["attempted_fixture_ids"] == "$.get('terminal_fixture_ids', [])"
    assert "finalize-stale-live-events" not in names


def test_ingest_marks_provider_terminal_truth_and_preserves_score_phases():
    result = MODULE.mint_event_identity({
        "params": {
            "fixtures": [dict(
                provider_fixture("AET"),
                fixture={
                    **provider_fixture("AET")["fixture"],
                    "date": "2026-06-20T19:00:00+00:00",
                    "venue": {"name": "Final Stadium", "city": "City"},
                },
                teams={"home": {"name": "Brazil"}, "away": {"name": "Spain"}},
                league={"round": "Round of 16"},
            )],
            "observed_at": "2026-06-20T22:15:00Z",
        }
    })["data"]["events"][0]

    assert result["sport:status"] == "AET"
    assert result["score"] == provider_fixture("AET")["score"]
    assert result["final_data_status"] == "provider_confirmed"
    assert result["terminal_observed_at"] == "2026-06-20T22:15:00Z"
    assert result["final_score_complete"] is True


def test_ingest_does_not_confirm_incomplete_terminal_score_evidence():
    fixture = dict(
        incomplete_provider_fixture("PEN"),
        fixture={
            **incomplete_provider_fixture("PEN")["fixture"],
            "date": "2026-06-20T19:00:00+00:00",
        },
        teams={"home": {"name": "Brazil"}, "away": {"name": "Spain"}},
    )
    previous = event(
        live_score={"home": 1, "away": 1, "elapsed": 120},
        score={"extratime": {"home": 1, "away": 1}},
        version_control={"terminal-retry-count": 1, "terminal-retry-exhausted": False},
    )
    result = MODULE.mint_event_identity({"params": {
        "fixtures": [fixture],
        "existing_events": [previous],
        "observed_at": "2026-06-20T22:15:00Z",
    }})["data"]["events"][0]

    assert result["final_data_status"] == "pending_confirmation"
    assert result["final_score_complete"] is False
    assert result["live_score"] == previous["live_score"]
    assert result["score"] == previous["score"]
    assert result["version_control"]["terminal-retry-count"] == 2
    assert result["version_control"]["next_retry_at"] == "2026-06-20T22:25:00Z"
    assert "terminal_observed_at" not in result


def test_ingest_preserves_and_advances_due_stale_nonterminal_retry_state():
    fixture = dict(
        incomplete_provider_fixture("NS"),
        fixture={
            **incomplete_provider_fixture("NS")["fixture"],
            "date": "2026-06-20T18:00:00+00:00",
        },
        teams={"home": {"name": "Brazil"}, "away": {"name": "Spain"}},
    )
    previous = event(
        status="NS",
        final_data_status="pending_confirmation",
        final_score_complete=False,
        version_control={
            "terminal-retry-count": 2,
            "terminal-retry-exhausted": False,
            "next_retry_at": "2026-06-20T21:10:00Z",
        },
        **{"schema:startDate": "2026-06-20T18:00:00+00:00"},
    )

    result = MODULE.mint_event_identity({"params": {
        "fixtures": [fixture],
        "existing_events": [previous],
        "observed_at": "2026-06-21T01:00:00Z",
    }})["data"]["events"][0]

    assert result["sport:status"] == "NS"
    assert result["final_data_status"] == "pending_confirmation"
    assert result["final_score_complete"] is False
    assert result["version_control"]["terminal-retry-count"] == 3
    assert result["version_control"]["next_retry_at"] == "2026-06-21T01:10:00Z"


def test_ingest_incomplete_terminal_row_preserves_confirmed_final_truth():
    fixture = dict(
        incomplete_provider_fixture("PEN"),
        fixture={
            **incomplete_provider_fixture("PEN")["fixture"],
            "date": "2026-06-20T18:00:00+00:00",
        },
        teams={"home": {"name": "Brazil"}, "away": {"name": "Spain"}},
    )
    previous = event(
        status="PEN",
        final_data_status="provider_confirmed",
        final_score_complete=True,
        terminal_observed_at="2026-06-20T22:10:00Z",
        score=provider_fixture("PEN")["score"],
        version_control={"terminal-reconciled": True, "terminal-retry-count": 0},
    )

    result = MODULE.mint_event_identity({"params": {
        "fixtures": [fixture],
        "existing_events": [previous],
        "observed_at": "2026-06-20T22:20:00Z",
    }})["data"]["events"][0]

    assert result["sport:status"] == "PEN"
    assert result["final_data_status"] == "provider_confirmed"
    assert result["final_score_complete"] is True
    assert result["terminal_observed_at"] == "2026-06-20T22:10:00Z"
    assert result["score"] == previous["score"]


def test_ingest_preserves_the_first_terminal_observation_from_existing_event():
    fixture = dict(
        provider_fixture("FT"),
        fixture={
            **provider_fixture("FT")["fixture"],
            "date": "2026-06-20T19:00:00+00:00",
        },
        teams={"home": {"name": "Brazil"}, "away": {"name": "Spain"}},
    )
    result = MODULE.mint_event_identity({
        "params": {
            "fixtures": [fixture],
            "existing_events": [{
                "provider_ids": {"api_football": "1489389"},
                "final_data_status": "provider_confirmed",
                "terminal_observed_at": "2026-06-20T22:15:00Z",
                "version_control": {"terminal-reconciled-timestamp": "2026-06-20T22:15:00Z"},
            }],
            "observed_at": "2026-06-21T05:00:00Z",
        }
    })["data"]["events"][0]

    assert result["terminal_observed_at"] == "2026-06-20T22:15:00Z"


def test_reusable_response_envelope_reports_per_capability_availability():
    builder = getattr(MODULE, "build_response_envelope", None)
    assert callable(builder)

    envelope = builder({
        "params": {
            "capabilities": {"schedule": "available", "terminal_scores": "partial"},
            "required_capabilities": ["schedule", "terminal_scores"],
            "evidence": [{"kind": "document-cache", "count": 3}],
            "provenance": [{"provider": "api-football", "role": "match-data"}],
            "warnings": ["One final score is inferred."],
        }
    })["data"]

    assert envelope == {
        "status": "partial",
        "availability": {"schedule": "available", "terminal_scores": "partial"},
        "evidence": [{"kind": "document-cache", "count": 3}],
        "provenance": [{"provider": "api-football", "role": "match-data"}],
        "warnings": ["One final score is inferred."],
        "required_evidence": [
            {"capability": "schedule", "status": "available"},
            {"capability": "terminal_scores", "status": "partial"},
        ],
        "unavailable_reason": None,
    }


def test_response_envelope_preserves_provider_error_and_explains_missing_requirement():
    envelope = MODULE.build_response_envelope({"params": {
        "capabilities": {"event": "available", "research": "provider_error"},
        "required_capabilities": ["event", "research"],
    }})["data"]

    assert envelope["status"] == "partial"
    assert envelope["availability"]["research"] == "provider_error"
    assert envelope["required_evidence"] == [
        {"capability": "event", "status": "available"},
        {"capability": "research", "status": "provider_error"},
    ]
    assert "research (provider_error)" in envelope["unavailable_reason"]


@pytest.mark.parametrize(
    ("params", "served_from", "evidence_kind", "providers"),
    [
        (
            {
                "cached_card": {"headline": "Cached"},
                "generated_card": {"headline": "Ignored"},
                "subject_urn": "urn:event:1",
                "subject_key": "event_urn",
                "cached_provider": "worldcup:skill-match-preview-cache",
                "generated_provider": "google-genai",
                "generated_research": "research",
            },
            "cache",
            "cached-skill-card",
            ["worldcup:skill-match-preview-cache"],
        ),
        (
            {
                "generated_card": {"headline": "Generated"},
                "subject_urn": "urn:event:1",
                "subject_key": "event_urn",
                "cached_provider": "worldcup:skill-match-preview-cache",
                "generated_provider": "google-genai",
                "generated_research": "research",
            },
            "generated",
            "generated-skill-card",
            ["google-genai", "google-genai"],
        ),
    ],
)
def test_skill_envelope_attributes_only_the_path_that_produced_the_card(
    params, served_from, evidence_kind, providers
):
    result = MODULE.build_skill_response_envelope({"params": params})["data"]

    assert result["served_from"] == served_from
    assert result["evidence"] == [{"kind": evidence_kind, "subject_urn": "urn:event:1"}]
    assert [item["provider"] for item in result["provenance"]] == providers


def test_unavailable_skill_envelope_does_not_claim_generated_evidence():
    result = MODULE.build_skill_response_envelope({"params": {
        "generated_card": {"provider_error": "generation failed"},
        "subject_urn": "urn:event:1",
        "subject_key": "event_urn",
        "generated_provider": "google-genai",
        "required_capabilities": ["skill_card"],
    }})["data"]

    assert result["skill_card"] == {}
    assert result["served_from"] == "unavailable"
    assert result["status"] == "unavailable"
    assert result["availability"]["skill_card"] == "provider_error"
    assert result["evidence"] == []
    assert result["provenance"] == []
    assert result["unavailable_reason"]


def test_normalized_read_models_include_envelopes_and_never_label_squads_as_lineups():
    schedule_event = event(
        status="PEN",
        final_data_status="provider_confirmed",
        final_score_complete=True,
    )
    schedule_event["score"] = provider_fixture("PEN")["score"]
    schedule = MODULE.normalize_schedule({"params": {"events": [schedule_event]}})["data"]
    injuries = MODULE.normalize_injuries({
        "params": {"af": {"errors": [], "results": 0, "response": []}, "home_team_id": 1, "home_team": "Brazil"}
    })["data"]
    squads = MODULE.normalize_squads({
        "params": {"home_af": {"response": [{"team": {"id": 1, "name": "Brazil"}, "players": [{"id": 10, "name": "Player"}]}]}}
    })["data"]

    for payload in (schedule, injuries, squads):
        assert set(payload) >= {"status", "availability", "evidence", "provenance", "warnings"}
    assert schedule["availability"]["terminal_results"] == "available"
    assert schedule["events"][0]["provider_status"] == "PEN"
    assert schedule["events"][0]["score_phases"] == provider_fixture("PEN")["score"]
    assert injuries["availability"]["injuries"] == "available"
    assert squads["availability"]["squads"] == "available"
    assert squads["availability"]["lineups"] == "unavailable"
    assert squads["teams"][0]["kind"] == "squad"
    assert "lineup" not in squads["teams"][0]


def projection_document(
    name,
    *,
    event_code="urn:machina:sport:soccer:event:brazil-vs-spain:20260620:wor",
    source_event_document_id="event-document-1",
    observed_at="2026-06-20T22:15:00Z",
    status="available",
    facts=None,
    unavailable_reason=None,
):
    value = {
        "event_code": event_code,
        "source_event_document_id": source_event_document_id,
        "provider_fixture_id": 1489389,
        "provider_envelope": {"response": [{"provider_only": True}]},
        "facts": list(facts or []),
    }
    if unavailable_reason is not None:
        value["unavailable_reason"] = unavailable_reason
    return {
        "_id": f"{name}:{observed_at}",
        "name": name,
        "metadata": {
            "event_code": event_code,
            "source_event_document_id": source_event_document_id,
            "observed_at": observed_at,
            "status": status,
            "provider": {"namespace": "api-football", "family": "licensed"},
            "provenance": {
                "provider": {"namespace": "api-football", "family": "licensed"},
                "observed_at": observed_at,
            },
        },
        "value": value,
    }


def test_event_context_assembles_canonical_event_and_latest_exact_bound_projections():
    assemble = getattr(MODULE, "assemble_event_context", None)
    assert callable(assemble)

    event_code = "urn:machina:sport:soccer:event:brazil-vs-spain:20260620:wor"
    canonical_event = {
        "@id": event_code,
        "@type": ["sport:Event", "schema:SportsEvent"],
        "name": "Brazil vs Spain",
        "sport:competitors": [{"@id": "urn:team:brazil"}, {"@id": "urn:team:spain"}],
        "squads": [{"team": "Brazil", "players": ["Roster player"]}],
    }
    documents = {
        "actions_documents": [
            projection_document(
                "api-football-event-actions",
                observed_at="2026-06-20T22:14:00Z",
                facts=[{"type": "old-action"}],
            ),
            projection_document(
                "api-football-event-actions",
                observed_at="2026-06-20T22:16:00Z",
                facts=[{"type": "goal"}],
            ),
        ],
        "lineups_documents": [
            projection_document(
                "api-football-event-lineups",
                facts=[{"team_id": "urn:team:brazil", "starting": []}],
            )
        ],
        "team_statistics_documents": [
            projection_document(
                "api-football-event-team-statistics",
                facts=[{"team_id": "urn:team:brazil", "statistics": []}],
            )
        ],
        "player_statistics_documents": [
            projection_document(
                "api-football-event-player-statistics",
                status="unavailable",
                unavailable_reason="provider returned zero results",
            )
        ],
    }

    result = assemble({
        "params": {
            "event_document": {
                "_id": "event-document-1",
                "metadata": {"event_code": event_code},
                "value": canonical_event,
            },
            **documents,
        }
    })["data"]

    assert result["event_context"]["event"] == canonical_event
    assert result["event_context"]["event"] is not canonical_event
    assert "provider_fixture_id" not in result["event_context"]["event"]
    assert "provider_envelope" not in result["event_context"]["event"]
    assert result["event_context"]["actions"]["facts"] == [{"type": "goal"}]
    assert result["event_context"]["actions"]["observed_at"] == "2026-06-20T22:16:00Z"
    assert result["event_context"]["actions"]["status"] == "available"
    assert result["event_context"]["actions"]["unavailable_reason"] is None
    assert result["event_context"]["lineups"]["facts"] == [
        {"team_id": "urn:team:brazil", "starting": []}
    ]
    assert result["event_context"]["player_statistics"]["status"] == "unavailable"
    assert result["event_context"]["player_statistics"]["unavailable_reason"] == (
        "provider returned zero results"
    )
    for capability in ("actions", "lineups", "team_statistics", "player_statistics"):
        assert set(result["event_context"][capability]) >= {
            "observed_at",
            "status",
            "unavailable_reason",
        }
    assert result["status"] == "partial"
    assert result["availability"] == {
        "event": "available",
        "actions": "available",
        "lineups": "available",
        "team_statistics": "available",
        "player_statistics": "unavailable",
    }
    assert {"provider": "worldcup:event", "role": "canonical-event"} in result["provenance"]
    assert set(result) >= {"status", "availability", "evidence", "provenance", "warnings"}


@pytest.mark.parametrize(
    ("metadata_override", "warning_fragment"),
    [
        ({"event_code": "urn:event:other"}, "event_code"),
        ({"source_event_document_id": "event-document-other"}, "source_event_document_id"),
    ],
)
def test_event_context_rejects_cross_event_projections(metadata_override, warning_fragment):
    event_code = "urn:machina:sport:soccer:event:brazil-vs-spain:20260620:wor"
    projection = projection_document(
        "api-football-event-actions",
        event_code=metadata_override.get("event_code", event_code),
        source_event_document_id=metadata_override.get(
            "source_event_document_id", "event-document-1"
        ),
        facts=[{"type": "must-not-leak"}],
    )

    result = MODULE.assemble_event_context({
        "params": {
            "event_document": {
                "_id": "event-document-1",
                "metadata": {"event_code": event_code},
                "value": {"@id": event_code, "name": "Brazil vs Spain"},
            },
            "actions_documents": [projection],
        }
    })["data"]

    assert result["event_context"]["actions"] == {
        "facts": [],
        "observed_at": None,
        "status": "unavailable",
        "unavailable_reason": "No exact-bound actions projection is available.",
    }
    assert result["availability"]["actions"] == "unavailable"
    assert any(warning_fragment in warning for warning in result["warnings"])


def test_event_context_never_uses_squads_as_lineups():
    event_code = "urn:machina:sport:soccer:event:brazil-vs-spain:20260620:wor"
    result = MODULE.assemble_event_context({
        "params": {
            "event_document": {
                "_id": "event-document-1",
                "metadata": {"event_code": event_code},
                "value": {
                    "@id": event_code,
                    "squads": [{"team": "Brazil", "players": ["Roster player"]}],
                },
            }
        }
    })["data"]

    assert result["event_context"]["event"]["squads"]
    assert result["event_context"]["lineups"]["facts"] == []
    assert result["event_context"]["lineups"]["status"] == "unavailable"


def test_event_context_workflow_loads_latest_exact_bound_projection_documents():
    workflow = load_workflow("worldcup-get-event-context")
    outputs = workflow["outputs"]
    assert set(outputs) >= {"status", "availability", "evidence", "provenance", "warnings"}

    lookup = task(workflow, "lookup-event")
    assert lookup["outputs"]["event_document"] == "($.get('documents', []) or [{}])[0]"
    assert "source_event_document_id" in lookup["outputs"]
    assert "resolved_event_code" in lookup["outputs"]

    expected = {
        "load-event-actions": "api-football-event-actions",
        "load-event-lineups": "api-football-event-lineups",
        "load-event-team-statistics": "api-football-event-team-statistics",
        "load-event-player-statistics": "api-football-event-player-statistics",
    }
    for task_name, document_name in expected.items():
        projection = task(workflow, task_name)
        assert projection["filters"] == {
            "name": repr(document_name),
            "metadata.event_code": "$.get('resolved_event_code')",
            "metadata.source_event_document_id": "$.get('source_event_document_id')",
        }
        assert projection["config"]["search-sorters"] == [
            ["metadata.observed_at", -1],
            ["_id", -1],
        ]
        assert projection["config"]["search-limit"] == 1

    assemble = task(workflow, "assemble-event-context")
    assert assemble["connector"]["command"] == "assemble_event_context"
    assert "squad" not in str(assemble).lower()


@pytest.mark.parametrize(
    "workflow_name",
    [
        "worldcup-get-schedule",
        "worldcup-get-event-context",
        "worldcup-get-injuries",
        "worldcup-get-squads",
        "worldcup-get-player-performance-context",
        "worldcup-get-match-forecast",
        "worldcup-backtest-forecasts",
        "worldcup-match-preview",
        "worldcup-match-recap",
    ],
)
def test_public_provider_workflows_expose_the_common_envelope(workflow_name):
    outputs = load_workflow(workflow_name)["outputs"]
    assert set(outputs) >= {
        "status",
        "availability",
        "evidence",
        "provenance",
        "warnings",
        "required_evidence",
        "unavailable_reason",
    }


def test_partner_agent_and_skill_wrappers_preserve_envelope_fields():
    agent = yaml.safe_load(
        (TEMPLATE_ROOT / "agents" / "world-cup-intelligence-agent.yml").read_text(
            encoding="utf-8"
        )
    )["agent"]
    partner_names = {
        "worldcup-match-preview",
        "worldcup-match-recap",
        "worldcup-player-spotlight",
        "worldcup-fan-pulse",
    }
    for workflow in agent["workflows"]:
        if workflow["name"] in partner_names:
            assert set(workflow["outputs"]) >= {
                "status",
                "availability",
                "evidence",
                "provenance",
                "warnings",
                "required_evidence",
                "unavailable_reason",
            }

    skill = yaml.safe_load(
        (TEMPLATE_ROOT.parents[1] / "skills" / "world-cup-intelligence" / "skill.yml").read_text(
            encoding="utf-8"
        )
    )["skill"]
    fan_pulse = next(
        workflow for workflow in skill["workflows"] if workflow["name"] == "worldcup-fan-pulse"
    )
    assert set(fan_pulse["outputs"]) >= {
        "status",
        "availability",
        "evidence",
        "provenance",
        "warnings",
        "required_evidence",
        "unavailable_reason",
    }


@pytest.mark.parametrize(
    "workflow_name",
    [
        "worldcup-match-preview",
        "worldcup-match-recap",
        "worldcup-player-spotlight",
        "worldcup-fan-pulse",
    ],
)
def test_partner_skill_workflows_expose_truthful_complete_envelopes(workflow_name):
    workflow = load_workflow(workflow_name)
    assert set(workflow["outputs"]) >= {
        "status",
        "availability",
        "evidence",
        "provenance",
        "warnings",
        "required_evidence",
        "unavailable_reason",
    }
    assert task(workflow, "build-response-envelope")["connector"]["command"] == (
        "build_skill_response_envelope"
    )


def test_match_recap_requires_provider_confirmed_finality():
    workflow = load_workflow("worldcup-match-recap")
    load_event = task(workflow, "load-event")

    assert "final_data_status" in load_event["outputs"]["is_final"]
    assert "provider_confirmed" in load_event["outputs"]["is_final"]
    assert "final_score_complete" in load_event["outputs"]["is_final"]


def test_health_probes_are_optional_and_provider_selected():
    workflow = load_workflow("worldcup-health")
    assert workflow["inputs"]["probe_providers"] == "$.get('probe_providers', [])"

    api_probe = task(workflow, "probe-api-football")
    sports_skills_probe = task(workflow, "probe-sports-skills")
    assert "api-football" in api_probe["condition"]
    assert "sports-skills" in sports_skills_probe["condition"]
    assert api_probe["continue_on_error"] is True
    assert sports_skills_probe["continue_on_error"] is True
    assert "next" not in api_probe["inputs"]
    assert api_probe["inputs"]["date"] == "'2026-06-20'"
    assert set(workflow["outputs"]) >= {"status", "availability", "evidence", "provenance"}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"response": [{"fixture": {"id": 1489389}}], "errors": {}}, True),
        ({"response": [], "errors": {}}, False),
        ({"response": [{"fixture": {}}], "errors": {}}, False),
        ({"response": [{"fixture": {"id": 1489389}}], "errors": {"date": "bad"}}, False),
    ],
)
def test_api_football_health_requires_a_non_error_usable_fixture_payload(payload, expected):
    probe = task(load_workflow("worldcup-health"), "probe-api-football")
    assert evaluate(probe["outputs"]["api_football_probe_ok"], payload) is expected


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"response": [{"fixture": {"id": 1489389}}], "errors": {}}, "available"),
        ({"response": [], "errors": {}}, "unavailable"),
        ({"response": [], "errors": {"request": "upstream failed"}}, "provider_error"),
    ],
)
def test_api_football_health_preserves_provider_error_status(payload, expected):
    workflow = load_workflow("worldcup-health")
    probe = task(workflow, "probe-api-football")
    build = task(workflow, "build-response-envelope")

    assert evaluate(probe["outputs"]["api_football_probe_status"], payload) == expected
    assert "api_football_probe_status" in build["inputs"]["capabilities"]


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"data": {"events": [{"id": "760447", "competitors": [{}, {}]}]}}, True),
        ({"message": "upstream failure", "data": {"events": [{"id": "760447", "competitors": [{}, {}]}]}}, False),
        ({"status": True, "data": {"events": []}}, False),
        ({"status": True, "data": {"events": [{"id": "760447"}]}}, False),
        ({"status": True, "data": {"error": "upstream failure"}}, False),
    ],
)
def test_sports_skills_health_requires_a_non_error_usable_fixture_payload(payload, expected):
    probe = task(load_workflow("worldcup-health"), "probe-sports-skills")
    assert probe["inputs"]["command"] == "'get_daily_schedule'"
    assert evaluate(probe["outputs"]["sports_skills_probe_ok"], payload) is expected


def test_health_evidence_includes_requested_sports_skills_probe_result():
    build = task(load_workflow("worldcup-health"), "build-response-envelope")
    evidence = evaluate(build["inputs"]["evidence"], {
        "store_reachable": True,
        "probe_providers": ["sports-skills"],
        "sports_skills_probe_ok": True,
        "sports_skills_probe_count": 3,
    })

    assert evidence == [
        {"kind": "document-store-read", "available": True},
        {
            "kind": "provider-health-probe",
            "provider": "sports-skills",
            "available": True,
            "result_count": 3,
        },
    ]
