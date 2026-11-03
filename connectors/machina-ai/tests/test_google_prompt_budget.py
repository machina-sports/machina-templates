"""Google prompt factories must carry the router's effective budget, not their own."""
import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from test_router import router

SAMPLING_DEFAULTS = ("temperature", "top_p", "top_k")


@pytest.fixture(autouse=True)
def no_ambient_vertex_env(monkeypatch):
    monkeypatch.delenv("TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL", raising=False)
    monkeypatch.delenv("TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID", raising=False)


class DelegateRuntime:
    """No injected adapters, so the built-in Google adapter delegates here."""

    def __init__(self, config=None, on_delegate=None):
        self._config = config or {}
        self.on_delegate = on_delegate
        self.payloads = []

    def config(self, key=None):
        return self._config

    def adapter(self, provider):
        return None

    def delegate(self, connector, request_data=None, command=None):
        assert connector == "google-genai"
        self.payloads.append((command, request_data))
        if self.on_delegate:
            return self.on_delegate()
        return {"status": True, "data": "vertex-chat", "metadata": {}}


class InProcessRuntime:
    """No injected adapters and no delegate, so Vertex is built in-process."""

    def __init__(self, config=None):
        self._config = config or {}

    def config(self, key=None):
        return self._config

    def adapter(self, provider):
        return None


def delegated_prompt(runtime, **params):
    with patch.object(router.time, "monotonic", lambda: 0.0):
        result = router.invoke_prompt({"_runtime": runtime, **params})
    assert result["status"] is True
    assert result["metadata"]["selected_provider"] == "vertex_ai"
    assert result["metadata"]["fallback_used"] is False
    assert result["metadata"]["fallback_attempts"] == []
    command, payload = runtime.payloads[-1]
    assert command == "invoke_prompt"
    return payload


def in_process_prompt(runtime, model_instance="vertex-chat", **params):
    chat = MagicMock(return_value=model_instance)
    module = SimpleNamespace(ChatVertexAI=chat, VertexAIEmbeddings=MagicMock())
    with patch.dict(sys.modules, {"langchain_google_vertexai": module}), \
            patch.object(router.time, "monotonic", lambda: 0.0):
        result = router.invoke_prompt({"_runtime": runtime, **params})
    assert result["status"] is True
    assert result["metadata"]["selected_provider"] == "vertex_ai"
    assert result["metadata"]["fallback_used"] is False
    assert chat.call_count == 1
    return result, chat.call_args.kwargs


# (runtime config, workflow params, effective route timeout in ms)
EFFECTIVE_TIMEOUTS = [
    pytest.param({}, {}, 30000, id="policy-default"),
    pytest.param({}, {"timeout_ms": 20000}, 20000, id="caller-shorter"),
    pytest.param({}, {"timeout_ms": 600000}, 120000, id="policy-max-clamp"),
    pytest.param({"policy": {"max_timeout_ms": 50000}}, {"timeout_ms": 90000}, 50000, id="operator-max-clamp"),
    pytest.param({}, {"timeout_ms": 60000, "total_deadline_ms": 45000}, 45000, id="caller-deadline-clamp"),
    pytest.param({}, {"timeout_ms": 60000, "options": {"total_deadline_ms": 45000}}, 45000, id="nested-deadline-clamp"),
    pytest.param({"policy": {"total_deadline_ms": 10000}}, {"timeout_ms": 60000}, 10000, id="policy-deadline-clamp"),
    pytest.param({}, {"timeout": 20}, 20000, id="legacy-seconds"),
]


