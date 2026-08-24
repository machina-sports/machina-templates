"""Regression tests for the post-live / terminal reconciliation lane.

Mirrors the evaluation conventions in test_workflow_guards.py, extended with
`datetime`/`timedelta` in the eval namespace since the claim-query filters
under test (unlike the guard expressions covered there) use them.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import warnings

import yaml


CONNECTOR_ROOT = Path(__file__).resolve().parents[1]
SAFE_BUILTINS = {
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "str": str,
    "tuple": tuple,
}

# The terminal short codes this lane claims. Derived from
# EVENT_STATUS_BY_SHORT_CODE (tools/iptc/canonical/adapters/api_football.py):
# closed (FT, AET, PEN), cancelled (CANC), abandoned (ABD), and awarded
# (AWD, WO). PST (postponed) is deliberately excluded -- it denotes a
# reschedule-pending state, not a final one, and the same fixture can still
# return to NS/live under the same `sport:status` field.
TERMINAL_STATUSES = ["FT", "AET", "PEN", "CANC", "ABD", "AWD", "WO"]


def load_yaml(relative_path):
    return yaml.safe_load(
        (CONNECTOR_ROOT / relative_path).read_text(encoding="utf-8")
    )


def raw_eval(expression, namespace):
    # datetime.utcnow() -- the convention every existing filter in this
    # connector already uses -- is deprecated on newer Pythons. The
    # deprecation warning is raised from inside the eval'd code's own
    # frame, and pytest's warning capture then needs `__import__` while
    # formatting it, which a restricted `__builtins__: {}` sandbox does not
    # provide. That is a test-sandbox artifact, not a production bug, so it
    # is suppressed here rather than by touching the production expression.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return eval(expression, namespace, namespace)


def evaluate(expression, response, workflow_context=None):
    if expression.strip() == "$":
        return response
    namespace = {
        "__builtins__": {},
        **SAFE_BUILTINS,
        "datetime": datetime,
        "timedelta": timedelta,
        "context": workflow_context if workflow_context is not None else response,
    }
    expression = expression.replace("$.context", "context")
    expression = expression.replace("$.get", "response.get")
    namespace["response"] = response
    return raw_eval(expression, namespace)


def task(workflow, name):
    return next(item for item in workflow["tasks"] if item["name"] == name)


# ---------------------------------------------------------------------------
# api-football-event-consumer-postlive.yml
# ---------------------------------------------------------------------------


def _and_clauses(schedule):
    """Evaluate the dual-shape $and claim filter into its clause list."""
    namespace = {"__builtins__": {}, "datetime": datetime, "timedelta": timedelta}
    clauses = raw_eval(schedule["filters"]["$and"], namespace)
    assert isinstance(clauses, list) and len(clauses) == 3
    return clauses


def _clause_for(clauses, field):
    for clause in clauses:
        for branch in clause["$or"]:
            if field in branch:
                return clause["$or"]
    raise AssertionError(f"no $or clause carries {field}")


def test_consumer_postlive_claims_exactly_the_terminal_status_set():
    workflow = load_yaml("workflows/event-consumer-postlive.yml")["workflow"]
    schedule = task(workflow, "load-event-by-schedule")
    stuck = task(workflow, "load-stuck-events")

    status_or = _clause_for(_and_clauses(schedule), "value.sport:status")
    legacy = status_or[0]["value.sport:status"]
    canonical = status_or[1]["value.event_view.status"]
    stuck_filter = raw_eval(
        stuck["filters"]["value.sport:status"],
        {"__builtins__": {}},
    )

    assert legacy == {"$in": TERMINAL_STATUSES}
    assert canonical == {"$in": ["closed", "cancelled", "abandoned", "awarded"]}
    assert stuck_filter == {"$in": TERMINAL_STATUSES}
    assert "PST" not in TERMINAL_STATUSES
    assert set(TERMINAL_STATUSES) == {"FT", "AET", "PEN", "CANC", "ABD", "AWD", "WO"}


def test_consumer_postlive_schedule_claim_guards_finished_processing_and_exhausted():
    workflow = load_yaml("workflows/event-consumer-postlive.yml")["workflow"]
    schedule = task(workflow, "load-event-by-schedule")

    assert raw_eval(
        schedule["filters"]["value.version_control.finished"], {"__builtins__": {}}
    ) == {"$ne": True}
    assert raw_eval(
        schedule["filters"]["value.version_control.processing"], {"__builtins__": {}}
    ) == {"$ne": True}
    assert raw_eval(
        schedule["filters"]["value.version_control.terminal-retry-exhausted"],
        {"__builtins__": {}},
    ) == {"$ne": True}


def test_consumer_postlive_schedule_window_is_bounded_to_the_recent_past():
    workflow = load_yaml("workflows/event-consumer-postlive.yml")["workflow"]
    schedule = task(workflow, "load-event-by-schedule")

    window_or = _clause_for(_and_clauses(schedule), "value.schema:startDate")
    window = window_or[0]["value.schema:startDate"]
    canonical_window = window_or[1]["value.event_view.start_time"]
    assert set(canonical_window) == set(window) == {"$gt", "$lt"}

    lower = datetime.fromisoformat(window["$gt"])
    upper = datetime.fromisoformat(window["$lt"])
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Lower bound is ~72h in the past; upper bound is ~now. A terminal
    # fixture has, by definition, already started, so the upper bound must
    # never reach into the future.
    assert timedelta(hours=71, minutes=59) < (now - lower) < timedelta(hours=72, minutes=1)
    assert (now - upper) < timedelta(minutes=1)
    assert lower < upper


def test_consumer_postlive_schedule_fairness_sort_and_or_clause():
    workflow = load_yaml("workflows/event-consumer-postlive.yml")["workflow"]
    schedule = task(workflow, "load-event-by-schedule")

    assert schedule["config"]["search-sorters"] == [
        ["value.version_control.consumer-update-timestamp", 1],
        ["value.schema:startDate", 1],
    ]

    fairness = _clause_for(
        _and_clauses(schedule), "value.version_control.consumer-update-timestamp"
    )
    assert fairness[1] == {
        "value.version_control.consumer-update-timestamp": {"$exists": False}
    }
    assert "$lt" in fairness[0]["value.version_control.consumer-update-timestamp"]


def test_consumer_postlive_stuck_lock_recovery_uses_five_minute_threshold():
    workflow = load_yaml("workflows/event-consumer-postlive.yml")["workflow"]
    stuck = task(workflow, "load-stuck-events")

    assert raw_eval(
        stuck["filters"]["value.version_control.processing"], {"__builtins__": {}}
    ) is True
    assert raw_eval(
        stuck["filters"]["value.version_control.finished"], {"__builtins__": {}}
    ) == {"$ne": True}
    assert raw_eval(
        stuck["filters"]["value.version_control.terminal-retry-exhausted"],
        {"__builtins__": {}},
    ) == {"$ne": True}

    namespace = {"__builtins__": {}, "datetime": datetime, "timedelta": timedelta}
    updated_filter = raw_eval(stuck["filters"]["updated"], namespace)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    threshold = updated_filter["$lt"]
    assert timedelta(minutes=4, seconds=59) < (now - threshold) < timedelta(minutes=5, seconds=1)


def test_consumer_postlive_workflow_status_reflects_whether_an_event_was_claimed():
    workflow = load_yaml("workflows/event-consumer-postlive.yml")["workflow"]

    assert evaluate(workflow["outputs"]["workflow-status"], {"event_exists": True}) == "executed"
    assert evaluate(workflow["outputs"]["workflow-status"], {"event_exists": False}) == "skipped"
    assert evaluate(workflow["outputs"]["workflow-status"], {}) == "skipped"


# ---------------------------------------------------------------------------
# api-football-event-terminal-update.yml
# ---------------------------------------------------------------------------


def terminal_update_result(event_value, synchronize_status, enrichment_status):
    workflow = load_yaml("workflows/event-terminal-update.yml")["workflow"]
    update = task(workflow, "version-control-update")
    context = {
        "event_value": event_value,
        "event-synchronize-status": synchronize_status,
        "event-data-enrichment-status": enrichment_status,
    }
    return evaluate(update["documents"]["sport:Event"], context)


def test_terminal_update_sets_finished_only_after_a_complete_final_refresh():
    event_value = {"sport:status": "FT", "version_control": {}}
    result = terminal_update_result(event_value, "executed", "executed")

    assert result["version_control"]["finished"] is True
    assert result["version_control"]["terminal-reconciled"] is True
    assert result["version_control"]["terminal-reconciled-status"] == "executed"
    assert result["version_control"]["processing"] is False
    assert result["version_control"]["terminal-retry-count"] == 0
    assert result["version_control"]["terminal-retry-exhausted"] is False


def test_terminal_update_treats_partial_and_unavailable_enrichment_as_complete():
    for enrichment_status in ("partial", "unavailable"):
        event_value = {"sport:status": "CANC", "version_control": {}}
        result = terminal_update_result(event_value, "executed", enrichment_status)

        assert result["version_control"]["finished"] is True
        assert result["version_control"]["terminal-reconciled-status"] == enrichment_status


def test_terminal_update_never_sets_finished_on_enrichment_failure():
    event_value = {"sport:status": "FT", "version_control": {"terminal-retry-count": 0}}
    result = terminal_update_result(event_value, "executed", "failed")

    assert result["version_control"]["finished"] is False
    assert result["version_control"]["terminal-reconciled"] is False
    assert result["version_control"]["terminal-reconciled-status"] == "pending-retry"
    assert result["version_control"]["terminal-retry-count"] == 1
    assert result["version_control"]["terminal-retry-exhausted"] is False


def test_terminal_update_never_sets_finished_when_status_is_not_actually_terminal():
    # Defense-in-depth: even if synchronize/enrichment both report success,
    # a non-terminal status (e.g. this event was mistakenly reclaimed) must
    # never be marked finished.
    event_value = {"sport:status": "1H", "version_control": {}}
    result = terminal_update_result(event_value, "executed", "executed")

    assert result["version_control"]["finished"] is False


def test_terminal_update_bounds_retries_and_marks_exhaustion_without_finishing():
    event_value = {"sport:status": "FT", "version_control": {}}

    for expected_count in range(1, 5):
        result = terminal_update_result(event_value, "executed", "failed")
        assert result["version_control"]["terminal-retry-count"] == expected_count
        assert result["version_control"]["terminal-retry-exhausted"] is False
        assert result["version_control"]["terminal-reconciled-status"] == "pending-retry"
        event_value = {"sport:status": "FT", "version_control": result["version_control"]}

    # 5th failed attempt exhausts the retry budget.
    result = terminal_update_result(event_value, "executed", "failed")
    assert result["version_control"]["terminal-retry-count"] == 5
    assert result["version_control"]["terminal-retry-exhausted"] is True
    assert result["version_control"]["terminal-reconciled-status"] == "retry-exhausted"
    assert result["version_control"]["finished"] is False


def test_terminal_update_is_idempotent_once_finished_is_already_true():
    event_value = {
        "sport:status": "FT",
        "version_control": {"finished": True, "terminal-reconciled": True},
    }
    result = terminal_update_result(event_value, None, None)

    assert result["version_control"]["finished"] is True
    assert result["version_control"]["terminal-reconciled"] is True


def test_terminal_update_workflow_status_reflects_whether_an_event_was_loaded():
    workflow = load_yaml("workflows/event-terminal-update.yml")["workflow"]

    assert evaluate(workflow["outputs"]["workflow-status"], {"event_exists": True}) == "executed"
    assert evaluate(workflow["outputs"]["workflow-status"], {"event_exists": False}) == "skipped"


# ---------------------------------------------------------------------------
# agents/event-postlive-update.yml
# ---------------------------------------------------------------------------


def test_postlive_agent_is_inactive_with_a_bounded_recurring_frequency():
    agent = load_yaml("agents/event-postlive-update.yml")["agent"]

    assert agent["context"]["status"] == "inactive"
    assert 0 < agent["context"]["config-frequency"] <= 60


def test_postlive_agent_chains_synchronize_enrichment_and_terminal_update():
    agent = load_yaml("agents/event-postlive-update.yml")["agent"]
    names = [item["name"] for item in agent["workflows"]]

    assert names == [
        "api-football-event-consumer-postlive",
        "api-football-event-synchronize",
        "api-football-enrich-event-data",
        "api-football-event-terminal-update",
    ]
    # No market sync: event-sync-markets is a no-op today (odds endpoint is
    # commented out) and markets are not a recap dependency post-match.
    assert "api-football-event-sync-markets" not in names


def test_postlive_agent_gates_enrichment_the_same_way_the_live_agent_does():
    live_agent = load_yaml("agents/event-live-update.yml")["agent"]
    postlive_agent = load_yaml("agents/event-postlive-update.yml")["agent"]

    live_enrich = next(
        item for item in live_agent["workflows"] if item["name"] == "api-football-enrich-event-data"
    )
    postlive_enrich = next(
        item for item in postlive_agent["workflows"] if item["name"] == "api-football-enrich-event-data"
    )

    assert postlive_enrich["condition"] == live_enrich["condition"]


def test_postlive_agent_terminal_update_requires_a_loaded_event():
    agent = load_yaml("agents/event-postlive-update.yml")["agent"]
    terminal_update = next(
        item for item in agent["workflows"] if item["name"] == "api-football-event-terminal-update"
    )

    assert terminal_update["condition"] == "$.get('event_exists') is True"
    assert evaluate(terminal_update["condition"], {"event_exists": True})
    assert not evaluate(terminal_update["condition"], {"event_exists": False})
    assert terminal_update["inputs"]["event-synchronize-status"] == "$.get('event-synchronize-status')"
    assert terminal_update["inputs"]["event-data-enrichment-status"] == "$.get('event-data-enrichment-status')"


def test_install_registers_the_postlive_agent_and_its_workflows():
    install = load_yaml("_install.yml")
    paths = {item["path"] for item in install["datasets"]}

    assert "agents/event-postlive-update.yml" in paths
    assert "workflows/event-consumer-postlive.yml" in paths
    assert "workflows/event-terminal-update.yml" in paths


# --- Dual-format scheduling (jobs[] + legacy config-frequency) ---------------

SCHEDULED_AGENTS = {
    "populate.yml": ("api-football-populate", 360, 21600),
    "event-prelive-update.yml": ("api-football-event-prelive-update", 0.5, 30),
    "event-live-update.yml": ("api-football-event-live-update", 0.1, 6),
    "event-postlive-update.yml": ("api-football-event-postlive-update", 1, 60),
}


def test_scheduled_agents_declare_dual_format_jobs():
    """Every scheduled api-football agent carries a self-targeting jobs[]
    entry for the jobs-only scheduler, with an interval consistent with its
    legacy config-frequency (minutes * 60), and keeps config-frequency for
    older three-lane runtimes (whose legacy lane skips jobs[] agents)."""

    for filename, (name, frequency, interval) in SCHEDULED_AGENTS.items():
        agent = yaml.safe_load(
            (CONNECTOR_ROOT / "agents" / filename).read_text(encoding="utf-8")
        )["agent"]
        assert agent["name"] == name
        assert agent["context"]["config-frequency"] == frequency
        assert agent["context"]["status"] == "inactive"

        jobs = agent["jobs"]
        assert len(jobs) == 1
        job = jobs[0]
        assert job["type"] == "agent"
        assert job["target"] == name
        assert job["enabled"] is True
        assert job["interval"] == interval
        assert job["interval"] == int(frequency * 60)
        assert job["name"] == f"{name}-tick"


def test_all_consumers_claim_both_document_shapes():
    """Prelive, live, and postlive claim filters must match both the legacy
    IPTC shape (value.sport:status / value.schema:startDate) and the canonical
    seam shape (value.event_view.status / value.event_view.start_time), since
    canonical events only gain legacy fields after their first synchronize."""

    expected_canonical = {
        "event-consumer-prelive.yml": ["not_started"],
        "event-consumer-live.yml": ["in_progress", "halftime", "suspended"],
        "event-consumer-postlive.yml": ["closed", "cancelled", "abandoned", "awarded"],
    }

    for filename, canonical_statuses in expected_canonical.items():
        workflow = load_yaml(f"workflows/{filename}")["workflow"]
        schedule = task(workflow, "load-event-by-schedule")
        clauses = _and_clauses(schedule)

        status_or = _clause_for(clauses, "value.sport:status")
        assert status_or[1]["value.event_view.status"] == {"$in": canonical_statuses}

        window_or = _clause_for(clauses, "value.schema:startDate")
        legacy_window = window_or[0]["value.schema:startDate"]
        canonical_window = window_or[1]["value.event_view.start_time"]
        # Both shapes carry the same window; the two utcnow() calls inside one
        # expression differ by microseconds, so compare with tolerance.
        assert set(canonical_window) == set(legacy_window)
        for bound in canonical_window:
            drift = abs(
                datetime.fromisoformat(canonical_window[bound])
                - datetime.fromisoformat(legacy_window[bound])
            )
            assert drift < timedelta(seconds=1)

        _clause_for(clauses, "value.version_control.consumer-update-timestamp")
