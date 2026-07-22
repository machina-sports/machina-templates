"""Machina AI intelligent router v1.

This connector intentionally ships as one installable Python file.  The connector
runtime currently persists only the declared ``filename`` from the connector
manifest, so architectural boundaries are represented by the small classes in
this module instead of nested packages.

The module has no provider SDK imports at import time.  Provider libraries are
loaded only after policy selects a route.  The server runtime injects the
``machina_router_runtime`` (RouterRuntimeServices) and ``machina_delegate``
globals; a legacy ``runtime`` global and the ``_runtime`` param remain as
offline/test fallbacks.
"""

import base64
import copy
import importlib
import ipaddress
import json
import mimetypes
import os
import re
import socket
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple
from urllib.parse import urlparse

CONTRACT_VERSION = "v1"
TRANSIENT_ERRORS = {
    "provider_timeout",
    "provider_rate_limited",
    "provider_unavailable",
    "provider_bad_response",
}
SECURITY_FIELDS = {
    "api_key",
    "credential",
    "endpoint",
    "base_url",
    "deployment",
    "api_version",
    "callback_url",
}
PROVIDER_ALIASES = {
    "vertex": "vertex_ai",
    "google_vertex": "vertex_ai",
    "gemini": "vertex_ai",
    "ai_studio": "google_ai_studio",
    "google_ai": "google_ai_studio",
    "azure": "azure_foundry",
    "azure_openai": "azure_foundry",
    "grok": "xai",
    "nim": "nvidia_nim",
    "nvidia": "nvidia_nim",
    "byteplus": "byteplus_modelark",
    "modelark": "byteplus_modelark",
    "google_speech_to_text": "google_speech",
    "vertex_model_garden": "vertex_anthropic",
    "model_garden": "vertex_anthropic",
    "anthropic_vertex": "vertex_anthropic",
    "anthropic": "vertex_anthropic",
    "claude": "vertex_anthropic",
}
COMMANDS = {
    "invoke_prompt": ("chat", "factory"),
    "invoke_chat": ("chat", "execute"),
    "completion_receipt": ("chat", "execute"),
    "invoke_embedding": ("embedding", "factory"),
    "embed_query": ("embedding", "execute"),
    "embed_documents": ("embedding", "execute"),
    "invoke_search": ("search_answer", "execute"),
    "invoke_image": ("image", "execute"),
    "generate_image": ("image", "execute"),
    "edit_image": ("image", "execute"),
    "invoke_video": ("video", "execute"),
    "transcribe_audio_to_text": ("transcription", "execute"),
    "invoke_transcribe": ("transcription", "execute"),
    "invoke_tts": ("tts", "execute"),
    "get_text_to_speech": ("tts", "execute"),
    "list_voices": ("voice", "execute"),
    "get_voices": ("voice", "execute"),
    "invoke_clone_instant_voice": ("voice", "execute"),
    "invoke_train_pro_voice": ("voice", "execute"),
    "invoke_synthesize_custom_voice": ("voice", "execute"),
    "invoke_music": ("music", "execute"),
    "list_models": ("management", "execute"),
    "health": ("management", "execute"),
}
CAPABILITY_ALIASES = {
    "search-answer": "search_answer",
    "search": "search_answer",
    "embeddings": "embedding",
    "speech_to_text": "transcription",
    "text_to_speech": "tts",
}
FIELD_ALIASES = {
    "model": ("model_name", "engine"),
    "api_key": ("credential",),
    "organization": ("org_id",),
    "project": ("project_id",),
    "endpoint": ("azure_endpoint",),
    "base_url": (),
    "deployment": ("azure_deployment", "deployment_name"),
    "api_version": ("azure_api_version",),
    "audio_path": ("audio-path",),
    "image_paths": ("image_path", "images"),
    "timeout_ms": ("timeout",),
    "task_id": ("id",),
}
HEADER_FIELDS = {
    "api_key",
    "credential",
    "organization",
    "org_id",
    "project",
    "project_id",
    "api_version",
}
PATH_FIELDS = {"task_id", "id", "operation"}
SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


DEFAULT_CONFIG: Dict[str, Any] = {
    "version": 1,
    "policy": {
        "default_profile": "balanced",
        "allow_workflow_credentials": False,
        "allow_custom_base_url": False,
        "allow_remote_media": False,
        "allowed_endpoint_hosts": [],
        "allowed_remote_media_hosts": [],
        "allowed_callback_urls": [],
        "default_timeout_ms": 30000,
        "max_timeout_ms": 120000,
        "total_deadline_ms": 120000,
        "max_retries": 0,
        "log_raw_prompts": False,
        "log_raw_responses": False,
    },
    "media": {
        "allowed_roots": [],
        "max_input_bytes": 25 * 1024 * 1024,
        "allowed_schemes": ["https"],
    },
    "defaults": {
        "chat": {"provider": "vertex_ai", "model": "gemini-2.5-flash"},
        "embedding": {"provider": "vertex_ai", "model": "text-embedding-004"},
        "search_answer": {"provider": "vertex_ai", "model": "gemini-2.5-flash"},
        "transcription": {"provider": "google_speech", "model": "latest_long"},
    },
    "profiles": {
        "default": {
            "chat": [{"provider": "vertex_ai", "model": "gemini-2.5-flash"}],
            "embedding": [{"provider": "vertex_ai", "model": "text-embedding-004"}],
        },
        "balanced": {
            "chat": [{"provider": "vertex_ai", "model": "gemini-2.5-flash"}],
            "embedding": [{"provider": "vertex_ai", "model": "text-embedding-004"}],
            "search_answer": [{"provider": "vertex_ai", "model": "gemini-2.5-flash"}],
        },
        "quality": {
            "chat": [{"provider": "vertex_ai", "model": "gemini-2.5-pro"}],
        },
        "cheap": {
            "chat": [{"provider": "vertex_ai", "model": "gemini-2.5-flash-lite"}],
        },
        "long_context": {
            "chat": [{"provider": "vertex_ai", "model": "gemini-2.5-pro"}],
        },
        "fast": {"chat": [{"provider": "groq", "model": "llama-3.3-70b-versatile"}]},
        "private_runtime": {"chat": [{"provider": "nvidia_nim"}]},
        "open_source": {"chat": [{"provider": "nvidia_nim"}]},
        "multimodal": {},
    },
    "remaps": {"families": {}, "capabilities": {}, "profiles": {}},
    "fallbacks": {},
    "providers": {
        "vertex_ai": {
            "enabled": True,
            "adapter": "google_genai",
            "credential_env": "TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL",
            "project_env": "TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID",
            "location": "global",
            "allowed_models": {
                "chat": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"],
                "embedding": ["text-embedding-004"],
                "search_answer": ["gemini-2.5-flash", "gemini-2.5-pro"],
                "image": [],
                "video": [],
                "tts": [],
                "music": [],
                "voice": [],
            },
        },
        "vertex_anthropic": {
            # Anthropic Claude on Vertex AI Model Garden.  Reuses the same Vertex
            # service-account as ``vertex_ai``; Claude is billed under the GCP
            # project, so no separate Anthropic credential is required.  Chat
            # only — no embedding/search/media parity on Vertex.
            #
            # Ships dormant: enable per-environment (Entain first) via router
            # config ``providers.vertex_anthropic.enabled: true`` so the Claude
            # cutover is a controlled canary, not a global default flip.
            "enabled": False,
            "adapter": "vertex_anthropic",
            "credential_env": "TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL",
            "project_env": "TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID",
            "location": "global",
            "allowed_models": {
                # Bare Model Garden ids (current-gen Claude uses no prefix / date
                # suffix on Vertex).  Exact availability is per-project — validate
                # in the target Vertex project and override via router config
                # (providers.vertex_anthropic.allowed_models.chat).
                "chat": [
                    "claude-haiku-4-5",
                    "claude-sonnet-4-6",
                    "claude-sonnet-5",
                    "claude-opus-4-8",
                ],
            },
        },
        "google_ai_studio": {
            "enabled": False,
            "adapter": "google_genai",
            "credential_env": "TEMP_CONTEXT_VARIABLE_GOOGLE_AI_API_KEY",
            "allowed_models": {"chat": [], "embedding": [], "search_answer": [], "image": [], "video": [], "tts": [], "music": [], "voice": []},
        },
        "openai": {
            "enabled": False,
            "adapter": "openai_compatible",
            "credential_env": "TEMP_CONTEXT_VARIABLE_OPENAI_API_KEY",
            "endpoint": "https://api.openai.com/v1",
            "allowed_models": {"chat": [], "embedding": [], "transcription": [], "image": []},
        },
        "openai_compatible": {
            "enabled": False,
            "adapter": "openai_compatible",
            "protected": True,
            "allowed_models": {"chat": [], "embedding": [], "transcription": []},
        },
        "azure_foundry": {
            "enabled": False,
            "adapter": "azure_foundry",
            "credential_env": "TEMP_CONTEXT_VARIABLE_AZURE_OPENAI_API_KEY",
            "endpoint_env": "TEMP_CONTEXT_VARIABLE_AZURE_OPENAI_ENDPOINT",
            "deployment_env": "TEMP_CONTEXT_VARIABLE_AZURE_OPENAI_DEPLOYMENT_NAME",
            "allowed_models": {"chat": [], "embedding": []},
        },
        "groq": {
            # Enabled for machina-ai-fast no-regression: credentials resolve from the
            # runtime environment only; absent credential fails typed credential_missing.
            "enabled": True,
            "adapter": "groq",
            "require_credential": True,
            "credential_env": "TEMP_CONTEXT_VARIABLE_GROQ_API_KEY",
            "credential_env_aliases": ["TEMP_CONTEXT_VARIABLE_SDK_GROQ_API_KEY"],
            "allowed_models": {"chat": ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]},
        },
        "xai": {
            "enabled": False,
            "adapter": "xai",
            "credential_env": "TEMP_CONTEXT_VARIABLE_XAI_API_KEY",
            "endpoint": "https://api.x.ai/v1",
            "allowed_models": {"chat": [], "search_answer": []},
        },
        "perplexity": {
            "enabled": False,
            "adapter": "perplexity",
            "credential_env": "TEMP_CONTEXT_VARIABLE_PERPLEXITY_API_KEY",
            "endpoint": "https://api.perplexity.ai",
            "allowed_models": {"chat": [], "search_answer": []},
        },
        "nvidia_nim": {
            "enabled": False,
            "adapter": "nvidia_nim",
            "protected": True,
            "fail_closed": True,
            "endpoint_env": "NVIDIA_NIM_CHAT_BASE_URL",
            "credential_env": "NVIDIA_NIM_CHAT_API_KEY",
            "model_env": "NVIDIA_NIM_CHAT_MODEL",
            "allowed_models_env": "NVIDIA_NIM_CHAT_ALLOWED_MODELS",
            "allowed_models": {"chat": []},
        },
        "byteplus_modelark": {
            "enabled": False,
            "adapter": "byteplus_modelark",
            "credential_env": "TEMP_CONTEXT_VARIABLE_BYTEPLUS_MODELARK_API_KEY",
            "allowed_models": {"video": []},
        },
        "stability": {
            "enabled": False,
            "adapter": "stability",
            "credential_env": "TEMP_CONTEXT_VARIABLE_STABILITY_API_KEY",
            "endpoint": "https://api.stability.ai",
            "allowed_models": {"image": []},
        },
        "elevenlabs": {
            "enabled": False,
            "adapter": "elevenlabs",
            "credential_env": "TEMP_CONTEXT_VARIABLE_ELEVENLABS_API_KEY",
            "endpoint": "https://api.elevenlabs.io/v1",
            "allowed_models": {"tts": [], "voice": []},
        },
        "google_speech": {
            "enabled": True,
            "adapter": "google_speech",
            "credential_env": "TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL",
            "project_env": "TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID",
            "allowed_models": {"transcription": ["latest_long", "latest_short"]},
        },
    },
}


