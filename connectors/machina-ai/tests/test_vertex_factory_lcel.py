import asyncio
import importlib.util
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable


CONNECTOR_DIR = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


router = load_module("machina_ai_vertex_lcel_tests", CONNECTOR_DIR / "machina-ai.py")


class RecordingChatModel(Runnable[str, AIMessage]):
    def __init__(self):
        self.calls = []
        self.structured_calls = []

    def invoke(self, input, config=None, **kwargs):
        self.calls.append(("invoke", input, config, kwargs))
        return AIMessage(content="complete")

    async def ainvoke(self, input, config=None, **kwargs):
        self.calls.append(("ainvoke", input, config, kwargs))
        return AIMessage(content="complete-async")

    def stream(self, input, config=None, **kwargs):
        self.calls.append(("stream", input, config, kwargs))
        yield AIMessageChunk(content="first")
        yield AIMessageChunk(content="second")

    async def astream(self, input, config=None, **kwargs):
        self.calls.append(("astream", input, config, kwargs))
        yield AIMessageChunk(content="first-async")
        yield AIMessageChunk(content="second-async")

    def with_structured_output(self, schema, **kwargs):
        self.structured_calls.append((schema, kwargs))
        return "structured-model"


def test_vertex_factory_is_a_runnable_with_left_and_right_composition():
    model = RecordingChatModel()
    factory = router._vertex_chat_model(model)

    assert isinstance(factory, Runnable)
    assert factory.InputType is model.InputType
    assert factory.OutputType is model.OutputType
    assert factory.get_input_jsonschema() == model.get_input_jsonschema()
    assert factory.get_output_jsonschema() == model.get_output_jsonschema()
    assert (factory | (lambda message: message.content.upper())).invoke("hello") == "COMPLETE"
    assert ((lambda value: f"prompt:{value}") | factory | StrOutputParser()).invoke("hello") == "complete"
    assert model.calls[-1][1] == "prompt:hello"


def test_composed_streaming_preserves_chunks_without_calling_invoke():
    model = RecordingChatModel()
    factory = router._vertex_chat_model(model)
    parser = StrOutputParser()

    assert list((factory | parser).stream("hello")) == ["first", "second"]
    prompt = ChatPromptTemplate.from_template("Question: {question}")
    assert list((prompt | factory | parser).stream({"question": "hello"})) == ["first", "second"]
    assert [call[0] for call in model.calls] == ["stream", "stream"]


def test_async_invocation_and_composed_streaming_preserve_native_methods():
    async def exercise():
        model = RecordingChatModel()
        factory = router._vertex_chat_model(model)
        parser = StrOutputParser()

        result = await (factory | parser).ainvoke("hello")
        chunks = [chunk async for chunk in (factory | parser).astream("hello")]
        prompt = ChatPromptTemplate.from_template("Question: {question}")
        prompt_chunks = [
            chunk async for chunk in (prompt | factory | parser).astream({"question": "hello"})
        ]

        assert result == "complete-async"
        assert chunks == ["first-async", "second-async"]
        assert prompt_chunks == ["first-async", "second-async"]
        assert [call[0] for call in model.calls] == ["ainvoke", "astream", "astream"]

    asyncio.run(exercise())


def test_lcel_forwards_config_to_sync_and_async_model_methods():
    async def exercise():
        model = RecordingChatModel()
        factory = router._vertex_chat_model(model)
        chain = factory | StrOutputParser()
        config = {"tags": ["factory-test"], "metadata": {"request_id": "req-1"}}

        chain.invoke("sync", config=config, stop=["done"])
        list(chain.stream("sync-stream", config=config, stop=["done"]))
        await chain.ainvoke("async", config=config, stop=["done"])
        _ = [chunk async for chunk in chain.astream("async-stream", config=config, stop=["done"])]

        assert [call[0] for call in model.calls] == ["invoke", "stream", "ainvoke", "astream"]
        for _, _, forwarded_config, kwargs in model.calls:
            assert forwarded_config["tags"] == ["factory-test"]
            assert forwarded_config["metadata"] == {"request_id": "req-1"}
            assert kwargs == {"stop": ["done"]}

    asyncio.run(exercise())


def test_runnable_factory_preserves_nullable_schema_contract():
    model = RecordingChatModel()
    factory = router._vertex_chat_model(model)
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": ["string", "null"], "enum": ["home", None]},
            "literal": {"type": "object", "default": {"type": ["string", "integer"]}},
        },
    }

    assert factory.with_structured_output(schema, method="json_schema") == "structured-model"
    normalized, kwargs = model.structured_calls[0]
    assert schema["properties"]["label"]["type"] == ["string", "null"]
    assert normalized["properties"]["label"] == {
        "type": "string",
        "nullable": True,
        "enum": ["home", None],
    }
    assert normalized["properties"]["literal"]["default"] == {"type": ["string", "integer"]}
    assert kwargs == {"method": "json_schema"}

    with pytest.raises(ValueError, match="Vertex structured output"):
        factory.with_structured_output({"type": ["string", "integer"]})
    assert len(model.structured_calls) == 1
