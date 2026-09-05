"""gemini-cv — Machina's Gemini computer-vision route for the Automated Highlights Agent.

Command ``rank_highlight_candidates``: validate, refine and rank SportsClaw highlight
candidates (a ``ClipManifest`` from ``sportsclaw highlights run`` / the relay artifacts, or
an explicit candidate list) against the source video with Gemini video understanding.

Contract, in one paragraph: deterministic play-by-play importance is the baseline. The
model may keep, hold, reject, refine or re-rank the candidates it was given and may propose
review-only *discovered moments*. It can never add a candidate. Any schema violation,
unknown candidate, refusal, provider error, timeout or unavailable processing mode makes
the result ``degraded: true`` with explicit ``degraded_reasons`` and a deterministic
PBP-importance fallback ranking (``fallback_mode: "pbp-importance"``). Nothing is
substituted silently: an agentic request never quietly runs static.

Providers
  vertex_ai  (default) project_id + service-account credential, location "global"
  ai_studio  api_key (Gemini Developer API)

Processing
  static   generateContent with the video attached (both providers)
  agentic  Interactions API ``processing: "agentic"`` (capability-gated: only when the
           route can reach it — today ai_studio via the Interactions REST surface; the
           pinned google-genai SDK 1.49 has no ``interactions`` client and Vertex AI is not
           verified — otherwise the run is degraded with reason ``agentic-unavailable``).

The credential never appears in the returned data. The video never leaves the provider the
caller configured.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
import json
import math
import os
import re
import stat
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROUTE = "gemini-cv/rank_highlight_candidates"
CONTRACT_VERSION = "1.1"
PROMPT_VERSION = "gemini-cv/2026-09-05.v2"
DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_LOCATION = "global"
DEFAULT_MAX_OUTPUT_TOKENS = 16384  # thought tokens count against this budget (Arena 2026-09-04)
DEFAULT_TIMEOUT_SEC = 180
INLINE_VIDEO_LIMIT_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 512 * 1024 * 1024
MAX_CANDIDATES = 100
MAX_DISCOVERIES = 100
MAX_MODEL_TEXT = 1024 * 1024
REFINEMENT_TOLERANCE_SEC = 10.0
PROVIDERS = ("vertex_ai", "ai_studio")
PROCESSING = ("static", "agentic")
THINKING = ("minimal", "low", "medium", "high")
VERDICTS = ("keep", "reject", "hold")
AI_STUDIO_BASE = "https://generativelanguage.googleapis.com"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string"},
                    "refined_start_sec": {"type": "number"},
                    "refined_end_sec": {"type": "number"},
                    "relevance": {"type": "integer", "minimum": 0, "maximum": 100},
                    "hype": {"type": "integer", "minimum": 0, "maximum": 100},
                    "editorial_safety": {"type": "integer", "minimum": 0, "maximum": 100},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "verdict": {"type": "string", "enum": list(VERDICTS)},
                    "description": {"type": "string"},
                },
                "required": ["candidate_id", "refined_start_sec", "refined_end_sec", "relevance", "hype",
                             "editorial_safety", "confidence", "verdict", "description"],
            },
        },
        "discovered_moments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "approx_sec": {"type": "number"},
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["approx_sec", "label", "confidence"],
            },
        },
        "refusal": {"type": "string"},
    },
    "required": ["candidates", "discovered_moments"],
}

SYSTEM_INSTRUCTION = (
    "You are a broadcast highlights reviewer. You receive one match video and a list of candidate "
    "moments that were selected from an official play-by-play feed. Your job is to validate, refine "
    "and rank those candidates only. Rules: (1) never invent events — if you cannot verify a candidate "
    "on screen, lower confidence and use verdict 'hold'; (2) a goal that is disallowed, a routine restart "
    "(goal kick, throw-in), and replays of an earlier action are NOT highlights: verdict 'reject' with "
    "editorial_safety reflecting the risk of airing it as a highlight; (3) refined_start_sec/refined_end_sec "
    "are absolute seconds on the video timeline and must stay within 10 seconds of the candidate window; "
    "(4) anything notable that is not in the candidate list goes to discovered_moments as a hypothesis, "
    "never as a candidate; (5) if the video is not sports footage, say so in 'refusal' and still return "
    "the candidates with verdict 'hold'. Answer with JSON only."
)


# ---------------------------------------------------------------------------
# request envelope helpers (pyscript connectors receive {"params", "headers", ...})
# ---------------------------------------------------------------------------

def _inputs(request_data):
    if not isinstance(request_data, dict):
        return {}
    merged = {}
    for key in ("headers", "params", "inputs"):
        container = request_data.get(key)
        if isinstance(container, dict):
            merged.update(container)
    for key, value in request_data.items():
        if key not in ("headers", "params", "inputs", "path_attribute", "server_params") and key not in merged:
            merged[key] = value
    return merged


def _error(code, message):
    return {"status": False, "data": {}, "error": {"code": code, "message": message}}


def _secret(inputs, key, env_name):
    value = inputs.get(key)
    # Unresolved optional workflow placeholders are not credentials. Keep the
    # portable pack provider-neutral; only the owner resolves pod defaults.
    if value is None or value == "" or (isinstance(value, str) and value.startswith("$")):
        return os.environ.get(env_name)
    return value


def _provider_error(error, secrets):
    message = str(error)
    def redact(value):
        nonlocal message
        if isinstance(value, str) and value:
            message = message.replace(value, "[redacted]")
            try:
                parsed = json.loads(value)
            except (ValueError, RecursionError):
                return
            if isinstance(parsed, dict):
                redact(parsed)
        elif isinstance(value, dict):
            for item in value.values():
                redact(item)
    for name in ("api_key", "credential"):
        redact(secrets.get(name))
    return f"provider-error: {type(error).__name__}: {message}"[:500]


def _number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and abs(value) <= 1e15 and math.isfinite(value))


def _sha256_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _text(value, name, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be a non-empty string of at most {limit} characters")
    return value.strip()


def _object(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def _rights(value):
    rights = _object(value, "rights")
    normalized = {}
    for camel, snake in (("clearedForClipping", "cleared_for_clipping"),
                         ("rightsHolder", "rights_holder"), ("licenseRef", "license_ref")):
        if camel in rights and snake in rights and (type(rights[camel]) is not type(rights[snake]) or rights[camel] != rights[snake]):
            raise ValueError(f"contradictory rights {camel}/{snake} — CV ranking refused")
        normalized[camel] = rights.get(camel, rights.get(snake))
    if normalized["clearedForClipping"] is not True:
        raise ValueError("rights do not clear this source for clipping — CV ranking refused")
    for key in ("rightsHolder", "licenseRef"):
        normalized[key] = _text(normalized[key], f"rights.{key}")
    # Retain additional policy restrictions in the evidence identity.
    return {**rights, **normalized}


def _source_digest(value):
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("source sha256 is required from the approved extraction manifest")
    return value


# ---------------------------------------------------------------------------
# candidates: from a ClipManifest or an explicit list. Fail closed on rights.
# ---------------------------------------------------------------------------

def _candidate_from_window(window, index):
    if not isinstance(window, dict):
        raise ValueError(f"manifest window {index} is not an object")
    candidate_id = _text(window.get("actionId") or window.get("candidate_id"), "candidate id", 256)
    start, end, action = window.get("startSec"), window.get("endSec"), window.get("actionVideoSec")
    if not candidate_id:
        raise ValueError(f"manifest window {index} has no actionId")
    if not (_number(start) and _number(end) and 0 <= start < end):
        raise ValueError(f"manifest window {candidate_id} has an invalid startSec/endSec")
    if not (_number(action) and start <= action <= end):
        raise ValueError(f"manifest window {candidate_id} has no actionVideoSec")
    importance = window.get("importance")
    if importance is not None and not (_number(importance) and 0 <= importance <= 100):
        raise ValueError("candidate importance must be between 0 and 100")
    return {
        "candidate_id": candidate_id,
        "label": _text(window.get("label") or candidate_id, "candidate label"),
        "type": _text(window.get("type") or "unknown", "candidate type", 256),
        "importance": importance if _number(importance) else None,
        "action_video_sec": float(action),
        "window_start_sec": float(start),
        "window_end_sec": float(end),
        "provider": str(window.get("provider") or ""),
        "provenance": str(window.get("provenance") or ""),
    }


def _candidate_from_explicit(entry, index):
    if not isinstance(entry, dict):
        raise ValueError(f"candidate {index} is not an object")
    candidate_id = _text(entry.get("candidate_id") or entry.get("actionId"), "candidate id", 256)
    start = entry.get("window_start_sec", entry.get("startSec"))
    end = entry.get("window_end_sec", entry.get("endSec"))
    action = entry.get("action_video_sec", entry.get("actionVideoSec"))
    if not candidate_id:
        raise ValueError(f"candidate {index} has no candidate_id")
    if not (_number(start) and _number(end) and 0 <= start < end):
        raise ValueError(f"candidate {candidate_id} has an invalid window")
    if not (_number(action) and start <= action <= end):
        raise ValueError(f"candidate {candidate_id} has no action_video_sec")
    importance = entry.get("importance")
    if importance is not None and not (_number(importance) and 0 <= importance <= 100):
        raise ValueError("candidate importance must be between 0 and 100")
    return {
        "candidate_id": candidate_id,
        "label": _text(entry.get("label") or candidate_id, "candidate label"),
        "type": _text(entry.get("type") or entry.get("pbp_type") or "unknown", "candidate type", 256),
        "importance": importance if _number(importance) else None,
        "action_video_sec": float(action),
        "window_start_sec": float(start),
        "window_end_sec": float(end),
        "provider": str(entry.get("provider") or ""),
        "provenance": str(entry.get("provenance") or ""),
    }


def build_context(inputs):
    """Return {candidates, sync_anchor, duration_sec, rights, event} or raise ValueError."""
    manifest = inputs.get("manifest")
    candidates = []
    if "manifest" in inputs:
        manifest = _object(manifest, "manifest")
        if manifest.get("state") != "succeeded":
            raise ValueError("manifest must be succeeded")
        rights = _rights(manifest.get("rights"))
        windows = manifest.get("windows")
        if not isinstance(windows, list) or not 1 <= len(windows) <= MAX_CANDIDATES:
            raise ValueError("manifest has no candidate windows")
        candidates = [_candidate_from_window(window, index) for index, window in enumerate(windows)]
        anchor = _object(manifest.get("syncAnchor"), "sync anchor")
        source = _object(manifest.get("source"), "source")
        duration = _object(source.get("ffprobe"), "source.ffprobe").get("durationSec")
        event = manifest.get("event")
        source_sha256 = _source_digest(source.get("sha256"))
    else:
        explicit = inputs.get("candidates")
        if not isinstance(explicit, list) or not 1 <= len(explicit) <= MAX_CANDIDATES:
            raise ValueError("provide a ClipManifest in `manifest` or a non-empty `candidates` list")
        candidates = [_candidate_from_explicit(entry, index) for index, entry in enumerate(explicit)]
        anchor = _object(inputs.get("sync_anchor", inputs.get("syncAnchor")), "sync anchor")
        duration = inputs.get("duration_sec", inputs.get("durationSec"))
        rights = _rights(inputs.get("rights"))
        event = inputs.get("event")
        source_sha256 = _source_digest(inputs.get("source_sha256"))
    event = _object(event, "event")
    for field in ("provider", "sport", "eventId"):
        _text(event.get(field), f"event.{field}")
    if not (_number(duration) and 0 < duration <= 24 * 60 * 60):
        raise ValueError("source duration must be finite and between 0 and 86400 seconds")
    if any(c["window_end_sec"] > duration for c in candidates):
        raise ValueError("candidate window exceeds source duration")
    ids = [c["candidate_id"] for c in candidates]
    if len(set(ids)) != len(ids):
        raise ValueError("candidate ids must be unique")
    video_sec = anchor.get("videoSec", anchor.get("video_sec"))
    clock_sec = anchor.get("clockSec", anchor.get("clock_sec"))
    if not (_number(video_sec) and 0 <= video_sec <= duration and _number(clock_sec) and clock_sec >= 0):
        raise ValueError("sync anchor requires numeric videoSec and clockSec")
    return {
        "candidates": candidates,
        "sync_anchor": {"video_sec": float(video_sec), "clock_sec": float(clock_sec)},
        "duration_sec": float(duration) if _number(duration) else None,
        "rights": rights,
        "event": event if isinstance(event, dict) else {},
        "source_sha256": source_sha256,
        "manifest_sha256": _sha256_json(manifest) if manifest is not None else None,
    }


def build_prompt(context):
    anchor = context["sync_anchor"]
    lines = []
    if context.get("duration_sec"):
        lines.append(f"Video duration: {context['duration_sec']} seconds.")
    lines.append(f"Sync anchor: video second {anchor['video_sec']} equals match clock {anchor['clock_sec']}s.")
    lines.append("Candidate moments selected from the play-by-play feed (validate, refine, rank — do not add candidates):")
    for candidate in context["candidates"]:
        lines.append(
            f"- {candidate['candidate_id']}: {candidate['label']} (type {candidate['type']}), "
            f"window {candidate['window_start_sec']}s–{candidate['window_end_sec']}s, "
            f"feed places the action near {candidate['action_video_sec']}s."
        )
    lines.append("Return JSON matching the schema. Descriptions at most 20 words.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# validation (fail closed) and ranking
# ---------------------------------------------------------------------------

def validate_output(raw_text, candidates, duration_sec=None):
    """Return (data, problems). data is None whenever any problem exists."""
    problems = []
    if not isinstance(raw_text, str) or not raw_text.strip() or len(raw_text) > MAX_MODEL_TEXT:
        return None, ["model returned no text"]
    try:
        def reject_constant(value):
            raise ValueError(f"non-finite number {value}")
        def unique_object(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate object key")
                result[key] = value
            return result
        data = json.loads(raw_text, parse_constant=reject_constant, object_pairs_hook=unique_object)
    except (TypeError, ValueError, RecursionError) as error:
        return None, [f"model output is not JSON: {error}"]
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list):
        return None, ["candidates[] missing"]
    if len(data["candidates"]) > MAX_CANDIDATES:
        return None, ["too many model candidates"]
    if set(data) - {"candidates", "discovered_moments", "refusal"}:
        problems.append("unknown response fields")
    by_id = {c["candidate_id"]: c for c in candidates}
    seen = set()
    for entry in data["candidates"]:
        if not isinstance(entry, dict):
            problems.append("candidate entry is not an object")
            continue
        cid = entry.get("candidate_id")
        if not isinstance(cid, str) or cid not in by_id:
            problems.append(f"unknown candidate_id {cid!r} (the model may not add candidates)")
            continue
        if cid in seen:
            problems.append(f"duplicate candidate_id {cid!r}")
            continue
        seen.add(cid)
        if set(entry) - {"candidate_id", "refined_start_sec", "refined_end_sec", "relevance", "hype",
                         "editorial_safety", "confidence", "verdict", "description"}:
            problems.append(f"{cid} has unknown fields")
        for field in ("relevance", "hype", "editorial_safety"):
            value = entry.get(field)
            if not (isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100):
                problems.append(f"{cid}.{field} out of range: {value!r}")
        confidence = entry.get("confidence")
        if not (_number(confidence) and 0 <= confidence <= 1):
            problems.append(f"{cid}.confidence out of range: {confidence!r}")
        if entry.get("verdict") not in VERDICTS:
            problems.append(f"{cid}.verdict invalid: {entry.get('verdict')!r}")
        start, end = entry.get("refined_start_sec"), entry.get("refined_end_sec")
        if not (_number(start) and _number(end) and 0 <= start < end
                and (duration_sec is None or end <= duration_sec)):
            problems.append(f"{cid} refined window invalid: {start!r}-{end!r}")
        else:
            window = by_id[cid]
            if abs(start - window["window_start_sec"]) > REFINEMENT_TOLERANCE_SEC or abs(end - window["window_end_sec"]) > REFINEMENT_TOLERANCE_SEC:
                problems.append(f"{cid} refined window drifts more than {REFINEMENT_TOLERANCE_SEC:g}s from the candidate window")
        if not isinstance(entry.get("description"), str) or not 1 <= len(entry["description"]) <= 2000:
            problems.append(f"{cid}.description missing")
    missing = set(by_id) - seen
    if missing:
        problems.append(f"candidates missing from output: {sorted(missing)}")
    if not isinstance(data.get("discovered_moments"), list) or len(data["discovered_moments"]) > MAX_DISCOVERIES:
        problems.append("discovered_moments[] missing")
    else:
        for moment in data["discovered_moments"]:
            if not (isinstance(moment, dict) and not set(moment) - {"approx_sec", "label", "confidence"}
                    and _number(moment.get("approx_sec")) and 0 <= moment["approx_sec"]
                    and (duration_sec is None or moment["approx_sec"] <= duration_sec)
                    and isinstance(moment.get("label"), str) and 1 <= len(moment["label"]) <= 2000
                    and _number(moment.get("confidence")) and 0 <= moment["confidence"] <= 1):
                problems.append("discovered_moments entry malformed")
                break
    refusal = data.get("refusal")
    if refusal is not None and (not isinstance(refusal, str) or len(refusal) > 2000):
        problems.append("refusal must be a string")
    return (data if not problems else None), problems


def pbp_fallback_ranking(candidates):
    """Deterministic baseline: PBP importance desc, then timeline order. Verdict hold, scores null."""
    ordered = sorted(candidates, key=lambda c: (-(c["importance"] if c["importance"] is not None else 0), c["action_video_sec"]))
    return [
        {
            "candidate_id": c["candidate_id"], "rank": index + 1, "verdict": "hold", "source": "pbp-importance",
            "relevance": None, "hype": None, "editorial_safety": None, "confidence": None,
            "refined_start_sec": c["window_start_sec"], "refined_end_sec": c["window_end_sec"],
            "pbp_importance": c["importance"], "label": c["label"], "type": c["type"],
            "description": "Deterministic play-by-play ranking; computer-vision scores unavailable.",
        }
        for index, c in enumerate(ordered)
    ]


def model_ranking(data, candidates):
    by_id = {c["candidate_id"]: c for c in candidates}
    verdict_order = {"keep": 0, "hold": 1, "reject": 2}
    entries = sorted(
        data["candidates"],
        key=lambda e: (verdict_order[e["verdict"]], -e["relevance"], -e["hype"], -e["confidence"], by_id[e["candidate_id"]]["action_video_sec"]),
    )
    return [
        {
            "candidate_id": e["candidate_id"], "rank": index + 1, "verdict": e["verdict"], "source": "gemini-cv",
            "relevance": e["relevance"], "hype": e["hype"], "editorial_safety": e["editorial_safety"],
            "confidence": e["confidence"], "refined_start_sec": e["refined_start_sec"], "refined_end_sec": e["refined_end_sec"],
            "pbp_importance": by_id[e["candidate_id"]]["importance"], "label": by_id[e["candidate_id"]]["label"],
            "type": by_id[e["candidate_id"]]["type"], "description": e["description"],
        }
        for index, e in enumerate(entries)
    ]


def _result(context, config, *, ranking, degraded, reasons, fallback_mode, discovered=None, refusal=None,
            usage=None, latency_ms=None, model_meta=None):
    return {
        "status": True,
        "data": {
            "contract_version": CONTRACT_VERSION,
            "route": ROUTE,
            "prompt_version": PROMPT_VERSION,
            "provider": config["provider"],
            "model": config["model"],
            "processing": config["processing"],
            "thinking_level": config["thinking_level"],
            "degraded": degraded,
            "degraded_reasons": reasons,
            "fallback_mode": fallback_mode,
            "candidate_ids": [c["candidate_id"] for c in context["candidates"]],
            "ranking": ranking,
            "discovered_moments": discovered or [],
            "refusal": refusal,
            "usage": usage,
            "latency_ms": latency_ms,
            "request_sha256": config["request_sha256"],
            "ranking_id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_sha256": context["source_sha256"],
            "manifest_sha256": context["manifest_sha256"],
            "rights_sha256": _sha256_json(context["rights"]),
            "media_verified": (model_meta or {}).get("model_meta", {}).get("verified_source_sha256") == context["source_sha256"],
            "event": context["event"],
            **(model_meta or {}),
        },
    }


# ---------------------------------------------------------------------------
# provider transports (network). Kept small and swappable for tests.
# ---------------------------------------------------------------------------

def _sdk_interactions_available():
    try:
        from google import genai  # noqa: F401
        return hasattr(genai.Client, "interactions") or any("interactions" in name for name in dir(genai))
    except Exception:
        return False


def route_capabilities(request_data=None, *_, **__):
    """Describe what this route can do in this runtime. No model call."""
    try:
        from google import genai
        sdk_version = getattr(genai, "__version__", "unknown")
    except Exception:
        sdk_version = None
    return {
        "status": True,
        "data": {
            "route": ROUTE, "contract_version": CONTRACT_VERSION, "prompt_version": PROMPT_VERSION,
            "providers": list(PROVIDERS), "processing": list(PROCESSING), "thinking_levels": list(THINKING),
            "default_model": DEFAULT_MODEL, "google_genai_sdk": sdk_version,
            "agentic_available": {"ai_studio": True, "vertex_ai": False},
            "inline_video_limit_bytes": INLINE_VIDEO_LIMIT_BYTES,
            "max_video_bytes": MAX_VIDEO_BYTES,
            "requires_source_sha256": True,
        },
    }


def _make_client(config, secrets):
    from google import genai
    if config["provider"] == "ai_studio":
        if not secrets.get("api_key"):
            raise ValueError("api_key is required for ai_studio")
        return genai.Client(api_key=secrets["api_key"])
    from google.oauth2 import service_account
    if not secrets.get("project_id"):
        raise ValueError("project_id is required for vertex_ai")
    credentials = None
    credential = secrets.get("credential")
    if credential:
        if isinstance(credential, str):
            credential = json.loads(credential)
        credentials = service_account.Credentials.from_service_account_info(
            credential, scopes=["https://www.googleapis.com/auth/cloud-platform"])
    return genai.Client(vertexai=True, project=secrets["project_id"], location=config["location"], credentials=credentials)


def _http(method, url, headers, body=None, timeout=60):
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def _ai_studio_upload(api_key, path, mime_type, timeout):
    """Files API resumable upload; returns {uri, mime_type, name}. Waits until ACTIVE."""
    size = os.path.getsize(path)
    status, headers, body = _http(
        "POST", f"{AI_STUDIO_BASE}/upload/v1beta/files",
        {"x-goog-api-key": api_key, "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start",
         "X-Goog-Upload-Header-Content-Length": str(size), "X-Goog-Upload-Header-Content-Type": mime_type,
         "Content-Type": "application/json"},
        json.dumps({"file": {"display_name": os.path.basename(path)}}).encode(), timeout)
    if status != 200:
        raise RuntimeError(f"files upload start failed: HTTP {status}")
    upload_url = next((v for k, v in headers.items() if k.lower() == "x-goog-upload-url"), None)
    if not upload_url:
        raise RuntimeError("files upload start returned no upload URL")
    with open(path, "rb") as handle:
        status, _, body = _http("POST", upload_url, {"Content-Length": str(size), "X-Goog-Upload-Offset": "0",
                                                      "X-Goog-Upload-Command": "upload, finalize"}, handle, timeout)
    if status != 200:
        raise RuntimeError(f"files upload finalize failed: HTTP {status}")
    info = json.loads(body)["file"]
    deadline = time.time() + timeout
    while info.get("state") == "PROCESSING" and time.time() < deadline:
        time.sleep(3)
        status, _, body = _http("GET", f"{AI_STUDIO_BASE}/v1beta/{info['name']}", {"x-goog-api-key": api_key}, None, 60)
        if status == 200:
            info = json.loads(body)
    if info.get("state") != "ACTIVE":
        raise RuntimeError(f"uploaded video did not become ACTIVE: {info.get('state')}")
    return {"uri": info["uri"], "mime_type": info.get("mimeType", mime_type), "name": info["name"]}


def _download_gcs_snapshot(uri, secrets, destination, limit, timeout):
    """Read one object generation with authenticated storage, never a mutable provider URI."""
    from google.cloud import storage
    from google.oauth2 import service_account
    parsed = urllib.parse.urlsplit(uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path.strip("/") or parsed.query or parsed.fragment:
        raise ValueError("video URI must be a gs://bucket/object without query or fragment")
    credential = secrets.get("credential")
    if isinstance(credential, str):
        credential = json.loads(credential)
    credentials = (service_account.Credentials.from_service_account_info(credential)
                   if credential else None)
    storage_client = storage.Client(project=secrets.get("project_id"), credentials=credentials)
    blob = storage_client.bucket(parsed.netloc).blob(parsed.path.lstrip("/"))
    blob.reload(timeout=timeout)
    if not isinstance(blob.size, int) or not 0 < blob.size <= limit:
        raise ValueError("source exceeds verified-media byte budget; no unverified URI fallback")
    # Both the generation and the precondition stay pinned across retries.
    generation = blob.generation
    pinned = storage_client.bucket(parsed.netloc).blob(parsed.path.lstrip("/"), generation=generation)
    with open(destination, "xb") as handle:
        pinned.download_to_file(handle, if_generation_match=generation, timeout=timeout,
                                start=0, end=limit - 1, raw_download=True)
    return str(generation)


def _resolve_video(config, secrets, client):
    """Send only bytes matching the extraction digest, or an upload of that private snapshot.

    Vertex inputs above the inline budget fail explicitly. Passing a mutable gs:// URL
    after hashing it would reopen a hash-to-model TOCTOU gap; there is no such fallback.
    """
    video = config["video"]
    mime_type = video["mime_type"]
    limit = INLINE_VIDEO_LIMIT_BYTES if config["provider"] == "vertex_ai" else MAX_VIDEO_BYTES
    with tempfile.TemporaryDirectory(prefix="gemini-cv-verified-") as directory:
        snapshot = os.path.join(directory, "source.mp4")
        generation = None
        if video.get("uri"):
            generation = _download_gcs_snapshot(video["uri"], secrets, snapshot, limit, config["timeout_sec"])
        else:
            # Open before checking, so a symlink/FIFO swap cannot change what is read.
            fd = os.open(video["path"], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as source, open(snapshot, "xb") as target:
                before = os.fstat(source.fileno())
                if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= limit:
                    raise ValueError("source exceeds verified-media byte budget or is not a regular file")
                total = 0
                while chunk := source.read(1024 * 1024):
                    total += len(chunk)
                    if total > limit:
                        raise ValueError("source exceeds verified-media byte budget")
                    target.write(chunk)
                after = os.fstat(source.fileno())
                if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                    raise ValueError("source changed during snapshot")
        size = os.path.getsize(snapshot)
        if not 0 < size <= limit:
            raise ValueError("source exceeds verified-media byte budget")
        with open(snapshot, "rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        if digest != config["source_sha256"]:
            raise ValueError("source digest does not match approved extraction manifest")
        meta = {"verified_source_sha256": digest, "video_bytes": size, "storage_generation": generation}
        if config["provider"] == "ai_studio" and (config["processing"] == "agentic" or size > INLINE_VIDEO_LIMIT_BYTES):
            uploaded = _ai_studio_upload(secrets["api_key"], snapshot, mime_type, config["timeout_sec"])
            return {"uri": uploaded["uri"], "mime_type": uploaded["mime_type"]}, {**meta, "video_source": "verified-files-api"}
        with open(snapshot, "rb") as handle:
            return {"bytes": handle.read(), "mime_type": mime_type}, {**meta, "video_source": "verified-inline"}


def _static_transport(config, secrets, context, prompt):
    """generateContent with the video attached. Returns (raw_text, usage, meta)."""
    from google.genai import types
    client = _make_client(config, secrets)
    video_ref, meta = _resolve_video(config, secrets, client)
    if "bytes" in video_ref:
        video_part = types.Part.from_bytes(data=video_ref["bytes"], mime_type=video_ref["mime_type"])
    else:
        video_part = types.Part.from_uri(file_uri=video_ref["uri"], mime_type=video_ref["mime_type"])
    generation = {
        "system_instruction": SYSTEM_INSTRUCTION,
        "temperature": 0,
        "max_output_tokens": config["max_output_tokens"],
        "response_mime_type": "application/json",
        "response_json_schema": RESPONSE_SCHEMA,
        "http_options": types.HttpOptions(timeout=int(config["timeout_sec"] * 1000)),
    }
    thinking_fields = set(getattr(types.ThinkingConfig, "model_fields", {}))
    if "thinking_level" in thinking_fields:
        generation["thinking_config"] = types.ThinkingConfig(thinking_level=config["thinking_level"].upper())
        meta["thinking"] = config["thinking_level"]
    else:
        meta["thinking"] = "model-default (SDK has no thinking_level)"
    started = time.time()
    response = client.models.generate_content(
        model=config["model"], contents=[video_part, prompt], config=types.GenerateContentConfig(**generation))
    meta["latency_ms"] = int((time.time() - started) * 1000)
    usage = None
    if getattr(response, "usage_metadata", None) is not None:
        usage = json.loads(response.usage_metadata.model_dump_json(exclude_none=True))
    finish = None
    try:
        finish = str(response.candidates[0].finish_reason)
    except Exception:
        pass
    meta["finish_reason"] = finish
    return getattr(response, "text", None), usage, meta


def _agentic_transport(config, secrets, context, prompt):
    """Interactions API with processing:"agentic" (ai_studio REST surface). Returns (raw_text, usage, meta)."""
    if config["provider"] != "ai_studio":
        raise RuntimeError("agentic-unavailable: the Interactions API is only reachable through ai_studio in this runtime")
    video_ref, meta = _resolve_video(config, secrets, None)
    body = {
        "model": config["model"],
        "system_instruction": SYSTEM_INSTRUCTION,
        "input": [{"type": "video", "uri": video_ref["uri"], "mime_type": video_ref["mime_type"], "processing": "agentic"},
                  {"type": "text", "text": prompt}],
        "generation_config": {"thinking_level": config["thinking_level"], "max_output_tokens": config["max_output_tokens"]},
        "response_format": {"type": "text", "mime_type": "application/json", "schema": RESPONSE_SCHEMA},
        "store": False,
    }
    started = time.time()
    status, _, raw = _http("POST", f"{AI_STUDIO_BASE}/v1beta/interactions",
                           {"x-goog-api-key": secrets["api_key"], "Content-Type": "application/json"},
                           json.dumps(body).encode(), config["timeout_sec"])
    meta["latency_ms"] = int((time.time() - started) * 1000)
    if status != 200:
        raise RuntimeError(f"interactions request failed: HTTP {status}: {raw[:300].decode(errors='replace')}")
    interaction = json.loads(raw)
    meta["interaction_status"] = interaction.get("status")
    meta["navigation_steps"] = sum(1 for s in interaction.get("steps", []) if s.get("type") in ("processing_call", "processing_result"))
    if interaction.get("status") != "completed":
        raise RuntimeError(f"interaction status is {interaction.get('status')!r}, not 'completed'")
    text = None
    for step in interaction.get("steps", []):
        if step.get("type") == "model_output":
            for part in step.get("content", []):
                if part.get("type") == "text" and part.get("text"):
                    text = part["text"]
    return text, interaction.get("usage"), meta


# ---------------------------------------------------------------------------
# command
# ---------------------------------------------------------------------------

def _config(inputs, context):
    provider = str(inputs.get("provider") or "vertex_ai").lower()
    processing = str(inputs.get("processing") or "static").lower()
    thinking = str(inputs.get("thinking_level") or "low").lower()
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {PROVIDERS}")
    if processing not in PROCESSING:
        raise ValueError(f"processing must be one of {PROCESSING}")
    if thinking not in THINKING:
        raise ValueError(f"thinking_level must be one of {THINKING}")
    video = inputs.get("video")
    if isinstance(video, str):
        video = {"path": video} if not video.startswith(("gs://", "https://", "http://")) else {"uri": video}
    if not isinstance(video, dict):
        raise ValueError("video is required: {gcs_uri|uri|path, mime_type}")
    refs = [video[k] for k in ("uri", "gcs_uri", "file_uri", "path") if k in video]
    if len(refs) != 1:
        raise ValueError("video must specify exactly one source reference")
    reference = _text(refs[0], "video reference", 4096)
    video = {"path" if "path" in video else "uri": reference,
             "mime_type": _text(video.get("mime_type", "video/mp4"), "video mime_type", 100)}
    if "uri" in video and not reference.startswith("gs://"):
        raise ValueError("remote video must be authenticated gs:// media; arbitrary URLs cannot prove source bytes")
    timeout_sec = inputs.get("timeout_sec", DEFAULT_TIMEOUT_SEC)
    max_output_tokens = inputs.get("max_output_tokens", DEFAULT_MAX_OUTPUT_TOKENS)
    if not (_number(timeout_sec) and 0 < timeout_sec <= 600):
        raise ValueError("timeout_sec must be finite and between 0 and 600")
    if not (isinstance(max_output_tokens, int) and not isinstance(max_output_tokens, bool) and 1 <= max_output_tokens <= 65536):
        raise ValueError("max_output_tokens must be an integer between 1 and 65536")
    config = {
        "provider": provider, "processing": processing, "thinking_level": thinking,
        "model": str(inputs.get("model_name") or inputs.get("model") or DEFAULT_MODEL),
        "location": str(inputs.get("location") or DEFAULT_LOCATION),
        "video": video, "timeout_sec": timeout_sec, "max_output_tokens": max_output_tokens,
        "source_sha256": context["source_sha256"],
    }
    config["request_sha256"] = _sha256_json({
        "prompt_version": PROMPT_VERSION, "model": config["model"], "processing": processing, "thinking": thinking,
        "provider": provider, "location": config["location"], "video": video, "context": context,
        "max_output_tokens": max_output_tokens, "candidates": context["candidates"], "sync_anchor": context["sync_anchor"],
    })
    return config


def rank_highlight_candidates(request_data, *_, transport=None, **__):
    inputs = _inputs(request_data)
    try:
        context = build_context(inputs)
        config = _config(inputs, context)
    except (ValueError, TypeError, OverflowError, RecursionError) as error:
        return _error(400, str(error))
    secrets = {"api_key": _secret(inputs, "api_key", "TEMP_CONTEXT_VARIABLE_GOOGLE_GENERATIVE_AI_API_KEY"),
               "project_id": _secret(inputs, "project_id", "TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID"),
               "credential": _secret(inputs, "credential", "TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL")}
    fallback = pbp_fallback_ranking(context["candidates"])

    if config["processing"] == "agentic" and config["provider"] != "ai_studio" and transport is None:
        return _result(context, config, ranking=fallback, degraded=True, fallback_mode="pbp-importance",
                       reasons=["agentic-unavailable: processing 'agentic' is not reachable through "
                                f"{config['provider']} in this runtime; static was NOT substituted"])

    prompt = build_prompt(context)
    run = transport or (_agentic_transport if config["processing"] == "agentic" else _static_transport)
    try:
        raw_text, usage, meta = run(config, secrets, context, prompt)
    except Exception as error:  # provider error, timeout, upload failure, missing credential
        return _result(context, config, ranking=fallback, degraded=True, fallback_mode="pbp-importance",
                       reasons=[_provider_error(error, secrets)])
    meta = dict(meta) if isinstance(meta, dict) else {}
    latency_ms = meta.pop("latency_ms", None)
    data, problems = validate_output(raw_text, context["candidates"], context["duration_sec"])
    if data is None:
        return _result(context, config, ranking=fallback, degraded=True, fallback_mode="pbp-importance",
                       reasons=[f"schema-violation: {p}" for p in problems], usage=usage, latency_ms=latency_ms,
                       model_meta={"model_meta": meta, "raw_output_excerpt": (str(raw_text) if raw_text else "")[:1000]})
    refusal = data.get("refusal") or None
    if refusal:
        return _result(context, config, ranking=fallback, degraded=True, fallback_mode="pbp-importance",
                       reasons=[f"model-refusal: {refusal}"[:500]], discovered=data.get("discovered_moments"),
                       refusal=refusal, usage=usage, latency_ms=latency_ms, model_meta={"model_meta": meta})
    return _result(context, config, ranking=model_ranking(data, context["candidates"]), degraded=False, reasons=[],
                   fallback_mode="none", discovered=data.get("discovered_moments"), refusal=None, usage=usage,
                   latency_ms=latency_ms, model_meta={"model_meta": meta})
