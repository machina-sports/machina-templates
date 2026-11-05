"""Exercise the google-genai invoke_tts request shapes offline; no credentials or model calls."""
import ast
import base64
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import types
from types import SimpleNamespace as NS
from unittest.mock import Mock
import uuid
import wave

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "connectors/google-genai/google-genai.py"
FUNCTIONS = {"invoke_tts", "_is_structured_tts_model"}
CONSTANTS = {"TTS_DEFAULT_MODEL", "_AI_STUDIO_TTS_MODEL_ALIASES"}

LEGACY_VERTEX_URL = (
    "https://us-central1-aiplatform.googleapis.com/v1/projects/test-project/locations/us-central1"
    "/publishers/google/models/gemini-2.5-flash-tts:generateContent"
)


def _pcm(seconds=0.5, rate=24000):
    return b"\x01\x00" * int(seconds * rate)


def _wav(pcm, rate=24000):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm)
    return buffer.getvalue()


@pytest.fixture
def tts(monkeypatch):
    auth_requests = types.ModuleType("google.auth.transport.requests")
    auth_requests.Request = Mock()
    for name in ("google", "google.auth", "google.auth.transport"):
        if name not in sys.modules:
            monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, "google.auth.transport.requests", auth_requests)

    audio = {"bytes": _pcm(), "mime": "audio/L16;codec=pcm;rate=24000"}

    def post(url, json=None, headers=None, timeout=None):
        body = {"candidates": [{"content": {"parts": [{"inlineData": {
            "mimeType": audio["mime"], "data": base64.b64encode(audio["bytes"]).decode()}}]}}]}
        return NS(status_code=200, text="", json=lambda: body)

    requests_stub = NS(post=Mock(side_effect=post))
    credentials = NS(refresh=Mock(), token="vertex-token")
    service_account = NS(Credentials=NS(from_service_account_info=Mock(return_value=credentials)))
    scope = dict(requests=requests_stub, service_account=service_account, json=json, base64=base64, os=os,
                 tempfile=tempfile, uuid=uuid, wave=wave, re=re)
    tree = ast.parse(SOURCE.read_text())
    nodes = [node for node in tree.body
             if (isinstance(node, ast.FunctionDef) and node.name in FUNCTIONS)
             or (isinstance(node, ast.Assign) and any(getattr(t, "id", None) in CONSTANTS for t in node.targets))]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), scope)
    return NS(invoke=scope["invoke_tts"], structured=scope["_is_structured_tts_model"],
              post=requests_stub.post, service_account=service_account, audio=audio)


def vertex(**params):
    return {"headers": {"credential": {"type": "service_account"}, "project_id": "test-project"}, "params": {"text": "Goal!", **params}}


def test_default_call_keeps_the_legacy_vertex_request_byte_for_byte(tts):
    result = tts.invoke(vertex(voice_name="Puck", language_code="pt-br"))
    assert result["status"] is True
    call = tts.post.call_args
    assert call.args[0] == LEGACY_VERTEX_URL
    assert call.kwargs["headers"]["Authorization"] == "Bearer vertex-token"
    assert call.kwargs["json"] == {
        "contents": {"role": "user", "parts": {"text": "Goal!"}},
        "generationConfig": {
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Puck"}}},
            "temperature": 2.0,
        },
    }
    data = result["data"]
    assert (data["model_id"], data["provider"], data["duration_seconds"]) == ("gemini-2.5-flash-tts", "vertex_ai", 0.5)
    with wave.open(data["file_path"]) as wf:
        assert (wf.getframerate(), wf.getnchannels(), wf.getnframes()) == (24000, 1, 12000)


def test_legacy_models_keep_the_style_prefix_in_the_text(tts):
    tts.invoke(vertex(prompt="Say it cheerfully"))
    assert tts.post.call_args.kwargs["json"]["contents"]["parts"]["text"] == "Say it cheerfully: Goal!"


@pytest.mark.parametrize("model_id", ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"])
def test_gemini_38_sends_the_structured_request_to_the_global_endpoint(tts, model_id):
    tts.audio.update(bytes=_wav(_pcm(0.25)), mime="audio/wav")
    result = tts.invoke(vertex(model_id=model_id, voice_name="Kore", prompt="excited live commentator"))
    assert result["status"] is True
    call = tts.post.call_args
    assert call.args[0] == (
        "https://aiplatform.googleapis.com/v1/projects/test-project/locations/global"
        f"/publishers/google/models/{model_id}:generateContent"
    )
    assert call.kwargs["json"] == {
        "contents": [{"role": "user", "parts": [{"text": "Goal!", "speechMetadata": {"style": "excited live commentator"}}]}],
        "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"voice": "Kore"}}},
    }
    # The returned WAV is stored as-is, not wrapped in a second RIFF header.
    assert Path(result["data"]["file_path"]).read_bytes() == tts.audio["bytes"]
    assert result["data"]["duration_seconds"] == 0.25


def test_gemini_38_omits_speech_metadata_without_a_style_and_honors_an_explicit_location(tts):
    tts.audio.update(bytes=_wav(_pcm(0.1)), mime="audio/wav")
    tts.invoke(vertex(model_id="gemini-3.8-flash-tts", location="europe-west4"))
    call = tts.post.call_args
    assert call.args[0].startswith("https://europe-west4-aiplatform.googleapis.com/v1/projects/test-project/locations/europe-west4/")
    assert call.kwargs["json"]["contents"] == [{"role": "user", "parts": [{"text": "Goal!"}]}]


def test_ai_studio_is_opt_in_and_uses_the_api_key_with_preview_aliases(tts):
    result = tts.invoke({"headers": {"api_key": "studio-key"}, "params": {"text": "Goal!", "provider": "ai_studio"}})
    assert result["status"] is True
    call = tts.post.call_args
    assert call.args[0] == (
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-tts:generateContent"
    )
    assert call.kwargs["headers"] == {"x-goog-api-key": "studio-key", "Content-Type": "application/json"}
    assert call.kwargs["json"]["generationConfig"]["responseModalities"] == ["AUDIO"]
    assert result["data"]["model_id"] == "gemini-2.5-flash-tts"
    tts.service_account.Credentials.from_service_account_info.assert_not_called()


@pytest.mark.parametrize("request_data", [
    {"headers": {"api_key": "studio-key"}, "params": {"text": "Goal!"}},  # default provider is still Vertex AI
    {"headers": {"credential": {"type": "service_account"}, "project_id": "p"}, "params": {"text": "Goal!", "provider": "ai_studio"}},
    {"headers": {"credential": {"type": "service_account"}, "project_id": "p"}, "params": {"text": "Goal!", "provider": "openai"}},
    {"headers": {"credential": {"type": "service_account"}, "project_id": "p"}, "params": {"text": ""}},
])
def test_invalid_requests_fail_before_any_model_call(tts, request_data):
    assert tts.invoke(request_data)["status"] is False
    tts.post.assert_not_called()


@pytest.mark.parametrize("model_id, expected", [
    ("gemini-2.5-flash-tts", False),
    ("gemini-2.5-pro-tts", False),
    ("gemini-3.1-flash-tts-preview", False),
    ("gemini-3.8-flash-tts", True),
    ("gemini-3.8-flash-lite-tts", True),
    ("gemini-4-flash-tts", True),
    ("gemini-3.8-flash", False),
    (None, False),
])
def test_structured_request_shape_starts_at_gemini_38_tts(tts, model_id, expected):
    assert tts.structured(model_id) is expected