class RouterError(Exception):
    def __init__(self, error_class: str, message: str, *, transient: bool = False, details: Optional[Mapping[str, Any]] = None):
        super().__init__(message)
        self.error_class = error_class
        self.safe_message = message
        self.transient = transient or error_class in TRANSIENT_ERRORS
        self.details = dict(details or {})


@dataclass
class NormalizedRequest:
    command: str
    capability: str
    operation_mode: str
    profile: str
    provider: Optional[str]
    model: Optional[str]
    options: Dict[str, Any]
    input: Dict[str, Any]
    output: Dict[str, Any]
    metadata: Dict[str, Any]
    security: Dict[str, Any]
    conflicts: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Route:
    provider: str
    adapter: str
    capability: str
    operation_mode: str
    model: Optional[str]
    reason: str
    config: Dict[str, Any]
    credentials: Dict[str, Any]
    endpoint: Optional[str]
    timeout_ms: int
    retries: int
    protected: bool = False


@dataclass
class AdapterResult:
    data: Any
    provider_request_id: Optional[str] = None
    usage: Any = None
    extensions: Dict[str, Any] = field(default_factory=dict)


def _deep_merge(base: Mapping[str, Any], overlay: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    merged = copy.deepcopy(dict(base))
    if not isinstance(overlay, Mapping):
        return merged
    for key, value in overlay.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.strip().lower() in {"true", "1", "yes", "on"}:
            return True
        if value.strip().lower() in {"false", "0", "no", "off"}:
            return False
    return default


def _safe_int(value: Any, default: int, minimum: int = 0, maximum: Optional[int] = None) -> int:
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def _canonical_provider(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    provider = str(value).strip().lower().replace("-", "_")
    return PROVIDER_ALIASES.get(provider, provider)


def _canonical_capability(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    capability = str(value).strip().lower().replace("-", "_")
    return CAPABILITY_ALIASES.get(capability, capability)


def _normalize_timeout(value: Any, default_ms: int, max_ms: int, *, legacy_seconds: bool = False) -> int:
    if value in (None, ""):
        return min(default_ms, max_ms)
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return min(default_ms, max_ms)
    if timeout <= 0:
        return min(default_ms, max_ms)
    # Only the legacy `timeout` alias carries the seconds heuristic (spec 8.4);
    # canonical `timeout_ms` is always milliseconds.
    if legacy_seconds and timeout <= 600:
        timeout *= 1000
    return min(int(timeout), max_ms)


def _thaw(value: Any) -> Any:
    """Deep-copy runtime-frozen mappings/tuples into plain dicts/lists."""

    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_thaw(item) for item in value]
    return value


def _safe_exception(error: Exception) -> Tuple[str, str]:
    name = error.__class__.__name__.lower()
    if isinstance(error, TimeoutError) or "timeout" in name:
        return "provider_timeout", "The provider did not respond before the route timeout."
    if "ratelimit" in name or "rate_limit" in name or "too many" in str(error).lower():
        return "provider_rate_limited", "The provider rate limit was reached."
    if "auth" in name or "permission" in name or "unauthorized" in str(error).lower():
        return "provider_authentication", "The provider rejected the configured credential."
    if "connection" in name or "unavailable" in str(error).lower():
        return "provider_unavailable", "The provider is temporarily unavailable."
    return "internal_adapter_error", "The selected provider adapter failed."


def _content_from_response(response: Any) -> Any:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, Mapping):
        if "content" in response:
            return response.get("content")
        if "text" in response:
            return response.get("text")
    content = getattr(response, "content", None)
    if content is not None:
        return content
    text = getattr(response, "text", None)
    if text is not None:
        return text
    return str(response)


def _chat_data(content: Any, *, finish_reason: Optional[str] = "stop", citations: Optional[List[Any]] = None, tool_calls: Optional[List[Any]] = None, extensions: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    return {
        "role": "assistant",
        "content": content,
        "finish_reason": finish_reason,
        "citations": list(citations or []),
        "tool_calls": list(tool_calls or []),
        "provider_extensions": dict(extensions or {}),
    }


class RuntimeFacade:
    """Tolerant interface over optional server-injected runtime services."""

    def __init__(self, candidate: Any = None):
        self.raw = candidate

    def _call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        target = getattr(self.raw, name, None) if self.raw is not None else None
        if callable(target):
            return target(*args, **kwargs)
        return None

    def config(self) -> Dict[str, Any]:
        def layered(value: Mapping[str, Any]) -> Dict[str, Any]:
            # Runtime-injected configs (RouterRuntimeServices.config) arrive frozen
            # (MappingProxyType/tuples) and already layer-merged; thaw before merging.
            value = _thaw(value)
            layer_names = ("repository", "project", "organization", "runtime")
            if not any(isinstance(value.get(name), Mapping) for name in layer_names):
                return dict(value)
            merged: Dict[str, Any] = {}
            for name in layer_names:
                merged = _deep_merge(merged, _as_dict(value.get(name)))
            return merged

        if self.raw is None:
            return {}
        value = getattr(self.raw, "config", None)
        if callable(value):
            for key in ("machina_ai", "machina-ai", None):
                try:
                    result = value(key) if key is not None else value()
                except (TypeError, KeyError):
                    continue
                if isinstance(result, Mapping):
                    if key is None:
                        return layered(_as_dict(result.get("machina_ai") or result.get("machina-ai") or result))
                    return layered(result)
        if isinstance(value, Mapping):
            return layered(_as_dict(value.get("machina_ai") or value.get("machina-ai") or value))
        return {}

    def scope(self) -> Dict[str, Any]:
        value = getattr(self.raw, "scope", None) if self.raw is not None else None
        if callable(value):
            try:
                value = value()
            except TypeError:
                value = None
        return _as_dict(value)

    def trusted_headers(self, incoming: Optional[Mapping[str, Any]] = None) -> Mapping[str, Any]:
        value = getattr(self.raw, "trusted_headers", None) if self.raw is not None else None
        if callable(value):
            try:
                value = value()
            except TypeError:
                try:
                    value = value(dict(incoming or {}))
                except TypeError:
                    value = None
        incoming = incoming or {}
        if isinstance(value, Mapping):
            return {
                key: (incoming.get(key) if marker is True else marker)
                for key, marker in value.items()
                if key in incoming or marker is not True
            }
        if isinstance(value, (set, list, tuple)):
            return {key: incoming[key] for key in value if key in incoming}
        return {}

    def adapter(self, provider: str) -> Any:
        result = self._call("adapter", provider)
        if result is None:
            result = self._call("get_adapter", provider)
        return result

    def delegate(self, connector: str, command: str, payload: Mapping[str, Any]) -> Any:
        # The server injects `machina_delegate` (bound RouterRuntimeServices.delegate)
        # into the module namespace; prefer it, then the runtime object's own method.
        handlers: List[Any] = []
        module_delegate = globals().get("machina_delegate")
        if callable(module_delegate):
            handlers.append(module_delegate)
        raw_delegate = getattr(self.raw, "delegate", None) if self.raw is not None else None
        if callable(raw_delegate) and all(raw_delegate is not handler and raw_delegate != handler for handler in handlers):
            handlers.append(raw_delegate)
        if not handlers:
            return None
        last_error: Optional[Exception] = None
        for handler in handlers:
            # Runtime contract first: delegate(target_name, request_data, command=command).
            attempts = (
                lambda h=handler: h(connector, dict(payload), command=command),
                lambda h=handler: h(connector=connector, command=command, params=dict(payload)),
                lambda h=handler: h(connector, command, dict(payload)),
                lambda h=handler: h({"connector": connector, "command": command, "params": dict(payload)}),
            )
            for attempt in attempts:
                try:
                    return attempt()
                except TypeError as error:
                    last_error = error
        if last_error:
            raise last_error
        return None

    def task_call(self, action: str, payload: Mapping[str, Any]) -> Any:
        if self.raw is None:
            return None
        service = getattr(self.raw, "task", None) or getattr(self.raw, "tasks", None)
        if service is None:
            return None
        if callable(service):
            try:
                return service(action, dict(payload))
            except TypeError:
                try:
                    return service(action=action, payload=dict(payload))
                except TypeError:
                    pass
        method = getattr(service, action, None)
        if callable(method):
            return method(dict(payload))
        # RouterTaskStore contract: ownership ledger with create/get/list/update/delete.
        data = _as_dict(payload)
        task_id = data.get("task_id")
        try:
            if action == "authorize" and callable(getattr(service, "get", None)):
                if not task_id:
                    return {"authorized": False}
                record = service.get(str(task_id))
                return {"authorized": bool(record)}
            if action == "record" and callable(getattr(service, "create", None)):
                if not task_id:
                    return None
                provider = str(data.get("provider") or "unknown")
                route_identity = str(data.get("route") or f"{provider}:{data.get('model') or '-'}:video")
                metadata = {key: value for key, value in data.items() if key not in {"task_id", "provider", "route"}}
                service.create(str(task_id), route=route_identity, provider=provider, metadata=metadata)
                return {"recorded": True}
        except Exception:
            return {"authorized": False} if action == "authorize" else None
        return None

    def circuit_allow(self, route_id: str) -> bool:
        if self.raw is None:
            return True
        service = getattr(self.raw, "circuit", None)
        if service is None:
            return True
        if callable(service):
            try:
                result = service("allow", route_id)
            except TypeError:
                result = service(action="allow", route_id=route_id)
            return result is not False
        method = getattr(service, "allow", None)
        if callable(method):
            return method(route_id) is not False
        # RouterCircuitStore contract: before_request raises when the circuit is open.
        before = getattr(service, "before_request", None)
        if callable(before):
            try:
                before(route_id)
                return True
            except Exception:
                return False
        return True

    def circuit_record(self, route_id: str, success: bool, error_class: Optional[str] = None) -> None:
        if self.raw is None:
            return
        service = getattr(self.raw, "circuit", None)
        if service is None:
            return
        try:
            if callable(service):
                service("record", route_id, success=success, error_class=error_class)
                return
            record = getattr(service, "record", None)
            if callable(record):
                record(route_id, success=success, error_class=error_class)
                return
            # RouterCircuitStore contract.
            target = getattr(service, "record_success" if success else "record_failure", None)
            if callable(target):
                target(route_id)
        except Exception:
            return


class RequestNormalizer:
    def __init__(self, config: Mapping[str, Any], runtime: RuntimeFacade):
        self.config = config
        self.runtime = runtime

    def _extract(self, canonical: str, sources: Sequence[Tuple[str, Mapping[str, Any]]], conflicts: List[str]) -> Any:
        aliases = FIELD_ALIASES.get(canonical, ())
        hits: List[Tuple[str, str, Any]] = []
        # Scan every source so cross-source conflicts are recorded (spec 8.1);
        # precedence stays first-source-wins, canonical before aliases per source.
        for source_name, source in sources:
            if canonical in source and source.get(canonical) not in (None, ""):
                hits.append((source_name, canonical, source.get(canonical)))
            for alias in aliases:
                if alias in source and source.get(alias) not in (None, ""):
                    hits.append((source_name, alias, source.get(alias)))
        if not hits:
            return None
        chosen_source = hits[0][0]
        same_source = [hit for hit in hits if hit[0] == chosen_source]
        chosen = same_source[0]
        for _, alias, value in same_source[1:]:
            if value != chosen[2]:
                conflicts.append(f"{canonical}:{chosen[1]}!={alias}")
        for later_name, alias, value in hits[len(same_source):]:
            if value != chosen[2]:
                conflicts.append(f"{canonical}:{chosen_source}!={later_name}.{alias}")
        return chosen[2]

    def normalize(self, command: str, params: Optional[Mapping[str, Any]]) -> NormalizedRequest:
        raw = _as_dict(params)
        nested_params = _as_dict(raw.get("params"))
        headers = {key: value for key, value in _as_dict(raw.get("headers")).items() if key in HEADER_FIELDS}
        trusted_headers = {key: value for key, value in self.runtime.trusted_headers(headers).items() if key in HEADER_FIELDS}
        path_attributes = {key: value for key, value in _as_dict(raw.get("path_attribute")).items() if key in PATH_FIELDS}
        sources: List[Tuple[str, Mapping[str, Any]]] = [
            ("top_level", raw),
            ("params", nested_params),
            ("trusted_headers", trusted_headers),
            ("headers", headers),
            ("path_attribute", path_attributes),
        ]
        conflicts: List[str] = []
        canonical_command = str(raw.get("command") or command or "").strip()
        if canonical_command not in COMMANDS:
            raise RouterError("invalid_request", "The requested router command is not recognized.")
        inferred_capability, default_mode = COMMANDS[canonical_command]
        capability = _canonical_capability(raw.get("capability")) or inferred_capability
        operation_mode = str(raw.get("operation_mode") or default_mode).strip().lower()
        if canonical_command == "invoke_embedding" and operation_mode not in {"factory", "execute"}:
            raise RouterError("invalid_request", "invoke_embedding operation_mode must be factory or execute.")
        if canonical_command != "invoke_embedding":
            operation_mode = default_mode

        policy = _as_dict(self.config.get("policy"))
        profile = str(raw.get("profile") or nested_params.get("profile") or policy.get("default_profile") or "balanced").strip().lower()
        provider = _canonical_provider(raw.get("provider") or nested_params.get("provider"))
        model = self._extract("model", sources, conflicts)
        model = str(model).strip() if model not in (None, "") else None

        options = _as_dict(raw.get("options"))
        option_fields = (
            "temperature", "max_tokens", "max_output_tokens", "response_format", "stream", "seed",
            "language", "language_code", "voice", "voice_id", "output_format", "operation", "task_id",
            "poll_after_ms", "grounding", "search", "tools", "dimensions", "aspect_ratio", "duration",
            "negative_prompt", "idempotency_key", "provider_options", "input_kind", "size", "quality", "style",
        )
        for field_name in option_fields:
            value = self._extract(field_name, sources, conflicts)
            if value is not None and field_name not in options:
                options[field_name] = value
        self._extract("timeout_ms", sources, conflicts)  # conflict telemetry only
        timeout_value: Any = None
        timeout_is_legacy = False
        for _, source in sources:
            if source.get("timeout_ms") not in (None, ""):
                timeout_value = source.get("timeout_ms")
                break
            if source.get("timeout") not in (None, ""):
                timeout_value = source.get("timeout")
                timeout_is_legacy = True
                break
        options["timeout_ms"] = _normalize_timeout(
            timeout_value,
            _safe_int(policy.get("default_timeout_ms"), 30000),
            _safe_int(policy.get("max_timeout_ms"), 120000),
            legacy_seconds=timeout_is_legacy,
        )
        if _as_bool(options.get("stream")):
            raise RouterError("unsupported_option", "Streaming is not supported by the v1 router contract.")

        input_data = _as_dict(raw.get("input"))
        for field_name in ("messages", "prompt", "texts", "text", "input", "audio_path", "image_paths", "image_path", "url", "audio_url", "image_url"):
            value = self._extract(field_name, sources, conflicts)
            if value is not None and field_name not in input_data:
                input_data[field_name] = value
        if "audio_path" not in input_data:
            input_data["audio_path"] = self._extract("audio_path", sources, conflicts)
        audio = input_data.get("audio_path")
        if isinstance(audio, Sequence) and not isinstance(audio, (str, bytes)):
            input_data["audio_path"] = audio[0] if audio else None
        if "image_paths" not in input_data:
            images = self._extract("image_paths", sources, conflicts)
            if images is not None:
                input_data["image_paths"] = images if isinstance(images, list) else [images]
        if canonical_command == "edit_image":
            options.setdefault("operation", "edit")
        if canonical_command == "embed_query":
            options["input_kind"] = "query"
        if canonical_command == "embed_documents":
            options["input_kind"] = "documents"

        security: Dict[str, Any] = {}
        security_sources: List[Tuple[str, Mapping[str, Any]]] = [
            ("trusted_headers", trusted_headers),
            ("top_level", raw),
            ("params", nested_params),
            ("headers", headers),
        ]
        for field_name in SECURITY_FIELDS | {"project", "organization", "location"}:
            value = self._extract(field_name, security_sources, conflicts)
            if value not in (None, ""):
                security[field_name] = value
        if trusted_headers.get("api_key") or trusted_headers.get("credential"):
            security["_credential_trusted"] = True

        return NormalizedRequest(
            command=canonical_command,
            capability=capability,
            operation_mode=operation_mode,
            profile=profile,
            provider=provider,
            model=model,
            options=options,
            input=input_data,
            output=_as_dict(raw.get("output")),
            metadata=_as_dict(raw.get("metadata")),
            security=security,
            conflicts=conflicts,
            raw=raw,
        )


class MediaSecurity:
    def __init__(self, config: Mapping[str, Any]):
        self.config = config
        media = _as_dict(config.get("media"))
        roots = list(media.get("allowed_roots") or [])
        env_root = os.getenv("MACHINA_WORK_DIR")
        if env_root:
            roots.append(env_root)
        if not roots:
            roots.append(os.getcwd())
        self.roots = [Path(root).expanduser().resolve() for root in roots]
        self.max_bytes = _safe_int(media.get("max_input_bytes"), 25 * 1024 * 1024, minimum=1)

    def local_input(self, raw_path: Any, expected_prefix: Optional[str] = None) -> Path:
        if not raw_path or not isinstance(raw_path, (str, os.PathLike)):
            raise RouterError("input_file_invalid", "A valid local media path is required.")
        path = Path(raw_path).expanduser().resolve()
        if not any(path == root or root in path.parents for root in self.roots):
            raise RouterError("input_file_invalid", "The media path is outside the approved work directory.")
        if not path.is_file():
            raise RouterError("input_file_invalid", "The media input file does not exist.")
        if path.stat().st_size > self.max_bytes:
            raise RouterError("input_file_invalid", "The media input exceeds the configured size limit.")
        mime, _ = mimetypes.guess_type(path.name)
        if expected_prefix and mime and not mime.startswith(expected_prefix):
            raise RouterError("input_file_invalid", "The media input type is not accepted for this operation.")
        return path

    def output_path(self, requested: Any, suffix: str, prefix: str) -> Path:
        root = self.roots[0]
        root.mkdir(parents=True, exist_ok=True)
        if requested:
            path = Path(str(requested)).expanduser().resolve()
            if not any(path == allowed or allowed in path.parents for allowed in self.roots):
                raise RouterError("input_file_invalid", "The output path is outside the approved work directory.")
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        name = f"{SAFE_FILENAME.sub('-', prefix).strip('-') or 'artifact'}-{uuid.uuid4().hex}{suffix}"
        return root / name

    def remote_url(self, raw_url: Any) -> str:
        policy = _as_dict(self.config.get("policy"))
        if not _as_bool(policy.get("allow_remote_media")):
            raise RouterError("policy_endpoint_not_allowed", "Remote media inputs are disabled by runtime policy.")
        parsed = urlparse(str(raw_url or ""))
        allowed_schemes = set(_as_dict(self.config.get("media")).get("allowed_schemes") or ["https"])
        if parsed.scheme not in allowed_schemes or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise RouterError("policy_endpoint_not_allowed", "The remote media URL is not allowed.")
        allowed_hosts = set(policy.get("allowed_remote_media_hosts") or [])
        if parsed.hostname not in allowed_hosts:
            raise RouterError("policy_endpoint_not_allowed", "The remote media host is not allowlisted.")
        _reject_unsafe_host(parsed.hostname)
        return parsed.geturl()


def _reject_unsafe_host(hostname: str) -> None:
    lowered = hostname.strip().lower().rstrip(".")
    if lowered in {"localhost", "metadata.google.internal"}:
        raise RouterError("policy_endpoint_not_allowed", "The endpoint host is not allowed.")
    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise RouterError("policy_endpoint_not_allowed", "The endpoint host could not be validated.")
    for address in addresses:
        ip_text = address[4][0]
        ip = ipaddress.ip_address(ip_text)
        if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise RouterError("policy_endpoint_not_allowed", "The endpoint resolves to a protected network address.")


def _validate_endpoint(endpoint: str, allowed_hosts: Iterable[str], *, protected: bool = False) -> str:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise RouterError("policy_endpoint_not_allowed", "The provider endpoint is not allowed.")
    allowed = set(allowed_hosts)
    if protected:
        return endpoint.rstrip("/")
    if parsed.hostname not in allowed:
        raise RouterError("policy_endpoint_not_allowed", "The provider endpoint host is not allowlisted.")
    _reject_unsafe_host(parsed.hostname)
    return endpoint.rstrip("/")


class PolicyEngine:
    def __init__(self, config: Mapping[str, Any], runtime: RuntimeFacade):
        self.config = config
        self.runtime = runtime

    def _provider_config(self, provider: str) -> Dict[str, Any]:
        providers = _as_dict(self.config.get("providers"))
        conf = _as_dict(providers.get(provider))
        if provider == "nvidia_nim" and os.getenv("NVIDIA_NIM_CHAT_BASE_URL"):
            conf["enabled"] = True
        if not conf:
            raise RouterError("policy_provider_not_allowed", "The requested provider is not configured.")
        if not _as_bool(conf.get("enabled")):
            raise RouterError("policy_provider_not_allowed", "The requested provider is disabled by runtime policy.")
        return conf

    def _profile_candidate(self, request: NormalizedRequest) -> Tuple[Dict[str, Any], str, bool]:
        """Resolve a route candidate per spec 12.1/13: family and capability remaps
        apply before profile resolution; a profile remap applies only when it carries
        an entry for the request's capability or is itself a direct provider candidate.

        Returns (candidate, reason, prefer_candidate_model).
        """
        remaps = _as_dict(self.config.get("remaps"))
        if request.model:
            family_remap = _as_dict(_as_dict(remaps.get("families")).get(request.model))
            if family_remap.get("provider"):
                # The requested "model" is an abstract family alias; the remap's own
                # model must win over the alias string.
                return family_remap, f"remap:family:{request.model}", True
        capability_remap = _as_dict(_as_dict(remaps.get("capabilities")).get(request.capability))
        if capability_remap.get("provider"):
            return capability_remap, f"remap:capability:{request.capability}", False
        profile_remap = _as_dict(_as_dict(remaps.get("profiles")).get(request.profile))
        if profile_remap:
            entry = _as_dict(profile_remap.get(request.capability))
            if entry.get("provider"):
                return entry, f"remap:profile:{request.profile}", False
            if profile_remap.get("provider"):
                return dict(profile_remap), f"remap:profile:{request.profile}", False
        profile = _as_dict(_as_dict(self.config.get("profiles")).get(request.profile))
        candidates = profile.get(request.capability)
        if isinstance(candidates, list) and candidates:
            return _as_dict(candidates[0]), f"profile:{request.profile}", False
        defaults = _as_dict(_as_dict(self.config.get("defaults")).get(request.capability))
        if defaults:
            return defaults, f"default:{request.capability}", False
        raise RouterError("unsupported_capability", "No allowed route is configured for this capability.")

    def _read_env(self, conf: Mapping[str, Any], field_name: str) -> Any:
        direct = conf.get(field_name)
        if direct not in (None, ""):
            return direct
        env_name = conf.get(f"{field_name}_env") or conf.get(f"{field_name}_ref")
        if env_name and os.getenv(str(env_name)) not in (None, ""):
            return os.getenv(str(env_name))
        for alias in conf.get(f"{field_name}_env_aliases") or []:
            if os.getenv(str(alias)) not in (None, ""):
                return os.getenv(str(alias))
        return None

    def _allowed_models(self, provider: str, conf: MutableMapping[str, Any], capability: str) -> List[str]:
        allowed = list(_as_dict(conf.get("allowed_models")).get(capability) or [])
        env_name = conf.get("allowed_models_env")
        if env_name and os.getenv(str(env_name)):
            env_models = [item.strip() for item in os.getenv(str(env_name), "").split(",") if item.strip()]
            allowed = env_models
        default_model = self._read_env(conf, "model")
        if default_model and not allowed:
            allowed = [str(default_model)]
        return allowed

    def route(
        self,
        request: NormalizedRequest,
        candidate: Optional[Mapping[str, Any]] = None,
        reason: Optional[str] = None,
        *,
        prefer_candidate_model: bool = False,
    ) -> Route:
        if candidate is None:
            if request.provider:
                candidate = {"provider": request.provider, "model": request.model}
                reason = "explicit_provider"
            else:
                candidate, reason, prefer_candidate_model = self._profile_candidate(request)
        candidate = _as_dict(candidate)
        provider = _canonical_provider(candidate.get("provider"))
        if not provider:
            raise RouterError("unsupported_capability", "The selected route does not identify a provider.")
        conf = self._provider_config(provider)
        allowed_models = self._allowed_models(provider, conf, request.capability)
        if prefer_candidate_model:
            # Fallback/family-remap candidates run with their own configured model;
            # a caller-pinned model must not leak across providers.
            model = candidate.get("model") or self._read_env(conf, "model")
        else:
            model = request.model or candidate.get("model") or self._read_env(conf, "model")
        if model is not None:
            model = str(model)
        if allowed_models and model not in allowed_models:
            raise RouterError("policy_model_not_allowed", "The selected model is not allowed for this runtime.")
        if not allowed_models and request.capability != "management":
            raise RouterError("unsupported_capability", "The provider is not enabled for this capability.")
        if request.capability == "embedding" and provider == "groq":
            raise RouterError("unsupported_capability", "Groq does not provide embeddings through this router.")

        policy = _as_dict(self.config.get("policy"))
        protected = _as_bool(conf.get("protected"))
        supplied_endpoint = request.security.get("endpoint") or request.security.get("base_url")
        callback_url = request.security.get("callback_url")
        if callback_url and callback_url not in set(policy.get("allowed_callback_urls") or []):
            raise RouterError("policy_endpoint_not_allowed", "The callback URL is not allowlisted by runtime policy.")
        if protected and supplied_endpoint:
            raise RouterError("policy_endpoint_not_allowed", "This route endpoint is controlled by runtime policy.")
        endpoint = self._read_env(conf, "endpoint")
        if supplied_endpoint:
            if not _as_bool(policy.get("allow_custom_base_url")):
                raise RouterError("policy_endpoint_not_allowed", "Caller-supplied provider endpoints are disabled.")
            endpoint = supplied_endpoint
        if endpoint:
            endpoint = _validate_endpoint(
                str(endpoint),
                policy.get("allowed_endpoint_hosts") or [],
                protected=protected or (not supplied_endpoint),
            )

        credential = self._read_env(conf, "credential") or self._read_env(conf, "api_key")
        request_credential = request.security.get("api_key") or request.security.get("credential")
        if request_credential and not credential:
            trusted = _as_bool(request.security.get("_credential_trusted"))
            if not (trusted or _as_bool(policy.get("allow_workflow_credentials"))):
                raise RouterError("credential_missing", "Workflow-supplied credentials are disabled by runtime policy.")
            credential = request_credential
        if not credential and _as_bool(conf.get("require_credential")):
            raise RouterError("credential_missing", "The provider credential is not configured for this runtime.")
        credentials = {
            "api_key": credential,
            "credential": credential,
            "project": self._read_env(conf, "project") or request.security.get("project"),
            "organization": self._read_env(conf, "organization") or request.security.get("organization"),
            "deployment": self._read_env(conf, "deployment"),
            "api_version": self._read_env(conf, "api_version") or conf.get("api_version"),
            "location": self._read_env(conf, "location") or conf.get("location") or request.security.get("location"),
        }
        if request.security.get("deployment") and not credentials["deployment"]:
            if protected:
                raise RouterError("policy_endpoint_not_allowed", "This deployment is controlled by runtime policy.")
            credentials["deployment"] = request.security.get("deployment")
        if request.security.get("api_version") and not credentials["api_version"]:
            credentials["api_version"] = request.security.get("api_version")

        adapter_name = str(conf.get("adapter") or provider)
        timeout_ms = _safe_int(request.options.get("timeout_ms"), 30000, minimum=1, maximum=_safe_int(policy.get("max_timeout_ms"), 120000))
        retries = _safe_int(conf.get("retries", policy.get("max_retries", 0)), 0, minimum=0, maximum=5)
        return Route(
            provider=provider,
            adapter=adapter_name,
            capability=request.capability,
            operation_mode=request.operation_mode,
            model=model,
            reason=str(reason or "policy"),
            config=conf,
            credentials=credentials,
            endpoint=endpoint,
            timeout_ms=timeout_ms,
            retries=retries,
            protected=protected,
        )

    def fallback_candidates(self, route: Route, request: NormalizedRequest) -> List[Tuple[Dict[str, Any], str]]:
        """Return raw fallback candidate specs; routes are built lazily at dispatch
        time so one unbuildable fallback cannot poison a healthy primary."""
        if route.protected and _as_bool(route.config.get("fail_closed", True)):
            return []
        configured = _as_dict(_as_dict(self.config.get("fallbacks")).get(request.capability))
        chain = configured.get(route.provider) or []
        if isinstance(chain, Mapping):
            chain = [chain]
        specs: List[Tuple[Dict[str, Any], str]] = []
        for index, candidate in enumerate(chain if isinstance(chain, (list, tuple)) else []):
            if isinstance(candidate, str):
                candidate = {"provider": candidate}
            candidate = _as_dict(candidate)
            if candidate.get("provider"):
                specs.append((candidate, f"fallback:{route.provider}:{index + 1}"))
        return specs


class ProviderAdapter:
    provider_id = "base"
    capabilities: set = set()
    delegate_connector: Optional[str] = None

    def __init__(self, runtime: RuntimeFacade, media: MediaSecurity):
        self.runtime = runtime
        self.media = media

    def _delegate(self, command: str, route: Route, request: NormalizedRequest) -> Optional[AdapterResult]:
        if not self.delegate_connector:
            return None
        safe_params = {**copy.deepcopy(request.input), **copy.deepcopy(request.options)}
        safe_params.update({
            "provider": route.provider,
            "model": route.model,
            "model_name": route.model,
            "timeout_ms": route.timeout_ms,
        })
        # Delegate-target connectors read credentials from flat params (for example
        # groq.py params.get("api_key")) as well as headers, so carry both.
        safe_headers: Dict[str, Any] = {}
        if route.credentials.get("api_key"):
            safe_headers["api_key"] = route.credentials["api_key"]
            safe_params["api_key"] = route.credentials["api_key"]
        if route.credentials.get("credential"):
            safe_headers["credential"] = route.credentials["credential"]
            safe_params["credential"] = route.credentials["credential"]
        if route.credentials.get("project"):
            safe_headers["project_id"] = route.credentials["project"]
            safe_params["project_id"] = route.credentials["project"]
        if route.credentials.get("organization"):
            safe_headers["organization"] = route.credentials["organization"]
            safe_params["organization"] = route.credentials["organization"]
        if route.credentials.get("location"):
            safe_params["location"] = route.credentials["location"]
        if request.security.get("callback_url"):
            safe_params["callback_url"] = request.security["callback_url"]
        payload: Dict[str, Any] = {
            **safe_params,
            "params": safe_params,
            "headers": safe_headers,
            "output": copy.deepcopy(request.output),
        }
        task_id = request.options.get("task_id") or request.input.get("task_id")
        if task_id:
            payload["path_attribute"] = {"id": task_id, "task_id": task_id}
        delegated = self.runtime.delegate(self.delegate_connector, command, payload)
        if delegated is None:
            return None
        if isinstance(delegated, Mapping):
            status = delegated.get("status")
            if status is False or str(status).lower() == "error":
                metadata = _as_dict(delegated.get("metadata"))
                raise RouterError(str(metadata.get("error_class") or "internal_adapter_error"), "The delegated provider operation failed.")
            return AdapterResult(
                delegated.get("data"),
                provider_request_id=_as_dict(delegated.get("metadata")).get("provider_request_id"),
                usage=_as_dict(delegated.get("metadata")).get("usage"),
            )
        return AdapterResult(delegated)

    def create_chat_model(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        raise RouterError("unsupported_capability", "This provider does not support chat model factories.")

    def invoke_chat(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        model = self.create_chat_model(route, request).data
        messages = request.input.get("messages") or request.input.get("prompt") or request.input.get("input")
        if messages in (None, ""):
            raise RouterError("invalid_request", "Chat execution requires messages or a prompt.")
        try:
            response = model.invoke(messages)
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)
        return AdapterResult(_chat_data(_content_from_response(response)))

    def create_embedding_model(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        raise RouterError("unsupported_capability", "This provider does not support embedding factories.")

    def embed(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        model = self.create_embedding_model(route, request).data
        values = request.input.get("texts") or request.input.get("input") or request.input.get("text")
        if values in (None, ""):
            raise RouterError("invalid_request", "Embedding execution requires input text.")
        try:
            if request.options.get("input_kind") == "query" or isinstance(values, str):
                data = model.embed_query(values if isinstance(values, str) else values[0])
            else:
                data = model.embed_documents(list(values))
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)
        return AdapterResult(data)

    def invoke_search(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        return self.invoke_chat(route, request)

    def invoke_image(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        raise RouterError("unsupported_capability", "This provider does not support image generation through the router.")

    def invoke_video(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        raise RouterError("unsupported_capability", "This provider does not support video operations through the router.")

    def transcribe(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        raise RouterError("unsupported_capability", "This provider does not support transcription through the router.")

    def invoke_tts(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        raise RouterError("unsupported_capability", "This provider does not support text to speech through the router.")

    def voice(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        raise RouterError("unsupported_capability", "This provider does not support the requested voice operation.")

    def invoke_music(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        raise RouterError("unsupported_capability", "This provider does not support music generation through the router.")


def _vertex_service_account_credentials(credential: Any) -> Any:
    """Build google.auth service-account credentials from a router credential.

    Shared by the Gemini (``vertex_ai``) and Claude (``vertex_anthropic``)
    routes, which authenticate to Vertex with the same service-account JSON.
    Returns ``None`` when nothing is configured (ADC is used) and passes an
    already-built credentials object through unchanged.
    """
    if not credential:
        return None
    if not isinstance(credential, (str, bytes, Mapping)):
        return credential
    try:
        info = json.loads(credential) if isinstance(credential, (str, bytes)) else dict(credential)
        service_account = importlib.import_module("google.oauth2.service_account")
        # Unscoped service-account credentials fail token refresh with
        # "invalid_scope" on clients that do not apply default scopes
        # (VertexAIEmbeddings, unlike ChatVertexAI).
        return service_account.Credentials.from_service_account_info(
            info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
    except Exception:
        raise RouterError("credential_invalid", "The configured Vertex credential is invalid.")


class GoogleGenAIAdapter(ProviderAdapter):
    provider_id = "vertex_ai"
    capabilities = {"chat", "embedding", "search_answer", "image", "video", "tts", "voice", "music"}
    delegate_connector = "google-genai"

    def _credentials(self, route: Route) -> Any:
        return _vertex_service_account_credentials(route.credentials.get("credential"))

    def create_chat_model(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        delegated = self._delegate("invoke_prompt", route, request)
        if delegated:
            return delegated
        try:
            if route.provider == "vertex_ai":
                module = importlib.import_module("langchain_google_vertexai")
                kwargs = {
                    "model_name": route.model,
                    "project": route.credentials.get("project"),
                    "location": route.credentials.get("location") or "global",
                    "temperature": request.options.get("temperature", 0.2),
                    "request_parallelism": 1,
                }
                credentials = self._credentials(route)
                if credentials is not None:
                    kwargs["credentials"] = credentials
                model = module.ChatVertexAI(**{k: v for k, v in kwargs.items() if v is not None})
            else:
                module = importlib.import_module("langchain_google_genai")
                model = module.ChatGoogleGenerativeAI(
                    model=route.model,
                    google_api_key=route.credentials.get("api_key"),
                    temperature=request.options.get("temperature", 0.2),
                    timeout=route.timeout_ms / 1000.0,
                )
        except RouterError:
            raise
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)
        return AdapterResult(model)

    def create_embedding_model(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        delegated = self._delegate("invoke_embedding", route, request)
        if delegated:
            return delegated
        try:
            if route.provider == "vertex_ai":
                module = importlib.import_module("langchain_google_vertexai")
                kwargs = {
                    "model_name": route.model,
                    "project": route.credentials.get("project"),
                    "location": route.credentials.get("location") or "global",
                }
                credentials = self._credentials(route)
                if credentials is not None:
                    kwargs["credentials"] = credentials
                model = module.VertexAIEmbeddings(**{k: v for k, v in kwargs.items() if v is not None})
            else:
                module = importlib.import_module("langchain_google_genai")
                model = module.GoogleGenerativeAIEmbeddings(model=route.model, google_api_key=route.credentials.get("api_key"))
        except RouterError:
            raise
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)
        return AdapterResult(model)

    def invoke_search(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        delegated = self._delegate("invoke_search", route, request)
        if delegated:
            data = delegated.data
            if not isinstance(data, Mapping) or "role" not in data:
                data = _chat_data(_content_from_response(data))
            delegated.data = data
            return delegated
        return self.invoke_chat(route, request)

    def invoke_image(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        delegated = self._delegate("invoke_image", route, request)
        if delegated:
            return delegated
        raise RouterError("provider_unavailable", "Google image generation requires the runtime delegation service.")

    def invoke_video(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        delegated = self._delegate("invoke_video", route, request)
        if delegated:
            return delegated
        raise RouterError("provider_unavailable", "Google video generation requires the runtime delegation service.")

    def invoke_tts(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        delegated = self._delegate("invoke_tts", route, request)
        if delegated:
            return delegated
        raise RouterError("provider_unavailable", "Google TTS requires the runtime delegation service.")

    def voice(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        delegated = self._delegate(request.command, route, request)
        if delegated:
            return delegated
        raise RouterError("provider_unavailable", "Google custom voice operations require the runtime delegation service.")

    def invoke_music(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        delegated = self._delegate("invoke_music", route, request)
        if delegated:
            return delegated
        raise RouterError("provider_unavailable", "Google music generation requires the runtime delegation service.")


class VertexAnthropicAdapter(ProviderAdapter):
    """Anthropic Claude on Vertex AI Model Garden.

    Reuses the same Vertex service-account as the Gemini route (``vertex_ai``);
    Model Garden bills Claude under the GCP project, so no separate Anthropic
    credential is required.  Chat only — Claude on Vertex has no embedding,
    search-grounding, or media parity, so those capabilities fall through to the
    base ``unsupported_capability`` guard by design.
    """

    provider_id = "vertex_anthropic"
    capabilities = {"chat"}
    # Claude requires an explicit output cap and the langchain default is 1024,
    # which truncates long report/article generations.  Use a generous default
    # whenever the workflow does not set ``max_tokens`` (Entain workflows do not).
    default_max_tokens = 8192

    def _credentials(self, route: Route) -> Any:
        return _vertex_service_account_credentials(route.credentials.get("credential"))

    def create_chat_model(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        try:
            module = importlib.import_module("langchain_google_vertexai.model_garden")
            kwargs = {
                "model_name": route.model,
                "project": route.credentials.get("project"),
                "location": route.credentials.get("location") or "global",
                "max_tokens": _safe_int(
                    request.options.get("max_tokens"),
                    self.default_max_tokens,
                    minimum=1,
                    maximum=64000,
                ),
            }
            # Claude 4.6+ (Sonnet 5, Opus 4.7/4.8, …) reject sampling params with
            # a 400 ("temperature is deprecated for this model"), so no default is
            # applied. The platform workflow prompt runner also injects
            # ``temperature: 0`` into every prompt task regardless of author
            # intent, so 0/None are treated as "unset" — only an explicit
            # non-zero temperature is forwarded on this route.
            if request.options.get("temperature"):
                kwargs["temperature"] = request.options["temperature"]
            credentials = self._credentials(route)
            if credentials is not None:
                kwargs["credentials"] = credentials
            model = module.ChatAnthropicVertex(**{k: v for k, v in kwargs.items() if v is not None})
        except RouterError:
            raise
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)
        return AdapterResult(model)


class OpenAICompatibleAdapter(ProviderAdapter):
    provider_id = "openai_compatible"
    capabilities = {"chat", "embedding", "transcription", "image", "search_answer"}

    def _chat_kwargs(self, route: Route, request: NormalizedRequest) -> Dict[str, Any]:
        kwargs = {
            "model": route.model,
            "api_key": route.credentials.get("api_key"),
            "temperature": request.options.get("temperature", 0.2),
            "timeout": route.timeout_ms / 1000.0,
        }
        if route.endpoint:
            kwargs["base_url"] = route.endpoint
        if route.credentials.get("organization"):
            kwargs["organization"] = route.credentials["organization"]
        if route.credentials.get("project"):
            kwargs["default_headers"] = {"OpenAI-Project": route.credentials["project"]}
        if request.options.get("max_tokens") is not None:
            kwargs["max_tokens"] = request.options["max_tokens"]
        return {key: value for key, value in kwargs.items() if value is not None}

    def create_chat_model(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        try:
            module = importlib.import_module("langchain_openai")
            return AdapterResult(module.ChatOpenAI(**self._chat_kwargs(route, request)))
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)

    def create_embedding_model(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        try:
            module = importlib.import_module("langchain_openai")
            kwargs = self._chat_kwargs(route, request)
            kwargs.pop("temperature", None)
            kwargs.pop("max_tokens", None)
            return AdapterResult(module.OpenAIEmbeddings(**kwargs))
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)

    def _client(self, route: Route) -> Any:
        try:
            module = importlib.import_module("openai")
            kwargs = {"api_key": route.credentials.get("api_key"), "timeout": route.timeout_ms / 1000.0}
            if route.endpoint:
                kwargs["base_url"] = route.endpoint
            if route.credentials.get("organization"):
                kwargs["organization"] = route.credentials["organization"]
            return module.OpenAI(**{k: v for k, v in kwargs.items() if v is not None})
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)

    def invoke_chat(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        messages = request.input.get("messages")
        if not messages:
            prompt = request.input.get("prompt") or request.input.get("input")
            if prompt in (None, ""):
                raise RouterError("invalid_request", "Chat execution requires messages or a prompt.")
            messages = [{"role": "user", "content": prompt}]
        kwargs = {"model": route.model, "messages": messages, "stream": False}
        for key in ("temperature", "max_tokens", "response_format", "tools"):
            if request.options.get(key) is not None:
                kwargs[key] = request.options[key]
        try:
            response = self._client(route).chat.completions.create(**kwargs)
            choice = response.choices[0]
            message = choice.message
            content = getattr(message, "content", None)
            tool_calls = getattr(message, "tool_calls", None) or []
            usage = getattr(response, "usage", None)
            if usage is not None and hasattr(usage, "model_dump"):
                usage = usage.model_dump()
            return AdapterResult(
                _chat_data(content, finish_reason=getattr(choice, "finish_reason", None), tool_calls=tool_calls),
                provider_request_id=getattr(response, "id", None),
                usage=usage,
            )
        except RouterError:
            raise
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)

    def invoke_image(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        prompt = request.input.get("prompt") or request.input.get("input")
        if not prompt:
            raise RouterError("invalid_request", "Image generation requires a prompt.")
        if request.options.get("operation") == "edit":
            raise RouterError("unsupported_capability", "Image editing is not enabled for this OpenAI-compatible route.")
        try:
            kwargs = {"model": route.model, "prompt": prompt, "response_format": "b64_json"}
            for key in ("size", "quality", "style"):
                if request.options.get(key) is not None:
                    kwargs[key] = request.options[key]
            response = self._client(route).images.generate(**kwargs)
            item = response.data[0]
            encoded = getattr(item, "b64_json", None)
            if not encoded:
                raise RouterError("provider_bad_response", "The image provider returned no inline artifact.", transient=True)
            content = base64.b64decode(encoded)
            output = self.media.output_path(request.output.get("path"), ".png", "openai-image")
            output.write_bytes(content)
            return AdapterResult(
                {"path": output.name, "bytes": len(content), "media_type": "image/png"},
                provider_request_id=getattr(response, "id", None),
            )
        except RouterError:
            raise
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)

    def transcribe(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        path = self.media.local_input(request.input.get("audio_path"), "audio/")
        try:
            with path.open("rb") as audio:
                response = self._client(route).audio.transcriptions.create(model=route.model, file=audio)
            return AdapterResult({"text": _content_from_response(response), "segments": getattr(response, "segments", None)})
        except RouterError:
            raise
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)


class AzureFoundryAdapter(OpenAICompatibleAdapter):
    provider_id = "azure_foundry"
    capabilities = {"chat", "embedding"}

    def _azure_kwargs(self, route: Route, request: NormalizedRequest) -> Dict[str, Any]:
        return {
            "api_key": route.credentials.get("api_key"),
            "azure_endpoint": route.endpoint,
            "api_version": route.credentials.get("api_version"),
            "azure_deployment": route.credentials.get("deployment") or route.model,
            "timeout": route.timeout_ms / 1000.0,
            "temperature": request.options.get("temperature", 0.2),
        }

    def create_chat_model(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        try:
            module = importlib.import_module("langchain_openai")
            return AdapterResult(module.AzureChatOpenAI(**{k: v for k, v in self._azure_kwargs(route, request).items() if v is not None}))
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)

    def create_embedding_model(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        try:
            module = importlib.import_module("langchain_openai")
            kwargs = self._azure_kwargs(route, request)
            kwargs.pop("temperature", None)
            return AdapterResult(module.AzureOpenAIEmbeddings(**{k: v for k, v in kwargs.items() if v is not None}))
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)

    def _client(self, route: Route) -> Any:
        try:
            module = importlib.import_module("openai")
            return module.AzureOpenAI(
                api_key=route.credentials.get("api_key"),
                azure_endpoint=route.endpoint,
                api_version=route.credentials.get("api_version"),
                timeout=route.timeout_ms / 1000.0,
            )
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)

    def invoke_chat(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        original = route.model
        route.model = route.credentials.get("deployment") or route.model
        try:
            return super().invoke_chat(route, request)
        finally:
            route.model = original


class GroqAdapter(ProviderAdapter):
    provider_id = "groq"
    capabilities = {"chat"}
    delegate_connector = "groq"

    def create_chat_model(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        delegated = self._delegate("invoke_prompt", route, request)
        if delegated:
            return delegated
        try:
            module = importlib.import_module("langchain_groq")
            kwargs = {
                "api_key": route.credentials.get("api_key"),
                "model_name": route.model,
                "temperature": request.options.get("temperature", 0.2),
                "timeout": route.timeout_ms / 1000.0,
            }
            return AdapterResult(module.ChatGroq(**{k: v for k, v in kwargs.items() if v is not None}))
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)


class PerplexityAdapter(OpenAICompatibleAdapter):
    provider_id = "perplexity"
    capabilities = {"chat", "search_answer"}

    def invoke_search(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        messages = request.input.get("messages")
        if not messages:
            prompt = request.input.get("prompt") or request.input.get("input")
            if not prompt:
                raise RouterError("invalid_request", "Search execution requires messages or a prompt.")
            messages = [{"role": "user", "content": prompt}]
        try:
            response = self._client(route).chat.completions.create(model=route.model, messages=messages, stream=False)
            choice = response.choices[0]
            citations = list(getattr(response, "citations", None) or [])
            usage = getattr(response, "usage", None)
            if usage is not None and hasattr(usage, "model_dump"):
                usage = usage.model_dump()
            return AdapterResult(
                _chat_data(getattr(choice.message, "content", None), finish_reason=getattr(choice, "finish_reason", None), citations=citations),
                provider_request_id=getattr(response, "id", None),
                usage=usage,
            )
        except RouterError:
            raise
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)


class XAIAdapter(OpenAICompatibleAdapter):
    provider_id = "xai"
    capabilities = {"chat", "search_answer"}

    def invoke_search(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        prompt = request.input.get("prompt") or request.input.get("input")
        if prompt in (None, ""):
            messages = request.input.get("messages") or []
            prompt = "\n".join(str(item.get("content", "")) for item in messages if isinstance(item, Mapping))
        if not prompt:
            raise RouterError("invalid_request", "Search execution requires a prompt or messages.")
        tools = request.options.get("tools") or [{"type": "web_search"}]
        try:
            response = self._client(route).responses.create(model=route.model, input=prompt, tools=tools)
            content = getattr(response, "output_text", None) or _content_from_response(response)
            citations = []
            for output in getattr(response, "output", None) or []:
                for item in getattr(output, "content", None) or []:
                    for annotation in getattr(item, "annotations", None) or []:
                        if hasattr(annotation, "model_dump"):
                            citations.append(annotation.model_dump())
            usage = getattr(response, "usage", None)
            if usage is not None and hasattr(usage, "model_dump"):
                usage = usage.model_dump()
            return AdapterResult(
                _chat_data(content, citations=citations, extensions={"tools": tools}),
                provider_request_id=getattr(response, "id", None),
                usage=usage,
            )
        except RouterError:
            raise
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)


class NvidiaNimAdapter(OpenAICompatibleAdapter):
    provider_id = "nvidia_nim"
    capabilities = {"chat"}
    delegate_connector = "nvidia-nim"

    def create_chat_model(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        # Preserve the provider connector contract: legacy nvidia-nim invoke_chat is a factory.
        delegated = self._delegate("invoke_chat", route, request)
        if delegated is not None:
            return delegated
        return super().create_chat_model(route, request)

    def invoke_chat(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        delegated = self._delegate("completion_receipt", route, request)
        if delegated is not None:
            data = delegated.data
            if isinstance(data, Mapping) and "output" in data:
                delegated.data = _chat_data(data.get("output"), extensions={"completion_receipt": dict(data)})
            return delegated
        return super().invoke_chat(route, request)


class StabilityAdapter(ProviderAdapter):
    provider_id = "stability"
    capabilities = {"image"}
    delegate_connector = "stability"

    def invoke_image(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        delegated = self._delegate("generate_image", route, request)
        if delegated:
            return delegated
        prompt = request.input.get("prompt") or request.input.get("input")
        if not prompt:
            raise RouterError("invalid_request", "Image generation requires a prompt.")
        try:
            requests = importlib.import_module("requests")
            endpoint = f"{route.endpoint.rstrip('/')}/v2beta/stable-image/generate/core"
            response = requests.post(
                endpoint,
                headers={"Authorization": f"Bearer {route.credentials.get('api_key')}", "Accept": "image/*"},
                files={"none": (None, "")},
                data={"prompt": prompt, "output_format": request.options.get("output_format", "png")},
                timeout=route.timeout_ms / 1000.0,
                allow_redirects=False,
            )
            response.raise_for_status()
            suffix = "." + str(request.options.get("output_format") or "png").lstrip(".")
            output = self.media.output_path(request.output.get("path"), suffix, "stability-image")
            output.write_bytes(response.content)
            return AdapterResult({"path": output.name, "bytes": len(response.content), "media_type": response.headers.get("content-type")})
        except RouterError:
            raise
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)


class ElevenLabsAdapter(ProviderAdapter):
    provider_id = "elevenlabs"
    capabilities = {"tts", "voice"}
    delegate_connector = "elevenlabs"

    def invoke_tts(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        delegated = self._delegate("get_text_to_speech", route, request)
        if delegated:
            return delegated
        text = request.input.get("text") or request.input.get("prompt") or request.input.get("input")
        voice_id = request.options.get("voice_id") or request.options.get("voice")
        if not text or not voice_id:
            raise RouterError("invalid_request", "Text and voice_id are required for text to speech.")
        try:
            requests = importlib.import_module("requests")
            response = requests.post(
                f"{route.endpoint.rstrip('/')}/text-to-speech/{voice_id}",
                headers={"xi-api-key": route.credentials.get("api_key"), "content-type": "application/json"},
                json={"text": text, "model_id": route.model},
                timeout=route.timeout_ms / 1000.0,
                allow_redirects=False,
            )
            response.raise_for_status()
            output = self.media.output_path(request.output.get("path"), ".mp3", "elevenlabs-tts")
            output.write_bytes(response.content)
            return AdapterResult({"path": output.name, "bytes": len(response.content), "media_type": "audio/mpeg"})
        except RouterError:
            raise
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)

    def voice(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        command = "get_voices" if request.command in {"list_voices", "get_voices"} else request.command
        delegated = self._delegate(command, route, request)
        if delegated:
            return delegated
        raise RouterError("provider_unavailable", "Voice management requires the runtime delegation service.")


class GoogleSpeechAdapter(ProviderAdapter):
    provider_id = "google_speech"
    capabilities = {"transcription"}
    delegate_connector = "google-speech-to-text"

    def transcribe(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        delegated = self._delegate("invoke_transcribe", route, request)
        if delegated:
            return delegated
        path = self.media.local_input(request.input.get("audio_path"), "audio/")
        try:
            speech = importlib.import_module("google.cloud.speech")
            client_kwargs: Dict[str, Any] = {}
            credential = route.credentials.get("credential")
            if credential:
                info = json.loads(credential) if isinstance(credential, str) else credential
                service_account = importlib.import_module("google.oauth2.service_account")
                client_kwargs["credentials"] = service_account.Credentials.from_service_account_info(
                    info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
            client = speech.SpeechClient(**client_kwargs)
            audio = speech.RecognitionAudio(content=path.read_bytes())
            config = speech.RecognitionConfig(
                language_code=request.options.get("language_code") or request.options.get("language") or "en-US",
                model=route.model or "latest_long",
            )
            response = client.recognize(config=config, audio=audio)
            text = " ".join(result.alternatives[0].transcript for result in response.results if result.alternatives)
            return AdapterResult({"text": text, "segments": []})
        except RouterError:
            raise
        except Exception as error:
            error_class, message = _safe_exception(error)
            raise RouterError(error_class, message)


class BytePlusAdapter(ProviderAdapter):
    provider_id = "byteplus_modelark"
    capabilities = {"video"}
    delegate_connector = "byteplus-modelark"

    COMMAND_BY_OPERATION = {
        "create_task": "post-contents/generations/tasks",
        "get_task": "get-contents/generations/tasks/{id}",
        "list_tasks": "get-contents/generations/tasks",
        "delete_task": "delete-contents/generations/tasks/{id}",
        "wait_for_task": "get-contents/generations/tasks/{id}",
    }

    def invoke_video(self, route: Route, request: NormalizedRequest) -> AdapterResult:
        operation = str(request.options.get("operation") or "create_task")
        if operation not in self.COMMAND_BY_OPERATION:
            raise RouterError("invalid_request", "The requested video task operation is not supported.")
        command = self.COMMAND_BY_OPERATION[operation]
        delegated = self._delegate(command, route, request)
        if delegated:
            if not isinstance(delegated.data, Mapping):
                # list_tasks returns a list; preserve non-mapping payloads verbatim.
                return delegated
            data = dict(delegated.data)
            state = str(data.get("state") or data.get("status") or "queued").lower()
            state_map = {"pending": "queued", "processing": "running", "success": "succeeded", "completed": "succeeded", "error": "failed", "deleted": "cancelled"}
            data["state"] = state_map.get(state, state if state in {"queued", "running", "succeeded", "failed", "cancelled", "expired"} else "queued")
            data.setdefault("task_id", data.get("id"))
            data.setdefault("poll_after_ms", 5000)
            data.setdefault("result", None)
            delegated.data = data
            return delegated
        raise RouterError("provider_unavailable", "BytePlus video operations require the runtime delegation service.")


class AdapterRegistry:
    def __init__(self, runtime: RuntimeFacade, media: MediaSecurity):
        self.runtime = runtime
        self.media = media
        self.factories = {
            "google_genai": GoogleGenAIAdapter,
            "vertex_anthropic": VertexAnthropicAdapter,
            "openai_compatible": OpenAICompatibleAdapter,
            "azure_foundry": AzureFoundryAdapter,
            "groq": GroqAdapter,
            "perplexity": PerplexityAdapter,
            "xai": XAIAdapter,
            "nvidia_nim": NvidiaNimAdapter,
            "stability": StabilityAdapter,
            "elevenlabs": ElevenLabsAdapter,
            "google_speech": GoogleSpeechAdapter,
            "byteplus_modelark": BytePlusAdapter,
        }

    def get(self, route: Route) -> ProviderAdapter:
        injected = self.runtime.adapter(route.provider)
        if injected is not None:
            return injected
        factory = self.factories.get(route.adapter)
        if factory is None:
            raise RouterError("unsupported_capability", "The selected provider adapter is not installed.")
        adapter = factory(self.runtime, self.media)
        if route.capability != "management" and route.capability not in adapter.capabilities:
            raise RouterError("unsupported_capability", "The selected provider does not support this capability.")
        return adapter


class Router:
    def __init__(self, runtime_candidate: Any = None):
        self.runtime = RuntimeFacade(runtime_candidate)
        self.config = _deep_merge(DEFAULT_CONFIG, self.runtime.config())
        self.normalizer = RequestNormalizer(self.config, self.runtime)
        self.policy = PolicyEngine(self.config, self.runtime)
        self.media = MediaSecurity(self.config)
        self.registry = AdapterRegistry(self.runtime, self.media)

    def _metadata(self, request: Optional[NormalizedRequest], started: float, **updates: Any) -> Dict[str, Any]:
        metadata = {
            "contract_version": CONTRACT_VERSION,
            "capability": request.capability if request else None,
            "operation_mode": request.operation_mode if request else None,
            "selected_provider": None,
            "selected_model": None,
            "route_reason": None,
            "latency_ms": max(0, int((time.monotonic() - started) * 1000)),
            "fallback_used": False,
            "fallback_attempts": [],
            "provider_request_id": None,
            "usage": None,
            "error_class": None,
        }
        if request and request.conflicts:
            metadata["normalization_conflicts"] = list(request.conflicts)
        metadata.update(updates)
        return metadata

    def _success(self, data: Any, message: str, metadata: Mapping[str, Any]) -> Dict[str, Any]:
        return {"status": True, "data": data, "message": message, "metadata": dict(metadata)}

    def _failure(self, error: RouterError, metadata: Mapping[str, Any]) -> Dict[str, Any]:
        result = {
            "status": False,
            "data": None,
            "message": error.safe_message,
            "metadata": {**dict(metadata), "error_class": error.error_class},
            "error": error.safe_message,
        }
        return result

    def _management(self, request: NormalizedRequest, started: float) -> Dict[str, Any]:
        providers = _as_dict(self.config.get("providers"))
        explicit = request.provider
        entries: List[Dict[str, Any]] = []
        for provider, conf_value in providers.items():
            provider = _canonical_provider(provider) or provider
            if explicit and provider != explicit:
                continue
            conf = _as_dict(conf_value)
            enabled = _as_bool(conf.get("enabled")) or (provider == "nvidia_nim" and bool(os.getenv("NVIDIA_NIM_CHAT_BASE_URL")))
            allowed_models = _as_dict(conf.get("allowed_models"))
            if request.command == "list_models":
                if not enabled:
                    continue
                for capability, models in allowed_models.items():
                    for model in models or []:
                        entries.append({"provider": provider, "model": model, "capability": capability, "enabled": True})
                env_name = conf.get("allowed_models_env")
                if env_name and os.getenv(str(env_name)):
                    for model in [item.strip() for item in os.getenv(str(env_name), "").split(",") if item.strip()]:
                        entries.append({"provider": provider, "model": model, "capability": "chat", "enabled": True})
            else:
                missing: List[str] = []
                if enabled and conf.get("credential_env") and not (conf.get("credential") or os.getenv(str(conf.get("credential_env")))):
                    missing.append("credential")
                if enabled and conf.get("endpoint_env") and not (conf.get("endpoint") or os.getenv(str(conf.get("endpoint_env")))):
                    missing.append("endpoint")
                entries.append({
                    "provider": provider,
                    "enabled": enabled,
                    "ready": enabled and not missing,
                    "missing": missing,
                    "adapter": conf.get("adapter"),
                    "capabilities": sorted(key for key, models in allowed_models.items() if models),
                })
        message = "Allowed models listed." if request.command == "list_models" else "Router health evaluated."
        return self._success(entries, message, self._metadata(request, started))

    def _execute_adapter(self, adapter: ProviderAdapter, route: Route, request: NormalizedRequest) -> AdapterResult:
        if request.capability == "chat":
            if request.operation_mode == "factory":
                return adapter.create_chat_model(route, request)
            return adapter.invoke_chat(route, request)
        if request.capability == "embedding":
            if request.operation_mode == "factory":
                return adapter.create_embedding_model(route, request)
            return adapter.embed(route, request)
        if request.capability == "search_answer":
            return adapter.invoke_search(route, request)
        if request.capability == "image":
            return adapter.invoke_image(route, request)
        if request.capability == "video":
            return self._video(adapter, route, request)
        if request.capability == "transcription":
            return adapter.transcribe(route, request)
        if request.capability == "tts":
            return adapter.invoke_tts(route, request)
        if request.capability == "voice":
            return adapter.voice(route, request)
        if request.capability == "music":
            return adapter.invoke_music(route, request)
        raise RouterError("unsupported_capability", "The requested capability is not supported.")

    def _video(self, adapter: ProviderAdapter, route: Route, request: NormalizedRequest) -> AdapterResult:
        operation = str(request.options.get("operation") or "create_task")
        scope = self.runtime.scope()
        task_id = request.options.get("task_id") or request.input.get("task_id")
        if operation != "create_task":
            authorization = self.runtime.task_call("authorize", {"operation": operation, "task_id": task_id, "scope": scope, "provider": route.provider})
            if authorization is None:
                raise RouterError("policy_provider_not_allowed", "Async task administration requires the runtime task service.")
            if authorization is False or (isinstance(authorization, Mapping) and authorization.get("authorized") is False):
                raise RouterError("policy_provider_not_allowed", "The async task is not authorized for this caller.")
        result = adapter.invoke_video(route, request)
        if operation == "create_task" and isinstance(result.data, Mapping):
            receipt = {
                "task_id": result.data.get("task_id") or result.data.get("id"),
                "provider": route.provider,
                "model": route.model,
                "scope": scope,
                "creator": scope.get("actor_id"),
            }
            stored = self.runtime.task_call("record", receipt)
            if stored is not None:
                result.extensions["task_recorded"] = True
        return result

    def dispatch(self, command: str, params: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        started = time.monotonic()
        request: Optional[NormalizedRequest] = None
        try:
            runtime_candidate = _as_dict(params).get("_runtime") if isinstance(params, Mapping) else None
            if runtime_candidate is not None and runtime_candidate is not self.runtime.raw:
                return Router(runtime_candidate).dispatch(command, {key: value for key, value in _as_dict(params).items() if key != "_runtime"})
            request = self.normalizer.normalize(command, params)
            if request.capability == "management":
                return self._management(request, started)
            primary = self.policy.route(request)
            fallback_specs = self.policy.fallback_candidates(primary, request)
            policy = _as_dict(self.config.get("policy"))
            deadline = started + (_safe_int(policy.get("total_deadline_ms"), 120000, minimum=1) / 1000.0)
            attempts: List[Dict[str, Any]] = []
            last_error: Optional[RouterError] = None
            plan: List[Any] = [primary] + list(fallback_specs)
            for route_index, planned in enumerate(plan):
                if route_index > 0 and time.monotonic() >= deadline:
                    last_error = last_error or RouterError("provider_timeout", "The router invocation deadline was exhausted.")
                    break
                if isinstance(planned, Route):
                    route = planned
                else:
                    candidate, fallback_reason = planned
                    try:
                        # Fallback routes are built lazily and tolerantly: a candidate
                        # that cannot be built is skipped instead of failing the request.
                        route = self.policy.route(request, candidate, fallback_reason, prefer_candidate_model=True)
                    except RouterError as error:
                        attempts.append({
                            "provider": _canonical_provider(candidate.get("provider")),
                            "model": candidate.get("model"),
                            "error_class": error.error_class,
                            "latency_ms": 0,
                            "retry": False,
                            "skipped": True,
                        })
                        continue
                route_id = f"{route.provider}:{route.model or '-'}:{route.capability}"
                if not self.runtime.circuit_allow(route_id):
                    error = RouterError("provider_unavailable", "The selected provider route circuit is open.", transient=True)
                    attempts.append({"provider": route.provider, "model": route.model, "error_class": error.error_class, "latency_ms": 0, "retry": False})
                    last_error = error
                    continue
                for retry in range(route.retries + 1):
                    if time.monotonic() >= deadline:
                        last_error = RouterError("provider_timeout", "The router invocation deadline was exhausted.")
                        break
                    attempt_started = time.monotonic()
                    try:
                        adapter = self.registry.get(route)
                        result = self._execute_adapter(adapter, route, request)
                        self.runtime.circuit_record(route_id, True)
                        metadata = self._metadata(
                            request,
                            started,
                            selected_provider=route.provider,
                            selected_model=route.model,
                            route_reason=route.reason,
                            fallback_used=route_index > 0,
                            fallback_attempts=attempts,
                            provider_request_id=result.provider_request_id,
                            usage=result.usage,
                        )
                        if result.extensions:
                            metadata["provider_extensions"] = result.extensions
                        message = "Route completed."
                        if request.operation_mode == "factory":
                            message = "Model loaded."
                        elif request.capability == "video":
                            message = "Video task operation completed."
                        return self._success(result.data, message, metadata)
                    except RouterError as error:
                        self.runtime.circuit_record(route_id, False, error.error_class)
                        attempts.append({
                            "provider": route.provider,
                            "model": route.model,
                            "error_class": error.error_class,
                            "latency_ms": max(0, int((time.monotonic() - attempt_started) * 1000)),
                            "retry": retry < route.retries and error.transient,
                        })
                        last_error = error
                        if not error.transient:
                            metadata = self._metadata(
                                request, started,
                                selected_provider=route.provider,
                                selected_model=route.model,
                                route_reason=route.reason,
                                fallback_used=route_index > 0,
                                fallback_attempts=attempts,
                            )
                            return self._failure(error, metadata)
                        if retry < route.retries:
                            continue
                        break
                if last_error and not last_error.transient:
                    break
            error = last_error or RouterError("provider_unavailable", "No configured route completed the request.")
            # Total-failure receipts carry the PRIMARY route identity in the headline
            # fields; fallback_attempts keeps the per-attempt truth.
            metadata = self._metadata(
                request, started,
                selected_provider=primary.provider,
                selected_model=primary.model,
                route_reason=primary.reason,
                fallback_used=bool(fallback_specs),
                fallback_attempts=attempts,
            )
            return self._failure(error, metadata)
        except RouterError as error:
            return self._failure(error, self._metadata(request, started))
        except Exception:
            error = RouterError("internal_adapter_error", "The router could not complete the request.")
            return self._failure(error, self._metadata(request, started))


# Public connector commands.  The optional injected globals are intentionally
# resolved at call time because connector runtimes may attach them after import.
# The server contract injects `machina_router_runtime` (RouterRuntimeServices);
# `runtime` and the `_runtime` param remain as offline/test fallbacks.
def _router(params: Optional[Mapping[str, Any]]) -> Router:
    supplied = _as_dict(params).get("_runtime") if isinstance(params, Mapping) else None
    injected = supplied
    if injected is None:
        injected = globals().get("machina_router_runtime")
    if injected is None:
        injected = globals().get("runtime")
    return Router(injected)


def _dispatch(command: str, params: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    clean = dict(params or {})
    clean.pop("_runtime", None)
    return _router(params).dispatch(command, clean)


def invoke_prompt(params):
    return _dispatch("invoke_prompt", params)


def invoke_chat(params):
    return _dispatch("invoke_chat", params)


def completion_receipt(params):
    return _dispatch("completion_receipt", params)


def invoke_embedding(params):
    return _dispatch("invoke_embedding", params)


def embed_query(params):
    return _dispatch("embed_query", params)


def embed_documents(params):
    return _dispatch("embed_documents", params)


def list_models(params):
    return _dispatch("list_models", params)


def health(params):
    return _dispatch("health", params)


def invoke_search(params):
    return _dispatch("invoke_search", params)


def invoke_image(params):
    return _dispatch("invoke_image", params)


def generate_image(params):
    return _dispatch("generate_image", params)


def edit_image(params):
    return _dispatch("edit_image", params)


def invoke_video(params):
    return _dispatch("invoke_video", params)


def transcribe_audio_to_text(params):
    return _dispatch("transcribe_audio_to_text", params)


def invoke_transcribe(params):
    return _dispatch("invoke_transcribe", params)


def invoke_tts(params):
    return _dispatch("invoke_tts", params)


def get_text_to_speech(params):
    return _dispatch("get_text_to_speech", params)


def list_voices(params):
    return _dispatch("list_voices", params)


def get_voices(params):
    return _dispatch("get_voices", params)


def invoke_clone_instant_voice(params):
    return _dispatch("invoke_clone_instant_voice", params)


def invoke_train_pro_voice(params):
    return _dispatch("invoke_train_pro_voice", params)


def invoke_synthesize_custom_voice(params):
    return _dispatch("invoke_synthesize_custom_voice", params)


def invoke_music(params):
    return _dispatch("invoke_music", params)
