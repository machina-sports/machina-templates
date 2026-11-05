"""Vercel AI Gateway backend: dormant by default, ZDR only on operator opt-in.

Offline only. The fake SDK tests prove what the router hands the SDK; the
real-SDK tests (skipped when langchain-openai is absent) prove what reaches the
wire, through an httpx mock transport, without any network call.
"""
import functools
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from test_router import FakeAdapter, FakeRuntime, router

ZDR_BODY = {"providerOptions": {"gateway": {"zeroDataRetention": True}}}
MODEL = "anthropic/claude-sonnet-4.5"
SECRET = "vck-test-only-not-a-real-key"


def gateway_config(zdr=False, **provider_extra):
    provider = {
        "enabled": True,
        "credential": SECRET,
        "allowed_models": {"chat": [MODEL]},
        "zero_data_retention": zdr,
        **provider_extra,
    }
    return {"providers": {"vertex_ai": {"retries": 0}, "vercel_gateway": provider}}


class ProviderError(Exception):
    def __init__(self, status_code):
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class FakeOpenAI:
    """Records every chat.completions.create call; optional scripted failures."""

    def __init__(self, failures=()):
        self.calls = []
        self.failures = list(failures)
        self.constructed = []

    def __call__(self, **kwargs):
        self.constructed.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=self.create)))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.failures:
            raise self.failures.pop(0)
        message = SimpleNamespace(content="ok", tool_calls=None)
        return SimpleNamespace(
            id="gen-1",
            model=MODEL,
            choices=[SimpleNamespace(message=message, finish_reason="stop")],
            usage=None,
        )


def run_chat(config, sdk, **params):
    runtime = FakeRuntime(config=config)
    with patch.dict("sys.modules", {"openai": SimpleNamespace(OpenAI=sdk)}):
        return router.invoke_chat({"_runtime": runtime, "provider": "vercel_gateway", "model": MODEL, "prompt": "hi", **params})


def run_factory(config, **params):
    chat_openai = MagicMock(return_value=object())
    runtime = FakeRuntime(config=config)
    with patch.dict("sys.modules", {"langchain_openai": SimpleNamespace(ChatOpenAI=chat_openai)}):
        result = router.invoke_prompt({"_runtime": runtime, "provider": "vercel_gateway", "model": MODEL, **params})
    return result, chat_openai


class TestDormantByDefault:
    def test_provider_ships_disabled_with_fixed_endpoint_and_no_zdr(self):
        conf = router.DEFAULT_CONFIG["providers"]["vercel_gateway"]
        assert conf["enabled"] is False
        assert conf["reject_request_credentials"] is True
        assert conf["zero_data_retention"] is False
        assert conf["allowed_models"] == {"chat": [], "search_answer": []}
        assert router.FIXED_PROVIDER_ENDPOINTS["vercel_gateway"] == "https://ai-gateway.vercel.sh/v1"

    def test_default_config_refuses_the_route(self):
        sdk = FakeOpenAI()
        result = run_chat({}, sdk)
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "policy_provider_not_allowed"
        assert sdk.calls == []

    def test_default_traffic_is_unchanged(self):
        adapter = FakeAdapter()
        result = router.invoke_chat({"_runtime": FakeRuntime(adapters={"vertex_ai": adapter}), "prompt": "hi"})
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert "zdr_mode" not in result["metadata"]
        assert "gateway" not in result["metadata"]

    def test_health_reports_unknown_account_state(self):
        result = router.health({"_runtime": FakeRuntime(), "provider": "vercel_gateway"})
        [entry] = result["data"]
        assert entry["enabled"] is False
        assert entry["zdr_mode"] == "not_requested"
        assert entry["gateway"] == {
            "backend": "vercel_ai_gateway",
            "zdr_effective": "unknown",
            "zdr_entitlement": "unknown",
            "account_byok": "unknown",
        }

    def test_health_shows_operator_opt_in_without_claiming_enforcement(self):
        result = router.health({"_runtime": FakeRuntime(config=gateway_config(zdr=True)), "provider": "vercel_gateway"})
        [entry] = result["data"]
        assert entry["ready"] is True
        assert entry["zdr_mode"] == "requested"
        assert entry["gateway"]["zdr_effective"] == "unknown"
        assert SECRET not in json.dumps(result)


