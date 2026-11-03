import copy
import importlib.util
import inspect
import json
import os
import re
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

CONNECTOR_DIR = Path(__file__).resolve().parents[1]
ROOT = CONNECTOR_DIR.parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


router = load_module("machina_ai_router_tests", CONNECTOR_DIR / "machina-ai.py")


class FakeAdapter:
    def __init__(self, failures=None):
        self.failures = failures or {}
        self.calls = []
        self.routes = []
        self.factory = object()
        self.embedding_factory = object()

    def _call(self, name, route, request, data):
        self.calls.append((name, route.provider, route.model, request))
        self.routes.append(route)
        failure = self.failures.get(name)
        if failure:
            if callable(failure):
                failure()
            raise failure
        return router.AdapterResult(data, provider_request_id=f"req-{route.provider}", usage={"total_tokens": 3})

    def create_chat_model(self, route, request):
        return self._call("create_chat_model", route, request, self.factory)

    def invoke_chat(self, route, request):
        return self._call("invoke_chat", route, request, router._chat_data("ok"))

    def create_embedding_model(self, route, request):
        return self._call("create_embedding_model", route, request, self.embedding_factory)

    def embed(self, route, request):
        values = request.input.get("texts") or request.input.get("input") or request.input.get("text")
        data = [0.1, 0.2] if isinstance(values, str) else [[0.1], [0.2]]
        return self._call("embed", route, request, data)

    def invoke_search(self, route, request):
        return self._call("invoke_search", route, request, router._chat_data("found", citations=[{"url": "https://example.test"}]))

    def invoke_image(self, route, request):
        return self._call("invoke_image", route, request, {"path": "image.png", "bytes": 4})

    def invoke_video(self, route, request):
        return self._call("invoke_video", route, request, {"task_id": "task-1", "state": "queued"})

    def transcribe(self, route, request):
        return self._call("transcribe", route, request, {"text": "hello", "segments": []})

    def invoke_tts(self, route, request):
        return self._call("invoke_tts", route, request, {"path": "speech.mp3"})

    def voice(self, route, request):
        return self._call("voice", route, request, {"voices": []})

    def invoke_music(self, route, request):
        return self._call("invoke_music", route, request, {"path": "music.wav"})


class FakeRuntime:
    def __init__(self, config=None, adapters=None, trusted_headers=None):
        self._config = config or {}
        self.adapters = adapters or {"vertex_ai": FakeAdapter()}
        self._trusted_headers = trusted_headers or {}
        self.task_events = []
        self.circuit_events = []
        self.delegations = []

    def config(self, key=None):
        return self._config

    def adapter(self, provider):
        return self.adapters.get(provider)

    def trusted_headers(self):
        return self._trusted_headers

    def scope(self):
        return {"tenant_id": "tenant-1", "project_id": "project-1", "actor_id": "actor-1"}

    def task(self, action, payload):
        self.task_events.append((action, payload))
        if action == "authorize":
            return {"authorized": True}
        if action == "record":
            return {"recorded": True}
        return None

    def circuit(self, action, route_id, **kwargs):
        self.circuit_events.append((action, route_id, kwargs))
        return True


def enabled_config(*providers, **extra):
    provider_config = {}
    for provider in providers:
        provider_config[provider] = {
            "enabled": True,
            "allowed_models": {"chat": [f"{provider}-chat"], "embedding": [f"{provider}-embed"]},
        }
    base = {"providers": provider_config}
    return router._deep_merge(base, extra)


class TestNormalization:
    @pytest.mark.parametrize(
        "params",
        [
            {"priority_paygo": True},
            {"params": {"priority_paygo": True}},
            {"options": {"priority_paygo": True}},
        ],
    )
    def test_priority_paygo_normalizes_as_a_canonical_boolean_option(self, params):
        request = router.Router(FakeRuntime()).normalizer.normalize("invoke_prompt", params)
        assert request.options["priority_paygo"] is True

    @pytest.mark.parametrize("value", ["true", "false", 1, 0, [], {}])
    def test_priority_paygo_rejects_non_boolean_values(self, value):
        adapter = FakeAdapter()
        result = router.invoke_prompt({
            "_runtime": FakeRuntime(adapters={"vertex_ai": adapter}),
            "priority_paygo": value,
        })
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "unsupported_option"
        assert adapter.calls == []

    def test_strict_image_options_survive_the_pod_params_boundary(self):
        request = router.Router(FakeRuntime()).normalizer.normalize("invoke_image", {"params": {
            "provider": "vertex_ai", "model_name": "gemini-3.1-flash-image",
            "prompt": "Text-free background", "strict_image": True, "image_size": "1K", "aspect_ratio": "16:9",
        }})
        assert request.options["strict_image"] is True
        assert request.options["image_size"] == "1K"
        assert request.options["aspect_ratio"] == "16:9"
        assert request.model == "gemini-3.1-flash-image"

    def test_canonical_top_level_wins_alias_and_nested_sources(self):
        runtime = FakeRuntime()
        request = router.Router(runtime).normalizer.normalize(
            "invoke_chat",
            {
                "model": "gemini-2.5-flash",
                "model_name": "top-alias",
                "params": {"model": "nested-model", "timeout": 20},
                "headers": {"model": "ignored-header", "api_key": "header-secret", "unknown": "drop"},
                "path_attribute": {"id": "task-1", "unknown": "drop"},
                "prompt": "hello",
            },
        )
        assert request.model == "gemini-2.5-flash"
        assert request.options["timeout_ms"] == 20000
        assert request.security["api_key"] == "header-secret"
        assert request.options["task_id"] == "task-1"
        assert request.conflicts

    @pytest.mark.parametrize("value,expected", [(20, 20000), (20000, 20000), ("bad", 30000)])
    def test_legacy_timeout_normalization(self, value, expected):
        request = router.Router(FakeRuntime()).normalizer.normalize("invoke_prompt", {"timeout": value})
        assert request.options["timeout_ms"] == expected

    def test_factory_command_never_switches_to_execute_from_prompt(self):
        request = router.Router(FakeRuntime()).normalizer.normalize("invoke_prompt", {"prompt": "do not send"})
        assert request.operation_mode == "factory"

    def test_trusted_header_credential_precedes_workflow_sources(self):
        runtime = FakeRuntime(trusted_headers={"api_key": True})
        request = router.Router(runtime).normalizer.normalize(
            "invoke_chat",
            {"api_key": "caller-secret", "headers": {"api_key": "trusted-secret"}, "prompt": "hello"},
        )
        assert request.security["api_key"] == "trusted-secret"
        assert request.security["_credential_trusted"] is True

    def test_aliases_and_legacy_transcription_envelope(self):
        request = router.Router(FakeRuntime()).normalizer.normalize(
            "transcribe_audio_to_text",
            {"headers": {"api_key": "secret"}, "params": {"audio-path": ["/tmp/audio.mp3"]}},
        )
        assert request.capability == "transcription"
        assert request.input["audio_path"] == "/tmp/audio.mp3"
        assert request.security["api_key"] == "secret"

    def test_streaming_is_typed_unsupported(self):
        result = router.invoke_chat({"_runtime": FakeRuntime(), "stream": True, "prompt": "hello"})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "unsupported_option"
        assert result["error"] == result["message"]


