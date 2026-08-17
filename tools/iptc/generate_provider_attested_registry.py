"""Generate the Design 034 data-only owner registry.

The records describe synthetic, provider-data-free replay artifacts. They attest
Sports Skills' normalized adapter boundary, never provider transport payloads.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "tools/iptc/canonical/data/source_shape_registry_v2.json"
PROVIDER = "sports-skills/espn"

OPERATIONS = {
    "arena_nba_event": {
        "shape_id": "arena-step10-nba-event",
        "fixtures": ["nba-exact-authoritative", "nba-exact-provider-scoped"],
        "sport": "basketball", "output_kind": "event", "family": "event",
    },
    "arena_nba_longitudinal": {
        "shape_id": "arena-step10-nba-longitudinal",
        "fixtures": ["nba-career-string"],
        "sport": "basketball", "output_kind": "longitudinal",
        "family": "longitudinal",
    },
    "arena_nba_refusal_event": {
        "shape_id": "arena-step10-nba-refusal-event",
        "fixtures": ["ambiguous-identity", "unpromised-managed-collection",
                     "unresolved-identity"],
        "sport": "basketball", "output_kind": "event", "family": "nba-refusal",
    },
    "arena_nfl_event": {
        "shape_id": "arena-step10-nfl-event",
        "fixtures": ["nfl-exact-authoritative", "nfl-exact-provider-scoped"],
        "sport": "american-football", "output_kind": "event", "family": "event",
    },
    "arena_nfl_longitudinal": {
        "shape_id": "arena-step10-nfl-longitudinal",
        "fixtures": ["nfl-rolling-anchor-number", "nfl-season-string"],
        "sport": "american-football", "output_kind": "longitudinal",
        "family": "longitudinal",
    },
    "arena_nfl_refusal_event": {
        "shape_id": "arena-step10-nfl-refusal-event",
        "fixtures": ["rights-ineligible", "unsupported-capability"],
        "sport": "american-football", "output_kind": "event", "family": "nfl-refusal",
    },
    "arena_soccer_event": {
        "shape_id": "arena-step10-soccer-event",
        "fixtures": ["soccer-exact-authoritative",
                     "soccer-exact-provider-scoped",
                     "soccer-reduced-provider-scoped"],
        "sport": "soccer", "output_kind": "event", "family": "event",
    },
    "arena_soccer_longitudinal": {
        "shape_id": "arena-step10-soccer-longitudinal",
        "fixtures": ["soccer-date-range-string", "soccer-season-number"],
        "sport": "soccer", "output_kind": "longitudinal",
        "family": "longitudinal",
    },
    "arena_soccer_refusal_event": {
        "shape_id": "arena-step10-soccer-refusal-event",
        "fixtures": ["provider-scoped-graph", "reduced-graph",
                     "source-representation-mismatch"],
        "sport": "soccer", "output_kind": "event", "family": "soccer-refusal",
    },
}

STATISTICS = {
    "arena_nba_event": {
        "name": "spbkbstat:minutesPlayed",
        "representation": "json-number-exact-integer/1",
        "unit": {"kind": "unit", "unit_id": "minute"},
        "projection": "not_projected", "reason": "closed-shape-not-admitted",
    },
    "arena_nfl_event": {
        "name": "spamfstat:rushesAttempts",
        "representation": "json-number-exact-integer/1",
        "unit": {"kind": "no_unit"},
        "projection": "not_projected", "reason": "closed-shape-not-admitted",
    },
    "arena_soccer_event": {
        "name": "spsocstat:cornerKicks",
        "representation": "json-string-canonical-integer/1",
        "unit": {"kind": "no_unit"},
        "projection": "projected", "reason": "shape-admitted",
    },
}

SPATIAL_REPRESENTATIONS = {
    "arena_nba_event": "json-number-exact-spatial-decimal/1",
    "arena_nfl_event": "json-number-exact-spatial-decimal/1",
    "arena_soccer_event": "json-string-canonical-spatial-decimal/1",
    "arena_soccer_refusal_event": "json-string-canonical-spatial-decimal/1",
}

SEQUENCE_REPRESENTATIONS = {
    "arena_nba_longitudinal": {
        "nba-career-string": "json-string-canonical-non-negative-integer/1",
    },
    "arena_nfl_longitudinal": {
        "nfl-rolling-anchor-number": "json-number-exact-non-negative-integer/1",
        "nfl-season-string": "json-string-canonical-non-negative-integer/1",
    },
    "arena_soccer_longitudinal": {
        "soccer-date-range-string": "json-string-canonical-non-negative-integer/1",
        "soccer-season-number": "json-number-exact-non-negative-integer/1",
    },
}


def string(*values):
    node = {"kind": "string"}
    if values:
        node["allowed_values"] = sorted(values)
    return node


def boolean(*values):
    node = {"kind": "boolean"}
    if values:
        node["allowed_values"] = sorted(values)
    return node


def number():
    return {"kind": "number"}


def array(items):
    return {"kind": "array", "items": items}


def object_shape(members, required=()):
    return {
        "kind": "object",
        "members": members,
        "required": sorted(required),
        "unknown_members": "forbidden",
    }


def boundary_schema():
    return object_shape(
        {"end_exclusive": string(), "start_inclusive": string()},
        ("end_exclusive", "start_inclusive"),
    )


def identity_schema(output_kind):
    entity_types = ("athlete", "team", "season") if output_kind == "longitudinal" \
        else ("athlete", "competition", "event", "season", "site", "team")
    return object_shape({
        "authority_id": string(),
        "entity_type": string(*entity_types),
        "provider_id": string(),
        "resolution_method": string(
            "synthetic_ambiguous", "synthetic_authority",
            "synthetic_provider_scoped", "synthetic_unresolved"),
        "status": string(
            "ambiguous", "authoritatively_resolved", "provider_scoped", "unresolved"),
    }, ("entity_type", "provider_id", "resolution_method", "status"))


def coverage_tuple_schema():
    return object_shape({
        "cursor": string(),
        "page_cap": number(),
        "request_limit": number(),
        "total": number(),
        "truncated": boolean(False, True),
    }, ("cursor", "page_cap", "request_limit", "total", "truncated"))


def statistic_schema(value_node):
    return object_shape({"field_id": string(), "value": value_node},
                        ("field_id", "value"))


def event_schema(operation, config):
    representation = SPATIAL_REPRESENTATIONS.get(operation)
    spatial_value = number() if representation == \
        "json-number-exact-spatial-decimal/1" else string()
    if operation == "arena_soccer_refusal_event":
        # The negative artifact deliberately carries the opposite representation;
        # the semantic binding remains string-only and must refuse it.
        spatial_value = number()
    statistic = STATISTICS.get(operation)
    statistic_value = number() if statistic and statistic["representation"].startswith(
        "json-number") else string()
    participant = object_shape({
        "alignment": string("away", "home"),
        "id": string(),
        "kind": string("athlete", "team"),
        "score": string(),
        "statistics": array(statistic_schema(statistic_value)),
    }, ("id", "kind", "statistics"))
    spatial = object_shape({
        "distance": spatial_value,
        "x": spatial_value,
        "y": spatial_value,
        "zone": string(),
    }, ("x", "y"))
    action = object_shape({
        "id": string(),
        "period_ref": string(),
        "spatial": spatial,
        "team_id": string(),
    }, ("id",))
    sequence = string() if config["sport"] == "soccer" else number()
    period = object_shape({
        "boundary": boundary_schema(),
        "event_provider_id": string(),
        "event_provider_namespace": string(),
        "event_resolution_method": string(),
        "scheme": string(),
        "sequence": sequence,
        "value": string(),
    }, ("event_provider_id", "event_provider_namespace", "event_resolution_method",
        "scheme", "sequence", "value"))
    event = object_shape({
        "actions": array(action),
        "competition_id": string(),
        "id": string(),
        "participants": array(participant),
        "periods": array(period),
        "phase_id": string(),
        "season_id": string(),
        "site_id": string(),
        "start": object_shape({
            "state": string("bounded", "exact"), "value": string(),
        }, ("state", "value")),
        "status": string(),
    }, ("actions", "competition_id", "id", "participants", "periods", "start",
        "status"))
    coverage = object_shape({
        "actions": coverage_tuple_schema(),
        "participant_statistics": array(coverage_tuple_schema()),
        "participants": coverage_tuple_schema(),
    }, ("actions", "participant_statistics", "participants"))
    return object_shape({
        "contains_provider_data": boolean(False),
        "coverage": coverage,
        "event": event,
        "fixture_id": string(*config["fixtures"]),
        "identity": array(identity_schema("event")),
        "sport": string(config["sport"]),
        "synthetic": boolean(True),
    }, ("contains_provider_data", "coverage", "event", "fixture_id", "identity",
        "sport", "synthetic"))


def longitudinal_schema(operation, config):
    statistic_value = string() if config["sport"] == "soccer" else number()
    statistic = statistic_schema(statistic_value)
    # The closed grammar has no unions. The owner record keeps the common scalar
    # slot closed; exact per-fixture number/string interpretation is digest-bound
    # in the operation evidence below and enforced by the consumer package.
    period = object_shape({
        "boundary": boundary_schema(),
        "scheme": string(),
        "sequence": string(),
        "value": string(),
    }, ("scheme", "sequence", "value"))
    record = object_shape({
        "period": period,
        "semantics": string(
            "cumulative_through_period", "period_delta", "snapshot_at_period"),
        "statistics": array(statistic),
    }, ("period", "semantics", "statistics"))
    anchor = object_shape({
        "provider_id": string(),
        "provider_namespace": string(),
        "resolution_method": string(),
        "source_record_id": string(),
    }, ("provider_id", "provider_namespace", "resolution_method", "source_record_id"))
    scope = object_shape({
        "anchor": anchor,
        "end": string(),
        "kind": string("career", "date-range", "rolling-window", "season"),
        "season_id": string(),
        "start": string(),
        "window_size": number(),
    }, ("kind",))
    coverage = object_shape({
        "aggregates": coverage_tuple_schema(),
        "record_statistics": array(coverage_tuple_schema()),
        "records": coverage_tuple_schema(),
    }, ("aggregates", "record_statistics", "records"))
    return object_shape({
        "aggregates": array(statistic),
        "contains_provider_data": boolean(False),
        "coverage": coverage,
        "fixture_id": string(*config["fixtures"]),
        "identity": array(identity_schema("longitudinal")),
        "records": array(record),
        "scope": scope,
        "sport": string(config["sport"]),
        "subject": object_shape({
            "entity_type": string("athlete", "team"), "provider_id": string(),
        }, ("entity_type", "provider_id")),
        "synthetic": boolean(True),
    }, ("aggregates", "contains_provider_data", "coverage", "fixture_id", "identity",
        "records", "scope", "sport", "subject", "synthetic"))


def nfl_refusal_schema(config):
    return object_shape({
        "contains_provider_data": boolean(False),
        "fixture_id": string(*config["fixtures"]),
        "sport": string(config["sport"]),
        "synthetic": boolean(True),
    }, ("contains_provider_data", "fixture_id", "sport", "synthetic"))


def artifact_schema(operation, config):
    if config["family"] == "nfl-refusal":
        return nfl_refusal_schema(config)
    if config["family"] == "longitudinal":
        return longitudinal_schema(operation, config)
    return event_schema(operation, config)


def statistic_evidence(operation):
    statistic = STATISTICS[operation]
    return {
        "canonical_occurrence_pattern":
            "/observation/participants/{participant_index}/statistics/{statistic_index}",
        "description": (
            "The statistic path is synthetic-replay-only. Its official name and "
            "projection disposition are constrained by the unchanged owner manifests; "
            "this record does not attest provider transport fields."
        ),
        "evidence_class": "validated_statistic_source_and_disposition",
        "projection": statistic["projection"],
        "projection_reason": statistic["reason"],
        "source_representation": statistic["representation"],
        "source_value_pointer_template":
            "/event/participants/{participant_index}/statistics/{statistic_index}/value",
        "statistic_kind": "official",
        "statistic_name": statistic["name"],
        "statistic_scope": "event",
        "unit_disposition": statistic["unit"],
        "value_kind": "integer",
    }


def spatial_evidence(operation):
    return {
        "canonical_occurrence_pattern": "/observation/actions/{action_index}",
        "description": (
            "Coordinates, distance, zones, and spatial coverage are "
            "synthetic-replay-only parser evidence and do not attest provider "
            "transport coordinates."
        ),
        "distance_pointer_template": "/event/actions/{action_index}/spatial/distance",
        "evidence_class": "validated_spatial_evidence_and_disposition",
        "period_ref_pointer_template": "/event/actions/{action_index}/period_ref",
        "source_representation": SPATIAL_REPRESENTATIONS[operation],
        "team_id_pointer_template": "/event/actions/{action_index}/team_id",
        "x_pointer_template": "/event/actions/{action_index}/spatial/x",
        "y_pointer_template": "/event/actions/{action_index}/spatial/y",
        "zone_pointer_template": "/event/actions/{action_index}/spatial/zone",
    }


def event_period_evidence():
    return {
        "boundary_pointer_template": "/event/periods/{period_index}/boundary",
        "canonical_occurrence_pattern": "/period_registry/{period_index}",
        "description": (
            "Period boundaries and resolution evidence are synthetic-replay-only; "
            "no provider-native period completeness is attested."
        ),
        "event_provider_id_pointer_template":
            "/event/periods/{period_index}/event_provider_id",
        "event_provider_namespace_pointer_template":
            "/event/periods/{period_index}/event_provider_namespace",
        "event_resolution_method_pointer_template":
            "/event/periods/{period_index}/event_resolution_method",
        "evidence_class": "event_period_source",
        "scheme_pointer_template": "/event/periods/{period_index}/scheme",
        "sequence_pointer_template": "/event/periods/{period_index}/sequence",
        "value_pointer_template": "/event/periods/{period_index}/value",
    }


def identity_evidence(output_kind):
    return {
        "canonical_occurrence_pattern": "/identity_evidence/{identity_index}",
        "description": (
            "Authority, ambiguity, unresolved status, and complete census semantics "
            "are synthetic-replay-only and grant no external identity authority."
        ),
        "evidence_class": "complete_identity_census",
        "source_pointer_template": "/identity/{identity_index}",
        "output_kind": output_kind,
    }


def longitudinal_evidence(operation):
    sport = OPERATIONS[operation]["sport"]
    name = {"soccer": "spsocstat:cornerKicks",
            "american-football": "spamfstat:rushesAttempts",
            "basketball": "spbkbstat:minutesPlayed"}[sport]
    description = (
        "Longitudinal period, scope, anchor, aggregation, and coverage semantics are "
        "synthetic-replay-only. Statistic rows may model the normalized core-stat "
        "shape but do not attest provider transport period semantics."
    )
    evidence = [{
        "boundary_pointer_template": "/records/{record_index}/period/boundary",
        "canonical_occurrence_pattern": "/records/{record_index}",
        "description": description,
        "evidence_class": "longitudinal_period_source",
        "fixture_sequence_representations": SEQUENCE_REPRESENTATIONS[operation],
        "scheme_pointer_template": "/records/{record_index}/period/scheme",
        "sequence_pointer_template": "/records/{record_index}/period/sequence",
        "value_pointer_template": "/records/{record_index}/period/value",
    }, {
        "canonical_occurrence_pattern":
            "/records/{record_index}/statistics/{statistic_index}",
        "description": description,
        "evidence_class": "longitudinal_record_statistic_source",
        "projection": "not_projected",
        "projection_reason": "longitudinal-contract-no-iptc-projection",
        "source_value_pointer_template":
            "/records/{record_index}/statistics/{statistic_index}/value",
        "statistic_name": name,
    }, {
        "canonical_occurrence_pattern": "/aggregates/{statistic_index}",
        "description": description,
        "evidence_class": "longitudinal_aggregate_statistic_source",
        "projection": "not_projected",
        "projection_reason": "longitudinal-contract-no-iptc-projection",
        "source_value_pointer_template": "/aggregates/{statistic_index}/value",
        "statistic_name": name,
    }, identity_evidence("longitudinal")]
    if operation == "arena_nfl_longitudinal":
        evidence.append({
            "canonical_occurrence_pattern": "/scope/anchor",
            "description": description,
            "evidence_class": "rolling_event_anchor_source",
            "provider_id_pointer_template": "/scope/anchor/provider_id",
            "provider_namespace_pointer_template":
                "/scope/anchor/provider_namespace",
            "resolution_method_pointer_template":
                "/scope/anchor/resolution_method",
            "source_record_id_pointer_template": "/scope/anchor/source_record_id",
        })
    return evidence


def operation_evidence(operation, config):
    if config["family"] == "longitudinal":
        return longitudinal_evidence(operation)
    if config["family"] == "nfl-refusal":
        return [{
            "description": (
                "This operation exists only for preflight rights, capability, and "
                "argument refusals; selecting it attests no provider source field."
            ),
            "evidence_class": "preflight_refusal_only",
        }]
    evidence = [identity_evidence("event"), event_period_evidence()]
    if operation in STATISTICS:
        evidence.append(statistic_evidence(operation))
    if operation in SPATIAL_REPRESENTATIONS:
        evidence.append(spatial_evidence(operation))
    return evidence


def source_fields(base):
    members = {
        "cursor": "cursor", "page_cap": "page_cap",
        "request_limit": "request_limit", "total": "total",
        "truncation": "truncated",
    }
    return {
        name: {"state": "value", "value_pointer_templates": [base + "/" + member]}
        for name, member in sorted(members.items())
    }


def collection_promise(pointer, base):
    return {
        "description": (
            "Collection totals, truncation, cursor, cap, and request-limit semantics "
            "are synthetic-replay-only coverage evidence."
        ),
        "pointer_pattern": pointer,
        "source_base_pointer_template": base,
        "source_fields": source_fields(base),
    }


def collection_promises(operation, config):
    event = {
        "/observation/actions": "/coverage/actions",
        "/observation/participants": "/coverage/participants",
        "/observation/participants/{participant_index}/statistics":
            "/coverage/participant_statistics/{participant_index}",
    }
    longitudinal = {
        "/aggregates": "/coverage/aggregates",
        "/records": "/coverage/records",
        "/records/{record_index}/statistics":
            "/coverage/record_statistics/{record_index}",
    }
    if config["family"] == "longitudinal":
        selected = longitudinal
    elif config["family"] == "soccer-refusal":
        selected = {key: value for key, value in event.items()
                    if "statistics" not in key}
    elif config["family"] == "nba-refusal":
        selected = {"/observation/participants": "/coverage/participants"}
    elif config["family"] == "nfl-refusal":
        selected = {}
    else:
        selected = event
    return [collection_promise(pointer, selected[pointer]) for pointer in sorted(selected)]


def record_digest(record):
    return "sha256:" + hashlib.sha256(canonical_bytes(record)).hexdigest()


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def generate_registry():
    shapes = []
    operations = []
    outputs = []
    for operation in sorted(OPERATIONS):
        config = OPERATIONS[operation]
        shape = {
            "artifact_schema": artifact_schema(operation, config),
            "media_type": "application/json",
            "operation": operation,
            "output_kind": config["output_kind"],
            "provider_namespace": PROVIDER,
            "schema_version": "machina-source-shape/1",
            "source_shape_id": config["shape_id"],
            "source_shape_version": "1",
        }
        source_ref = {
            "source_shape_digest": record_digest(shape),
            "source_shape_id": config["shape_id"],
            "source_shape_version": "1",
        }
        output = {
            "operation": operation,
            "output_collection_contract_id": config["shape_id"] + "-collections",
            "output_collection_contract_version": "1",
            "output_kind": config["output_kind"],
            "promised_collections": collection_promises(operation, config),
            "provider_namespace": PROVIDER,
            "schema_version": "machina-output-collection-contract/1",
            "source_shape_ref": source_ref,
        }
        output_ref = {
            "output_collection_contract_digest": record_digest(output),
            "output_collection_contract_id": output[
                "output_collection_contract_id"],
            "output_collection_contract_version": "1",
        }
        contract = {
            "operation": operation,
            "output_collection_contract_ref": output_ref,
            "output_kind": config["output_kind"],
            "promised_non_collection_evidence": operation_evidence(operation, config),
            "provider_namespace": PROVIDER,
            "schema_version": "machina-operation-contract/1",
            "source_shape_ref": source_ref,
        }
        shapes.append(shape)
        operations.append(contract)
        outputs.append(output)
    return {
        "operation_contracts": operations,
        "output_collection_contracts": outputs,
        "registry_id": "machina-phase1-source-shapes",
        "registry_version": "2",
        "schema_version": "machina-source-shape-registry/1",
        "shapes": shapes,
    }


def generate():
    OUTPUT.write_bytes(canonical_bytes(generate_registry()) + b"\n")


if __name__ == "__main__":
    generate()