class TestDelegatedPromptBudget:
    @pytest.mark.parametrize("config,params,expected_ms", EFFECTIVE_TIMEOUTS)
    def test_prompt_carries_effective_timeout_seconds(self, config, params, expected_ms):
        payload = delegated_prompt(DelegateRuntime(config), provider="vertex_ai",
                                   model="gemini-3.8-flash", **params)
        for scope in (payload, payload["params"]):
            assert scope["timeout"] == pytest.approx(expected_ms / 1000.0)
            assert scope["timeout_ms"] == expected_ms

    def test_prompt_timeout_is_not_the_raw_workflow_value(self):
        payload = delegated_prompt(DelegateRuntime(), provider="vertex_ai",
                                   model="gemini-3.8-flash", timeout_ms=600000)
        assert payload["params"]["timeout"] != 600000
        assert payload["params"]["timeout"] != 600.0
        assert payload["params"]["timeout"] == pytest.approx(120.0)

    @pytest.mark.parametrize("model", ["gemini-3.8-flash", "gemini-3.5-flash-lite"])
    def test_router_controlled_prompt_disables_connector_retries(self, model):
        payload = delegated_prompt(DelegateRuntime(), provider="vertex_ai", model=model)
        assert payload["max_retries"] == 0
        assert payload["params"]["max_retries"] == 0

    def test_router_retries_stay_inside_caller_deadline(self):
        clock = [0.0]

        def slow_timeout():
            clock[0] += 0.125
            return {"status": False, "metadata": {"error_class": "provider_timeout"}}

        runtime = DelegateRuntime({"providers": {"vertex_ai": {"retries": 2}}}, on_delegate=slow_timeout)
        with patch.object(router.time, "monotonic", lambda: clock[0]):
            result = router.invoke_prompt({"_runtime": runtime, "provider": "vertex_ai",
                                           "model": "gemini-3.8-flash", "timeout_ms": 1000,
                                           "total_deadline_ms": 250})
        assert result["status"] is False
        assert result["metadata"]["error_class"] == "provider_timeout"
        timeouts = [payload["params"]["timeout"] for _, payload in runtime.payloads]
        assert timeouts == [pytest.approx(0.25), pytest.approx(0.125)]
        assert all(payload["params"]["max_retries"] == 0 for _, payload in runtime.payloads)

    def test_gemini_38_prompt_does_not_gain_sampling_defaults(self):
        payload = delegated_prompt(DelegateRuntime(), provider="vertex_ai", model="gemini-3.8-flash")
        for name in SAMPLING_DEFAULTS:
            assert name not in payload
            assert name not in payload["params"]

    def test_search_keeps_effective_timeout_seconds(self):
        runtime = DelegateRuntime(on_delegate=lambda: {"status": True, "data": {"answer": "ok", "search_results": []}})
        with patch.object(router.time, "monotonic", lambda: 0.0):
            result = router.invoke_search({"_runtime": runtime, "provider": "vertex_ai",
                                           "model": "gemini-3.8-flash", "prompt": "news",
                                           "timeout_ms": 60000, "total_deadline_ms": 45000})
        assert result["status"] is True
        command, payload = runtime.payloads[-1]
        assert command == "invoke_search"
        assert payload["params"]["timeout"] == pytest.approx(45.0)
        assert payload["params"]["search_query"] == "news"


class TestInProcessVertexPromptBudget:
    @pytest.mark.parametrize("config,params,expected_ms", EFFECTIVE_TIMEOUTS)
    def test_factory_receives_effective_timeout_and_no_sdk_retries(self, config, params, expected_ms):
        _, kwargs = in_process_prompt(InProcessRuntime(config), provider="vertex_ai",
                                      model="gemini-3.8-flash", **params)
        assert kwargs["timeout"] == pytest.approx(expected_ms / 1000.0)
        assert kwargs["max_retries"] == 0

    @pytest.mark.parametrize("model", ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-2.5-flash"])
    def test_existing_routes_also_bound_timeout_and_retries(self, model):
        _, kwargs = in_process_prompt(InProcessRuntime(), provider="vertex_ai", model=model,
                                      timeout_ms=15000)
        assert kwargs["timeout"] == pytest.approx(15.0)
        assert kwargs["max_retries"] == 0

    def test_gemini_38_absent_sampling_is_not_forced(self):
        _, kwargs = in_process_prompt(InProcessRuntime(), provider="vertex_ai", model="gemini-3.8-flash")
        for name in SAMPLING_DEFAULTS:
            assert name not in kwargs

    def test_gemini_38_explicit_temperature_is_forwarded(self):
        _, kwargs = in_process_prompt(InProcessRuntime(), provider="vertex_ai",
                                      model="gemini-3.8-flash", temperature=0.7)
        assert kwargs["temperature"] == 0.7

    @pytest.mark.parametrize("model", ["gemini-3.5-flash-lite", "gemini-3.7-flash", "gemini-2.5-flash"])
    def test_existing_routes_keep_their_temperature_default(self, model):
        _, kwargs = in_process_prompt(InProcessRuntime(), provider="vertex_ai", model=model)
        assert kwargs["temperature"] == 0.2

    def test_profile_default_route_is_unchanged(self):
        result, kwargs = in_process_prompt(InProcessRuntime(), profile="balanced")
        assert result["metadata"]["selected_model"] == "gemini-3.5-flash-lite"
        assert kwargs["model_name"] == "gemini-3.5-flash-lite"
        assert kwargs["temperature"] == 0.2

    def test_gemini_38_factory_keeps_structured_output_proxy(self):
        class VertexModel:
            def __init__(self):
                self.schema = None

            def with_structured_output(self, schema, **kwargs):
                self.schema = schema
                return "structured-model"

        model = VertexModel()
        result, _ = in_process_prompt(InProcessRuntime(), model_instance=model,
                                      provider="vertex_ai", model="gemini-3.8-flash")
        factory = result["data"]
        proxy_class = router._vertex_runnable_proxy_class()
        assert isinstance(factory, proxy_class)
        schema = {"type": "object", "properties": {"label": {"type": ["string", "null"]}}}
        structured = factory.with_structured_output(schema)
        # The structured view stays behind the router's inference boundary.
        assert isinstance(structured, proxy_class)
        assert structured._model == "structured-model"
        assert model.schema["properties"]["label"] == {"type": "string", "nullable": True}


SECRET = "sk-live-secret prompt: confidential"


class ProviderHTTPError(Exception):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}: {SECRET}")
        self.status_code = status_code


