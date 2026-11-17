"""Deterministic regression coverage for the NFL workload skill package."""

import ast
from copy import deepcopy
from pathlib import Path

import pytest
import yaml


PACKAGE = Path(__file__).resolve().parents[1] / "skills" / "nfl-workload"
WORKFLOWS = PACKAGE / "workflows"
SAFE_BUILTINS = {
    "all": all,
    "any": any,
    "len": len,
}


def load_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_workflow(name):
    return load_yaml(WORKFLOWS / name)["workflow"]


def evaluate_output(workflow, name, state):
    expression = workflow["outputs"][name]
    namespace = {"__builtins__": {}, **SAFE_BUILTINS, "context": state}
    return eval(
        expression.replace("$.get", "context.get"), namespace, namespace
    )


def conjunction_terms(node):
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return {term for value in node.values for term in conjunction_terms(value)}
    return {ast.dump(node, include_attributes=False)}


def test_all_package_yaml_is_parseable():
    for path in PACKAGE.rglob("*.yml"):
        assert load_yaml(path) is not None, path


def test_lookup_pair_forwards_each_players_team_scope():
    workflow = load_workflow("fantasy-explain-reasoning.yml")
    lookup_pair = next(task for task in workflow["tasks"] if task["name"] == "lookup-pair")

    assert lookup_pair["inputs"]["player_a_team"] == "$.get('player_a_team', '')"
    assert lookup_pair["inputs"]["player_b_team"] == "$.get('player_b_team', '')"


@pytest.mark.parametrize(
    ("missing_field", "missing_value"),
    [
        ("season", 0),
        ("week", 0),
        ("player_a_name", ""),
        ("player_b_name", ""),
    ],
)
def test_incomplete_explain_request_reports_invalid_input(missing_field, missing_value):
    workflow = load_workflow("fantasy-explain-reasoning.yml")
    state = {
        "season": 2025,
        "week": 17,
        "player_a_name": "Shaheed",
        "player_b_name": "Chase",
    }
    state[missing_field] = missing_value

    assert evaluate_output(workflow, "workflow-status", state) == "invalid-input"
    validation_error = evaluate_output(workflow, "validation_error", state).lower()
    assert "required" in validation_error
    assert missing_field in validation_error
    for status in (
        "player_a_status",
        "player_a_context_status",
        "player_b_status",
        "player_b_context_status",
    ):
        assert evaluate_output(workflow, status, state) == "invalid-input"


def test_install_declares_only_platform_integrations():
    setup = load_yaml(PACKAGE / "_install.yml")["setup"]

    assert setup["integrations"] == ["google-genai"]


def test_skill_surfaces_explain_validation_error():
    skill = load_yaml(PACKAGE / "skill.yml")["skill"]
    explain = next(
        workflow
        for workflow in skill["workflows"]
        if workflow["name"] == "fantasy-explain-reasoning"
    )

    assert explain["outputs"]["validation_error"] == "$.get('validation_error', '')"


def test_skill_examples_use_execute_endpoint():
    text = (PACKAGE / "SKILL.md").read_text(encoding="utf-8")

    assert "/workflow/executor" not in text
    for workflow_name in (
        "nfl-workload-report",
        "nfl-workload-latest",
        "nfl-workload-machina-snapshot",
        "fantasy-explain-reasoning",
    ):
        assert f"POST /workflow/execute/{workflow_name}" in text


def test_traded_player_result_contains_every_advertised_assertion():
    workflow = load_workflow("test-traded-player.yml")
    result_tree = ast.parse(
        workflow["outputs"]["result"].replace("$.get", "context.get"), mode="eval"
    )
    result_condition = result_tree.body.values[0]
    result_terms = conjunction_terms(result_condition)

    for name, expression in workflow["outputs"].items():
        if name.startswith("assert_"):
            assertion_tree = ast.parse(
                expression.replace("$.get", "context.get"), mode="eval"
            )
            assert conjunction_terms(assertion_tree.body) <= result_terms, name


@pytest.mark.parametrize(
    ("case", "changes"),
    [
        ("exact SEA excluded stint", {"sa_stints": [{"team": "LAR"}]}),
        ("no excluded Chase stint", {"sb_stints": [{"team": "KC"}]}),
        ("split names selected stint", {"rec.caveat": "SEA; 68 of 100"}),
        ("split names excluded stint", {"rec.caveat": "NO stint; 68 of 100"}),
        ("68-of-100 caveat", {"rec.caveat": "NO stint excludes SEA"}),
        ("key-factor stint marker", {"rec.key_factors": ["matchup advantage"]}),
        (
            "no bare key-factor comparison",
            {"rec.key_factors": ["178 vs 68", "NO stint"]},
        ),
        ("reasoning stint marker", {"rec.reasoning": "prefer Shaheed"}),
    ],
)
def test_traded_player_result_enforces_every_advertised_assertion(case, changes):
    workflow = load_workflow("test-traded-player.yml")
    state = {
        "sa_team": "NO",
        "sb_team": "CIN",
        "sa_stints": [{"team": "SEA"}],
        "sb_stints": [],
        "rec": {
            "caveat": "NO stint excludes SEA and covers 68 of 100 opportunities",
            "key_factors": ["0.305 from the NO stint"],
            "reasoning": "The NO stint supports the recommendation",
        },
    }
    state = deepcopy(state)
    for key, value in changes.items():
        if key.startswith("rec."):
            state["rec"][key.removeprefix("rec.")] = value
        else:
            state[key] = value

    advertised = {
        name: evaluate_output(workflow, name, state)
        for name in workflow["outputs"]
        if name.startswith("assert_")
    }
    assert not all(advertised.values()), case
    assert evaluate_output(workflow, "result", state) == "FAIL", case


