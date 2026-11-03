"""Cross-feature regressions where live inference controls meet the merged router.

Each test covers an interaction no single-feature suite exercises: vault-bound
Vertex with ZDR profile selection, gateway extensions through the shared plan
runner, governed inference receipts against factory receipts, and SDK retry
ownership only where the router actually governs inference. Offline only.
"""
from unittest.mock import patch

from test_google_prompt_budget import DelegateRuntime, FakeVertexSDK, InProcessRuntime, _Patched
from test_router import FakeAdapter, VaultRuntime, router, vault_bound_config

GATEWAY_MODEL = "anthropic/claude-sonnet-4.5"


def zdr_gateway(**extra):
    return {"enabled": True, "zero_data_retention": True, "allowed_models": {"chat": [GATEWAY_MODEL]}, **extra}


def test_zdr_candidate_missing_credential_does_not_fall_through_to_vault_bound_vertex():
    vertex = FakeAdapter()
    runtime = VaultRuntime(
        config=vault_bound_config(
            providers={"vercel_gateway": zdr_gateway()},
            profiles={"private": {"chat": [
                {"provider": "vercel_gateway", "model": GATEWAY_MODEL},
                {"provider": "vertex_ai", "model": "gemini-3.5-flash-lite"},
            ]}},
        ),
        adapters={"vertex_ai": vertex},
    )
    with patch.dict("os.environ", {}, clear=True):
        result = router.invoke_chat({"_runtime": runtime, "profile": "private", "prompt": "hi"})
    assert result["status"] is False
    assert result["metadata"]["error_class"] == "credential_missing"
    assert runtime.auth_calls == []
    assert vertex.calls == []


def test_vault_bound_vertex_ahead_of_zdr_gateway_resolves_lazily_once():
    vertex = FakeAdapter()
    runtime = VaultRuntime(
        config=vault_bound_config(
            providers={"vercel_gateway": zdr_gateway(credential="test-only")},
            profiles={"private": {"chat": [
                {"provider": "vertex_ai", "model": "gemini-3.5-flash-lite"},
                {"provider": "vercel_gateway", "model": GATEWAY_MODEL},
            ]}},
        ),
        adapters={"vertex_ai": vertex},
    )
    with patch.dict("os.environ", {}, clear=True):
        result = router.invoke_chat({"_runtime": runtime, "profile": "private", "prompt": "hi"})
    assert result["status"] is True
    assert result["metadata"]["selected_provider"] == "vertex_ai"
    assert runtime.auth_calls == [((), {})]
    assert "zdr_mode" not in result["metadata"]


class ExtensionsAdapter(FakeAdapter):
    def invoke_chat(self, route, request):
        result = super().invoke_chat(route, request)
        result.extensions = {"upstream_model": "upstream/actual-model", "cache": "hit"}
        return result


def test_plan_runner_keeps_gateway_upstream_model_and_other_extensions():
    config = {"providers": {"vercel_gateway": zdr_gateway(credential="test-only")}}
    runtime = VaultRuntime(config=config, adapters={"vercel_gateway": ExtensionsAdapter()})
    result = router.invoke_chat({"_runtime": runtime, "provider": "vercel_gateway", "model": GATEWAY_MODEL, "prompt": "hi"})
    metadata = result["metadata"]
    assert result["status"] is True
    assert metadata["zdr_mode"] == "requested"
    assert metadata["gateway"]["upstream_model"] == "upstream/actual-model"
    assert metadata["provider_extensions"] == {"cache": "hit"}
    assert runtime.auth_calls == []


def test_governed_inference_receipt_reports_inference_not_construction(monkeypatch):
    monkeypatch.delenv("TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL", raising=False)
    monkeypatch.delenv("TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID", raising=False)
    clock = [0.0]
    # Binary-exact costs so integer millisecond receipts are deterministic.
    sdk = FakeVertexSDK(clock, [(0.5, "answer")], setup_s=0.125)
    runtime = InProcessRuntime({"policy": {"total_deadline_ms": 1000}})
    with _Patched(sdk, clock):
        result = router.invoke_prompt({"_runtime": runtime, "provider": "vertex_ai", "model": "gemini-3.8-flash"})
        factory = result["data"]
        assert factory.invoke("hello") == "answer"
    # The factory receipt stays a construction receipt (#413).
    assert "latency_ms" not in result["metadata"]
    assert "usage" not in result["metadata"]
    assert result["metadata"]["construction_latency_ms"] == 125
    # The governed receipt times the real call: refresh 125ms + inference 500ms.
    receipt = factory.get_inference_receipt()
    assert receipt["execution_phase"] == "inference"
    assert receipt["latency_ms"] == 625
    assert "construction_latency_ms" not in receipt
    assert receipt["usage"] is None


def test_ungoverned_ai_studio_prompt_keeps_sdk_retry_default():
    runtime = DelegateRuntime({"providers": {"google_ai_studio": {
        "enabled": True, "credential": "test-only", "allowed_models": {"chat": ["gemini-2.5-flash"]},
    }}})
    with patch.object(router.time, "monotonic", lambda: 0.0):
        result = router.invoke_prompt({"_runtime": runtime, "provider": "google_ai_studio",
                                       "model": "gemini-2.5-flash", "timeout_ms": 20000})
    assert result["status"] is True
    _, payload = runtime.payloads[-1]
    assert payload["params"]["timeout"] == 20.0
    assert "max_retries" not in payload["params"]