BODY_SECRET = "CONFIDENTIAL-PROMPT-ECHO sk-body-secret"


class LeakyProviderError(Exception):
    """Provider error whose string and response body both echo secrets."""

    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}: {SECRET}")
        self.response = SimpleNamespace(status_code=status_code, text=f'{{"echo": "{BODY_SECRET}"}}')


def assert_classification_only_log(captured, status, error_class):
    output = captured.out + captured.err
    for marker in (SECRET, BODY_SECRET, "sk-live-secret", "sk-body-secret", "confidential", "CONFIDENTIAL"):
        assert marker not in output
    assert "LeakyProviderError" not in output
    assert f"status={status}" in output
    assert error_class in output


class FakeVertexSDK:
    """ChatVertexAI stub: every construction costs setup time and returns an
    invocable model that runs the next scripted (cost_seconds, outcome) step.
    `invocations` records the timeout each actual inference call received."""

    def __init__(self, clock, steps, setup_s=0.0, transform_s=0.0):
        self.clock = clock
        self.steps = list(steps)
        self.setup_s = setup_s
        self.transform_s = transform_s
        self.timeouts = []
        self.invocations = []
        self.models = []

    def ChatVertexAI(self, **kwargs):
        self.timeouts.append(kwargs["timeout"])
        self.clock[0] += self.setup_s
        model = FakeVertexModel(self)
        self.models.append(model)
        return model

    def module(self):
        return SimpleNamespace(ChatVertexAI=self.ChatVertexAI, VertexAIEmbeddings=MagicMock())


class FakeVertexModel:
    def __init__(self, sdk):
        self.sdk = sdk
        self.schemas = []
        self.bound_tools = []

    def _step(self):
        cost, outcome = self.sdk.steps.pop(0)
        self.sdk.clock[0] += cost
        return outcome

    def invoke(self, input, config=None, **kwargs):
        self.sdk.invocations.append(kwargs.get("timeout"))
        outcome = self._step()
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def stream(self, input, config=None, **kwargs):
        self.sdk.invocations.append(kwargs.get("timeout"))
        for item in self._step():
            if isinstance(item, BaseException):
                raise item
            yield item

    def with_structured_output(self, schema, **kwargs):
        self.schemas.append(schema)
        self.sdk.clock[0] += self.sdk.transform_s
        return FakeStructuredView(self)

    def bind_tools(self, tools, **kwargs):
        self.bound_tools.append(tools)
        return FakeStructuredView(self)

    def generate(self, messages):
        raise AssertionError("ungoverned inference entry point reached")


class FakeStructuredView:
    """Like LangChain's `llm | parser`: call kwargs reach the model's invoke."""

    def __init__(self, model):
        self.model = model

    def invoke(self, input, config=None, **kwargs):
        return {"answer": self.model.invoke(input, config, **kwargs)}


