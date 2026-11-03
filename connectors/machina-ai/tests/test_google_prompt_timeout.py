"""Offline contract: router deadlines reach the actual Google factory in seconds."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from test_router import router


@pytest.mark.parametrize("requested_ms", [180000, 300000])
@pytest.mark.parametrize("delegated", [True, False])
def test_google_prompt_factory_receives_policy_bounded_timeout(requested_ms, delegated):
    constructor = MagicMock(return_value=object())
    source = Path(__file__).resolve().parents[2] / "google-genai" / "google-genai.py"
    function = next(node for node in ast.parse(source.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == "invoke_prompt")
    namespace = {"ChatVertexAI": constructor, "json": json}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    config = {
        "policy": {"max_timeout_ms": 300000, "total_deadline_ms": 300000},
        "providers": {"vertex_ai": {"project": "synthetic-project", "location": "global"}},
        "profiles": {"test_brief": {"chat": [{"provider": "vertex_ai", "model": "gemini-3.7-flash"}]}},
    }
    def delegate(target, payload, command=None):
        assert target == "google-genai" and command == "invoke_prompt"
        return namespace["invoke_prompt"](payload["params"])
    runtime = SimpleNamespace(config=lambda: config)
    if delegated:
        runtime.delegate = delegate
    with patch.dict("os.environ", {}, clear=True), \
         patch.object(router.time, "monotonic", return_value=0.0), \
         patch.dict("sys.modules", {"langchain_google_vertexai": SimpleNamespace(ChatVertexAI=constructor)}):
        result = router.invoke_prompt({"_runtime": runtime, "profile": "test_brief", "timeout_ms": requested_ms})
    assert result["status"] is True, result
    assert result["metadata"]["selected_provider"] == "vertex_ai"
    assert result["metadata"]["selected_model"] == "gemini-3.7-flash"
    assert constructor.call_args.kwargs.get("timeout") == requested_ms / 1000


def test_google_prompt_factory_cannot_bypass_policy_cap():
    constructor = MagicMock(return_value=object())
    runtime = SimpleNamespace(config=lambda: {"policy": {"max_timeout_ms": 1000, "total_deadline_ms": 1000}})
    with patch.dict("os.environ", {}, clear=True), \
         patch.object(router.time, "monotonic", return_value=0.0), \
         patch.dict("sys.modules", {"langchain_google_vertexai": SimpleNamespace(ChatVertexAI=constructor)}):
        result = router.invoke_prompt({"_runtime": runtime, "timeout_ms": 300000})
    assert result["status"] is True, result
    assert constructor.call_args.kwargs.get("timeout") == 1.0