# ---------------------------------------------------------------------------
# get_player_context against a fake sports_skills.nfl (no network, no install)
# ---------------------------------------------------------------------------

import importlib.util  # noqa: E402
import sys  # noqa: E402
import types  # noqa: E402

_CONNECTOR_SPEC = importlib.util.spec_from_file_location(
    "nfl_workload_connector", PACKAGE / "connectors" / "nfl-workload.py"
)
CONNECTOR = importlib.util.module_from_spec(_CONNECTOR_SPEC)
_CONNECTOR_SPEC.loader.exec_module(CONNECTOR)

TEAMS = {"teams": [
    {"id": "8", "name": "Synthetic Lions", "abbreviation": "SYL", "nickname": "Lions", "location": "Synthetic"},
    {"id": "9", "name": "Synthetic Bears", "abbreviation": "SYB", "nickname": "Bears", "location": "Synthetic"},
]}
DEPTH = {"charts": [{"name": "3WR 1TE", "positions": [{"abbreviation": "QB", "name": "Quarterback", "athletes": [
    {"id": "100", "name": "Healthy Starter", "depth": 1}, {"id": "101", "name": "Hurt Backup", "depth": 2}]}]}]}
# sports-skills 0.40.6+ shape: reported injuries only, no "Active" rows, `type` is the injury.
INJURED_ONLY = {"teams": [{"team_id": "8", "team": "Synthetic Lions", "injuries": [
    {"name": "Hurt Backup", "status": "Out", "type": "Wrist", "detail": "Not Specified", "side": "Left",
     "return_date": "2026-12-20"}]}]}


def player_context(monkeypatch, injuries, player="Healthy Starter", team="SYL"):
    ok = lambda data: {"status": True, "data": data, "message": ""}  # noqa: E731
    nfl = types.SimpleNamespace(
        get_teams=lambda: ok(TEAMS),
        get_depth_chart=lambda team_id: ok(DEPTH),
        get_injuries=lambda: injuries if "status" in injuries else ok(injuries),
    )
    package = types.ModuleType("sports_skills")
    package.nfl = nfl
    monkeypatch.setitem(sys.modules, "sports_skills", package)
    monkeypatch.setitem(sys.modules, "sports_skills.nfl", nfl)
    reply = CONNECTOR.get_player_context({"params": {"team": team, "player_name": player}})
    assert reply["status"] is True, reply
    return reply["data"]


def test_player_missing_from_an_injured_only_report_is_not_listed_on_a_covered_team(monkeypatch):
    data = player_context(monkeypatch, INJURED_ONLY)
    assert (data["reason"], data["on_depth_chart"], data["injury_listed"]) == ("matched", True, False)
    assert data["injury_status"] is None, "absence is never turned into an Active status"
    assert data["injury_report"] == {"team_listed": True, "entries": 1}


def test_reported_injury_passes_through_with_the_report_scope(monkeypatch):
    data = player_context(monkeypatch, INJURED_ONLY, player="Hurt Backup")
    assert data["injury_listed"] is True
    assert (data["injury_status"]["status"], data["injury_status"]["type"]) == ("Out", "Wrist")
    assert data["injury_report"] == {"team_listed": True, "entries": 1}


def test_team_without_a_block_in_the_feed_is_reported_as_not_covered(monkeypatch):
    other_team_only = {"teams": [{"team_id": "9", "team": "Synthetic Bears", "injuries": [
        {"name": "Healthy Starter", "status": "Out", "type": "Knee"}]}]}
    data = player_context(monkeypatch, other_team_only)
    assert data["injury_listed"] is False, "another team's entry never answers for this one"
    assert data["injury_report"] == {"team_listed": False, "entries": 0}


def test_older_feed_with_active_rows_still_reports_the_explicit_status(monkeypatch):
    legacy = {"teams": [{"team_id": "8", "team": "Synthetic Lions", "injuries": [
        {"name": "Healthy Starter", "status": "Active", "type": "active"}]}]}
    data = player_context(monkeypatch, legacy)
    assert (data["injury_listed"], data["injury_status"]["status"]) == (True, "Active")
    assert data["injury_report"] == {"team_listed": True, "entries": 1}


def test_failed_injury_feed_carries_no_report_scope(monkeypatch):
    data = player_context(monkeypatch, {"status": False, "data": None, "message": "HTTP 503"})
    assert "injury_report" not in data
    assert "HTTP 503" in data["degraded"]["injury_error"]
    assert (data["on_depth_chart"], data["injury_listed"]) == (True, False)


def test_player_not_found_still_reports_the_report_scope(monkeypatch):
    data = player_context(monkeypatch, INJURED_ONLY, player="Nobody Atall")
    assert data["reason"] == "not_found"
    assert data["injury_report"] == {"team_listed": True, "entries": 1}


def test_fantasy_prompt_reads_the_report_scope_and_never_requires_an_explicit_active():
    prompt = load_yaml(PACKAGE / "prompts" / "fantasy-explain-prompt.yml")
    text = yaml.safe_dump(prompt)
    assert text.count("injury_report.team_listed") >= 4
    assert "not on the injury report" in text
    assert "the other an explicit Active, use" not in text
    assert "other's carries an explicit Active" not in text