class FallbackRuntime(InProcessRuntime):
    def __init__(self, config, adapters):
        super().__init__(config)
        self.adapters = adapters

    def adapter(self, provider):
        return self.adapters.get(provider)


class FallbackAdapter:
    def __init__(self, model):
        self.model = model
        self.routes = []

    def create_chat_model(self, route, request):
        self.routes.append(route)
        return router.AdapterResult(self.model)


class AnswerModel:
    def __init__(self, answer):
        self.answer = answer
        self.inputs = []

    def invoke(self, input, config=None, **kwargs):
        self.inputs.append(input)
        return self.answer


GROQ_FALLBACK = {
    "providers": {"groq": {"credential": "test-only"}},
    "fallbacks": {"chat": {"vertex_ai": [{"provider": "groq", "model": "openai/gpt-oss-120b"}]}},
}


class TestGovernedVertexInference:
    """Factory success is not inference success: the returned model's real
    invocations must run under the router's retry, fallback, and deadline."""

    def setup_factory(self, sdk, clock, runtime, **params):
        result = router.invoke_prompt({"_runtime": runtime, "provider": "vertex_ai",
                                       "model": "gemini-3.8-flash", **params})
        assert result["status"] is True
        assert result["message"] == "Model loaded."
        assert result["metadata"]["selected_provider"] == "vertex_ai"
        assert result["metadata"]["selected_model"] == "gemini-3.8-flash"
        return result["data"]

    def patched(self, sdk, clock):
        return _Patched(sdk, clock)

    def test_setup_time_is_counted_and_late_result_is_rejected(self):
        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.070, "late-answer")], setup_s=0.040)
        runtime = InProcessRuntime({"policy": {"total_deadline_ms": 100}})
        with self.patched(sdk, clock):
            factory = self.setup_factory(sdk, clock, runtime, timeout_ms=1000)
            assert factory.get_inference_receipt() is None
            assert factory.get_inference_deadline() == pytest.approx(0.100)
            with pytest.raises(router.RouterError) as caught:
                factory.invoke("hello")
        assert caught.value.error_class == "provider_timeout"
        # Setup took 40ms of the 100ms operator budget: the refreshed factory sees <=60ms.
        assert sdk.timeouts[0] == pytest.approx(0.100)
        assert sdk.timeouts[1] <= 0.060 + 1e-9
        # One Vertex route, no retry and no hidden gemini-3.7 fallback.
        assert len(sdk.timeouts) == 2
        receipt = factory.get_inference_receipt()
        assert receipt["execution_phase"] == "inference"
        assert receipt["error_class"] == "provider_timeout"
        assert receipt["selected_provider"] == "vertex_ai"
        assert receipt["selected_model"] == "gemini-3.8-flash"
        assert receipt["fallback_used"] is False
        assert [attempt["error_class"] for attempt in receipt["fallback_attempts"]] == ["provider_timeout"]

    def test_structured_transient_timeout_retries_inside_shared_budget(self):
        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.100, TimeoutError(SECRET)), (0.010, "home")], setup_s=0.010)
        runtime = InProcessRuntime({"policy": {"total_deadline_ms": 1000},
                                    "providers": {"vertex_ai": {"retries": 1}}})
        schema = {"type": "object", "properties": {"label": {"type": ["string", "null"]}}}
        with self.patched(sdk, clock):
            factory = self.setup_factory(sdk, clock, runtime, timeout_ms=5000)
            structured = factory.with_structured_output(schema)
            assert structured.invoke("hello") == {"answer": "home"}
        # Setup, first attempt, retry: each refresh gets only the remaining budget.
        assert len(sdk.timeouts) == 3
        assert sdk.timeouts[0] > sdk.timeouts[1] > sdk.timeouts[2] > 0
        assert sdk.timeouts[2] <= 1.0 - 0.120 + 1e-9
        # The structured boundary is replayed on every refreshed model.
        for model in sdk.models:
            assert model.schemas == [{"type": "object", "properties": {"label": {"type": "string", "nullable": True}}}]
        receipt = structured.get_inference_receipt()
        assert receipt == factory.get_inference_receipt()
        assert receipt["execution_phase"] == "inference"
        assert receipt["error_class"] is None
        assert receipt["selected_model"] == "gemini-3.8-flash"
        assert receipt["fallback_used"] is False
        assert [(a["error_class"], a["retry"]) for a in receipt["fallback_attempts"]] == [("provider_timeout", True)]
        assert structured.get_inference_deadline() == factory.get_inference_deadline()

    def test_auth_failure_never_retries_or_falls_back_and_is_sanitized(self):
        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.0, ProviderHTTPError(401))])
        fallback = FallbackAdapter(AnswerModel("groq-answer"))
        config = router._deep_merge(GROQ_FALLBACK, {"providers": {"vertex_ai": {"retries": 2}}})
        runtime = FallbackRuntime(config, {"groq": fallback})
        with self.patched(sdk, clock):
            factory = self.setup_factory(sdk, clock, runtime)
            with pytest.raises(router.RouterError) as caught:
                factory.invoke("hello")
        error = caught.value
        assert error.error_class == "provider_authentication"
        assert SECRET not in str(error)
        assert error.__cause__ is None and error.__context__ is None
        assert len(sdk.timeouts) == 2
        assert fallback.routes == []
        receipt = factory.get_inference_receipt()
        assert receipt["error_class"] == "provider_authentication"
        assert receipt["selected_provider"] == "vertex_ai"
        assert len(receipt["fallback_attempts"]) == 1
        assert SECRET not in repr(receipt)

    def test_configured_transient_fallback_updates_original_receipt(self):
        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.0, ProviderHTTPError(503))])
        answer = AnswerModel("groq-answer")
        fallback = FallbackAdapter(answer)
        runtime = FallbackRuntime(GROQ_FALLBACK, {"groq": fallback})
        with self.patched(sdk, clock):
            factory = self.setup_factory(sdk, clock, runtime)
            assert fallback.routes == []
            assert factory.invoke("hello") == "groq-answer"
        assert answer.inputs == ["hello"]
        receipt = factory.get_inference_receipt()
        assert receipt["execution_phase"] == "inference"
        assert receipt["selected_provider"] == "groq"
        assert receipt["selected_model"] == "openai/gpt-oss-120b"
        assert receipt["fallback_used"] is True
        assert receipt["error_class"] is None
        assert [(a["provider"], a["error_class"]) for a in receipt["fallback_attempts"]] == [("vertex_ai", "provider_unavailable")]
        assert SECRET not in repr(receipt)

    def test_stream_failure_after_emitted_chunk_is_not_replayed(self):
        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.0, ["first", TimeoutError(SECRET)]), (0.0, ["replayed"])])
        runtime = InProcessRuntime({"providers": {"vertex_ai": {"retries": 1}}})
        emitted = []
        with self.patched(sdk, clock):
            factory = self.setup_factory(sdk, clock, runtime)
            with pytest.raises(router.RouterError) as caught:
                for chunk in factory.stream("hello"):
                    emitted.append(chunk)
        assert emitted == ["first"]
        assert caught.value.error_class == "provider_timeout"
        assert SECRET not in str(caught.value)
        assert len(sdk.timeouts) == 2
        assert factory.get_inference_receipt()["error_class"] == "provider_timeout"

    def test_tool_binding_is_governed_and_raw_entry_points_are_closed(self):
        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.0, TimeoutError(SECRET)), (0.0, "tool-answer")])
        runtime = InProcessRuntime({"providers": {"vertex_ai": {"retries": 1}}})
        with self.patched(sdk, clock):
            factory = self.setup_factory(sdk, clock, runtime)
            bound = factory.bind_tools(["lookup"])
            assert bound.invoke("hello") == {"answer": "tool-answer"}
            with pytest.raises(AttributeError):
                factory.generate
        assert [model.bound_tools for model in sdk.models[1:]] == [[["lookup"]], [["lookup"]]]
        assert factory.get_inference_receipt()["fallback_attempts"][0]["retry"] is True

    def test_async_and_batch_invocations_use_the_governed_loop(self):
        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.0, TimeoutError(SECRET)), (0.0, "async-answer"), (0.0, "batch-answer")])
        runtime = InProcessRuntime({"providers": {"vertex_ai": {"retries": 1}}})
        with self.patched(sdk, clock):
            factory = self.setup_factory(sdk, clock, runtime)
            assert asyncio.run(factory.ainvoke("hello")) == "async-answer"
            assert factory.batch(["hello"]) == ["batch-answer"]
        # Setup, async attempt + retry, batch attempt: all refreshed by the router.
        assert len(sdk.timeouts) == 4
        assert factory.get_inference_receipt()["error_class"] is None


