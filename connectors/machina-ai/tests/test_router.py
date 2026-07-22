import importlib.util
import json
import os
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
        self.factory = object()
        self.embedding_factory = object()

    def _call(self, name, route, request, data):
        self.calls.append((name, route.provider, route.model, request))
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
        assert result["metadata"]["selected_model"] == "gemini-2.5-flash"
        assert result["metadata"]["route_reason"] == "profile:balanced"

    def test_direct_chat_returns_canonical_envelope_and_receipt(self):
        result = router.invoke_chat({"_runtime": FakeRuntime(), "prompt": "hello"})
        assert result["status"] is True
        assert set(result) == {"status", "data", "message", "metadata"}
        assert result["data"]["role"] == "assistant"
        assert result["data"]["content"] == "ok"
        assert result["metadata"]["provider_request_id"] == "req-vertex_ai"
        assert result["metadata"]["usage"] == {"total_tokens": 3}

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
        assert providers == {"vertex_ai", "groq", "google_speech"}
        assert "openai" not in providers
        assert all(item["enabled"] for item in result["data"])

    def test_health_is_local_and_structured(self):
        result = router.health({"_runtime": FakeRuntime()})
        assert result["status"] is True
        vertex = next(item for item in result["data"] if item["provider"] == "vertex_ai")
        assert vertex["enabled"] is True
        assert "capabilities" in vertex


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

    def route(self, provider="groq", adapter="groq", capability="chat", model="llama-3.3-70b-versatile"):
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
        result = adapter.create_chat_model(self.route(), self.request())
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
                "fallbacks": {"chat": {"vertex_ai": [{"provider": "groq", "model": "llama-3.1-8b-instant"}]}},
            },
            adapters={"vertex_ai": primary, "groq": fallback},
        )
        result = router.invoke_chat({"_runtime": runtime, "model": "gemini-2.5-flash", "prompt": "hello"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"
        assert result["metadata"]["selected_model"] == "llama-3.1-8b-instant"
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
                "fallbacks": {"chat": {"vertex_ai": [{"provider": "groq", "model": "llama-3.3-70b-versatile"}]}},
            },
            adapters={"vertex_ai": primary, "groq": fallback},
        )
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello"})
        assert result["status"] is False
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert result["metadata"]["selected_model"] == "gemini-2.5-flash"
        assert result["metadata"]["route_reason"] == "profile:balanced"
        assert [attempt["provider"] for attempt in result["metadata"]["fallback_attempts"]] == ["vertex_ai", "groq"]


class TestRemapPrecedence:
    def test_profile_remap_without_capability_entry_falls_through(self):
        runtime = FakeRuntime(config={"remaps": {"profiles": {"fast": {"chat": {"provider": "groq", "model": "llama-3.3-70b-versatile"}}}}})
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
        assert result["metadata"]["selected_model"] == "gemini-2.5-flash-lite"
        assert result["metadata"]["route_reason"] == "profile:cheap"

    def test_groq_enabled_with_env_credential_only(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", "env-secret")
        groq = FakeAdapter()
        runtime = FakeRuntime(adapters={"vertex_ai": FakeAdapter(), "groq": groq})
        result = router.invoke_chat({"_runtime": runtime, "provider": "groq", "model": "llama-3.3-70b-versatile", "prompt": "hi"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"

    def test_groq_without_env_credential_is_typed_credential_missing(self, monkeypatch):
        monkeypatch.delenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", raising=False)
        monkeypatch.delenv("TEMP_CONTEXT_VARIABLE_SDK_GROQ_API_KEY", raising=False)
        result = router.invoke_chat({"_runtime": FakeRuntime(), "provider": "groq", "model": "llama-3.3-70b-versatile", "prompt": "hi"})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "credential_missing"

    def test_fast_profile_routes_to_groq_default_model(self, monkeypatch):
        monkeypatch.setenv("TEMP_CONTEXT_VARIABLE_GROQ_API_KEY", "env-secret")
        groq = FakeAdapter()
        runtime = FakeRuntime(adapters={"vertex_ai": FakeAdapter(), "groq": groq})
        result = router.invoke_prompt({"_runtime": runtime, "profile": "fast"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "groq"
        assert result["metadata"]["selected_model"] == "llama-3.3-70b-versatile"

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