class TestRoutingAndReceipts:
    def test_repository_default_is_vertex(self):
        runtime = FakeRuntime()
        result = router.invoke_prompt({"_runtime": runtime})
        assert result["status"] is True
        assert result["data"] is runtime.adapters["vertex_ai"].factory
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert result["metadata"]["selected_model"] == "gemini-3.5-flash-lite"
        assert result["metadata"]["route_reason"] == "profile:balanced"
        assert result["metadata"]["requested_profile"] == "balanced"
        assert result["metadata"]["decision_method"] == "profile"
        assert result["metadata"]["resolved_route"] == {
            "provider": "vertex_ai",
            "model": "gemini-3.5-flash-lite",
            "capability": "chat",
            "operation_mode": "factory",
        }

    def test_direct_chat_returns_canonical_envelope_and_receipt(self):
        result = router.invoke_chat({"_runtime": FakeRuntime(), "prompt": "hello"})
        assert result["status"] is True
        assert set(result) == {"status", "data", "message", "metadata"}
        assert result["data"]["role"] == "assistant"
        assert result["data"]["content"] == "ok"
        assert "router_receipt" not in result["data"]["provider_extensions"]
        assert result["metadata"]["provider_request_id"] == "req-vertex_ai"
        assert result["metadata"]["usage"] == {"total_tokens": 3}

    @pytest.mark.parametrize("requested", [True, False])
    def test_receipt_records_requested_priority_without_claiming_acknowledgement(self, requested):
        result = router.invoke_prompt({"_runtime": FakeRuntime(), "priority_paygo": requested})
        assert result["status"] is True
        assert result["metadata"]["requested_priority_paygo"] is requested
        assert "priority_acknowledged" not in result["metadata"]

    def test_default_receipt_does_not_claim_priority(self):
        result = router.invoke_prompt({"_runtime": FakeRuntime()})
        assert result["status"] is True
        assert "requested_priority_paygo" not in result["metadata"]

    def test_search_embeds_exact_router_receipt_in_data(self):
        result = router.invoke_search({"_runtime": FakeRuntime(), "prompt": "latest"})

        assert result["status"] is True
        assert result["data"]["provider_extensions"] == {
            "router_receipt": {
                "selected_provider": "vertex_ai",
                "selected_model": "gemini-3.5-flash-lite",
                "resolved_route": {
                    "provider": "vertex_ai",
                    "model": "gemini-3.5-flash-lite",
                    "capability": "search_answer",
                    "operation_mode": "execute",
                },
                "decision_method": "profile",
                "requested_profile": "balanced",
                "route_reason": "profile:balanced",
                "fallback_used": False,
                "provider_request_id": "req-vertex_ai",
            }
        }
        for key, value in result["data"]["provider_extensions"]["router_receipt"].items():
            assert result["metadata"][key] == value

    def test_search_model_output_cannot_override_router_receipt(self):
        class SpoofingAdapter(FakeAdapter):
            def invoke_search(self, route, request):
                data = router._chat_data(
                    "found",
                    citations=[{"url": "https://example.test"}],
                    extensions={
                        "provider_marker": "preserved",
                        "router_receipt": {
                            "selected_provider": "attacker",
                            "selected_model": "attacker-model",
                            "route_reason": "model_output",
                            "fallback_used": True,
                            "provider_request_id": "attacker-request",
                        },
                    },
                )
                return router.AdapterResult(data, provider_request_id="trusted-request")

        result = router.invoke_search({
            "_runtime": FakeRuntime(adapters={"vertex_ai": SpoofingAdapter()}),
            "prompt": "latest",
        })

        assert result["data"]["content"] == "found"
        assert result["data"]["citations"] == [{"url": "https://example.test"}]
        assert result["data"]["provider_extensions"]["provider_marker"] == "preserved"
        assert result["data"]["provider_extensions"]["router_receipt"] == {
            "selected_provider": "vertex_ai",
            "selected_model": "gemini-3.5-flash-lite",
            "resolved_route": {
                "provider": "vertex_ai",
                "model": "gemini-3.5-flash-lite",
                "capability": "search_answer",
                "operation_mode": "execute",
            },
            "decision_method": "profile",
            "requested_profile": "balanced",
            "route_reason": "profile:balanced",
            "fallback_used": False,
            "provider_request_id": "trusted-request",
        }

    def test_embedding_factory_and_direct_aliases(self):
        runtime = FakeRuntime()
        factory = router.invoke_embedding({"_runtime": runtime})
        query = router.embed_query({"_runtime": runtime, "input": "hello"})
        documents = router.embed_documents({"_runtime": runtime, "texts": ["a", "b"]})
        assert factory["data"] is runtime.adapters["vertex_ai"].embedding_factory
        assert query["data"] == [0.1, 0.2]
        assert documents["data"] == [[0.1], [0.2]]

    def test_explicit_allowed_provider_wins_profile(self):
        groq = FakeAdapter()
        runtime = FakeRuntime(
            config={
                "providers": {"groq": {"enabled": True, "credential": "groq-secret", "allowed_models": {"chat": ["groq-chat"]}}},
                "profiles": {"fast": {"chat": [{"provider": "groq", "model": "groq-chat"}]}},
            },
            adapters={"vertex_ai": FakeAdapter(), "groq": groq},
        )
        result = router.invoke_chat({"_runtime": runtime, "provider": "groq", "model": "groq-chat", "profile": "balanced", "prompt": "hello"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"
        assert result["metadata"]["route_reason"] == "explicit_provider"
        assert result["metadata"]["decision_method"] == "explicit_override"

    def test_profile_and_global_remap(self):
        groq = FakeAdapter()
        runtime = FakeRuntime(
            config={
                "providers": {"groq": {"enabled": True, "credential": "groq-secret", "allowed_models": {"chat": ["groq-chat"]}}},
                "profiles": {"fast": {"chat": [{"provider": "groq", "model": "groq-chat"}]}},
                "remaps": {"profiles": {"fast": {"chat": {"provider": "groq", "model": "groq-chat"}}}},
            },
            adapters={"vertex_ai": FakeAdapter(), "groq": groq},
        )
        result = router.invoke_prompt({"_runtime": runtime, "profile": "fast"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"
        assert result["metadata"]["route_reason"] == "remap:profile:fast"
        assert result["metadata"]["decision_method"] == "profile_remap"

    def test_disallowed_provider_and_model_are_typed(self):
        provider = router.invoke_chat({"_runtime": FakeRuntime(), "provider": "perplexity", "prompt": "hello"})
        model = router.invoke_chat({"_runtime": FakeRuntime(), "model": "not-allowed", "prompt": "hello"})
        assert provider["metadata"]["error_class"] == "policy_provider_not_allowed"
        assert model["metadata"]["error_class"] == "policy_model_not_allowed"

    def test_list_models_hides_disabled_provider_models(self):
        result = router.list_models({"_runtime": FakeRuntime()})
        assert result["status"] is True
        providers = {item["provider"] for item in result["data"]}
        # groq and google_speech ship enabled (env-only credentials) for no-regression.
        # xai ships enabled but require_credential, so a tenant without an XAI key
        # gets a typed credential_missing and falls through to the profile's
        # Vertex entry rather than losing the run.
        assert providers == {"vertex_ai", "groq", "google_speech", "xai"}
        assert "openai" not in providers
        assert all(item["enabled"] for item in result["data"])

    def test_list_models_publishes_what_each_profile_is_for(self):
        result = router.list_models({"_runtime": FakeRuntime()})
        profiles = {item["profile"]: item for item in result["metadata"]["profiles"]}

        # The intent map travels in metadata so `data` stays a list of models
        # and callers iterating it never meet a second entry shape.
        assert not any("profile" in item for item in result["data"])
        assert "social_pulse" in profiles
        assert "live_search" in profiles
        assert "paraphrased" in profiles["social_pulse"]["intent"]
        assert "search_answer" in profiles["social_pulse"]["capabilities"]
        # Every advertised profile has to actually route somewhere; an intent
        # with no routes is a promise the router cannot keep, so it is not
        # published at all.
        for name, entry in profiles.items():
            assert entry["capabilities"], f"profile {name} advertises no routes"
        assert "multimodal" not in profiles

    def test_credential_accepts_either_storage_form(self):
        # The same secret is stored as a whole Authorization header value for a
        # restapi connector and as a bare token for an SDK client. Every client
        # here does `Bearer {api_key}`, so a stored scheme would double up and
        # the provider rejects it with a message that hides the real cause.
        module = router
        assert module._bare_credential("api_key", "Bearer xai-abc123") == "xai-abc123"
        assert module._bare_credential("api_key", "bearer  xai-abc123") == "xai-abc123"
        assert module._bare_credential("credential", "Token xai-abc123") == "xai-abc123"
        # A bare token is untouched.
        assert module._bare_credential("api_key", "xai-abc123") == "xai-abc123"
        # Non-credential fields are never rewritten.
        assert module._bare_credential("endpoint", "Bearer https://x") == "Bearer https://x"
        # A value that is nothing but a scheme is kept rather than emptied.
        assert module._bare_credential("api_key", "Bearer ") == "Bearer "

    def test_allowed_workflow_credential_outranks_a_stale_environment(self, monkeypatch):
        # The pod environment is baked when the project is provisioned, so a key
        # rotated or added since is stale there while the vault — what a workflow
        # context-variable resolves against — is current. Preferring the
        # environment made that staleness invisible: the provider reported a bad
        # key for a credential the operator had just saved correctly.
        monkeypatch.setenv("GROQ_STALE_ENV_KEY", "stale-from-env")
        groq = FakeAdapter()
        runtime = FakeRuntime(
            config={
                "policy": {"allow_workflow_credentials": True},
                "providers": {"groq": {
                    "enabled": True,
                    "credential_env": "GROQ_STALE_ENV_KEY",
                    "allowed_models": {"chat": ["groq-chat"]},
                }},
                "profiles": {"fast": {"chat": [{"provider": "groq", "model": "groq-chat"}]}},
            },
            adapters={"vertex_ai": FakeAdapter(), "groq": groq},
        )
        result = router.invoke_chat({
            "_runtime": runtime, "provider": "groq", "model": "groq-chat",
            "prompt": "hello", "headers": {"api_key": "fresh-from-vault"},
        })

        assert result["status"] is True
        assert groq.routes[-1].credentials["api_key"] == "fresh-from-vault"

    def test_workflow_credential_is_refused_when_policy_disallows_it(self, monkeypatch):
        # With the default policy the configured credential stands and the
        # workflow's is ignored — it must not be able to swap in its own.
        monkeypatch.setenv("GROQ_STALE_ENV_KEY", "configured-secret")
        groq = FakeAdapter()
        runtime = FakeRuntime(
            config={
                "providers": {"groq": {
                    "enabled": True,
                    "credential_env": "GROQ_STALE_ENV_KEY",
                    "allowed_models": {"chat": ["groq-chat"]},
                }},
                "profiles": {"fast": {"chat": [{"provider": "groq", "model": "groq-chat"}]}},
            },
            adapters={"vertex_ai": FakeAdapter(), "groq": groq},
        )
        result = router.invoke_chat({
            "_runtime": runtime, "provider": "groq", "model": "groq-chat",
            "prompt": "hello", "headers": {"api_key": "workflow-supplied"},
        })

        assert result["status"] is True
        assert groq.routes[-1].credentials["api_key"] == "configured-secret"

        # And with nothing configured it is a typed refusal, not a silent pass.
        monkeypatch.delenv("GROQ_STALE_ENV_KEY", raising=False)
        refused = router.invoke_chat({
            "_runtime": runtime, "provider": "groq", "model": "groq-chat",
            "prompt": "hello", "headers": {"api_key": "workflow-supplied"},
        })
        assert refused["status"] is False
        assert refused["metadata"]["error_class"] == "credential_missing"

    def test_workflow_credential_stays_gated_by_policy(self):
        # Default policy is allow_workflow_credentials: False. A workflow must
        # not be able to swap in its own credential unless an operator opted in
        # or the runtime marked the header trusted.
        assert router.DEFAULT_CONFIG["policy"]["allow_workflow_credentials"] is False
        # The canonical fields are the ones the normalizer already accepts, so
        # there is exactly one workflow-credential path, not a parallel one.
        assert "api_key" in router.HEADER_FIELDS
        assert "credential" in router.HEADER_FIELDS

    def test_social_profiles_fall_back_to_vertex(self):
        # An absent XAI credential must cost recency, not the whole workflow.
        config = router.DEFAULT_CONFIG
        for name in ("social_pulse", "live_search"):
            routes = config["profiles"][name]["search_answer"]
            assert routes[0]["provider"] == "xai"
            assert routes[-1]["provider"] == "vertex_ai"

    def test_health_is_local_and_structured(self):
        result = router.health({"_runtime": FakeRuntime()})
        assert result["status"] is True
        vertex = next(item for item in result["data"] if item["provider"] == "vertex_ai")
        assert vertex["enabled"] is True
        assert "capabilities" in vertex


class TestGemini35FlashLiteDefaults:
    MODEL = "gemini-3.5-flash-lite"

    def test_default_chat_config_uses_gemini_35_flash_lite(self):
        assert router.DEFAULT_CONFIG["defaults"]["chat"] == {
            "provider": "vertex_ai",
            "model": self.MODEL,
        }

    @pytest.mark.parametrize("profile", ["default", "balanced", "quality", "cheap", "long_context"])
    def test_gemini_chat_profiles_use_gemini_35_flash_lite(self, profile):
        result = router.invoke_prompt({"_runtime": FakeRuntime(), "profile": profile})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert result["metadata"]["selected_model"] == self.MODEL
        assert result["metadata"]["route_reason"] == f"profile:{profile}"

    def test_search_default_and_balanced_profile_use_gemini_35_flash_lite(self):
        assert router.DEFAULT_CONFIG["defaults"]["search_answer"] == {
            "provider": "vertex_ai",
            "model": self.MODEL,
        }
        result = router.invoke_search({"_runtime": FakeRuntime(), "profile": "balanced", "prompt": "latest"})
        assert result["status"] is True
        assert result["metadata"]["selected_model"] == self.MODEL
        assert result["metadata"]["route_reason"] == "profile:balanced"

    def test_vertex_allowlists_include_gemini_35_flash_lite(self):
        allowed = router.DEFAULT_CONFIG["providers"]["vertex_ai"]["allowed_models"]
        assert self.MODEL in allowed["chat"]
        assert self.MODEL in allowed["search_answer"]

    def test_exact_model_passes_policy_and_arbitrary_model_is_refused(self):
        accepted = router.invoke_chat({"_runtime": FakeRuntime(), "model": self.MODEL, "prompt": "hello"})
        refused = router.invoke_chat({"_runtime": FakeRuntime(), "model": "gemini-arbitrary-unsupported", "prompt": "hello"})
        assert accepted["status"] is True
        assert accepted["metadata"]["selected_model"] == self.MODEL
        assert refused["status"] is False
        assert refused["metadata"]["error_class"] == "policy_model_not_allowed"

    def test_profile_only_priority_factory_selects_exact_model_and_vertex_header(self):
        class InProcessRuntime:
            def config(self, key=None):
                return {}

            def adapter(self, provider):
                return None

        fake_chat = MagicMock(return_value="vertex-chat")
        vertex_module = SimpleNamespace(ChatVertexAI=fake_chat, VertexAIEmbeddings=MagicMock())
        with patch.dict(sys.modules, {"langchain_google_vertexai": vertex_module}):
            result = router.invoke_prompt({
                "_runtime": InProcessRuntime(),
                "profile": "balanced",
                "priority_paygo": True,
            })

        assert result["status"] is True
        assert result["data"] == "vertex-chat"
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert result["metadata"]["selected_model"] == self.MODEL
        assert fake_chat.call_args.kwargs["additional_headers"] == {
            "x-vertex-ai-llm-shared-request-type": "priority"
        }

    def test_management_commands_expose_gemini_35_flash_lite(self):
        models = router.list_models({"_runtime": FakeRuntime()})
        health = router.health({"_runtime": FakeRuntime()})
        assert {
            "provider": "vertex_ai",
            "model": self.MODEL,
            "capability": "chat",
            "enabled": True,
        } in models["data"]
        vertex = next(item for item in health["data"] if item["provider"] == "vertex_ai")
        assert self.MODEL in vertex["models"]["chat"]


class TestBroadcastModelCompatibility:
    @pytest.mark.parametrize("command,model", [
        ("invoke_prompt", "gemini-3.8-flash"),
        ("invoke_search", "gemini-3.8-flash"),
        ("invoke_image", "gemini-3.1-flash-image"),
    ])
    def test_explicit_broadcast_models_are_admitted_without_changing_defaults(self, command, model):
        result = getattr(router, command)({"_runtime": FakeRuntime(), "provider": "vertex_ai", "model": model, "prompt": "test"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert result["metadata"]["selected_model"] == model
        assert result["metadata"]["fallback_used"] is False
        assert router.DEFAULT_CONFIG["defaults"]["chat"]["model"] == "gemini-3.5-flash-lite"

    def test_operator_model_restrictions_still_override_new_allowances(self):
        adapter = FakeAdapter()
        runtime = FakeRuntime(config={"providers": {"vertex_ai": {"allowed_models": {"chat": ["gemini-3.5-flash-lite"]}}}}, adapters={"vertex_ai": adapter})
        result = router.invoke_prompt({"_runtime": runtime, "provider": "vertex_ai", "model": "gemini-3.8-flash"})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "policy_model_not_allowed"
        assert adapter.calls == []


class TestFallbacks:
    def test_transient_failure_falls_back_with_independent_route(self):
        primary = FakeAdapter({"invoke_chat": router.RouterError("provider_timeout", "timed out", transient=True)})
        fallback = FakeAdapter()
        runtime = FakeRuntime(
            config={
                "providers": {"groq": {"enabled": True, "allowed_models": {"chat": ["groq-chat"]}, "credential": "groq-secret"}},
                "fallbacks": {"chat": {"vertex_ai": [{"provider": "groq", "model": "groq-chat"}]}},
            },
            adapters={"vertex_ai": primary, "groq": fallback},
        )
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello"})
        assert result["status"] is True
        assert result["metadata"]["fallback_used"] is True
        assert result["metadata"]["selected_provider"] == "groq"
        assert result["metadata"]["decision_method"] == "fallback"
        assert result["metadata"]["fallback_attempts"][0]["error_class"] == "provider_timeout"

    def test_authentication_and_invalid_request_do_not_fallback(self):
        primary = FakeAdapter({"invoke_chat": router.RouterError("provider_authentication", "bad credential")})
        fallback = FakeAdapter()
        runtime = FakeRuntime(
            config={
                "providers": {"groq": {"enabled": True, "allowed_models": {"chat": ["groq-chat"]}}},
                "fallbacks": {"chat": {"vertex_ai": [{"provider": "groq", "model": "groq-chat"}]}},
            },
            adapters={"vertex_ai": primary, "groq": fallback},
        )
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello"})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "provider_authentication"
        assert not fallback.calls

    def test_deadline_blocks_late_fallback(self):
        def slow_failure():
            time.sleep(0.01)

        primary = FakeAdapter({"invoke_chat": slow_failure})
        # Callable returns then FakeAdapter raises the callable object; use explicit adapter below.
        class SlowAdapter(FakeAdapter):
            def invoke_chat(self, route, request):
                time.sleep(0.01)
                raise router.RouterError("provider_timeout", "timed out", transient=True)

        fallback = FakeAdapter()
        runtime = FakeRuntime(
            config={
                "policy": {"total_deadline_ms": 1},
                "providers": {"groq": {"enabled": True, "allowed_models": {"chat": ["groq-chat"]}}},
                "fallbacks": {"chat": {"vertex_ai": [{"provider": "groq", "model": "groq-chat"}]}},
            },
            adapters={"vertex_ai": SlowAdapter(), "groq": fallback},
        )
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello"})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "provider_timeout"
        assert not fallback.calls


class TestSecurity:
    def test_runtime_credential_and_endpoint_cannot_be_shadowed(self):
        runtime = FakeRuntime(
            config={
                "policy": {"allow_workflow_credentials": True, "allow_custom_base_url": True, "allowed_endpoint_hosts": ["caller.test"]},
                "providers": {
                    "openai_compatible": {
                        "enabled": True,
                        "protected": True,
                        "credential": "runtime-secret",
                        "endpoint": "https://runtime.internal/v1",
                        "allowed_models": {"chat": ["approved"]},
                    }
                },
            },
            adapters={"openai_compatible": FakeAdapter()},
        )
        result = router.invoke_chat({
            "_runtime": runtime,
            "provider": "openai_compatible",
            "model": "approved",
            "api_key": "caller-secret",
            "base_url": "https://caller.test/v1",
            "prompt": "secret prompt",
        })
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "policy_endpoint_not_allowed"
        serialized = json.dumps(result)
        assert "caller-secret" not in serialized
        assert "secret prompt" not in serialized

    def test_caller_endpoint_denied_by_default(self):
        runtime = FakeRuntime(
            config={"providers": {"openai_compatible": {"enabled": True, "allowed_models": {"chat": ["approved"]}}}},
            adapters={"openai_compatible": FakeAdapter()},
        )
        result = router.invoke_chat({"_runtime": runtime, "provider": "openai_compatible", "model": "approved", "base_url": "https://example.com/v1", "prompt": "hi"})
        assert result["metadata"]["error_class"] == "policy_endpoint_not_allowed"

    def test_nim_endpoint_override_and_model_allowlist_fail_before_adapter(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_NIM_CHAT_BASE_URL", "http://nim:8001/v1")
        monkeypatch.setenv("NVIDIA_NIM_CHAT_MODEL", "allowed-model")
        monkeypatch.setenv("NVIDIA_NIM_CHAT_ALLOWED_MODELS", "allowed-model")
        adapter = FakeAdapter()
        runtime = FakeRuntime(adapters={"nvidia_nim": adapter})
        endpoint = router.invoke_prompt({"_runtime": runtime, "provider": "nvidia_nim", "base_url": "http://evil/v1"})
        model = router.invoke_prompt({"_runtime": runtime, "provider": "nvidia_nim", "model": "bad-model"})
        assert endpoint["metadata"]["error_class"] == "policy_endpoint_not_allowed"
        assert model["metadata"]["error_class"] == "policy_model_not_allowed"
        assert not adapter.calls

    def test_private_runtime_transient_failure_does_not_escape_publicly(self, monkeypatch):
        monkeypatch.setenv("NVIDIA_NIM_CHAT_BASE_URL", "http://nim:8001/v1")
        monkeypatch.setenv("NVIDIA_NIM_CHAT_MODEL", "allowed-model")
        primary = FakeAdapter({"invoke_chat": router.RouterError("provider_unavailable", "down", transient=True)})
        public = FakeAdapter()
        runtime = FakeRuntime(
            config={
                "providers": {"groq": {"enabled": True, "allowed_models": {"chat": ["groq-chat"]}}},
                "fallbacks": {"chat": {"nvidia_nim": [{"provider": "groq", "model": "groq-chat"}]}},
            },
            adapters={"nvidia_nim": primary, "groq": public},
        )
        result = router.invoke_chat({"_runtime": runtime, "provider": "nvidia_nim", "prompt": "hello"})
        assert result["status"] is False
        assert not public.calls

    def test_local_media_path_traversal_and_size(self, tmp_path):
        root = tmp_path / "work"
        root.mkdir()
        outside = tmp_path / "outside.wav"
        outside.write_bytes(b"audio")
        media = router.MediaSecurity({"media": {"allowed_roots": [str(root)], "max_input_bytes": 2}})
        with pytest.raises(router.RouterError) as traversal:
            media.local_input(outside, "audio/")
        assert traversal.value.error_class == "input_file_invalid"
        inside = root / "inside.wav"
        inside.write_bytes(b"large")
        with pytest.raises(router.RouterError):
            media.local_input(inside, "audio/")

    def test_remote_media_deny_by_default(self):
        media = router.MediaSecurity({"policy": {"allow_remote_media": False}, "media": {}})
        with pytest.raises(router.RouterError) as denied:
            media.remote_url("https://example.com/image.png")
        assert denied.value.error_class == "policy_endpoint_not_allowed"


class TestModalitiesAndAsync:
    def multimodal_runtime(self):
        adapter = FakeAdapter()
        config = {
            "providers": {
                "stability": {"enabled": True, "allowed_models": {"image": ["image-model"]}},
                "byteplus_modelark": {"enabled": True, "allowed_models": {"video": ["video-model"]}},
                "google_speech": {"enabled": True, "allowed_models": {"transcription": ["latest_long"]}},
                "elevenlabs": {"enabled": True, "allowed_models": {"tts": ["tts-model"], "voice": ["voice-model"]}},
                "vertex_ai": {"enabled": True, "allowed_models": {"chat": ["gemini-2.5-flash"], "embedding": ["text-embedding-004"], "music": ["music-model"]}},
            },
            "defaults": {
                "image": {"provider": "stability", "model": "image-model"},
                "video": {"provider": "byteplus_modelark", "model": "video-model"},
                "transcription": {"provider": "google_speech", "model": "latest_long"},
                "tts": {"provider": "elevenlabs", "model": "tts-model"},
                "voice": {"provider": "elevenlabs", "model": "voice-model"},
                "music": {"provider": "vertex_ai", "model": "music-model"},
            },
        }
        adapters = {name: adapter for name in ("stability", "byteplus_modelark", "google_speech", "elevenlabs", "vertex_ai")}
        return FakeRuntime(config=config, adapters=adapters), adapter

    def test_expensive_media_routes_disabled_by_default(self):
        result = router.invoke_image({"_runtime": FakeRuntime(), "prompt": "cat"})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "unsupported_capability"

    def test_image_search_transcription_tts_voice_music_aliases(self):
        runtime, adapter = self.multimodal_runtime()
        assert router.invoke_image({"_runtime": runtime, "prompt": "cat"})["status"] is True
        assert router.generate_image({"_runtime": runtime, "prompt": "cat"})["status"] is True
        assert router.invoke_search({"_runtime": runtime, "prompt": "news"})["data"]["citations"]
        assert router.invoke_transcribe({"_runtime": runtime, "audio_path": "unused-by-fake"})["data"]["text"] == "hello"
        assert router.get_text_to_speech({"_runtime": runtime, "text": "hello"})["status"] is True
        assert router.get_voices({"_runtime": runtime})["status"] is True
        assert router.invoke_music({"_runtime": runtime, "prompt": "song"})["status"] is True

    def test_video_task_records_scope_and_authorizes_admin(self):
        runtime, _ = self.multimodal_runtime()
        created = router.invoke_video({"_runtime": runtime, "operation": "create_task", "prompt": "video"})
        fetched = router.invoke_video({"_runtime": runtime, "operation": "get_task", "task_id": "task-1"})
        assert created["status"] is True
        assert fetched["status"] is True
        assert any(action == "record" for action, _ in runtime.task_events)
        assert any(action == "authorize" for action, _ in runtime.task_events)

    def test_video_admin_without_task_service_fails_closed(self):
        runtime, _ = self.multimodal_runtime()
        runtime.task = None
        result = router.invoke_video({"_runtime": runtime, "operation": "get_task", "task_id": "task-1"})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "policy_provider_not_allowed"


class TestProviderAdapters:
    def test_google_search_translates_prompt_deadline_and_preserves_grounding(self):
        class DelegateRuntime:
            def delegate(self, connector, request_data=None, command=None):
                assert connector == "google-genai" and command == "invoke_search"
                self.payload = request_data
                return {"status": True, "data": {"answer": '{"news": []}',
                    "search_results": [{"url": "https://news.example/story", "title": "Reporting"}],
                    "search_queries": ["fixture reporting"]}}
        runtime = DelegateRuntime()
        adapter = router.GoogleGenAIAdapter(router.RuntimeFacade(runtime), router.MediaSecurity({}))
        result = adapter.invoke_search(self.route("vertex_ai", "google_genai", capability="search_answer"),
                                       self.request("invoke_search", "search_answer", "execute", prompt="fixture reporting"))
        assert runtime.payload["params"]["search_query"] == "fixture reporting"
        assert runtime.payload["params"]["timeout"] == 1.0
        assert result.data["content"] == '{"news": []}'
        assert result.data["citations"] == [{"url": "https://news.example/story", "title": "Reporting"}]

    def test_google_search_does_not_fall_back_to_ungrounded_chat(self):
        adapter = router.GoogleGenAIAdapter(router.RuntimeFacade(), router.MediaSecurity({}))
        adapter.invoke_chat = MagicMock(return_value=router.AdapterResult(router._chat_data("invented")))
        with pytest.raises(router.RouterError, match="grounded search"):
            adapter.invoke_search(self.route("vertex_ai", "google_genai", capability="search_answer"),
                                  self.request("invoke_search", "search_answer", "execute", prompt="fixture reporting"))
        adapter.invoke_chat.assert_not_called()

    def route(self, provider="openai_compatible", adapter="openai_compatible", capability="chat", model="model"):
        return router.Route(
            provider=provider,
            adapter=adapter,
            capability=capability,
            operation_mode="factory",
            model=model,
            reason="test",
            config={},
            credentials={"api_key": "secret", "project": None, "organization": None, "deployment": None, "api_version": None, "location": "global"},
            endpoint=None,
            timeout_ms=1000,
            retries=0,
        )

    def request(self, command="invoke_prompt", capability="chat", mode="factory", **kwargs):
        return router.NormalizedRequest(command, capability, mode, "balanced", None, None, kwargs, kwargs, {}, {}, {}, raw=kwargs)

    def test_openai_compatible_factories_are_lazy_and_parameterized(self):
        fake_chat = MagicMock(return_value="chat-model")
        fake_embeddings = MagicMock(return_value="embedding-model")
        module = SimpleNamespace(ChatOpenAI=fake_chat, OpenAIEmbeddings=fake_embeddings)
        adapter = router.OpenAICompatibleAdapter(router.RuntimeFacade(), router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        with patch.dict(sys.modules, {"langchain_openai": module}):
            chat = adapter.create_chat_model(self.route(), self.request()).data
            embedding = adapter.create_embedding_model(self.route(capability="embedding", model="embed-model"), self.request("invoke_embedding", "embedding")).data
        assert chat == "chat-model"
        assert embedding == "embedding-model"
        assert fake_chat.call_args.kwargs["api_key"] == "secret"

    def test_azure_uses_correct_classes(self):
        fake_chat = MagicMock(return_value="azure-chat")
        fake_embeddings = MagicMock(return_value="azure-embed")
        module = SimpleNamespace(AzureChatOpenAI=fake_chat, AzureOpenAIEmbeddings=fake_embeddings)
        route = self.route("azure_foundry", "azure_foundry")
        route.endpoint = "https://azure.example"
        route.credentials.update({"deployment": "deployment", "api_version": "2024-08-01-preview"})
        adapter = router.AzureFoundryAdapter(router.RuntimeFacade(), router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        with patch.dict(sys.modules, {"langchain_openai": module}):
            assert adapter.create_chat_model(route, self.request()).data == "azure-chat"
            assert adapter.create_embedding_model(route, self.request("invoke_embedding", "embedding")).data == "azure-embed"
        assert fake_chat.call_args.kwargs["azure_deployment"] == "deployment"

    def test_vertex_service_account_credentials_are_scoped(self):
        fake_from_info = MagicMock(return_value="scoped-creds")
        sa_module = SimpleNamespace(Credentials=SimpleNamespace(from_service_account_info=fake_from_info))
        fake_embeddings = MagicMock(return_value="vertex-embed")
        vertex_module = SimpleNamespace(VertexAIEmbeddings=fake_embeddings, ChatVertexAI=MagicMock(return_value="vertex-chat"))
        adapter = router.GoogleGenAIAdapter(router.RuntimeFacade(), router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        route = self.route("vertex_ai", "vertex_ai", capability="embedding", model="text-embedding-004")
        route.credentials["credential"] = json.dumps({"type": "service_account", "project_id": "demo"})
        with patch.dict(sys.modules, {"langchain_google_vertexai": vertex_module, "google.oauth2.service_account": sa_module}):
            result = adapter.create_embedding_model(route, self.request("invoke_embedding", "embedding"))
        assert result.data == "vertex-embed"
        assert fake_from_info.call_args.kwargs["scopes"] == ["https://www.googleapis.com/auth/cloud-platform"]
        assert fake_embeddings.call_args.kwargs["credentials"] == "scoped-creds"

    @pytest.mark.parametrize("priority_paygo,expected", [(True, True), (False, False), (None, False)])
    def test_vertex_prompt_delegation_translates_priority_paygo(self, priority_paygo, expected):
        class DelegateRuntime:
            def __init__(self):
                self.payload = None

            def delegate(self, connector, request_data=None, command=None):
                self.payload = request_data
                return {"status": True, "data": "vertex-chat", "metadata": {}}

        runtime = DelegateRuntime()
        adapter = router.GoogleGenAIAdapter(router.RuntimeFacade(runtime), router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        options = {} if priority_paygo is None else {"priority_paygo": priority_paygo}
        result = adapter.create_chat_model(
            self.route("vertex_ai", "google_genai", model="gemini-3.5-flash-lite"),
            self.request(**options),
        )

        assert result.data == "vertex-chat"
        assert runtime.payload["priority_mode"] is expected
        assert runtime.payload["params"]["priority_mode"] is expected
        assert "priority_paygo" not in runtime.payload
        assert "priority_paygo" not in runtime.payload["params"]

    def test_in_process_vertex_omits_priority_header_when_false_or_default(self):
        fake_chat = MagicMock(return_value="vertex-chat")
        vertex_module = SimpleNamespace(ChatVertexAI=fake_chat, VertexAIEmbeddings=MagicMock())
        adapter = router.GoogleGenAIAdapter(router.RuntimeFacade(), router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        route = self.route("vertex_ai", "google_genai", model="gemini-3.5-flash-lite")
        with patch.dict(sys.modules, {"langchain_google_vertexai": vertex_module}):
            adapter.create_chat_model(route, self.request(priority_paygo=False))
            adapter.create_chat_model(route, self.request())
        for call in fake_chat.call_args_list:
            assert "additional_headers" not in call.kwargs

    @staticmethod
    def nullable_schema():
        return {
            "type": "object",
            "required": ["interval_quantity", "details"],
            "properties": {
                "interval_quantity": {
                    "type": ["integer", "null"],
                    "description": "Number of intervals when known.",
                    "enum": [1, 2, None],
                },
                "details": {
                    "type": "object",
                    "properties": {
                        "label": {"type": ["string", "null"]},
                        "scores": {
                            "type": "array",
                            "items": {"type": ["number", "null"]},
                        },
                    },
                },
            },
        }

    @pytest.mark.parametrize("delegated", [False, True])
    def test_vertex_factory_normalizes_nullable_dictionary_schemas(self, delegated):
        class VertexModel:
            def __init__(self):
                self.schema = None
                self.kwargs = None

            def with_structured_output(self, schema, **kwargs):
                self.schema = schema
                self.kwargs = kwargs
                return "structured-model"

        model = VertexModel()
        runtime = router.RuntimeFacade()
        modules = {}
        if delegated:
            class DelegateRuntime:
                def delegate(self, connector, request_data=None, command=None):
                    return {"status": True, "data": model, "metadata": {}}

            runtime = router.RuntimeFacade(DelegateRuntime())
        else:
            modules = {
                "langchain_google_vertexai": SimpleNamespace(
                    ChatVertexAI=MagicMock(return_value=model),
                    VertexAIEmbeddings=MagicMock(),
                )
            }

        adapter = router.GoogleGenAIAdapter(runtime, router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        route = self.route("vertex_ai", "google_genai", model="gemini-3.5-flash-lite")
        schema = self.nullable_schema()
        original = json.loads(json.dumps(schema))
        with patch.dict(sys.modules, modules):
            factory = adapter.create_chat_model(route, self.request()).data
        result = factory.with_structured_output(schema, method="json_schema")

        assert result == "structured-model"
        assert schema == original
        assert model.kwargs == {"method": "json_schema"}
        assert model.schema["properties"]["interval_quantity"] == {
            "type": "integer",
            "nullable": True,
            "description": "Number of intervals when known.",
            "enum": [1, 2, None],
        }
        assert model.schema["properties"]["details"]["properties"]["label"] == {
            "type": "string",
            "nullable": True,
        }
        assert model.schema["properties"]["details"]["properties"]["scores"]["items"] == {
            "type": "number",
            "nullable": True,
        }
        assert model.schema["required"] == ["interval_quantity", "details"]

    def test_vertex_nullable_schema_preserves_literal_annotation_values(self):
        literal = {"type": ["integer", "null"], "nested": {"type": ["string", "number"]}}
        schema = {
            "type": "object",
            "properties": {
                "details": {
                    "type": ["object", "null"],
                    "enum": [literal, None],
                    "const": literal,
                    "default": literal,
                    "examples": [literal],
                }
            },
            "required": ["details"],
        }
        original = json.loads(json.dumps(schema))
        converted = router._vertex_response_schema(schema)
        assert schema == original
        details = converted["properties"]["details"]
        assert details["type"] == "object"
        assert details["nullable"] is True
        for name in ("enum", "const", "default", "examples"):
            assert details[name] == original["properties"]["details"][name]

    def test_vertex_factory_forwards_non_dictionary_schemas_invoke_and_stream(self):
        class ResponseModel:
            pass

        class VertexModel:
            def __init__(self):
                self.structured_schema = None

            def with_structured_output(self, schema, **kwargs):
                self.structured_schema = schema
                return "structured-model"

            def invoke(self, *args, **kwargs):
                return (args, kwargs)

            def stream(self, *args, **kwargs):
                return iter([(args, kwargs)])

        model = VertexModel()
        vertex_module = SimpleNamespace(ChatVertexAI=MagicMock(return_value=model), VertexAIEmbeddings=MagicMock())
        adapter = router.GoogleGenAIAdapter(router.RuntimeFacade(), router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        route = self.route("vertex_ai", "google_genai", model="gemini-3.5-flash-lite")
        with patch.dict(sys.modules, {"langchain_google_vertexai": vertex_module}):
            factory = adapter.create_chat_model(route, self.request()).data

        assert factory.with_structured_output(ResponseModel) == "structured-model"
        assert model.structured_schema is ResponseModel
        assert factory.invoke("hello", config={"tag": "test"}) == (("hello",), {"config": {"tag": "test"}})
        assert list(factory.stream("hello", stop=["done"])) == [(("hello",), {"stop": ["done"]})]
        # LCEL accepts Runnable instances, callables, or mappings in a pipe.
        assert callable(factory)
        assert factory("hello", config={"tags": ["test"]}, stop=["done"]) == (
            ("hello",), {"config": {"tags": ["test"]}, "stop": ["done"]}
        )

    def test_google_ai_studio_factory_does_not_normalize_nullable_schemas(self):
        model = MagicMock()
        google_module = SimpleNamespace(ChatGoogleGenerativeAI=MagicMock(return_value=model))
        adapter = router.GoogleGenAIAdapter(router.RuntimeFacade(), router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        route = self.route("google_ai_studio", "google_genai", model="gemini-3.5-flash-lite")
        with patch.dict(sys.modules, {"langchain_google_genai": google_module}):
            factory = adapter.create_chat_model(route, self.request()).data

        schema = self.nullable_schema()
        factory.with_structured_output(schema)
        assert factory is model
        assert model.with_structured_output.call_args.args[0] is schema

    @pytest.mark.parametrize(
        "schema_type",
        [
            ["string", "integer"],
            ["string", "integer", "null"],
            ["unsupported", "null"],
        ],
    )
    def test_vertex_factory_rejects_unsupported_type_unions(self, schema_type):
        model = MagicMock()
        vertex_module = SimpleNamespace(ChatVertexAI=MagicMock(return_value=model), VertexAIEmbeddings=MagicMock())
        adapter = router.GoogleGenAIAdapter(router.RuntimeFacade(), router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        route = self.route("vertex_ai", "google_genai", model="gemini-3.5-flash-lite")
        with patch.dict(sys.modules, {"langchain_google_vertexai": vertex_module}):
            factory = adapter.create_chat_model(route, self.request()).data

        with pytest.raises(ValueError, match="Vertex structured output"):
            factory.with_structured_output({"type": "object", "properties": {"value": {"type": schema_type}}})
        model.with_structured_output.assert_not_called()

    def test_priority_paygo_requires_vertex_global_region_before_invocation(self):
        adapter = FakeAdapter()
        runtime = FakeRuntime(
            config={"providers": {"vertex_ai": {"location": "us-central1"}}},
            adapters={"vertex_ai": adapter},
        )
        result = router.invoke_prompt({"_runtime": runtime, "priority_paygo": True})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "unsupported_option"
        assert adapter.calls == []

    def test_priority_paygo_true_is_not_applied_to_other_providers(self):
        adapter = FakeAdapter()
        runtime = FakeRuntime(
            config={
                "providers": {"groq": {"enabled": True, "credential": "secret", "allowed_models": {"chat": ["groq-chat"]}}},
                "profiles": {"fast": {"chat": [{"provider": "groq", "model": "groq-chat"}]}},
            },
            adapters={"groq": adapter},
        )
        result = router.invoke_prompt({"_runtime": runtime, "profile": "fast", "priority_paygo": True})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "unsupported_option"
        assert adapter.calls == []

    def test_groq_chat_and_embedding_rejection(self):
        fake_chat = MagicMock(return_value="groq-chat")
        adapter = router.GroqAdapter(router.RuntimeFacade(), router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        with patch.dict(sys.modules, {"langchain_groq": SimpleNamespace(ChatGroq=fake_chat)}):
            result = adapter.create_chat_model(self.route("groq", "groq"), self.request())
        assert result.data == "groq-chat"
        policy = router.PolicyEngine(router._deep_merge(router.DEFAULT_CONFIG, {"providers": {"groq": {"enabled": True, "allowed_models": {"embedding": ["fake"]}}}}), router.RuntimeFacade())
        request = self.request("invoke_embedding", "embedding")
        request.provider = "groq"
        request.model = "fake"
        with pytest.raises(router.RouterError) as unsupported:
            policy.route(request)
        assert unsupported.value.error_class == "unsupported_capability"

    def test_vertex_anthropic_omits_default_temperature(self):
        # Sonnet 5 / Opus 4.8-class models reject sampling params (400
        # "temperature is deprecated"); the adapter must not inject a default.
        fake_chat = MagicMock(return_value="claude-chat")
        mg_module = SimpleNamespace(ChatAnthropicVertex=fake_chat)
        adapter = router.VertexAnthropicAdapter(router.RuntimeFacade(), router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        route = self.route("vertex_anthropic", "vertex_anthropic", model="claude-sonnet-5")
        with patch.dict(sys.modules, {"langchain_google_vertexai.model_garden": mg_module}):
            result = adapter.create_chat_model(route, self.request())
        assert result.data == "claude-chat"
        assert "temperature" not in fake_chat.call_args.kwargs
        assert fake_chat.call_args.kwargs["max_tokens"] == adapter.default_max_tokens
        with patch.dict(sys.modules, {"langchain_google_vertexai.model_garden": mg_module}):
            adapter.create_chat_model(route, self.request(temperature=0.7))
        assert fake_chat.call_args.kwargs["temperature"] == 0.7
        # The platform prompt runner injects temperature: 0 into every prompt
        # task; 0 must be treated as unset on this route (Claude rejects it).
        with patch.dict(sys.modules, {"langchain_google_vertexai.model_garden": mg_module}):
            adapter.create_chat_model(route, self.request(temperature=0))
        assert "temperature" not in fake_chat.call_args.kwargs

    def test_vertex_and_google_media_can_delegate_without_provider_imports(self):
        class DelegateRuntime:
            def delegate(self, connector, command, payload):
                return {"status": True, "data": {"delegated": command}, "metadata": {"provider_request_id": "delegated-1"}}

        adapter = router.GoogleGenAIAdapter(router.RuntimeFacade(DelegateRuntime()), router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        route = self.route("vertex_ai", "google_genai")
        assert adapter.create_chat_model(route, self.request()).data == {"delegated": "invoke_prompt"}
        assert adapter.invoke_image(route, self.request("invoke_image", "image", "execute")).data == {"delegated": "invoke_image"}

    def test_sanitized_provider_exception_does_not_leak_secret(self):
        class Broken:
            def __init__(self, **kwargs):
                raise RuntimeError("secret-token provider exploded")

        adapter = router.OpenAICompatibleAdapter(router.RuntimeFacade(), router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        with patch.dict(sys.modules, {"langchain_openai": SimpleNamespace(ChatOpenAI=Broken)}):
            with pytest.raises(router.RouterError) as failure:
                adapter.create_chat_model(self.route(), self.request())
        assert "secret-token" not in failure.value.safe_message


class RuntimeServicesDelegate:
    """Mimics the server RouterRuntimeServices.delegate signature."""

    def __init__(self, response=None):
        self.calls = []
        self.response = response or {"status": True, "data": {"delegated": True}, "metadata": {"provider_request_id": "svc-1"}}

    def delegate(self, target_name, request_data=None, command=None):
        self.calls.append({"target": target_name, "request": request_data, "command": command})
        return self.response


class TestRuntimeContractAdoption:
    def media(self):
        return router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}})

    def route(self, provider="groq", adapter="groq", capability="chat", model="openai/gpt-oss-120b"):
        return router.Route(
            provider=provider,
            adapter=adapter,
            capability=capability,
            operation_mode="factory",
            model=model,
            reason="test",
            config={},
            credentials={
                "api_key": "groq-secret",
                "credential": "groq-secret",
                "project": "proj-1",
                "organization": "org-1",
                "deployment": None,
                "api_version": None,
                "location": None,
            },
            endpoint=None,
            timeout_ms=1000,
            retries=0,
        )

    def request(self, command="invoke_prompt", capability="chat", mode="factory", **kwargs):
        return router.NormalizedRequest(command, capability, mode, "balanced", None, None, dict(kwargs), dict(kwargs), {}, {}, {}, raw=dict(kwargs))

    def test_machina_router_runtime_global_is_adopted(self, monkeypatch):
        runtime = FakeRuntime()
        monkeypatch.setattr(router, "machina_router_runtime", runtime, raising=False)
        result = router.invoke_prompt({})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "vertex_ai"

    def test_delegate_uses_runtime_signature_with_flat_and_header_credentials(self):
        services = RuntimeServicesDelegate()
        adapter = router.GroqAdapter(router.RuntimeFacade(services), self.media())
        result = adapter.create_chat_model(self.route(), self.request(priority_paygo=False))
        assert result.data == {"delegated": True}
        call = services.calls[0]
        assert call["target"] == "groq"
        assert call["command"] == "invoke_prompt"
        payload = call["request"]
        assert payload["api_key"] == "groq-secret"
        assert payload["params"]["api_key"] == "groq-secret"
        assert payload["headers"]["api_key"] == "groq-secret"
        assert payload["params"]["project_id"] == "proj-1"
        assert payload["organization"] == "org-1"
        assert "priority_paygo" not in payload
        assert "priority_paygo" not in payload["params"]

    def test_module_global_machina_delegate_is_preferred(self, monkeypatch):
        calls = []

        def machina_delegate(target_name, request_data=None, command=None):
            calls.append((target_name, command))
            return {"status": True, "data": {"delegated": command}, "metadata": {}}

        monkeypatch.setattr(router, "machina_delegate", machina_delegate, raising=False)
        adapter = router.GoogleGenAIAdapter(router.RuntimeFacade(), self.media())
        result = adapter.create_chat_model(self.route("vertex_ai", "google_genai", model="gemini-2.5-flash"), self.request())
        assert result.data == {"delegated": "invoke_prompt"}
        assert calls == [("google-genai", "invoke_prompt")]

    def test_frozen_runtime_services_config_tasks_and_circuit_shapes(self):
        from types import MappingProxyType

        class TaskStore:
            def __init__(self):
                self.created = []

            def get(self, task_id):
                return {"task_id": task_id} if task_id == "task-1" else None

            def create(self, task_id, *, route, provider, state="queued", result=None, metadata=None):
                self.created.append((task_id, route, provider))
                return {"task_id": task_id}

        class CircuitStore:
            def __init__(self):
                self.events = []

            def before_request(self, route):
                self.events.append(("before", route))
                return {"state": "closed"}

            def record_success(self, route):
                self.events.append(("success", route))

            def record_failure(self, route):
                self.events.append(("failure", route))

        class Services:
            def __init__(self):
                self.tasks = TaskStore()
                self.circuit = CircuitStore()
                self.scope = MappingProxyType({"organization_id": "org-1", "project_id": "project-1", "creator_id": "creator-1"})
                self.trusted_headers = MappingProxyType({"X-Machina-Project-Id": "project-1"})

            @property
            def config(self):
                return MappingProxyType({
                    "providers": MappingProxyType({
                        "byteplus_modelark": MappingProxyType({
                            "enabled": True,
                            "credential": "bp-secret",
                            "allowed_models": MappingProxyType({"video": ("video-model",)}),
                        })
                    }),
                    "defaults": MappingProxyType({"video": MappingProxyType({"provider": "byteplus_modelark", "model": "video-model"})}),
                })

            def delegate(self, target_name, request_data=None, command=None):
                return {"status": True, "data": {"id": "task-1", "status": "pending"}, "metadata": {}}

        services = Services()
        created = router.invoke_video({"_runtime": services, "operation": "create_task", "prompt": "clip"})
        assert created["status"] is True
        assert created["data"]["task_id"] == "task-1"
        assert services.tasks.created and services.tasks.created[0][0] == "task-1"
        fetched = router.invoke_video({"_runtime": services, "operation": "get_task", "task_id": "task-1"})
        assert fetched["status"] is True
        denied = router.invoke_video({"_runtime": services, "operation": "get_task", "task_id": "other"})
        assert denied["status"] is False
        assert denied["metadata"]["error_class"] == "policy_provider_not_allowed"
        assert ("before", "byteplus_modelark:video-model:video") in services.circuit.events
        assert any(event[0] == "success" for event in services.circuit.events)


class TestLazyFallbacksAndReceipts:
    def test_primary_succeeds_despite_unbuildable_fallback_provider(self):
        runtime = FakeRuntime(config={"fallbacks": {"chat": {"vertex_ai": [{"provider": "perplexity", "model": "sonar"}]}}})
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert result["metadata"]["fallback_used"] is False

    def test_pinned_model_with_cross_provider_fallback_uses_candidate_model(self):
        primary = FakeAdapter({"invoke_chat": router.RouterError("provider_timeout", "t", transient=True)})
        fallback = FakeAdapter()
        runtime = FakeRuntime(
            config={
                "providers": {"groq": {"enabled": True, "credential": "groq-secret"}},
                "fallbacks": {"chat": {"vertex_ai": [{"provider": "groq", "model": "openai/gpt-oss-20b"}]}},
            },
            adapters={"vertex_ai": primary, "groq": fallback},
        )
        result = router.invoke_chat({"_runtime": runtime, "model": "gemini-2.5-flash", "prompt": "hello"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"
        assert result["metadata"]["selected_model"] == "openai/gpt-oss-20b"
        assert result["metadata"]["fallback_used"] is True

    def test_unbuildable_fallback_recorded_as_skipped(self):
        primary = FakeAdapter({"invoke_chat": router.RouterError("provider_timeout", "t", transient=True)})
        runtime = FakeRuntime(
            config={"fallbacks": {"chat": {"vertex_ai": [{"provider": "perplexity", "model": "sonar"}]}}},
            adapters={"vertex_ai": primary},
        )
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello"})
        assert result["status"] is False
        skipped = [attempt for attempt in result["metadata"]["fallback_attempts"] if attempt.get("skipped")]
        assert skipped and skipped[0]["provider"] == "perplexity"
        assert skipped[0]["error_class"] == "policy_provider_not_allowed"

    def test_total_failure_reports_primary_route_identity(self):
        primary = FakeAdapter({"invoke_chat": router.RouterError("provider_timeout", "t", transient=True)})
        fallback = FakeAdapter({"invoke_chat": router.RouterError("provider_unavailable", "down", transient=True)})
        runtime = FakeRuntime(
            config={
                "providers": {"groq": {"enabled": True, "credential": "groq-secret"}},
                "fallbacks": {"chat": {"vertex_ai": [{"provider": "groq", "model": "openai/gpt-oss-120b"}]}},
            },
            adapters={"vertex_ai": primary, "groq": fallback},
        )
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello"})
        assert result["status"] is False
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert result["metadata"]["selected_model"] == "gemini-3.5-flash-lite"
        assert result["metadata"]["route_reason"] == "profile:balanced"
        assert [attempt["provider"] for attempt in result["metadata"]["fallback_attempts"]] == ["vertex_ai", "groq"]


class TestRemapPrecedence:
    def test_profile_remap_without_capability_entry_falls_through(self):
        runtime = FakeRuntime(config={"remaps": {"profiles": {"fast": {"chat": {"provider": "groq", "model": "openai/gpt-oss-120b"}}}}})
        result = router.invoke_embedding({"_runtime": runtime, "profile": "fast"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert result["metadata"]["route_reason"] == "default:embedding"

    def test_capability_remap_wins_over_profile_remap(self):
        groq = FakeAdapter()
        runtime = FakeRuntime(
            config={
                "providers": {"groq": {"enabled": True, "credential": "groq-secret", "allowed_models": {"chat": ["groq-chat"]}}},
                "remaps": {
                    "capabilities": {"chat": {"provider": "groq", "model": "groq-chat"}},
                    "profiles": {"balanced": {"chat": {"provider": "perplexity", "model": "sonar"}}},
                },
            },
            adapters={"vertex_ai": FakeAdapter(), "groq": groq},
        )
        result = router.invoke_prompt({"_runtime": runtime})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"
        assert result["metadata"]["route_reason"] == "remap:capability:chat"

    def test_family_remap_redirects_abstract_model(self):
        groq = FakeAdapter()
        runtime = FakeRuntime(
            config={
                "providers": {"groq": {"enabled": True, "credential": "groq-secret", "allowed_models": {"chat": ["groq-chat"]}}},
                "remaps": {"families": {"gemini-default": {"provider": "groq", "model": "groq-chat"}}},
            },
            adapters={"vertex_ai": FakeAdapter(), "groq": groq},
        )
        result = router.invoke_chat({"_runtime": runtime, "model": "gemini-default", "prompt": "hi"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"
        assert result["metadata"]["selected_model"] == "groq-chat"
        assert result["metadata"]["route_reason"] == "remap:family:gemini-default"


class TestTimeoutAndConflicts:
    def test_timeout_ms_is_always_milliseconds(self):
        request = router.Router(FakeRuntime()).normalizer.normalize("invoke_chat", {"timeout_ms": 500, "prompt": "x"})
        assert request.options["timeout_ms"] == 500

    def test_legacy_timeout_alias_keeps_seconds_heuristic(self):
        request = router.Router(FakeRuntime()).normalizer.normalize("invoke_chat", {"timeout": 20, "prompt": "x"})
        assert request.options["timeout_ms"] == 20000

    def test_cross_source_conflict_is_recorded(self):
        request = router.Router(FakeRuntime()).normalizer.normalize(
            "invoke_chat", {"model": "gemini-2.5-flash", "params": {"model": "nested-model"}, "prompt": "x"}
        )
        assert request.model == "gemini-2.5-flash"
        assert any(conflict.startswith("model:top_level!=params.") for conflict in request.conflicts)


class TestBytePlusListPayloads:
    def test_list_tasks_preserves_list_payload(self):
        class Services:
            def delegate(self, target_name, request_data=None, command=None):
                return {"status": True, "data": [{"id": "t1"}, {"id": "t2"}], "metadata": {}}

        adapter = router.BytePlusAdapter(router.RuntimeFacade(Services()), router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        route = router.Route(
            provider="byteplus_modelark",
            adapter="byteplus_modelark",
            capability="video",
            operation_mode="execute",
            model="video-model",
            reason="test",
            config={},
            credentials={"api_key": "secret"},
            endpoint=None,
            timeout_ms=1000,
            retries=0,
        )
        request = router.NormalizedRequest("invoke_video", "video", "execute", "balanced", None, None, {"operation": "list_tasks"}, {}, {}, {}, {}, raw={})
        result = adapter.invoke_video(route, request)
        assert result.data == [{"id": "t1"}, {"id": "t2"}]


class TestDefaultEnablement:
    def test_cheap_profile_routes_to_low_cost_vertex_model(self):
        result = router.invoke_prompt({"_runtime": FakeRuntime(), "profile": "cheap"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert result["metadata"]["selected_model"] == "gemini-3.5-flash-lite"
        assert result["metadata"]["route_reason"] == "profile:cheap"

    def test_groq_enabled_with_env_credential_only(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", "env-secret")
        groq = FakeAdapter()
        runtime = FakeRuntime(adapters={"vertex_ai": FakeAdapter(), "groq": groq})
        result = router.invoke_chat({"_runtime": runtime, "provider": "groq", "model": "openai/gpt-oss-120b", "prompt": "hi"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"

    def test_groq_without_env_credential_is_typed_credential_missing(self, monkeypatch):
        monkeypatch.delenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", raising=False)
        monkeypatch.delenv("TEMP_CONTEXT_VARIABLE_SDK_GROQ_API_KEY", raising=False)
        result = router.invoke_chat({"_runtime": FakeRuntime(), "provider": "groq", "model": "openai/gpt-oss-120b", "prompt": "hi"})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "credential_missing"

    def test_fast_profile_preserves_groq_when_cerebras_is_dormant(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", "env-secret")
        groq = FakeAdapter()
        runtime = FakeRuntime(adapters={"vertex_ai": FakeAdapter(), "groq": groq})
        result = router.invoke_prompt({"_runtime": runtime, "profile": "fast"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"
        assert result["metadata"]["selected_model"] == "openai/gpt-oss-120b"

    def test_google_speech_transcription_enabled_by_default(self):
        speech = FakeAdapter()
        runtime = FakeRuntime(adapters={"google_speech": speech})
        result = router.transcribe_audio_to_text({"_runtime": runtime, "audio_path": "handled-by-fake"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "google_speech"
        assert result["data"]["text"] == "hello"


class TestVertexAnthropicRoute:
    """Claude on Vertex AI Model Garden — Stage 0 route."""

    def _runtime(self, **config_extra):
        config = router._deep_merge(
            {"providers": {"vertex_anthropic": {"enabled": True}}}, config_extra
        )
        return FakeRuntime(
            config=config,
            adapters={"vertex_ai": FakeAdapter(), "vertex_anthropic": FakeAdapter()},
        )

    def test_route_ships_dormant_and_registered(self):
        conf = router.DEFAULT_CONFIG["providers"]["vertex_anthropic"]
        assert conf["enabled"] is False  # dormant; enabled per-environment
        assert conf["adapter"] == "vertex_anthropic"
        assert conf["credential_env"] == "TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL"
        assert conf["project_env"] == "TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID"
        for model in ("claude-haiku-4-5", "claude-sonnet-5", "claude-opus-4-8"):
            assert model in conf["allowed_models"]["chat"]
        assert "vertex_anthropic" in router.Router(FakeRuntime()).registry.factories
        assert router.VertexAnthropicAdapter.capabilities == {"chat"}

    def test_provider_aliases_canonicalize_to_vertex_anthropic(self):
        for alias in ("vertex_model_garden", "model_garden", "anthropic_vertex", "anthropic", "claude"):
            assert router.PROVIDER_ALIASES[alias] == "vertex_anthropic"

    def test_explicit_claude_route_selected(self):
        result = router.invoke_prompt(
            {"_runtime": self._runtime(), "provider": "vertex_anthropic", "model": "claude-haiku-4-5", "prompt": "hi"}
        )
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "vertex_anthropic"
        assert result["metadata"]["selected_model"] == "claude-haiku-4-5"
        assert result["metadata"]["route_reason"] == "explicit_provider"

    def test_vertex_model_garden_alias_routes_to_claude(self):
        result = router.invoke_prompt(
            {"_runtime": self._runtime(), "provider": "vertex_model_garden", "model": "claude-sonnet-5", "prompt": "hi"}
        )
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "vertex_anthropic"
        assert result["metadata"]["selected_model"] == "claude-sonnet-5"

    def test_gemini_model_rejected_on_claude_route(self):
        result = router.invoke_prompt(
            {"_runtime": self._runtime(), "provider": "vertex_anthropic", "model": "gemini-2.5-flash", "prompt": "hi"}
        )
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "policy_model_not_allowed"

    def test_capability_remap_redirects_chat_to_claude(self):
        # One config flip redirects all chat off the Gemini repository default
        # onto Claude, without editing any workflow.
        runtime = self._runtime(
            remaps={"capabilities": {"chat": {"provider": "vertex_anthropic", "model": "claude-haiku-4-5"}}}
        )
        result = router.invoke_prompt({"_runtime": runtime, "prompt": "hi"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "vertex_anthropic"
        assert result["metadata"]["selected_model"] == "claude-haiku-4-5"
        assert result["metadata"]["route_reason"] == "remap:capability:chat"

    def test_haiku_5_5_explicit_opt_in_routes(self):
        result = router.invoke_prompt(
            {"_runtime": self._runtime(), "provider": "vertex_anthropic", "model": "claude-haiku-5-5", "prompt": "hi"}
        )
        assert result["metadata"].get("error_class") is None
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "vertex_anthropic"
        assert result["metadata"]["selected_model"] == "claude-haiku-5-5"
        assert result["metadata"]["route_reason"] == "explicit_provider"

    def test_haiku_5_5_rejected_while_provider_dormant(self):
        result = router.invoke_prompt(
            {"_runtime": FakeRuntime(), "provider": "vertex_anthropic", "model": "claude-haiku-5-5", "prompt": "hi"}
        )
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "policy_provider_not_allowed"

    def test_haiku_5_5_rejected_on_wrong_provider_or_capability(self):
        gemini_route = router.invoke_prompt(
            {"_runtime": self._runtime(), "provider": "vertex_ai", "model": "claude-haiku-5-5", "prompt": "hi"}
        )
        assert gemini_route["metadata"]["error_class"] == "policy_model_not_allowed"
        embedding = router.invoke_embedding(
            {"_runtime": self._runtime(), "provider": "vertex_anthropic", "model": "claude-haiku-5-5", "text": "hi"}
        )
        assert embedding["status"] is False
        assert embedding["metadata"]["error_class"] == "unsupported_capability"

    def test_list_models_exposes_haiku_5_5_only_when_enabled(self):
        entry = {"provider": "vertex_anthropic", "model": "claude-haiku-5-5", "capability": "chat", "enabled": True}
        assert entry in router.list_models({"_runtime": self._runtime()})["data"]
        assert entry not in router.list_models({"_runtime": FakeRuntime()})["data"]

    def test_haiku_5_5_is_opt_in_only(self):
        conf = router.DEFAULT_CONFIG["providers"]["vertex_anthropic"]
        assert conf["enabled"] is False
        assert conf["location"] == "global"
        assert conf["allowed_models"]["chat"] == [
            "claude-haiku-4-5",
            "claude-sonnet-4-6",
            "claude-sonnet-5",
            "claude-opus-4-8",
            "claude-haiku-5-5",
        ]
        for section in ("defaults", "profiles", "fallbacks", "remaps"):
            assert "claude-haiku-5-5" not in json.dumps(router.DEFAULT_CONFIG.get(section, {}))
        # Enabling Claude does not move default chat off the Gemini route.
        result = router.invoke_prompt({"_runtime": self._runtime(), "prompt": "hi"})
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert result["metadata"]["selected_model"] == "gemini-3.5-flash-lite"

    def test_haiku_5_5_reaches_chat_anthropic_vertex_factory(self, monkeypatch):
        monkeypatch.delenv("TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL", raising=False)
        monkeypatch.delenv("TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID", raising=False)
        sdk = MagicMock()
        sdk.return_value.invoke.return_value = "pong"
        # No vertex_anthropic fake: the router builds the real VertexAnthropicAdapter.
        runtime = FakeRuntime(config={"providers": {"vertex_anthropic": {"enabled": True}}})
        with patch.dict(sys.modules, {"langchain_google_vertexai.model_garden": SimpleNamespace(ChatAnthropicVertex=sdk)}):
            result = router.invoke_prompt(
                {"_runtime": runtime, "provider": "vertex_anthropic", "model": "claude-haiku-5-5", "prompt": "hi"}
            )
            assert result["status"] is True, result
            assert result["data"].invoke("ping") == "pong"
        assert sdk.call_args.kwargs["model_name"] == "claude-haiku-5-5"
        assert sdk.call_args.kwargs["location"] == "global"
        sdk.return_value.invoke.assert_called_once()
        assert sdk.return_value.invoke.call_args.args[0] == "ping"


class TestCerebrasFastRoute:
    def _runtime(self, cerebras, groq, **config):
        return FakeRuntime(
            config=config,
            adapters={"vertex_ai": FakeAdapter(), "cerebras": cerebras, "groq": groq},
        )

    def test_provider_ships_dormant_registered_and_allowlisted_from_official_catalog(self):
        conf = router.DEFAULT_CONFIG["providers"]["cerebras"]
        assert conf["enabled"] is False
        assert conf["adapter"] == "cerebras"
        assert conf["protected"] is True
        assert conf["endpoint"] == "https://api.cerebras.ai/v1"
        assert conf["credential_env"] == "TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY"
        assert conf["credential_env_aliases"] == ["TEMP_CONTEXT_VARIABLE_SDK_CEREBRAS_API_KEY"]
        assert conf["allowed_models"]["chat"] == ["gpt-oss-120b", "gemma-4-31b"]
        assert router.DEFAULT_CONFIG["profiles"]["fast"]["chat"] == [
            {"provider": "cerebras", "model": "gpt-oss-120b"},
            {"provider": "groq", "model": "openai/gpt-oss-120b"},
        ]
        assert router.DEFAULT_CONFIG["fallbacks"]["chat"]["cerebras"] == [
            {"provider": "groq", "model": "openai/gpt-oss-120b"}
        ]
        assert "cerebras" in router.Router(FakeRuntime()).registry.factories
        assert router.CerebrasAdapter.capabilities == {"chat"}

    def test_provider_alias_is_canonical(self):
        assert router._canonical_provider("cerebras-cloud") == "cerebras"

    def test_health_accepts_repository_credential_alias(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_SDK_CEREBRAS_API_KEY", "alias-secret")
        runtime = self._runtime(FakeAdapter(), FakeAdapter(), providers={"cerebras": {"enabled": True}})
        result = router.health({"_runtime": runtime, "provider": "cerebras"})
        assert result["status"] is True
        assert result["data"] == [{
            "provider": "cerebras",
            "enabled": True,
            "ready": True,
            "missing": [],
            "adapter": "cerebras",
            "capabilities": ["chat"],
            "models": {"chat": ["gpt-oss-120b", "gemma-4-31b"]},
        }]

    def test_explicit_provider_routes_to_cerebras(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY", "operator-secret")
        cerebras = FakeAdapter()
        result = router.invoke_prompt({
            "_runtime": self._runtime(cerebras, FakeAdapter(), providers={"cerebras": {"enabled": True}}),
            "provider": "cerebras",
            "model": "gpt-oss-120b",
        })
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "cerebras"
        assert result["metadata"]["route_reason"] == "explicit_provider"

    def test_runtime_config_cannot_replace_fixed_cerebras_endpoint(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY", "operator-secret")
        runtime = self._runtime(
            FakeAdapter(),
            FakeAdapter(),
            providers={"cerebras": {"enabled": True, "endpoint": "https://evil.example/v1"}},
        )
        request = router.Router(runtime).normalizer.normalize(
            "invoke_chat", {"provider": "cerebras", "model": "gpt-oss-120b", "prompt": "hello"}
        )
        route = router.Router(runtime).policy.route(request)
        assert route.endpoint == "https://api.cerebras.ai/v1"

    def test_runtime_overlay_cannot_disable_endpoint_or_credential_injection_guards(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY", "operator-secret")
        cerebras = FakeAdapter()
        runtime = self._runtime(
            cerebras,
            FakeAdapter(),
            policy={"allow_custom_base_url": True, "allow_workflow_credentials": True,
                    "allowed_endpoint_hosts": ["evil.example"]},
            providers={"cerebras": {"enabled": True, "protected": False,
                                     "reject_request_credentials": False}},
        )
        endpoint = router.invoke_chat({
            "_runtime": runtime, "provider": "cerebras", "model": "gpt-oss-120b",
            "base_url": "https://evil.example/v1", "prompt": "hello",
        })
        credential = router.invoke_chat({
            "_runtime": runtime, "provider": "cerebras", "model": "gpt-oss-120b",
            "api_key": "caller-secret", "prompt": "hello",
        })
        assert endpoint["metadata"]["error_class"] == "policy_endpoint_not_allowed"
        assert credential["metadata"]["error_class"] == "policy_credential_not_allowed"
        assert not cerebras.calls

    def test_fast_profile_uses_cerebras_when_enabled_and_configured(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY", "operator-secret")
        cerebras = FakeAdapter()
        result = router.invoke_prompt({
            "_runtime": self._runtime(cerebras, FakeAdapter(), providers={"cerebras": {"enabled": True}}),
            "profile": "fast",
        })
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "cerebras"
        assert result["metadata"]["selected_model"] == "gpt-oss-120b"

    def test_fast_profile_with_explicit_groq_model_skips_configured_cerebras(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY", "operator-secret")
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", "groq-secret")
        cerebras = FakeAdapter()
        groq = FakeAdapter()
        result = router.invoke_prompt({
            "_runtime": self._runtime(cerebras, groq, providers={"cerebras": {"enabled": True}}),
            "profile": "fast",
            "model": "openai/gpt-oss-120b",
        })
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"
        assert result["metadata"]["selected_model"] == "openai/gpt-oss-120b"
        assert not cerebras.calls

    def test_fast_profile_skips_enabled_cerebras_without_credential(self, monkeypatch):
        monkeypatch.delenv("TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY", raising=False)
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", "groq-secret")
        groq = FakeAdapter()
        result = router.invoke_prompt({
            "_runtime": self._runtime(FakeAdapter(), groq, providers={"cerebras": {"enabled": True}}),
            "profile": "fast",
        })
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"
        assert result["metadata"]["selected_model"] == "openai/gpt-oss-120b"

    def test_explicit_cerebras_missing_credential_does_not_fallback(self, monkeypatch):
        monkeypatch.delenv("TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY", raising=False)
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", "groq-secret")
        groq = FakeAdapter()
        result = router.invoke_chat({
            "_runtime": self._runtime(FakeAdapter(), groq, providers={"cerebras": {"enabled": True}}),
            "provider": "cerebras",
            "model": "gpt-oss-120b",
            "prompt": "hello",
        })
        assert result["metadata"]["error_class"] == "credential_missing"
        assert not groq.calls

    def test_explicit_cerebras_transient_failure_does_not_change_provider(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY", "operator-secret")
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", "groq-secret")
        primary = FakeAdapter({"invoke_chat": router.RouterError("provider_unavailable", "down")})
        fallback = FakeAdapter()
        result = router.invoke_chat({
            "_runtime": self._runtime(primary, fallback, providers={"cerebras": {"enabled": True}}),
            "provider": "cerebras",
            "model": "gpt-oss-120b",
            "prompt": "hello",
        })
        assert result["status"] is False
        assert result["metadata"]["selected_provider"] == "cerebras"
        assert result["metadata"]["fallback_used"] is False
        assert not fallback.calls

    def test_transient_cerebras_failure_falls_back_to_explicit_groq_receipt(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY", "operator-secret")
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", "groq-secret")
        primary = FakeAdapter({"invoke_chat": router.RouterError("provider_rate_limited", "busy")})
        fallback = FakeAdapter()
        result = router.invoke_chat({
            "_runtime": self._runtime(primary, fallback, providers={"cerebras": {"enabled": True}}),
            "profile": "fast",
            "prompt": "hello",
        })
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"
        assert result["metadata"]["selected_model"] == "openai/gpt-oss-120b"
        assert result["metadata"]["fallback_used"] is True
        assert result["metadata"]["fallback_attempts"] == [{
            "provider": "cerebras",
            "model": "gpt-oss-120b",
            "error_class": "provider_rate_limited",
            "latency_ms": 0,
            "retry": False,
        }]

    @pytest.mark.parametrize(
        "error_class",
        ["provider_authentication", "policy_model_not_allowed", "invalid_request",
         "provider_content_rejected", "unsupported_capability"],
    )
    def test_non_transient_cerebras_errors_never_fallback(self, monkeypatch, error_class):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY", "operator-secret")
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", "groq-secret")
        primary = FakeAdapter({"invoke_chat": router.RouterError(error_class, "safe failure")})
        fallback = FakeAdapter()
        result = router.invoke_chat({
            "_runtime": self._runtime(primary, fallback, providers={"cerebras": {"enabled": True}}),
            "profile": "fast",
            "prompt": "hello",
        })
        assert result["status"] is False
        assert result["metadata"]["error_class"] == error_class
        assert not fallback.calls

    @pytest.mark.parametrize("field", ["endpoint", "base_url"])
    def test_endpoint_injection_is_rejected_before_adapter(self, monkeypatch, field):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY", "operator-secret")
        cerebras = FakeAdapter()
        result = router.invoke_chat({
            "_runtime": self._runtime(cerebras, FakeAdapter(), providers={"cerebras": {"enabled": True}}),
            "provider": "cerebras",
            "model": "gpt-oss-120b",
            field: "https://evil.example/v1",
            "prompt": "hello",
        })
        assert result["metadata"]["error_class"] == "policy_endpoint_not_allowed"
        assert not cerebras.calls

    def test_api_key_injection_is_rejected_and_sanitized_before_adapter(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY", "operator-secret")
        cerebras = FakeAdapter()
        result = router.invoke_chat({
            "_runtime": self._runtime(cerebras, FakeAdapter(), providers={"cerebras": {"enabled": True}}),
            "provider": "cerebras",
            "model": "gpt-oss-120b",
            "api_key": "caller-secret",
            "prompt": "private prompt",
        })
        assert result["metadata"]["error_class"] == "policy_credential_not_allowed"
        assert not cerebras.calls
        serialized = json.dumps(result)
        assert "caller-secret" not in serialized
        assert "private prompt" not in serialized

    def test_cerebras_adapter_delegates_and_parses_receipt(self):
        services = RuntimeServicesDelegate(response={
            "status": True,
            "data": {"completed": True, "output": "ok"},
            "metadata": {"provider_request_id": "cerebras-1", "usage": {"total_tokens": 2}},
        })
        adapter = router.CerebrasAdapter(router.RuntimeFacade(services), router.MediaSecurity({"media": {"allowed_roots": [os.getcwd()]}}))
        route = TestProviderAdapters().route("cerebras", "cerebras", model="gpt-oss-120b")
        request = TestProviderAdapters().request("completion_receipt", "chat", "execute", prompt="hello")
        result = adapter.invoke_chat(route, request)
        assert services.calls[0]["target"] == "cerebras"
        assert services.calls[0]["command"] == "completion_receipt"
        assert result.data["content"] == "ok"
        assert result.provider_request_id == "cerebras-1"
        assert result.usage == {"total_tokens": 2}


# --- Vault-bound Vertex auth -------------------------------------------------
# An operator binds providers.vertex_ai to vault references; the router then
# asks the runtime for the (credential, project) pair through the zero-argument
# RuntimeFacade.resolve_vertex_auth() and never reads the environment, ADC, or
# a caller-supplied value for that route. All secrets below are synthetic.

SYNTHETIC_KEY_MARKER = "SYNTHETIC-TEST-KEY-NOT-A-SECRET"
SYNTHETIC_KEY_ID = "synthetic-key-id"
SYNTHETIC_PROJECT = "syntheticproject"
SYNTHETIC_SERVICE_ACCOUNT = json.dumps({
    "type": "service_account",
    "project_id": SYNTHETIC_PROJECT,
    "private_key_id": SYNTHETIC_KEY_ID,
    "private_key": f"-----BEGIN PRIVATE KEY-----\n{SYNTHETIC_KEY_MARKER}\n-----END PRIVATE KEY-----\n",
    "client_email": f"router-test@{SYNTHETIC_PROJECT}.iam.gserviceaccount.com",
})
VAULT_CREDENTIAL_REF = "TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL"
VAULT_PROJECT_REF = "TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID"
VAULT_SCOPE = {"organization_id": "org-synthetic", "project_id": "project-synthetic"}
VAULT_BINDING = {
    "credential_vault_ref": VAULT_CREDENTIAL_REF,
    "project_vault_ref": VAULT_PROJECT_REF,
    "vault_scope_allowlist": [dict(VAULT_SCOPE)],
}
ENV_CREDENTIAL = "env-credential-must-not-be-used"
ENV_PROJECT = "env-project-must-not-be-used"
CALLER_VALUE = "caller-value-must-not-leak"
# Typed, non-transient failure classes for an unusable vault pair.
VAULT_FAILURE_CLASSES = {"credential_missing", "credential_invalid"}
_UNSET = object()


def vault_bound_config(**extra):
    return router._deep_merge({"providers": {"vertex_ai": copy.deepcopy(VAULT_BINDING)}}, extra)


def assert_no_secret(*values):
    for value in values:
        text = value if isinstance(value, str) else json.dumps(value, default=repr)
        for secret in (SYNTHETIC_KEY_MARKER, SYNTHETIC_KEY_ID, CALLER_VALUE):
            assert secret not in text


def assert_sanitized_vault_error(error):
    assert isinstance(error, router.RouterError)
    assert error.error_class in VAULT_FAILURE_CLASSES
    assert error.transient is False
    # The original exception must not ride along as an explicit or implicit cause.
    assert error.__cause__ is None
    assert error.__context__ is None or error.__suppress_context__ is True
    assert_no_secret(error.safe_message, str(error), repr(error), repr(error.args), error.details)


class ScopedRuntime(FakeRuntime):
    def scope(self):
        return {**VAULT_SCOPE, "actor_id": "actor-1"}


class VaultRuntime(ScopedRuntime):
    """Runtime exposing the zero-argument resolve_vertex_auth() contract."""

    def __init__(self, config=None, adapters=None, trusted_headers=None, auth=_UNSET, error=None):
        super().__init__(config=config, adapters=adapters, trusted_headers=trusted_headers)
        self.auth = {"credential": SYNTHETIC_SERVICE_ACCOUNT, "project": SYNTHETIC_PROJECT} if auth is _UNSET else auth
        self.error = error
        self.auth_calls = []

    def resolve_vertex_auth(self, *args, **kwargs):
        # Records every call so tests can prove no params or reference are passed.
        self.auth_calls.append((args, kwargs))
        if self.error is not None:
            raise self.error() if callable(self.error) else self.error
        return copy.deepcopy(self.auth)


class NonCallableResolverRuntime(ScopedRuntime):
    resolve_vertex_auth = "not-callable"


class VaultDelegateRuntime(VaultRuntime):
    """No injected adapters, so the built-in Google adapter delegates here."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.adapters = {}
        self.payloads = []

    def delegate(self, connector, request_data=None, command=None):
        self.payloads.append((connector, command, request_data))
        return {"status": True, "data": "vertex-chat", "metadata": {}}


MALFORMED_AUTH = [
    pytest.param(None, id="none"),
    pytest.param({}, id="empty"),
    pytest.param({"credential": SYNTHETIC_SERVICE_ACCOUNT}, id="missing-project"),
    pytest.param({"project": SYNTHETIC_PROJECT}, id="missing-credential"),
    pytest.param({"credential": "", "project": SYNTHETIC_PROJECT}, id="empty-credential"),
    pytest.param({"credential": SYNTHETIC_SERVICE_ACCOUNT, "project": ""}, id="empty-project"),
    pytest.param({"credential": SYNTHETIC_SERVICE_ACCOUNT, "project": None}, id="null-project"),
    pytest.param({"credential": 42, "project": SYNTHETIC_PROJECT}, id="non-string-credential"),
    pytest.param({"credential": SYNTHETIC_SERVICE_ACCOUNT, "project": [SYNTHETIC_PROJECT]}, id="non-string-project"),
    pytest.param((SYNTHETIC_SERVICE_ACCOUNT, SYNTHETIC_PROJECT), id="tuple"),
    pytest.param(SYNTHETIC_SERVICE_ACCOUNT, id="bare-string"),
]

RESOLVER_ERRORS = [
    pytest.param(lambda: RuntimeError(f"vault read failed {SYNTHETIC_KEY_MARKER}"), id="runtime-error"),
    pytest.param(lambda: KeyError(SYNTHETIC_SERVICE_ACCOUNT), id="key-error"),
    pytest.param(lambda: TypeError(f"bad call {SYNTHETIC_KEY_MARKER}"), id="type-error"),
    pytest.param(lambda: TimeoutError(f"vault timeout {SYNTHETIC_KEY_MARKER}"), id="timeout"),
    pytest.param(lambda: PermissionError(f"denied {SYNTHETIC_KEY_ID}"), id="permission"),
    pytest.param(lambda: router.RouterError("credential_missing", f"leaky {SYNTHETIC_KEY_MARKER}"), id="router-error"),
]

MISSING_RESOLVER_RUNTIMES = [
    pytest.param(ScopedRuntime, id="no-method"),
    pytest.param(NonCallableResolverRuntime, id="non-callable"),
]

_CALLER_OVERRIDE_FIELDS = {
    "credential": CALLER_VALUE,
    "api_key": CALLER_VALUE,
    "project": CALLER_VALUE,
    "project_id": CALLER_VALUE,
    "location": CALLER_VALUE,
    "credential_vault_ref": CALLER_VALUE,
    "project_vault_ref": CALLER_VALUE,
    "vault_scope_allowlist": [{"organization_id": "org-attacker", "project_id": CALLER_VALUE}],
}
# (workflow params, runtime trusted_headers)
CALLER_OVERRIDES = (
    [pytest.param({name: value}, {}, id=f"top-level-{name}") for name, value in _CALLER_OVERRIDE_FIELDS.items()]
    + [pytest.param({"params": {name: value}}, {}, id=f"params-{name}") for name, value in _CALLER_OVERRIDE_FIELDS.items()]
    + [pytest.param({"headers": {name: CALLER_VALUE}}, {}, id=f"headers-{name}")
       for name in ("credential", "api_key", "project", "project_id")]
    + [pytest.param({"headers": {name: CALLER_VALUE}}, {name: True}, id=f"trusted-header-{name}")
       for name in ("credential", "api_key")]
)


class TestRuntimeFacadeResolveVertexAuth:
    def test_accepts_validated_service_account_mapping_from_runtime(self):
        credential = json.loads(SYNTHETIC_SERVICE_ACCOUNT)
        credential["token_uri"] = "https://oauth2.googleapis.com/token"
        auth = {"credential": credential, "project": SYNTHETIC_PROJECT}
        runtime = VaultRuntime(auth=auth)
        assert router.RuntimeFacade(runtime).resolve_vertex_auth() == auth
        assert runtime.auth_calls == [((), {})]

    def test_facade_method_takes_no_parameters(self):
        parameters = list(inspect.signature(router.RuntimeFacade.resolve_vertex_auth).parameters)
        assert parameters == ["self"]

    def test_invokes_runtime_method_with_zero_arguments_and_returns_exact_pair(self):
        runtime = VaultRuntime()
        pair = router.RuntimeFacade(runtime).resolve_vertex_auth()
        assert pair == {"credential": SYNTHETIC_SERVICE_ACCOUNT, "project": SYNTHETIC_PROJECT}
        assert runtime.auth_calls == [((), {})]

    @pytest.mark.parametrize("candidate", [
        pytest.param(None, id="no-runtime"),
        pytest.param(object(), id="bare-object"),
        pytest.param(SimpleNamespace(resolve_vertex_auth="not-callable"), id="non-callable"),
        pytest.param(ScopedRuntime(), id="runtime-without-method"),
    ])
    def test_missing_runtime_method_is_typed_and_never_reads_environment(self, monkeypatch, candidate):
        monkeypatch.setenv(VAULT_CREDENTIAL_REF, ENV_CREDENTIAL)
        monkeypatch.setenv(VAULT_PROJECT_REF, ENV_PROJECT)
        with pytest.raises(router.RouterError) as failure:
            router.RuntimeFacade(candidate).resolve_vertex_auth()
        assert_sanitized_vault_error(failure.value)
        assert ENV_CREDENTIAL not in str(failure.value)

    @pytest.mark.parametrize("error", RESOLVER_ERRORS)
    def test_runtime_exception_is_typed_and_sanitized(self, capsys, error):
        runtime = VaultRuntime(error=error)
        with pytest.raises(router.RouterError) as failure:
            router.RuntimeFacade(runtime).resolve_vertex_auth()
        assert_sanitized_vault_error(failure.value)
        # A TypeError must not trigger a retry with a different call shape.
        assert runtime.auth_calls == [((), {})]
        captured = capsys.readouterr()
        assert_no_secret(captured.out, captured.err)

    @pytest.mark.parametrize("auth", MALFORMED_AUTH)
    def test_empty_or_malformed_pair_is_typed_and_sanitized(self, auth):
        with pytest.raises(router.RouterError) as failure:
            router.RuntimeFacade(VaultRuntime(auth=auth)).resolve_vertex_auth()
        assert_sanitized_vault_error(failure.value)


class TestVaultBoundVertexRoute:
    def test_explicit_null_binding_fails_closed_without_environment(self, monkeypatch):
        monkeypatch.setenv(VAULT_CREDENTIAL_REF, ENV_CREDENTIAL)
        monkeypatch.setenv(VAULT_PROJECT_REF, ENV_PROJECT)
        config = {"providers": {"vertex_ai": {key: None for key in VAULT_BINDING}}}
        adapter = FakeAdapter()
        runtime = VaultRuntime(config=config, adapters={"vertex_ai": adapter})
        result = router.invoke_prompt({"_runtime": runtime, "prompt": "hello"})
        assert result["status"] is False
        assert runtime.auth_calls == []
        assert not adapter.routes
        assert_no_secret(result)

    @pytest.mark.parametrize("nested", [False, True])
    @pytest.mark.parametrize("field", list(_CALLER_OVERRIDE_FIELDS))
    def test_options_auth_override_fails_before_resolution(self, nested, field):
        options = {field: CALLER_VALUE}
        if nested:
            options = {"provider_options": options}
        adapter = FakeAdapter()
        runtime = VaultRuntime(config=vault_bound_config(), adapters={"vertex_ai": adapter})
        result = router.invoke_prompt({"_runtime": runtime, "prompt": "hello", "options": options})
        assert result["status"] is False
        assert runtime.auth_calls == []
        assert not adapter.routes
        assert_no_secret(result)

    @pytest.fixture(autouse=True)
    def ambient_environment(self, monkeypatch):
        # Present on purpose: a bound route must ignore these entirely.
        monkeypatch.setenv(VAULT_CREDENTIAL_REF, ENV_CREDENTIAL)
        monkeypatch.setenv(VAULT_PROJECT_REF, ENV_PROJECT)
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", "groq-env-secret")

    def fallback_config(self, **extra):
        return vault_bound_config(
            fallbacks={"chat": {"vertex_ai": [{"provider": "groq", "model": "openai/gpt-oss-120b"}]}},
            **extra,
        )

    @pytest.mark.parametrize("command", ["invoke_prompt", "invoke_chat", "invoke_embedding", "invoke_search"])
    def test_bound_route_consumes_resolved_pair(self, command):
        adapter = FakeAdapter()
        runtime = VaultRuntime(config=vault_bound_config(), adapters={"vertex_ai": adapter})
        result = getattr(router, command)({"_runtime": runtime, "prompt": "hello"})

        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert runtime.auth_calls == [((), {})]
        credentials = adapter.routes[-1].credentials
        assert credentials["credential"] == SYNTHETIC_SERVICE_ACCOUNT
        assert credentials["project"] == SYNTHETIC_PROJECT
        assert credentials["location"] == "global"
        serialized = json.dumps(credentials, default=repr)
        assert ENV_CREDENTIAL not in serialized
        assert ENV_PROJECT not in serialized

    def test_bound_route_keeps_secrets_out_of_receipt_logs_and_config(self, capsys):
        config = vault_bound_config()
        runtime = VaultRuntime(config=config, adapters={"vertex_ai": FakeAdapter()})
        instance = router.Router(runtime)
        result = instance.dispatch("invoke_chat", {"prompt": "hello"})

        assert result["status"] is True
        assert runtime.auth_calls == [((), {})]
        assert_no_secret(result["metadata"], result["message"])
        assert_no_secret(instance.config)
        assert runtime._config == config
        captured = capsys.readouterr()
        assert_no_secret(captured.out, captured.err)

    def test_bound_route_uses_existing_google_delegation(self):
        runtime = VaultDelegateRuntime(config=vault_bound_config())
        with patch.object(router.time, "monotonic", lambda: 0.0):
            result = router.invoke_prompt({"_runtime": runtime, "provider": "vertex_ai",
                                           "model": "gemini-3.8-flash", "timeout_ms": 20000})

        assert result["status"] is True
        assert result["data"] == "vertex-chat"
        assert runtime.auth_calls == [((), {})]
        connector, command, payload = runtime.payloads[-1]
        assert (connector, command) == ("google-genai", "invoke_prompt")
        assert payload["params"]["credential"] == SYNTHETIC_SERVICE_ACCOUNT
        assert payload["params"]["project_id"] == SYNTHETIC_PROJECT
        assert payload["headers"]["project_id"] == SYNTHETIC_PROJECT
        assert payload["params"]["location"] == "global"
        # Existing timeout/retry corrections still apply on the bound route.
        assert payload["params"]["timeout"] == pytest.approx(20.0)
        assert payload["params"]["max_retries"] == 0
        serialized = json.dumps(payload, default=repr)
        assert ENV_CREDENTIAL not in serialized
        assert ENV_PROJECT not in serialized
        for key in VAULT_BINDING:
            assert key not in payload
            assert key not in payload["params"]

    def test_bound_route_uses_existing_in_process_vertex_factory(self):
        runtime = VaultRuntime(config=vault_bound_config())
        runtime.adapters = {}
        chat = MagicMock(return_value="vertex-chat")
        from_info = MagicMock(return_value="scoped-creds")
        modules = {
            "langchain_google_vertexai": SimpleNamespace(ChatVertexAI=chat, VertexAIEmbeddings=MagicMock()),
            "google.oauth2.service_account": SimpleNamespace(Credentials=SimpleNamespace(from_service_account_info=from_info)),
        }
        with patch.dict(sys.modules, modules):
            result = router.invoke_prompt({"_runtime": runtime})

        assert result["status"] is True
        assert runtime.auth_calls == [((), {})]
        assert chat.call_args.kwargs["project"] == SYNTHETIC_PROJECT
        assert chat.call_args.kwargs["credentials"] == "scoped-creds"
        assert from_info.call_args.args[0]["project_id"] == SYNTHETIC_PROJECT

    @pytest.mark.parametrize("params", [
        pytest.param({"provider": "vertex_ai", "model": "gemini-arbitrary-unsupported"}, id="explicit-provider"),
        pytest.param({"model": "gemini-arbitrary-unsupported"}, id="profile"),
    ])
    def test_unsupported_model_rejects_before_resolution(self, params):
        adapter = FakeAdapter()
        runtime = VaultRuntime(config=vault_bound_config(), adapters={"vertex_ai": adapter})
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello", **params})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "policy_model_not_allowed"
        assert runtime.auth_calls == []
        assert adapter.calls == []

    @pytest.mark.parametrize("params", [
        pytest.param({"base_url": "https://caller.test/v1"}, id="base-url"),
        pytest.param({"endpoint": "https://caller.test/v1"}, id="endpoint"),
        pytest.param({"callback_url": "https://caller.test/callback"}, id="callback-url"),
    ])
    def test_request_security_violation_rejects_before_resolution(self, params):
        adapter = FakeAdapter()
        runtime = VaultRuntime(config=vault_bound_config(), adapters={"vertex_ai": adapter})
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello", **params})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "policy_endpoint_not_allowed"
        assert runtime.auth_calls == []
        assert adapter.calls == []

    @pytest.mark.parametrize("params,trusted_headers", CALLER_OVERRIDES)
    def test_bound_route_rejects_caller_auth_overrides_even_when_workflow_credentials_allowed(self, params, trusted_headers):
        vertex = FakeAdapter()
        groq = FakeAdapter()
        runtime = VaultRuntime(
            config=self.fallback_config(policy={"allow_workflow_credentials": True}),
            adapters={"vertex_ai": vertex, "groq": groq},
            trusted_headers=trusted_headers,
        )
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello", **params})

        assert result["status"] is False
        assert result["metadata"]["error_class"] == "policy_credential_not_allowed"
        assert runtime.auth_calls == []
        assert vertex.calls == []
        assert groq.calls == []
        assert_no_secret(result)

    @pytest.mark.parametrize("runtime_class", MISSING_RESOLVER_RUNTIMES)
    def test_missing_resolver_fails_typed_without_env_or_fallback(self, runtime_class):
        vertex = FakeAdapter()
        groq = FakeAdapter()
        runtime = runtime_class(config=self.fallback_config(), adapters={"vertex_ai": vertex, "groq": groq})
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello"})

        assert result["status"] is False
        assert result["metadata"]["error_class"] in VAULT_FAILURE_CLASSES
        assert result["metadata"]["fallback_used"] is False
        assert vertex.calls == []
        assert groq.calls == []
        assert ENV_CREDENTIAL not in json.dumps(result, default=repr)

    @pytest.mark.parametrize("error", RESOLVER_ERRORS)
    def test_resolver_exception_fails_typed_sanitized_without_fallback(self, capsys, error):
        vertex = FakeAdapter()
        groq = FakeAdapter()
        runtime = VaultRuntime(config=self.fallback_config(), adapters={"vertex_ai": vertex, "groq": groq}, error=error)
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello"})

        assert result["status"] is False
        assert result["metadata"]["error_class"] in VAULT_FAILURE_CLASSES
        assert runtime.auth_calls == [((), {})]
        assert vertex.calls == []
        assert groq.calls == []
        assert_no_secret(result)
        captured = capsys.readouterr()
        assert_no_secret(captured.out, captured.err)

    @pytest.mark.parametrize("auth", MALFORMED_AUTH)
    def test_malformed_pair_fails_typed_without_env_or_fallback(self, auth):
        vertex = FakeAdapter()
        groq = FakeAdapter()
        runtime = VaultRuntime(config=self.fallback_config(), adapters={"vertex_ai": vertex, "groq": groq}, auth=auth)
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello"})

        assert result["status"] is False
        assert result["metadata"]["error_class"] in VAULT_FAILURE_CLASSES
        assert vertex.calls == []
        assert groq.calls == []
        assert_no_secret(result)
        assert ENV_CREDENTIAL not in json.dumps(result, default=repr)

    def test_resolver_failure_never_builds_an_adc_client(self):
        runtime = VaultRuntime(config=vault_bound_config(), error=lambda: RuntimeError("vault down"))
        runtime.adapters = {}
        chat = MagicMock(return_value="vertex-chat")
        from_info = MagicMock(return_value="scoped-creds")
        modules = {
            "langchain_google_vertexai": SimpleNamespace(ChatVertexAI=chat, VertexAIEmbeddings=MagicMock()),
            "google.oauth2.service_account": SimpleNamespace(Credentials=SimpleNamespace(from_service_account_info=from_info)),
        }
        with patch.dict(sys.modules, modules):
            result = router.invoke_prompt({"_runtime": runtime})

        assert result["status"] is False
        assert result["metadata"]["error_class"] in VAULT_FAILURE_CLASSES
        chat.assert_not_called()
        from_info.assert_not_called()

    def test_profile_resolver_failure_does_not_fall_through_to_next_candidate(self):
        vertex = FakeAdapter()
        groq = FakeAdapter()
        runtime = VaultRuntime(
            config=vault_bound_config(profiles={"balanced": {"chat": [
                {"provider": "vertex_ai", "model": "gemini-3.5-flash-lite"},
                {"provider": "groq", "model": "openai/gpt-oss-120b"},
            ]}}),
            adapters={"vertex_ai": vertex, "groq": groq},
            error=lambda: RuntimeError("vault down"),
        )
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello"})

        assert result["status"] is False
        assert result["metadata"]["error_class"] in VAULT_FAILURE_CLASSES
        assert vertex.calls == []
        assert groq.calls == []


class TestVaultBindingProfileAvailability:
    @pytest.fixture(autouse=True)
    def groq_environment(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", "groq-env-secret")

    def test_unrelated_available_candidate_never_resolves_vertex(self, monkeypatch):
        monkeypatch.setenv(VAULT_CREDENTIAL_REF, ENV_CREDENTIAL)
        groq = FakeAdapter()
        runtime = VaultRuntime(
            config=vault_bound_config(profiles={"fast": {"chat": [
                {"provider": "groq", "model": "openai/gpt-oss-120b"},
                {"provider": "vertex_ai", "model": "gemini-3.5-flash-lite"},
            ]}}),
            adapters={"vertex_ai": FakeAdapter(), "groq": groq},
        )
        result = router.invoke_prompt({"_runtime": runtime, "profile": "fast"})

        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"
        assert runtime.auth_calls == []

    def test_unkeyed_xai_is_skipped_and_bound_vertex_resolves_once(self, monkeypatch):
        monkeypatch.delenv("TEMP_CONTEXT_VARIABLE_XAI_API_KEY", raising=False)
        monkeypatch.delenv("MACHINA_CONTEXT_VARIABLE_GROK_API_KEY", raising=False)
        monkeypatch.setenv(VAULT_CREDENTIAL_REF, ENV_CREDENTIAL)
        vertex = FakeAdapter()
        runtime = VaultRuntime(config=vault_bound_config(), adapters={"vertex_ai": vertex, "xai": FakeAdapter()})
        result = router.invoke_prompt({"_runtime": runtime, "profile": "social_pulse"})

        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert runtime.auth_calls == [((), {})]
        assert vertex.routes[-1].credentials["credential"] == SYNTHETIC_SERVICE_ACCOUNT

    def test_bound_candidate_is_not_skipped_because_environment_is_absent(self, monkeypatch):
        monkeypatch.delenv(VAULT_CREDENTIAL_REF, raising=False)
        monkeypatch.delenv(VAULT_PROJECT_REF, raising=False)
        vertex = FakeAdapter()
        groq = FakeAdapter()
        runtime = VaultRuntime(
            config=vault_bound_config(
                providers={"vertex_ai": {"require_credential": True}},
                profiles={"balanced": {"chat": [
                    {"provider": "vertex_ai", "model": "gemini-3.5-flash-lite"},
                    {"provider": "groq", "model": "openai/gpt-oss-120b"},
                ]}},
            ),
            adapters={"vertex_ai": vertex, "groq": groq},
        )
        result = router.invoke_prompt({"_runtime": runtime})

        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert runtime.auth_calls == [((), {})]
        assert vertex.routes[-1].credentials["project"] == SYNTHETIC_PROJECT
        assert groq.calls == []


class TestEnvironmentOnlyVertexRouteUnchanged:
    @pytest.fixture(autouse=True)
    def ambient_environment(self, monkeypatch):
        monkeypatch.setenv(VAULT_CREDENTIAL_REF, ENV_CREDENTIAL)
        monkeypatch.setenv(VAULT_PROJECT_REF, ENV_PROJECT)

    def test_env_only_route_never_calls_resolver(self):
        adapter = FakeAdapter()
        runtime = VaultRuntime(adapters={"vertex_ai": adapter})
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello"})

        assert result["status"] is True
        assert runtime.auth_calls == []
        assert adapter.routes[-1].credentials["credential"] == ENV_CREDENTIAL
        assert adapter.routes[-1].credentials["project"] == ENV_PROJECT

    def test_env_only_route_keeps_existing_workflow_credential_policy(self):
        adapter = FakeAdapter()
        runtime = VaultRuntime(config={"policy": {"allow_workflow_credentials": True}}, adapters={"vertex_ai": adapter})
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello", "headers": {"credential": "fresh-from-vault"}})

        assert result["status"] is True
        assert runtime.auth_calls == []
        assert adapter.routes[-1].credentials["credential"] == "fresh-from-vault"

    def test_other_providers_never_call_resolver_when_vertex_is_bound(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", "groq-env-secret")
        groq = FakeAdapter()
        runtime = VaultRuntime(config=vault_bound_config(), adapters={"vertex_ai": FakeAdapter(), "groq": groq})
        result = router.invoke_chat({"_runtime": runtime, "provider": "groq", "model": "openai/gpt-oss-120b", "prompt": "hi"})

        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"
        assert runtime.auth_calls == []


class TestVaultBindingManifest:
    def test_manifest_commands_are_unchanged(self):
        manifest = (CONNECTOR_DIR / "machina-ai.yml").read_text()
        values = set(re.findall(r'^\s*value:\s*"([^"]+)"', manifest, flags=re.MULTILINE))
        assert values == set(router.COMMANDS)
        assert not any("vault" in value or "auth" in value for value in values)
        assert not callable(getattr(router, "resolve_vertex_auth", None))
