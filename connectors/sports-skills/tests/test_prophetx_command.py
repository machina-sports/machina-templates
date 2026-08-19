"""Regression contract for the ProphetX public dispatcher surface."""

import importlib.util
import os


_PARENT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location(
    "sports_skills_connector_prophetx",
    os.path.join(_PARENT, "sports-skills.py"),
)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


def test_prophetx_requires_the_release_that_added_the_module():
    assert _MODULE._MIN_VERSION == (0, 33, 0)
    assert _MODULE._PIP_PACKAGE == "sports-skills>=0.33.0,<1.0"


def test_invoke_prophetx_dispatches_only_to_the_prophetx_module(monkeypatch):
    calls = []

    def fake_dispatch(module, request_data):
        calls.append((module, request_data))
        return {"status": True}

    monkeypatch.setattr(_MODULE, "_dispatch", fake_dispatch)
    request = {"params": {"command": "search_markets", "sport": "nfl"}}
    assert _MODULE.invoke_prophetx(request) == {"status": True}
    assert calls == [("prophetx", request)]


def test_prophetx_command_is_declared_in_connector_yaml():
    text = open(os.path.join(_PARENT, "sports-skills.yml"), encoding="utf-8").read()
    assert 'value: "invoke_prophetx"' in text