class TestZdrOff:
    def test_direct_invocation_omits_the_field(self):
        sdk = FakeOpenAI()
        result = run_chat(gateway_config(), sdk)
        assert result["status"] is True
        assert "extra_body" not in sdk.calls[0]
        assert sdk.constructed[0]["base_url"] == "https://ai-gateway.vercel.sh/v1"
        assert result["metadata"]["zdr_mode"] == "not_requested"

    def test_factory_omits_the_field(self):
        result, chat_openai = run_factory(gateway_config())
        assert result["status"] is True
        assert "extra_body" not in chat_openai.call_args.kwargs

    def test_ordinary_fallback_still_applies(self):
        config = gateway_config(retries=0)
        config["fallbacks"] = {"chat": {"vercel_gateway": [{"provider": "vertex_ai", "model": "gemini-3.5-flash-lite"}]}}
        fallback = FakeAdapter()
        runtime = FakeRuntime(config=config, adapters={"vertex_ai": fallback})
        sdk = FakeOpenAI(failures=[ProviderError(503)])
        with patch.dict("sys.modules", {"openai": SimpleNamespace(OpenAI=sdk)}):
            result = router.invoke_chat({"_runtime": runtime, "provider": "vercel_gateway", "model": MODEL, "prompt": "hi"})
        assert result["status"] is True
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert result["metadata"]["fallback_used"] is True

    def test_byok_config_does_not_block_non_zdr_route(self):
        sdk = FakeOpenAI()
        result = run_chat(gateway_config(byok=True), sdk)
        assert result["status"] is True


class TestZdrOn:
    def test_direct_invocation_sends_flag_with_tools_and_structured_output(self):
        sdk = FakeOpenAI()
        tools = [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}]
        response_format = {"type": "json_schema", "json_schema": {"name": "x", "schema": {"type": "object"}}}
        result = run_chat(gateway_config(zdr=True), sdk, options={"tools": tools, "response_format": response_format})
        assert result["status"] is True
        call = sdk.calls[0]
        assert call["extra_body"] == ZDR_BODY
        assert call["tools"] == tools
        assert call["response_format"] == response_format

    def test_every_retry_carries_the_flag(self):
        sdk = FakeOpenAI(failures=[ProviderError(503)])
        result = run_chat(gateway_config(zdr=True, retries=1), sdk)
        assert result["status"] is True
        assert len(sdk.calls) == 2
        assert all(call["extra_body"] == ZDR_BODY for call in sdk.calls)

    def test_factory_model_carries_the_flag(self):
        result, chat_openai = run_factory(gateway_config(zdr=True))
        assert result["status"] is True
        assert chat_openai.call_args.kwargs["extra_body"] == ZDR_BODY
        assert result["metadata"]["zdr_mode"] == "requested"

    @pytest.mark.parametrize("operator_override", [{}, {"fail_closed": False, "protected": False}])
    def test_no_fallback_downgrades_retention(self, operator_override):
        config = gateway_config(zdr=True, **operator_override)
        config["fallbacks"] = {"chat": {"vercel_gateway": [{"provider": "vertex_ai", "model": "gemini-3.5-flash-lite"}]}}
        fallback = FakeAdapter()
        runtime = FakeRuntime(config=config, adapters={"vertex_ai": fallback})
        sdk = FakeOpenAI(failures=[ProviderError(503)])
        with patch.dict("sys.modules", {"openai": SimpleNamespace(OpenAI=sdk)}):
            result = router.invoke_chat({"_runtime": runtime, "provider": "vercel_gateway", "model": MODEL, "prompt": "hi"})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "provider_unavailable"
        assert fallback.calls == []

    def test_profile_does_not_skip_zdr_route_on_missing_credential(self):
        config = gateway_config(zdr=True)
        del config["providers"]["vercel_gateway"]["credential"]
        config["profiles"] = {"private": {"chat": [
            {"provider": "vercel_gateway", "model": MODEL},
            {"provider": "vertex_ai", "model": "gemini-3.5-flash-lite"},
        ]}}
        fallback = FakeAdapter()
        runtime = FakeRuntime(config=config, adapters={"vertex_ai": fallback})
        with patch.dict("os.environ", {}, clear=True):
            result = router.invoke_chat({"_runtime": runtime, "profile": "private", "prompt": "hi"})
        assert result["metadata"]["error_class"] == "credential_missing"
        assert fallback.calls == []

    def test_operator_byok_is_refused(self):
        sdk = FakeOpenAI()
        result = run_chat(gateway_config(zdr=True, byok={"anthropic": "configured"}), sdk)
        assert result["metadata"]["error_class"] == "policy_credential_not_allowed"
        assert sdk.calls == []

    def test_string_opt_in_from_json_config_is_honoured(self):
        sdk = FakeOpenAI()
        run_chat(gateway_config(zdr="true"), sdk)
        assert sdk.calls[0]["extra_body"] == ZDR_BODY