STRUCTURED_SCHEMA = {"type": "object", "properties": {"label": {"type": "string"}}}
VIEWS = [
    pytest.param("with_structured_output", STRUCTURED_SCHEMA, id="structured"),
    pytest.param("bind_tools", ["lookup"], id="tool-binding"),
]


class TestInferenceCallDeadline:
    """The deadline is re-read after the model is rebuilt and its views are
    replayed, and the remaining seconds reach the actual inference call."""

    def setup_factory(self, runtime, **params):
        return TestGovernedVertexInference().setup_factory(None, None, runtime, **params)

    def test_rebuild_and_transform_exhausting_deadline_makes_no_inference_call(self):
        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.0, "never")], setup_s=0.030, transform_s=0.030)
        runtime = InProcessRuntime({"policy": {"total_deadline_ms": 100}})
        with _Patched(sdk, clock):
            factory = self.setup_factory(runtime, timeout_ms=1000)
            structured = factory.with_structured_output(STRUCTURED_SCHEMA)
            # 60ms spent; the refresh (30ms) plus the replayed view (30ms) crosses 100ms.
            with pytest.raises(router.RouterError) as caught:
                structured.invoke("hello")
        assert caught.value.error_class == "provider_timeout"
        assert sdk.invocations == []
        assert sdk.steps == [(0.0, "never")]
        assert structured.get_inference_receipt()["error_class"] == "provider_timeout"

    def test_invocation_receives_only_budget_left_after_rebuild(self):
        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.0, "answer")], setup_s=0.040)
        runtime = InProcessRuntime({"policy": {"total_deadline_ms": 100}})
        with _Patched(sdk, clock):
            factory = self.setup_factory(runtime, timeout_ms=1000)
            assert factory.invoke("hello") == "answer"
        # Constructor 40ms + rebuild 40ms of 100ms: the constructor saw 60ms, the call 20ms.
        assert sdk.timeouts[1] == pytest.approx(0.060)
        assert len(sdk.invocations) == 1
        assert 0 < sdk.invocations[0] <= 0.020 + 1e-9
        assert sdk.invocations[0] == pytest.approx(0.020)

    def test_caller_timeout_cannot_expand_the_remaining_budget(self):
        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.0, "long"), (0.0, "short")])
        runtime = InProcessRuntime({"policy": {"total_deadline_ms": 100}})
        caller_kwargs = {"timeout": 30.0}
        with _Patched(sdk, clock):
            factory = self.setup_factory(runtime, timeout_ms=1000)
            assert factory.invoke("hello", **caller_kwargs) == "long"
            assert factory.invoke("hello", timeout=0.005) == "short"
        assert sdk.invocations == [pytest.approx(0.100), pytest.approx(0.005)]
        assert caller_kwargs == {"timeout": 30.0}

    @pytest.mark.parametrize("view,argument", VIEWS)
    def test_view_retry_invocations_shrink_with_the_shared_budget(self, view, argument):
        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.100, TimeoutError(SECRET)), (0.0, "home")], setup_s=0.010)
        runtime = InProcessRuntime({"policy": {"total_deadline_ms": 1000},
                                    "providers": {"vertex_ai": {"retries": 1}}})
        with _Patched(sdk, clock):
            factory = self.setup_factory(runtime, timeout_ms=5000)
            bound = getattr(factory, view)(argument)
            assert bound.invoke("hello", timeout=60.0) == {"answer": "home"}
        # Attempt 1: rebuilt at 20ms -> 980ms left. Attempt 2: rebuilt at 130ms -> 870ms left.
        assert sdk.invocations == [pytest.approx(0.980), pytest.approx(0.870)]

    def test_non_vertex_fallback_call_is_unchanged(self):
        class NoKwargsModel(AnswerModel):
            def invoke(self, input, config=None, **kwargs):
                assert kwargs == {}
                return super().invoke(input, config)

        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.0, ProviderHTTPError(503))])
        answer = NoKwargsModel("groq-answer")
        runtime = FallbackRuntime(GROQ_FALLBACK, {"groq": FallbackAdapter(answer)})
        with _Patched(sdk, clock):
            factory = self.setup_factory(runtime)
            assert factory.invoke("hello") == "groq-answer"
        assert answer.inputs == ["hello"]


