#!/usr/bin/env python3
"""Build and verify the offline World Cup storefront v3 candidate from v2."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


CONNECTOR = _module("worldcup_storefront_connector", ROOT / "worldcup-market-intelligence.py")
ARCHIVE = _module("worldcup_storefront_archive", ROOT / "tools" / "worldcup_archive.py")
FIFA = _module("worldcup_fifa_reconciliation", ROOT / "tools" / "worldcup_fifa_reconciliation.py")


def _read(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_file(path_value: Any) -> Path | None:
    if not isinstance(path_value, str) or not path_value:
        return None
    path = Path(path_value)
    path = path if path.is_absolute() else REPO / path
    resolved = path.resolve()
    try:
        resolved.relative_to(REPO.resolve())
    except ValueError as exc:
        raise ARCHIVE.ArchivePreparationError(f"source file escapes repository: {path_value}") from exc
    return resolved


def _verified_source_hashes(
    manifest: dict[str, Any], manifest_path: Path, extra_paths: list[Path] | None = None,
) -> dict[str, str]:
    hashes = {str(manifest_path.relative_to(REPO)): _sha_file(manifest_path)}
    for extra_path in extra_paths or []:
        resolved = extra_path.resolve()
        try:
            relative = resolved.relative_to(REPO.resolve())
        except ValueError as exc:
            raise ARCHIVE.ArchivePreparationError(f"source file escapes repository: {extra_path}") from exc
        if not resolved.is_file():
            raise ARCHIVE.ArchivePreparationError(f"required evidence file is missing: {resolved}")
        hashes[str(relative)] = _sha_file(resolved)
    for entry in manifest.get("entries", []):
        for source in entry.get("source_manifest", []):
            path = _source_file(source.get("source_file"))
            if path is None:
                continue
            if not path.is_file():
                raise ARCHIVE.ArchivePreparationError(f"referenced source file is missing: {path}")
            digest = hashes.setdefault(str(path.relative_to(REPO)), _sha_file(path))
            declared = source.get("source_file_sha256")
            if declared and declared != digest:
                raise ARCHIVE.ArchivePreparationError(f"referenced source file hash mismatch: {path}")
    return dict(sorted(hashes.items()))


def _iso(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _find_timestamps(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    candidates = [
        ((value.get("workflow_output") or {}).get("audit") or {}).get("finished_time"),
        (value.get("_capture_meta") or {}).get("captured_at"),
        value.get("observed_at"),
        value.get("captured_at"),
        value.get("date"),
    ]
    return [normalized for item in candidates if (normalized := _iso(item))]


def _observed_at(entry: dict[str, Any], cache: dict[Path, list[str]]) -> str | None:
    values: list[str] = []
    for source in entry.get("source_manifest", []):
        values.extend(_find_timestamps(source))
        path = _source_file(source.get("source_file"))
        if path is None or not path.is_file():
            continue
        relative = str(path.relative_to(REPO))
        if "/captures/" not in relative and "/executions/" not in relative and path.name != "provider-results-compact.json":
            continue
        if path not in cache:
            try:
                cache[path] = _find_timestamps(_read(path))
            except (OSError, json.JSONDecodeError):
                cache[path] = []
        values.extend(cache[path])
    return max(values) if values else None


def _coverage(
    status: str,
    reason: str,
    provenance: list[str],
    *,
    population: int | None,
    eligible: int | None = None,
    included: int | None = None,
    excluded: int | None = None,
    exclusion_reasons: dict[str, int] | None = None,
    unsupported: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "worldcup-storefront-coverage-v1",
        "status": status,
        "reason": reason,
        "scope": "completed_tournament_archive",
        "mode": "historical",
        "source_provenance": list(dict.fromkeys(provenance)),
        "population_count": population,
        "eligible_count": population if eligible is None else eligible,
        "included_count": population if included is None else included,
        "excluded_count": (0 if population is not None else None) if excluded is None else excluded,
        "exclusion_reasons": dict(sorted((exclusion_reasons or {}).items())),
        "unsupported_fields": sorted(unsupported or []),
    }


def _derived_source(name: str, payload: Any, source_path: Path, source_hash: str, **extra: Any) -> dict[str, Any]:
    return {
        "document_name": name,
        "source": name,
        "source_file": str(source_path.relative_to(REPO)),
        "source_file_sha256": source_hash,
        "source_payload": payload,
        "source_sha256": CONNECTOR._archive_sha256(payload),
        **extra,
    }


def _evidence_source(name: str, payload: Any, source_path: Path, *, public_url: str, **extra: Any) -> dict[str, Any]:
    return {
        "document_name": name,
        "source": name,
        "source_url": public_url,
        "source_file": str(source_path.relative_to(REPO)),
        "source_file_sha256": _sha_file(source_path),
        "source_payload": payload,
        "source_sha256": CONNECTOR._archive_sha256(payload),
        **extra,
    }


def _sanitize_public_value(value: Any) -> Any:
    """Remove local implementation paths while retaining useful public provenance."""
    if isinstance(value, list):
        return [_sanitize_public_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _sanitize_public_value(item)
        for key, item in value.items()
        if key not in {"capture_file", "source_file"}
        and not (isinstance(item, str) and item.startswith(".local/"))
    }


def _qualify_public_provenance(value: Any, observed_at: str | None) -> Any:
    if isinstance(value, list):
        return [_qualify_public_provenance(item, observed_at) for item in value]
    if not isinstance(value, dict):
        return value
    qualified = {key: _qualify_public_provenance(item, observed_at) for key, item in value.items()}
    if qualified.get("provider") == "api-football" and qualified.get("fixture_id"):
        qualified.setdefault("source_url", "https://www.api-football.com/")
        qualified.setdefault("observed_at", observed_at)
    return qualified


def _source_payload(entry: dict[str, Any], document_name: str) -> Any:
    for source in entry.get("source_manifest", []):
        if source.get("document_name") == document_name:
            return source.get("source_payload")
    raise ARCHIVE.ArchivePreparationError(f"missing {document_name} source payload")


def _raw_player_stats(path: Path, fixture_id: str, event_urn: str) -> dict[str, Any]:
    execution = _read(path)
    outputs = ((execution.get("workflow_output") or {}).get("outputs") or {})
    if str(outputs.get("event_urn") or "") != event_urn:
        raise ARCHIVE.ArchivePreparationError(f"raw player capture event mismatch: {path}")
    stats = outputs.get("player_stats") if isinstance(outputs.get("player_stats"), dict) else {}
    required = {"errors", "get", "paging", "parameters", "response", "results"}
    if not required <= set(stats) or stats.get("errors"):
        raise ARCHIVE.ArchivePreparationError(f"raw player capture is incomplete: {path}")
    paging = stats.get("paging") if isinstance(stats.get("paging"), dict) else {}
    if paging.get("current") != 1 or paging.get("total") != 1:
        raise ARCHIVE.ArchivePreparationError(f"raw player capture pagination is incomplete: {path}")
    if str((stats.get("parameters") or {}).get("fixture") or "") != fixture_id:
        raise ARCHIVE.ArchivePreparationError(f"raw player capture fixture mismatch: {path}")
    teams = stats.get("response")
    if not isinstance(teams, list) or stats.get("results") != len(teams):
        raise ARCHIVE.ArchivePreparationError(f"raw player capture result count mismatch: {path}")
    return stats


def _set_timestamp_semantics(entry: dict[str, Any], file_cache: dict[Path, Any]) -> None:
    endpoint = entry["endpoint"]
    response = entry["response"]
    archive = response["archive"]
    prior = archive.get("snapshot_as_of")
    if endpoint == "worldcup-get-match-forecast":
        archive["timestamp_semantics"] = "original_model_computation"
        archive["source_observed_at"] = None
        archive["content_created_at"] = None
        return
    if endpoint in {"worldcup-match-recap", "worldcup-player-spotlight"}:
        card = response.get("skill_card") if isinstance(response.get("skill_card"), dict) else {}
        original = (
            endpoint == "worldcup-player-spotlight" and archive.get("capability_status") == "archived_editorial"
        ) or (
            endpoint == "worldcup-match-recap" and card.get("generation_method") != "deterministic_source_only"
        )
        archive["snapshot_as_of"] = prior if original else None
        archive["timestamp_semantics"] = "original_editorial_generation" if original else "derived_content_creation_not_source_freshness"
        archive["source_observed_at"] = None
        archive["content_created_at"] = prior
        return
    observed = _observed_at(entry, file_cache)
    archive["snapshot_as_of"] = observed
    archive["timestamp_semantics"] = "source_capture_observation" if observed else "unavailable"
    archive["source_observed_at"] = observed
    archive["content_created_at"] = prior if prior and prior != observed else None


def _entry_map(manifest: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    result = {endpoint: [] for endpoint in CONNECTOR.FINAL_ARCHIVE_ENDPOINTS}
    for entry in manifest.get("entries", []):
        endpoint = entry.get("endpoint")
        if endpoint not in result:
            raise ARCHIVE.ArchivePreparationError(f"unsupported v2 endpoint: {endpoint}")
        result[endpoint].append(entry)
    return result


def _team_name(row: dict[str, Any]) -> str:
    team = row.get("team") if isinstance(row.get("team"), dict) else {}
    return str(row.get("team_name") or team.get("name") or row.get("name") or "")


def _standings_by_team(standings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for group in standings.get("groups", []):
        if not isinstance(group, dict):
            continue
        for row in group.get("table", []):
            if isinstance(row, dict) and _team_name(row):
                result[CONNECTOR._canonical_team_slug(_team_name(row))] = {
                    "group": group.get("group") or group.get("name"),
                    "row": row,
                }
    return result


def _team_urns(entries: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    result = {}
    for entry in entries["worldcup-get-event-context"]:
        event = entry["subject"].get("event") or {}
        for team in event.get("sport:competitors", []):
            if isinstance(team, dict) and team.get("name") and team.get("@id"):
                result[FIFA._team_key(team["name"])] = str(team["@id"])
    return result


def _existing_identity_source(entries: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    first = entries["worldcup-get-player-performance-context"][0]
    identities = _source_payload(first, "worldcup:identity-crosswalk")
    if not isinstance(identities, list):
        raise ARCHIVE.ArchivePreparationError("identity-crosswalk source payload must be a list")
    return identities


def _reconciliation_source(
    payload: Any,
    evidence: dict[str, Path],
    *,
    fixture_id: str | None = None,
) -> dict[str, Any]:
    return _evidence_source(
        "worldcup:identity-reconciliation",
        payload,
        evidence["provider_evidence"],
        public_url=FIFA.FIFA_SOURCE_URL,
        temporal_scope="tournament-archive",
        fixture_id=fixture_id,
        fifa_pdf_sha256=FIFA.FIFA_SOURCE_SHA256,
        fifa_snapshot_file_sha256=_sha_file(evidence["snapshot"]),
    )


def _registration_source(payload: Any, evidence: dict[str, Path], *, fixture_id: str | None = None) -> dict[str, Any]:
    return _evidence_source(
        "fifa.com:official-registration",
        payload,
        evidence["pdf"],
        public_url=FIFA.FIFA_SOURCE_URL,
        temporal_scope="final-published-tournament-roster-snapshot",
        fixture_id=fixture_id,
        published_at=FIFA.FIFA_DOCUMENT_GENERATED_AT,
    )


def _replace_player_resolve_rows(
    manifest: dict[str, Any],
    entries: dict[str, list[dict[str, Any]]],
    reconciliation: dict[str, Any],
    evidence: dict[str, Path],
) -> int:
    identities = {row["_id"]: row for row in reconciliation["identities"]}
    existing_keys = set()
    for entry in entries["worldcup-resolve"]:
        key = entry["subject"]["key"]
        existing_keys.add(key)
        if key == FIFA.QUARANTINED_MARIO_URN:
            original = copy.deepcopy(entry["subject"].get("entity") or {})
            quarantined = copy.deepcopy(original)
            quarantined["provider_ids"] = {}
            quarantined["identity_mapping_status"] = "quarantined"
            quarantined["identity_status"] = "invalid"
            quarantined["quarantined_provider_ids"] = dict(original.get("provider_ids") or {})
            quarantined["quarantine_reason"] = "Corrupt Mario/Marco identity collision; this identifier must not resolve to either player."
            candidates = [identities[FIFA.MARCO_URN], identities["urn:machina:sport:soccer:player:mario-pasalic:19950209:hrv"]]
            entry["subject"] = {"key": key, "entity": quarantined, "aliases": []}
            entry["response"] = {
                "entity": quarantined,
                "entities": [],
                "count": 0,
                "identity_status": "quarantined",
                "replacement_candidates": candidates,
                "candidates": candidates,
                "warnings": [quarantined["quarantine_reason"]],
                "archive": {
                    "mode": "final_archive", "competition": "FIFA World Cup 2026",
                    "competition_status": "completed", "live": False, "snapshot_as_of": None,
                    "capability_status": "invalid_identity",
                    "provenance": ["worldcup:identity-crosswalk", "worldcup:identity-reconciliation", "fifa.com:official-registration"],
                    "missing_capabilities": ["valid_canonical_identity"],
                    "notes": ["The immutable v2 evidence is preserved; v3 quarantines this corrupt mapping explicitly."],
                },
                "coverage": _coverage(
                    "unavailable", quarantined["quarantine_reason"],
                    ["worldcup:identity-crosswalk", "worldcup:identity-reconciliation", "fifa.com:official-registration"],
                    population=1, eligible=0, included=0, excluded=1,
                    exclusion_reasons={"quarantined_identity": 1}, unsupported=["valid_canonical_identity"],
                ),
            }
            entry["source_manifest"].extend([
                _reconciliation_source(reconciliation["ledger"], evidence),
                _registration_source({"players": [row["official_registration"] for row in candidates]}, evidence),
            ])
            entry["response_sha256"] = CONNECTOR._archive_sha256(entry["response"])
            continue
        if key not in identities:
            continue
        identity = copy.deepcopy(identities[key])
        entry["subject"]["entity"] = identity
        entry["subject"]["aliases"] = sorted(set(entry["subject"].get("aliases") or []) | {
            str(value) for value in (identity.get("provider_ids") or {}).values() if value
        } | {
            str(value) for values in (identity.get("provider_id_aliases") or {}).values() for value in values
        })
        response = entry["response"]
        response.update({"entity": identity, "entities": [identity], "count": 1})
        response["archive"]["provenance"] = list(dict.fromkeys(
            list(response["archive"].get("provenance") or [])
            + ["worldcup:identity-reconciliation", "fifa.com:official-registration"]
        ))
        response["archive"]["notes"] = list(response["archive"].get("notes") or []) + [
            "Official registration metadata is source-scoped; the stable canonical identifier is retained."
        ]
        entry["source_manifest"].extend([
            _reconciliation_source({"canonical_urn": key}, evidence),
            _registration_source(identity["official_registration"], evidence),
        ])
        entry["response_sha256"] = CONNECTOR._archive_sha256(response)

    added = 0
    for key, identity in sorted(identities.items()):
        if key in existing_keys:
            continue
        aliases = [str(value) for value in (identity.get("provider_ids") or {}).values() if value]
        aliases.extend(
            str(value) for values in (identity.get("provider_id_aliases") or {}).values() for value in values
        )
        response = {
            "entity": identity, "entities": [identity], "count": 1, "warnings": [],
            "archive": {
                "mode": "final_archive", "competition": "FIFA World Cup 2026",
                "competition_status": "completed", "live": False, "snapshot_as_of": None,
                "capability_status": "complete",
                "provenance": ["worldcup:identity-reconciliation", "fifa.com:official-registration"],
                "missing_capabilities": [],
                "notes": ["Canonical player identity reconciled from provider observations and the official FIFA registration snapshot."],
            },
            "coverage": _coverage(
                "complete", "Provider identity and official registration agree on team, jersey, and name evidence.",
                ["worldcup:identity-reconciliation", "fifa.com:official-registration"], population=1,
            ),
        }
        entry = {
            "endpoint": "worldcup-resolve",
            "subject": {"key": key, "entity": identity, "player": identity, "aliases": sorted(set(aliases))},
            "parameters": {}, "response": response,
            "response_sha256": CONNECTOR._archive_sha256(response),
            "source_manifest": [
                _reconciliation_source({"canonical_urn": key, "provider_aliases": aliases}, evidence),
                _registration_source(identity["official_registration"], evidence),
            ],
        }
        entries["worldcup-resolve"].append(entry)
        manifest["targets"]["worldcup-resolve"].append({"subject_key": key, "parameters": {}})
        existing_keys.add(key)
        added += 1
    return added


def _rebuild_fixture_player_packs(
    entries: dict[str, list[dict[str, Any]]],
    reconciliation: dict[str, Any],
    rankings: list[dict[str, Any]],
    captures_dir: Path,
    evidence: dict[str, Path],
) -> dict[str, Any]:
    raw_total = 0
    archived_total = 0
    restored_marco_fixtures = []
    source_hashes = {}
    for entry in entries["worldcup-get-player-performance-context"]:
        event = entry["subject"]["event"]
        event_urn = entry["subject"]["event_urn"]
        fixture_id = str(entry["subject"]["provider_event_id"])
        capture_path = captures_dir / fixture_id / "worldcup-archive-capture-players.json"
        raw_stats = _raw_player_stats(capture_path, fixture_id, event_urn)
        pack = CONNECTOR.build_fixture_player_pack({"params": {
            "event": event,
            "player_stats": raw_stats,
            "identities": reconciliation["identities"],
            "rankings": rankings,
        }})["data"]["fixture_player_pack"]
        if pack["raw_player_count"] != pack["player_count"]:
            raise ARCHIVE.ArchivePreparationError(
                f"raw-to-archive participant omission for fixture {fixture_id}: {pack['raw_player_count']}/{pack['player_count']}"
            )
        person_keys = [row["player"].get("_id") for row in pack["players"]]
        if None in person_keys or len(person_keys) != len(set(person_keys)):
            raise ARCHIVE.ArchivePreparationError(f"fixture pack contains unresolved or duplicate people: {fixture_id}")
        raw_total += pack["raw_player_count"]
        archived_total += pack["player_count"]
        if any((row.get("provider_observation") or {}).get("player_id") == "260865" for row in pack["players"]):
            restored_marco_fixtures.append(fixture_id)
        response = entry["response"]
        response["fixture_player_pack"] = pack
        response["status"] = "complete"
        response["warnings"] = list(pack.get("warnings") or [])
        response["identity_coverage"] = {
            "canonical_count": pack["player_count"], "provider_only_count": 0,
            "ambiguous_omitted_count": 0, "raw_observation_count": pack["raw_player_count"],
            "retained_observation_count": pack["player_count"],
        }
        response["archive"]["capability_status"] = "complete"
        response["archive"]["missing_capabilities"] = []
        response["archive"]["provenance"] = list(dict.fromkeys(
            list(response["archive"].get("provenance") or [])
            + ["worldcup:identity-reconciliation", "fifa.com:official-registration"]
        ))
        response["coverage"] = _coverage(
            "complete", "Every raw provider player-fixture observation is retained with reconciled identity lineage.",
            response["archive"]["provenance"], population=pack["raw_player_count"],
        )
        for source in entry["source_manifest"]:
            if source.get("document_name") == "api-football":
                source.update({
                    "source_file": str(capture_path.relative_to(REPO)),
                    "source_file_sha256": _sha_file(capture_path),
                    "source_payload": raw_stats,
                    "source_sha256": CONNECTOR._archive_sha256(raw_stats),
                })
            elif source.get("document_name") == "fifa.com":
                source["source_payload"] = {
                    "fixture_player_pack": pack,
                    "final_ranking_export_sha256": source["source_payload"].get("final_ranking_export_sha256"),
                }
                source["source_sha256"] = CONNECTOR._archive_sha256(source["source_payload"])
        entry["source_manifest"].extend([
            _reconciliation_source({
                "fixture_id": fixture_id,
                "provider_observations": [row.get("provider_observation") for row in pack["players"]],
            }, evidence, fixture_id=fixture_id),
            _registration_source({
                "fixture_id": fixture_id,
                "registrations": [row["player"]["official_registration"] for row in pack["players"]],
            }, evidence, fixture_id=fixture_id),
        ])
        entry["response_sha256"] = CONNECTOR._archive_sha256(response)
        source_hashes[str(capture_path.relative_to(REPO))] = _sha_file(capture_path)
    if raw_total != 5323 or archived_total != 5323:
        raise ARCHIVE.ArchivePreparationError(f"unexpected raw corpus cardinality: {raw_total}/{archived_total}")
    if sorted(restored_marco_fixtures) != ["1489384", "1489403", "1489420", "1567309"]:
        raise ARCHIVE.ArchivePreparationError(f"Marco restoration mismatch: {restored_marco_fixtures}")
    return {
        "raw_player_fixture_observations": raw_total,
        "archived_player_fixture_observations": archived_total,
        "raw_capture_count": len(source_hashes),
        "raw_capture_sha256": dict(sorted(source_hashes.items())),
        "restored_marco_fixtures": sorted(restored_marco_fixtures),
    }


def _official_team_payload(
    team_name: str,
    official_snapshot: dict[str, Any],
    reconciliation: dict[str, Any],
) -> dict[str, Any]:
    team_key = FIFA._team_key(team_name)
    records = sorted(
        [row for row in official_snapshot["records"] if FIFA._team_key(row["team_name"]) == team_key],
        key=lambda row: row["jersey_number"],
    )
    if len(records) != 26:
        raise ARCHIVE.ArchivePreparationError(f"official registration missing for {team_name}")
    players = []
    for record in records:
        identity = reconciliation["registration_to_identity"][(team_key, record["jersey_number"])]
        players.append({
            **copy.deepcopy(record),
            "canonical_urn": identity["_id"],
            "provider_ids": dict(identity.get("provider_ids") or {}),
            "provider_id_aliases": dict(identity.get("provider_id_aliases") or {}),
            "canonical_birth_date": identity["official_registration"]["canonical_birth_date"],
            "canonical_birth_date_conflict": identity["official_registration"]["canonical_birth_date_conflict"],
            "identity_mapping_status": "official_reconciled",
        })
    return {
        "team_name": records[0]["team_name"], "fifa_team_code": records[0]["fifa_team_code"],
        "source_page": records[0]["source_page"], "player_count": 26, "players": players,
        "source": {
            "publisher": "FIFA", "url": FIFA.FIFA_SOURCE_URL,
            "sha256": FIFA.FIFA_SOURCE_SHA256, "published_at": FIFA.FIFA_DOCUMENT_GENERATED_AT,
            "page": records[0]["source_page"],
        },
        "completeness": {"status": "complete_for_published_snapshot", "expected_players": 26, "included_players": 26},
    }


def _add_official_squads(
    entries: dict[str, list[dict[str, Any]]],
    official_snapshot: dict[str, Any],
    reconciliation: dict[str, Any],
    evidence: dict[str, Path],
) -> None:
    for entry in entries["worldcup-get-squads"]:
        event = entry["subject"]["event"]
        fixture_id = str(entry["subject"]["provider_event_id"])
        team_names = [row["name"] for row in event.get("sport:competitors", []) if isinstance(row, dict)]
        official_teams = [_official_team_payload(name, official_snapshot, reconciliation) for name in team_names]
        squads = entry["response"]["squads"]
        squads.update({
            "official_registration_status": "verified_final_published_snapshot",
            "official_registration_snapshot": {
                "scope": "final_published_tournament_roster_snapshot",
                "published_at": FIFA.FIFA_DOCUMENT_GENERATED_AT,
                "source_url": FIFA.FIFA_SOURCE_URL,
                "source_sha256": FIFA.FIFA_SOURCE_SHA256,
                "snapshot_team_count": 48,
                "players_per_team": 26,
                "teams": official_teams,
                "completeness": {"status": "complete_for_published_snapshot", "requested_teams": 2, "included_teams": 2},
                "limitations": [
                    "This final published snapshot is not a fixture-date lineup, eligibility, or replacement history.",
                    "The FIFA registration snapshot does not certify injury status.",
                    "International caps and goals are FIFA-reported totals, not World Cup match statistics.",
                ],
            },
        })
        response = entry["response"]
        response["archive"]["provenance"] = list(dict.fromkeys(
            list(response["archive"].get("provenance") or []) + ["fifa.com:official-registration"]
        ))
        response["archive"]["missing_capabilities"] = [
            item for item in response["archive"].get("missing_capabilities", [])
            if item != "verified_complete_official_squad_registration"
        ]
        response["archive"]["notes"] = list(response["archive"].get("notes") or []) + [
            "Official FIFA registration is complete for the published snapshot and distinct from fixture-date availability."
        ]
        entry["source_manifest"].append(_registration_source({"fixture_id": fixture_id, "teams": official_teams}, evidence, fixture_id=fixture_id))
        entry["response_sha256"] = CONNECTOR._archive_sha256(response)


def _write_import_openapi(source_path: Path, output_path: Path) -> None:
    spec = _read(source_path)
    spec["servers"] = [{
        "url": "https://api.machina.gg",
        "description": "Upstream Machina API used by the ZeroClick catalog importer; not the buyer-facing gateway.",
    }]
    spec["x-publication"] = {
        "status": "local_import_source_not_published",
        "buyer_facing_spec": "https://agents.machina.gg/zcj/ajgpivnid8bn",
        "openApiUrl": "https://raw.githubusercontent.com/machina-sports/machina-templates/main/agent-templates/world-cup-intelligence/docs/openapi-import-source.json",
        "manual_gate": "Authorized dashboard re-import and post-import verification are required; changing openApiUrl alone does not publish or overwrite the catalog.",
    }
    _write(output_path, spec)


def _fixture_observed_players(pack: dict[str, Any]) -> list[dict[str, Any]]:
    observations = []
    for item in pack.get("players", []):
        if not isinstance(item, dict):
            continue
        player = item.get("player") if isinstance(item.get("player"), dict) else {}
        context = ((item.get("response") or {}).get("player_performance_context") or {})
        stats = context.get("player") if isinstance(context.get("player"), dict) else {}
        observations.append({
            "player_key": player.get("_id") or f"provider:api-football:{(player.get('provider_ids') or {}).get('api_football')}",
            "player_urn": player.get("_id"),
            "player_id": (player.get("provider_ids") or {}).get("api_football"),
            "name": player.get("name"),
            "team": player.get("team_name") or (player.get("team") or {}).get("name"),
            "statistics": stats,
        })
    return observations


def _build_backtest(entries: dict[str, list[dict[str, Any]]], source_path: Path, source_hash: str) -> None:
    forecasts = [row["response"]["forecast"] for row in entries["worldcup-get-match-forecast"]]
    events = [row["subject"]["event"] for row in entries["worldcup-get-match-forecast"]]
    details = [
        row["response"]["event_context"]["result_details"]
        for row in entries["worldcup-get-event-context"]
    ]
    finished = [{
        "fixture": {"id": row["fixture_id"], "status": {"short": row["status"]}},
        "goals": row["regulation_time_score"],
    } for row in details]
    selected = CONNECTOR.compute_forecast_audit({"params": {
        "mode": "batch",
        "forecasts": forecasts,
        "finished_fixtures": finished,
        "events": events,
        "require_pre_kickoff": True,
    }})["data"]
    report = CONNECTOR.compute_forecast_audit({"params": {
        "mode": "aggregate", "audit_results": selected["audits"],
    }})["data"]["backtesting_report"]
    if selected["total_count"] != 104 or selected["included_count"] != 98 or selected["exclusion_reasons"] != {"forecast_at_or_after_kickoff": 6}:
        raise ARCHIVE.ArchivePreparationError(f"unexpected recomputed backtest coverage: {selected}")
    entry = entries["worldcup-backtest-forecasts"][0]
    response = entry["response"]
    response.update({
        "finished_fixtures": finished,
        "status": "available",
        "provenance": "verified-v2-result-details",
        "audited_count": selected["included_count"],
        "total_count": selected["total_count"],
        "included_count": selected["included_count"],
        "excluded_count": selected["excluded_count"],
        "exclusion_reasons": selected["exclusion_reasons"],
        "sources": ["worldcup:event", "worldcup:model-forecast", "api-football"],
        "track_record": report,
    })
    response["archive"].update({
        "capability_status": "historical_aggregate",
        "provenance": ["worldcup:event", "worldcup:model-forecast", "api-football", "worldcup:forecast-audit"],
        "missing_capabilities": ["closing_line_value", "market_calibration"],
        "sample_size": 98,
        "cutoff": None,
        "notes": ["Recomputed offline from original forecast bytes and verified regulation-time result evidence; six at/after-kickoff forecasts are excluded."],
    })
    response["coverage"] = _coverage(
        "complete", "All forecasts with a pre-kickoff timestamp and verified regulation result were scored.",
        response["archive"]["provenance"], population=104, eligible=98, included=98, excluded=6,
        exclusion_reasons=selected["exclusion_reasons"], unsupported=["closing_line_value", "market_calibration"],
    )
    entry["source_manifest"] = [
        _derived_source("worldcup:event", events, source_path, source_hash, temporal_scope="tournament-archive"),
        _derived_source("worldcup:model-forecast", forecasts, source_path, source_hash, temporal_scope="historical-fixture"),
        _derived_source("api-football", details, source_path, source_hash, temporal_scope="historical-fixture"),
        _derived_source("worldcup:forecast-audit", {"backtesting_report": report}, source_path, source_hash, temporal_scope="tournament-archive"),
    ]


def _player_groups(entries: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for entry in entries["worldcup-get-player-performance-context"]:
        pack = entry["response"].get("fixture_player_pack") or {}
        event = entry["subject"]["event"]
        teams = [team for team in event.get("sport:competitors", []) if isinstance(team, dict)]
        for item in pack.get("players", []):
            player = item.get("player") if isinstance(item.get("player"), dict) else {}
            provider_id = str(
                (item.get("provider_observation") or {}).get("player_id")
                or (player.get("provider_ids") or {}).get("api_football") or ""
            )
            if not provider_id:
                raise ARCHIVE.ArchivePreparationError("fixture player is missing api-football id")
            canonical_urn = str(player.get("_id") or "")
            key = canonical_urn or f"provider:api-football:{provider_id}"
            group = groups.setdefault(key, {
                "player": copy.deepcopy(player), "observations": [], "names": set(),
                "canonical_urns": set(), "observed_provider_ids": set(),
            })
            previous = group["player"]
            if str(previous.get("team_id") or "") != str(player.get("team_id") or ""):
                raise ARCHIVE.ArchivePreparationError(f"conflicting provider player identity: {key}")
            if player.get("_id") and not previous.get("_id"):
                group["player"] = copy.deepcopy(player)
            if player.get("name"):
                group["names"].add(str(player["name"]))
            if player.get("_id"):
                group["canonical_urns"].add(str(player["_id"]))
            group["observed_provider_ids"].add(provider_id)
            team_name = player.get("team_name") or (player.get("team") or {}).get("name")
            opponents = [team.get("name") for team in teams if CONNECTOR._canonical_team_slug(team.get("name")) != CONNECTOR._canonical_team_slug(team_name)]
            context = ((item.get("response") or {}).get("player_performance_context") or {})
            group["observations"].append({
                "event_urn": pack.get("event_urn"),
                "fixture_id": pack.get("fixture_id"),
                "provider_player_id": provider_id,
                "opponent": opponents[0] if len(opponents) == 1 else None,
                "team": team_name,
                "statistics": context.get("player") if isinstance(context.get("player"), dict) else {},
                "official_fifa_power_ranking": context.get("official_fifa_power_ranking") if isinstance(context.get("official_fifa_power_ranking"), dict) else {},
            })
    for key, group in groups.items():
        if len(group["canonical_urns"]) > 1:
            raise ARCHIVE.ArchivePreparationError(f"player group maps to multiple canonical players: {key}")
        canonical_urn = next(iter(group["canonical_urns"]), "")
        player = group["player"]
        if canonical_urn:
            player["_id"] = canonical_urn
        names = sorted(group["names"])
        if names:
            player["name"] = names[0]
        player["aliases"] = sorted(set(player.get("aliases") or []) | set(names[1:]))
        player["observed_provider_ids"] = sorted(group["observed_provider_ids"], key=int)
        group["player"] = player
    return groups


def _build_spotlights(
    manifest: dict[str, Any],
    entries: dict[str, list[dict[str, Any]]],
    source_path: Path,
    source_hash: str,
    reconciliation: dict[str, Any],
    evidence: dict[str, Path],
) -> tuple[int, int]:
    originals = {row["subject"]["key"]: row for row in entries["worldcup-player-spotlight"]}
    groups = _player_groups(entries)
    spotlights = []
    for key, group in sorted(groups.items()):
        player = group["player"]
        observations = sorted(group["observations"], key=lambda row: (row["event_urn"], row["fixture_id"]))
        opponents = sorted({row["opponent"] for row in observations if row.get("opponent")})
        provider_only = not bool(player.get("_id"))
        structured = {
            "content_type": "structured_retrospective",
            "historical_perspective": "retrospective_completed_tournament",
            "player_key": key,
            "player_urn": player.get("_id"),
            "name": player.get("name"),
            "team": player.get("team_name") or (player.get("team") or {}).get("name"),
            "identity_mapping_status": player.get("identity_mapping_status") or ("provider_only" if provider_only else "canonical"),
            "provider_ids": dict(player.get("provider_ids") or {}),
            "provider_id_aliases": dict(player.get("provider_id_aliases") or {}),
            "official_registration": copy.deepcopy(player.get("official_registration")),
            "observed_appearance_count": len(observations),
            "observed_opponents": opponents,
            "observations": observations,
            "unsupported_fields": ["biography", "transfers", "match_awards", "impact_narrative"],
            "grounding": {"source": "reconciled_raw_fixture_player_captures_and_official_fifa_registration", "unsupported_claims_included": False},
        }
        original = originals.get(key)
        if original:
            skill_card = original["response"]["skill_card"]
            capability = "archived_editorial"
            snapshot = original["response"]["archive"].get("snapshot_as_of")
            content_type = "original_editorial_with_structured_retrospective"
            sources = copy.deepcopy(original["source_manifest"])
            provenance = list(original["response"]["archive"].get("provenance") or [])
        else:
            skill_card = structured
            capability = "structured_retrospective"
            snapshot = None
            content_type = "structured_retrospective"
            sources = []
            provenance = []
        derived_payload = {"body": structured, "player": player, "observations": observations}
        sources.append(_derived_source(
            "worldcup:storefront-derived-player-card", derived_payload, source_path, source_hash,
            temporal_scope="tournament-archive",
        ))
        sources.extend([
            _reconciliation_source({
                "canonical_urn": key,
                "accepted_provider_ids": player.get("observed_provider_ids") or [],
            }, evidence),
            _registration_source(player.get("official_registration"), evidence),
        ])
        provenance.extend([
            "worldcup:storefront-derived-player-card",
            "worldcup:identity-reconciliation",
            "fifa.com:official-registration",
        ])
        response = {
            "skill_card": skill_card,
            "structured_retrospective": structured,
            "original_editorial": ({
                "body": original["response"]["skill_card"],
                "generated_at": snapshot,
            } if original else None),
            "content_type": content_type,
            "player_key": key,
            "player_urn": player.get("_id"),
            "resolved_player": player,
            "player_overview": {
                "player_key": key,
                "player_urn": player.get("_id"),
                "name": player.get("name"),
                "team": player.get("team_name") or (player.get("team") or {}).get("name"),
                "provider_ids": dict(player.get("provider_ids") or {}),
                "provider_id_aliases": dict(player.get("provider_id_aliases") or {}),
                "official_registration": copy.deepcopy(player.get("official_registration")),
                "identity_mapping_status": player.get("identity_mapping_status") or ("provider_only" if provider_only else "canonical"),
            },
            "candidates": [{
                "player_key": key, "player_urn": player.get("_id"), "name": player.get("name"),
                "team": player.get("team_name") or (player.get("team") or {}).get("name"),
                "provider_ids": dict(player.get("provider_ids") or {}),
            }],
            "served_from": "final_archive",
            "warnings": ([] if original else ["No original editorial card exists; returning a deterministic source-grounded retrospective."]),
            "archive": {
                "mode": "final_archive", "competition": "FIFA World Cup 2026",
                "competition_status": "completed", "live": False, "snapshot_as_of": snapshot,
                "capability_status": capability, "provenance": list(dict.fromkeys(provenance)),
                "missing_capabilities": ["original_editorial"] if not original else [],
                "notes": ["Structured retrospective is derived only from verified archived fixture player observations."],
            },
            "coverage": _coverage(
                "complete", "Observed tournament appearances are available; unsupported biography and narrative fields are explicit.",
                list(dict.fromkeys(provenance)), population=len(observations), unsupported=structured["unsupported_fields"],
            ),
        }
        spotlights.append({
            "endpoint": "worldcup-player-spotlight",
            "subject": {
                "key": key,
                "player": player,
                "aliases": sorted(set(player.get("observed_provider_ids") or []) | {
                    str((player.get("provider_ids") or {}).get("api_football") or "")
                } - {""}),
            },
            "parameters": {}, "response": response,
            "response_sha256": CONNECTOR._archive_sha256(response), "source_manifest": sources,
        })
    entries["worldcup-player-spotlight"][:] = spotlights
    manifest["spotlight_targets"] = sorted(groups)
    manifest["targets"]["worldcup-player-spotlight"] = [{"subject_key": key, "parameters": {}} for key in sorted(groups)]
    return len(groups), sum(1 for group in groups.values() if not group["player"].get("_id"))


def _add_provider_resolve_rows(
    manifest: dict[str, Any],
    entries: dict[str, list[dict[str, Any]]],
    source_path: Path,
    source_hash: str,
) -> int:
    groups = _player_groups(entries)
    added = 0
    existing = {row["subject"]["key"] for row in entries["worldcup-resolve"]}
    for key, group in sorted(groups.items()):
        player = group["player"]
        if player.get("_id") or key in existing:
            continue
        entity = copy.deepcopy(player)
        entity["player_key"] = key
        entity["identity_mapping_status"] = "provider_only"
        provider_id = str((player.get("provider_ids") or {}).get("api_football") or "")
        response = {
            "entity": entity, "entities": [entity], "count": 1, "warnings": [],
            "archive": {
                "mode": "final_archive", "competition": "FIFA World Cup 2026",
                "competition_status": "completed", "live": False, "snapshot_as_of": None,
                "capability_status": "partial", "provenance": ["worldcup:fixture-player-packs"],
                "missing_capabilities": ["canonical_player_urn"],
                "notes": ["Provider identity is preserved without minting an unsupported canonical cross-provider URN."],
            },
            "coverage": _coverage(
                "partial", "An exact provider player id is available but canonical cross-provider identity is unverified.",
                ["worldcup:fixture-player-packs"], population=1, unsupported=["canonical_player_urn"],
            ),
        }
        source = _derived_source(
            "worldcup:fixture-player-packs", {"player": player, "observations": group["observations"]},
            source_path, source_hash, temporal_scope="tournament-archive",
        )
        entry = {
            "endpoint": "worldcup-resolve",
            "subject": {"key": key, "entity": entity, "player": entity, "aliases": [provider_id]},
            "parameters": {}, "response": response,
            "response_sha256": CONNECTOR._archive_sha256(response), "source_manifest": [source],
        }
        entries["worldcup-resolve"].append(entry)
        manifest["targets"]["worldcup-resolve"].append({"subject_key": key, "parameters": {}})
        added += 1
    return added


def build_candidate(
    source_manifest: dict[str, Any],
    source_path: Path,
    *,
    candidate_created_at: str,
    official_snapshot: dict[str, Any],
    provider_evidence: dict[str, Any],
    rankings: list[dict[str, Any]],
    captures_dir: Path,
    evidence: dict[str, Path],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    if source_manifest.get("archive_version") != CONNECTOR.FINAL_ARCHIVE_VERSION:
        raise ARCHIVE.ArchivePreparationError("readiness input must be the verified v2 manifest")
    ARCHIVE.prepare_manifest(source_manifest)
    source_hash = _sha_file(source_path)
    entries = _entry_map(source_manifest)
    if len(entries["worldcup-get-event-context"]) != 104 or len(entries["worldcup-get-player-performance-context"]) != 104:
        raise ARCHIVE.ArchivePreparationError("v2 fixture coverage is not exactly 104")

    reconciliation = FIFA.reconcile_provider_identities(
        official_snapshot,
        provider_evidence,
        _existing_identity_source(entries),
        _team_urns(entries),
    )
    added_resolve_rows = _replace_player_resolve_rows(source_manifest, entries, reconciliation, evidence)
    raw_coverage = _rebuild_fixture_player_packs(entries, reconciliation, rankings, captures_dir, evidence)
    _add_official_squads(entries, official_snapshot, reconciliation, evidence)
    source_manifest["fixture_player_urns"] = {
        row["subject"]["event_urn"]: sorted({
            item["player"]["_id"] for item in row["response"]["fixture_player_pack"]["players"]
        })
        for row in entries["worldcup-get-player-performance-context"]
    }

    standings_response = entries["worldcup-get-standings"][0]["response"]
    standings = standings_response.get("standings") or {}
    standings_index = _standings_by_team(standings)
    fixture_packs = {
        row["subject"]["event_urn"]: row["response"].get("fixture_player_pack") or {}
        for row in entries["worldcup-get-player-performance-context"]
    }

    for endpoint, endpoint_entries in entries.items():
        for entry in endpoint_entries:
            response = entry["response"]
            archive = response.get("archive") if isinstance(response.get("archive"), dict) else {}
            provenance = list(archive.get("provenance") or [])
            status = "partial" if archive.get("capability_status") in {"partial", "historical_model"} else "complete"
            reason = "Archived source evidence is available with endpoint-specific limitations recorded."
            population = 1
            unsupported: list[str] = []

            if endpoint == "worldcup-get-schedule":
                schedule = response.get("schedule") or {}
                events = schedule.get("events") or []
                schedule.update({"count": len(events), "total_count": len(events), "offset": 0, "limit": 104, "has_more": False, "truncated": False})
                population = len(events)
                reason = "All canonical tournament fixtures and verified result details are included."
            elif endpoint == "worldcup-get-event-context":
                context = response.get("event_context") or {}
                event = context.get("event") or entry["subject"].get("event") or {}
                teams = [team.get("name") for team in event.get("sport:competitors", []) if isinstance(team, dict)]
                context["sports_context"] = {
                    "status": "available",
                    "mode": "retrospective_completed_tournament",
                    "result_details": context.get("result_details"),
                    "final_group_standings": [standings_index[CONNECTOR._canonical_team_slug(name)] for name in teams if CONNECTOR._canonical_team_slug(name) in standings_index],
                }
                context["context_coverage"] = {
                    "sports_context": "available",
                    "prematch_research": "unavailable" if not context.get("prematch_research") else "available",
                    "social_pulse": "unavailable" if not context.get("social_pulse") else "available",
                    "reason": "Retrospective sports context is derived from archived result and final standings evidence; it is not prematch research.",
                }
                archive["capability_status"] = "partial"
                archive["missing_capabilities"] = [name for name in ("prematch_research", "social_pulse") if context["context_coverage"][name] == "unavailable"]
                status, reason, unsupported = "partial", context["context_coverage"]["reason"], archive["missing_capabilities"]
            elif endpoint == "worldcup-get-injuries":
                injury = response.get("injuries") or {}
                records = sum(int(team.get("count") or 0) for team in injury.get("teams", []) if isinstance(team, dict))
                complete = injury.get("coverage_complete") is True
                evidence_status = "recorded_absences" if records else ("confirmed_none" if complete else "unavailable")
                injury.update({"evidence_status": evidence_status, "observed_record_count": records, "historical_completeness_verified": complete})
                status = "complete" if complete else ("partial" if records else "unavailable")
                reason = "Archived provider absence records exist for this fixture." if records else "The archived feed was empty and does not prove no injuries."
                unsupported = [] if complete else ["complete_historical_injury_coverage"]
            elif endpoint == "worldcup-get-squads":
                squads = response.get("squads") or {}
                teams = squads.get("teams") or []
                player_count = sum(len(team.get("players") or []) for team in teams if isinstance(team, dict))
                squads.update({
                    "evidence_status": "observed_tournament_player_pool" if player_count else "unavailable",
                    "official_registration_status": "verified_final_published_snapshot", "observed_player_count": player_count,
                })
                status, reason, population = "complete", "Both fixture teams have complete 26-player rosters in the final published FIFA snapshot; observed pools remain separate.", 52
                unsupported = ["fixture_date_lineup_or_eligibility", "complete_replacement_history", "injury_certification"]
            elif endpoint == "worldcup-get-player-performance-context":
                pack = response.get("fixture_player_pack") or {}
                population = int(pack.get("raw_player_count") or 0)
                included = int(pack.get("player_count") or 0)
                provider_only = sum(1 for item in pack.get("players", []) if not (item.get("player") or {}).get("_id"))
                response["identity_coverage"] = {"canonical_count": included - provider_only, "provider_only_count": provider_only, "ambiguous_omitted_count": population - included}
                status = "complete" if included and not provider_only and population == included else ("partial" if included else "unavailable")
                reason = "Fixture participants preserve canonical URNs when evidenced and exact provider ids otherwise."
                response["coverage"] = _coverage(status, reason, provenance, population=population, eligible=included, included=included, excluded=population - included, exclusion_reasons={"ambiguous_identity": population - included} if population > included else {}, unsupported=["canonical_player_urn"] if provider_only else [])
            elif endpoint == "worldcup-get-match-forecast":
                integrity = response.get("forecast_integrity") or {}
                pre = integrity.get("verified_pre_kickoff") is True
                market = response.get("market_integrity") or {}
                status = "complete" if pre else "unavailable"
                reason = "Original model output predates kickoff." if pre else "Original model output was computed at or after kickoff."
                unsupported = [] if market.get("valid_for_edge_comparison") is True else ["verified_prematch_market_comparison"]
            elif endpoint == "worldcup-get-standings":
                groups = standings.get("groups") or []
                standings.update({"standings_scope": "final_group_standings", "team_count": sum(len(group.get("table") or []) for group in groups), "is_final_1_to_48_ranking": False})
                population = standings["team_count"]
                reason = "Twelve final group tables are separate from the 12-team third-place ranking; no 1-to-48 ranking is inferred."
                unsupported = ["final_1_to_48_tournament_ranking"]
            elif endpoint == "worldcup-match-recap":
                card = response.get("skill_card") or {}
                pack = fixture_packs.get(entry["subject"]["event_urn"], {})
                observed = _fixture_observed_players(pack)
                factual = [row for row in observed if any((row.get("statistics") or {}).get(key) not in (None, 0, "") for key in ("goals", "assists", "rating", "minutes_played"))]
                card["content_depth"] = {
                    "tier": "result_and_observed_player_evidence" if observed else "result_only",
                    "observed_player_records": observed,
                    "unsupported_narrative": ["scorers", "turning_points", "quotes", "match_awards"],
                    "narrative_verification": "unverified_original" if card.get("historical_perspective") == "original_cached_matchday_copy" else "not_included",
                }
                population = len(observed)
                reason = "Final result facts and archived player observations are exposed separately from unsupported narrative."
                unsupported = card["content_depth"]["unsupported_narrative"]
                payload = {"event_urn": entry["subject"]["event_urn"], "observed_players": factual}
                entry["source_manifest"].append(_derived_source("worldcup:fixture-player-pack", payload, source_path, source_hash, temporal_scope="historical-fixture"))
                archive["provenance"] = list(dict.fromkeys(provenance + ["worldcup:fixture-player-pack"]))
                provenance = archive["provenance"]
            elif endpoint == "worldcup-resolve":
                entity = response.get("entity") or {}
                entity.setdefault("identity_mapping_status", "canonical" if entity.get("_id") else "provider_only")
                if entity.get("identity_mapping_status") == "quarantined":
                    status = "unavailable"
                    reason = entity.get("quarantine_reason") or "Identity is quarantined."
                    unsupported = ["valid_canonical_identity"]
                else:
                    reason = "Exact archived canonical or provider identity resolution."

            if "coverage" not in response:
                response["coverage"] = _coverage(status, reason, provenance, population=population, unsupported=unsupported)
            entry["response_sha256"] = CONNECTOR._archive_sha256(response)

    _build_backtest(entries, source_path, source_hash)
    spotlight_count, provider_only_count = _build_spotlights(
        source_manifest, entries, source_path, source_hash, reconciliation, evidence,
    )
    provider_resolve_count = _add_provider_resolve_rows(source_manifest, entries, source_path, source_hash)

    all_entries = [entry for endpoint in CONNECTOR.FINAL_ARCHIVE_ENDPOINTS for entry in entries[endpoint]]
    source_manifest["entries"] = all_entries
    source_manifest.update({
        "schema_version": 2,
        "archive_version": CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION,
        "derived_from_archive_version": CONNECTOR.FINAL_ARCHIVE_VERSION,
        "derived_from_manifest_sha256": source_hash,
        "candidate_created_at": candidate_created_at,
        "expected_archive_count": len(all_entries),
        "publication_ready": True,
        "identity_reconciliation": {
            "schema_version": reconciliation["ledger"]["schema_version"],
            "counts": reconciliation["ledger"]["counts"],
            "ledger_sha256": CONNECTOR._archive_sha256(reconciliation["ledger"]),
        },
        "storefront_readiness": {
            "status": "local_candidate_ready_not_published",
            "fixture_count": 104,
            "eligible_backtest_count": 98,
            "late_forecast_exclusion_count": 6,
            "distinct_player_count": spotlight_count,
            "distinct_provider_id_count": reconciliation["ledger"]["counts"]["provider_ids"],
            "provider_only_player_count": provider_only_count,
            "retained_original_editorial_spotlight_count": 2,
            "new_reconciled_resolve_count": added_resolve_rows,
            "provider_only_resolve_count": provider_resolve_count,
            **raw_coverage,
        },
    })

    file_cache: dict[Path, list[str]] = {}
    for entry in all_entries:
        _set_timestamp_semantics(entry, file_cache)
        provenance_observed_at = _observed_at(entry, file_cache)
        entry["response"] = _sanitize_public_value(
            _qualify_public_provenance(entry["response"], provenance_observed_at)
        )
        if entry["endpoint"] in {"worldcup-match-recap", "worldcup-player-spotlight"}:
            for source in entry["source_manifest"]:
                payload = source.get("source_payload")
                if isinstance(payload, dict) and isinstance(payload.get("body"), dict):
                    payload["body"] = _sanitize_public_value(
                        _qualify_public_provenance(payload["body"], provenance_observed_at)
                    )
                    source["source_sha256"] = CONNECTOR._archive_sha256(payload)
        entry["response_sha256"] = CONNECTOR._archive_sha256(entry["response"])

    documents = ARCHIVE.prepare_manifest(source_manifest)
    bundle = {
        "archive_version": CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION,
        "manifest_sha256": CONNECTOR._archive_sha256(source_manifest),
        "offset": 0, "next_offset": len(documents), "total_count": len(documents),
        "count": len(documents), "unique_identity_count": len(documents),
        "invalidated": False, "documents": documents,
    }
    ARCHIVE.verify_bundle(bundle, source_manifest)
    document_ids = [row["value"]["_id"] for row in documents]
    document_commitments = CONNECTOR._archive_document_commitments(documents)
    closure = CONNECTOR.build_final_archive_manifest({"params": {
        "fixture_urns": source_manifest["fixture_urns"],
        "fixture_coverage": source_manifest["fixture_coverage"],
        "grounded_recap_fixture_urns": source_manifest["grounded_recap_fixture_urns"],
        "fixture_player_urns": source_manifest["fixture_player_urns"],
        "spotlight_targets": source_manifest["spotlight_targets"],
        "archive_document_ids": document_ids,
        "archive_document_commitments": document_commitments,
        "expected_archive_count": len(documents),
        "forecast_baseline_sha256": source_manifest["forecast_baseline_sha256"],
        "forecast_readback_sha256": source_manifest["forecast_baseline_sha256"],
        "closed_at": candidate_created_at,
    }}, archive_version=CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION)
    closure_bundle = {"archive_version": CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION, "count": 1, "documents": [closure]}
    if CONNECTOR.validate_final_archive_manifest(closure_bundle["documents"], archive_version=CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION)[0] != "closed":
        raise ARCHIVE.ArchivePreparationError("v3 closure candidate failed validation")
    closure_search_payload = {
        "status": "success",
        "data": {"data": closure_bundle["documents"], "total_documents": 1},
    }
    closure_mcp_envelope = {
        "content": [{"type": "text", "text": json.dumps(closure_search_payload, ensure_ascii=False, separators=(",", ":"))}],
    }
    closure_mcp_envelope_bytes = len(json.dumps(closure_mcp_envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if closure_mcp_envelope_bytes >= 1024 * 1024:
        raise ARCHIVE.ArchivePreparationError("v3 closure MCP envelope exceeds the 1 MiB client limit")
    forecast_rows = entries["worldcup-get-match-forecast"]
    forecast_timing_counts: dict[str, int] = {}
    market_timing_counts: dict[str, int] = {}
    for row in forecast_rows:
        forecast_class = str((row["response"].get("forecast_integrity") or {}).get("classification") or "unavailable")
        market_class = str((row["response"].get("market_integrity") or {}).get("classification") or "unavailable")
        forecast_timing_counts[forecast_class] = forecast_timing_counts.get(forecast_class, 0) + 1
        market_timing_counts[market_class] = market_timing_counts.get(market_class, 0) + 1
    injury_counts: dict[str, int] = {}
    for row in entries["worldcup-get-injuries"]:
        status = str((row["response"].get("injuries") or {}).get("evidence_status") or "unavailable")
        injury_counts[status] = injury_counts.get(status, 0) + 1
    squad_teams = {
        CONNECTOR._canonical_team_slug(team.get("team") or team.get("name"))
        for row in entries["worldcup-get-squads"]
        for team in (row["response"].get("squads") or {}).get("teams", [])
        if isinstance(team, dict) and (team.get("team") or team.get("name"))
    }
    report = {
        "schema_version": 1,
        "status": "local_candidate_ready_not_published",
        "archive_version": CONNECTOR.NEXT_FINAL_ARCHIVE_VERSION,
        "derived_from_archive_version": CONNECTOR.FINAL_ARCHIVE_VERSION,
        "candidate_created_at": candidate_created_at,
        "counts": {
            "fixtures": 104, "archive_records": len(documents), "endpoints": len(entries),
            "backtest_population": 104, "backtest_eligible": 98, "backtest_excluded_late": 6,
            "distinct_people": spotlight_count,
            "distinct_provider_ids": reconciliation["ledger"]["counts"]["provider_ids"],
            "provider_only_players": provider_only_count,
            "spotlights": len(entries["worldcup-player-spotlight"]), "retained_original_editorial_spotlights": len([
                row for row in entries["worldcup-player-spotlight"] if row["response"]["original_editorial"] is not None
            ]),
            "provider_only_resolve_rows": provider_resolve_count,
            "new_reconciled_resolve_rows": added_resolve_rows,
            "official_registration_teams": official_snapshot["team_count"],
            "official_registration_players": official_snapshot["player_count"],
            "official_registration_font_warnings": official_snapshot["validation"]["font_artifact_warning_count"],
            "official_registration_unknown_clubs": official_snapshot["validation"]["club_not_reported_count"],
            "raw_player_fixture_observations": raw_coverage["raw_player_fixture_observations"],
            "archived_player_fixture_observations": raw_coverage["archived_player_fixture_observations"],
            "raw_player_capture_files": raw_coverage["raw_capture_count"],
            "restored_marco_fixtures": raw_coverage["restored_marco_fixtures"],
            "identity_reconciliation": reconciliation["ledger"]["counts"],
            "forecast_timing": dict(sorted(forecast_timing_counts.items())),
            "market_timing": dict(sorted(market_timing_counts.items())),
            "injury_evidence": dict(sorted(injury_counts.items())),
            "observed_squad_teams": len(squad_teams),
        },
        "integrity": {
            "candidate_manifest_sha256": CONNECTOR._archive_sha256(source_manifest),
            "candidate_document_ids_sha256": CONNECTOR._archive_sha256(sorted(document_ids)),
            "forecast_baseline_sha256": source_manifest["forecast_baseline_sha256"],
            "forecast_candidate_payload_sha256": CONNECTOR._archive_sha256(sorted([
                {"id": str(row["response"]["forecast"].get("_id") or row["response"]["forecast"].get("@id") or ""), "value": row["response"]["forecast"]}
                for row in forecast_rows
            ], key=lambda item: item["id"])),
            "bundle_verified": True, "closure_verified": True,
            "closure_commitment_count": len(document_commitments),
            "closure_mcp_envelope_bytes": closure_mcp_envelope_bytes,
            "provider_calls": 0, "model_calls": 0, "document_writes": 0,
        },
        "unsupported_capabilities": [
            "fixture_date_lineup_or_eligibility", "complete_replacement_history", "injury_certification",
            "complete_historical_injury_coverage",
            "prematch_research_for_all_fixtures", "social_pulse_for_all_fixtures",
            "closing_line_value", "market_calibration",
        ],
        "remaining_release_gates": [
            "Review and import the v3 candidate rows into the target document store.",
            "Read all v3 rows back and verify exact identities, values, counts, and hashes.",
            "Import the reviewed v3 closure manifest and explicitly switch the server-owned workflow version from v2 to v3.",
            "Publish and verify the external ZeroClick catalog/OpenAPI transport contract separately.",
            "Rollback remains an explicit workflow switch to the preserved active v2 closure.",
        ],
    }
    return source_manifest, bundle, closure_bundle, report, reconciliation["ledger"]


def prepare(
    source: Path,
    output_dir: Path,
    *,
    candidate_created_at: str,
    fifa_pdf: Path,
    fifa_snapshot: Path,
    fifa_raw_cells: Path,
    provider_evidence_path: Path,
    preliminary_audit_path: Path,
    raw_captures_dir: Path,
    rankings_path: Path,
    openapi_source: Path,
    import_openapi_output: Path,
) -> dict[str, Any]:
    source = source.resolve()
    output_dir = output_dir.resolve()
    evidence = {
        "pdf": fifa_pdf.resolve(),
        "snapshot": fifa_snapshot.resolve(),
        "raw_cells": fifa_raw_cells.resolve(),
        "provider_evidence": provider_evidence_path.resolve(),
        "preliminary_audit": preliminary_audit_path.resolve(),
    }
    raw_captures_dir = raw_captures_dir.resolve()
    rankings_path = rankings_path.resolve()
    openapi_source = openapi_source.resolve()
    import_openapi_output = import_openapi_output.resolve()
    try:
        source.relative_to(REPO.resolve())
        output_dir.relative_to(REPO.resolve())
        raw_captures_dir.relative_to(REPO.resolve())
        rankings_path.relative_to(REPO.resolve())
        openapi_source.relative_to(REPO.resolve())
        import_openapi_output.relative_to(REPO.resolve())
        for path in evidence.values():
            path.relative_to(REPO.resolve())
    except ValueError as exc:
        raise ARCHIVE.ArchivePreparationError("all readiness inputs and outputs must stay inside this repository") from exc
    manifest = _read(source)
    fixture_ids = {
        str(entry.get("subject", {}).get("provider_event_id"))
        for entry in manifest.get("entries", [])
        if entry.get("endpoint") == "worldcup-get-player-performance-context"
    }
    raw_capture_paths = [
        raw_captures_dir / fixture_id / "worldcup-archive-capture-players.json"
        for fixture_id in sorted(fixture_ids)
    ]
    extra_sources = [*evidence.values(), rankings_path, openapi_source, *raw_capture_paths]
    before = _verified_source_hashes(manifest, source, extra_sources)
    official_snapshot = FIFA.load_official_registration(
        evidence["pdf"], evidence["snapshot"], evidence["raw_cells"],
    )
    provider_evidence = _read(evidence["provider_evidence"])
    rankings = _read(rankings_path)
    if not isinstance(provider_evidence, dict) or not isinstance(rankings, list):
        raise ARCHIVE.ArchivePreparationError("provider evidence and rankings have invalid shapes")
    candidate, bundle, closure, report, reconciliation_ledger = build_candidate(
        manifest,
        source,
        candidate_created_at=candidate_created_at,
        official_snapshot=official_snapshot,
        provider_evidence=provider_evidence,
        rankings=rankings,
        captures_dir=raw_captures_dir,
        evidence=evidence,
    )
    preliminary = _read(evidence["preliminary_audit"])
    expected_preliminary = {
        "raw_rows": report["counts"]["raw_player_fixture_observations"],
        "distinct_provider_ids": report["counts"]["distinct_provider_ids"],
        "matched_official_team_jersey_keys": report["counts"]["distinct_people"],
    }
    if any(preliminary.get(key) != value for key, value in expected_preliminary.items()):
        raise ARCHIVE.ArchivePreparationError("independent preliminary FIFA audit does not match rebuilt corpus")
    outputs = {
        "candidate_manifest": output_dir / "candidate-manifest-v3.json",
        "candidate_bundle": output_dir / "candidate-bundle-v3.json",
        "closure_candidate": output_dir / "closure-candidate-v3.json",
        "identity_reconciliation": output_dir / "identity-reconciliation-v3.json",
        "import_openapi": import_openapi_output,
        "readiness_report": output_dir / "readiness-report.json",
    }
    _write(outputs["candidate_manifest"], candidate)
    _write(outputs["candidate_bundle"], bundle)
    _write(outputs["closure_candidate"], closure)
    _write(outputs["identity_reconciliation"], reconciliation_ledger)
    _write_import_openapi(openapi_source, outputs["import_openapi"])
    after = _verified_source_hashes(_read(source), source, extra_sources)
    if before != after:
        raise ARCHIVE.ArchivePreparationError("source evidence changed while preparing the candidate")
    report["source_evidence"] = {"unchanged": True, "file_count": len(before), "sha256": before}
    report["artifacts"] = {name: str(path.relative_to(REPO)) for name, path in outputs.items()}
    report["artifact_sha256"] = {
        name: _sha_file(path) for name, path in outputs.items() if name != "readiness_report"
    }
    _write(outputs["readiness_report"], report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate-created-at", required=True)
    parser.add_argument("--fifa-pdf", type=Path, required=True)
    parser.add_argument("--fifa-snapshot", type=Path, required=True)
    parser.add_argument("--fifa-raw-cells", type=Path, required=True)
    parser.add_argument("--provider-player-evidence", type=Path, required=True)
    parser.add_argument("--fifa-preliminary-audit", type=Path, required=True)
    parser.add_argument("--raw-captures-dir", type=Path, required=True)
    parser.add_argument("--rankings", type=Path, required=True)
    parser.add_argument("--openapi-source", type=Path, required=True)
    parser.add_argument("--import-openapi-output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        report = prepare(
            args.source,
            args.output_dir,
            candidate_created_at=args.candidate_created_at,
            fifa_pdf=args.fifa_pdf,
            fifa_snapshot=args.fifa_snapshot,
            fifa_raw_cells=args.fifa_raw_cells,
            provider_evidence_path=args.provider_player_evidence,
            preliminary_audit_path=args.fifa_preliminary_audit,
            raw_captures_dir=args.raw_captures_dir,
            rankings_path=args.rankings,
            openapi_source=args.openapi_source,
            import_openapi_output=args.import_openapi_output,
        )
    except (ARCHIVE.ArchivePreparationError, FIFA.FifaReconciliationError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"storefront readiness preparation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({
        "status": report["status"], "archive_version": report["archive_version"],
        "archive_records": report["counts"]["archive_records"],
        "fixtures": report["counts"]["fixtures"],
        "backtest_eligible": report["counts"]["backtest_eligible"],
        "spotlights": report["counts"]["spotlights"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