class TestWorkflowCannotChangePolicy:
    @pytest.mark.parametrize("zdr", [False, True])
    @pytest.mark.parametrize("params", [
        {"options": {"provider_options": {"gateway": {"zeroDataRetention": False}}}},
        {"provider_options": {"gateway": {"order": ["bedrock"]}}},
        {"extra_body": {"providerOptions": {"gateway": {"zeroDataRetention": False}}}},
        {"params": {"zero_data_retention": False}},
        {"options": {"zeroDataRetention": True}},
        {"options": {"byok": {"anthropic": [{"apiKey": "x"}]}}},
    ])
    def test_provider_option_injection_rejected_before_any_call(self, zdr, params):
        sdk = FakeOpenAI()
        result = run_chat(gateway_config(zdr=zdr), sdk, **params)
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "unsupported_option"
        assert sdk.calls == [] and sdk.constructed == []

    @pytest.mark.parametrize("zdr", [False, True])
    def test_endpoint_override_rejected(self, zdr):
        sdk = FakeOpenAI()
        result = run_chat(gateway_config(zdr=zdr), sdk, base_url="https://evil.example/v1")
        assert result["metadata"]["error_class"] == "policy_endpoint_not_allowed"
        assert sdk.calls == []

    @pytest.mark.parametrize("zdr", [False, True])
    def test_request_credential_rejected(self, zdr):
        sdk = FakeOpenAI()
        result = run_chat(gateway_config(zdr=zdr), sdk, api_key="workflow-key")
        assert result["metadata"]["error_class"] == "policy_credential_not_allowed"
        assert sdk.calls == []

    def test_zdr_rejects_trusted_request_credential_even_if_policy_relaxed(self):
        sdk = FakeOpenAI()
        result = run_chat(gateway_config(zdr=True, reject_request_credentials=False), sdk, api_key="workflow-key")
        assert result["metadata"]["error_class"] == "policy_credential_not_allowed"

    @pytest.mark.parametrize("zdr", [False, True])
    def test_missing_credential_fails_typed(self, zdr):
        config = gateway_config(zdr=zdr)
        del config["providers"]["vercel_gateway"]["credential"]
        sdk = FakeOpenAI()
        with patch.dict("os.environ", {}, clear=True):
            result = run_chat(config, sdk)
        assert result["metadata"]["error_class"] == "credential_missing"
        assert sdk.calls == []

    def test_model_outside_operator_allowlist_rejected(self):
        sdk = FakeOpenAI()
        result = run_chat(gateway_config(zdr=True), sdk, model="openai/gpt-5")
        assert result["metadata"]["error_class"] == "policy_model_not_allowed"


