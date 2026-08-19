"""Cerebras public inference connector with operator-owned routing policy."""

import importlib
import os
import time
from collections.abc import Mapping

import requests


CONTRACT_VERSION = "v1"
BASE_URL = "https://api.cerebras.ai/v1"
PUBLIC_CHAT_MODELS = ("gpt-oss-120b", "gemma-4-31b")
DEFAULT_MODEL = "gpt-oss-120b"
API_KEY_ENVS = (
    "TEMP_CONTEXT_VARIABLE_CEREBRAS_API_KEY",
    "TEMP_CONTEXT_VARIABLE_SDK_CEREBRAS_API_KEY",
)


class ConnectorError(Exception):
    def __init__(self, error_class, message):
        super().__init__(message)
        self.error_class = error_class
        self.safe_message = message


def _dict(value):
    return dict(value) if isinstance(value, Mapping) else {}


def _value(params, *names):
    params = _dict(params)
    nested = _dict(params.get("params"))
    for source in (params, nested):
        for name in names:
            if source.get(name) not in (None, ""):
                return source[name]
    return None


def _metadata(operation, started, *, model=None, request_id=None, usage=None, error_class=None):
    return {
        "contract_version": CONTRACT_VERSION,
        "provider": "cerebras",
        "operation": operation,
        "model": model,
        "latency_ms": max(0, int((time.monotonic() - started) * 1000)),
        "provider_request_id": request_id,
        "usage": usage,
        "error_class": error_class,
    }


def _success(data, message, metadata):
    return {"status": True, "data": data, "message": message, "metadata": metadata}


def _failure(error, metadata):
    return {
        "status": False,
        "data": None,
        "message": error.safe_message,
        "error": error.safe_message,
        "metadata": {**metadata, "error_class": error.error_class},
    }


