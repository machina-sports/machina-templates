"""Slack incoming-webhook connector.

Why pyscript instead of restapi:

Slack incoming webhooks embed the secret in the URL itself
(hooks.slack.com/services/<TEAM>/<WEBHOOK>/<TOKEN>). The restapi
connector type wants a fixed server URL in OpenAPI, so we'd have to
split the URL into 3 path params and pass them — but the workflow yml
engine's expression evaluator chokes on the slicing logic with
`'error'` / KeyErrors that are nearly impossible to diagnose.

A pyscript:
  - Takes the FULL webhook URL as one input (resolved from
    `TEMP_CONTEXT_VARIABLE_SLACK_WEBHOOK_URL` by the calling
    workflow's context-variables block).
  - Does the POST itself — no URL splitting, no path-param dance.
  - Returns the {status: True, data: 'ok'} envelope the executor
    expects.

Single command: `invoke_post`. Inputs:
  webhook_url  (str, required)  full hooks.slack.com/services/...
  text         (str, optional)
  blocks       (list, optional)  Block Kit blocks
  username     (str, optional)
  icon_emoji   (str, optional)
  icon_url     (str, optional)
  thread_ts    (str, optional)  reply in an existing thread

Returns {status: True, data: 'ok'} on success.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


def invoke_post(request_data, *_, **__):
    """Connector entrypoint."""

    if isinstance(request_data, dict):
        inputs = request_data.get("params") or request_data.get("inputs") or request_data
    else:
        inputs = {}

    webhook_url = (inputs.get("webhook_url") or "").strip()
    if not webhook_url:
        return {
            "status": False,
            "data": {},
            "error": {"code": 400, "message": "Missing webhook_url — set TEMP_CONTEXT_VARIABLE_SLACK_WEBHOOK_URL in vault and pass via context-variables"},
        }
    if "hooks.slack.com" not in webhook_url:
        return {
            "status": False,
            "data": {},
            "error": {"code": 400, "message": f"webhook_url doesn't look like a Slack incoming webhook (must contain 'hooks.slack.com'): {webhook_url[:60]}..."},
        }

    text = inputs.get("text") or ""
    blocks = inputs.get("blocks") or []

    if not text and not blocks:
        return {
            "status": False,
            "data": {},
            "error": {"code": 400, "message": "At least one of `text` or `blocks` is required"},
        }

    body = {}
    if text:
        body["text"] = text
    if blocks:
        body["blocks"] = blocks
    if inputs.get("username"):
        body["username"] = inputs.get("username")
    if inputs.get("icon_emoji"):
        body["icon_emoji"] = inputs.get("icon_emoji")
    if inputs.get("icon_url"):
        body["icon_url"] = inputs.get("icon_url")
    if inputs.get("thread_ts"):
        body["thread_ts"] = inputs.get("thread_ts")

    req = urllib.request.Request(
        webhook_url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            # Slack returns the literal string "ok" on success, not JSON.
            return {
                "status": True,
                "data": raw or "ok",
                "message": "Posted to Slack",
            }
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode("utf-8", errors="replace")
        except Exception:
            body_text = ""
        # Slack error vocabulary: `no_service` (URL invalid/revoked),
        # `invalid_payload`, `channel_disabled`, etc.
        return {
            "status": False,
            "data": {},
            "error": {
                "code": e.code,
                "message": body_text[:200] or f"Slack HTTP {e.code}",
            },
        }
    except Exception as e:
        return {
            "status": False,
            "data": {},
            "error": {"code": 500, "message": f"{type(e).__name__}: {e}"},
        }
