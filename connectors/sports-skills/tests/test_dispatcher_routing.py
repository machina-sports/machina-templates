"""Routing tests for invoke_sports_skills.

The dispatcher used to end in `else: module_name = "nfl"`, so any sport or
league the table did not name was sent to the NFL module. That is worse than an
error: the NFL endpoint answers with HTTP 404 "No stats found", callers set
continue_on_error on the task, and the 404 then reads exactly like "this
athlete has no provider id". A college football player with a perfectly good
ESPN id silently produced nothing (issue #343).

These tests pin the routing table and, just as importantly, pin the refusal.
"""
import importlib.util
import os

_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "sports_skills_connector", os.path.join(_parent_dir, "sports-skills.py")
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


def _route(monkeypatch, **params):
    """Return the module invoke_sports_skills would dispatch to."""
    seen = {}

    def fake_dispatch(module_name, request_data):
        seen["module"] = module_name
        seen["command"] = (request_data.get("params") or {}).get("command")
        return {"status": True, "data": {"status": True}}

    monkeypatch.setattr(_module, "_dispatch", fake_dispatch)
    result = _module.invoke_sports_skills({"params": dict(params)})
    return seen, result


def test_college_football_routes_to_cfb(monkeypatch):
    """The bug from #343: this used to land on nfl and 404."""
    seen, _ = _route(monkeypatch, sport="football", league="CFB", player_id="5079720")
    assert seen["module"] == "cfb"


def test_ncaaf_alias_also_routes_to_cfb(monkeypatch):
    seen, _ = _route(monkeypatch, sport="football", league="NCAAF")
    assert seen["module"] == "cfb"


def test_college_basketball_routes_to_cbb(monkeypatch):
    seen, _ = _route(monkeypatch, sport="basketball", league="NCAAW")
    assert seen["module"] == "cbb"


def test_volleyball_routes_to_volleyball(monkeypatch):
    seen, _ = _route(monkeypatch, sport="volleyball")
    assert seen["module"] == "volleyball"


def test_track_and_field_routes_to_xctf(monkeypatch):
    seen, _ = _route(monkeypatch, sport="track_and_field")
    assert seen["module"] == "xctf"


def test_athletics_is_treated_as_track_and_field(monkeypatch):
    seen, _ = _route(monkeypatch, sport="athletics")
    assert seen["module"] == "xctf"


def test_nfl_still_routes_to_nfl(monkeypatch):
    seen, _ = _route(monkeypatch, sport="football", league="NFL")
    assert seen["module"] == "nfl"


def test_soccer_still_routes_to_football(monkeypatch):
    seen, _ = _route(monkeypatch, sport="soccer")
    assert seen["module"] == "football"
    assert seen["command"] == "get_player_profile"


def test_baseball_still_routes_to_mlb(monkeypatch):
    seen, _ = _route(monkeypatch, sport="baseball")
    assert seen["module"] == "mlb"


def test_bare_football_without_league_refuses_instead_of_guessing(monkeypatch):
    """Ambiguous between American football and soccer — say so, don't pick."""
    seen, result = _route(monkeypatch, sport="football")
    assert "module" not in seen
    assert result["status"] is False
    assert "ambiguous" in result["message"]


def test_unknown_sport_refuses_and_names_what_it_saw(monkeypatch):
    seen, result = _route(monkeypatch, sport="curling", league="WCF")
    assert "module" not in seen, "must not fall through to a guessed module"
    assert result["status"] is False
    assert "curling" in result["message"] and "WCF" in result["message"]


def test_softball_refuses_rather_than_returning_nfl_data(monkeypatch):
    """There is no softball module; the caller needs to know that."""
    seen, result = _route(monkeypatch, sport="softball")
    assert "module" not in seen
    assert result["status"] is False


def test_basketball_without_league_still_cascades(monkeypatch):
    """Pre-existing behaviour: wnba, then nba, then cbb."""
    tried = []

    def fake_dispatch(module_name, request_data):
        tried.append(module_name)
        ok = module_name == "cbb"
        return {"status": True, "data": {"status": ok}}

    monkeypatch.setattr(_module, "_dispatch", fake_dispatch)
    _module.invoke_sports_skills({"params": {"sport": "basketball"}})
    assert tried == ["wnba", "nba", "cbb"]


def test_metadata_docstring_names_search_players():
    """An agent picks a command from this docstring; it listed only get_team_logo."""
    assert "search_players" in _module.invoke_metadata.__doc__