class TestRealVertexTransportTimeout:
    """Offline: the installed ChatVertexAI, structured through its own
    `bind_tools | parser` sequence, with only the prediction client mocked."""

    def test_structured_invocation_timeout_reaches_prediction_client(self):
        vertex = pytest.importorskip("langchain_google_vertexai")
        auth = pytest.importorskip("google.auth.credentials")
        clock = [0.0]

        def build(**kwargs):
            # Synthetic project and anonymous credentials: no ADC, no network.
            kwargs.update(project="synthetic-project", location="us-central1",
                          credentials=auth.AnonymousCredentials())
            model = vertex.ChatVertexAI(**kwargs)
            clock[0] += 0.040
            return model

        client = MagicMock()
        client.generate_content.side_effect = ProviderHTTPError(503)
        module = SimpleNamespace(ChatVertexAI=build, VertexAIEmbeddings=MagicMock())
        runtime = InProcessRuntime({"policy": {"total_deadline_ms": 100}})
        schema = {"title": "Answer", "type": "object", "properties": {"label": {"type": "string"}}}
        with patch.dict(sys.modules, {"langchain_google_vertexai": module}), \
                patch.object(router.time, "monotonic", lambda: clock[0]), \
                patch.object(vertex.ChatVertexAI, "prediction_client", new_callable=PropertyMock, return_value=client):
            result = router.invoke_prompt({"_runtime": runtime, "provider": "vertex_ai",
                                           "model": "gemini-2.5-flash", "timeout_ms": 1000})
            assert result["status"] is True
            structured = result["data"].with_structured_output(schema)
            with pytest.raises(router.RouterError) as caught:
                structured.invoke("hello", timeout=30.0)
        assert caught.value.error_class == "provider_unavailable"
        assert client.generate_content.call_count == 1
        # Setup 40ms + rebuild 40ms of 100ms: the transport sees the last 20ms.
        assert client.generate_content.call_args.kwargs["timeout"] == pytest.approx(0.020)


