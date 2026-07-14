"""Versioned tests for the nvidia-nim connector (no network, no NIM).

Run: pytest connectors/nvidia-nim/tests/ -q
Requires: langchain-openai, requests (same deps the client-api runtime has).
"""

import importlib.util
import os
from unittest.mock import MagicMock, patch

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "nvidia_nim",
    os.path.join(os.path.dirname(__file__), "..", "nvidia-nim.py"),
)
nim = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(nim)


ENVS = (
    "NVIDIA_NIM_CHAT_BASE_URL",
    "NVIDIA_NIM_CHAT_MODEL",
    "NVIDIA_NIM_ALLOWED_MODELS",
    "NVIDIA_NIM_TIMEOUT_SECONDS",
    "NVIDIA_NIM_MAX_OUTPUT_TOKENS",
    "NVIDIA_NIM_API_KEY",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ENVS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def nim_env(monkeypatch):
    monkeypatch.setenv("NVIDIA_NIM_CHAT_BASE_URL", "http://nim:8001/v1")
    monkeypatch.setenv("NVIDIA_NIM_CHAT_MODEL", "nvidia/nemotron-3-super-120b-a12b")


class TestOperationalConfigGates:
    def test_missing_config_fails_closed(self):
        result = nim.invoke_chat({"value": "hi"})
        assert result["status"] == "error"
        assert "NVIDIA_NIM_CHAT_BASE_URL" in result["message"]

    def test_workflow_supplied_base_url_fails_closed(self, nim_env):
        result = nim.invoke_chat({"params": {"base_url": "http://evil:9/v1"}})
        assert result["status"] == "error"
        assert "operational config" in result["message"]

    def test_model_outside_allowlist_rejected(self, nim_env):
        result = nim.invoke_chat({"model_name": "some-other-model"})
        assert result["status"] == "error"
        assert "ALLOWED_MODELS" in result["message"]


class TestInvokeChat:
    def test_happy_path_builds_chat_openai(self, nim_env, monkeypatch):
        monkeypatch.setenv("NVIDIA_NIM_MAX_OUTPUT_TOKENS", "2000")
        result = nim.invoke_chat({"params": {"max_tokens": 4000, "temperature": 0}})
        assert result["status"] is True
        llm = result["data"]
        assert llm.max_tokens == 2000  # capped by env
        assert llm.temperature == 0.0

    def test_invalid_params_error_cleanly(self, nim_env):
        result = nim.invoke_chat({"params": {"max_tokens": "quatro mil"}})
        assert result["status"] == "error"
        assert "max_tokens" in result["message"]


class TestHealth:
    def test_default_model_missing_from_allowlist_is_unhealthy(self, nim_env, monkeypatch):
        monkeypatch.setenv("NVIDIA_NIM_ALLOWED_MODELS", "nvidia/nemotron-nano")
        result = nim.health({})
        assert result["status"] == "error"
        assert result["data"]["healthy"] is False
        failed = [c for c in result["data"]["checks"] if c["check"] == "default_model_allowlisted"]
        assert failed and failed[0]["ok"] is False

    def test_endpoint_timeout_is_a_failed_check_not_an_exception(self, nim_env):
        with patch.object(nim.requests, "get", side_effect=Exception("timed out")):
            result = nim.health({})
        assert result["status"] == "error"
        reach = [c for c in result["data"]["checks"] if c["check"] == "endpoint_reachable"]
        assert reach and reach[0]["ok"] is False

    def test_healthy_when_default_model_served(self, nim_env):
        response = MagicMock()
        response.json.return_value = {"data": [{"id": "nvidia/nemotron-3-super-120b-a12b"}]}
        response.raise_for_status.return_value = None
        with patch.object(nim.requests, "get", return_value=response):
            result = nim.health({})
        assert result["status"] is True
        assert result["data"]["healthy"] is True


class TestListModels:
    def test_lists_served_and_allowlist(self, nim_env):
        response = MagicMock()
        response.json.return_value = {"data": [{"id": "a"}, {"id": "b"}]}
        response.raise_for_status.return_value = None
        with patch.object(nim.requests, "get", return_value=response):
            result = nim.list_models({})
        assert result["status"] is True
        assert result["data"]["models"] == ["a", "b"]
        assert result["data"]["default"] == "nvidia/nemotron-3-super-120b-a12b"
