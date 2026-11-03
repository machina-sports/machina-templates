"""Perplexity Sonar search readiness: dormant by default, canonical POST /v1/sonar.

Offline only. Wire tests drive the real `openai` SDK through an httpx mock
transport; no network call, no real credential. Every response body below is a
SYNTHETIC fixture shaped after the published Sonar `CompletionResponse` schema
(docs.perplexity.ai/openapi.json), not captured provider output. URLs use the
reserved `.invalid` TLD.
"""
import copy
import functools
import json
from unittest.mock import patch

import pytest
from test_router import CONNECTOR_DIR, FakeAdapter, FakeRuntime, router

SECRET = "pplx-test-only-not-a-real-key"
A = "https://a.invalid/1"
B = "https://b.invalid/2"
C = "https://c.invalid/3"
EXAMPLE = CONNECTOR_DIR / "examples" / "perplexity-search.disabled.json"


def expected_body(model="sonar"):
    # The whole wire payload: fixed fields only, no caller option pass-through.
    return {
        "model": model,
        "messages": [{"role": "user", "content": "synthetic question"}],
        "stream": False,
        "disable_search": False,
        "enable_search_classifier": False,
    }


def sonar_response(**overrides):
    """SYNTHETIC Sonar response body (schema-shaped, not real provider output)."""
    body = {
        "id": "synthetic-req-1",
        "model": "sonar",
        "created": 0,
        "object": "chat.completion",
        "choices": [{
            "index": 0,
            "finish_reason": "stop",
            "message": {"role": "assistant", "content": "Synthetic answer [1][2][3]."},
            "delta": {"role": "assistant", "content": ""},
        }],
        "citations": [A, B, C],
        "search_results": [
            # Near-miss URL first: titles must match by exact URL only.
            {"url": A + "/", "title": "Wrong near-match", "snippet": "", "source": "web"},
            {"url": B, "title": "Synthetic B", "date": None, "snippet": "", "source": "web"},
            {"url": A, "title": "Synthetic A", "date": "2026-01-01", "snippet": "", "source": "web"},
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12,
                  "search_context_size": "low", "cost": {"total_cost": 0}},
    }
    body.update(overrides)
    return body


def enabled_config(**provider_extra):
    # Only enable + credential: allowlist, endpoint and require_credential must
    # come from the shipped DEFAULT_CONFIG.
    return {"providers": {"perplexity": {"enabled": True, "credential": SECRET, **provider_extra}}}


