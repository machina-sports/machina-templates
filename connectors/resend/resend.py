"""Resend transactional email connector.

Why pyscript instead of restapi:

The restapi connector type wires auth via context-variables — but its
substitution engine only handles `$NAME` (single-token) replacement.
You can't write `"Bearer $TOKEN"` because the whole value gets either
treated as a literal string OR substituted as a single token. That
mismatch + the workflow yml expression engine's quirks around list
inputs and unicode characters in subjects made the restapi path
brittle enough that smoke tests kept failing (HTTP 422 missing-to,
'invalid syntax', etc).

A pyscript:
  - Takes the API key as a request input (resolved from
    `TEMP_CONTEXT_VARIABLE_RESEND_API_KEY` by the calling workflow's
    context-variables block — that path's substitution IS clean).
  - Adds the "Bearer " prefix itself.
  - Serializes the body via json.dumps, so list/dict inputs survive
    intact regardless of how the workflow engine sliced them.
  - Returns the {status: True, data: {...}} envelope the executor
    expects (see machina-client-api/core/connector/executor.py).

Single command: `invoke_send`. Inputs:
  from         (str, required)  sender
  to           (str OR list, required)  recipient(s) — coerced to list
  subject      (str, required)
  html         (str, optional)
  text         (str, optional)
  attachments  (list of {filename, path|content, content_type}, opt)
  cc, bcc      (str OR list, optional)
  tags         (list of {name, value}, optional)
  api_key      (str, required)  the Resend API key, NO "Bearer " prefix

Returns {status: True, data: {id, from, to, created_at}} on success.
On Resend error returns {status: False, error: {code, message, body}}.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


_API = "https://api.resend.com/emails"


def _as_list(value):
    """Resend rejects single-string `to`/`cc`/`bcc` with HTTP 422.
    Coerce here so callers can pass whichever shape is convenient."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(v) for v in value if v]
    return [str(value)]


def invoke_send(request_data, *_, **__):
    """Connector entrypoint. Pyscript executor passes the full
    request_data dict — actual inputs live under params/inputs."""

    if isinstance(request_data, dict):
        inputs = request_data.get("params") or request_data.get("inputs") or request_data
    else:
        inputs = {}

    api_key = (inputs.get("api_key") or "").strip()
    # Strip a stale "Bearer " prefix if the vault entry was set that way
    # for an earlier restapi-based attempt — we add Bearer ourselves below.
    if api_key.lower().startswith("bearer "):
        api_key = api_key[7:].strip()

    if not api_key:
        return {
            "status": False,
            "data": {},
            "error": {"code": 400, "message": "Missing api_key — set TEMP_CONTEXT_VARIABLE_RESEND_API_KEY in vault and pass via context-variables"},
        }

    from_ = inputs.get("from") or ""
    to = _as_list(inputs.get("to"))
    subject = inputs.get("subject") or ""

    if not from_ or not to or not subject:
        return {
            "status": False,
            "data": {},
            "error": {"code": 400, "message": f"Missing required field: from={bool(from_)} to={bool(to)} subject={bool(subject)}"},
        }

    body = {
        "from": from_,
        "to": to,
        "subject": subject,
    }
    if inputs.get("html"):
        body["html"] = inputs.get("html")
    if inputs.get("text"):
        body["text"] = inputs.get("text")
    cc = _as_list(inputs.get("cc"))
    if cc:
        body["cc"] = cc
    bcc = _as_list(inputs.get("bcc"))
    if bcc:
        body["bcc"] = bcc
    if inputs.get("attachments"):
        body["attachments"] = inputs.get("attachments")
    if inputs.get("tags"):
        body["tags"] = inputs.get("tags")
    if inputs.get("reply_to"):
        body["reply_to"] = _as_list(inputs.get("reply_to"))

    req = urllib.request.Request(
        _API,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Some APIs (incl. Resend on certain account states) reject
            # requests without an identifiable User-Agent. urllib's
            # default is "Python-urllib/3.x" which Resend may flag.
            "User-Agent": "machina-connector/1.0",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            try:
                parsed = json.loads(raw) if raw else {}
            except Exception:
                parsed = {"_raw": raw}
            # Debug: log the parsed response so we can see what Resend
            # actually returned (id field present? wrong key?).
            print(f"[RESEND_DEBUG] response keys: {list(parsed.keys()) if isinstance(parsed, dict) else type(parsed).__name__}")
            print(f"[RESEND_DEBUG] response full: {raw[:300]}")
            return {
                "status": True,
                "data": parsed,
                "message": "Email sent via Resend",
                # Surface `id` at top level too so workflow expressions
                # can read it as $.get('id') OR $.get('data', {}).get('id')
                "id": parsed.get("id") if isinstance(parsed, dict) else None,
            }
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode("utf-8", errors="replace")
        except Exception:
            body_text = ""
        try:
            parsed = json.loads(body_text) if body_text else {}
        except Exception:
            parsed = {}
        # Surface the FULL body even if it's not JSON — Resend's 403 is
        # opaque and we need to see what they're complaining about.
        msg = parsed.get("message") or parsed.get("error") or body_text[:500] or f"Resend HTTP {e.code}"
        return {
            "status": False,
            "data": {},
            "error": {
                "code": e.code,
                "message": f"Resend HTTP {e.code}: {msg}",
                "details": parsed if parsed else {"raw": body_text[:500]},
            },
        }
    except Exception as e:
        return {
            "status": False,
            "data": {},
            "error": {"code": 500, "message": f"{type(e).__name__}: {e}"},
        }
