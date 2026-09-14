"""Offline contract tests for the Live Tennis API connector.

No network, no key. HTTP is mocked at `requests.get`; the break-point
derivation is pure. The descriptor and install manifest are pinned so a
renamed command or a missing dataset shows up here rather than at import
time on a pod.
"""

import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

CONNECTOR_DIR = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "live_tennis_api_connector", CONNECTOR_DIR / "live-tennis-api.py"
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

KEY = "test-key-never-real"


def read_yaml(path):
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


class FakeResponse:
    def __init__(self, status_code, body=None, headers=None, text=""):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._body is None:
            raise ValueError("no json")
        return self._body


def score(points, server=1, is_tiebreak=False):
    return {"sets": [0, 0], "games": [[3], [3]], "points": points,
            "server": server, "is_tiebreak": is_tiebreak}


# ---------------------------------------------------------------- descriptor


def test_descriptor_declares_every_command_as_a_module_function():
    descriptor = read_yaml(CONNECTOR_DIR / "live-tennis-api.yml")["connector"]
    assert descriptor["name"] == "live-tennis-api"
    assert descriptor["filename"] == "live-tennis-api.py"
    assert descriptor["filetype"] == "pyscript"
    for command in descriptor["commands"]:
        assert callable(getattr(_module, command["value"])), command


def test_install_manifest_lists_the_shipped_datasets_and_vault_secret():
    manifest = read_yaml(CONNECTOR_DIR / "_install.yml")
    assert manifest["setup"]["value"] == "connectors/live-tennis-api"
    assert "TEMP_CONTEXT_VARIABLE_LIVE_TENNIS_API_KEY" in manifest["setup"]["requirements"]
    for dataset in manifest["datasets"]:
        assert (CONNECTOR_DIR / dataset["path"]).is_file(), dataset


def test_workflows_take_the_key_from_the_vault_and_never_inline_it():
    for name in ("test-credentials.yml", "workflows/sync-live-matches.yml",
                 "workflows/sync-fixtures.yml"):
        workflow = read_yaml(CONNECTOR_DIR / name)["workflow"]
        assert workflow["context-variables"]["live-tennis-api"]["api_key"] == \
            "$TEMP_CONTEXT_VARIABLE_LIVE_TENNIS_API_KEY", name
        for task in workflow["tasks"]:
            if task["type"] == "connector":
                assert task["inputs"]["api_key"] == "$.get('api_key')", (name, task["name"])


