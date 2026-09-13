#!/usr/bin/env python3
"""Plan, capture, assemble, import, verify, and close the 104-match archive."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


CONNECTOR = _module("worldcup_bulk_connector", ROOT / "worldcup-market-intelligence.py")
ARCHIVE = _module("worldcup_bulk_archive", ROOT / "tools" / "worldcup_archive.py")

CAPTURE_WORKFLOWS = (
    "worldcup-get-event-context",
    "worldcup-get-squads",
    "worldcup-get-injuries",
    "worldcup-get-match-forecast",
    "worldcup-archive-capture-players",
)
TERMINAL = {"FT", "AET", "PEN"}


def _read(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _score_pair(value: Any, label: str, *, optional: bool = False) -> dict[str, int] | None:
    if not isinstance(value, dict):
        if optional and value is None:
            return None
        raise ARCHIVE.ArchivePreparationError(f"result details {label} must be an object")
    home, away = value.get("home"), value.get("away")
    if home is None and away is None and optional:
        return None
    if isinstance(home, bool) or isinstance(away, bool) or not isinstance(home, int) or not isinstance(away, int) or home < 0 or away < 0:
        raise ARCHIVE.ArchivePreparationError(f"result details {label} must contain non-negative integer home/away scores")
    return {"home": home, "away": away}


def _event_team_provider_id(team: dict[str, Any]) -> str:
    logo = str(team.get("schema:logo") or team.get("crest") or "")
    match = re.search(r"/teams/(\d+)\.[A-Za-z0-9]+(?:\?.*)?$", logo)
    return match.group(1) if match else ""


def load_result_details(path: Path, events: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate one complete provider capture and build immutable per-fixture evidence."""
    execution = _read(path)
    if not isinstance(execution, dict):
        raise ARCHIVE.ArchivePreparationError("result details capture must be an object")
    if not execution.get("_id") or execution.get("name") != "worldcup-archive-capture-results" or str(execution.get("status") or "").lower() != "executed":
        raise ARCHIVE.ArchivePreparationError("result details capture label/status mismatch")
    outputs = ((execution.get("workflow_output") or {}).get("outputs"))
    if not isinstance(outputs, dict) or outputs.get("workflow-status") != "executed":
        raise ARCHIVE.ArchivePreparationError("result details capture has incomplete terminal outputs")
    payload = outputs.get("fixture_results")
    required = {"errors", "results", "paging", "parameters", "response"}
    if not isinstance(payload, dict) or not required <= set(payload):
        raise ARCHIVE.ArchivePreparationError("truncated result details payload")
    if payload.get("errors"):
        raise ARCHIVE.ArchivePreparationError("provider errors in result details payload")
    paging = payload.get("paging") if isinstance(payload.get("paging"), dict) else {}
    if paging.get("current") != 1 or paging.get("total") != 1:
        raise ARCHIVE.ArchivePreparationError("incomplete result details pagination")
    response = payload.get("response")
    if not isinstance(response, list) or payload.get("results") != len(response):
        raise ARCHIVE.ArchivePreparationError("result details response/results count mismatch")

    events_by_id = {str((event.get("provider_ids") or {}).get("api_football") or ""): event for event in events}
    if len(events) != 104 or len(events_by_id) != 104 or "" in events_by_id:
        raise ARCHIVE.ArchivePreparationError("result details require exactly 104 canonical fixture identities")
    canonical_ids = set(events_by_id)
    result_ids = [str(((row.get("fixture") or {}).get("id")) or "") for row in response if isinstance(row, dict)]
    if len(response) != len(events) or len(set(result_ids)) != len(events) or set(result_ids) != canonical_ids:
        raise ARCHIVE.ArchivePreparationError("result details fixture IDs/count do not exactly match the canonical fixtures")

    capture_sha256 = _sha_file(path)
    details_by_id, raw_by_id = {}, {}
    for row, fixture_id in zip(response, result_ids):
        event = events_by_id[fixture_id]
        fixture = row.get("fixture") if isinstance(row.get("fixture"), dict) else {}
        provider_status = fixture.get("status") if isinstance(fixture.get("status"), dict) else {}
        status = str(provider_status.get("short") or "").upper()
        event_status = str(event.get("sport:status") or "").upper()
        if status not in TERMINAL or status != event_status:
            raise ARCHIVE.ArchivePreparationError(f"result details status mismatch for fixture {fixture_id}")
        goals = _score_pair(row.get("goals"), "goals")
        live_score = _score_pair(event.get("live_score"), "event live_score")
        if goals != live_score:
            raise ARCHIVE.ArchivePreparationError(f"result details goals mismatch for fixture {fixture_id}")
        if provider_status.get("elapsed") != event.get("live_score", {}).get("elapsed"):
            raise ARCHIVE.ArchivePreparationError(f"result details elapsed status mismatch for fixture {fixture_id}")

        score = row.get("score") if isinstance(row.get("score"), dict) else {}
        regulation = _score_pair(score.get("fulltime"), "score.fulltime")
        extra_time = _score_pair(score.get("extratime"), "score.extratime", optional=True)
        shootout = _score_pair(score.get("penalty"), "score.penalty", optional=True)
        if status == "AET" and extra_time is None:
            raise ARCHIVE.ArchivePreparationError(f"result details AET score missing for fixture {fixture_id}")
        if status == "PEN" and (shootout is None or shootout["home"] == shootout["away"]):
            raise ARCHIVE.ArchivePreparationError(f"result details shootout score missing for fixture {fixture_id}")
        if status != "PEN" and shootout is not None:
            raise ARCHIVE.ArchivePreparationError(f"unexpected shootout score for fixture {fixture_id}")
        if status == "FT" and regulation != goals:
            raise ARCHIVE.ArchivePreparationError(f"result details regulation score mismatch for fixture {fixture_id}")
        if extra_time is not None and {
            "home": regulation["home"] + extra_time["home"],
            "away": regulation["away"] + extra_time["away"],
        } != goals:
            raise ARCHIVE.ArchivePreparationError(f"result details extra-time contribution mismatch for fixture {fixture_id}")

        provider_teams = row.get("teams") if isinstance(row.get("teams"), dict) else {}
        event_home, event_away = CONNECTOR._archive_event_teams(event)
        winner = None
        winner_flags = {}
        for qualifier, event_team in (("home", event_home), ("away", event_away)):
            provider_team = provider_teams.get(qualifier) if isinstance(provider_teams.get(qualifier), dict) else {}
            expected_id = _event_team_provider_id(event_team)
            if not expected_id or str(provider_team.get("id") or "") != expected_id or str(provider_team.get("name") or "") != str(event_team.get("name") or ""):
                raise ARCHIVE.ArchivePreparationError(f"result details team identity mismatch for fixture {fixture_id}/{qualifier}")
            flag = provider_team.get("winner")
            if flag is not None and not isinstance(flag, bool):
                raise ARCHIVE.ArchivePreparationError(f"result details winner flag is invalid for fixture {fixture_id}/{qualifier}")
            winner_flags[qualifier] = flag
            if flag is True:
                if winner is not None:
                    raise ARCHIVE.ArchivePreparationError(f"result details has multiple winners for fixture {fixture_id}")
                winner = {"qualifier": qualifier, "team_id": str(provider_team["id"]), "name": provider_team["name"]}
        decisive_score = shootout if status == "PEN" else goals
        expected_winner = None if decisive_score["home"] == decisive_score["away"] else ("home" if decisive_score["home"] > decisive_score["away"] else "away")
        if (winner or {}).get("qualifier") != expected_winner:
            raise ARCHIVE.ArchivePreparationError(f"result details winner flag mismatch for fixture {fixture_id}")
        if expected_winner is None and winner_flags != {"home": None, "away": None}:
            raise ARCHIVE.ArchivePreparationError(f"result details draw winner flags mismatch for fixture {fixture_id}")
        if expected_winner is not None:
            loser = "away" if expected_winner == "home" else "home"
            if winner_flags != {expected_winner: True, loser: False}:
                raise ARCHIVE.ArchivePreparationError(f"result details winner flags are incomplete for fixture {fixture_id}")

        details_by_id[fixture_id] = {
            "schema_version": CONNECTOR.FINAL_RESULT_DETAILS_VERSION,
            "fixture_id": fixture_id,
            "status": status,
            "regulation_time_score": regulation,
            "extra_time_score_contribution": extra_time,
            "shootout_score": shootout,
            "winner": winner,
            "provenance": {
                "provider": "api-football",
                "capture_name": execution["name"],
                "capture_id": str(execution.get("_id") or ""),
                "capture_file": str(path),
                "capture_sha256": capture_sha256,
                "fixture_id": fixture_id,
                "provider_result_sha256": CONNECTOR._archive_sha256(row),
            },
        }
        raw_by_id[fixture_id] = row
    return {
        "details_by_id": details_by_id,
        "raw_by_id": raw_by_id,
        "payload": payload,
        "source_info": {"path": path, "sha256": capture_sha256},
    }


