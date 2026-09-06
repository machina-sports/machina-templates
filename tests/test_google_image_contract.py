"""Exercise the existing image entry point offline; no credentials or model calls."""
import ast
import datetime
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
from unittest.mock import Mock
import importlib.util

from PIL import Image
import pytest

SOURCE = Path(__file__).resolve().parents[1] / "connectors/google-genai/google-genai.py"


def test_real_pinned_sdk_accepts_image_resolution_and_image_only_output():
    types = pytest.importorskip("google.genai.types")
    config = types.GenerateContentConfig(response_modalities=["IMAGE"], image_config=types.ImageConfig(aspect_ratio="16:9", image_size="1K"))
    assert config.image_config.image_size == "1K"
    pytest.importorskip("langchain_google_vertexai")
    pytest.importorskip("langchain_google_genai")
    spec = importlib.util.spec_from_file_location("google_image_full_sdk", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.invoke_image)


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("MACHINA_WORK_DIR", str(tmp_path))
    buffer = BytesIO()
    Image.new("RGB", (160, 90), "navy").save(buffer, format="PNG")
    response = NS(prompt_feedback=NS(block_reason=None), model_version="gemini-image-tested-version", candidates=[
        NS(finish_reason="STOP", content=NS(parts=[NS(thought=False, inline_data=NS(data=buffer.getvalue(), mime_type="image/png"))])),
    ])
    model = Mock()
    model.models.generate_content.return_value = response
    client = Mock(return_value=model)
    scope = dict(Image=Image, BytesIO=BytesIO, os=os, Path=Path, tempfile=tempfile, json=json,
                 datetime=datetime, hashlib=hashlib, genai=NS(Client=client),
                 types=NS(Part=NS, Blob=NS, Content=NS, ImageConfig=NS, GenerateContentConfig=NS, HttpOptions=NS),
                 service_account=NS(Credentials=NS(from_service_account_info=Mock(return_value="oauth"))))
    tree = ast.parse(SOURCE.read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {"invoke_image", "_output_root"}]
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), scope)
    return scope["invoke_image"], client, model, response


def request(**overrides):
    return {"headers": {"credential": {}, "project_id": "test-project"}, "params": {
        "provider": "vertex_ai", "model_name": "gemini-3.1-flash-image", "location": "global",
        "prompt": "A text-free editorial background", "aspect_ratio": "16:9", "image_size": "1K", "strict_image": True,
        **overrides,
    }}


def test_empty_feedback_is_not_a_refusal_and_image_has_a_verifiable_receipt(runtime):
    invoke, client, model, _ = runtime
    result = invoke(request())
    assert result["status"] is True
    data = result["data"]
    assert data["sha256"] == hashlib.sha256(Path(data["image_path"]).read_bytes()).hexdigest()
    assert (data["width"], data["height"], data["provider"]) == (160, 90, "vertex_ai")
    assert data["model_version"] == "gemini-image-tested-version"
    assert data["synthetic"] is True
    assert client.call_args.kwargs["http_options"].timeout == 120000
    assert model.models.generate_content.call_args.kwargs["config"].response_modalities == ["IMAGE"]


@pytest.mark.parametrize("override", [{"prompt": ""}, {"model_name": ""}, {"image_size": "8K"}, {"aspect_ratio": "bad"}])
def test_strict_contract_never_falls_back_to_a_default_prompt_or_model(runtime, override):
    invoke, client, _, _ = runtime
    assert invoke(request(**override))["status"] is False
    client.assert_not_called()


@pytest.mark.parametrize("reason", ["SAFETY", "MAX_TOKENS", "IMAGE_SAFETY"])
def test_non_success_finish_reasons_cannot_return_an_asset(runtime, reason):
    invoke, _, _, response = runtime
    response.candidates[0].finish_reason = reason
    assert invoke(request())["status"] is False


def test_blocked_or_text_only_output_never_reports_success(runtime):
    invoke, _, _, response = runtime
    response.prompt_feedback.block_reason = "SAFETY"
    assert invoke(request())["status"] is False
    response.prompt_feedback.block_reason = None
    response.candidates[0].content.parts = [NS(text="Cannot comply", inline_data=None)]
    assert invoke(request())["status"] is False