def test_shipped_files_reference_the_key_only_through_the_vault_variable():
    """Every `api_key` mention in the shipped YAML is the vault reference or the
    `$.get('api_key')` pass-through — never a literal value."""
    for path in CONNECTOR_DIR.rglob("*.yml"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if "api_key" in line and ":" in line:
                value = line.split(":", 1)[1].strip().strip('"')
                assert value in ("$TEMP_CONTEXT_VARIABLE_LIVE_TENNIS_API_KEY", "$.get('api_key')", ""), (path, line)


# ------------------------------------------------------------- break point


@pytest.mark.parametrize("points, server, expected", [
    (["30", "40"], 1, True),      # receiver 40, server 30
    (["0", "40"], 1, True),       # receiver 40, server 0
    (["15", "40"], 1, True),
    (["40", "AD"], 1, True),      # receiver at AD
    (["40", "40"], 1, False),     # deuce
    (["AD", "40"], 1, False),     # AD server
    (["40", "30"], 1, False),     # game point server
    (["0", "0"], 1, False),
    (["40", "30"], 2, True),      # server is player 2; receiver (p1) at 40 vs 30
    (["AD", "40"], 2, True),      # receiver (p1) at AD
    (["30", "40"], 2, False),     # server p2 at 40, receiver at 30
])
def test_break_point_by_server_and_points(points, server, expected):
    assert _module.is_break_point(score(points, server)) is expected


def test_break_point_is_never_true_in_a_tiebreak():
    assert _module.is_break_point(score(["5", "6"], 1, is_tiebreak=True)) is False
    assert _module.is_break_point(score(["30", "40"], 1, is_tiebreak=True)) is False


@pytest.mark.parametrize("value", [
    None,
    {},
    score([None, "40"], 1),
    score(["30", None], 1),
    score(["30", "40"], None),
    score(["30", "40"], 3),
    score(["30"], 1),
    score("30-40", 1),
    score(["30", "45"], 1),
    "not a score",
])
def test_break_point_is_null_when_the_state_is_unknown(value):
    assert _module.is_break_point(value) is None


def test_derive_match_state_is_offline_and_names_the_receiver():
    with patch.object(_module.requests, "get") as get:
        result = _module.derive_match_state({"params": {"score": score(["30", "40"], 1)}})
        get.assert_not_called()
    assert result["status"] is True
    assert result["data"]["state"] == {
        "break_point": True, "server": 1, "receiver": 2, "is_tiebreak": False,
        "points_server": "30", "points_receiver": "40",
    }


def test_derive_match_state_rejects_a_non_object_score():
    result = _module.derive_match_state({"params": {"score": "x"}})
    assert result["status"] is False
    assert result["data"]["error"] == "bad_score"


# -------------------------------------------------------------- transport


def test_missing_key_is_refused_before_any_request():
    with patch.object(_module.requests, "get") as get:
        result = _module.get_live_matches({"params": {}})
        get.assert_not_called()
    assert result["status"] is False
    assert result["data"]["error"] == "missing_api_key"


def test_key_is_sent_as_x_api_key_header_and_never_in_the_query():
    body = {"data": [], "meta": {"limit": 50, "offset": 0, "count": 0, "total": 0, "has_more": False}}
    with patch.object(_module.requests, "get", return_value=FakeResponse(200, body)) as get:
        result = _module.get_live_matches({"params": {"api_key": KEY, "tour": "atp", "limit": "10"}})
    assert result["status"] is True
    (url,), kwargs = get.call_args
    assert url == "https://api.livetennisapi.com/api/public/v1/matches"
    assert kwargs["headers"]["X-API-Key"] == KEY
    assert kwargs["params"] == {"status": "live", "tour": "atp", "limit": 10}
    assert "token" not in kwargs["params"]
    assert kwargs["timeout"] == _module.DEFAULT_TIMEOUT


def test_key_can_also_arrive_through_the_headers_block():
    body = {"principal": "p", "tier": "free"}
    with patch.object(_module.requests, "get", return_value=FakeResponse(200, body)) as get:
        result = _module.get_usage({"headers": {"api_key": KEY}, "params": {}})
    assert result == {"status": True, "data": {"usage": body}}
    assert get.call_args.kwargs["headers"]["X-API-Key"] == KEY


def test_live_matches_carry_the_derived_block_and_leave_the_match_untouched():
    match = {"id": 7, "players": {"p1": {"name": "A"}, "p2": {"name": "B"}},
             "score": score(["40", "AD"], 1)}
    body = {"data": [match], "meta": {"has_more": False}}
    with patch.object(_module.requests, "get", return_value=FakeResponse(200, body)):
        result = _module.get_live_matches({"params": {"api_key": KEY}})
    out = result["data"]["matches"][0]
    assert out["derived"]["break_point"] is True
    assert {k: v for k, v in out.items() if k != "derived"} == match
    assert result["data"]["meta"] == {"has_more": False}


def test_unknown_enum_values_are_dropped_not_sent():
    body = {"data": [], "meta": {}}
    with patch.object(_module.requests, "get", return_value=FakeResponse(200, body)) as get:
        _module.get_matches({"params": {"api_key": KEY, "status": "bogus", "tour": "nba", "draw": ""}})
    assert get.call_args.kwargs["params"] == {"status": "live"}


def test_single_match_requires_an_integer_id():
    with patch.object(_module.requests, "get") as get:
        result = _module.get_match({"params": {"api_key": KEY, "match_id": "abc"}})
        get.assert_not_called()
    assert result["status"] is False and result["data"]["error"] == "missing_match_id"


def test_single_match_path_and_derived_state():
    body = {"id": 42, "score": score(["30", "40"], 1)}
    with patch.object(_module.requests, "get", return_value=FakeResponse(200, body)) as get:
        result = _module.get_match({"params": {"api_key": KEY, "match_id": 42}})
    assert get.call_args.args[0].endswith("/matches/42")
    assert result["data"]["match"] == body
    assert result["data"]["derived"]["break_point"] is True


def test_429_minute_limit_is_reported_with_retry_after_and_not_retried():
    body = {"error": "rate_limited", "detail": "slow down", "tier": "free"}
    resp = FakeResponse(429, body, headers={"Retry-After": "12"})
    with patch.object(_module.requests, "get", return_value=resp) as get:
        result = _module.get_live_matches({"params": {"api_key": KEY}})
    assert get.call_count == 1
    assert result["status"] is False
    assert result["data"]["status_code"] == 429
    assert result["data"]["error"] == "rate_limited"
    assert result["data"]["retry_after"] == "12"
    assert "Retry-After 12s" in result["message"]


def test_429_daily_quota_names_the_reset_instant():
    body = {"error": "rate_limited", "scope": "day", "limit_per_day": 100,
            "resets_at": "2026-09-13T00:00:00Z"}
    resp = FakeResponse(429, body, headers={"Retry-After": "3600"})
    with patch.object(_module.requests, "get", return_value=resp):
        result = _module.get_fixtures({"params": {"api_key": KEY}})
    assert result["status"] is False
    assert result["data"]["scope"] == "day"
    assert result["data"]["resets_at"] == "2026-09-13T00:00:00Z"
    assert "2026-09-13T00:00:00Z" in result["message"]


def test_429_abuse_throttle_tells_the_caller_not_to_retry():
    body = {"error": "abuse_throttled", "retry_at_epoch": 1789000000}
    with patch.object(_module.requests, "get", return_value=FakeResponse(429, body)):
        result = _module.get_usage({"params": {"api_key": KEY}})
    assert result["data"]["error"] == "abuse_throttled"
    assert result["data"]["retry_at_epoch"] == 1789000000
    assert "do not retry" in result["message"].lower()


@pytest.mark.parametrize("code, error, fragment", [
    (401, None, "Unauthorized"),
    (403, "upgrade_required", "does not unlock"),
    (404, "not_found", "No such resource"),
    (400, "bad_date", "Bad query parameter"),
    (500, None, "HTTP 500"),
])
def test_non_2xx_answers_become_status_false_with_the_provider_code(code, error, fragment):
    body = {"error": error} if error else None
    with patch.object(_module.requests, "get", return_value=FakeResponse(code, body, text="oops")):
        result = _module.search_players({"params": {"api_key": KEY, "search": "alc"}})
    assert result["status"] is False
    assert result["data"]["status_code"] == code
    assert result["data"]["error"] == error
    assert fragment in result["message"]


def test_transport_failures_are_returned_not_raised():
    with patch.object(_module.requests, "get", side_effect=_module.requests.exceptions.ConnectionError("down")):
        result = _module.get_usage({"params": {"api_key": KEY}})
    assert result["status"] is False and result["data"]["error"] == "request_failed"
    with patch.object(_module.requests, "get", side_effect=_module.requests.exceptions.Timeout()):
        result = _module.get_usage({"params": {"api_key": KEY}})
    assert result["status"] is False and result["data"]["error"] == "timeout"


def test_head_to_head_needs_two_fragments_of_three_characters():
    with patch.object(_module.requests, "get") as get:
        result = _module.get_head_to_head({"params": {"api_key": KEY, "p1": "al", "p2": "sinner"}})
        get.assert_not_called()
    assert result["data"]["error"] == "missing_players"
    body = {"players": None, "totals": {"p1_wins": 0, "p2_wins": 0, "meetings": 0, "undecided": 0}}
    with patch.object(_module.requests, "get", return_value=FakeResponse(200, body)) as get:
        result = _module.get_head_to_head({"params": {"api_key": KEY, "p1": "alcaraz", "p2": "sinner"}})
    assert get.call_args.kwargs["params"] == {"p1": "alcaraz", "p2": "sinner"}
    assert result["data"]["h2h"] == body


def test_generic_request_refuses_paths_off_the_allow_list_before_any_call():
    with patch.object(_module.requests, "get") as get:
        for path, path_id in (("/webhooks", None), ("/ws-token", None), ("/webhooks/{id}", 3),
                              ("/matches/{id}", None), ("matches", None), ("/matches/1", None)):
            result = _module.invoke_request({"params": {"api_key": KEY, "path": path, "path_id": path_id}})
            assert result["status"] is False, path
            assert result["data"]["error"] == "path_not_allowed", path
        get.assert_not_called()


def test_generic_request_fills_the_id_and_passes_the_query_through():
    body = {"data": [{"seq": 1}], "meta": {}}
    with patch.object(_module.requests, "get", return_value=FakeResponse(200, body)) as get:
        result = _module.invoke_request({"params": {
            "api_key": KEY, "path": "/matches/{id}/events", "path_id": 99, "query": {"limit": 5, "x": None}}})
    assert get.call_args.args[0].endswith("/matches/99/events")
    assert get.call_args.kwargs["params"] == {"limit": 5}
    assert result["data"]["response"] == body
