"""Regression tests for the sports-skills connector exact version pin.

Pods bake a sports-skills copy into system site-packages; the connector
installs the pinned release to /tmp whenever the imported copy is not exactly
the pin. All tests are offline: import and pip are mocked, no network.
"""
import importlib.util
import os
import re
import subprocess
import sys
import types

import pytest

# Load module with hyphenated filename using importlib
_parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "sports_skills_connector",
    os.path.join(_parent_dir, "sports-skills.py")
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)

_EXPECTED_ARGV = [
    sys.executable,
    "-m",
    "pip",
    "install",
    "--no-cache-dir",
    "--upgrade",
    "--target",
    None,  # filled with the per-test target dir
    "sports-skills==0.35.0",
]


def _fake_sports_skills(version):
    mod = types.ModuleType("sports_skills")
    mod.__version__ = version
    return mod


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Isolate sys.path/sys.modules/target dir and mock import + pip."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setattr(_module, "_TARGET_DIR", str(tmp_path / "site"))
    monkeypatch.setitem(sys.modules, "sports_skills", _fake_sports_skills("0.0.0"))

    state = {"import_version": None, "run": None, "run_calls": [], "import_calls": []}

    def fake_import(name):
        state["import_calls"].append(name)
        if state["import_version"] is None:
            raise ImportError(f"No module named {name!r}")
        mod = _fake_sports_skills(state["import_version"])
        sys.modules[name] = mod
        return mod

    def fake_run(*args, **kwargs):
        state["run_calls"].append((args, kwargs))
        if state["run"] is None:
            raise AssertionError("pip must not run")
        return state["run"](*args, **kwargs)

    monkeypatch.setattr(_module.importlib, "import_module", fake_import)
    monkeypatch.setattr(_module.subprocess, "run", fake_run)

    def preload(version):
        if version is None:
            monkeypatch.delitem(sys.modules, "sports_skills")
        else:
            sys.modules["sports_skills"] = _fake_sports_skills(version)

    state["preload"] = preload
    return state


def _pip_ok(*args, **kwargs):
    return subprocess.CompletedProcess(args[0], 0, stdout="ok", stderr="")


def test_pin_is_exactly_0_35_0():
    assert _module._PINNED_VERSION == "0.35.0"
    assert _module._PIP_PACKAGE == "sports-skills==0.35.0"


def test_runtime_requirement_docs_state_only_the_exact_pin():
    pins = re.findall(r"sports-skills(==|>=)([0-9][0-9.]*[0-9])", _module.__doc__)
    assert pins, "runtime requirement docs must state the sports-skills pin"
    assert all(p == ("==", "0.35.0") for p in pins), pins


def test_upgrade_target_stays_in_tmp():
    assert _module._TARGET_DIR == "/tmp/sports-skills-site"


def test_exact_pinned_version_preloaded_skips_install(env):
    env["preload"]("0.35.0")
    assert _module._ensure_sports_skills() == (True, None)
    assert env["run_calls"] == []
    assert env["import_calls"] == []


@pytest.mark.parametrize("preloaded", [None, "0.31.0", "0.33.0", "0.34.0", "0.36.0", "1.0.0"])
def test_missing_stale_or_later_version_installs_the_pin(env, preloaded):
    env["preload"](preloaded)
    env["run"] = _pip_ok
    env["import_version"] = "0.35.0"

    assert _module._ensure_sports_skills() == (True, None)
    assert len(env["run_calls"]) == 1
    assert sys.modules["sports_skills"].__version__ == "0.35.0"
    assert sys.path[0] == _module._TARGET_DIR


def test_pip_runs_exact_argv_without_shell(env):
    env["preload"]("0.34.0")
    env["run"] = _pip_ok
    env["import_version"] = "0.35.0"

    _module._ensure_sports_skills()

    (args, kwargs), = env["run_calls"]
    expected = list(_EXPECTED_ARGV)
    expected[7] = _module._TARGET_DIR
    assert args == (expected,)
    assert kwargs.get("shell", False) is False
    assert kwargs["timeout"] == _module._PIP_TIMEOUT_SECONDS


