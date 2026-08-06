"""Regression tests for the sports-skills smoke workflow output expressions.

During a total ESPN outage the package still returns its full static
competition list, but every `current_season` is a placeholder carrying
`estimated: true`. A smoke test that only checks `len(competitions) > 0`
therefore reports `executed` while the connector is serving no live data.

These tests evaluate the workflow's declared output expressions against
fixtures shaped like the real payload, so the smoke test's verdict is pinned
by behaviour rather than by prose.
"""
import re
from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).resolve().parents[1] / "test-credentials.yml"

# Mirrors core/workflow/safe_eval.py::_SAFE_BUILTINS in machina-client-api.
# Anything outside this set is unavailable to the expressions under test, so a
# mapping that leans on a non-whitelisted builtin fails here instead of passing
# on the ambient builtins of the test process.
SAFE_BUILTINS = {
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "isinstance": isinstance,
    "any": any,
    "all": all,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "enumerate": enumerate,
}


def load_workflow():
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))["workflow"]


def evaluate_outputs(state):
    """Evaluate the workflow's top-level output expressions against `state`.

    Mirrors machina-client-api `core/workflow/context.py::_retrieve_from_context`:
    only the literal `$.get` is rewritten to `context.get`, and the namespace is
    passed as *both* globals and locals. Passing it as globals is what makes
    names resolve inside comprehension scopes, which have no access to the
    enclosing locals mapping on Python < 3.12.

    Exceptions are deliberately not caught: an expression that blows up on a
    malformed payload must surface here, not be laundered into a verdict.
    """
    outputs = load_workflow()["outputs"]
    evaluated = {}
    for key, expr in outputs.items():
        namespace = {"__builtins__": {}, **SAFE_BUILTINS, "context": state}
        evaluated[key] = eval(expr.replace("$.get", "context.get"), namespace, namespace)
    return evaluated


def competition(comp_id, estimated=False):
    """One competition shaped like the live get_competitions payload."""
    season = {
        "year": "2026",
        "start_date": "2026-08-01T00:00Z",
        "end_date": "2027-06-30T23:59Z",
    }
    if estimated:
        season["estimated"] = True
    return {
        "id": comp_id,
        "name": comp_id.replace("-", " ").title(),
        "category": {"id": "england", "name": "England"},
        "type": "LEAGUE",
        "current_season": season,
    }


def healthy_competitions():
    """32 competitions, every current_season ESPN-derived (no `estimated` key)."""
    return [competition(f"league-{i}") for i in range(32)]


def test_healthy_competitions_report_executed_with_no_degraded_leagues():
    outputs = evaluate_outputs({"competitions": healthy_competitions()})

    assert outputs.get("workflow-status") == "executed"
    assert outputs.get("degraded-competition-count") == 0
    assert outputs.get("degraded-competition-ids") == []
    assert len(outputs["competitions"]) == 32


def test_estimated_seasons_report_failed_and_name_the_degraded_competitions():
    competitions = healthy_competitions()
    competitions[3] = competition("la-liga", estimated=True)
    competitions[7] = competition("serie-a", estimated=True)

    outputs = evaluate_outputs({"competitions": competitions})

    assert outputs.get("workflow-status") == "failed"
    assert outputs.get("degraded-competition-count") == 2
    assert outputs.get("degraded-competition-ids") == ["la-liga", "serie-a"]


def test_total_outage_static_list_reports_failed():
    """The false green: a full, non-empty list where every season is a placeholder."""
    competitions = [competition(f"league-{i}", estimated=True) for i in range(32)]

    outputs = evaluate_outputs({"competitions": competitions})

    assert outputs.get("workflow-status") == "failed"
    assert outputs.get("degraded-competition-count") == 32


def test_empty_competitions_report_failed():
    outputs = evaluate_outputs({"competitions": []})

    assert outputs.get("workflow-status") == "failed"
    assert outputs.get("degraded-competition-count") == 0
    assert outputs.get("degraded-competition-ids") == []


