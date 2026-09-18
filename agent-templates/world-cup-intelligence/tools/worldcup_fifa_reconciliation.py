#!/usr/bin/env python3
"""Validate the official FIFA squad PDF and reconcile its players offline."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any


FIFA_SOURCE_URL = "https://fdp.fifa.org/assetspublic/ce281/pdf/SquadLists-English.pdf"
FIFA_SOURCE_SHA256 = "02a0a9beb5d219e7cc0aedde19273e9a3bfe4818ecd600d37804b8801dd96d94"
FIFA_DOCUMENT_GENERATED_AT = "2026-07-19T22:34:35+00:00"
QUARANTINED_MARIO_URN = "urn:machina:sport:soccer:player:mario-pasalic:20000914:hrv"
MARCO_URN = "urn:machina:sport:soccer:player:marco-pasalic:20000914:hrv"

TEAM_ALIASES = {
    "bosnia-herzegovina": "bosnia-and-herzegovina",
    "cape-verde-islands": "cabo-verde",
    "ivory-coast": "cote-d-ivoire",
    "iran": "ir-iran",
    "south-korea": "korea-republic",
}

# These are explicit source-to-source transliteration aliases. They are not
# fuzzy matches: every row is also bound to one stable team/jersey registration.
VERIFIED_PROVIDER_NAME_ALIASES = {
    "1138", "1361", "2685", "2687", "2892", "3034", "1115", "16805", "16831",
    "16841", "16797", "18938", "190575", "196343", "2533", "2539", "2545",
    "303362", "339795", "36579", "36967", "37892", "38114", "393977", "41552",
    "42207", "42286", "43953", "44315", "44324", "44335", "44367", "44382",
    "44411", "44449", "44475", "44551", "44362", "49866", "50057", "50132", "535046",
    "53835", "65576", "65584", "72122", "72142", "73507", "73510", "89982",
    "102505", "102538", "104244", "123530", "134217", "134590", "134995",
    "147812", "15286", "158433", "163884", "175439", "193288", "25915",
    "269174", "283174", "304467", "314882", "315099", "343405", "375608",
    "395075", "409492", "416964", "423753", "430078", "453073", "542541",
    "542542", "575283", "626479", "63274", "61837", "62490", "339883",
    "36967", "134590",
}


class FifaReconciliationError(ValueError):
    """Raised when local official-registration evidence is incomplete or inconsistent."""


def _read(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _slug(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _compact(value: Any) -> str:
    return _slug(value).replace("-", "")


def _team_key(value: Any) -> str:
    slug = _slug(value)
    return TEAM_ALIASES.get(slug, slug)


def _date(value: Any) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError) as exc:
        raise FifaReconciliationError(f"invalid FIFA birth date: {value!r}") from exc


def _raw_cells_match(record: dict[str, Any], cells: list[Any]) -> bool:
    if len(cells) == 9 and record.get("club_raw") is None:
        cells = [*cells[:6], "", *cells[6:]]
    if len(cells) != 10:
        return False
    expected = [
        record.get("position_code"), record.get("player_name_raw"), record.get("first_names_raw"),
        record.get("last_names_raw"), record.get("shirt_name_raw"),
        date.fromisoformat(record["birth_date"]).strftime("%d/%m/%Y"), record.get("club_raw") or "",
        record.get("height_cm"), record.get("international_caps_as_reported"),
        record.get("international_goals_as_reported"),
    ]
    return all(
        (actual is None and wanted is None)
        or (actual is not None and wanted is not None and str(actual) == str(wanted))
        for actual, wanted in zip(cells, expected)
    )


def load_official_registration(
    pdf_path: Path,
    snapshot_path: Path,
    raw_cells_path: Path,
) -> dict[str, Any]:
    """Bind the structured snapshot to the exact PDF, raw cells, and jersey geometry."""
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - the build command supplies it.
        raise FifaReconciliationError("PyMuPDF is required to validate the FIFA PDF") from exc

    if _sha_file(pdf_path) != FIFA_SOURCE_SHA256:
        raise FifaReconciliationError("official FIFA PDF hash mismatch")
    snapshot = _read(snapshot_path)
    raw = _read(raw_cells_path)
    records = snapshot.get("records") if isinstance(snapshot, dict) else None
    raw_records = raw.get("records") if isinstance(raw, dict) else None
    if not isinstance(records, list) or not isinstance(raw_records, list):
        raise FifaReconciliationError("FIFA snapshot and raw cells must contain records arrays")
    if snapshot.get("source_url") != FIFA_SOURCE_URL or raw.get("source_url") != FIFA_SOURCE_URL:
        raise FifaReconciliationError("FIFA source URL mismatch")
    if snapshot.get("source_sha256") != FIFA_SOURCE_SHA256:
        raise FifaReconciliationError("structured FIFA snapshot is not bound to the supplied PDF")
    if snapshot.get("document_generated_at") != FIFA_DOCUMENT_GENERATED_AT:
        raise FifaReconciliationError("unexpected FIFA publication timestamp")
    if snapshot.get("team_count") != 48 or snapshot.get("player_count") != 1248:
        raise FifaReconciliationError("unexpected FIFA snapshot counts")
    if raw.get("pages") != 48 or len(records) != 1248 or len(raw_records) != 1248:
        raise FifaReconciliationError("FIFA evidence must contain 48 pages and 1,248 players")

    by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    raw_by_page: dict[int, list[dict[str, Any]]] = defaultdict(list)
    registration_keys: set[tuple[str, int]] = set()
    identity_keys: set[tuple[str, str, str]] = set()
    font_warning_count = 0
    club_not_reported_count = 0
    for record in records:
        page = record.get("source_page")
        number = record.get("jersey_number")
        if not isinstance(page, int) or not isinstance(number, int) or not 1 <= page <= 48 or not 1 <= number <= 26:
            raise FifaReconciliationError("invalid FIFA page or jersey number")
        _date(record.get("birth_date"))
        key = (_team_key(record.get("team_name")), number)
        identity_key = (key[0], record["birth_date"], _compact(record.get("player_name_raw")))
        if key in registration_keys or identity_key in identity_keys:
            raise FifaReconciliationError(f"duplicate FIFA registration: {key}")
        registration_keys.add(key)
        identity_keys.add(identity_key)
        warnings = record.get("warnings") if isinstance(record.get("warnings"), list) else []
        font_warning_count += int("pdf_text_encoding_artifact_in_raw_name_or_club" in warnings)
        club_not_reported_count += int("club_not_reported" in warnings)
        if record.get("club_raw") is None and warnings != ["club_not_reported"]:
            raise FifaReconciliationError("a null FIFA club must be explicitly flagged")
        by_page[page].append(record)
    for raw_record in raw_records:
        if not isinstance(raw_record, dict) or not isinstance(raw_record.get("page"), int):
            raise FifaReconciliationError("invalid raw FIFA cell record")
        raw_by_page[raw_record["page"]].append(raw_record)
    if font_warning_count != 15 or club_not_reported_count != 1:
        raise FifaReconciliationError("unexpected FIFA extraction warning counts")

    document = pymupdf.open(pdf_path)
    if document.page_count != 48:
        raise FifaReconciliationError("official FIFA PDF must contain 48 pages")
    team_labels = set()
    for page_number in range(1, 49):
        page_records = sorted(by_page[page_number], key=lambda row: row["jersey_number"])
        page_raw = raw_by_page[page_number]
        if len(page_records) != 26 or len(page_raw) != 26:
            raise FifaReconciliationError(f"FIFA page {page_number} does not contain 26 players")
        labels = {str(row.get("team_label") or "") for row in page_raw}
        if len(labels) != 1:
            raise FifaReconciliationError(f"FIFA page {page_number} has an ambiguous team label")
        label = labels.pop()
        team_labels.add(label)
        expected_label = f"{page_records[0]['team_name']} ({page_records[0]['fifa_team_code']})"
        if label != expected_label:
            raise FifaReconciliationError(f"FIFA team label mismatch on page {page_number}")
        for record, raw_record in zip(page_records, page_raw):
            if raw_record.get("team_label") != label or not _raw_cells_match(record, raw_record.get("cells") or []):
                raise FifaReconciliationError(f"structured FIFA row is not bound to raw cells: page {page_number}")

        page = document[page_number - 1]
        words = page.get_text("words", sort=True)
        numbers = [
            (int(word[4]), float(word[1])) for word in words
            if float(word[2]) < 15 and str(word[4]).isdigit() and 1 <= int(word[4]) <= 26 and 45 < float(word[1]) < 185
        ]
        if [number for number, _ in numbers] != list(range(1, 27)):
            raise FifaReconciliationError(f"FIFA jersey geometry mismatch on page {page_number}")
        page_text = page.get_text("text")
        if _compact(label) not in _compact(page_text):
            raise FifaReconciliationError(f"FIFA team label missing from PDF page {page_number}")
        if "sunday19july2026" not in _compact(page_text) or "2234utc" not in _compact(page_text):
            raise FifaReconciliationError(f"FIFA publication footer mismatch on page {page_number}")
        for record, (_, y) in zip(page_records, numbers):
            line = " ".join(str(word[4]) for word in words if abs(float(word[1]) - y) < 0.4)
            if _compact(record["player_name_raw"]) not in _compact(line):
                raise FifaReconciliationError(
                    f"FIFA player row is not bound to PDF geometry: page {page_number}, jersey {record['jersey_number']}"
                )
    document.close()
    if len(team_labels) != 48:
        raise FifaReconciliationError("FIFA team labels are not unique across all 48 pages")
    return {
        **snapshot,
        "validation": {
            "pdf_sha256_verified": True,
            "pdf_page_count": 48,
            "team_label_count": 48,
            "players_per_team": 26,
            "unique_registration_count": 1248,
            "all_birth_dates_valid": True,
            "jersey_numbers_geometry_verified": True,
            "font_artifact_warning_count": font_warning_count,
            "club_not_reported_count": club_not_reported_count,
        },
    }


def _name_match_basis(provider_id: str, provider_name: str, official: dict[str, Any]) -> str | None:
    provider_slug = _slug(provider_name)
    provider_tokens = set(provider_slug.split("-"))
    official_values = [
        official.get("player_name_raw"), official.get("first_names_raw"),
        official.get("last_names_raw"), official.get("shirt_name_raw"),
    ]
    official_tokens = set().union(*(set(_slug(value).split("-")) for value in official_values if value))
    if provider_tokens and provider_tokens <= official_tokens:
        return "normalized_name_tokens"
    provider_compact = _compact(provider_name)
    official_compact = {_compact(value) for value in official_values if value}
    first_last = _compact(official.get("first_names_raw")) + _compact(official.get("last_names_raw"))
    last_first = _compact(official.get("last_names_raw")) + _compact(official.get("first_names_raw"))
    if provider_compact in official_compact or provider_compact in {first_last, last_first}:
        return "normalized_name_order_spacing"
    if provider_id in VERIFIED_PROVIDER_NAME_ALIASES:
        return "verified_source_transliteration_alias"
    return None


def _provider_aliases(identity: dict[str, Any], provider: str) -> list[str]:
    aliases = identity.get("provider_id_aliases") if isinstance(identity.get("provider_id_aliases"), dict) else {}
    return [str(value) for value in aliases.get(provider, []) if str(value)]


def reconcile_provider_identities(
    official_snapshot: dict[str, Any],
    provider_evidence: dict[str, Any],
    existing_identities: list[dict[str, Any]],
    team_urns: dict[str, str],
) -> dict[str, Any]:
    """Create a strict provider-to-official ledger and a one-row-per-person identity index."""
    records = official_snapshot["records"]
    official_by_key = {(_team_key(row["team_name"]), row["jersey_number"]): row for row in records}
    existing_by_provider: dict[str, list[dict[str, Any]]] = defaultdict(list)
    existing_by_urn = {}
    for identity in existing_identities:
        urn = str(identity.get("_id") or identity.get("@id") or "")
        if urn:
            existing_by_urn[urn] = copy.deepcopy(identity)
        provider_ids = identity.get("provider_ids") if isinstance(identity.get("provider_ids"), dict) else {}
        provider_id = str(provider_ids.get("api_football") or "")
        if provider_id:
            existing_by_provider[provider_id].append(identity)

    accepted = []
    ambiguous = []
    conflicts = []
    registration_provider_ids: dict[tuple[str, int], list[str]] = defaultdict(list)
    provider_match: dict[str, dict[str, Any]] = {}
    for provider_id, evidence in provider_evidence.items():
        observations = evidence.get("observations") if isinstance(evidence, dict) else None
        if not isinstance(observations, list) or not observations:
            ambiguous.append({"provider_id": provider_id, "reason": "missing_provider_observations"})
            continue
        observed_keys = {
            (_team_key(row.get("team_name")), row.get("number"))
            for row in observations if isinstance(row, dict)
        }
        if len(observed_keys) != 1:
            ambiguous.append({"provider_id": provider_id, "reason": "inconsistent_provider_observations"})
            continue
        team_key, jersey_number = next(iter(observed_keys))
        official = official_by_key.get((team_key, jersey_number))
        if official is None:
            ambiguous.append({"provider_id": provider_id, "reason": "official_team_jersey_not_found"})
            continue
        provider_names = sorted({str(row.get("name") or "") for row in observations})
        match_bases = {_name_match_basis(str(provider_id), name, official) for name in provider_names}
        if None in match_bases:
            ambiguous.append({
                "provider_id": str(provider_id), "provider_names": provider_names,
                "official_name": official["player_name_raw"], "team": official["team_name"],
                "jersey_number": jersey_number, "reason": "name_evidence_does_not_agree",
            })
            continue
        provider_name = provider_names[0]
        canonical_evidence = evidence.get("canonical") if isinstance(evidence.get("canonical"), dict) else {}
        canonical_urn = str(canonical_evidence.get("_id") or "")
        canonical_date = canonical_urn.split(":")[-2] if canonical_urn else ""
        canonical_birth_date = (
            f"{canonical_date[:4]}-{canonical_date[4:6]}-{canonical_date[6:]}"
            if len(canonical_date) == 8 and canonical_date.isdigit() else None
        )
        canonical_basis = []
        if canonical_urn:
            canonical_basis.append("existing_canonical_provider_mapping")
            canonical_basis.append(
                "canonical_birth_date_agrees" if canonical_birth_date == official["birth_date"]
                else "canonical_birth_date_conflict_retained"
            )
        registration_key = (team_key, jersey_number)
        registration_provider_ids[registration_key].append(str(provider_id))
        provider_match[str(provider_id)] = official
        accepted.append({
            "provider": "api-football", "provider_id": str(provider_id),
            "provider_name": provider_name, "team": official["team_name"],
            "jersey_number": jersey_number, "official_name": official["player_name_raw"],
            "official_birth_date": official["birth_date"], "official_source_page": official["source_page"],
            "provider_name_aliases": provider_names,
            "match_basis": [
                "consistent_provider_team_jersey", *sorted(match_bases), *canonical_basis,
                "official_pdf_registration",
            ],
            "observation_count": len(observations),
        })
    if ambiguous or len(accepted) != 1249 or len(registration_provider_ids) != 1248:
        raise FifaReconciliationError(
            f"identity reconciliation incomplete: accepted={len(accepted)}, ambiguous={len(ambiguous)}, registrations={len(registration_provider_ids)}"
        )
    duplicate_registrations = {
        key: sorted(ids) for key, ids in registration_provider_ids.items() if len(ids) > 1
    }
    if duplicate_registrations != {("qatar", 25): ["339795", "542542"]}:
        raise FifaReconciliationError(f"unexpected duplicate provider registration: {duplicate_registrations}")

    identities_by_urn: dict[str, dict[str, Any]] = {}
    identity_by_provider: dict[str, dict[str, Any]] = {}
    registration_to_identity: dict[tuple[str, int], dict[str, Any]] = {}
    for registration_key, provider_ids in sorted(registration_provider_ids.items()):
        official = official_by_key[registration_key]
        evidenced_urns = {
            str((provider_evidence[provider_id].get("canonical") or {}).get("_id") or "")
            for provider_id in provider_ids
        } - {"", QUARANTINED_MARIO_URN}
        candidates = []
        for provider_id in provider_ids:
            candidates.extend(existing_by_provider.get(provider_id, []))
        valid_candidates = []
        for candidate in candidates:
            candidate_urn = str(candidate.get("_id") or candidate.get("@id") or "")
            candidate_name = str(candidate.get("name") or "")
            if candidate_urn == QUARANTINED_MARIO_URN:
                conflicts.append({
                    "type": "quarantined_identity_mapping", "canonical_urn": candidate_urn,
                    "provider_ids": dict(candidate.get("provider_ids") or {}),
                    "reason": "Mario/Marco collision: name and FIFA DOB/jersey disagree with provider 260865.",
                    "valid_candidates": [MARCO_URN, "urn:machina:sport:soccer:player:mario-pasalic:19950209:hrv"],
                })
                continue
            if candidate_urn in evidenced_urns or _name_match_basis(provider_ids[0], candidate_name, official):
                valid_candidates.append(candidate)
        unique_candidate_urns = {
            str(row.get("_id") or row.get("@id") or "") for row in valid_candidates
            if str(row.get("_id") or row.get("@id") or "")
        }
        if len(unique_candidate_urns) > 1:
            raise FifaReconciliationError(f"multiple canonical identities agree with registration {registration_key}")
        if unique_candidate_urns:
            urn = next(iter(unique_candidate_urns))
            identity = copy.deepcopy(existing_by_urn[urn])
        else:
            provider_name = str(provider_evidence[provider_ids[0]]["observations"][0]["name"])
            team_urn = team_urns.get(registration_key[0])
            if not team_urn:
                raise FifaReconciliationError(f"missing canonical team URN for {official['team_name']}")
            country_code = team_urn.rsplit(":", 1)[-1]
            urn = (
                "urn:machina:sport:soccer:player:"
                f"{_slug(provider_name)}:{official['birth_date'].replace('-', '')}:{country_code}"
            )
            identity = {
                "@id": urn, "_id": urn, "id": urn,
                "@type": ["sport:IdentityCrosswalk", "sport:Player"],
                "name": provider_name, "aliases": [], "nationality": official["team_name"],
                "team": {"@id": team_urn, "name": official["team_name"]},
                "mapping_status": {"official_registration_reconciled": True},
            }
        primary_provider_id = sorted(provider_ids, key=lambda value: (value != "339795", int(value)))[0]
        provider_id_aliases = [value for value in sorted(provider_ids) if value != primary_provider_id]
        identity["provider_ids"] = dict(identity.get("provider_ids") or {})
        identity["provider_ids"]["api_football"] = primary_provider_id
        if provider_id_aliases:
            identity["provider_id_aliases"] = dict(identity.get("provider_id_aliases") or {})
            identity["provider_id_aliases"]["api_football"] = provider_id_aliases
        canonical_birth_date = str(identity.get("birth_date") or "") or None
        birth_date_conflict = canonical_birth_date is not None and canonical_birth_date != official["birth_date"]
        identity["official_registration"] = {
            "status": "verified_final_published_snapshot",
            "source": "FIFA",
            "source_url": FIFA_SOURCE_URL,
            "source_sha256": FIFA_SOURCE_SHA256,
            "published_at": FIFA_DOCUMENT_GENERATED_AT,
            "source_page": official["source_page"],
            "team_name": official["team_name"],
            "fifa_team_code": official["fifa_team_code"],
            "jersey_number": official["jersey_number"],
            "player_name_raw": official["player_name_raw"],
            "first_names_raw": official["first_names_raw"],
            "last_names_raw": official["last_names_raw"],
            "shirt_name_raw": official["shirt_name_raw"],
            "birth_date": official["birth_date"],
            "position_code": official["position_code"],
            "club_raw": official["club_raw"],
            "height_cm": official["height_cm"],
            "international_caps_as_reported": official["international_caps_as_reported"],
            "international_goals_as_reported": official["international_goals_as_reported"],
            "warnings": list(official.get("warnings") or []),
            "canonical_birth_date": canonical_birth_date,
            "canonical_birth_date_conflict": birth_date_conflict,
            "scope_note": "Caps/goals are FIFA-reported international totals, not World Cup match statistics.",
        }
        if birth_date_conflict:
            conflicts.append({
                "type": "canonical_birth_date_conflict", "canonical_urn": urn,
                "provider_id": primary_provider_id, "canonical_birth_date": canonical_birth_date,
                "official_birth_date": official["birth_date"], "official_source_page": official["source_page"],
                "resolution": "stable canonical identifier retained; FIFA DOB exposed only in source-scoped registration metadata",
            })
        identities_by_urn[urn] = identity
        registration_to_identity[registration_key] = identity
        for provider_id in provider_ids:
            identity_by_provider[provider_id] = identity
            next(row for row in accepted if row["provider_id"] == provider_id)["canonical_urn"] = urn

    if len(identities_by_urn) != 1248 or len(identity_by_provider) != 1249:
        raise FifaReconciliationError("reconciled identity cardinality mismatch")
    dob_conflicts = [row for row in conflicts if row["type"] == "canonical_birth_date_conflict"]
    quarantine_conflicts = [row for row in conflicts if row["type"] == "quarantined_identity_mapping"]
    if len(dob_conflicts) != 14 or len(quarantine_conflicts) != 1:
        raise FifaReconciliationError(
            f"unexpected conflict ledger counts: dob={len(dob_conflicts)}, quarantine={len(quarantine_conflicts)}"
        )
    ledger = {
        "schema_version": "worldcup-fifa-reconciliation-v1",
        "official_source": {
            "url": FIFA_SOURCE_URL, "sha256": FIFA_SOURCE_SHA256,
            "published_at": FIFA_DOCUMENT_GENERATED_AT,
        },
        "accepted": sorted(accepted, key=lambda row: int(row["provider_id"])),
        "ambiguous": ambiguous,
        "conflicting": sorted(conflicts, key=lambda row: (row["type"], row.get("canonical_urn", ""))),
        "counts": {
            "official_people": 1248, "provider_ids": 1249, "accepted_provider_ids": len(accepted),
            "ambiguous_provider_ids": len(ambiguous), "duplicate_provider_aliases": 1,
            "canonical_birth_date_conflicts": len(dob_conflicts), "quarantined_identity_mappings": 1,
        },
    }
    return {
        "ledger": ledger,
        "identities": sorted(identities_by_urn.values(), key=lambda row: row["_id"]),
        "identity_by_provider": identity_by_provider,
        "registration_to_identity": registration_to_identity,
        "quarantined_identity": copy.deepcopy(existing_by_urn[QUARANTINED_MARIO_URN]),
    }


def provider_id_matches(identity: dict[str, Any], provider_id: Any) -> bool:
    """Return whether a scalar provider id or a separately typed alias matches."""
    requested = str(provider_id or "")
    ids = identity.get("provider_ids") if isinstance(identity.get("provider_ids"), dict) else {}
    return requested == str(ids.get("api_football") or "") or requested in _provider_aliases(identity, "api_football")
