"""Regression contract for the NBA G League dispatcher (sports-skills 0.40.0).

Offline: the package module is faked in sys.modules, except the parity test,
which only imports the installed package (no provider call) and is skipped
unless the installed copy is exactly the pin.
"""

import importlib.util
import os
import sys
import types

import pytest

_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location(
    "sports_skills_connector_gleague",
    os.path.join(_PARENT, "sports-skills.py"),
)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def _read(name):
    return open(os.path.join(_PARENT, name), encoding="utf-8").read()


def test_gleague_requires_the_release_that_added_the_module():
    assert _MODULE._PINNED_VERSION == "0.40.0"
    assert _MODULE._PIP_PACKAGE == "sports-skills==0.40.0"


def test_invoke_gleague_dispatches_only_to_the_gleague_module(monkeypatch):
    calls = []

    def fake_dispatch(module, request_data):
        calls.append((module, request_data))
        return {"status": True}

    monkeypatch.setattr(_MODULE, "_dispatch", fake_dispatch)
    request = {"params": {"command": "get_teams"}}
    assert _MODULE.invoke_gleague(request) == {"status": True}
    assert calls == [("gleague", request)]


def test_gleague_command_is_declared_in_connector_yaml():
    assert 'value: "invoke_gleague"' in _read("sports-skills.yml")


def test_install_description_names_g_league():
    assert "G League" in _read("_install.yml")


@pytest.fixture
def fake_gleague(monkeypatch):
    """A stand-in sports_skills.gleague with the 0.40.0 signatures used here."""
    mod = types.ModuleType("sports_skills.gleague")
    mod.calls = []

    def get_teams():
        mod.calls.append(("get_teams", {}))
        return {"status": True, "data": {"teams": []}, "message": ""}

    def get_standings(*, season=None):
        mod.calls.append(("get_standings", {"season": season}))
        return {"status": False, "data": None, "message": "provider unavailable"}

    mod.get_teams = get_teams
    mod.get_standings = get_standings
    monkeypatch.setattr(_MODULE, "_ensure_sports_skills", lambda: (True, None))
    monkeypatch.setitem(sys.modules, "sports_skills", types.ModuleType("sports_skills"))
    monkeypatch.setitem(sys.modules, "sports_skills.gleague", mod)
    return mod


def test_gleague_wraps_the_package_result_in_the_connector_envelope(fake_gleague):
    result = _MODULE.invoke_gleague({"params": {"command": "get_teams"}})
    assert result == {"status": True, "data": {"status": True, "data": {"teams": []}, "message": ""}}


def test_gleague_filters_framework_params_to_the_function_signature(fake_gleague):
    _MODULE.invoke_gleague({"params": {
        "command": "get_standings", "season": 2026, "model_name": "x", "api_key": "k",
    }})
    assert fake_gleague.calls == [("get_standings", {"season": 2026})]


def test_gleague_inner_provider_failure_is_not_reported_as_success(fake_gleague):
    result = _MODULE.invoke_gleague({"params": {"command": "get_standings"}})
    assert result["status"] is True
    assert result["data"]["status"] is False
    assert result["data"]["message"] == "provider unavailable"


def test_gleague_missing_command_fails_closed(fake_gleague):
    result = _MODULE.invoke_gleague({"params": {}})
    assert result["status"] is False
    assert "invoke_gleague" in result["message"]
    assert fake_gleague.calls == []


def test_gleague_unknown_command_lists_available(fake_gleague):
    result = _MODULE.invoke_gleague({"params": {"command": "get_player_stats"}})
    assert result["status"] is False
    assert "get_teams" in result["message"]


def test_gleague_install_failure_never_imports_the_module(monkeypatch):
    monkeypatch.setattr(_MODULE, "_ensure_sports_skills", lambda: (False, "pin failed"))
    assert _MODULE.invoke_gleague({"params": {"command": "get_teams"}}) == {
        "status": False, "message": "pin failed"}


def test_installed_pin_exposes_gleague_to_module_and_cli():
    sports_skills = pytest.importorskip("sports_skills")
    if getattr(sports_skills, "__version__", None) != _MODULE._PINNED_VERSION:
        pytest.skip("installed sports-skills is not the connector pin")
    import sports_skills.cli as cli
    import sports_skills.gleague as gleague

    assert callable(gleague.get_teams)
    assert "get_teams" in cli._REGISTRY["gleague"]
