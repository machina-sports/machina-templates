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


def test_elevenlabs_returns_relative_artifact_and_sanitized_errors():
    source = (ROOT / "connectors" / "elevenlabs" / "elevenlabs.py").read_text()
    assert "relative_to(root)" in source
    assert "print(" not in source
    assert "str(error)" not in source