def test_pip_failure_returns_structured_false(env):
    env["preload"]("0.34.0")
    env["run"] = lambda *a, **k: subprocess.CompletedProcess(a[0], 1, stdout="", stderr="boom")

    ok, err = _module._ensure_sports_skills()
    assert ok is False
    assert "rc=1" in err and "boom" in err and "sports-skills==0.35.0" in err
    assert env["import_calls"] == []


def test_pip_timeout_returns_structured_false(env):
    env["preload"]("0.34.0")

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired(a[0], k["timeout"])

    env["run"] = timeout
    ok, err = _module._ensure_sports_skills()
    assert ok is False
    assert "timed out" in err


def test_pip_start_error_returns_structured_false(env):
    env["preload"]("0.34.0")

    def cannot_start(*a, **k):
        raise OSError("no such file")

    env["run"] = cannot_start
    ok, err = _module._ensure_sports_skills()
    assert ok is False
    assert "could not start" in err and "no such file" in err


def test_successful_pip_with_stale_import_fails(env):
    env["preload"]("0.34.0")
    env["run"] = _pip_ok
    env["import_version"] = "0.34.0"

    ok, err = _module._ensure_sports_skills()
    assert ok is False
    assert "'0.34.0'" in err and "'0.35.0'" in err


def test_successful_pip_but_not_importable_fails(env):
    env["preload"]("0.34.0")
    env["run"] = _pip_ok
    env["import_version"] = None

    ok, err = _module._ensure_sports_skills()
    assert ok is False
    assert "not importable" in err


def test_dispatch_surfaces_install_failure_without_running_command(monkeypatch):
    monkeypatch.setattr(_module, "_ensure_sports_skills", lambda: (False, "pin failed"))
    result = _module._dispatch("football", {"params": {"command": "get_competitions"}})
    assert result == {"status": False, "message": "pin failed"}


def test_bootstrap_is_registered_in_connector_yaml():
    text = open(os.path.join(_parent_dir, "sports-skills.yml"), encoding="utf-8").read()
    assert 'value: "invoke_bootstrap"' in text


def _no_dispatch(*a, **k):
    raise AssertionError("bootstrap must not dispatch to a module")


def test_bootstrap_reports_the_imported_pin_and_origin(env, monkeypatch):
    monkeypatch.setattr(_module, "_dispatch", _no_dispatch)
    env["preload"]("0.35.0")
    sys.modules["sports_skills"].__file__ = "/image.invalid/sports_skills/__init__.py"

    assert _module.invoke_bootstrap({"params": {}}) == {"status": True, "data": {
        "ready": True, "pinned_version": "0.35.0", "version": "0.35.0",
        "origin": "/image.invalid/sports_skills/__init__.py"}}
    assert env["run_calls"] == [] and env["import_calls"] == []


def test_bootstrap_installs_the_pin_on_a_cold_container(env, monkeypatch):
    monkeypatch.setattr(_module, "_dispatch", _no_dispatch)
    env["preload"](None)
    env["run"] = _pip_ok
    env["import_version"] = "0.35.0"

    result = _module.invoke_bootstrap({"params": {}})
    assert result["status"] is True
    assert (result["data"]["ready"], result["data"]["version"]) == (True, "0.35.0")
    assert len(env["run_calls"]) == 1
    assert env["import_calls"] == ["sports_skills"], "only the package itself is imported"
    assert sys.path[0] == _module._TARGET_DIR


def test_bootstrap_failure_answers_structured_data(env):
    env["preload"]("0.34.0")
    env["run"] = lambda *a, **k: subprocess.CompletedProcess(a[0], 1, stdout="", stderr="boom")

    result = _module.invoke_bootstrap({"params": {}})
    assert result["status"] is False
    data = result["data"]
    assert (data["ready"], data["pinned_version"], data["version"]) == (False, "0.35.0", "0.34.0")
    assert "rc=1" in data["error"] and "boom" in data["error"]
    assert result["message"] == data["error"]


def test_bootstrap_timeout_answers_structured_data(env):
    env["preload"](None)

    def timeout(*a, **k):
        raise subprocess.TimeoutExpired(a[0], k["timeout"])

    env["run"] = timeout
    result = _module.invoke_bootstrap({"params": {}})
    assert result["status"] is False
    assert (result["data"]["ready"], result["data"]["version"]) == (False, None)
    assert "timed out" in result["data"]["error"]
