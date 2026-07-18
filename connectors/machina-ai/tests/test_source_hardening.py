import base64
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[3]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_azure_import_and_boolean_failure_status():
    fake = SimpleNamespace(AzureChatOpenAI=MagicMock(), AzureOpenAIEmbeddings=MagicMock())
    with patch.dict(sys.modules, {"langchain_openai": fake}):
        azure = load_module("azure_foundry_hardening", ROOT / "connectors" / "azure-foundry" / "azure-foundry.py")
    failure = azure.invoke_prompt({})
    assert failure["status"] is False
    assert hasattr(fake, "AzureChatOpenAI")


def test_groq_fake_embedding_is_not_declared_and_is_typed():
    fake = SimpleNamespace(ChatGroq=MagicMock())
    with patch.dict(sys.modules, {"langchain_groq": fake, "groq": SimpleNamespace(Groq=MagicMock())}):
        groq = load_module("groq_hardening", ROOT / "connectors" / "groq" / "groq.py")
    manifest = (ROOT / "connectors" / "groq" / "groq.yml").read_text()
    result = groq.invoke_embedding({})
    assert 'value: "invoke_embedding"' not in manifest
    assert result["status"] is False
    assert result["metadata"]["error_class"] == "unsupported_capability"


def test_vertex_embedding_source_never_logs_credential_material():
    source = (ROOT / "connectors" / "vertex-embedding" / "vertex-embedding.py").read_text()
    assert "credential value" not in source
    assert "print(" not in source
    assert "from_service_account_info" in source


def test_google_speech_rejects_credential_paths_and_arbitrary_http_downloads():
    source = (ROOT / "connectors" / "google-speech-to-text" / "google-speech-to-text.py").read_text()
    assert "from_service_account_info" in source
    assert "from_service_account_json" not in source
    assert "requests.get" not in source
    assert 'parsed.hostname != "storage.googleapis.com"' in source


def test_stability_sanitizes_output_names_and_errors():
    source = (ROOT / "connectors" / "stability" / "stability.py").read_text()
    assert "SAFE_NAME" in source
    assert "uuid.uuid4" in source
    assert "response.text" not in source
    assert "allow_redirects=False" in source


def _load_google_genai_with_stubs(generate_content_response):
    """Load google-genai.py offline with the SDK surface stubbed out."""
    fake_types = SimpleNamespace(
        Part=MagicMock(),
        Blob=MagicMock(),
        Content=MagicMock(),
        GenerateContentConfig=MagicMock(),
        ImageConfig=MagicMock(),
    )
    client = MagicMock()
    client.models.generate_content.return_value = generate_content_response
    fake_genai = SimpleNamespace(Client=MagicMock(return_value=client), types=fake_types)
    fake_service_account = SimpleNamespace(
        Credentials=SimpleNamespace(from_service_account_info=MagicMock())
    )
    fake_oauth2 = SimpleNamespace(service_account=fake_service_account)
    fake_google = SimpleNamespace(genai=fake_genai, oauth2=fake_oauth2)
    image_module = MagicMock()
    modules = {
        "google": fake_google,
        "google.genai": fake_genai,
        "google.genai.types": fake_types,
        "google.oauth2": fake_oauth2,
        "google.oauth2.service_account": fake_service_account,
        "langchain_google_genai": SimpleNamespace(ChatGoogleGenerativeAI=MagicMock()),
        "langchain_google_vertexai": SimpleNamespace(
            ChatVertexAI=MagicMock(), VertexAIEmbeddings=MagicMock()
        ),
        "PIL": SimpleNamespace(Image=image_module),
        "PIL.Image": image_module,
        "requests": MagicMock(),
    }
    with patch.dict(sys.modules, modules):
        module = load_module(
            "google_genai_hardening", ROOT / "connectors" / "google-genai" / "google-genai.py"
        )
    return module, client


def test_google_genai_invoke_image_skips_invalid_media_and_continues(tmp_path, monkeypatch):
    part = SimpleNamespace(
        inline_data=SimpleNamespace(data=b"generated", mime_type="image/webp"), text=None
    )
    candidate = SimpleNamespace(
        content=SimpleNamespace(parts=[part]), finish_reason="STOP", safety_ratings=None
    )
    response = SimpleNamespace(candidates=[candidate], prompt_feedback=None)
    module, client = _load_google_genai_with_stubs(response)

    monkeypatch.setenv("MACHINA_WORK_DIR", str(tmp_path))
    valid = tmp_path / "valid.png"
    valid.write_bytes(b"\x89PNG-ok")

    result = module.invoke_image(
        {
            "params": {
                "api_key": "test-key",
                "prompt": "a football",
                "image_paths": [str(valid), "/etc/hosts"],
            },
            "headers": {},
        }
    )

    # The invalid out-of-sandbox image is skipped, the call proceeds with the
    # valid one, and the skip is recorded with a sanitized reason.
    assert result["status"] is True
    assert result["data"]["input_images_count"] == 1
    skipped = result["data"]["skipped_media"]
    assert len(skipped) == 1
    assert skipped[0]["index"] == 1
    assert "/etc/hosts" not in str(skipped)
    client.models.generate_content.assert_called_once()


def test_google_genai_invoke_image_sandbox_still_rejects_outside_paths(tmp_path, monkeypatch):
    module, _ = _load_google_genai_with_stubs(SimpleNamespace(candidates=[], prompt_feedback=None))
    monkeypatch.setenv("MACHINA_WORK_DIR", str(tmp_path))
    try:
        module._safe_local_media_path("/etc/hosts")
    except ValueError as error:
        assert "/etc/hosts" not in str(error)
    else:
        raise AssertionError("out-of-sandbox path must still be rejected")


def test_temp_downloader_save_to_tmp_honors_machina_work_dir(tmp_path, monkeypatch):
    module = load_module(
        "temp_downloader_hardening", ROOT / "connectors" / "temp-downloader" / "temp-downloader.py"
    )
    payload = base64.b64encode(b"image-bytes").decode()

    monkeypatch.setenv("MACHINA_WORK_DIR", str(tmp_path))
    result = module.invoke_save_to_tmp({"params": {"image_base64": payload}, "headers": {}})
    assert result["status"] is True
    image_path = Path(result["data"]["image_path"])
    assert image_path.is_file()
    assert image_path.read_bytes() == b"image-bytes"
    assert (tmp_path / "tmp") in image_path.parents

    # Return shape and system-temp fallback are preserved when unset.
    monkeypatch.delenv("MACHINA_WORK_DIR")
    fallback = module.invoke_save_to_tmp({"params": {"image_base64": payload}, "headers": {}})
    assert fallback["status"] is True
    assert set(fallback) == {"status", "data", "message"}
    fallback_path = Path(fallback["data"]["image_path"])
    assert fallback_path.is_file()
    assert tmp_path not in fallback_path.parents
    fallback_path.unlink()


def test_elevenlabs_returns_relative_artifact_and_sanitized_errors():
    source = (ROOT / "connectors" / "elevenlabs" / "elevenlabs.py").read_text()
    assert "relative_to(root)" in source
    assert "print(" not in source
    assert "str(error)" not in source
