"""Compatibility facade for the machina-ai ``fast`` profile.

Installed connectors contain only their declared Python file, so production
uses the runtime delegation service.  The sibling-file loader is strictly an
offline/development fallback and keeps tests credential-free.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _error(error_class, message):
    return {
        "status": False,
        "data": None,
        "message": message,
        "error": message,
        "metadata": {
            "contract_version": "v1",
            "capability": "embedding" if error_class == "unsupported_capability" else "chat",
            "operation_mode": "factory",
            "selected_provider": None,
            "selected_model": None,
            "route_reason": "compatibility:machina-ai-fast",
            "latency_ms": 0,
            "fallback_used": False,
            "fallback_attempts": [],
            "provider_request_id": None,
            "usage": None,
            "error_class": error_class,
        },
    }


def _runtime_from(params):
    if isinstance(params, dict) and params.get("_runtime") is not None:
        return params.get("_runtime")
    return globals().get("runtime")


def _delegate(command, params):
    payload = dict(params or {})
    runtime_service = _runtime_from(payload)
    payload.pop("_runtime", None)
    payload.setdefault("profile", "fast")

    delegate = getattr(runtime_service, "delegate", None) if runtime_service is not None else None
    if callable(delegate):
        attempts = (
            lambda: delegate(connector="machina-ai", command=command, params=payload),
            lambda: delegate("machina-ai", command, payload),
            lambda: delegate({"connector": "machina-ai", "command": command, "params": payload}),
        )
        for attempt in attempts:
            try:
                return attempt()
            except TypeError:
                continue
        return _error("provider_unavailable", "The runtime delegation service rejected the compatibility request.")

    router_path = Path(__file__).resolve().parents[1] / "machina-ai" / "machina-ai.py"
    if router_path.is_file():
        spec = importlib.util.spec_from_file_location("machina_ai_router_offline", router_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, command)(payload)

    return _error("provider_unavailable", "The machina-ai router delegation service is unavailable.")


def invoke_prompt(params):
    return _delegate("invoke_prompt", params)


def invoke_embedding(params):
    return _error(
        "unsupported_capability",
        "machina-ai-fast does not provide embeddings; use machina-ai invoke_embedding.",
    )
