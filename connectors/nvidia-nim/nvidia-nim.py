"""
NVIDIA NIM chat connector — OpenAI-compatible /v1 endpoint resolved from
OPERATIONAL CONFIG ONLY (private-runtime requirement).

The endpoint and the model allowlist come from the runtime environment
(NVIDIA_NIM_* envs injected by the deployment), never from workflow YAML:
a template can pick a model within the allowlist, but cannot point the
runtime at an arbitrary URL. Embeddings are deliberately separate
(RETRIEVAL_NIM_* on the client-api retrieval facade).

Env contract:
  NVIDIA_NIM_CHAT_BASE_URL      e.g. http://nemotron-nim:8001/v1 (required)
  NVIDIA_NIM_CHAT_MODEL         default model, e.g. nvidia/nemotron-3-super-120b-a12b (required)
  NVIDIA_NIM_ALLOWED_MODELS     csv allowlist (default: just the default model)
  NVIDIA_NIM_TIMEOUT_SECONDS    request timeout (default 70 — Nemotron with
                                reasoning needs >18s for structured answers)
  NVIDIA_NIM_MAX_OUTPUT_TOKENS  optional hard cap on max_tokens
  NVIDIA_NIM_API_KEY            optional; local NIMs don't validate it
"""

import os

import requests


def _operational_config():
    base_url = (os.environ.get("NVIDIA_NIM_CHAT_BASE_URL") or "").strip().rstrip("/")
    default_model = (os.environ.get("NVIDIA_NIM_CHAT_MODEL") or "").strip()
    allowed_raw = os.environ.get("NVIDIA_NIM_ALLOWED_MODELS") or default_model
    allowed = tuple(m.strip() for m in allowed_raw.split(",") if m.strip())
    timeout = float(os.environ.get("NVIDIA_NIM_TIMEOUT_SECONDS") or 70)
    return base_url, default_model, allowed, timeout


def _models_headers():
    headers = {}
    api_key = os.environ.get("NVIDIA_NIM_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _config_error():
    return {
        "status": "error",
        "message": "NVIDIA NIM operational config missing: set "
                   "NVIDIA_NIM_CHAT_BASE_URL and NVIDIA_NIM_CHAT_MODEL on the "
                   "runtime (never in workflow YAML).",
    }


def invoke_chat(params):
    """Build a ChatOpenAI wired to the NIM endpoint (the engine runs the prompt)."""
    base_url, default_model, allowed, timeout = _operational_config()

    if not base_url or not default_model:
        return _config_error()

    # Fail closed on endpoint injection: the URL is operational config.
    supplied_url = (
        params.get("base_url")
        or params.get("params", {}).get("base_url")
        or params.get("headers", {}).get("base_url")
    )
    if supplied_url and str(supplied_url).strip().rstrip("/") != base_url:
        return {
            "status": "error",
            "message": "base_url is operational config for nvidia-nim; "
                       "remove it from the workflow.",
        }

    requested = (
        params.get("model_name")
        or params.get("params", {}).get("model_name")
        or ""
    ).strip()
    model = requested or default_model
    if model not in allowed:
        return {
            "status": "error",
            "message": f"Model '{model}' is not in NVIDIA_NIM_ALLOWED_MODELS "
                       f"({', '.join(allowed)}).",
        }

    try:
        from langchain_openai import ChatOpenAI

        kwargs = {
            "base_url": base_url,
            "model": model,
            "api_key": os.environ.get("NVIDIA_NIM_API_KEY") or "not-needed",
            "timeout": timeout,
        }

        max_tokens = params.get("max_tokens")
        if max_tokens is None:
            max_tokens = params.get("params", {}).get("max_tokens")
        cap = os.environ.get("NVIDIA_NIM_MAX_OUTPUT_TOKENS")
        if max_tokens is not None and cap:
            kwargs["max_tokens"] = min(int(max_tokens), int(cap))
        elif max_tokens is not None:
            kwargs["max_tokens"] = int(max_tokens)
        elif cap:
            kwargs["max_tokens"] = int(cap)

        temperature = params.get("temperature")
        if temperature is None:
            temperature = params.get("params", {}).get("temperature")
        if temperature is not None:
            kwargs["temperature"] = float(temperature)

        llm = ChatOpenAI(**kwargs)

        return {"status": True, "data": llm, "message": "Model loaded."}
    except Exception as e:
        return {"status": "error", "message": f"Error loading NIM model: {str(e)}"}


def list_models(params):
    """List models served by the NIM endpoint, alongside the allowlist."""
    base_url, default_model, allowed, timeout = _operational_config()

    if not base_url:
        return _config_error()

    try:
        response = requests.get(
            f"{base_url}/models", headers=_models_headers(), timeout=min(timeout, 15)
        )
        response.raise_for_status()
        served = [m.get("id") for m in response.json().get("data", []) if m.get("id")]

        return {
            "status": True,
            "data": {"models": served, "allowed": list(allowed), "default": default_model},
            "message": "Models retrieved successfully.",
        }
    except Exception as e:
        return {"status": "error", "message": f"Error listing NIM models: {str(e)}"}


def health(params):
    """Private-runtime receipt: config present, endpoint reachable, default model served."""
    base_url, default_model, allowed, timeout = _operational_config()

    checks = []

    configured = bool(base_url and default_model)
    checks.append({
        "check": "operational_config",
        "ok": configured,
        "detail": "NVIDIA_NIM_CHAT_BASE_URL + NVIDIA_NIM_CHAT_MODEL set" if configured
        else "missing NVIDIA_NIM_CHAT_BASE_URL / NVIDIA_NIM_CHAT_MODEL",
    })
    if not configured:
        return {
            "status": "error",
            "data": {"healthy": False, "checks": checks},
            "message": "NIM operational config missing.",
        }

    healthy = True
    served = []
    try:
        response = requests.get(
            f"{base_url}/models", headers=_models_headers(), timeout=min(timeout, 15)
        )
        response.raise_for_status()
        served = [m.get("id") for m in response.json().get("data", []) if m.get("id")]
        checks.append({"check": "endpoint_reachable", "ok": True, "detail": base_url})
    except Exception as e:
        healthy = False
        checks.append({"check": "endpoint_reachable", "ok": False, "detail": str(e)[:200]})

    if healthy:
        model_served = default_model in served
        healthy = model_served
        checks.append({
            "check": "default_model_served",
            "ok": model_served,
            "detail": default_model if model_served
            else f"'{default_model}' not among served models",
        })

    data = {
        "healthy": healthy,
        "endpoint": base_url,
        "default_model": default_model,
        "allowed_models": list(allowed),
        "checks": checks,
    }
    if healthy:
        return {"status": True, "data": data, "message": "NIM healthy."}
    return {"status": "error", "data": data, "message": "NIM health check failed."}
