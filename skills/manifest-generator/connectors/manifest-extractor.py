"""Manifest Extractor — pyscript connector for the manifest-generator skill.

Walks a list of workflow names, fetches each workflow_object from the
`workflow` Mongo collection, runs static extraction, and returns an
aggregated draft manifest ready to be rendered as YAML.

This duplicates the core extraction primitives from machina-client-api's
`core/workflow/dependency_graph.py` so the skill stays self-contained
within a template repo (no client-api code import). When the patterns
diverge, sync this file against the client-api one.

Commands exposed (see manifest-extractor.yml):
  - aggregate_manifest : the main entry point
"""

import re
from collections import OrderedDict

# Regex primitives — mirror dependency_graph.py
_CRED_PATTERN = re.compile(r"TEMP_CONTEXT_VARIABLE_[A-Z0-9_]+")
_GET_PATTERN = re.compile(r"\$\.get\(['\"]([a-z0-9_\-]+)['\"]")


def _walk_strings(obj):
    """Yield every string anywhere in a nested dict/list."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk_strings(v)


def _strip_yaml_quotes(s):
    """Workflow YAML quotes literals as `\"'name'\"`. Strip + reject expr noise."""
    if not isinstance(s, str):
        return None
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"'):
        s = s[1:-1]
    if not s or any(c in s for c in ("{", "}", "$", " ", "\n", "(", ")", "[", "]")):
        return None
    return s


def _extract_credentials(workflow_doc):
    found = set()
    for s in _walk_strings(workflow_doc):
        found.update(_CRED_PATTERN.findall(s))
    return found


def _extract_connectors(workflow_doc):
    out = set()
    for task in workflow_doc.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        if task.get("type") in ("connector", "prompt"):
            conn = task.get("connector") or {}
            if isinstance(conn, dict):
                name = conn.get("name")
                if isinstance(name, str) and name:
                    out.add(name)
    return out


def _extract_agents(workflow_doc):
    out = set()
    for task in workflow_doc.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        if task.get("type") == "agent":
            ag = task.get("agent") or task.get("agent_id") or task.get("agent_name")
            if isinstance(ag, str) and ag:
                out.add(ag)
    return out


def _extract_dataset_reads(workflow_doc):
    out = set()
    for task in workflow_doc.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        if task.get("type") != "document":
            continue
        cfg = task.get("config") or {}
        action = (cfg.get("action") or "").lower()
        if action not in ("search", "retrieve", "get", "find"):
            continue
        filters = task.get("filters") or {}
        if isinstance(filters, dict):
            name = _strip_yaml_quotes(filters.get("name"))
            if name:
                out.add(name)
    return out


def _extract_dataset_writes(workflow_doc):
    out = set()
    for task in workflow_doc.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        if task.get("type") != "document":
            continue
        cfg = task.get("config") or {}
        action = (cfg.get("action") or "").lower()
        if action not in ("update", "insert", "save", "upsert", "create"):
            continue
        docs = task.get("documents") or {}
        if isinstance(docs, dict):
            for ds_name in docs.keys():
                if isinstance(ds_name, str) and ds_name:
                    out.add(ds_name)
    return out


def _extract_workflow_calls(workflow_doc):
    out = set()
    for task in workflow_doc.get("tasks") or []:
        if not isinstance(task, dict):
            continue
        if task.get("type") in ("workflow", "execute-workflow"):
            ref = task.get("workflow") or task.get("workflow_id") or task.get("workflow_name")
            if isinstance(ref, str) and ref:
                out.add(ref)
    return out


# -------------------------------------------------------------------------
# Public connector commands
# -------------------------------------------------------------------------

def _coerce_workflow_names(raw):
    """Accept either a list[str] OR a comma/space/newline-separated string.

    The Studio Execute UI sometimes serialises array inputs as strings
    (single-line text input + JSON-escaped). To keep the operator UX clean
    we accept both shapes and normalise to list[str].
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    if isinstance(raw, str):
        # Split on common separators; ignore empties.
        import re
        parts = re.split(r"[,\n;]+|\s{2,}", raw.strip())
        return [p.strip() for p in parts if p.strip()]
    # Anything else — return empty so the caller hits the validation error.
    return []