def test_missing_competitions_key_reports_failed():
    outputs = evaluate_outputs({})

    assert outputs.get("workflow-status") == "failed"


def test_missing_current_season_reports_failed():
    """A competition with no season at all is degraded, not healthy."""
    competitions = healthy_competitions()
    degraded = competition("la-liga")
    del degraded["current_season"]
    competitions[3] = degraded

    outputs = evaluate_outputs({"competitions": competitions})

    assert outputs.get("workflow-status") == "failed"
    assert outputs.get("degraded-competition-count") == 1
    assert outputs.get("degraded-competition-ids") == ["la-liga"]


def test_null_current_season_reports_failed():
    competitions = healthy_competitions()
    degraded = competition("la-liga")
    degraded["current_season"] = None
    competitions[3] = degraded

    outputs = evaluate_outputs({"competitions": competitions})

    assert outputs.get("workflow-status") == "failed"
    assert outputs.get("degraded-competition-count") == 1
    assert outputs.get("degraded-competition-ids") == ["la-liga"]


def test_non_dict_current_season_reports_failed():
    """`current_season` arriving as a bare string must not raise."""
    competitions = healthy_competitions()
    degraded = competition("la-liga")
    degraded["current_season"] = "2026"
    competitions[3] = degraded

    outputs = evaluate_outputs({"competitions": competitions})

    assert outputs.get("workflow-status") == "failed"
    assert outputs.get("degraded-competition-count") == 1
    assert outputs.get("degraded-competition-ids") == ["la-liga"]


def test_non_dict_competition_entry_reports_failed():
    """A bare string where a competition dict was expected must not raise."""
    competitions = healthy_competitions()
    competitions[3] = "la-liga"

    outputs = evaluate_outputs({"competitions": competitions})

    assert outputs.get("workflow-status") == "failed"
    assert outputs.get("degraded-competition-count") == 1


def test_non_list_competitions_dict_reports_failed():
    """An error envelope in place of the list must not raise."""
    outputs = evaluate_outputs({"competitions": {"error": "upstream 502"}})

    assert outputs.get("workflow-status") == "failed"
    assert outputs.get("degraded-competition-count") == 0
    assert outputs.get("degraded-competition-ids") == []


def test_non_list_competitions_string_reports_failed():
    """A string would iterate character-by-character; it must be rejected outright."""
    outputs = evaluate_outputs({"competitions": "upstream 502"})

    assert outputs.get("workflow-status") == "failed"
    assert outputs.get("degraded-competition-count") == 0
    assert outputs.get("degraded-competition-ids") == []


def test_malformed_entries_report_stable_placeholder_ids():
    """Malformed entries still need a name in the diagnostic output."""
    outputs = evaluate_outputs(
        {"competitions": ["la-liga", None, {"name": "No Id"}]}
    )

    assert outputs.get("workflow-status") == "failed"
    assert outputs.get("degraded-competition-count") == 3
    assert outputs.get("degraded-competition-ids") == [
        "<malformed-entry>",
        "<malformed-entry>",
        "<unknown-id>",
    ]


def test_competitions_output_is_still_exposed():
    assert load_workflow()["outputs"]["competitions"] == "$.get('competitions', [])"


def test_connector_task_output_mapping_is_unchanged():
    tasks = load_workflow()["tasks"]

    assert [t["name"] for t in tasks] == ["smoke-football-get-competitions"]
    assert tasks[0]["connector"] == {
        "name": "sports-skills",
        "command": "invoke_football",
    }
    assert tasks[0]["inputs"] == {"command": "'get_competitions'"}
    assert tasks[0]["outputs"] == {
        "competitions": "$.get('data', {}).get('competitions', [])"
    }


def test_descriptions_state_live_season_validation_without_a_league_count():
    """The league count drifts with ESPN's catalogue; the season check does not."""
    workflow = load_workflow()
    descriptions = [workflow["description"], workflow["tasks"][0]["description"]]

    for text in descriptions:
        assert not re.search(r"\d+\s*(leagues|competitions)", text), text

    joined = " ".join(descriptions).lower()
    assert "current_season" in joined
