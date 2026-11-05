"""Grounded search through the Vercel AI Gateway (`vercel_gateway` + perplexity/*).

Route under test: consumer -> machina-ai invoke_search -> Vercel AI Gateway
POST /v3/ai/language-model (AI SDK protocol) -> Perplexity Sonar.

A live call (2026-11-05) showed the gateway's OpenAI-compatible endpoints
(/v1/chat/completions and /v1/responses) answer Perplexity requests but drop
the sources: only the AI SDK protocol returns them, as `source` content parts.
The fixtures below follow the shape of that live result.

Offline only. Wire tests drive the real `openai` SDK through an httpx mock
transport; no network call, no real credential. Every response body below is a
SYNTHETIC fixture. URLs use the reserved `.invalid` TLD.
"""
import functools
import json
from unittest.mock import patch

import pytest
from test_router import FakeAdapter, FakeRuntime, router

SECRET = "vck-test-only-not-a-real-key"
MODEL = "perplexity/sonar"
A = "https://a.invalid/1"
B = "https://b.invalid/2"
C = "https://c.invalid/3"


def gateway_config(zdr=False, models=(MODEL,), profiles=None, **provider_extra):
    config = {
        "policy": {"max_timeout_ms": 300000, "total_deadline_ms": 300000},
        "providers": {
            "vertex_ai": {"retries": 0},
            "vercel_gateway": {
                "enabled": True,
                "credential": SECRET,
                "allowed_models": {"chat": [], "search_answer": list(models)},
                "zero_data_retention": zdr,
                **provider_extra,
            },
        },
    }
    if profiles is not None:
        config["profiles"] = profiles
    return config


def source(index, url, title="Synthetic"):
    return {"type": "source", "sourceType": "url", "id": str(index), "url": url, "title": title,
            "providerMetadata": {"perplexity": {"resultId": index, "snippet": "synthetic"}}}


def native(content=None, **overrides):
    """SYNTHETIC gateway AI SDK generate result for a Perplexity model."""
    body = {
        "content": [source(1, A), source(2, B), {"type": "text", "text": "Synthetic answer [1][2]."}]
        if content is None else content,
        "finishReason": {"unified": "stop", "raw": "completed"},
        "usage": {"inputTokens": {"total": 5, "noCache": 5}, "outputTokens": {"total": 7, "text": 7}},
        "providerMetadata": {"gateway": {"generationId": "gen-synthetic-1", "billableWebSearchCalls": 1}},
        "warnings": [],
    }
    body.update(overrides)
    return body


def text(value):
    return {"type": "text", "text": value}


