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


def aggregate_manifest(inputs):
    """Run the extraction across a list of workflow names + emit a draft.

    Inputs (from the calling workflow task):
        - workflow_names: list[str] OR comma-separated string
        - template_name:  str
        - description:    str

    Returns a dict shaped like `project.manifest.yml`.
    """
    from core.system.database import MongoDBConnection  # available inside pyscript runtime

    workflow_names = _coerce_workflow_names(inputs.get("workflow_names"))
    template_name = (inputs.get("template_name") or "unnamed-template").strip()
    description   = (inputs.get("description")   or "").strip()

    if not workflow_names:
        return {
            "ok": False,
            "error": "workflow_names is required and must be a non-empty list (or comma-separated string)",
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

    return {
        "ok": True,
        "manifest": manifest,
        "stats": {
            "workflows_seen": len(workflows_seen),
            "workflows_missing": len(missing),
            "credentials": len(creds),
            "connectors": len(connectors),
            "datasets_read": len(ds_reads),
            "datasets_written": len(ds_writes),
            "agents": len(agents),
            "workflow_calls": len(wf_calls),
        },
        "missing": missing,
        "datasets_read_only": sorted(ds_reads - ds_writes),  # external deps to track elsewhere
        "agents": sorted(agents),
        "workflow_calls": sorted(wf_calls),
    }
