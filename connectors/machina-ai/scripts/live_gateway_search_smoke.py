#!/usr/bin/env python3
"""Live smoke: one grounded search through the REAL machina-ai router -> Vercel AI Gateway -> Perplexity.

Runs this checkout's machina-ai.py locally (no pod, no import, no deploy) with a runtime policy
that enables only `vercel_gateway` for `search_answer` on `perplexity/sonar` behind one
single-entry profile. It makes exactly one paid call per --runs.

The key is read from AI_GATEWAY_API_KEY / TEMP_CONTEXT_VARIABLE_AI_GATEWAY_API_KEY or, if
neither is set, from a hidden prompt. It is never printed, logged or written: the evidence
file is scrubbed for it before saving, and the script refuses to save if it still appears.

What it records (evidence JSON + a short summary on stdout):
  - the router's receipt (selected provider/model, route_reason, fallback_used, gateway
    backend and the upstream model/provider the gateway reported, usage, latency)
  - the canonical answer data: citations and citation_source (which response shape the
    gateway actually used for Perplexity sources: perplexity_fields / message_annotations / none)
  - the wire request the router sent (URL, body without messages content) and the SHAPE of the
    gateway's raw reply (top-level keys, message keys, counts/types of citation fields), never
    the raw reply itself
  - router file sha256 and git commit, so the evidence is tied to exact source

Usage (from connectors/machina-ai, with python that has `openai` and `httpx`):

    python scripts/live_gateway_search_smoke.py --out /path/evidence.json
    python scripts/live_gateway_search_smoke.py --profile adidas_research_search \\
        --prompt "Latest news about an adidas athlete" --out evidence.json

Exit code 0 only when the route completed on vercel_gateway/perplexity with no fallback.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import functools
import getpass
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROUTER = HERE.parent / "machina-ai.py"
MODEL = "perplexity/sonar"
DEFAULT_PROMPT = ("What were the most recent adidas Samba product releases? "
                  "Answer in two sentences and cite your sources.")
KEY_ENVS = ("AI_GATEWAY_API_KEY", "TEMP_CONTEXT_VARIABLE_AI_GATEWAY_API_KEY")
# Provider credentials that must not be visible to this process: the route must stand alone.
STRIP_PREFIXES = ("TEMP_CONTEXT_VARIABLE_", "MACHINA_CONTEXT_VARIABLE_", "MACHINA_AI_ROUTER_CONFIG",
                  "NVIDIA_NIM_", "OPENAI_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS")


def policy(profile: str, zdr: bool) -> dict:
    """The same shape as adidas-templates research-router-config.json's gateway part."""
    return {
        "policy": {"max_timeout_ms": 300000, "total_deadline_ms": 300000},
        "providers": {"vercel_gateway": {
            "enabled": True, "zero_data_retention": zdr,
            "allowed_models": {"search_answer": [MODEL]},
        }},
        "profiles": {profile: {"search_answer": [{"provider": "vercel_gateway", "model": MODEL}]}},
    }


class Runtime:
    def __init__(self, config: dict):
        self._config = config

    def config(self, key=None):
        return self._config