class TestInferenceErrorLogging:
    """Provider error text can echo prompts and secrets: logs carry only the
    status code and the router's fixed classification."""

    def test_retried_inference_failure_logs_classification_only(self, capsys):
        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.0, LeakyProviderError(503)), (0.0, "ok")])
        runtime = InProcessRuntime({"providers": {"vertex_ai": {"retries": 1}}})
        with _Patched(sdk, clock):
            factory = TestInferenceCallDeadline().setup_factory(runtime)
            assert factory.invoke("hello") == "ok"
        assert_classification_only_log(capsys.readouterr(), 503, "provider_unavailable")

    def test_final_auth_failure_logs_classification_only(self, capsys):
        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.0, LeakyProviderError(401))])
        runtime = InProcessRuntime({"providers": {"vertex_ai": {"retries": 2}}})
        with _Patched(sdk, clock):
            factory = TestInferenceCallDeadline().setup_factory(runtime)
            with pytest.raises(router.RouterError) as caught:
                factory.invoke("hello")
        assert caught.value.error_class == "provider_authentication"
        assert len(sdk.invocations) == 1
        assert_classification_only_log(capsys.readouterr(), 401, "provider_authentication")

    def test_streaming_failure_logs_classification_only(self, capsys):
        clock = [0.0]
        sdk = FakeVertexSDK(clock, [(0.0, ["first", LeakyProviderError(503)])])
        runtime = InProcessRuntime()
        emitted = []
        with _Patched(sdk, clock):
            factory = TestInferenceCallDeadline().setup_factory(runtime)
            with pytest.raises(router.RouterError) as caught:
                for chunk in factory.stream("hello"):
                    emitted.append(chunk)
        assert emitted == ["first"]
        assert caught.value.error_class == "provider_unavailable"
        assert_classification_only_log(capsys.readouterr(), 503, "provider_unavailable")


class _Patched:
    def __init__(self, sdk, clock):
        self.patches = [
            patch.dict(sys.modules, {"langchain_google_vertexai": sdk.module()}),
            patch.object(router.time, "monotonic", lambda: clock[0]),
        ]

    def __enter__(self):
        for item in self.patches:
            item.__enter__()
        return self

    def __exit__(self, *exc):
        for item in reversed(self.patches):
            item.__exit__(*exc)
        return False