def _value(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("value") if isinstance(row, dict) else None
    if not isinstance(value, dict):
        raise ARCHIVE.ArchivePreparationError("document row is missing value")
    return value


def load_bulk_sources(checklist_path: Path, baseline_dir: Path) -> dict[str, Any]:
    checklist = _read(checklist_path)
    manifest = _read(baseline_dir / "manifest.json")
    if not isinstance(checklist, list) or len(checklist) != 104:
        raise ARCHIVE.ArchivePreparationError("match checklist must enumerate exactly 104 fixtures")
    ids = [str(item.get("id") or "") for item in checklist]
    urns = [str(item.get("event_urn") or "") for item in checklist]
    if not all(ids) or not all(urns) or len(set(ids)) != 104 or len(set(urns)) != 104:
        raise ARCHIVE.ArchivePreparationError("match checklist fixture ids/URNs must be complete and unique")
    collections = {}
    for logical_name, expected in manifest.items():
        path = baseline_dir / f"{logical_name.replace(':', '-')}.json"
        rows = _read(path)
        if not isinstance(rows, list) or expected.get("expected") != len(rows) or expected.get("collected") != len(rows):
            raise ARCHIVE.ArchivePreparationError(f"baseline count mismatch for {logical_name}")
        if expected.get("sha256") != _sha_file(path):
            raise ARCHIVE.ArchivePreparationError(f"baseline hash mismatch for {logical_name}")
        collections[logical_name] = {"rows": rows, "path": path, "sha256": expected["sha256"]}
    events = [_value(row) for row in collections["worldcup:event"]["rows"]]
    events_by_id = {str((event.get("provider_ids") or {}).get("api_football") or ""): event for event in events}
    for item in checklist:
        event = events_by_id.get(str(item["id"]))
        if not event or str(event.get("_id") or event.get("@id") or "") != item["event_urn"]:
            raise ARCHIVE.ArchivePreparationError(f"checklist/baseline identity mismatch for fixture {item['id']}")
        if str(event.get("sport:status") or "").upper() not in TERMINAL:
            raise ARCHIVE.ArchivePreparationError(f"fixture is not terminal: {item['event_urn']}")
    return {"checklist": checklist, "manifest": manifest, "collections": collections, "events": events}


def build_capture_plan(sources: dict[str, Any], captures_dir: Path, journal: dict[str, Any] | None = None) -> dict[str, Any]:
    journal = journal or {}
    states = journal.get("items") if isinstance(journal.get("items"), dict) else {}
    items = []
    for fixture in sources["checklist"]:
        for workflow in CAPTURE_WORKFLOWS:
            key = f"{fixture['id']}:{workflow}"
            state = states.get(key) if isinstance(states.get(key), dict) else {}
            output = captures_dir / str(fixture["id"]) / f"{workflow}.json"
            if workflow == "worldcup-archive-capture-players":
                request = {"provider_event_id": str(fixture["id"])}
            else:
                request = {"event_urn": fixture["event_urn"], "provider_event_id": str(fixture["id"])}
                if workflow == "worldcup-get-match-forecast":
                    request["include_reasoning"] = False
            items.append({
                "key": key,
                "fixture_id": str(fixture["id"]),
                "event_urn": fixture["event_urn"],
                "workflow": workflow,
                "request": request,
                "output": str(output),
                "status": "captured" if output.exists() else state.get("status", "pending"),
                "workflow_run_id": state.get("workflow_run_id"),
                "attempts": int(state.get("attempts", 0)),
            })
    return {"schema_version": 1, "fixture_count": 104, "item_count": len(items), "items": items}


def build_replay_plan(manifest: dict[str, Any], replay_dir: Path, journal: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build deterministic post-import requests from archive entries, not invented selectors."""
    journal = journal or {}
    states = journal.get("items") if isinstance(journal.get("items"), dict) else {}
    items = []
    for entry in manifest.get("entries", []):
        endpoint = entry.get("endpoint")
        subject = entry.get("subject") if isinstance(entry.get("subject"), dict) else {}
        response = entry.get("response") if isinstance(entry.get("response"), dict) else {}
        requests: list[tuple[dict[str, Any], dict[str, Any]]] = []
        if endpoint == "worldcup-resolve":
            requests = [({"id": subject.get("key")}, response)]
        elif endpoint == "worldcup-get-schedule":
            requests = [({"limit": 500}, response)]
        elif endpoint in {"worldcup-get-standings", "worldcup-backtest-forecasts"}:
            requests = [({}, response)]
        elif endpoint == "worldcup-player-spotlight":
            requests = [({"player_urn": subject.get("key")}, response)]
        elif endpoint == "worldcup-get-player-performance-context":
            pack = response.get("fixture_player_pack") if isinstance(response.get("fixture_player_pack"), dict) else {}
            requests = [
                (
                    {"event_urn": subject.get("event_urn"), "player_urn": (item.get("player") or {}).get("_id")},
                    item.get("response") if isinstance(item.get("response"), dict) else {},
                )
                for item in pack.get("players", [])
                if (item.get("player") or {}).get("_id")
            ]
            if not requests and not pack and isinstance(subject.get("player"), dict):
                requests = [({"event_urn": subject.get("event_urn"), "player_urn": subject["player"].get("_id")}, response)]
        else:
            requests = [({"event_urn": subject.get("event_urn")}, response)]
        for index, (request, expected_response) in enumerate(requests):
            request_key = CONNECTOR._archive_sha256({"workflow": endpoint, "request": request})
            key = f"replay:{endpoint}:{request_key}"
            state = states.get(key) if isinstance(states.get(key), dict) else {}
            output = replay_dir / endpoint / f"{request_key}-{index}.json"
            items.append({
                "key": key, "workflow": endpoint, "request": request, "output": str(output),
                "status": "captured" if output.exists() else state.get("status", "pending"),
                "workflow_run_id": state.get("workflow_run_id"), "attempts": int(state.get("attempts", 0)),
                "expected_response": expected_response,
                "expected_response_sha256": CONNECTOR._archive_sha256(response),
            })
    return {"schema_version": 1, "item_count": len(items), "items": items}


def _decode_tool_result(result: Any) -> dict[str, Any]:
    wire = result.model_dump(by_alias=True)
    if wire.get("isError") is True:
        raise ARCHIVE.ArchivePreparationError("MCP tool returned isError=true")
    content = wire.get("content")
    if not isinstance(content, list):
        raise ARCHIVE.ArchivePreparationError("MCP result is missing content")
    texts = [item.get("text") for item in content if isinstance(item, dict) and isinstance(item.get("text"), str)]
    if len(texts) != 1:
        raise ARCHIVE.ArchivePreparationError("MCP result must contain exactly one JSON text payload")
    decoded = json.loads(texts[0])
    if not isinstance(decoded, dict):
        raise ARCHIVE.ArchivePreparationError("MCP JSON payload must be an object")
    status = str(decoded.get("status") or "").lower()
    if decoded.get("success") is False or decoded.get("status") is False or status in {"error", "failed", "failure"}:
        raise ARCHIVE.ArchivePreparationError(f"MCP tool returned a failed envelope: {decoded.get('error') or decoded.get('message') or status}")
    return decoded


def _payload_data(envelope: dict[str, Any]) -> Any:
    data = envelope.get("data")
    return data.get("data") if isinstance(data, dict) and "data" in data else data


class McpOperator:
    def __init__(self, session: Any):
        self.session = session

    async def execute_workflow(self, name: str, request: dict[str, Any]) -> str:
        decoded = _decode_tool_result(await self.session.call_tool(
            "execute_workflow", arguments={"name": name, "context": request},
        ))
        data = _payload_data(decoded)
        run_id = (data.get("workflow_run_id") if isinstance(data, dict) else None) or decoded.get("workflow_run_id")
        if not run_id:
            raise ARCHIVE.ArchivePreparationError(f"execute_workflow returned no workflow_run_id for {name}")
        return str(run_id)

    async def get_execution(self, run_id: str) -> dict[str, Any]:
        decoded = _decode_tool_result(await self.session.call_tool(
            "get_workflow_execution", arguments={
                "workflow_id": run_id,
                "compact": False,
                "fields": ["_id", "name", "status", "date", "workflow_output", "request_data", "tasks"],
            },
        ))
        data = _payload_data(decoded)
        if not isinstance(data, dict) or data.get("_id") != run_id:
            raise ARCHIVE.ArchivePreparationError(f"execution readback mismatch for {run_id}")
        return data

    async def create_document(self, row: dict[str, Any]) -> dict[str, Any]:
        decoded = _decode_tool_result(await self.session.call_tool(
            "create_document", arguments={"name": row["name"], "content": {"value": row["value"]}},
        ))
        data = _payload_data(decoded)
        return data if isinstance(data, dict) else {"data": data}

    async def search_documents_exact(self, filters: dict[str, Any], *, page_size: int = 100) -> list[dict[str, Any]]:
        rows, seen, page, declared_total = [], set(), 1, None
        while declared_total is None or len(rows) < declared_total:
            decoded = _decode_tool_result(await self.session.call_tool(
                "search_documents", arguments={"filters": filters, "page": page, "page_size": page_size},
            ))
            outer = decoded.get("data") if isinstance(decoded.get("data"), dict) else {}
            batch = outer.get("data")
            total = outer.get("total_documents")
            if not isinstance(batch, list) or not isinstance(total, int):
                raise ARCHIVE.ArchivePreparationError("search_documents omitted rows or declared total_documents")
            if declared_total is None:
                declared_total = total
            elif total != declared_total:
                raise ARCHIVE.ArchivePreparationError("search_documents total_documents changed during pagination")
            for row in batch:
                identity = str(row.get("_id") or (_value(row).get("_id")) or "")
                if not identity or identity in seen:
                    raise ARCHIVE.ArchivePreparationError("search_documents returned a missing/duplicate identity")
                seen.add(identity)
                rows.append(row)
            if not batch:
                break
            page += 1
        if declared_total != len(rows):
            raise ARCHIVE.ArchivePreparationError("search_documents exact pagination count mismatch")
        return rows


def _validate_replay_execution(item: dict[str, Any], execution: dict[str, Any]) -> None:
    outputs = ((execution.get("workflow_output") or {}).get("outputs"))
    if execution.get("name") != item["workflow"] or str(execution.get("status") or "").lower() != "executed" or not isinstance(outputs, dict):
        raise ARCHIVE.ArchivePreparationError(f"replay execution mismatch for {item['key']}")
    archive = outputs.get("archive") if isinstance(outputs.get("archive"), dict) else {}
    if archive.get("status") != "hit" or archive.get("version") != CONNECTOR.FINAL_ARCHIVE_VERSION:
        raise ARCHIVE.ArchivePreparationError(f"replay did not produce a v2 archive hit for {item['key']}")
    if item.get("expected_response_sha256") and archive.get("response_sha256") != item["expected_response_sha256"]:
        raise ARCHIVE.ArchivePreparationError(f"replay archive snapshot hash mismatch for {item['key']}")
    if outputs.get("workflow-status") != "executed":
        raise ARCHIVE.ArchivePreparationError(f"replay public workflow did not execute for {item['key']}")
    tokens = (((execution.get("workflow_output") or {}).get("audit") or {}).get("execution_tokens") or {})
    if "total_tokens" not in tokens or tokens.get("total_tokens") != 0:
        raise ARCHIVE.ArchivePreparationError(f"replay lacks explicit zero token accounting for {item['key']}")
    tasks = execution.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise ARCHIVE.ArchivePreparationError(f"replay task trace is missing for {item['key']}")
    executed_tasks = [task for task in tasks if isinstance(task, dict) and task.get("status") == "task-executed"]
    if not executed_tasks:
        raise ARCHIVE.ArchivePreparationError(f"replay has no executed task trace for {item['key']}")
    for task in tasks:
        if not isinstance(task, dict) or task.get("status") not in {"task-executed", "task-skipped"}:
            raise ARCHIVE.ArchivePreparationError(f"replay contains a failed task for {item['key']}")
        if task.get("status") != "task-executed":
            continue
        context = task.get("task_context") if isinstance(task.get("task_context"), dict) else {}
        if task.get("type") == "document":
            if (context.get("config") or {}).get("action") != "search":
                raise ARCHIVE.ArchivePreparationError(f"replay executed a document mutation for {item['key']}")
        elif task.get("type") == "connector":
            if (context.get("connector") or {}).get("name") != "worldcup-market-intelligence":
                raise ARCHIVE.ArchivePreparationError(f"replay executed a non-pure connector for {item['key']}")
        else:
            raise ARCHIVE.ArchivePreparationError(f"replay executed forbidden task type {task.get('type')} for {item['key']}")
    expected = item.get("expected_response") if isinstance(item.get("expected_response"), dict) else {}
    for key, value in expected.items():
        if key == "archive":
            actual_archive = outputs.get("archive") if isinstance(outputs.get("archive"), dict) else {}
            transport_fields = {"version", "status", "response_sha256", "source_manifest_sha256", "request_identity_sha256"}
            if any(actual_archive.get(field) != expected["archive"].get(field) for field in expected["archive"] if field not in transport_fields):
                raise ARCHIVE.ArchivePreparationError(f"replay archive metadata mismatch for {item['key']}")
        elif outputs.get(key) != value:
            raise ARCHIVE.ArchivePreparationError(f"replay public field mismatch for {item['key']}: {key}")


async def capture_with_operator(
    operator: McpOperator,
    plan: dict[str, Any],
    journal_path: Path,
    *,
    batch_size: int = 8,
    concurrency: int = 2,
    retries: int = 2,
) -> dict[str, Any]:
    if not 1 <= batch_size <= 100 or not 1 <= concurrency <= 2 or not 0 <= retries <= 5:
        raise ARCHIVE.ArchivePreparationError("capture bounds are batch_size=1..100, concurrency=1..2, retries=0..5")
    journal = _read(journal_path) if journal_path.exists() else {"schema_version": 1, "items": {}}
    states = journal.setdefault("items", {})
    plan_keys = {item["key"] for item in plan["items"]}
    initial_active = sum(
        1 for key, state in states.items()
        if key in plan_keys and isinstance(state, dict) and state.get("status") in {"dispatching", "dispatched"}
    )
    if initial_active > 2:
        raise ARCHIVE.ArchivePreparationError(f"journal contains {initial_active} active runs; maximum is 2")

    async def poll(item: dict[str, Any], state: dict[str, Any]) -> None:
        execution = await operator.get_execution(state["workflow_run_id"])
        status = str(execution.get("status") or "").lower()
        if status in {"executed", "completed", "success"}:
            try:
                if "expected_response" in item:
                    _validate_replay_execution(item, execution)
                output = Path(item["output"])
                _write(output, execution)
                state["status"] = "captured"
            except ARCHIVE.ArchivePreparationError as exc:
                state["status"] = "error"
                state["last_error"] = str(exc)
                _write(journal_path, journal)
                raise
        elif status in {"failed", "error", "cancelled", "skipped"}:
            state["status"] = "error"
            state["last_error"] = status
        else:
            state["status"] = "dispatched"
        _write(journal_path, journal)

    for item in plan["items"]:
        output = Path(item["output"])
        if output.exists() and "expected_response" in item:
            existing = _read(output)
            if not isinstance(existing, dict):
                raise ARCHIVE.ArchivePreparationError(f"invalid saved replay execution for {item['key']}")
            _validate_replay_execution(item, existing)
            states.setdefault(item["key"], {})["status"] = "captured"
        state = states.get(item["key"])
        if isinstance(state, dict) and state.get("status") == "dispatching" and not state.get("workflow_run_id"):
            raise ARCHIVE.ArchivePreparationError(f"uncertain dispatch requires operator recovery: {item['key']}")
        if isinstance(state, dict) and state.get("status") == "dispatched" and state.get("workflow_run_id"):
            await poll(item, state)
    _write(journal_path, journal)

    active = sum(
        1 for key, state in states.items()
        if key in plan_keys and isinstance(state, dict) and state.get("status") in {"dispatching", "dispatched"}
    )
    if active > 2:
        raise ARCHIVE.ArchivePreparationError(f"journal contains {active} active runs; maximum is 2")
    pending = []
    for item in plan["items"]:
        state = states.get(item["key"], {})
        if Path(item["output"]).exists() or state.get("status") in {"captured", "dispatched"}:
            continue
        if state.get("status") == "error" and int(state.get("attempts", 0)) > retries:
            continue
        pending.append(item)
    pending = pending[:min(batch_size, 2 - active)]
    semaphore = asyncio.Semaphore(concurrency)

    async def dispatch(item: dict[str, Any]) -> None:
        async with semaphore:
            state = states.setdefault(item["key"], {})
            state.update({
                "status": "dispatching",
                "attempts": int(state.get("attempts", 0)) + 1,
                "request": item["request"],
                "output": item["output"],
            })
            _write(journal_path, journal)
            run_id = await operator.execute_workflow(item["workflow"], item["request"])
            state.update({
                "status": "dispatched",
                "workflow_run_id": run_id,
            })
            _write(journal_path, journal)
            await poll(item, state)

    await asyncio.gather(*(dispatch(item) for item in pending))
    exhausted = [
        key for key, state in states.items()
        if key in plan_keys and isinstance(state, dict) and state.get("status") == "error" and int(state.get("attempts", 0)) > retries
    ]
    if exhausted:
        raise ARCHIVE.ArchivePreparationError(f"bounded retries exhausted for {len(exhausted)} run(s): {exhausted[:5]}")
    counts = {}
    for state in states.values():
        counts[state.get("status", "pending")] = counts.get(state.get("status", "pending"), 0) + 1
    return {"dispatched": len(pending), "counts": counts}


def _archive_metadata(capability: str, provenance: list[str], snapshot: Any, missing: list[str], note: str) -> dict[str, Any]:
    return {
        "mode": "final_archive", "competition": "FIFA World Cup 2026",
        "competition_status": "completed", "live": False, "snapshot_as_of": snapshot,
        "capability_status": capability, "provenance": provenance,
        "missing_capabilities": missing, "notes": [note],
    }


def _source(name: str, payload: Any, source_info: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "document_name": name,
        "source": name,
        "source_file": str(source_info["path"]),
        "source_file_sha256": source_info["sha256"],
        "source_payload": payload,
        "source_sha256": CONNECTOR._archive_sha256(payload),
        **extra,
    }


def _capture_task_statuses(execution: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = execution.get("tasks")
    if isinstance(tasks, list) and tasks:
        return [task for task in tasks if isinstance(task, dict)]
    metadata = execution.get("_capture_meta") if isinstance(execution.get("_capture_meta"), dict) else {}
    statuses = metadata.get("task_statuses")
    return [task for task in statuses if isinstance(task, dict)] if isinstance(statuses, list) else []


def _validate_capture_execution(
    execution: dict[str, Any],
    path: Path,
    *,
    fixture_id: str,
    event_urn: str,
    endpoint: str,
) -> dict[str, Any]:
    required = {"_id", "date", "name", "status", "workflow_output", "request_data"}
    if not required <= set(execution):
        raise ARCHIVE.ArchivePreparationError(f"truncated captured execution: {path}")
    outputs = ((execution.get("workflow_output") or {}).get("outputs"))
    request = ((execution.get("request_data") or {}).get("context-workflow"))
    if execution.get("name") != endpoint or str(execution.get("status") or "").lower() != "executed":
        raise ARCHIVE.ArchivePreparationError(f"captured execution label/status mismatch: {path}")
    if not isinstance(outputs, dict) or outputs.get("workflow-status") != "executed" or not isinstance(request, dict):
        raise ARCHIVE.ArchivePreparationError(f"captured execution has incomplete terminal outputs: {path}")
    task_statuses = _capture_task_statuses(execution)
    if not task_statuses or any(task.get("status") not in {"task-executed", "task-skipped"} for task in task_statuses):
        raise ARCHIVE.ArchivePreparationError(f"captured execution has missing or failed task trace: {path}")
    requested_fixture = str(request.get("provider_event_id") or request.get("fixture_id") or "")
    requested_event = str(request.get("event_urn") or "")
    if requested_fixture and requested_fixture != fixture_id:
        raise ARCHIVE.ArchivePreparationError(f"captured request fixture mismatch for {fixture_id}: {path}")
    if requested_event and requested_event != event_urn:
        raise ARCHIVE.ArchivePreparationError(f"captured request event mismatch for {fixture_id}: {path}")
    observed_event = str(outputs.get("event_urn") or "")
    if not observed_event:
        observed_event = str((outputs.get("forecast") or {}).get("_id") or (outputs.get("forecast") or {}).get("@id") or "")
    if not observed_event:
        candidates = outputs.get("candidates") if isinstance(outputs.get("candidates"), list) else []
        observed_event = str((candidates[0] if candidates else {}).get("event_urn") or "")
    if observed_event != event_urn:
        raise ARCHIVE.ArchivePreparationError(f"captured resolved event mismatch for {fixture_id}: {path}")
    required_output = {
        "worldcup-get-event-context": "event_context",
        "worldcup-get-squads": "squads",
        "worldcup-get-injuries": "injuries",
        "worldcup-get-match-forecast": "forecast",
        "worldcup-archive-capture-players": "player_stats",
        "worldcup-match-recap": "skill_card",
    }[endpoint]
    if not isinstance(outputs.get(required_output), dict):
        raise ARCHIVE.ArchivePreparationError(f"captured output is missing {required_output}: {path}")
    serialized = json.dumps(outputs, ensure_ascii=False).lower()
    transport_markers = ("rate limit", "rate-limit", "transport error", "timed out", "timeout", "connection error", "connector failed", '"status": 429')
    if any(marker in serialized for marker in transport_markers):
        raise ARCHIVE.ArchivePreparationError(f"capture contains a provider transport/rate-limit failure: {path}")
    if endpoint == "worldcup-get-match-forecast" and request.get("include_reasoning") is not False:
        raise ARCHIVE.ArchivePreparationError(f"forecast capture must set include_reasoning=false: {path}")
    if endpoint == "worldcup-archive-capture-players":
        stats = outputs.get("player_stats")
        required_stats = {"errors", "get", "paging", "parameters", "response", "results"}
        if not isinstance(stats, dict) or not required_stats <= set(stats):
            raise ARCHIVE.ArchivePreparationError(f"truncated fixture player payload: {path}")
        if stats.get("errors") or outputs.get("provider_errors"):
            raise ARCHIVE.ArchivePreparationError(f"provider errors in fixture player payload: {path}")
        paging = stats.get("paging") if isinstance(stats.get("paging"), dict) else {}
        if paging.get("current") != paging.get("total") or paging.get("current") != 1:
            raise ARCHIVE.ArchivePreparationError(f"incomplete fixture player pagination: {path}")
        if str((stats.get("parameters") or {}).get("fixture") or "") != fixture_id:
            raise ARCHIVE.ArchivePreparationError(f"fixture player parameters mismatch for {fixture_id}: {path}")
        response = stats.get("response")
        if not isinstance(response, list) or not isinstance(stats.get("results"), int) or stats["results"] != len(response):
            raise ARCHIVE.ArchivePreparationError(f"fixture player response/results mismatch: {path}")
    return outputs


def _captured_outputs(
    captures_dir: Path,
    fixture_id: str,
    event_urn: str,
    endpoint: str,
    *,
    required: bool = True,
) -> tuple[dict[str, Any], Path] | None:
    path = captures_dir / fixture_id / f"{endpoint}.json"
    if not path.exists():
        if required:
            raise ARCHIVE.ArchivePreparationError(f"missing required capture: {path}")
        return None
    execution = _read(path)
    if not isinstance(execution, dict):
        raise ARCHIVE.ArchivePreparationError(f"invalid captured execution: {path}")
    outputs = _validate_capture_execution(
        execution, path, fixture_id=fixture_id, event_urn=event_urn, endpoint=endpoint,
    )
    return outputs, path


def _entry(endpoint: str, subject: dict[str, Any], parameters: dict[str, Any], response: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "endpoint": endpoint, "subject": subject, "parameters": parameters,
        "response": response, "response_sha256": CONNECTOR._archive_sha256(response),
        "source_manifest": sources,
    }


def _captured_response(outputs: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps({key: value for key, value in outputs.items() if key != "workflow-status"}))


def _captured_generated_at(path: Path) -> str:
    execution = _read(path)
    for task in reversed(execution.get("tasks") or []):
        output = task.get("output_response") if isinstance(task, dict) else None
        candidates = [output]
        while candidates:
            value = candidates.pop()
            if isinstance(value, dict):
                if value.get("generated_at"):
                    return str(value["generated_at"])
                candidates.extend(value.values())
            elif isinstance(value, list):
                candidates.extend(value)
    return str((((execution.get("workflow_output") or {}).get("audit") or {}).get("finished_time")) or "")


def _capture_sources(endpoint: str, outputs: dict[str, Any], path: Path, fixture_id: str) -> list[dict[str, Any]]:
    provenance = ((outputs.get("archive") or {}).get("provenance")) if isinstance(outputs.get("archive"), dict) else []
    names = list(dict.fromkeys(str(item) for item in provenance if str(item))) or [f"capture:{endpoint}"]
    source_info = {"path": path, "sha256": _sha_file(path)}
    return [
        _source(name, outputs, source_info, temporal_scope="historical-fixture", fixture_id=fixture_id)
        for name in names
    ]


def _apply_result_details_to_recap(
    body: dict[str, Any],
    event: dict[str, Any],
    forecast: dict[str, Any],
    result_details: dict[str, Any] | None,
    generated_at: str,
) -> None:
    status = str(event.get("sport:status") or "").upper()
    if result_details:
        verified = CONNECTOR.build_grounded_match_recap({"params": {
            "event": event,
            "forecast": forecast,
            "result_details": result_details,
            "generated_at": generated_at,
        }})["data"]["body"]
        body["result_details"] = result_details
        body["sources"] = list(body.get("sources") or [])
        body["sources"].extend(source for source in verified["sources"] if source.get("source") == "api-football")
        if status in {"AET", "PEN"}:
            body["forecast_scorecard"] = verified["forecast_scorecard"]
        if status == "PEN":
            for key in ("headline", "summary", "final_score", "shootout_score", "winner", "what_it_means"):
                body[key] = verified[key]
        return
    if status not in {"AET", "PEN"}:
        return
    scorecard = body.get("forecast_scorecard") if isinstance(body.get("forecast_scorecard"), dict) else {}
    body["forecast_scorecard"] = {
        "actual_outcome": None,
        "predicted_outcome": scorecard.get("predicted_outcome"),
        "predicted_score": scorecard.get("predicted_score"),
        "hit": None,
        "regulation_outcome_status": "unavailable",
        "note": "The final score includes extra time or penalties. No source-backed regulation-time outcome is stored, so the regulation 1X2 forecast is not scored.",
    }


def _reuse_original_recap(raw: dict[str, Any], event: dict[str, Any], forecast: dict[str, Any]) -> dict[str, Any]:
    body = json.loads(json.dumps(raw.get("body") or {}))
    event_urn = str(event.get("_id") or event.get("@id") or "")
    body["event_urn"] = event_urn
    body["historical_perspective"] = "original_cached_matchday_copy"
    body["sources"] = [
        {"source": "worldcup:skill-match-recap", "subject_urn": event_urn, "generated_at": raw.get("generated_at")},
        {"source": "worldcup:event", "event_urn": event_urn, "provider_ids": dict(event.get("provider_ids") or {})},
        {"source": "worldcup:model-forecast", "event_urn": event_urn, "model_computed_at": ((forecast.get("model") or {}).get("computed_at"))},
    ]
    body["grounding"] = {
        "claims_scope": "original_cached_copy_with_unverified_narrative",
        "event_sha256": CONNECTOR._archive_sha256(event),
        "forecast_sha256": CONNECTOR._archive_sha256(forecast),
        "final_score_verified": True,
        "narrative_details_revalidated": False,
    }
    body["archive_caveats"] = [
        "Original cached matchday copy is preserved. Claims beyond fixture identity and final score were not independently revalidated for this archive release."
    ]
    return body


def assemble_bulk_manifest(
    checklist_path: Path,
    baseline_dir: Path,
    captures_dir: Path,
    executions_dir: Path,
    *,
    generated_at: str,
    result_details_path: Path | None = None,
) -> dict[str, Any]:
    sources = load_bulk_sources(checklist_path, baseline_dir)
    collections = sources["collections"]
    events = sources["events"]
    event_by_urn = {str(event.get("_id") or event.get("@id")): event for event in events}
    identities = [_value(row) for row in collections["worldcup:identity-crosswalk"]["rows"]]
    forecasts = [_value(row) for row in collections["worldcup:model-forecast"]["rows"]]
    forecast_by_urn = {str(row.get("_id") or row.get("@id")): row for row in forecasts}
    forecast_baseline_records = [
        {"id": str(row.get("_id") or row.get("@id") or ""), "value": row}
        for row in sorted(forecasts, key=lambda item: str(item.get("_id") or item.get("@id") or ""))
    ]
    rankings = collections["worldcup:final-fifa-player-power-ranking"]["rows"]
    raw_recaps = [_value(row) for row in collections["worldcup:skill-match-recap"]["rows"]]
    raw_recap_by_urn = {str(row.get("subject_urn") or row.get("event_urn") or ""): row for row in raw_recaps}
    raw_recap_audit = []
    for raw in raw_recaps:
        event_urn = str(raw.get("subject_urn") or raw.get("event_urn") or "")
        validation = CONNECTOR.validate_grounded_match_recap({"params": {"event": event_by_urn.get(event_urn, {}), "recap": raw}})["data"]
        raw_recap_audit.append({
            "event_urn": event_urn,
            "raw_source_sha256": CONNECTOR._archive_sha256(raw),
            "valid_for_final_archive": validation["valid"],
            "factually_valid": validation["factually_valid"],
            "format": validation["format"],
            "failures": validation["failures"],
        })
    targets = {endpoint: [] for endpoint in CONNECTOR.FINAL_ARCHIVE_ENDPOINTS}
    entries, fixture_coverage, fixture_player_urns = [], {}, {}
    event_source = collections["worldcup:event"]
    identity_source = collections["worldcup:identity-crosswalk"]
    forecast_source = collections["worldcup:model-forecast"]
    ranking_source = collections["worldcup:final-fifa-player-power-ranking"]
    recap_source = collections["worldcup:skill-match-recap"]
    result_evidence = load_result_details(result_details_path, events) if result_details_path else None
    result_details_by_id = result_evidence["details_by_id"] if result_evidence else {}
    raw_results_by_id = result_evidence["raw_by_id"] if result_evidence else {}
    recap_modes: dict[str, int] = {}

    schedule = CONNECTOR.normalize_schedule({"params": {"events": events, "limit": 500}})["data"]
    if result_evidence:
        for schedule_event in schedule["events"]:
            schedule_event["result_details"] = result_details_by_id[str(schedule_event["fixture_id"])]
    schedule_provenance = ["worldcup:event"] + (["api-football"] if result_evidence else [])
    schedule_response = {"schedule": schedule, "archive": _archive_metadata("complete", schedule_provenance, None, [], "Immutable 104-fixture final schedule."), "warnings": []}
    targets["worldcup-get-schedule"].append({"subject_key": "tournament", "parameters": {}})
    schedule_sources = [_source("worldcup:event", events, event_source, temporal_scope="tournament-archive")]
    if result_evidence:
        schedule_sources.append(_source("api-football", result_evidence["payload"], result_evidence["source_info"], temporal_scope="tournament-archive", fixture_count=104))
    entries.append(_entry("worldcup-get-schedule", {"key": "tournament", "canonical_event_count": 104}, {}, schedule_response, schedule_sources))

    for entity in identities + events:
        key = str(entity.get("_id") or entity.get("@id") or "")
        if not key:
            continue
        response = {"entity": entity, "entities": [entity], "count": 1, "warnings": [], "archive": _archive_metadata("complete", ["worldcup:identity-crosswalk" if entity in identities else "worldcup:event"], None, [], "Exact archived entity resolution.")}
        source_info = identity_source if entity in identities else event_source
        source_name = "worldcup:identity-crosswalk" if entity in identities else "worldcup:event"
        targets["worldcup-resolve"].append({"subject_key": key, "parameters": {}})
        entries.append(_entry("worldcup-resolve", {"key": key, "entity": entity}, {}, response, [_source(source_name, entity, source_info, temporal_scope="tournament-archive")]))

    for item in sources["checklist"]:
        fixture_id, event_urn = str(item["id"]), item["event_urn"]
        event, forecast = event_by_urn[event_urn], forecast_by_urn.get(event_urn)
        if not forecast:
            raise ARCHIVE.ArchivePreparationError(f"missing original forecast for {event_urn}")
        resolved = CONNECTOR.normalize_schedule({"params": {"events": [event], "limit": 1}})["data"]["events"][0]
        result_details = result_details_by_id.get(fixture_id)
        if result_details:
            resolved["result_details"] = result_details
        subject = {"key": event_urn, "event_urn": event_urn, "provider_event_id": fixture_id, "event": event}
        coverage = {}

        captured = _captured_outputs(captures_dir, fixture_id, event_urn, "worldcup-get-event-context")
        context_response = _captured_response(captured[0])
        if result_details:
            event_context = context_response.get("event_context") if isinstance(context_response.get("event_context"), dict) else None
            if event_context is None:
                raise ARCHIVE.ArchivePreparationError(f"event context cannot store result details for fixture {fixture_id}")
            event_context["result_details"] = result_details
        context_status = str((context_response.get("archive") or {}).get("capability_status") or "partial")
        context_sources = _capture_sources("worldcup-get-event-context", captured[0], captured[1], fixture_id)
        if result_details:
            context_sources.append(_source("api-football", raw_results_by_id[fixture_id], result_evidence["source_info"], temporal_scope="historical-fixture", fixture_id=fixture_id, capture_name="worldcup-archive-capture-results"))
            context_response["archive"]["provenance"] = list(dict.fromkeys(list(context_response["archive"].get("provenance") or []) + ["api-football"]))
        params = {"include_prematch_research": True, "include_social_pulse": False}
        targets["worldcup-get-event-context"].append({"subject_key": event_urn, "parameters": params})
        entries.append(_entry("worldcup-get-event-context", subject, params, context_response, context_sources))
        coverage["worldcup-get-event-context"] = context_status

        captured = _captured_outputs(captures_dir, fixture_id, event_urn, "worldcup-get-squads")
        squad_response = _captured_response(captured[0])
        squad_status = str((squad_response.get("archive") or {}).get("capability_status") or "partial")
        targets["worldcup-get-squads"].append({"subject_key": event_urn, "parameters": {}})
        entries.append(_entry("worldcup-get-squads", subject, {}, squad_response, _capture_sources("worldcup-get-squads", captured[0], captured[1], fixture_id)))
        coverage["worldcup-get-squads"] = squad_status

        captured = _captured_outputs(captures_dir, fixture_id, event_urn, "worldcup-get-injuries")
        injury_response = _captured_response(captured[0])
        injury_status = str((injury_response.get("archive") or {}).get("capability_status") or "partial")
        injury_params = {"league": "1", "season": "2026"}
        targets["worldcup-get-injuries"].append({"subject_key": event_urn, "parameters": injury_params})
        entries.append(_entry("worldcup-get-injuries", subject, injury_params, injury_response, _capture_sources("worldcup-get-injuries", captured[0], captured[1], fixture_id)))
        coverage["worldcup-get-injuries"] = injury_status

        captured = _captured_outputs(captures_dir, fixture_id, event_urn, "worldcup-archive-capture-players")
        raw_player_stats = captured[0]["player_stats"]
        pack = CONNECTOR.build_fixture_player_pack({"params": {
            "event": event,
            "player_stats": raw_player_stats,
            "identities": identities,
            "rankings": rankings,
        }})["data"]["fixture_player_pack"]
        if str(pack.get("event_urn") or "") != event_urn or str(pack.get("fixture_id") or "") != fixture_id:
            raise ARCHIVE.ArchivePreparationError(f"offline fixture player pack identity mismatch for {fixture_id}")
        player_status = "complete" if pack.get("player_count") else "unavailable"
        player_provenance = ["worldcup:event", "worldcup:identity-crosswalk", "fifa.com", "api-football"]
        player_response = {"fixture_player_pack": pack, "status": player_status, "warnings": pack.get("warnings", []), "archive": _archive_metadata(player_status, player_provenance, None, ["provider_player_statistics"] if player_status == "unavailable" else [], "One fixture-scoped pack; player selection occurs locally at read time.")}
        targets["worldcup-get-player-performance-context"].append({"subject_key": event_urn, "parameters": {}})
        player_sources = [
            _source("worldcup:event", event, event_source, temporal_scope="historical-fixture", fixture_id=fixture_id),
            _source("worldcup:identity-crosswalk", identities, identity_source, temporal_scope="tournament-archive", fixture_id=fixture_id),
            _source("fifa.com", {"fixture_player_pack": pack, "final_ranking_export_sha256": ranking_source["sha256"]}, ranking_source, temporal_scope="tournament-archive", fixture_id=fixture_id),
            _source("api-football", raw_player_stats, {"path": captured[1], "sha256": _sha_file(captured[1])}, temporal_scope="historical-fixture", fixture_id=fixture_id),
        ]
        entries.append(_entry("worldcup-get-player-performance-context", subject, {}, player_response, player_sources))
        fixture_player_urns[event_urn] = sorted({str((row.get("player") or {}).get("_id")) for row in pack.get("players", []) if (row.get("player") or {}).get("_id")})
        coverage["worldcup-get-player-performance-context"] = player_status

        captured = _captured_outputs(captures_dir, fixture_id, event_urn, "worldcup-get-match-forecast")
        forecast_response = _captured_response(captured[0])
        if forecast_response.get("forecast") != forecast:
            raise ARCHIVE.ArchivePreparationError(f"captured forecast differs from original baseline for {event_urn}")
        forecast_status = str((forecast_response.get("archive") or {}).get("capability_status") or "unavailable")
        forecast_params = {"include_reasoning": False, "min_gap_bps": 100}
        targets["worldcup-get-match-forecast"].append({"subject_key": event_urn, "parameters": forecast_params})
        forecast_sources = [_source("worldcup:model-forecast", forecast, forecast_source, temporal_scope="historical-fixture", fixture_id=fixture_id)]
        forecast_sources.extend(source for source in _capture_sources("worldcup-get-match-forecast", captured[0], captured[1], fixture_id) if source["document_name"] != "worldcup:model-forecast")
        entries.append(_entry("worldcup-get-match-forecast", subject, forecast_params, forecast_response, forecast_sources))
        coverage["worldcup-get-match-forecast"] = forecast_status

        raw_recap = raw_recap_by_urn.get(event_urn)
        recap_validation = CONNECTOR.validate_grounded_match_recap({"params": {"event": event, "recap": raw_recap or {}}})["data"]
        pilot = _captured_outputs(captures_dir, fixture_id, event_urn, "worldcup-match-recap", required=False)
        pilot_body = pilot[0].get("skill_card") if pilot else None
        pilot_validation = CONNECTOR.validate_grounded_match_recap({"params": {"event": event, "recap": pilot_body or {}}})["data"] if pilot_body else {"valid": False}
        if pilot_body and pilot_validation["valid"]:
            recap_body = pilot_body
            recap_generated_at = str((pilot[0].get("archive") or {}).get("snapshot_as_of") or _captured_generated_at(pilot[1]) or generated_at)
            recap_source_name = "capture:worldcup-match-recap"
            recap_mode = "captured_pilot"
            recap_note = "Validated captured recap pilot; no new generation was dispatched."
        elif raw_recap and recap_validation["factually_valid"]:
            recap_body = _reuse_original_recap(raw_recap, event, forecast)
            recap_generated_at = str(raw_recap.get("generated_at") or generated_at)
            recap_source_name = "worldcup:skill-match-recap-original-copy"
            recap_mode = "legacy_original_copy"
            recap_note = "Original cached matchday copy with final score verified; narrative details retain an explicit non-revalidation caveat."
        else:
            corrected = CONNECTOR.build_grounded_match_recap({"params": {"event": event, "forecast": forecast, "result_details": result_details or {}, "generated_at": generated_at}})["data"]
            recap_body = corrected["body"]
            recap_generated_at = generated_at
            recap_source_name = "worldcup:skill-match-recap-source-only"
            recap_mode = "deterministic_source_only"
            recap_note = "Conservative deterministic source-only retrospective; not LLM output."
        _apply_result_details_to_recap(recap_body, event, forecast, result_details, recap_generated_at)
        recap_modes[recap_mode] = recap_modes.get(recap_mode, 0) + 1
        corrected_payload = {"subject_urn": event_urn, "body": recap_body, "generated_at": recap_generated_at, "scope": "world-cup-2026-tournament", "raw_source_preserved": raw_recap is not None}
        recap_sources = [
            _source(recap_source_name, corrected_payload, {"path": pilot[1], "sha256": _sha_file(pilot[1])} if pilot_body and pilot_validation["valid"] else event_source, temporal_scope="historical-fixture", fixture_id=fixture_id, generated_at=recap_generated_at),
            _source("worldcup:event", event, event_source, temporal_scope="historical-fixture", fixture_id=fixture_id),
            _source("worldcup:model-forecast", forecast, forecast_source, temporal_scope="historical-fixture", fixture_id=fixture_id),
        ]
        if raw_recap is not None:
            recap_sources.append(_source("worldcup:skill-match-recap-raw", raw_recap, recap_source, temporal_scope="historical-fixture", fixture_id=fixture_id, generated_at=raw_recap.get("generated_at")))
        if result_details:
            recap_sources.append(_source("api-football", raw_results_by_id[fixture_id], result_evidence["source_info"], temporal_scope="historical-fixture", fixture_id=fixture_id, capture_name="worldcup-archive-capture-results"))
        recap_provenance = [recap_source_name, "worldcup:event", "worldcup:model-forecast"] + (["api-football"] if result_details else [])
        recap_response = {"skill_card": recap_body, "event_urn": event_urn, "resolved_fixture": resolved, "candidates": [resolved], "served_from": "final_archive", "warnings": list(recap_body.get("archive_caveats") or []), "archive": _archive_metadata("evergreen_editorial", recap_provenance, recap_generated_at, [], recap_note)}
        targets["worldcup-match-recap"].append({"subject_key": event_urn, "parameters": {}})
        entries.append(_entry("worldcup-match-recap", subject, {}, recap_response, recap_sources))
        coverage["worldcup-match-recap"] = "evergreen_editorial"
        fixture_coverage[event_urn] = coverage

    for endpoint in ("worldcup-get-standings", "worldcup-backtest-forecasts"):
        execution_path = executions_dir / f"{endpoint}.json"
        execution = _read(execution_path)
        outputs = dict(((execution.get("workflow_output") or {}).get("outputs")) or {})
        outputs.pop("workflow-status", None)
        subject_key = "world-cup-2026"
        parameters = CONNECTOR._archive_parameters(endpoint, ((execution.get("request_data") or {}).get("context-workflow")) or {})
        targets[endpoint].append({"subject_key": subject_key, "parameters": parameters})
        global_sources = []
        for provenance in outputs.get("archive", {}).get("provenance", []):
            payload = forecasts if provenance == "worldcup:model-forecast" else execution
            source_info = forecast_source if provenance == "worldcup:model-forecast" else {"path": execution_path, "sha256": _sha_file(execution_path)}
            global_sources.append(_source(provenance, payload, source_info, temporal_scope="tournament-archive"))
        if endpoint == "worldcup-backtest-forecasts" and outputs.get("track_record"):
            audit_payload = {"backtesting_report": outputs["track_record"]}
            global_sources.append(_source("worldcup:forecast-audit", audit_payload, {"path": execution_path, "sha256": _sha_file(execution_path)}, temporal_scope="tournament-archive"))
        entries.append(_entry(endpoint, {"key": subject_key}, parameters, outputs, global_sources))

    spotlight_targets = []
    identity_by_urn = {str(row.get("_id") or row.get("@id")): row for row in identities}
    for row in collections["worldcup:skill-player-spotlight"]["rows"]:
        spotlight = _value(row)
        player_urn = str(spotlight.get("subject_urn") or "")
        player = identity_by_urn.get(player_urn)
        if not player or not isinstance(spotlight.get("body"), dict) or not spotlight.get("generated_at"):
            continue
        spotlight_targets.append(player_urn)
        response = {"skill_card": spotlight["body"], "player_urn": player_urn, "resolved_player": player, "player_overview": {}, "candidates": [{"player_urn": player_urn, "name": player.get("name")}], "served_from": "final_archive", "warnings": [], "archive": _archive_metadata("archived_editorial", ["worldcup:skill-player-spotlight"], spotlight["generated_at"], [], "Finite archived spotlight; future generation is disabled at closure.")}
        targets["worldcup-player-spotlight"].append({"subject_key": player_urn, "parameters": {}})
        entries.append(_entry("worldcup-player-spotlight", {"key": player_urn, "player": player}, {}, response, [_source("worldcup:skill-player-spotlight", spotlight, collections["worldcup:skill-player-spotlight"], temporal_scope="tournament-archive", generated_at=spotlight["generated_at"])]))

    manifest = {
        "schema_version": 1, "archive_version": CONNECTOR.FINAL_ARCHIVE_VERSION,
        "coverage_scope": "all_104_fixtures", "publication_ready": True,
        "canonical_event_count": 104, "fixture_urns": [item["event_urn"] for item in sources["checklist"]],
        "recap_fixture_urns": [item["event_urn"] for item in sources["checklist"]],
        "grounded_recap_fixture_urns": [item["event_urn"] for item in sources["checklist"]],
        "fixture_player_packs": True,
        "fixture_player_targets": [
            {"event_urn": event_urn, "player_urn": player_urn, "subject_key": f"{event_urn}|{player_urn}"}
            for event_urn, player_urns in fixture_player_urns.items() for player_urn in player_urns
        ],
        "fixture_player_urns": fixture_player_urns, "spotlight_targets": sorted(spotlight_targets),
        "fixture_coverage": fixture_coverage, "targets": targets, "entries": entries,
        "expected_archive_count": len(entries),
        "forecast_baseline_records": forecast_baseline_records,
        "forecast_baseline_sha256": CONNECTOR._archive_sha256(forecast_baseline_records),
        "forecast_baseline_source_file_sha256": collections["worldcup:model-forecast"]["sha256"],
        "legacy_recap_audit": sorted(raw_recap_audit, key=lambda row: row["event_urn"]),
        "result_details_count": len(result_details_by_id),
        "result_details_capture_sha256": result_evidence["source_info"]["sha256"] if result_evidence else None,
        "recap_modes": recap_modes,
    }
    ARCHIVE.prepare_manifest(manifest)
    return manifest


def _forecast_export_records(export: Any) -> list[dict[str, Any]]:
    rows = _read(export) if isinstance(export, Path) else export
    if not isinstance(rows, list) or len(rows) != 104:
        raise ARCHIVE.ArchivePreparationError("fresh original-forecast export must contain exactly 104 rows")
    records = []
    for row in rows:
        if not isinstance(row, dict) or row.get("name") not in {None, "worldcup:model-forecast"}:
            raise ARCHIVE.ArchivePreparationError("fresh original-forecast export contains an unexpected document name")
        value = _value(row)
        identity = str(value.get("_id") or value.get("@id") or "")
        if not identity:
            raise ARCHIVE.ArchivePreparationError("fresh original-forecast export contains a missing identity")
        records.append({"id": identity, "value": value})
    records.sort(key=lambda item: item["id"])
    if len({item["id"] for item in records}) != 104:
        raise ARCHIVE.ArchivePreparationError("fresh original-forecast export identities are not unique")
    return records


def prepare_closure(
    manifest: dict[str, Any],
    readback: dict[str, Any],
    forecast_export: Any,
    *,
    closed_at: str,
) -> dict[str, Any]:
    documents = ARCHIVE.prepare_manifest(manifest)
    expected_ids = {row["value"]["_id"] for row in documents}
    ARCHIVE.verify_bundle(readback, manifest, expected_ids)
    rows, total = ARCHIVE.extract_mcp_document_rows(readback) if "content" in readback else (readback.get("documents", []), readback.get("total_count"))
    if total != len(documents):
        raise ARCHIVE.ArchivePreparationError("closure readback is not the exact full archive")
    baseline_records = manifest.get("forecast_baseline_records")
    if not isinstance(baseline_records, list) or len(baseline_records) != 104:
        raise ARCHIVE.ArchivePreparationError("closure manifest lacks the independent 104-row forecast baseline")
    baseline_records = sorted(baseline_records, key=lambda item: str(item.get("id") or ""))
    fresh_records = _forecast_export_records(forecast_export)
    if fresh_records != baseline_records:
        raise ARCHIVE.ArchivePreparationError("fresh original-forecast export differs from the assembly baseline")
    archived_records = sorted([
        {
            "id": str(row["value"]["response"]["forecast"].get("_id") or row["value"]["response"]["forecast"].get("@id") or ""),
            "value": row["value"]["response"]["forecast"],
        }
        for row in rows if row["value"].get("endpoint") == "worldcup-get-match-forecast"
    ], key=lambda item: item["id"])
    if archived_records != baseline_records:
        raise ARCHIVE.ArchivePreparationError("archive readback forecasts differ from the independent baseline")
    forecast_hash = CONNECTOR._archive_sha256(fresh_records)
    baseline_hash = CONNECTOR._archive_sha256(baseline_records)
    if manifest.get("forecast_baseline_sha256") != baseline_hash:
        raise ARCHIVE.ArchivePreparationError("manifest forecast baseline commitment is invalid")
    closure = CONNECTOR.build_final_archive_manifest({"params": {
        "fixture_urns": manifest["fixture_urns"], "fixture_coverage": manifest["fixture_coverage"],
        "grounded_recap_fixture_urns": manifest["grounded_recap_fixture_urns"],
        "fixture_player_urns": manifest["fixture_player_urns"], "spotlight_targets": manifest["spotlight_targets"],
        "archive_document_ids": sorted(expected_ids), "expected_archive_count": len(documents),
        "forecast_baseline_sha256": baseline_hash, "forecast_readback_sha256": forecast_hash,
        "closed_at": closed_at,
    }})
    return {"archive_version": CONNECTOR.FINAL_ARCHIVE_VERSION, "count": 1, "documents": [closure]}


def verify_import_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    documents = bundle.get("documents") if isinstance(bundle, dict) else None
    if not isinstance(documents, list) or not documents:
        raise ARCHIVE.ArchivePreparationError("import bundle must contain documents")
    if len(documents) > 100:
        raise ARCHIVE.ArchivePreparationError("import accepts at most 100 rows; prepare a bounded batch first")
    names = {row.get("name") for row in documents if isinstance(row, dict)}
    if names == {CONNECTOR.FINAL_ARCHIVE_MANIFEST_DOCUMENT}:
        if len(documents) != 1:
            raise ARCHIVE.ArchivePreparationError("closure import must contain exactly one manifest")
        state, _, warnings = CONNECTOR.validate_final_archive_manifest(documents)
        if state != "closed":
            raise ARCHIVE.ArchivePreparationError("invalid closure import: " + "; ".join(warnings))
        return {"verified": True, "count": 1, "kind": "closure"}
    if names != {CONNECTOR.FINAL_ARCHIVE_DOCUMENT}:
        raise ARCHIVE.ArchivePreparationError("import bundle mixes unsupported document types")
    result = ARCHIVE.verify_bundle(bundle)
    return {**result, "kind": "archive"}


def _sse_headers(token: str) -> dict[str, str]:
    return {"X-Api-Token": token} if token else {}


async def _open_operator(url: str, token: str):
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    headers = _sse_headers(token)
    transport = sse_client(url, headers=headers, timeout=90)
    read_stream, write_stream = await transport.__aenter__()
    session_context = ClientSession(read_stream, write_stream)
    session = await session_context.__aenter__()
    await session.initialize()
    return McpOperator(session), transport, session_context


async def _capture_apply(args: argparse.Namespace, plan: dict[str, Any]) -> dict[str, Any]:
    url, token = os.environ.get(args.url_env, ""), os.environ.get(args.token_env, "")
    if not url or not token:
        raise ARCHIVE.ArchivePreparationError(f"--apply requires {args.url_env} and {args.token_env}")
    operator, transport, session_context = await _open_operator(url, token)
    try:
        return await capture_with_operator(operator, plan, args.journal, batch_size=args.batch_size, concurrency=args.concurrency, retries=args.retries)
    finally:
        await session_context.__aexit__(None, None, None)
        await transport.__aexit__(None, None, None)


async def _import_apply(args: argparse.Namespace, bundle: dict[str, Any]) -> dict[str, Any]:
    url, token = os.environ.get(args.url_env, ""), os.environ.get(args.token_env, "")
    if not url or not token:
        raise ARCHIVE.ArchivePreparationError(f"--apply requires {args.url_env} and {args.token_env}")
    operator, transport, session_context = await _open_operator(url, token)
    try:
        journal = _read(args.journal) if args.journal.exists() else {"schema_version": 1, "imported_document_ids": []}
        imported = set(journal.get("imported_document_ids", []))
        written = 0
        for row in bundle["documents"]:
            document_id = row["value"]["_id"]
            filters = {"name": row["name"], "value._id": document_id}
            readback = await operator.search_documents_exact(filters, page_size=2)
            was_journaled = document_id in imported
            if not readback and was_journaled:
                raise ARCHIVE.ArchivePreparationError(f"journaled import row is missing on resume: {document_id}")
            if not readback:
                await operator.create_document(row)
                readback = await operator.search_documents_exact(filters, page_size=2)
                written += 1
            if len(readback) != 1 or readback[0].get("name") != row["name"] or readback[0].get("value") != row["value"]:
                raise ARCHIVE.ArchivePreparationError(f"exact import readback mismatch for {document_id}")
            if row["name"] == CONNECTOR.FINAL_ARCHIVE_MANIFEST_DOCUMENT:
                state, _, warnings = CONNECTOR.validate_final_archive_manifest(readback)
                if state != "closed":
                    raise ARCHIVE.ArchivePreparationError("closure readback failed manifest validation: " + "; ".join(warnings))
            else:
                ARCHIVE.verify_bundle({
                    "documents": readback,
                    "count": 1,
                    "unique_identity_count": 1,
                    "total_count": 1,
                    "offset": 0,
                }, expected_document_ids={document_id})
            imported.add(document_id)
            journal["imported_document_ids"] = sorted(imported)
            _write(args.journal, journal)
        return {"imported": written, "already_imported": len(bundle["documents"]) - written}
    finally:
        await session_context.__aexit__(None, None, None)
        await transport.__aexit__(None, None, None)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--checklist", type=Path, required=True)
    common.add_argument("--baseline", type=Path, required=True)
    plan = commands.add_parser("plan", parents=[common])
    plan.add_argument("--captures", type=Path, required=True)
    plan.add_argument("--journal", type=Path)
    plan.add_argument("--output", type=Path)
    plan.add_argument("--write", action="store_true")
    capture = commands.add_parser("capture", parents=[common])
    capture.add_argument("--captures", type=Path, required=True)
    capture.add_argument("--journal", type=Path, required=True)
    capture.add_argument("--batch-size", type=int, default=8)
    capture.add_argument("--concurrency", type=int, default=2)
    capture.add_argument("--retries", type=int, default=2)
    capture.add_argument("--apply", action="store_true")
    capture.add_argument("--url-env", default="WORLDCUP_MCP_URL")
    capture.add_argument("--token-env", default="WORLDCUP_MCP_TOKEN")
    replay = commands.add_parser("replay")
    replay.add_argument("--manifest", type=Path, required=True)
    replay.add_argument("--output-dir", type=Path, required=True)
    replay.add_argument("--journal", type=Path, required=True)
    replay.add_argument("--batch-size", type=int, default=8)
    replay.add_argument("--concurrency", type=int, default=2)
    replay.add_argument("--retries", type=int, default=2)
    replay.add_argument("--apply", action="store_true")
    replay.add_argument("--url-env", default="WORLDCUP_MCP_URL")
    replay.add_argument("--token-env", default="WORLDCUP_MCP_TOKEN")
    assemble = commands.add_parser("assemble", parents=[common])
    assemble.add_argument("--captures", type=Path, required=True)
    assemble.add_argument("--executions", type=Path, required=True)
    assemble.add_argument("--result-details", type=Path)
    assemble.add_argument("--generated-at", required=True)
    assemble.add_argument("--manifest-output", type=Path)
    assemble.add_argument("--output", type=Path)
    assemble.add_argument("--write", action="store_true")
    import_command = commands.add_parser("import")
    import_command.add_argument("--bundle", type=Path, required=True)
    import_command.add_argument("--journal", type=Path, required=True)
    import_command.add_argument("--apply", action="store_true")
    import_command.add_argument("--url-env", default="WORLDCUP_MCP_URL")
    import_command.add_argument("--token-env", default="WORLDCUP_MCP_TOKEN")
    verify = commands.add_parser("verify")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    close = commands.add_parser("close")
    close.add_argument("--manifest", type=Path, required=True)
    close.add_argument("--readback", type=Path, required=True)
    close.add_argument("--forecast-export", type=Path, required=True)
    close.add_argument("--closed-at", required=True)
    close.add_argument("--output", type=Path)
    close.add_argument("--write", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command in {"plan", "capture"}:
            sources = load_bulk_sources(args.checklist, args.baseline)
            journal = _read(args.journal) if args.journal and args.journal.exists() else {}
            result = build_capture_plan(sources, args.captures, journal)
            if args.command == "capture" and args.apply:
                result = asyncio.run(_capture_apply(args, result))
            elif args.command == "capture":
                result = {"dry_run": True, "pending": sum(item["status"] == "pending" for item in result["items"]), "item_count": result["item_count"]}
            elif args.write:
                if args.output is None:
                    raise ARCHIVE.ArchivePreparationError("plan --write requires --output")
                _write(args.output, result)
            print(json.dumps(result if args.command == "capture" else {"dry_run": not args.write, "fixture_count": 104, "item_count": result["item_count"]}, sort_keys=True))
        elif args.command == "replay":
            journal = _read(args.journal) if args.journal.exists() else {}
            plan = build_replay_plan(_read(args.manifest), args.output_dir, journal)
            result = asyncio.run(_capture_apply(args, plan)) if args.apply else {
                "dry_run": True, "pending": sum(item["status"] == "pending" for item in plan["items"]), "item_count": plan["item_count"],
            }
            print(json.dumps(result, sort_keys=True))
        elif args.command == "assemble":
            manifest = assemble_bulk_manifest(
                args.checklist,
                args.baseline,
                args.captures,
                args.executions,
                generated_at=args.generated_at,
                result_details_path=args.result_details,
            )
            documents = ARCHIVE.prepare_manifest(manifest)
            bundle = {"archive_version": CONNECTOR.FINAL_ARCHIVE_VERSION, "manifest_sha256": CONNECTOR._archive_sha256(manifest), "offset": 0, "next_offset": len(documents), "total_count": len(documents), "count": len(documents), "unique_identity_count": len(documents), "invalidated": False, "documents": documents}
            ARCHIVE.verify_bundle(bundle, manifest)
            if args.write:
                if args.manifest_output is None or args.output is None:
                    raise ARCHIVE.ArchivePreparationError("assemble --write requires --manifest-output and --output")
                _write(args.manifest_output, manifest)
                _write(args.output, bundle)
            print(json.dumps({
                "dry_run": not args.write,
                "fixture_count": 104,
                "archive_count": len(documents),
                "publication_ready": True,
                "result_details_count": manifest["result_details_count"],
                "recap_modes": manifest["recap_modes"],
            }, sort_keys=True))
        elif args.command == "import":
            bundle = _read(args.bundle)
            verify_import_bundle(bundle)
            result = asyncio.run(_import_apply(args, bundle)) if args.apply else {"dry_run": True, "would_import": len(bundle["documents"])}
            print(json.dumps(result, sort_keys=True))
        elif args.command == "verify":
            print(json.dumps(ARCHIVE.verify_bundle(_read(args.bundle), _read(args.manifest)), sort_keys=True))
        elif args.command == "close":
            closure = prepare_closure(
                _read(args.manifest), _read(args.readback), args.forecast_export, closed_at=args.closed_at,
            )
            if args.write:
                if args.output is None:
                    raise ARCHIVE.ArchivePreparationError("close --write requires --output")
                _write(args.output, closure)
            print(json.dumps({"dry_run": not args.write, "closure_ready": True, "count": 1}, sort_keys=True))
        return 0
    except (ARCHIVE.ArchivePreparationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"world cup bulk operation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