def run_search(config, respond, **params):
    """Invoke the router with the real OpenAI SDK over an httpx MockTransport."""
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
    runtime = FakeRuntime(config=config, adapters={"vertex_ai": vertex})
    client = functools.partial(openai.OpenAI, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    with patch.object(openai, "OpenAI", client):
        result = router.invoke_search({
            "_runtime": runtime, "provider": "perplexity", "model": "sonar",
            "prompt": "synthetic question", **params,
        })
    return result, seen, vertex


def ok(body=None):
    httpx = pytest.importorskip("httpx")
    return lambda request: httpx.Response(200, json=sonar_response() if body is None else body)


class TestDormantByDefault:
    def test_provider_ships_disabled_credential_gated_with_sonar_search_allowlist(self):
        conf = router.DEFAULT_CONFIG["providers"]["perplexity"]
        assert conf["enabled"] is False
        assert conf["require_credential"] is True
        assert conf["endpoint"] == "https://api.perplexity.ai"
        assert conf["allowed_models"]["search_answer"] == ["sonar", "sonar-pro"]
        assert conf["allowed_models"]["chat"] == []

    def test_no_default_profile_or_fallback_routes_to_perplexity(self):
        config = router.DEFAULT_CONFIG
        routed = json.dumps([config["defaults"], config["profiles"], config["fallbacks"], config["remaps"]])
        assert "perplexity" not in routed
        assert config["defaults"]["search_answer"] == {"provider": "vertex_ai", "model": "gemini-3.5-flash-lite"}
        assert [c["provider"] for c in config["profiles"]["live_search"]["search_answer"]] == ["xai", "vertex_ai"]

    def test_disabled_provider_blocks_before_http(self):
        result, seen, _ = run_search({}, ok())
        assert result["metadata"]["error_class"] == "policy_provider_not_allowed"
        assert seen == []

    def test_inactive_example_stays_disabled_and_does_not_route(self):
        example = json.loads(EXAMPLE.read_text())
        conf = example["providers"]["perplexity"]
        assert conf["enabled"] is False
        assert conf["allowed_models"]["chat"] == []
        assert example["profiles"] == {
            "perplexity_search": {"search_answer": [{"provider": "perplexity", "model": "sonar"}]},
        }
        assert set(example) <= {"providers", "profiles", "profile_intents"}
        # Applied as-is it still refuses before any HTTP and never falls back.
        with patch.dict("os.environ", {}, clear=True):
            result, seen, vertex = run_search(example, ok(), provider=None, profile="perplexity_search")
        assert result["metadata"]["error_class"] == "policy_provider_not_allowed"
        assert seen == [] and vertex.calls == []


class TestPolicyBeforeHttp:
    def test_missing_credential_blocks_even_with_ambient_openai_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-ambient-test-only"}, clear=True):
            result, seen, _ = run_search({"providers": {"perplexity": {"enabled": True}}}, ok())
        assert result["metadata"]["error_class"] == "credential_missing"
        assert seen == []
        assert "sk-ambient-test-only" not in json.dumps(result, default=str)

    @pytest.mark.parametrize("model", ["sonar-deep-research", "sonar-reasoning-pro", "gpt-4o"])
    def test_model_outside_allowlist_blocked(self, model):
        result, seen, _ = run_search(enabled_config(), ok(), model=model)
        assert result["metadata"]["error_class"] == "policy_model_not_allowed"
        assert seen == []

    def test_endpoint_override_blocked(self):
        result, seen, _ = run_search(enabled_config(), ok(), base_url="https://evil.invalid")
        assert result["metadata"]["error_class"] == "policy_endpoint_not_allowed"
        assert seen == []

    def test_generic_chat_is_not_claimed(self):
        runtime = FakeRuntime(config=enabled_config())
        result = router.invoke_chat({"_runtime": runtime, "provider": "perplexity", "model": "sonar", "prompt": "hi"})
        assert result["metadata"]["error_class"] == "unsupported_capability"


class TestSonarWire:
    def test_canonical_post_payload_timeout_and_no_sdk_retries(self):
        result, seen, _ = run_search(enabled_config(), ok(), timeout_ms=12000)
        assert result["status"] is True
        [request] = seen
        assert request.method == "POST"
        assert str(request.url) == "https://api.perplexity.ai/v1/sonar"
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        assert request.extensions["timeout"]["read"] == 12.0
        assert json.loads(request.content) == expected_body()

    def test_sonar_pro_selected_through_router_without_route_changes(self):
        result, seen, _ = run_search(enabled_config(), ok(sonar_response(model="sonar-pro")), model="sonar-pro")
        assert result["status"] is True
        assert result["metadata"]["selected_model"] == "sonar-pro"
        assert result["metadata"]["route_reason"] == "explicit_provider"
        [request] = seen
        assert json.loads(request.content) == expected_body("sonar-pro")

    def test_unmodeled_caller_fields_are_ignored_not_forwarded(self):
        # The normalizer does not carry these into the adapter; nothing reaches the wire.
        result, seen, _ = run_search(
            enabled_config(), ok(),
            extra_body={"disable_search": True},
            options={"provider_options": {"x": 1}, "disable_search": True, "api_key": "smuggled"},
        )
        assert result["status"] is True
        [request] = seen
        assert json.loads(request.content) == expected_body()
        assert request.headers["authorization"] == f"Bearer {SECRET}"
        assert "smuggled" not in request.content.decode()


class TestNormalization:
    def test_answer_id_usage_and_citations_in_citation_order_with_exact_url_titles(self):
        result, _, _ = run_search(enabled_config(), ok())
        data = result["data"]
        assert data["content"] == "Synthetic answer [1][2][3]."
        assert data["citations"] == [
            {"url": A, "title": "Synthetic A", "citation_index": 1},
            {"url": B, "title": "Synthetic B", "citation_index": 2},
            {"url": C, "title": "", "citation_index": 3},
        ]
        assert result["metadata"]["provider_request_id"] == "synthetic-req-1"
        assert result["metadata"]["usage"]["total_tokens"] == 12

    def test_absent_usage_stays_unknown(self):
        body = sonar_response()
        del body["usage"]
        result, _, _ = run_search(enabled_config(), ok(body))
        assert result["status"] is True
        assert result["metadata"]["usage"] is None

    def test_without_citations_uses_valid_web_search_results_in_order(self):
        bad = [
            "ftp://x.invalid/a", "https://", "https://user:pw@x.invalid/a",
            "https://x.invalid:99999/a", "https://bad host.invalid/a", "javascript:alert(1)", "",
        ]
        results = [{"url": B, "title": "Synthetic B", "source": "web"}]
        results += [{"url": url, "title": "Malformed", "source": "web"} for url in bad]
        results += [{"url": "https://attach.invalid/f", "title": "Attachment", "source": "attachment"}]
        results += [{"url": A, "title": "Synthetic A"}, {"url": C}]
        result, _, _ = run_search(enabled_config(), ok(sonar_response(citations=None, search_results=results)))
        assert result["data"]["citations"] == [
            {"url": B, "title": "Synthetic B"},
            {"url": A, "title": "Synthetic A"},
            {"url": C, "title": ""},
        ]

    def test_sources_are_never_invented_from_answer_text(self):
        choices = [{"index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "See https://invented.invalid/x"},
                    "delta": {"role": "assistant", "content": ""}}]
        body = sonar_response(choices=choices, citations=[], search_results=[])
        result, _, _ = run_search(enabled_config(), ok(body))
        assert result["status"] is True
        assert result["data"]["citations"] == []

    def test_duplicate_citations_keep_marker_order_and_attachments_are_not_web_evidence(self):
        att = "https://attach.invalid/f"
        results = [
            {"url": A, "title": "Synthetic A", "source": "web"},
            {"url": att, "title": "Attachment", "source": "attachment"},
        ]
        body = sonar_response(citations=[A, B, A, att, "not a url"], search_results=results)
        result, _, _ = run_search(enabled_config(), ok(body))
        assert result["data"]["citations"] == [
            {"url": A, "title": "Synthetic A", "citation_index": 1},
            {"url": B, "title": "", "citation_index": 2},
            {"url": A, "title": "Synthetic A", "citation_index": 3},
        ]

    def test_filtered_citations_keep_original_marker_indices(self):
        body = sonar_response(citations=["https://?bad", A, "https://attach.invalid/f", B], search_results=[
            {"url": A, "title": "Synthetic A"},
            {"url": "https://attach.invalid/f", "title": "Attachment", "source": "attachment"}])
        result, _, _ = run_search(enabled_config(), ok(body))
        assert result["data"]["citations"] == [
            {"url": A, "title": "Synthetic A", "citation_index": 2},
            {"url": B, "title": "", "citation_index": 4}]

    def test_receipt_records_requested_route_not_server_model(self):
        result, _, _ = run_search(enabled_config(), ok(sonar_response(model="sonar-pro")))
        assert result["metadata"]["selected_model"] == "sonar"
        assert result["metadata"]["resolved_route"]["model"] == "sonar"
        extensions = result["data"]["provider_extensions"]
        assert extensions["provider_model"] == "sonar-pro"
        assert extensions["router_receipt"]["selected_provider"] == "perplexity"
        assert extensions["router_receipt"]["selected_model"] == "sonar"
        assert SECRET not in json.dumps(result, default=str)


def _choice(**message_or_reason):
    choice = {"index": 0, "finish_reason": "stop",
              "message": {"role": "assistant", "content": "x"},
              "delta": {"role": "assistant", "content": ""}}
    if "finish_reason" in message_or_reason:
        choice["finish_reason"] = message_or_reason.pop("finish_reason")
    choice["message"].update(message_or_reason)
    return [choice]


class TestBadResponses:
    @pytest.mark.parametrize("overrides", [
        {"choices": []},
        {"choices": _choice(content=None)},
        {"choices": _choice(content="")},
        {"choices": _choice(content="   ")},
        {"choices": _choice(finish_reason="length")},
    ], ids=["no-choices", "null-content", "empty-content", "blank-content", "truncated"])
    def test_no_fabricated_success(self, overrides):
        result, _, _ = run_search(enabled_config(), ok(sonar_response(**copy.deepcopy(overrides))))
        assert result["status"] is False
        assert result["data"] is None
        assert result["metadata"]["error_class"] == "provider_bad_response"

    def test_missing_choices_key(self):
        body = sonar_response()
        del body["choices"]
        result, _, _ = run_search(enabled_config(), ok(body))
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "provider_bad_response"

    # Sonar documents finish_reason stop|length only; these OpenAI-compatible
    # refusal shapes are SYNTHETIC and handled defensively.
    @pytest.mark.parametrize("overrides", [
        {"choices": _choice(finish_reason="content_filter")},
        {"choices": _choice(content="", refusal="synthetic refusal text")},
    ], ids=["content-filter", "refusal"])
    def test_refusal_is_content_rejected_without_echo(self, overrides):
        result, _, _ = run_search(enabled_config(), ok(sonar_response(**copy.deepcopy(overrides))))
        assert result["status"] is False
        assert result["data"] is None
        assert result["metadata"]["error_class"] == "provider_content_rejected"
        assert "synthetic refusal text" not in json.dumps(result, default=str)


class TestProviderErrors:
    @pytest.mark.parametrize("status,error_class", [
        (401, "provider_authentication"),
        (429, "provider_rate_limited"),
        (503, "provider_unavailable"),
        ("timeout", "provider_timeout"),
    ])
    def test_typed_once_without_sdk_retry_or_fallback(self, status, error_class):
        httpx = pytest.importorskip("httpx")

        def respond(request):
            if status == "timeout":
                return httpx.ReadTimeout("synthetic timeout", request=request)
            return httpx.Response(status, json={"error": {"message": f"synthetic {status}"}})

        result, seen, vertex = run_search(enabled_config(), respond)
        assert result["status"] is False
        assert result["metadata"]["error_class"] == error_class
        assert len(seen) == 1
        assert result["metadata"]["fallback_used"] is False
        assert vertex.calls == []
        assert SECRET not in json.dumps(result, default=str)
