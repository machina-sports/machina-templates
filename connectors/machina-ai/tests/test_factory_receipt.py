"""Factory-mode receipts must not pass model construction off as inference.

`invoke_prompt` (and factory `invoke_embedding`) return a model object; the
receipt is written before any inference. Client API merges that receipt into
the prompt task's metadata, so an inference-shaped `latency_ms`/`usage` there
would be read as the cost of the model call.
"""
import pytest
from test_router import FakeAdapter, FakeRuntime, router


def fallback_runtime(primary, fallback):
    return FakeRuntime(config={
        "providers": {"groq": {"enabled": True, "allowed_models": {"chat": ["groq-chat"]}, "credential": "test-only"}},
        "fallbacks": {"chat": {"vertex_ai": [{"provider": "groq", "model": "groq-chat"}]}},
    }, adapters={"vertex_ai": primary, "groq": fallback})


@pytest.mark.parametrize("command,params", [
    ("invoke_prompt", {}),
    ("invoke_embedding", {"operation_mode": "factory"}),
])
def test_factory_receipt_reports_construction_not_inference(command, params):
    result = getattr(router, command)({"_runtime": FakeRuntime(), **params})
    metadata = result["metadata"]
    assert result["status"] is True
    assert metadata["operation_mode"] == "factory"
    assert metadata["resolved_route"]["operation_mode"] == "factory"
    assert isinstance(metadata["construction_latency_ms"], int)
    assert "latency_ms" not in metadata
    # The fake adapter reports usage; a factory receipt still must not.
    assert "usage" not in metadata


def test_execute_receipt_is_unchanged():
    result = router.invoke_chat({"_runtime": FakeRuntime(), "prompt": "hello"})
    metadata = result["metadata"]
    assert metadata["operation_mode"] == "execute"
    assert isinstance(metadata["latency_ms"], int)
    assert metadata["usage"] == {"total_tokens": 3}
    assert "construction_latency_ms" not in metadata


def test_factory_failure_receipt_reports_construction():
    adapter = FakeAdapter({"create_chat_model": router.RouterError("invalid_request", "bad")})
    result = router.invoke_prompt({"_runtime": FakeRuntime(adapters={"vertex_ai": adapter})})
    metadata = result["metadata"]
    assert result["status"] is False
    assert metadata["operation_mode"] == "factory"
    assert "latency_ms" not in metadata and "usage" not in metadata
    assert isinstance(metadata["construction_latency_ms"], int)


def test_factory_fallback_attempts_report_construction():
    primary = FakeAdapter({"create_chat_model": router.RouterError("provider_unavailable", "down")})
    result = router.invoke_prompt({"_runtime": fallback_runtime(primary, FakeAdapter())})
    metadata = result["metadata"]
    assert metadata["fallback_used"] is True
    [attempt] = metadata["fallback_attempts"]
    assert attempt["provider"] == "vertex_ai"
    assert "latency_ms" not in attempt
    assert isinstance(attempt["construction_latency_ms"], int)


def test_execute_fallback_attempts_keep_latency():
    primary = FakeAdapter({"invoke_chat": router.RouterError("provider_unavailable", "down")})
    result = router.invoke_chat({"_runtime": fallback_runtime(primary, FakeAdapter()), "prompt": "hello"})
    [attempt] = result["metadata"]["fallback_attempts"]
    assert isinstance(attempt["latency_ms"], int)
    assert "construction_latency_ms" not in attempt


def test_request_level_failure_before_routing_keeps_shape():
    # Normalization fails before a mode exists; nothing to relabel.
    result = router.invoke_embedding({"_runtime": FakeRuntime(), "operation_mode": "bogus"})
    assert result["status"] is False
    assert "latency_ms" in result["metadata"]
