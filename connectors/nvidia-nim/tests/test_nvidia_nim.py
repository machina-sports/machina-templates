"""Versioned tests for the nvidia-nim connector (no network, no NIM).

Run: pytest connectors/nvidia-nim/tests/ -q
Requires: langchain-openai, requests (same deps the client-api runtime has).
"""

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "nvidia_nim",
    os.path.join(os.path.dirname(__file__), "..", "nvidia-nim.py"),
)
nim = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(nim)

CONNECTOR_DIR = Path(__file__).resolve().parents[1]


ENVS = (
    "NVIDIA_NIM_CHAT_BASE_URL",
    "NVIDIA_NIM_CHAT_MODEL",
    "NVIDIA_NIM_CHAT_ALLOWED_MODELS",
    "NVIDIA_NIM_CHAT_TIMEOUT_SECONDS",
    "NVIDIA_NIM_CHAT_MAX_OUTPUT_TOKENS",
    "NVIDIA_NIM_CHAT_API_KEY",
    # Legacy mixed-family names must not affect the chat connector.
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
        monkeypatch.setenv("NVIDIA_NIM_CHAT_MAX_OUTPUT_TOKENS", "2000")

        class FakeChatOpenAI:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        fake_module = SimpleNamespace(ChatOpenAI=FakeChatOpenAI)
        with patch.dict(sys.modules, {"langchain_openai": fake_module}):
            result = nim.invoke_chat({"params": {"max_tokens": 4000, "temperature": 0}})

        assert result["status"] is True
        llm = result["data"]
        assert llm.max_tokens == 2000  # capped by env
        assert llm.temperature == 0.0

    def test_invalid_params_error_cleanly(self, nim_env):
        result = nim.invoke_chat({"params": {"max_tokens": "quatro mil"}})
        assert result["status"] == "error"
        assert "max_tokens" in result["message"]

    def test_invalid_operational_timeout_error_cleanly(self, nim_env, monkeypatch):
        monkeypatch.setenv("NVIDIA_NIM_CHAT_TIMEOUT_SECONDS", "eventually")
        result = nim.invoke_chat({})
        assert result["status"] == "error"
        assert "operational config" in result["message"]


class TestHealth:
    def test_default_model_missing_from_allowlist_is_unhealthy(self, nim_env, monkeypatch):
        monkeypatch.setenv("NVIDIA_NIM_CHAT_ALLOWED_MODELS", "nvidia/nemotron-nano")
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


class TestCompletionReceipt:
    def test_executes_real_completion_with_chat_contract(self, nim_env, monkeypatch):
        monkeypatch.setenv("NVIDIA_NIM_CHAT_API_KEY", "demo-secret")
        monkeypatch.setenv("NVIDIA_NIM_CHAT_MAX_OUTPUT_TOKENS", "12")
        response = MagicMock()
        response.json.return_value = {
            "id": "chatcmpl-receipt",
            "model": "nvidia/nemotron-3-super-120b-a12b",
            "choices": [{"message": {"content": "MACHINA_NIM_OK"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        }
        response.raise_for_status.return_value = None

        with patch.object(nim.requests, "post", return_value=response) as post:
            result = nim.completion_receipt({})

        assert result["status"] is True
        assert result["data"]["completed"] is True
        assert result["data"]["output"] == "MACHINA_NIM_OK"
        post.assert_called_once()
        _, kwargs = post.call_args
        assert post.call_args.args[0] == "http://nim:8001/v1/chat/completions"
        assert kwargs["headers"]["Authorization"] == "Bearer demo-secret"
        assert kwargs["json"]["model"] == "nvidia/nemotron-3-super-120b-a12b"
        assert kwargs["json"]["max_tokens"] == 12
        assert kwargs["json"]["stream"] is False

    def test_legacy_api_key_is_not_used(self, nim_env, monkeypatch):
        monkeypatch.setenv("NVIDIA_NIM_API_KEY", "legacy-secret")
        response = MagicMock()
        response.json.return_value = {
            "choices": [{"message": {"content": "MACHINA_NIM_OK"}}]
        }
        response.raise_for_status.return_value = None

        with patch.object(nim.requests, "post", return_value=response) as post:
            result = nim.completion_receipt({})

        assert result["status"] is True
        assert "Authorization" not in post.call_args.kwargs["headers"]

    def test_empty_completion_fails_receipt(self, nim_env):
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": ""}}]}
        response.raise_for_status.return_value = None
        with patch.object(nim.requests, "post", return_value=response):
            result = nim.completion_receipt({})
        assert result["status"] == "error"
        assert result["data"]["completed"] is False


class TestConnectorWiring:
    def test_completion_receipt_is_registered_and_run_by_credentials_workflow(self):
        manifest = (CONNECTOR_DIR / "nvidia-nim.yml").read_text()
        workflow = (CONNECTOR_DIR / "test-credentials.yml").read_text()
        assert 'value: "completion_receipt"' in manifest
        assert "command: completion_receipt" in workflow
        assert "workflow-status" in workflow
