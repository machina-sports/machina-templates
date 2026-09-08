"""SDK retries must not multiply the router's selected timeout/retry policy."""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from test_router import FakeAdapter, FakeRuntime, TestProviderAdapters as _AdapterFixture, router


@pytest.mark.parametrize("adapter_class", [router.OpenAICompatibleAdapter, router.XAIAdapter])
def test_sdk_client_and_factory_do_not_add_hidden_retries(adapter_class):
    fixture = _AdapterFixture()
    adapter = adapter_class(router.RuntimeFacade(), router.MediaSecurity({}))
    constructor = MagicMock(return_value=object())
    with patch.dict("sys.modules", {"openai": SimpleNamespace(OpenAI=constructor)}):
        adapter._client(fixture.route())
    assert constructor.call_args.kwargs["max_retries"] == 0
    assert constructor.call_args.kwargs["timeout"] == 1
    assert adapter._chat_kwargs(fixture.route(), fixture.request())["max_retries"] == 0


def test_primary_and_fallback_receive_only_remaining_deadline_budget():
    clock = [0.0]
    class SlowFailure(FakeAdapter):
        def invoke_chat(self, route, request):
            self.routes.append(route)
            clock[0] += 0.15
            raise router.RouterError("provider_timeout", "timed out", transient=True)
    primary, fallback = SlowFailure(), FakeAdapter()
    runtime = FakeRuntime(config={
        "policy": {"total_deadline_ms": 250},
        "providers": {"groq": {"enabled": True, "allowed_models": {"chat": ["groq-chat"]}, "credential": "test-only"}},
        "fallbacks": {"chat": {"vertex_ai": [{"provider": "groq", "model": "groq-chat"}]}},
    }, adapters={"vertex_ai": primary, "groq": fallback})
    with patch.object(router.time, "monotonic", lambda: clock[0]):
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello"})
    assert result["status"] is True
    assert 0 < primary.routes[0].timeout_ms <= 250
    assert 0 < fallback.routes[0].timeout_ms <= 100
    assert primary.routes[0].timeout_ms == 250  # Previous route was not mutated.


def test_provider_return_after_deadline_is_not_reported_as_timely_success():
    clock = [0.0]
    class LateSuccess(FakeAdapter):
        def invoke_chat(self, route, request):
            clock[0] += 2
            return super().invoke_chat(route, request)
    runtime = FakeRuntime(config={"policy": {"total_deadline_ms": 1000}},
                          adapters={"vertex_ai": LateSuccess()})
    with patch.object(router.time, "monotonic", lambda: clock[0]):
        result = router.invoke_chat({"_runtime": runtime, "prompt": "hello"})
    assert result["status"] is False
    assert result["metadata"]["error_class"] == "provider_timeout"