class TestReceipt:
    def test_receipt_separates_gateway_from_upstream_without_secrets(self):
        sdk = FakeOpenAI()
        result = run_chat(gateway_config(zdr=True), sdk)
        metadata = result["metadata"]
        assert metadata["selected_provider"] == "vercel_gateway"
        assert metadata["selected_model"] == MODEL
        assert metadata["zdr_mode"] == "requested"
        assert metadata["gateway"] == {
            "backend": "vercel_ai_gateway",
            "zdr_effective": "unknown",
            "upstream_provider": None,
            "upstream_model": MODEL,
        }
        assert "provider_extensions" not in metadata
        assert SECRET not in json.dumps(result, default=str)

    def test_failure_receipt_keeps_gateway_identity(self):
        sdk = FakeOpenAI(failures=[ProviderError(403)])
        result = run_chat(gateway_config(zdr=True), sdk)
        assert result["metadata"]["error_class"] == "provider_authentication"
        assert result["metadata"]["zdr_mode"] == "requested"
        assert result["metadata"]["gateway"]["upstream_model"] is None


class TestRealSdkWire:
    """What actually reaches the wire, through the real SDKs, offline."""

    @pytest.fixture
    def wire(self):
        httpx = pytest.importorskip("httpx")
        bodies = []
        completion = {
            "id": "gen-1", "object": "chat.completion", "created": 0, "model": MODEL,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "{\"a\": 1}"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
        chunk = {"id": "gen-1", "object": "chat.completion.chunk", "created": 0, "model": MODEL,
                 "choices": [{"index": 0, "delta": {"content": "ok"}, "finish_reason": None}]}

        def handler(request):
            body = json.loads(request.content)
            bodies.append(body)
            assert request.url.host == "ai-gateway.vercel.sh"
            if body.get("stream"):
                stream = f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n"
                return httpx.Response(200, text=stream, headers={"content-type": "text/event-stream"})
            return httpx.Response(200, json=completion)

        return SimpleNamespace(bodies=bodies, client=lambda: httpx.Client(transport=httpx.MockTransport(handler)))

    @pytest.mark.parametrize("zdr", [False, True])
    def test_returned_model_invocations(self, wire, zdr):
        langchain_openai = pytest.importorskip("langchain_openai")
        pydantic = pytest.importorskip("pydantic")

        class Answer(pydantic.BaseModel):
            a: int

        chat_openai = functools.partial(langchain_openai.ChatOpenAI, http_client=wire.client())
        runtime = FakeRuntime(config=gateway_config(zdr=zdr))
        with patch.object(langchain_openai, "ChatOpenAI", chat_openai):
            result = router.invoke_prompt({"_runtime": runtime, "provider": "vercel_gateway", "model": MODEL})
        model = result["data"]
        model.invoke("hi")
        model.bind_tools([Answer]).invoke("hi")
        model.with_structured_output(Answer, method="json_schema").invoke("hi")
        list(model.stream("hi"))
        assert len(wire.bodies) == 4
        for body in wire.bodies:
            if zdr:
                assert body["providerOptions"] == ZDR_BODY["providerOptions"]
            else:
                assert "providerOptions" not in body
        assert "tools" in wire.bodies[1]
        assert "response_format" in wire.bodies[2]
        assert wire.bodies[3]["stream"] is True

    @pytest.mark.parametrize("zdr", [False, True])
    def test_direct_invocation(self, wire, zdr):
        openai = pytest.importorskip("openai")
        client = functools.partial(openai.OpenAI, http_client=wire.client())
        runtime = FakeRuntime(config=gateway_config(zdr=zdr))
        with patch.object(openai, "OpenAI", client):
            result = router.invoke_chat({"_runtime": runtime, "provider": "vercel_gateway", "model": MODEL, "prompt": "hi"})
        assert result["status"] is True
        [body] = wire.bodies
        assert ("providerOptions" in body) is zdr
        if zdr:
            assert body["providerOptions"] == ZDR_BODY["providerOptions"]
        assert result["metadata"]["gateway"]["upstream_model"] == MODEL