def run(config, respond, adapters=None, **params):
    httpx = pytest.importorskip("httpx")
    openai = pytest.importorskip("openai")
    seen = []

    def handler(request):
        seen.append(request)
        result = respond(request)
        if isinstance(result, Exception):
            raise result
        return result

    vertex = FakeAdapter()
    runtime = FakeRuntime(config=config, adapters=adapters if adapters is not None else {"vertex_ai": vertex})
    client = functools.partial(openai.OpenAI, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    call = {"_runtime": runtime, "prompt": "synthetic question", **params}
    if "profile" not in params:
        call.setdefault("provider", "vercel_gateway")
        call.setdefault("model", MODEL)
    with patch.object(openai, "OpenAI", client):
        result = router.invoke_search(call)
    return result, seen, vertex


def ok(body=None, status=200):
    httpx = pytest.importorskip("httpx")
    return lambda request: httpx.Response(status, json=native() if body is None else body)


def body_of(request):
    return json.loads(request.content)


class TestDormantByDefault:
    def test_gateway_ships_disabled_with_empty_search_allowlist(self):
        conf = router.DEFAULT_CONFIG["providers"]["vercel_gateway"]
        assert conf["enabled"] is False
        assert conf["allowed_models"] == {"chat": [], "search_answer": []}

    def test_no_default_profile_or_fallback_routes_search_to_the_gateway(self):
        config = router.DEFAULT_CONFIG
        routed = json.dumps([config["defaults"], config["profiles"], config["fallbacks"], config["remaps"]])
        assert "vercel_gateway" not in routed
        assert config["defaults"]["search_answer"]["provider"] == "vertex_ai"

    def test_default_config_refuses_before_http(self):
        result, seen, vertex = run({}, ok())
        assert result["metadata"]["error_class"] == "policy_provider_not_allowed"
        assert seen == [] and vertex.calls == []

    def test_enabled_for_chat_only_is_not_search_support(self):
        config = gateway_config(models=())
        config["providers"]["vercel_gateway"]["allowed_models"]["chat"] = ["anthropic/claude-sonnet-4.5"]
        result, seen, _ = run(config, ok())
        assert result["metadata"]["error_class"] == "unsupported_capability"
        assert seen == []

    def test_ungrounded_gateway_model_is_refused_even_if_allowlisted(self):
        model = "anthropic/claude-sonnet-4.5"
        result, seen, _ = run(gateway_config(models=(model,)), ok(), model=model)
        assert result["metadata"]["error_class"] == "unsupported_capability"
        assert seen == []

    def test_model_outside_allowlist_is_refused(self):
        result, seen, _ = run(gateway_config(), ok(), model="perplexity/sonar-pro")
        assert result["metadata"]["error_class"] == "policy_model_not_allowed"
        assert seen == []


class TestExactWireRequest:
    def test_request_goes_to_the_gateway_with_runtime_credential_and_fixed_body(self):
        result, [request], vertex = run(gateway_config(), ok(), timeout=180)
        assert result["status"] is True
        assert request.method == "POST"
        assert str(request.url) == "https://ai-gateway.vercel.sh/v3/ai/language-model"
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        assert request.headers["ai-gateway-protocol-version"] == "0.0.1"
        assert request.headers["ai-gateway-auth-method"] == "api-key"
        assert request.headers["ai-language-model-specification-version"] == "3"
        assert request.headers["ai-language-model-id"] == MODEL
        assert request.headers["ai-language-model-streaming"] == "false"
        assert body_of(request) == {
            "prompt": [{"role": "user", "content": [{"type": "text", "text": "synthetic question"}]}],
            "providerOptions": {"gateway": {"only": ["perplexity"]}},
        }
        # Router-owned deadline reaches the transport; the SDK never retries.
        assert request.extensions["timeout"]["read"] == pytest.approx(180)
        assert vertex.calls == []

    def test_never_calls_perplexity_directly_or_the_openai_compatible_path(self):
        _, [request], _ = run(gateway_config(), ok())
        assert request.url.host == "ai-gateway.vercel.sh"
        assert "api.perplexity.ai" not in str(request.url)
        assert "chat/completions" not in str(request.url)

    def test_zdr_opt_in_is_sent_with_the_provider_pin(self):
        _, [request], _ = run(gateway_config(zdr=True), ok())
        assert body_of(request)["providerOptions"] == {"gateway": {"only": ["perplexity"], "zeroDataRetention": True}}

    def test_no_gateway_model_fallback_is_requested(self):
        _, [request], _ = run(gateway_config(), ok())
        body = body_of(request)
        assert "models" not in body and "models" not in body["providerOptions"]["gateway"]
        assert "order" not in body["providerOptions"]["gateway"]

    def test_caller_temperature_and_max_tokens_are_forwarded(self):
        _, [request], _ = run(gateway_config(), ok(), temperature=0, max_tokens=900)
        body = body_of(request)
        assert body["temperature"] == 0 and body["maxOutputTokens"] == 900
        assert "max_tokens" not in body

    def test_messages_are_mapped_to_the_ai_sdk_prompt(self):
        messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"},
                    {"role": "assistant", "content": "a"}, {"role": "user", "content": "u2"}]
        _, [request], _ = run(gateway_config(), ok(), messages=messages, prompt=None)
        assert body_of(request)["prompt"] == [
            {"role": "system", "content": "s"},
            {"role": "user", "content": [{"type": "text", "text": "u"}]},
            {"role": "assistant", "content": [{"type": "text", "text": "a"}]},
            {"role": "user", "content": [{"type": "text", "text": "u2"}]},
        ]

    @pytest.mark.parametrize("messages", [
        [{"role": "tool", "content": "x"}],
        [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": A}}]}],
        [{"role": "user", "content": None}],
        ["not a message"],
    ])
    def test_unsupported_messages_are_invalid_before_http(self, messages):
        result, seen, _ = run(gateway_config(), ok(), messages=messages, prompt=None)
        assert result["metadata"]["error_class"] == "invalid_request"
        assert seen == []

    def test_missing_prompt_is_invalid_before_http(self):
        result, seen, _ = run(gateway_config(), ok(), prompt=None)
        assert result["metadata"]["error_class"] == "invalid_request"
        assert seen == []


class TestWorkflowCannotChangePolicy:
    @pytest.mark.parametrize("option", [
        "search_recency_filter", "search_domain_filter", "web_search_options",
        "return_related_questions", "tools", "response_format", "disable_search",
    ])
    def test_unsupported_search_options_are_refused_by_name(self, option):
        result, seen, _ = run(gateway_config(), ok(), **{option: "week"})
        assert result["metadata"]["error_class"] == "unsupported_option"
        assert option in result["message"]
        assert seen == []

    def test_nested_params_option_is_refused_too(self):
        result, seen, _ = run(gateway_config(), ok(), params={"search_domain_filter": ["a.invalid"]})
        assert result["metadata"]["error_class"] == "unsupported_option"
        assert seen == []

    @pytest.mark.parametrize("field", ["provider_options", "providerOptions", "extra_body", "zero_data_retention", "byok"])
    def test_gateway_policy_fields_are_refused(self, field):
        result, seen, _ = run(gateway_config(), ok(), **{field: {"gateway": {"models": ["x"]}}})
        assert result["metadata"]["error_class"] == "unsupported_option"
        assert seen == []

    def test_workflow_credential_is_refused(self):
        result, seen, _ = run(gateway_config(), ok(), api_key="vck-workflow-supplied")
        assert result["metadata"]["error_class"] == "policy_credential_not_allowed"
        assert seen == []
        assert "vck-workflow-supplied" not in json.dumps(result, default=str)

    def test_workflow_endpoint_is_refused(self):
        result, seen, _ = run(gateway_config(), ok(), base_url="https://api.perplexity.ai")
        assert result["metadata"]["error_class"] == "policy_endpoint_not_allowed"
        assert seen == []

    def test_missing_credential_blocks_even_with_ambient_keys(self):
        config = gateway_config()
        del config["providers"]["vercel_gateway"]["credential"]
        env = {"OPENAI_API_KEY": "sk-ambient", "TEMP_CONTEXT_VARIABLE_PERPLEXITY_API_KEY": "pplx-ambient"}
        with patch.dict("os.environ", env, clear=True):
            result, seen, _ = run(config, ok())
        assert result["metadata"]["error_class"] == "credential_missing"
        assert seen == []


class TestCitations:
    def test_source_parts_become_citations_with_marker_indices(self):
        body = native([source(1, A, "Synthetic A"), source(2, "javascript:alert(1)"), source(3, B, None),
                       source(4, "https://user@c.invalid/x"), source(5, C), text("Answer [1][3][5].")])
        result, _, _ = run(gateway_config(), ok(body))
        data = result["data"]
        assert data["content"] == "Answer [1][3][5]."
        assert data["citations"] == [
            {"url": A, "title": "Synthetic A", "citation_index": 1},
            {"url": B, "title": "", "citation_index": 3},
            {"url": C, "title": "Synthetic", "citation_index": 5},
        ]
        assert data["provider_extensions"]["citation_source"] == "source_parts"

    @pytest.mark.parametrize("marker", [None, "", "0", "-1", "a1", "1.5", "\u0661", 0, True, 2.0, ["1"]])
    def test_non_positive_integer_ids_get_no_invented_index(self, marker):
        part = {**source(1, A), "id": marker}
        result, _, _ = run(gateway_config(), ok(native([part, text("x")])))
        assert result["data"]["citations"] == [{"url": A, "title": "Synthetic"}]

    def test_non_url_and_malformed_parts_are_ignored(self):
        body = native([
            {"type": "source", "sourceType": "document", "id": "1", "url": A, "title": "doc"},
            {"type": "reasoning", "text": "hidden"},
            {"type": "tool-call", "toolName": "search_web"},
            "garbage", None, 3,
            source(2, B),
            text("x"),
        ])
        result, _, _ = run(gateway_config(), ok(body))
        assert result["data"]["citations"] == [{"url": B, "title": "Synthetic", "citation_index": 2}]

    def test_no_sources_means_none_never_derived_from_answer_text(self):
        result, _, _ = run(gateway_config(), ok(native([text(f"See {A} and {B}.")])))
        assert result["status"] is True
        assert result["data"]["citations"] == []
        assert result["data"]["provider_extensions"]["citation_source"] == "none"

    def test_openai_compatible_fields_are_not_read(self):
        body = native([text("x")], citations=[A], search_results=[{"url": B}],
                      choices=[{"message": {"annotations": [{"type": "url_citation", "url": C}]}}])
        result, _, _ = run(gateway_config(), ok(body))
        assert result["data"]["citations"] == []

    def test_multiple_text_parts_are_joined_in_order(self):
        result, _, _ = run(gateway_config(), ok(native([text("one "), source(1, A), text("two")])))
        assert result["data"]["content"] == "one two"


class TestAnswerFailures:
    @pytest.mark.parametrize("body", [
        native([text("")]),
        native([text("   ")]),
        native([source(1, A)]),
        native([]),
        native([{"type": "text", "text": None}]),
        native(content="not a list"),
        {"choices": [{"message": {"content": "an OpenAI-shaped body"}, "finish_reason": "stop"}]},
        {"not": "a result"},
    ])
    def test_empty_or_unusable_answer_is_bad_response(self, body):
        result, _, _ = run(gateway_config(), ok(body))
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "provider_bad_response"
        assert result["data"] is None

    @pytest.mark.parametrize("finish", [{"unified": "length", "raw": "length"}, "length", {"unified": "error"},
                                        {"unified": "tool-calls"}, None, {}])
    def test_non_stop_finish_is_bad_response(self, finish):
        result, _, _ = run(gateway_config(), ok(native(finishReason=finish)))
        assert result["metadata"]["error_class"] == "provider_bad_response"

    def test_plain_string_stop_is_accepted(self):
        result, _, _ = run(gateway_config(), ok(native(finishReason="stop")))
        assert result["status"] is True

    @pytest.mark.parametrize("finish", [{"unified": "content-filter", "raw": "x"}, "content-filter"])
    def test_content_filter_is_content_rejected_without_echo(self, finish):
        body = native([text("I cannot help with that.")], finishReason=finish)
        result, _, _ = run(gateway_config(), ok(body))
        assert result["metadata"]["error_class"] == "provider_content_rejected"
        assert "I cannot help" not in json.dumps(result, default=str)

    @pytest.mark.parametrize("status,error_class", [
        (401, "provider_authentication"),
        (403, "provider_authentication"),
        (429, "provider_rate_limited"),
        (503, "provider_unavailable"),
        (400, "invalid_request"),
    ])
    def test_http_errors_are_typed(self, status, error_class):
        error = {"error": {"message": "synthetic", "type": "no_providers_available"}}
        result, seen, vertex = run(gateway_config(), ok(error, status=status))
        assert result["status"] is False
        assert result["metadata"]["error_class"] == error_class
        assert len(seen) == 1  # the SDK never retries on its own
        assert vertex.calls == []
        assert SECRET not in json.dumps(result, default=str)

    def test_timeout_is_typed(self):
        httpx = pytest.importorskip("httpx")
        result, seen, vertex = run(gateway_config(), lambda request: httpx.ReadTimeout("synthetic", request=request))
        assert result["metadata"]["error_class"] == "provider_timeout"
        assert len(seen) == 1 and vertex.calls == []


class TestNoSilentFallback:
    PROFILE = {"adidas_research_search": {"search_answer": [{"provider": "vercel_gateway", "model": MODEL}]}}

    def test_profile_routes_to_the_gateway(self):
        result, [request], vertex = run(gateway_config(profiles=self.PROFILE), ok(), profile="adidas_research_search")
        assert result["status"] is True
        assert result["metadata"]["route_reason"] == "profile:adidas_research_search"
        assert request.url.host == "ai-gateway.vercel.sh"
        assert vertex.calls == []

    def test_failed_gateway_does_not_fall_back_to_vertex(self):
        result, seen, vertex = run(gateway_config(profiles=self.PROFILE), ok(status=503), profile="adidas_research_search")
        assert result["metadata"]["error_class"] == "provider_unavailable"
        assert result["metadata"]["fallback_used"] is False
        assert len(seen) == 1 and vertex.calls == []

    def test_missing_credential_with_single_entry_profile_fails_typed(self):
        config = gateway_config(profiles=self.PROFILE)
        del config["providers"]["vercel_gateway"]["credential"]
        with patch.dict("os.environ", {}, clear=True):
            result, seen, vertex = run(config, ok(), profile="adidas_research_search")
        assert result["metadata"]["error_class"] == "credential_missing"
        assert seen == [] and vertex.calls == []

    def test_zdr_route_never_falls_back_even_when_one_is_configured(self):
        config = gateway_config(zdr=True, profiles=self.PROFILE)
        config["fallbacks"] = {"search_answer": {"vercel_gateway": [{"provider": "vertex_ai", "model": "gemini-3.5-flash-lite"}]}}
        result, seen, vertex = run(config, ok(status=503), profile="adidas_research_search")
        assert result["metadata"]["error_class"] == "provider_unavailable"
        assert vertex.calls == []


class TestReceipt:
    def test_receipt_separates_gateway_from_reported_upstream(self):
        body = native(providerMetadata={"gateway": {
            "generationId": "gen-synthetic-1",
            "billableWebSearchCalls": 1,
            "routing": {"finalProvider": "perplexity", "canonicalSlug": "perplexity/sonar-upstream-reported"},
        }})
        result, _, _ = run(gateway_config(), ok(body))
        metadata = result["metadata"]
        assert metadata["selected_provider"] == "vercel_gateway"
        assert metadata["selected_model"] == MODEL
        assert metadata["provider_request_id"] == "gen-synthetic-1"
        assert metadata["usage"] == {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12,
                                     "web_search_calls": 1}
        assert metadata["gateway"] == {
            "backend": "vercel_ai_gateway",
            "zdr_effective": "unknown",
            "upstream_provider": "perplexity",
            "upstream_model": "perplexity/sonar-upstream-reported",
        }
        receipt = result["data"]["provider_extensions"]["router_receipt"]
        assert receipt["selected_provider"] == "vercel_gateway"
        assert receipt["selected_model"] == MODEL
        assert receipt["zdr_mode"] == "not_requested"
        assert receipt["gateway"] == metadata["gateway"]
        assert SECRET not in json.dumps(result, default=str)

    def test_response_model_id_wins_over_the_routing_slug(self):
        body = native(response={"id": "resp-1", "modelId": "perplexity/sonar-2"},
                      providerMetadata={"gateway": {"routing": {"canonicalSlug": "perplexity/sonar"}}})
        result, _, _ = run(gateway_config(), ok(body))
        assert result["metadata"]["gateway"]["upstream_model"] == "perplexity/sonar-2"
        assert result["metadata"]["provider_request_id"] == "resp-1"

    @pytest.mark.parametrize("usage", [None, "x", {}, {"inputTokens": "5"}, {"inputTokens": {"total": None}}])
    def test_unreported_upstream_and_usage_stay_unknown(self, usage):
        body = native(usage=usage, providerMetadata=None)
        result, _, _ = run(gateway_config(), ok(body))
        assert result["metadata"]["usage"] is None
        assert result["metadata"]["provider_request_id"] is None
        assert result["metadata"]["gateway"]["upstream_provider"] is None
        assert result["metadata"]["gateway"]["upstream_model"] is None

    def test_spec_v2_integer_usage_is_read(self):
        result, _, _ = run(gateway_config(), ok(native(usage={"inputTokens": 3, "outputTokens": 4})))
        assert result["metadata"]["usage"]["total_tokens"] == 7


class TestUnchangedRoutes:
    def test_direct_perplexity_adapter_stays_dormant_and_separate(self):
        conf = router.DEFAULT_CONFIG["providers"]["perplexity"]
        assert conf["enabled"] is False
        assert conf["endpoint"] == "https://api.perplexity.ai"

    def test_default_search_still_goes_to_vertex(self):
        vertex = FakeAdapter()
        result = router.invoke_search({"_runtime": FakeRuntime(adapters={"vertex_ai": vertex}), "prompt": "q"})
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert "gateway" not in result["metadata"]


class TestInactiveExample:
    EXAMPLE = router.Path(__file__).resolve().parents[1] / "examples" / "perplexity-gateway-search.disabled.json"

    def test_example_is_disabled_single_entry_and_refuses_before_http(self):
        example = json.loads(self.EXAMPLE.read_text())
        assert example["providers"]["vercel_gateway"]["enabled"] is False
        assert example["profiles"]["perplexity_gateway_search"] == {"search_answer": [{"provider": "vercel_gateway", "model": MODEL}]}
        with patch.dict("os.environ", {}, clear=True):
            result, seen, vertex = run(example, ok(), profile="perplexity_gateway_search")
        assert result["metadata"]["error_class"] == "policy_provider_not_allowed"
        assert seen == [] and vertex.calls == []