def _error_from_exception(error):
    status_code = getattr(error, "status_code", None)
    response = getattr(error, "response", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    name = error.__class__.__name__.lower()
    if isinstance(error, (requests.Timeout, TimeoutError)) or "timeout" in name or status_code == 408:
        return ConnectorError("provider_timeout", "Cerebras did not respond before the request timeout.")
    if status_code == 429 or "ratelimit" in name or "rate_limit" in name:
        return ConnectorError("provider_rate_limited", "The Cerebras rate limit was reached.")
    if status_code in {401, 402, 403} or "authentication" in name or "permission" in name:
        return ConnectorError("provider_authentication", "Cerebras rejected the configured credential.")
    if status_code == 413 or "contenttoolarge" in name:
        return ConnectorError("provider_content_rejected", "Cerebras rejected the request content.")
    if status_code in {400, 404, 422}:
        return ConnectorError("invalid_request", "Cerebras rejected the request parameters.")
    if isinstance(error, requests.ConnectionError) or status_code in {500, 502, 503, 504} or "connection" in name:
        return ConnectorError("provider_unavailable", "Cerebras is temporarily unavailable.")
    return ConnectorError("internal_adapter_error", "The Cerebras connector could not complete the operation.")


def _reject_overrides(params):
    params = _dict(params)
    nested = _dict(params.get("params"))
    headers = _dict(params.get("headers"))
    for source in (params, nested, headers):
        if source.get("endpoint") not in (None, "") or source.get("base_url") not in (None, ""):
            raise ConnectorError("policy_endpoint_not_allowed", "The Cerebras endpoint is fixed by connector policy.")

    header_credential = headers.get("api_key") or headers.get("credential")
    supplied = [
        source.get(name)
        for source in (params, nested)
        for name in ("api_key", "credential")
        if source.get(name) not in (None, "")
    ]
    if supplied and (not header_credential or any(value != header_credential for value in supplied)):
        raise ConnectorError("policy_credential_not_allowed", "The Cerebras credential is controlled by runtime policy.")
    return header_credential


def _credential(params):
    header_credential = _reject_overrides(params)
    env_credential = next((os.getenv(name) for name in API_KEY_ENVS if os.getenv(name)), None)
    if env_credential and header_credential and env_credential != header_credential:
        raise ConnectorError("policy_credential_not_allowed", "The Cerebras credential is controlled by runtime policy.")
    credential = env_credential or header_credential
    if not credential:
        raise ConnectorError("credential_missing", "The Cerebras credential is not configured for this runtime.")
    return credential


def _allowed_models():
    configured = os.getenv("CEREBRAS_ALLOWED_MODELS")
    if not configured:
        return PUBLIC_CHAT_MODELS
    requested = tuple(item.strip() for item in configured.split(",") if item.strip())
    allowed = tuple(item for item in PUBLIC_CHAT_MODELS if item in requested)
    if not allowed:
        raise ConnectorError("policy_model_not_allowed", "No public Cerebras model is enabled by runtime policy.")
    return allowed


def _model(params):
    allowed = _allowed_models()
    default = (os.getenv("CEREBRAS_DEFAULT_MODEL") or DEFAULT_MODEL).strip()
    model = str(_value(params, "model", "model_name") or default).strip()
    if model not in allowed:
        raise ConnectorError("policy_model_not_allowed", "The selected Cerebras model is not allowed for this runtime.")
    return model


def _timeout(params):
    raw = _value(params, "timeout_ms")
    legacy = raw in (None, "")
    if legacy:
        raw = _value(params, "timeout")
    try:
        value = float(raw) if raw not in (None, "") else 30000.0
    except (TypeError, ValueError):
        raise ConnectorError("invalid_request", "The Cerebras timeout must be numeric.")
    if legacy and raw not in (None, "") and value <= 600:
        value *= 1000
    if value <= 0:
        raise ConnectorError("invalid_request", "The Cerebras timeout must be greater than zero.")
    return min(value, 120000.0) / 1000.0


def _headers(credential):
    return {"Authorization": f"Bearer {credential}", "Content-Type": "application/json"}


def _request(method, path, credential, timeout, **kwargs):
    try:
        response = method(
            f"{BASE_URL}/{path.lstrip('/')}",
            headers=_headers(credential),
            timeout=timeout,
            allow_redirects=False,
            **kwargs,
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except Exception:
            raise ConnectorError("provider_bad_response", "Cerebras returned invalid JSON.")
        if not isinstance(payload, Mapping):
            raise ConnectorError("provider_bad_response", "Cerebras returned an invalid response envelope.")
        return dict(payload)
    except ConnectorError:
        raise
    except Exception as error:
        raise _error_from_exception(error)


def _messages(params):
    messages = _value(params, "messages")
    if messages:
        if not isinstance(messages, list):
            raise ConnectorError("invalid_request", "Cerebras chat messages must be a list.")
        return messages
    prompt = _value(params, "prompt", "input", "text")
    if prompt in (None, ""):
        raise ConnectorError("invalid_request", "Cerebras chat execution requires messages or a prompt.")
    return [{"role": "user", "content": prompt}]


def _chat_payload(params, model, messages):
    payload = {"model": model, "messages": messages, "stream": False}
    for key in ("temperature", "max_tokens", "max_completion_tokens", "response_format", "tools", "seed"):
        value = _value(params, key)
        if value is not None:
            payload[key] = value
    return payload


def _parse_chat(payload):
    choices = payload.get("choices") or []
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        raise ConnectorError("provider_bad_response", "Cerebras returned no chat completion choice.")
    choice = choices[0]
    message = _dict(choice.get("message"))
    content = message.get("content")
    tool_calls = message.get("tool_calls") or []
    if not isinstance(tool_calls, list):
        raise ConnectorError("provider_bad_response", "Cerebras returned invalid tool call data.")
    if content is None and not tool_calls:
        raise ConnectorError("provider_bad_response", "Cerebras returned no completion content.")
    usage = _dict(payload.get("usage")) or None
    data = {
        "role": message.get("role") or "assistant",
        "content": content,
        "finish_reason": choice.get("finish_reason"),
        "citations": [],
        "tool_calls": tool_calls,
        "provider_extensions": {},
    }
    return data, payload.get("id"), usage


def _model_entries(payload):
    entries = payload.get("data")
    if not isinstance(entries, list):
        raise ConnectorError("provider_bad_response", "Cerebras returned an invalid model catalog.")
    return [item for item in entries if isinstance(item, Mapping)]


def invoke_prompt(params):
    started = time.monotonic()
    model = None
    try:
        credential = _credential(params)
        model = _model(params)
        kwargs = {
            "model": model,
            "api_key": credential,
            "base_url": BASE_URL,
            "timeout": _timeout(params),
            "temperature": _value(params, "temperature"),
            "max_tokens": _value(params, "max_tokens"),
        }
        chat_openai = importlib.import_module("langchain_openai").ChatOpenAI
        model_instance = chat_openai(**{key: value for key, value in kwargs.items() if value is not None})
        return _success(model_instance, "Model loaded.", _metadata("invoke_prompt", started, model=model))
    except ConnectorError as error:
        return _failure(error, _metadata("invoke_prompt", started, model=model))
    except Exception as error:
        safe = _error_from_exception(error)
        return _failure(safe, _metadata("invoke_prompt", started, model=model))


def invoke_chat(params):
    started = time.monotonic()
    model = None
    try:
        credential = _credential(params)
        model = _model(params)
        payload = _request(
            requests.post,
            "chat/completions",
            credential,
            _timeout(params),
            json=_chat_payload(params, model, _messages(params)),
        )
        data, request_id, usage = _parse_chat(payload)
        return _success(data, "Cerebras chat completed.", _metadata(
            "invoke_chat", started, model=model, request_id=request_id, usage=usage
        ))
    except ConnectorError as error:
        return _failure(error, _metadata("invoke_chat", started, model=model))


def list_models(params):
    started = time.monotonic()
    try:
        credential = _credential(params)
        allowed = _allowed_models()
        payload = _request(requests.get, "models", credential, _timeout(params))
        remote = _model_entries(payload)
        models = [
            {"id": item.get("id"), "owned_by": item.get("owned_by")}
            for item in remote
            if item.get("id") in allowed
        ]
        data = {"models": models, "allowed": list(allowed), "default": os.getenv("CEREBRAS_DEFAULT_MODEL") or DEFAULT_MODEL}
        return _success(data, "Cerebras models retrieved.", _metadata("list_models", started))
    except ConnectorError as error:
        return _failure(error, _metadata("list_models", started))


def health(params):
    started = time.monotonic()
    try:
        credential = _credential(params)
        allowed = _allowed_models()
        default = os.getenv("CEREBRAS_DEFAULT_MODEL") or DEFAULT_MODEL
        if default not in allowed:
            raise ConnectorError("policy_model_not_allowed", "The default Cerebras model is not allowed for this runtime.")
        payload = _request(requests.get, "models", credential, min(_timeout(params), 15.0))
        served = [item.get("id") for item in _model_entries(payload)]
        healthy = default in served
        data = {"healthy": healthy, "default_model": default, "allowed_models": list(allowed), "default_model_served": healthy}
        if not healthy:
            raise ConnectorError("provider_unavailable", "The default Cerebras model is not currently served.")
        return _success(data, "Cerebras is healthy.", _metadata("health", started, model=default))
    except ConnectorError as error:
        return _failure(error, _metadata("health", started))


def completion_receipt(params):
    started = time.monotonic()
    model = None
    try:
        credential = _credential(params)
        model = _model(params)
        messages = [{"role": "user", "content": "Reply with exactly MACHINA_CEREBRAS_OK."}]
        payload = _request(
            requests.post,
            "chat/completions",
            credential,
            _timeout(params),
            json={"model": model, "messages": messages, "temperature": 0, "max_tokens": 16, "stream": False},
        )
        chat, request_id, usage = _parse_chat(payload)
        data = {
            "completed": True,
            "requested_model": model,
            "response_model": payload.get("model") or model,
            "response_id": request_id or "",
            "output": str(chat.get("content") or "")[:200],
            "usage": usage or {},
        }
        return _success(data, "Cerebras completion receipt succeeded.", _metadata(
            "completion_receipt", started, model=model, request_id=request_id, usage=usage
        ))
    except ConnectorError as error:
        return _failure(error, _metadata("completion_receipt", started, model=model))