def load_router(path: Path):
    spec = importlib.util.spec_from_file_location("machina_ai_router_live", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def shape(value, depth=0):
    """Type/keys/length of a JSON value, never its text."""
    if isinstance(value, dict):
        if depth >= 3:
            return {"type": "object", "keys": sorted(value)}
        return {"type": "object", "keys": {k: shape(v, depth + 1) for k, v in sorted(value.items())}}
    if isinstance(value, list):
        return {"type": "array", "length": len(value),
                "item": shape(value[0], depth + 1) if value else None}
    return {"type": type(value).__name__}


def git_commit() -> str | None:
    try:
        return subprocess.check_output(["git", "-C", str(HERE), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return None


def read_key() -> str:
    for name in KEY_ENVS:
        if os.environ.get(name):
            return os.environ[name].strip()
    if not sys.stdin.isatty():
        sys.exit("No AI Gateway key: set AI_GATEWAY_API_KEY or run interactively.")
    key = getpass.getpass("Vercel AI Gateway key (hidden): ").strip()
    if not key:
        sys.exit("No AI Gateway key given.")
    return key


def scrub(value, secret: str):
    if isinstance(value, dict):
        return {k: scrub(v, secret) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub(v, secret) for v in value]
    if isinstance(value, str) and secret and secret in value:
        return value.replace(secret, "[REDACTED]")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--profile", default="adidas_research_search")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--timeout", type=int, default=180, help="route deadline in seconds")
    parser.add_argument("--zdr", action="store_true", help="request ZDR (expected to fail typed for Perplexity)")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--router", type=Path, default=ROUTER)
    parser.add_argument("--out", type=Path, default=Path("gateway-search-evidence.json"))
    args = parser.parse_args(argv)

    import httpx
    import openai

    key = read_key()
    for name in list(os.environ):
        if name.startswith(STRIP_PREFIXES) or name in KEY_ENVS:
            del os.environ[name]
    os.environ["TEMP_CONTEXT_VARIABLE_AI_GATEWAY_API_KEY"] = key

    wire: list[dict] = []

    def on_response(response: httpx.Response):
        response.read()
        try:
            body = response.json()
        except ValueError:
            body = None
        request = response.request
        sent = json.loads(request.content or b"{}")
        message = (((body or {}).get("choices") or [{}])[0] or {}).get("message") if isinstance(body, dict) else None
        wire.append({
            "request": {
                "method": request.method, "url": str(request.url),
                "authorization_scheme": (request.headers.get("authorization") or "").split(" ")[0] or None,
                "body": {k: v for k, v in sent.items() if k != "messages"},
                "message_roles": [m.get("role") for m in sent.get("messages") or []],
                "timeout": request.extensions.get("timeout"),
            },
            "response": {
                "status": response.status_code,
                "body_shape": shape(body),
                "message_shape": shape(message) if isinstance(message, dict) else None,
                "gateway_headers": {k: v for k, v in response.headers.items()
                                    if k.lower().startswith(("x-vercel", "x-ai-gateway", "ai-gateway"))
                                    or k.lower() in ("x-request-id",)},
                "error": (body or {}).get("error") if isinstance(body, dict) and response.status_code >= 400 else None,
            },
        })

    client_factory = functools.partial(openai.OpenAI, http_client=httpx.Client(
        event_hooks={"response": [on_response]}))
    router = load_router(args.router)
    runtime = Runtime(policy(args.profile, args.zdr))
    results = []
    openai.OpenAI = client_factory  # the router imports openai lazily and calls openai.OpenAI(...)
    for _ in range(max(1, args.runs)):
        reply = router.invoke_search({"_runtime": runtime, "profile": args.profile,
                                      "prompt": args.prompt, "timeout": args.timeout})
        data = reply.get("data") if isinstance(reply.get("data"), dict) else {}
        results.append({
            "status": reply.get("status"),
            "message": reply.get("message"),
            "metadata": reply.get("metadata"),
            "answer_preview": (data.get("content") or "")[:400],
            "answer_chars": len(data.get("content") or ""),
            "citations": data.get("citations"),
            "provider_extensions": data.get("provider_extensions"),
        })

    evidence = {
        "kind": "machina-ai live gateway search smoke",
        "clickup": "17tpepcwnxc",
        "ran_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "route": "local machina-ai router -> Vercel AI Gateway -> Perplexity",
        "router": {"path": str(args.router), "sha256": hashlib.sha256(args.router.read_bytes()).hexdigest(),
                   "git_commit": git_commit()},
        "policy": runtime._config,
        "profile": args.profile,
        "prompt": args.prompt,
        "results": results,
        "wire": wire,
    }
    evidence = scrub(evidence, key)
    text = json.dumps(evidence, indent=2, default=str)
    if key in text:
        sys.exit("Refusing to save: the key would appear in the evidence.")
    args.out.write_text(text + "\n")

    ok = True
    for index, result in enumerate(results, 1):
        meta = result["metadata"] or {}
        gateway = meta.get("gateway") or {}
        ext = result.get("provider_extensions") or {}
        passed = (result["status"] is True and meta.get("selected_provider") == "vercel_gateway"
                  and meta.get("selected_model") == MODEL and meta.get("fallback_used") is False
                  and meta.get("route_reason") == f"profile:{args.profile}")
        ok = ok and passed
        print(f"run {index}: {'PASS' if passed else 'FAIL'} status={result['status']} "
              f"error_class={meta.get('error_class')} route={meta.get('selected_provider')}/{meta.get('selected_model')} "
              f"reason={meta.get('route_reason')} fallback={meta.get('fallback_used')} "
              f"upstream={gateway.get('upstream_provider')}/{gateway.get('upstream_model')} "
              f"citations={len(result.get('citations') or [])} citation_source={ext.get('citation_source')} "
              f"latency_ms={meta.get('latency_ms')} usage={meta.get('usage')}")
    for item in wire:
        print(f"wire: {item['request']['method']} {item['request']['url']} -> HTTP {item['response']['status']}; "
              f"top-level keys={sorted((item['response']['body_shape'] or {}).get('keys', {}) or [])}")
    print(f"evidence: {args.out.resolve()}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
