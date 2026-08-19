"""Offline contract tests for the Cerebras connector."""

import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml


CONNECTOR_DIR = Path(__file__).resolve().parents[1]
IMPLEMENTATION = CONNECTOR_DIR / "cerebras.py"


def load_connector():
    spec = importlib.util.spec_from_file_location("cerebras_connector_tests", IMPLEMENTATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cerebras = load_connector()


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in (
        "TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY",
        "TEMP_CONTEXT_VARIABLE_SDK_CEREBRAS_API_KEY",
        "CEREBRAS_ALLOWED_MODELS",
        "CEREBRAS_DEFAULT_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def credential(monkeypatch):
    monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY", "operator-secret")


def fake_response(payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


class TestPolicyGates:
    def test_missing_credential_is_typed(self):
        result = cerebras.invoke_chat({"prompt": "hello"})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "credential_missing"

    def test_model_outside_operator_allowlist_is_rejected_before_network(self, credential):
        with patch.object(cerebras.requests, "post") as post:
            result = cerebras.invoke_chat({"model": "unapproved", "prompt": "hello"})
        assert result["metadata"]["error_class"] == "policy_model_not_allowed"
        post.assert_not_called()

    @pytest.mark.parametrize("field", ["endpoint", "base_url"])
    def test_endpoint_injection_is_rejected_before_network(self, credential, field):
        with patch.object(cerebras.requests, "post") as post:
            result = cerebras.invoke_chat({field: "https://evil.example/v1", "prompt": "hello"})
        assert result["metadata"]["error_class"] == "policy_endpoint_not_allowed"
        post.assert_not_called()

    def test_api_key_shadowing_is_rejected_before_network(self, credential):
        with patch.object(cerebras.requests, "post") as post:
            result = cerebras.invoke_chat({"api_key": "caller-secret", "prompt": "hello"})
        assert result["metadata"]["error_class"] == "policy_credential_not_allowed"
        post.assert_not_called()
        assert "caller-secret" not in json.dumps(result)

    def test_invalid_legacy_timeout_is_typed(self, credential):
        result = cerebras.invoke_chat({"timeout": "eventually", "prompt": "hello"})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "invalid_request"


class TestPromptAndChat:
    def test_prompt_factory_uses_fixed_public_endpoint(self, credential):
        chat = MagicMock(return_value="chat-model")
        with patch.dict(sys.modules, {"langchain_openai": SimpleNamespace(ChatOpenAI=chat)}):
            result = cerebras.invoke_prompt({"model": "gpt-oss-120b", "temperature": 0})
        assert result["status"] is True
        assert result["data"] == "chat-model"
        assert chat.call_args.kwargs["base_url"] == "https://api.cerebras.ai/v1"
        assert chat.call_args.kwargs["api_key"] == "operator-secret"

    def test_chat_returns_typed_receipt_without_input_or_secret(self, credential):
        response = fake_response({
            "id": "chatcmpl-1",
            "model": "gpt-oss-120b",
            "choices": [{"finish_reason": "stop", "message": {"content": "hello", "tool_calls": None}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        })
        with patch.object(cerebras.requests, "post", return_value=response) as post:
            result = cerebras.invoke_chat({"prompt": "private prompt"})
        assert result["status"] is True
        assert result["data"]["content"] == "hello"
        assert result["metadata"]["provider_request_id"] == "chatcmpl-1"
        assert result["metadata"]["usage"]["total_tokens"] == 3
        assert post.call_args.args[0] == "https://api.cerebras.ai/v1/chat/completions"
        serialized = json.dumps(result)
        assert "operator-secret" not in serialized
        assert "private prompt" not in serialized

    def test_sdk_alias_is_repository_compatible(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_SDK_CEREBRAS_API_KEY", "alias-secret")
        response = fake_response({
            "id": "chatcmpl-alias",
            "choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
        })
        with patch.object(cerebras.requests, "post", return_value=response) as post:
            result = cerebras.invoke_chat({"prompt": "hello"})
        assert result["status"] is True
        assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer alias-secret"


class TestManagementAndErrors:
    def test_list_models_filters_remote_catalog_through_operator_allowlist(self, credential):
        response = fake_response({"data": [
            {"id": "gpt-oss-120b", "owned_by": "Cerebras"},
            {"id": "not-approved", "owned_by": "other"},
        ]})
        with patch.object(cerebras.requests, "get", return_value=response):
            result = cerebras.list_models({})
        assert result["status"] is True
        assert [item["id"] for item in result["data"]["models"]] == ["gpt-oss-120b"]
        assert result["data"]["allowed"] == ["gpt-oss-120b", "gemma-4-31b"]

    def test_health_is_typed_and_sanitized(self, credential):
        response = fake_response({"data": [{"id": "gpt-oss-120b"}]})
        with patch.object(cerebras.requests, "get", return_value=response):
            result = cerebras.health({})
        assert result["status"] is True
        assert result["data"]["healthy"] is True
        assert "operator-secret" not in json.dumps(result)

    def test_completion_receipt_executes_small_completion(self, credential):
        response = fake_response({
            "id": "chatcmpl-receipt",
            "model": "gpt-oss-120b",
            "choices": [{"finish_reason": "stop", "message": {"content": "MACHINA_CEREBRAS_OK"}}],
            "usage": {"total_tokens": 7},
        })
        with patch.object(cerebras.requests, "post", return_value=response) as post:
            result = cerebras.completion_receipt({})
        assert result["status"] is True
        assert result["data"]["completed"] is True
        assert result["data"]["output"] == "MACHINA_CEREBRAS_OK"
        assert post.call_args.kwargs["json"]["max_tokens"] == 16

    @pytest.mark.parametrize(
        "status_code,error_class",
        [(400, "invalid_request"), (401, "provider_authentication"),
         (403, "provider_authentication"), (413, "provider_content_rejected"),
         (429, "provider_rate_limited"), (500, "provider_unavailable"),
         (503, "provider_unavailable")],
    )
    def test_http_errors_are_typed_and_sanitized(self, credential, status_code, error_class):
        error = RuntimeError("operator-secret private prompt")
        error.response = SimpleNamespace(status_code=status_code)
        with patch.object(cerebras.requests, "post", side_effect=error):
            result = cerebras.invoke_chat({"prompt": "private prompt"})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == error_class
        assert "operator-secret" not in json.dumps(result)
        assert "private prompt" not in json.dumps(result)

    @pytest.mark.parametrize(
        "command,payload",
        [("invoke_chat", {"choices": {"bad": "shape"}}), ("list_models", {"data": None}),
         ("health", {"data": None}),
         ("invoke_chat", {"choices": [{"message": {"content": None, "tool_calls": 1}}]})],
    )
    def test_malformed_provider_shapes_return_typed_bad_response(self, credential, command, payload):
        response = fake_response(payload)
        method = "post" if command == "invoke_chat" else "get"
        with patch.object(cerebras.requests, method, return_value=response):
            params = {"prompt": "hello"} if command == "invoke_chat" else {}
            result = getattr(cerebras, command)(params)
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "provider_bad_response"

    def test_invalid_json_is_typed_as_transient_bad_response(self, credential):
        response = fake_response({})
        response.json.side_effect = ValueError("invalid JSON with operator-secret")
        with patch.object(cerebras.requests, "post", return_value=response):
            result = cerebras.invoke_chat({"prompt": "private prompt"})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "provider_bad_response"
        assert "operator-secret" not in json.dumps(result)


class TestPackageParity:
    def test_manifest_install_and_smoke_workflow_are_in_parity(self):
        manifest = yaml.safe_load((CONNECTOR_DIR / "cerebras.yml").read_text())
        install = yaml.safe_load((CONNECTOR_DIR / "_install.yml").read_text())
        smoke = (CONNECTOR_DIR / "test-credentials.yml").read_text()
        declared = {item["value"] for item in manifest["connector"]["commands"]}
        assert declared == {"invoke_prompt", "invoke_chat", "list_models", "health", "completion_receipt"}
        assert all(callable(getattr(cerebras, command)) for command in declared)
        paths = {item["path"] for item in install["datasets"]}
        assert paths == {"cerebras.yml", "test-credentials.yml"}
        assert "$TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY" in smoke
        assert "command: completion_receipt" in smoke
        assert "workflow-status" in smoke
        assert "api_key:" not in "\n".join(
            line for line in smoke.splitlines() if "$TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY" not in line
        )

    def test_connector_executes_without_file_global(self):
        source = IMPLEMENTATION.read_text()
        namespace = {"__builtins__": __builtins__}
        exec(compile(source, "<cerebras>", "exec"), namespace)
        assert "__file__" not in namespace
        result = namespace["invoke_chat"]({"prompt": "hello"})
        assert result["metadata"]["error_class"] == "credential_missing"
