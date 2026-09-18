#!/usr/bin/env python3
"""Prepare and verify immutable World Cup final-archive import bundles.

This tool is deliberately offline. It accepts a source-backed manifest containing
already validated endpoint responses and emits document-store import records. It
does not fetch data, invoke a model, or mutate a document store.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONNECTOR_PATH = ROOT / "worldcup-market-intelligence.py"
SPEC = importlib.util.spec_from_file_location("worldcup_archive_connector", CONNECTOR_PATH)
CONNECTOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(CONNECTOR)


class ArchivePreparationError(ValueError):
    pass


CANARY_EVENT_URN = "urn:machina:sport:soccer:event:brazil-vs-morocco:20260613:wor"
CANARY_FIXTURE_ID = "1489371"
CANARY_PLAYER_ID = "762"


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    path.write_text(encoded, encoding="utf-8")


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _value(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("value") if isinstance(row, dict) else None
    if not isinstance(value, dict):
        raise ArchivePreparationError("source export row is missing a value object")
    return value


def _load_export(export_dir: Path, logical_name: str, source_manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], str, Path]:
    filename = logical_name.replace(":", "-") + ".json"
    path = export_dir / filename
    rows = _read_json(path)
    if not isinstance(rows, list):
        raise ArchivePreparationError(f"source export must be a list: {path}")
    expected = source_manifest.get(logical_name)
    if not isinstance(expected, dict):
        raise ArchivePreparationError(f"source export manifest is missing {logical_name}")
    digest = _file_sha256(path)
    if expected.get("collected") != len(rows) or expected.get("expected") != len(rows):
        raise ArchivePreparationError(f"source export count mismatch for {logical_name}")
    if expected.get("sha256") != digest:
        raise ArchivePreparationError(f"source export file hash mismatch for {logical_name}")
    return rows, digest, path


def _source(document_name: str, source: str, payload: Any, path: Path, file_sha256: str, **metadata: Any) -> dict[str, Any]:
    return {
        "document_name": document_name,
        "source": source,
        "source_file": str(path),
        "source_file_sha256": file_sha256,
        "source_payload": payload,
        "source_sha256": CONNECTOR._archive_sha256(payload),
        **metadata,
    }


def capture_canary_manifest(executions_dir: Path, export_dir: Path) -> dict[str, Any]:
    """Build the one-fixture manifest only from captured executions and exports."""
    export_manifest = _read_json(export_dir / "manifest.json")
    if not isinstance(export_manifest, dict):
        raise ArchivePreparationError("source export manifest must be an object")
    loaded = {}
    for name in (
        "worldcup:event", "worldcup:model-forecast", "worldcup:identity-crosswalk",
        "worldcup:final-fifa-player-power-ranking", "worldcup:skill-match-recap",
        "worldcup:skill-player-spotlight",
    ):
        loaded[name] = _load_export(export_dir, name, export_manifest)

    event_rows = loaded["worldcup:event"][0]
    identity_rows = loaded["worldcup:identity-crosswalk"][0]
    forecast_rows = loaded["worldcup:model-forecast"][0]
    ranking_rows = loaded["worldcup:final-fifa-player-power-ranking"][0]
    recap_rows = loaded["worldcup:skill-match-recap"][0]
    spotlight_rows = loaded["worldcup:skill-player-spotlight"][0]
    if len(event_rows) != 104 or len(forecast_rows) != 104 or len(identity_rows) != 1281:
        raise ArchivePreparationError("canonical export counts do not match the captured World Cup universe")
    if len(ranking_rows) != 231 or len(recap_rows) != 13 or len(spotlight_rows) != 2:
        raise ArchivePreparationError("source-backed ranking/editorial export counts are incomplete")

    events = [_value(row) for row in event_rows]
    identities = [_value(row) for row in identity_rows]
    event_matches = [event for event in events if str((event.get("provider_ids") or {}).get("api_football")) == CANARY_FIXTURE_ID]
    player_matches = [player for player in identities if str((player.get("provider_ids") or {}).get("api_football")) == CANARY_PLAYER_ID]
    team_matches = [team for team in identities if str(team.get("_id") or team.get("@id") or "") == "urn:machina:sport:soccer:team:brazil:bra"]
    if len(event_matches) != 1 or len(player_matches) != 1 or len(team_matches) != 1:
        raise ArchivePreparationError("canary event/player/team identity is missing or ambiguous")
    event = event_matches[0]
    player = player_matches[0]
    team = team_matches[0]
    player_urn = str(player.get("_id") or player.get("@id") or "")

    forecast_matches = [_value(row) for row in forecast_rows if str((_value(row).get("provider_ids") or {}).get("api_football")) == CANARY_FIXTURE_ID]
    recap_matches = [_value(row) for row in recap_rows if str(_value(row).get("subject_urn") or "") == CANARY_EVENT_URN]
    spotlight_matches = [_value(row) for row in spotlight_rows if str(_value(row).get("subject_urn") or "") == player_urn]
    ranking_matches = [_value(row) for row in ranking_rows if str(_value(row).get("player_urn") or "") == player_urn]
    if len(forecast_matches) != 1 or len(recap_matches) != 1 or len(spotlight_matches) != 1 or len(ranking_matches) != 1:
        raise ArchivePreparationError("canary forecast/editorial source is missing or ambiguous")

    executions = {}
    for endpoint in sorted(CONNECTOR.FINAL_ARCHIVE_ENDPOINTS):
        path = executions_dir / f"{endpoint}.json"
        execution = _read_json(path)
        outputs = ((execution.get("workflow_output") or {}).get("outputs")) if isinstance(execution, dict) else None
        request = ((execution.get("request_data") or {}).get("context-workflow")) if isinstance(execution, dict) else None
        if execution.get("name") != endpoint or execution.get("status") != "executed":
            raise ArchivePreparationError(f"execution label/status mismatch for {endpoint}")
        if not isinstance(outputs, dict) or not isinstance(request, dict) or outputs.get("workflow-status") != "executed":
            raise ArchivePreparationError(f"execution payload is incomplete for {endpoint}")
        if any(any(marker in str(key).lower() for marker in ("credential", "secret", "token", "api_key")) for key in request):
            raise ArchivePreparationError(f"execution request contains unsafe context fields for {endpoint}")
        executions[endpoint] = (execution, dict(request), dict(outputs), path, _file_sha256(path))

    fixture_endpoints = {
        "worldcup-get-event-context", "worldcup-get-squads", "worldcup-get-injuries",
        "worldcup-get-player-performance-context", "worldcup-get-match-forecast", "worldcup-match-recap",
    }
    for endpoint in fixture_endpoints:
        outputs = executions[endpoint][2]
        observed = str(outputs.get("event_urn") or "")
        if not observed:
            observed = str(((outputs.get("forecast") or {}).get("_id")) or "")
        if not observed:
            observed = str((((outputs.get("player_performance_context") or {}).get("event") or {}).get("_id")) or "")
        if not observed:
            candidates = outputs.get("candidates") or []
            observed = str((candidates[0] if candidates else {}).get("event_urn") or "")
        if observed != CANARY_EVENT_URN:
            raise ArchivePreparationError(f"execution identity mismatch for {endpoint}: {observed!r}")
    if str((executions["worldcup-resolve"][2].get("entity") or {}).get("_id") or "") != team["_id"]:
        raise ArchivePreparationError("execution identity mismatch for worldcup-resolve")
    performance_player_id = str((((executions["worldcup-get-player-performance-context"][2].get("player_performance_context") or {}).get("player") or {}).get("player_id")) or "")
    if performance_player_id != CANARY_PLAYER_ID:
        raise ArchivePreparationError("execution identity mismatch for worldcup-get-player-performance-context")
    if str(executions["worldcup-player-spotlight"][2].get("player_urn") or "") != player_urn:
        raise ArchivePreparationError("execution identity mismatch for worldcup-player-spotlight")
    captured_schedule = executions["worldcup-get-schedule"][2].get("schedule") or {}
    if not captured_schedule.get("events") or any(
        "brazil" not in {CONNECTOR._canonical_team_slug(team_row.get("name")) for team_row in event_row.get("teams", [])}
        for event_row in captured_schedule.get("events", [])
    ):
        raise ArchivePreparationError("captured schedule is not the expected Brazil-filtered execution")

    schedule = CONNECTOR.normalize_schedule({"params": {"events": events, "limit": 500}})["data"]
    if schedule.get("count") != 104:
        raise ArchivePreparationError("full schedule regeneration did not produce all 104 canonical events")
    executions["worldcup-get-schedule"][2]["schedule"] = schedule

    standings = executions["worldcup-get-standings"][2].get("standings") or {}
    groups = standings.get("groups") if isinstance(standings, dict) else None
    if not isinstance(groups, list) or len(groups) != 12 or sum(len(group.get("table") or []) for group in groups) != 48:
        raise ArchivePreparationError("captured standings must contain 12 groups and 48 teams")
    if not isinstance(standings.get("third_place_ranking"), list):
        raise ArchivePreparationError("captured standings must preserve the separate third-place ranking")
    injuries = executions["worldcup-get-injuries"][2].get("injuries") or {}
    injury_ids = {
        str(item.get("fixture_id"))
        for team_row in injuries.get("teams", [])
        for item in team_row.get("missing", [])
        if isinstance(item, dict) and item.get("fixture_id") is not None
    }
    if injury_ids and injury_ids != {CANARY_FIXTURE_ID}:
        raise ArchivePreparationError("captured injuries are not scoped to the canary fixture")

    subjects = {
        "worldcup-resolve": {"key": team["_id"], "entity": team},
        "worldcup-get-schedule": {"key": "tournament", "canonical_event_count": 104},
        "worldcup-get-standings": {"key": "world-cup-2026", "league": "1", "season": "2026"},
        "worldcup-backtest-forecasts": {"key": "world-cup-2026"},
        "worldcup-player-spotlight": {"key": player_urn, "player": player},
        "worldcup-get-player-performance-context": {"key": f"{CANARY_EVENT_URN}|{player_urn}", "event_urn": CANARY_EVENT_URN, "provider_event_id": CANARY_FIXTURE_ID, "event": event, "player": player},
    }
    for endpoint in (
        "worldcup-get-event-context", "worldcup-get-squads", "worldcup-get-injuries",
        "worldcup-get-match-forecast", "worldcup-match-recap",
    ):
        subjects[endpoint] = {"key": CANARY_EVENT_URN, "event_urn": CANARY_EVENT_URN, "provider_event_id": CANARY_FIXTURE_ID, "event": event}

    export_sources = {
        "worldcup:event": (events, loaded["worldcup:event"]),
        "worldcup-event-cache": (events, loaded["worldcup:event"]),
        "worldcup:identity-crosswalk": (identities, loaded["worldcup:identity-crosswalk"]),
        "worldcup:model-forecast": (forecast_matches[0], loaded["worldcup:model-forecast"]),
        "worldcup:skill-match-recap": (recap_matches[0], loaded["worldcup:skill-match-recap"]),
        "worldcup:skill-player-spotlight": (spotlight_matches[0], loaded["worldcup:skill-player-spotlight"]),
        "fifa.com": (ranking_matches[0], loaded["worldcup:final-fifa-player-power-ranking"]),
    }
    entries = []
    targets = {}
    for endpoint in sorted(CONNECTOR.FINAL_ARCHIVE_ENDPOINTS):
        execution, request, outputs, execution_path, execution_hash = executions[endpoint]
        response = {key: value for key, value in outputs.items() if key != "workflow-status"}
        parameters = CONNECTOR._archive_parameters(endpoint, request)
        subject = subjects[endpoint]
        sources = []
        for provenance in response["archive"].get("provenance", []):
            if provenance in export_sources:
                payload, (_, file_hash, source_path) = export_sources[provenance]
                if endpoint == "worldcup-backtest-forecasts" and provenance == "worldcup:model-forecast":
                    payload = [_value(row) for row in forecast_rows]
                sources.append(_source(
                    provenance, provenance, payload, source_path, file_hash,
                    temporal_scope="historical-fixture" if endpoint in {
                        "worldcup-get-event-context", "worldcup-get-injuries", "worldcup-get-player-performance-context",
                        "worldcup-get-match-forecast", "worldcup-match-recap",
                    } else "tournament-archive",
                    fixture_id=CANARY_FIXTURE_ID if endpoint in {
                        "worldcup-get-event-context", "worldcup-get-injuries", "worldcup-get-player-performance-context",
                        "worldcup-get-match-forecast", "worldcup-match-recap",
                    } else None,
                ))
            else:
                sources.append(_source(
                    f"execution:{endpoint}", provenance, execution, execution_path, execution_hash,
                    temporal_scope="historical-fixture" if endpoint in {
                        "worldcup-get-event-context", "worldcup-get-injuries", "worldcup-get-player-performance-context",
                        "worldcup-get-match-forecast", "worldcup-match-recap",
                    } else "tournament-archive",
                    fixture_id=CANARY_FIXTURE_ID if endpoint in {
                        "worldcup-get-event-context", "worldcup-get-injuries", "worldcup-get-player-performance-context",
                        "worldcup-get-match-forecast", "worldcup-match-recap",
                    } else None,
                    execution_id=execution.get("_id"),
                ))
        if endpoint == "worldcup-backtest-forecasts":
            payload = {"backtesting_report": response.get("track_record")}
            sources.append(_source("worldcup:forecast-audit", "worldcup:forecast-audit", payload, execution_path, execution_hash, temporal_scope="tournament-archive"))
        if endpoint in {"worldcup-match-recap", "worldcup-player-spotlight"}:
            generated_at = response["archive"].get("snapshot_as_of")
            for source in sources:
                source["generated_at"] = generated_at
        targets[endpoint] = [{"subject_key": subject["key"], "parameters": parameters}]
        entries.append({
            "endpoint": endpoint,
            "subject": subject,
            "parameters": parameters,
            "request": request,
            "execution_id": execution.get("_id"),
            "response": response,
            "response_sha256": CONNECTOR._archive_sha256(response),
            "source_manifest": sources,
        })

    manifest = {
        "schema_version": 1,
        "archive_version": CONNECTOR.FINAL_ARCHIVE_VERSION,
        "coverage_scope": "one_fixture_canary",
        "publication_ready": False,
        "coverage_gate": "Full manifest publication requires independently complete coverage for every declared endpoint target.",
        "canonical_event_count": 104,
        "fixture_urns": [CANARY_EVENT_URN],
        "recap_fixture_urns": [CANARY_EVENT_URN],
        "fixture_player_targets": [{"event_urn": CANARY_EVENT_URN, "player_urn": player_urn, "subject_key": f"{CANARY_EVENT_URN}|{player_urn}"}],
        "spotlight_targets": [player_urn],
        "targets": targets,
        "entries": entries,
        "expected_archive_count": 11,
    }
    prepare_manifest(manifest)
    return manifest


def extract_mcp_document_rows(payload: Any) -> tuple[list[dict[str, Any]], int | None]:
    """Extract `data.data` rows from the observed MCP content-text envelope."""
    if not isinstance(payload, dict):
        raise ArchivePreparationError("MCP export must be an object")
    content = payload.get("content")
    if not isinstance(content, list) or not content or not isinstance(content[0], dict):
        raise ArchivePreparationError("MCP export is missing content[0]")
    text = content[0].get("text")
    if not isinstance(text, str):
        raise ArchivePreparationError("MCP export content[0].text must be JSON text")
    decoded = json.loads(text)
    data = decoded.get("data") if isinstance(decoded, dict) else None
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get("value"), dict) for row in rows):
        raise ArchivePreparationError("MCP export must contain data.data rows with value payloads")
    total = data.get("total_documents")
    if total is not None and (not isinstance(total, int) or total < len(rows)):
        raise ArchivePreparationError("MCP export total_documents is invalid")
    return rows, total


def _identity(endpoint: str, subject_key: str, parameters: dict[str, Any], archive_version: str) -> str:
    return CONNECTOR._archive_sha256({
        "archive_version": archive_version,
        "endpoint": endpoint,
        "subject_key": subject_key,
        "parameters": parameters,
    })


def _target_set(manifest: dict[str, Any]) -> set[tuple[str, str, str]]:
    targets = manifest.get("targets")
    if not isinstance(targets, dict) or set(targets) != CONNECTOR.FINAL_ARCHIVE_ENDPOINTS:
        missing = sorted(CONNECTOR.FINAL_ARCHIVE_ENDPOINTS - set(targets or {}))
        extra = sorted(set(targets or {}) - CONNECTOR.FINAL_ARCHIVE_ENDPOINTS)
        raise ArchivePreparationError(f"targets must enumerate all 11 endpoints; missing={missing}, extra={extra}")
    result: set[tuple[str, str, str]] = set()
    for endpoint, rows in targets.items():
        if not isinstance(rows, list) or not rows:
            raise ArchivePreparationError(f"targets.{endpoint} must be a non-empty list")
        for row in rows:
            if not isinstance(row, dict) or not str(row.get("subject_key") or "").strip():
                raise ArchivePreparationError(f"targets.{endpoint} contains an invalid subject")
            parameters = row.get("parameters", {})
            if not isinstance(parameters, dict):
                raise ArchivePreparationError(f"targets.{endpoint} parameters must be an object")
            key = (
                endpoint,
                str(row["subject_key"]),
                _identity(endpoint, str(row["subject_key"]), parameters, str(manifest.get("archive_version") or "")),
            )
            if key in result:
                raise ArchivePreparationError(f"duplicate target identity: {endpoint}/{row['subject_key']}")
            result.add(key)
    return result


def _validate_enumerations(manifest: dict[str, Any], targets: set[tuple[str, str, str]]) -> None:
    fixture_urns = manifest.get("fixture_urns")
    recap_urns = manifest.get("recap_fixture_urns")
    stats = manifest.get("fixture_player_targets")
    spotlights = manifest.get("spotlight_targets")
    if not isinstance(fixture_urns, list) or not fixture_urns:
        raise ArchivePreparationError("fixture_urns must be the non-empty source fixture manifest")
    if len(set(fixture_urns)) != len(fixture_urns):
        raise ArchivePreparationError("fixture_urns contains duplicates")
    if not isinstance(recap_urns, list) or len(set(recap_urns)) != len(recap_urns):
        raise ArchivePreparationError("recap_fixture_urns must be a deduplicated list")
    if not set(recap_urns) <= set(fixture_urns):
        raise ArchivePreparationError("recap_fixture_urns contains an id outside fixture_urns")
    if not isinstance(stats, list):
        raise ArchivePreparationError("fixture_player_targets must be a list")
    for row in stats:
        if not isinstance(row, dict) or not row.get("event_urn") or not row.get("player_urn") or not row.get("subject_key"):
            raise ArchivePreparationError("each fixture_player_targets row needs event_urn, player_urn, and subject_key")
        if row["event_urn"] not in fixture_urns:
            raise ArchivePreparationError(f"stats target references unknown fixture: {row['event_urn']}")
    if not isinstance(spotlights, list) or len(set(spotlights)) != len(spotlights):
        raise ArchivePreparationError("spotlight_targets must be a finite deduplicated list")

    target_subjects: dict[str, set[str]] = {}
    for endpoint, subject, _ in targets:
        target_subjects.setdefault(endpoint, set()).add(subject)
    for endpoint in ("worldcup-get-event-context", "worldcup-get-injuries", "worldcup-get-squads", "worldcup-get-match-forecast"):
        if target_subjects.get(endpoint) != set(fixture_urns):
            raise ArchivePreparationError(f"{endpoint} targets must exactly match fixture_urns")
    if target_subjects.get("worldcup-match-recap") != set(recap_urns):
        raise ArchivePreparationError("match recap targets must exactly match recap_fixture_urns")
    if target_subjects.get("worldcup-player-spotlight") != set(spotlights):
        raise ArchivePreparationError("spotlight targets must exactly match spotlight_targets")
    expected_performance_subjects = (
        set(fixture_urns)
        if manifest.get("fixture_player_packs") is True
        else {row["subject_key"] for row in stats}
    )
    if target_subjects.get("worldcup-get-player-performance-context") != expected_performance_subjects:
        raise ArchivePreparationError("player-performance targets must exactly match the declared fixture/player layout")


def prepare_manifest(manifest: dict[str, Any], *, invalidated: bool = False) -> list[dict[str, Any]]:
    archive_version = str(manifest.get("archive_version") or "")
    if manifest.get("schema_version") not in {1, 2}:
        raise ArchivePreparationError("schema_version must be 1 or 2")
    if archive_version not in CONNECTOR.SUPPORTED_FINAL_ARCHIVE_VERSIONS:
        raise ArchivePreparationError(
            "archive_version must be one of " + ", ".join(sorted(CONNECTOR.SUPPORTED_FINAL_ARCHIVE_VERSIONS))
        )
    if archive_version == CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION and manifest.get("schema_version") != 2:
        raise ArchivePreparationError("the next archive version requires schema_version 2")
    targets = _target_set(manifest)
    _validate_enumerations(manifest, targets)
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        raise ArchivePreparationError("entries must be a list")

    documents: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ArchivePreparationError("every entry must be an object")
        endpoint = str(entry.get("endpoint") or "")
        subject = entry.get("subject") if isinstance(entry.get("subject"), dict) else {}
        subject_key = str(subject.get("key") or "")
        parameters = entry.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ArchivePreparationError(f"parameters must be an object for {endpoint}/{subject_key}")
        key = (endpoint, subject_key, _identity(endpoint, subject_key, parameters, archive_version))
        if key in seen:
            raise ArchivePreparationError(f"duplicate entry identity: {endpoint}/{subject_key}")
        seen.add(key)
        if key not in targets:
            raise ArchivePreparationError(f"entry is not declared by targets: {endpoint}/{subject_key}")
        source_manifest = entry.get("source_manifest")
        if not isinstance(source_manifest, list) or not source_manifest:
            raise ArchivePreparationError(f"missing source_manifest for {endpoint}/{subject_key}")
        stored_sources = []
        for source in source_manifest:
            if not isinstance(source, dict) or not source.get("document_name") or "source_payload" not in source:
                raise ArchivePreparationError(f"source manifest rows need document_name and source_payload: {endpoint}/{subject_key}")
            actual_source_hash = CONNECTOR._archive_sha256(source["source_payload"])
            if source.get("source_sha256") != actual_source_hash:
                raise ArchivePreparationError(f"source payload hash mismatch: {endpoint}/{subject_key}")
            if endpoint in {"worldcup-get-squads", "worldcup-get-injuries"}:
                scope = str(source.get("temporal_scope") or "")
                if scope not in {
                    "world-cup-2026", "historical-fixture", "tournament-archive",
                    "final-published-tournament-roster-snapshot",
                }:
                    raise ArchivePreparationError(f"unverified squad/injury temporal scope: {endpoint}/{subject_key}")
            stored_sources.append({key: value for key, value in source.items() if key != "source_payload"})
        archive = entry.get("response", {}).get("archive", {}) if isinstance(entry.get("response"), dict) else {}
        represented_sources = {
            str(source.get("source") or source.get("document_name") or "") for source in stored_sources
        }
        unproven = [source for source in archive.get("provenance", []) if source not in represented_sources]
        if unproven:
            raise ArchivePreparationError(f"unproven response provenance for {endpoint}/{subject_key}: {unproven}")
        source_payloads = {
            source["document_name"]: (
                source["source_payload"].get("value")
                if isinstance(source["source_payload"], dict) and isinstance(source["source_payload"].get("value"), dict)
                else source["source_payload"]
            )
            for source in source_manifest
        }
        response = entry.get("response")
        if entry.get("response_sha256") not in (None, CONNECTOR._archive_sha256(response)):
            raise ArchivePreparationError(f"captured response hash mismatch: {endpoint}/{subject_key}")
        if endpoint == "worldcup-get-match-forecast" and response.get("forecast"):
            if source_payloads.get("worldcup:model-forecast") != response["forecast"]:
                raise ArchivePreparationError("forecast response differs from the original model-forecast source")
        if endpoint == "worldcup-backtest-forecasts" and response.get("track_record"):
            audit_source = source_payloads.get("worldcup:forecast-audit")
            if not isinstance(audit_source, dict) or audit_source.get("backtesting_report") != response["track_record"]:
                raise ArchivePreparationError("backtest response differs from the precomputed forecast-audit source")
        if endpoint in {"worldcup-match-recap", "worldcup-player-spotlight"} and response.get("skill_card"):
            if endpoint == "worldcup-match-recap":
                recap_sources = [
                    "capture:worldcup-match-recap",
                    "worldcup:skill-match-recap-original-copy",
                    "worldcup:skill-match-recap-source-only",
                    "worldcup:skill-match-recap-corrected",
                    "worldcup:skill-match-recap",
                ]
                source_name = next((name for name in recap_sources if name in source_payloads), "")
            else:
                spotlight_sources = [
                    "worldcup:skill-player-spotlight",
                    "worldcup:storefront-derived-player-card",
                ]
                source_name = next((name for name in spotlight_sources if name in source_payloads), "")
            editorial_source = source_payloads.get(source_name)
            if not isinstance(editorial_source, dict) or not isinstance(editorial_source.get("body"), dict):
                raise ArchivePreparationError(f"{endpoint} requires its original editorial source payload")
            for key, value in editorial_source["body"].items():
                if response["skill_card"].get(key) != value:
                    raise ArchivePreparationError(f"{endpoint} response differs from its original editorial body")
        value = CONNECTOR.build_final_archive_document(
            endpoint,
            subject,
            parameters,
            response,
            stored_sources,
            invalidated=invalidated,
            archive_version=archive_version,
        )
        documents.append({"name": CONNECTOR.FINAL_ARCHIVE_DOCUMENT, "value": value})

    if seen != targets:
        missing = sorted((endpoint, subject) for endpoint, subject, digest in targets if (endpoint, subject, digest) not in seen)
        raise ArchivePreparationError(f"manifest entries do not exactly cover targets; missing={missing[:20]}")
    expected_count = manifest.get("expected_archive_count")
    if expected_count != len(documents):
        raise ArchivePreparationError(f"expected_archive_count={expected_count!r}, prepared={len(documents)}")
    documents.sort(key=lambda item: item["value"]["_id"])
    return documents


def verify_bundle(
    bundle: dict[str, Any],
    manifest: dict[str, Any] | None = None,
    expected_document_ids: set[str] | None = None,
) -> dict[str, Any]:
    is_mcp_export = isinstance(bundle, dict) and "content" in bundle
    if is_mcp_export:
        rows, total_documents = extract_mcp_document_rows(bundle)
        declared_count = len(rows)
        declared_unique = len(rows)
    else:
        rows = bundle.get("documents") if isinstance(bundle, dict) else None
        total_documents = bundle.get("total_count") if isinstance(bundle, dict) else None
        declared_count = bundle.get("count") if isinstance(bundle, dict) else None
        declared_unique = bundle.get("unique_identity_count") if isinstance(bundle, dict) else None
    if not isinstance(rows, list):
        raise ArchivePreparationError("bundle.documents must be a list")
    identities: set[str] = set()
    for document in rows:
        value = document.get("value") if isinstance(document, dict) and isinstance(document.get("value"), dict) else {}
        endpoint = str(value.get("endpoint") or "")
        subject = value.get("subject") if isinstance(value.get("subject"), dict) else {}
        parameters = value.get("parameter_identity") if isinstance(value.get("parameter_identity"), dict) else {}
        rebuilt = CONNECTOR.build_final_archive_document(
            endpoint,
            subject,
            parameters,
            value.get("response"),
            value.get("source_manifest"),
            invalidated=value.get("invalidated") is True,
            archive_version=str(value.get("archive_version") or ""),
        )
        if value != rebuilt:
            raise ArchivePreparationError(f"readback hash/schema mismatch for {value.get('_id')}")
        identity = value["parameter_identity_sha256"]
        if identity in identities:
            raise ArchivePreparationError(f"duplicate readback identity: {identity}")
        identities.add(identity)
    if declared_count != len(rows) or declared_unique != len(identities):
        raise ArchivePreparationError("bundle count/dedupe guard failed")
    actual_ids = {row["value"]["_id"] for row in rows}
    if expected_document_ids is not None and actual_ids != expected_document_ids:
        raise ArchivePreparationError("readback rows do not exactly match the pending batch")
    if is_mcp_export and total_documents != len(rows):
        raise ArchivePreparationError("MCP readback is paginated or has an inexact document count")
    if manifest is not None:
        all_rows = prepare_manifest(manifest, invalidated=bool(rows and rows[0]["value"].get("invalidated")))
        expected_by_id = {row["value"]["_id"]: row["value"] for row in all_rows}
        expected_ids = set(expected_by_id)
        if not actual_ids <= expected_ids:
            raise ArchivePreparationError("bundle contains identities outside the source manifest")
        for row in rows:
            value = row["value"]
            if value != expected_by_id[value["_id"]]:
                raise ArchivePreparationError(f"readback differs from source manifest: {value['_id']}")
        if expected_document_ids is None:
            if is_mcp_export and actual_ids != expected_ids:
                raise ArchivePreparationError("full readback does not exactly cover the source manifest")
            if not is_mcp_export:
                offset = bundle.get("offset")
                count = bundle.get("count")
                if not isinstance(offset, int) or not isinstance(count, int) or bundle.get("total_count") != len(all_rows):
                    raise ArchivePreparationError("prepared bundle pagination metadata is invalid")
                expected_page_ids = {row["value"]["_id"] for row in all_rows[offset:offset + count]}
                if actual_ids != expected_page_ids:
                    raise ArchivePreparationError("prepared bundle does not exactly match its manifest page")
        if total_documents is not None and total_documents < len(rows):
            raise ArchivePreparationError("readback total_documents is smaller than returned rows")
    return {"verified": True, "count": len(rows), "unique_identity_count": len(identities)}


def _state(path: Path | None) -> dict[str, Any]:
    return _read_json(path) if path and path.exists() else {}


def _prepare(args: argparse.Namespace) -> int:
    manifest = _read_json(args.manifest)
    documents = prepare_manifest(manifest, invalidated=args.invalidate)
    manifest_hash = CONNECTOR._archive_sha256(manifest)
    state = _state(args.resume_state)
    if state and state.get("manifest_sha256") != manifest_hash:
        raise ArchivePreparationError("resume manifest hash changed")
    pending = state.get("pending") if isinstance(state.get("pending"), dict) else {}
    offset = args.offset if args.offset is not None else int(pending.get("offset", state.get("next_offset", 0)))
    if offset < 0 or offset > len(documents):
        raise ArchivePreparationError("offset is outside the prepared archive")
    batch_size = args.batch_size
    if batch_size < 1 or batch_size > 100:
        raise ArchivePreparationError("batch_size must be between 1 and 100")
    if args.write:
        if args.canary == args.fanout:
            raise ArchivePreparationError("choose exactly one of --canary or --fanout when writing")
        if args.canary and (offset != 0 or batch_size != 1):
            raise ArchivePreparationError("canary requires offset 0 and batch_size 1")
        if args.fanout and not state.get("canary_verified"):
            raise ArchivePreparationError("fanout requires a verified canary resume state")
        if args.fanout and manifest.get("publication_ready") is not True:
            raise ArchivePreparationError("fanout requires a separately completed full-publication coverage gate")

    selected = documents[offset:offset + batch_size]
    bundle = {
        "archive_version": str(manifest.get("archive_version") or ""),
        "manifest_sha256": manifest_hash,
        "offset": offset,
        "next_offset": offset + len(selected),
        "total_count": len(documents),
        "count": len(selected),
        "unique_identity_count": len({row["value"]["parameter_identity_sha256"] for row in selected}),
        "invalidated": args.invalidate,
        "documents": selected,
    }
    verify_bundle(bundle, manifest)
    summary = {key: bundle[key] for key in ("archive_version", "offset", "next_offset", "total_count", "count", "unique_identity_count", "invalidated")}
    summary["dry_run"] = not args.write
    print(json.dumps(summary, sort_keys=True))
    if not args.write:
        return 0
    if args.output is None or args.resume_state is None:
        raise ArchivePreparationError("--write requires --output and --resume-state")
    selected_ids = [row["value"]["_id"] for row in selected]
    if pending and pending.get("document_ids") != selected_ids:
        raise ArchivePreparationError("pending batch differs from the idempotent retry")
    _write_json(args.output, bundle)
    _write_json(args.resume_state, {
        "archive_version": str(manifest.get("archive_version") or ""),
        "manifest_sha256": manifest_hash,
        "next_offset": int(state.get("next_offset", 0)),
        "emitted_response_sha256": list(state.get("emitted_response_sha256", [])),
        "canary_verified": bool(state.get("canary_verified", False)),
        "pending": {
            "offset": offset,
            "next_offset": bundle["next_offset"],
            "document_ids": selected_ids,
            "response_sha256": [row["value"]["response_sha256"] for row in selected],
            "canary": bool(args.canary),
        },
    })
    return 0


def _capture(args: argparse.Namespace) -> int:
    manifest = capture_canary_manifest(args.executions, args.exports)
    documents = prepare_manifest(manifest)
    bundle = {
        "archive_version": str(manifest.get("archive_version") or CONNECTOR.FINAL_ARCHIVE_VERSION),
        "coverage_scope": manifest["coverage_scope"],
        "publication_ready": False,
        "manifest_sha256": CONNECTOR._archive_sha256(manifest),
        "offset": 0,
        "next_offset": len(documents),
        "total_count": len(documents),
        "count": len(documents),
        "unique_identity_count": len({row["value"]["parameter_identity_sha256"] for row in documents}),
        "invalidated": False,
        "documents": documents,
    }
    verify_bundle(bundle, manifest)
    summary = {
        "archive_version": CONNECTOR.FINAL_ARCHIVE_VERSION,
        "coverage_scope": manifest["coverage_scope"],
        "canonical_event_count": manifest["canonical_event_count"],
        "count": len(documents),
        "manifest_sha256": bundle["manifest_sha256"],
        "publication_ready": False,
        "dry_run": not args.write,
    }
    print(json.dumps(summary, sort_keys=True))
    if args.write:
        if args.manifest_output is None or args.output is None:
            raise ArchivePreparationError("capture --write requires --manifest-output and --output")
        _write_json(args.manifest_output, manifest)
        _write_json(args.output, bundle)
    return 0


def _verify(args: argparse.Namespace) -> int:
    bundle = _read_json(args.bundle)
    manifest = _read_json(args.manifest) if args.manifest else None
    state = _state(args.resume_state)
    pending = state.get("pending") if isinstance(state.get("pending"), dict) else {}
    expected_ids = set(pending.get("document_ids", [])) if pending else None
    result = verify_bundle(bundle, manifest, expected_ids)
    if args.resume_state:
        if state.get("manifest_sha256") != bundle.get("manifest_sha256"):
            if not (isinstance(bundle, dict) and "content" in bundle and pending):
                raise ArchivePreparationError("verified bundle does not match resume state")
        if not pending:
            raise ArchivePreparationError("resume state has no pending batch to verify")
        emitted = list(state.get("emitted_response_sha256", [])) + list(pending.get("response_sha256", []))
        state["next_offset"] = pending["next_offset"]
        state["emitted_response_sha256"] = sorted(set(emitted))
        state["canary_verified"] = bool(state.get("canary_verified") or pending.get("canary"))
        state.pop("pending", None)
        _write_json(args.resume_state, state)
    print(json.dumps(result, sort_keys=True))
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    capture = commands.add_parser("capture", help="capture a one-fixture 11-endpoint bundle from offline exports")
    capture.add_argument("--executions", type=Path, required=True)
    capture.add_argument("--exports", type=Path, required=True)
    capture.add_argument("--manifest-output", type=Path)
    capture.add_argument("--output", type=Path)
    capture.add_argument("--write", action="store_true", help="write manifest and bundle; default is dry-run")
    capture.set_defaults(handler=_capture)
    prepare = commands.add_parser("prepare", help="validate and prepare a bounded import bundle")
    prepare.add_argument("--manifest", type=Path, required=True)
    prepare.add_argument("--offset", type=int)
    prepare.add_argument("--batch-size", type=int, default=1)
    prepare.add_argument("--output", type=Path)
    prepare.add_argument("--resume-state", type=Path)
    prepare.add_argument("--write", action="store_true", help="write bundle/state; default is dry-run")
    prepare.add_argument("--canary", action="store_true")
    prepare.add_argument("--fanout", action="store_true")
    prepare.add_argument("--invalidate", action="store_true", help="prepare explicit invalidation rows")
    prepare.set_defaults(handler=_prepare)
    verify = commands.add_parser("verify", help="verify a prepared or read-back import bundle")
    verify.add_argument("--bundle", type=Path, required=True)
    verify.add_argument("--manifest", type=Path)
    verify.add_argument("--resume-state", type=Path)
    verify.set_defaults(handler=_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except (ArchivePreparationError, OSError, json.JSONDecodeError) as exc:
        print(f"archive preparation failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