def _coerce_bool(raw):
    """Coerce a string/bool/int to a bool. The Studio Execute UI sometimes
    passes JSON booleans as strings ("true" / "false")."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    if isinstance(raw, str):
        return raw.strip().lower() in ("true", "1", "yes", "y", "on")
    return False


def aggregate_manifest(request_data):
    """Run the extraction across a list of workflow names + emit a draft.

    Returns the Machina-canonical pyscript shape:
        {"status": True, "data": {...result...}, "message": "..."}

    The engine (core/workflow/runner/connector.py:95) checks
    `response.get("status") is not True` to decide failure; a non-True
    `status` triggers connector_execution_failed and drops most of the
    response. We always return `status: True` and put soft-fail flags
    inside `data` (data.ok = False with error_message when input bad).
    """
    try:
        data = _aggregate_manifest_inner(request_data)
    except Exception as exc:
        import traceback
        data = {
            "ok": False,
            "error_message": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc()[-1200:],
            "request_data_keys": sorted(list((request_data or {}).keys())),
            "manifest": {},
            "stats": {},
            "missing": [],
        }
    return {
        "status": True,
        "data": data,
        "message": "aggregate_manifest executed",
    }


def _aggregate_manifest_inner(request_data):
    from core.system.database import MongoDBConnection  # available inside pyscript runtime

    params = (request_data or {}).get("params") or {}
    raw_workflow_names = params.get("workflow_names")
    workflow_names = _coerce_workflow_names(raw_workflow_names)
    template_name = (params.get("template_name") or "unnamed-template").strip()
    description   = (params.get("description")   or "").strip()

    if not workflow_names:
        return {
            "ok": True,
            "status": "no_input",
            "error_message": (
                "workflow_names is required and must be a non-empty list "
                "(or comma-separated string)"
            ),
            "request_data_keys": sorted(list((request_data or {}).keys())),
            "params_keys": sorted(list(params.keys())),
            "workflow_names_type": type(raw_workflow_names).__name__,
            "workflow_names_repr": repr(raw_workflow_names)[:200],
            "manifest": {},
            "stats": {},
            "missing": [],
        }

    col = MongoDBConnection().get_collection("workflow")
    creds = set()
    connectors = set()
    ds_reads = set()
    ds_writes = set()
    agents = set()
    wf_calls = set()
    workflows_seen = []
    missing = []

    for name in workflow_names:
        doc = col.find_one({"name": name})
        if not doc:
            missing.append(name)
            continue
        workflows_seen.append(name)
        creds.update(_extract_credentials(doc))
        connectors.update(_extract_connectors(doc))
        ds_reads.update(_extract_dataset_reads(doc))
        ds_writes.update(_extract_dataset_writes(doc))
        agents.update(_extract_agents(doc))
        wf_calls.update(_extract_workflow_calls(doc))

    # Build the manifest skeleton. Source labels / validation rules / min_counts
    # are left empty — the operator (or the optional LLM enrichment task)
    # fills them in. Comments inline explain each block.
    manifest = OrderedDict()
    manifest["name"] = template_name
    manifest["version"] = 1
    if description:
        manifest["description"] = description

    manifest["required_credentials"] = [
        {
            "name": cred,
            "source_label": "",          # operator fills: "<service> API key (<console-url>)"
            "test_workflow": "",         # operator fills: "<connector>-test-credentials"
            "validation": None,           # operator fills via LLM enrichment task or by hand
        }
        for cred in sorted(creds)
    ]

    manifest["required_config_documents"] = []  # not extractable from workflows alone

    manifest["required_templates"] = [
        # The template itself — placeholder, operator fills in the repo URL.
        {
            "repo": "https://github.com/<org>/<repo>",
            "path": f"<path-to>/{template_name}",
            "reason": "This template",
        },
    ] + [
        # Each connector the workflows use likely points at a connector template.
        {
            "repo": "https://github.com/machina-sports/machina-templates",
            "path": f"connectors/{c}",
            "reason": f"Connector: {c}",
        }
        for c in sorted(connectors)
    ]

    manifest["depends_on_datasets"] = [
        # Datasets the workflows WRITE to — these are the data this template
        # produces and therefore the health signal for "is this project alive?".
        {
            "name": ds,
            "description": "",                  # operator fills
            "populated_by": "",                 # operator fills
            "min_count": 1,                     # conservative default
        }
        for ds in sorted(ds_writes)
    ]

    stats = {
        "workflows_seen": len(workflows_seen),
        "workflows_missing": len(missing),
        "credentials": len(creds),
        "connectors": len(connectors),
        "datasets_read": len(ds_reads),
        "datasets_written": len(ds_writes),
        "agents": len(agents),
        "workflow_calls": len(wf_calls),
    }
    external_datasets = sorted(ds_reads - ds_writes)

    # Persist the draft directly here — the engine doesn't interpolate
    # dynamic document keys in workflow `documents:` blocks, so we do
    # the save in code where we know the template_name.
    #
    # IMPORTANT: write the full Studio-visible doc shape (title, filename,
    # filetype, metadata.category, status, timestamps). A bare `{name,value}`
    # doc is technically in the collection but Studio's Documents tab filters
    # them out as orphans.
    draft_doc_name = f"{template_name}-manifest-draft"
    try:
        from datetime import datetime as _dt
        import yaml as _yaml
        now = _dt.utcnow()
        manifest_dict = _ordered_to_dict(manifest)
        # Render the manifest as YAML for display — operators prefer YAML
        # for project.manifest.yml drafts. Falls back to JSON if PyYAML
        # isn't available (it should be — it's a core platform dep).
        try:
            manifest_yaml = _yaml.dump(
                manifest_dict, default_flow_style=False, sort_keys=False, allow_unicode=True
            )
        except Exception:
            import json as _json
            manifest_yaml = _json.dumps(manifest_dict, indent=2)
        doc_col = MongoDBConnection().get_collection("document")
        existing = doc_col.find_one({"name": draft_doc_name}, {"created": 1})
        doc_col.update_one(
            {"name": draft_doc_name},
            {"$set": {
                "name": draft_doc_name,
                "title": f"Manifest draft — {template_name}",
                "filename": f"{template_name}.manifest.yml",
                "filetype": "yaml",
                "status": "active",
                "metadata": {
                    "category": "manifest-draft",
                    "template_name": template_name,
                    "generated_by": "manifest-generator",
                    "extraction_stats": stats,
                    "missing_workflows": missing,
                    "external_datasets": external_datasets,
                    "generated_at": now.isoformat(),
                },
                "value": {
                    "manifest": manifest_dict,
                    "manifest_yaml": manifest_yaml,
                    "extraction_stats": stats,
                    "missing_workflows": missing,
                    "external_datasets": external_datasets,
                    "template_name": template_name,
                    "generated_at": now.isoformat(),
                },
                "updated": now,
                **({"created": existing.get("created", now)} if existing else {"created": now}),
            }},
            upsert=True,
        )
    except Exception as exc:  # pragma: no cover — write is best-effort
        # Don't fail the run on persistence — caller still gets the manifest
        # in the response and can save it themselves.
        pass

    return {
        "ok": True,
        "manifest": _ordered_to_dict(manifest),
        "stats": stats,
        "missing": missing,
        "datasets_read_only": external_datasets,
        "agents": sorted(agents),
        "workflow_calls": sorted(wf_calls),
        "draft_doc_name": draft_doc_name,
    }


def _ordered_to_dict(o):
    """Recursively convert OrderedDict → regular dict so Mongo + the engine
    serialise it cleanly (some BSON encoders trip on OrderedDict)."""
    if isinstance(o, dict):
        return {k: _ordered_to_dict(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_ordered_to_dict(x) for x in o]
    return o


# -------------------------------------------------------------------------
# Auto-discovery (Sprint 5 / Nível A)
# -------------------------------------------------------------------------

def _infer_template_prefix(workflow_name):
    """Derive a template grouping key from a workflow name.

    Heuristic: most Machina workflows follow `<template>-<area>-<action>`
    or `<template>-<action>` naming. We take the first 1-2 segments as
    the group key. Single-segment names (rare) become their own group.

    Special-cases templates that publish multi-word prefixes like
    `byteplus-modelark-...` so they aren't split incorrectly.
    """
    parts = workflow_name.split("-")
    if not parts:
        return workflow_name

    # Multi-word known prefixes — extend as we onboard more templates.
    MULTI_WORD_PREFIXES = {
        ("byteplus", "modelark"),
        ("api", "football"),
        ("google", "genai"),
        ("google", "workstation"),
        ("google", "speech"),
        ("google", "vertex"),
        ("machina", "ai"),
        ("machina", "ai", "fast"),
        ("machina", "assistant"),
        ("machina", "cockpit"),
        ("daily", "football", "recap"),
        ("sports", "interaction"),
        ("sportradar", "soccer"),
        ("sportradar", "nba"),
        ("voice", "tts"),
        ("bwin", "coverage"),
        ("bwin", "assistant"),
        ("bwin", "data"),
        ("botandwin", "coverage"),
        ("personalized", "podcast"),
        ("bundesliga", "podcast"),
        ("event", "podcast"),
    }

    # Try longest match first
    for n in (3, 2):
        if len(parts) >= n and tuple(parts[:n]) in MULTI_WORD_PREFIXES:
            return "-".join(parts[:n])

    # Fall back to first segment
    return parts[0]


def discover_and_generate_all(request_data):
    """Auto-discover every installed template via workflow name prefixes,
    then run aggregate_manifest for each discovered template.

    Inputs (under request_data["params"]):
        - dry_run: bool (default false) — when true, only return the
                   group mapping without generating manifests
        - enrich_with_llm: bool (default false) — passed through

    Returns:
        {
          "status": True,
          "data": {
            "ok": True,
            "templates_found": [...],
            "drafts_written": [...],
            "summary": { templates: N, workflows_scanned: M, ... }
          }
        }
    """
    try:
        data = _discover_and_generate_inner(request_data)
    except Exception as exc:
        import traceback
        data = {
            "ok": False,
            "error_message": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc()[-1200:],
        }
    return {
        "status": True,
        "data": data,
        "message": "discover_and_generate_all executed",
    }


def _discover_and_generate_inner(request_data):
    from core.system.database import MongoDBConnection

    params = (request_data or {}).get("params") or {}
    dry_run = _coerce_bool(params.get("dry_run"))
    enrich_with_llm = _coerce_bool(params.get("enrich_with_llm"))

    # Step 1: list every workflow in this project's Mongo
    col = MongoDBConnection().get_collection("workflow")
    all_workflows = list(col.find({}, {"name": 1, "_id": 0}))
    names = [w.get("name") for w in all_workflows if w.get("name")]

    # Step 2: group by inferred template prefix
    groups = {}
    for n in names:
        key = _infer_template_prefix(n)
        groups.setdefault(key, []).append(n)

    # Pre-filter trivial groups (single workflows whose key matches their
    # name — these are usually `test-credentials` or one-shot utilities,
    # not full templates).
    full_groups = {k: v for k, v in groups.items() if len(v) >= 2 or k != v[0]}
    trivial_groups = {k: v for k, v in groups.items() if k not in full_groups}

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "templates_found": sorted(full_groups.keys()),
            "trivial_groups": sorted(trivial_groups.keys()),
            "summary": {
                "total_workflows": len(names),
                "groups": len(groups),
                "templates_with_drafts": len(full_groups),
            },
        }

    # Step 3: for each non-trivial group, run aggregate_manifest
    drafts_written = []
    failures = []
    for template_name, workflow_names in sorted(full_groups.items()):
        try:
            result = _aggregate_manifest_inner({
                "params": {
                    "workflow_names": workflow_names,
                    "template_name": template_name,
                    "description": f"Auto-discovered: {len(workflow_names)} workflows",
                },
            })
            if result.get("ok"):
                drafts_written.append({
                    "template": template_name,
                    "workflows": len(workflow_names),
                    "stats": result.get("stats", {}),
                    "draft_doc": result.get("draft_doc_name"),
                })
            else:
                failures.append({"template": template_name, "error": result.get("error_message")})
        except Exception as exc:  # noqa: BLE001 — keep walking
            failures.append({"template": template_name, "error": f"{type(exc).__name__}: {exc}"})

    return {
        "ok": True,
        "enrich_with_llm": enrich_with_llm,  # propagated for future use
        "templates_found": sorted(full_groups.keys()),
        "trivial_groups": sorted(trivial_groups.keys()),
        "drafts_written": drafts_written,
        "failures": failures,
        "summary": {
            "total_workflows": len(names),
            "groups": len(groups),
            "drafts_written": len(drafts_written),
            "failures": len(failures),
        },
    }
