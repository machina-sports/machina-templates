"""Offline contract tests for the NFL workload Machina snapshot."""

import ast
import importlib.util
import json
import re
import socket
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skills" / "nfl-workload"
CONNECTOR_PATH = PACKAGE / "connectors" / "nfl-workload.py"
CONTRACT_PATH = PACKAGE / "contracts" / "machina-player-workload-snapshot-v1.json"
CI_PATH = ROOT / ".github" / "workflows" / "test-nfl-workload.yml"
CANONICAL = ROOT / "tools" / "iptc" / "canonical"


def load_source_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


IDS = load_source_module("nfl_snapshot_ids", CANONICAL / "ids.py")
RIGHTS_MODULE = load_source_module("nfl_snapshot_rights", CANONICAL / "rights.py")
surrogate_resolver = IDS.surrogate_resolver
rights_findings = RIGHTS_MODULE.rights_findings


def canonical_capability_names():
    tree = ast.parse((CANONICAL / "capabilities.py").read_text(encoding="utf-8"))
    values = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id in {
                "TIER_REQUIRED",
                "TIER_OPTIONAL",
            }:
                values[target.id] = ast.literal_eval(node.value)
    return tuple(
        sorted(
            {
                capability
                for tiers in values.values()
                for capabilities in tiers.values()
                for capability in capabilities
            }
        )
    )


ALL_CAPABILITIES = canonical_capability_names()

RIGHTS = {
    "data_class": "open-public",
    "prototype_only": True,
    "commercial_use": False,
}

REPORT = {
    "season": 2025,
    "through_week": 8,
    "position": "WR",
    "team": "CIN",
    "lookback_weeks": 3,
    "sorted_by": "wopr",
    "method_version": "workload-v0",
    "source": "nflverse play-by-play via nflreadpy (public data)",
    "players": [
        {
            "player_id": "00-0036900",
            "player_display_name": "Ja'Marr Chase",
            "player_name": "J.Chase",
            "position": "WR",
            "team": "CIN",
            "targets": 70,
            "receptions": 52,
            "carries": 2,
            "target_share": 0.31,
            "air_yards_share": 0.42,
            "rush_share": 0.01,
            "wopr": 0.759,
            "opportunities": 72,
            "rz_targets": 10,
            "rz_carries": 1,
            "rz_touches": 11,
            "total_epa": 18.25,
            "epa_per_opportunity": 0.253472,
            "recent_target_share": 0.34,
            "recent_wopr": 0.81,
            "recent_rush_share": 0.0,
            "recent_opportunities": 26,
            "target_share_delta": 0.03,
            "wopr_delta": 0.051,
            "rush_share_delta": -0.01,
            "last_week": 8,
            "unused_provider_payload": {"secret": "must-not-leak"},
        },
        {
            "player_id": "00-0039325",
            "player_display_name": "Andrei Iosivas",
            "player_name": "A.Iosivas",
            "position": "WR",
            "team": "CIN",
            "targets": 24,
            "receptions": 13,
            "carries": 0,
            "target_share": None,
            "air_yards_share": 0.14,
            "rush_share": 0.0,
            "wopr": 0.098,
            "opportunities": 24,
            "rz_targets": 4,
            "rz_carries": 0,
            "rz_touches": 4,
            "total_epa": -1.5,
            "epa_per_opportunity": -0.0625,
            "target_share_delta": None,
            "wopr_delta": -0.01,
            "rush_share_delta": 0.0,
            "last_week": 8,
        },
    ],
}

DEPS = {"nflreadpy": "0.1.5", "polars": "1.43.2"}
OBSERVED_AT = "2026-08-15T12:30:00+00:00"


def load_connector():
    spec = importlib.util.spec_from_file_location(
        "nfl_workload_snapshot_test", CONNECTOR_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def public_schema_validator():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(contract)
    return Draft202012Validator(contract, format_checker=FormatChecker())


def install_canonical_runtime(monkeypatch, rights_findings_fn):
    package = ModuleType("machina_sports_canonical")
    package.__path__ = []
    capabilities = ModuleType("machina_sports_canonical.capabilities")
    capabilities.ALL_CAPABILITIES = ALL_CAPABILITIES
    ids = ModuleType("machina_sports_canonical.ids")
    ids.surrogate_resolver = surrogate_resolver
    rights = ModuleType("machina_sports_canonical.rights")
    rights.rights_findings = rights_findings_fn
    modules = {
        "machina_sports_canonical": package,
        "machina_sports_canonical.capabilities": capabilities,
        "machina_sports_canonical.ids": ids,
        "machina_sports_canonical.rights": rights,
    }
    for name, fake_module in modules.items():
        monkeypatch.setitem(sys.modules, name, fake_module)


def project(module, report=None, observed_at=OBSERVED_AT, rights=None):
    return module._project_machina_workload_snapshot(
        deepcopy(REPORT if report is None else report),
        observed_at,
        dict(DEPS),
        id_resolver=surrogate_resolver("nflverse"),
        rights=deepcopy(RIGHTS if rights is None else rights),
        capability_names=ALL_CAPABILITIES,
        contract_findings_fn=module._snapshot_contract_findings,
    )


def walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_keys(child)


def walk_values(value):
    if isinstance(value, dict):
        for child in value.values():
            yield child
            yield from walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield child
            yield from walk_values(child)


def test_native_report_response_is_deep_equal_unchanged(monkeypatch):
    module = load_connector()
    expected_report = deepcopy(REPORT)
    fake_nflreadpy = SimpleNamespace(__version__="0.1.5")
    fake_polars = SimpleNamespace(__version__="1.43.2")
    monkeypatch.setitem(sys.modules, "nflreadpy", fake_nflreadpy)
    monkeypatch.setitem(sys.modules, "polars", fake_polars)
    monkeypatch.setattr(module, "_ensure_deps", lambda: (True, None))
    monkeypatch.setattr(
        module, "_load_frames", lambda _nfl, _season: (object(), object(), None)
    )
    monkeypatch.setattr(
        module,
        "_build_report_payload",
        lambda *_args, **_kwargs: deepcopy(expected_report),
    )
    monkeypatch.setattr(module, "_loaded_versions", lambda: dict(DEPS))

    actual = module.generate_workload_report(
        {
            "params": {
                "season": 2025,
                "through_week": 8,
                "position": "WR",
                "team": "CIN",
            }
        }
    )

    assert actual == {
        "status": True,
        "data": {
            "report": expected_report,
            "season": 2025,
            "week": 8,
            "position": "WR",
            "n_players": 2,
            "deps": DEPS,
        },
    }


def test_projection_is_deterministic_and_has_only_the_aggregate_contract():
    module = load_connector()
    first = project(module)
    second = project(module)

    assert first == second
    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(
        second, sort_keys=True, separators=(",", ":")
    )
    assert set(first) == {"machina_workload_snapshot"}
    assert first["machina_workload_snapshot"]["schema_version"] == (
        "machina-player-workload-snapshot/1"
    )
    forbidden = {
        "machina_sports_schema",
        "sport_schema_graph",
        "event_view",
        "canonical-observation/1.1",
        "@context",
        "@id",
        "@type",
    }
    keys = set(walk_keys(first))
    assert not forbidden.intersection(keys)
    assert not any(key.startswith("sport:") for key in keys)


@pytest.mark.parametrize("forbidden_key", ["@id", "sport:fake"])
def test_forbidden_key_walkers_recurse_into_players(forbidden_key):
    module = load_connector()
    snapshot = project(module)
    snapshot["machina_workload_snapshot"]["players"][0][forbidden_key] = "forbidden"

    assert forbidden_key in set(walk_keys(snapshot))
    assert "event/RDF/envelope keys are forbidden in this aggregate" in (
        module._snapshot_contract_findings(snapshot)
    )


@pytest.mark.parametrize(
    ("sort_key", "tie_value"), [("wopr", 0.5), ("opportunities", 40)]
)
def test_snapshot_ties_are_byte_stable_across_native_input_order(sort_key, tie_value):
    module = load_connector()
    tied_first, tied_second = deepcopy(REPORT["players"])
    tied_first[sort_key] = tie_value
    tied_second[sort_key] = tie_value
    null_last = deepcopy(tied_first)
    null_last.update(
        {
            "player_id": "00-0099999",
            "player_display_name": "Null Wopr",
            "player_name": "N.Wopr",
            sort_key: None,
        }
    )
    first_report = deepcopy(REPORT)
    first_report["sorted_by"] = sort_key
    first_report["players"] = [tied_second, null_last, tied_first]
    second_report = deepcopy(REPORT)
    second_report["sorted_by"] = sort_key
    second_report["players"] = [null_last, tied_first, tied_second]

    first = project(module, report=first_report)
    second = project(module, report=second_report)
    first_body = first["machina_workload_snapshot"]

    assert json.dumps(first, separators=(",", ":")) == json.dumps(
        second, separators=(",", ":")
    )
    assert [player["id"] for player in first_body["players"]] == [
        surrogate_resolver("nflverse")("player", player_id)
        for player_id in ("00-0036900", "00-0039325", "00-0099999")
    ]
    assert [player["metrics"].get(sort_key) for player in first_body["players"]] == [
        tie_value,
        tie_value,
        None,
    ]
    assert [
        item["provider_id"]
        for item in first_body["provider_ids"]
        if item["entity_type"] == "player"
    ] == ["00-0036900", "00-0039325", "00-0099999"]


def test_projection_is_pure_and_invokes_injected_contract(monkeypatch):
    module = load_connector()
    called = []

    def refuse_side_effect(*_args, **_kwargs):
        raise AssertionError("pure projection attempted an external side effect")

    monkeypatch.setattr(module, "_ensure_deps", refuse_side_effect)
    monkeypatch.setattr(module.subprocess, "run", refuse_side_effect)
    monkeypatch.setattr(module, "_load_frames", refuse_side_effect)
    monkeypatch.setattr(socket, "socket", refuse_side_effect)

    result = module._project_machina_workload_snapshot(
        deepcopy(REPORT),
        OBSERVED_AT,
        dict(DEPS),
        id_resolver=surrogate_resolver("nflverse"),
        rights=deepcopy(RIGHTS),
        capability_names=ALL_CAPABILITIES,
        contract_findings_fn=lambda snapshot: called.append(snapshot) or [],
    )

    assert called == [result]


def test_projection_fails_closed_on_injected_contract_findings():
    module = load_connector()

    with pytest.raises(ValueError, match="snapshot contract failed: injected finding"):
        module._project_machina_workload_snapshot(
            deepcopy(REPORT),
            OBSERVED_AT,
            dict(DEPS),
            id_resolver=surrogate_resolver("nflverse"),
            rights=deepcopy(RIGHTS),
            capability_names=ALL_CAPABILITIES,
            contract_findings_fn=lambda _snapshot: ["injected finding"],
        )


def test_production_canonical_rights_refusal_precedes_all_data_access(monkeypatch):
    module = load_connector()
    calls = []
    finding = {
        "code": "rights-prototype-only",
        "consumer_tier": "production",
        "data_class": "open-public",
        "detail": "canonical refusal",
    }

    def fake_rights_findings(envelope, consumer_tier):
        calls.append((deepcopy(envelope), consumer_tier))
        return [finding]

    def refuse_side_effect(*_args, **_kwargs):
        raise AssertionError("production refusal reached workload execution")

    install_canonical_runtime(monkeypatch, fake_rights_findings)
    monkeypatch.setattr(module, "_ensure_deps", refuse_side_effect)
    monkeypatch.setattr(module, "_load_frames", refuse_side_effect)
    monkeypatch.setattr(module, "generate_workload_report", refuse_side_effect)
    monkeypatch.setattr(module.subprocess, "run", refuse_side_effect)
    monkeypatch.setattr(socket, "socket", refuse_side_effect)
    monkeypatch.delitem(sys.modules, "nflreadpy", raising=False)
    monkeypatch.delitem(sys.modules, "polars", raising=False)

    result = module.generate_machina_workload_snapshot(
        {
            "params": {
                "season": 2025,
                "through_week": 8,
                "position": "WR",
                "team": "CIN",
                "observed_at": OBSERVED_AT,
                "consumer_tier": "production",
            }
        }
    )

    assert calls == [
        (
            {"machina_sports_schema": {"rights": deepcopy(module._SNAPSHOT_RIGHTS)}},
            "production",
        )
    ]
    assert result == {
        "status": False,
        "message": "rights refusal: canonical policy does not permit this consumer tier",
        "data": {
            "allowed": False,
            "snapshot": None,
            "refusals": [finding],
            "stage": "pre-retrieval",
        },
    }
    assert "nflreadpy" not in sys.modules
    assert "polars" not in sys.modules


def test_prototype_runtime_lazily_imports_installed_canonical_distribution(monkeypatch):
    module = load_connector()
    calls = []

    def fake_rights_findings(envelope, consumer_tier):
        calls.append((deepcopy(envelope), consumer_tier))
        return rights_findings(envelope, consumer_tier=consumer_tier)

    expected_call = (
        {"machina_sports_schema": {"rights": deepcopy(module._SNAPSHOT_RIGHTS)}},
        "prototype",
    )

    def fake_generate_workload_report(_request):
        assert calls == [expected_call]
        return {
            "status": True,
            "data": {
                "report": deepcopy(REPORT),
                "season": 2025,
                "week": 8,
                "position": "WR",
                "n_players": 2,
                "deps": dict(DEPS),
            },
        }

    install_canonical_runtime(monkeypatch, fake_rights_findings)
    monkeypatch.setattr(
        module, "generate_workload_report", fake_generate_workload_report
    )

    result = module.generate_machina_workload_snapshot(
        {
            "params": {
                "season": 2025,
                "through_week": 8,
                "position": "WR",
                "team": "CIN",
                "observed_at": OBSERVED_AT,
                "consumer_tier": "prototype",
            }
        }
    )

    assert result["status"] is True
    assert calls == [expected_call]
    assert result["data"]["snapshot"]["machina_workload_snapshot"][
        "schema_version"
    ] == ("machina-player-workload-snapshot/1")


def test_missing_canonical_runtime_fails_closed_before_data_access(monkeypatch):
    module = load_connector()
    package = ModuleType("machina_sports_canonical")
    package.__path__ = []

    def refuse_side_effect(*_args, **_kwargs):
        raise AssertionError("missing canonical runtime reached workload execution")

    for name in (
        "machina_sports_canonical.capabilities",
        "machina_sports_canonical.ids",
        "machina_sports_canonical.rights",
    ):
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setitem(sys.modules, "machina_sports_canonical", package)
    monkeypatch.setattr(module, "generate_workload_report", refuse_side_effect)
    monkeypatch.setattr(module, "_ensure_deps", refuse_side_effect)
    monkeypatch.setattr(module.subprocess, "run", refuse_side_effect)

    result = module.generate_machina_workload_snapshot(
        {
            "params": {
                "observed_at": OBSERVED_AT,
                "consumer_tier": "production",
            }
        }
    )

    assert result == {
        "status": False,
        "message": "machina_sports_canonical is required at runtime",
    }


def test_ids_are_marked_surrogates_and_provider_ids_remain_evidence():
    module = load_connector()
    body = project(module)["machina_workload_snapshot"]

    urns = [body["competition"]["id"], body["season"]["id"], body["team"]["id"]]
    urns.extend(player["id"] for player in body["players"])
    urns.extend(
        value
        for value in walk_values(body)
        if isinstance(value, str) and value.startswith("urn:machina:sports:")
    )
    assert all(urn.startswith("urn:machina:sports:") for urn in urns)
    assert all(urn.rsplit(":", 1)[-1].startswith("x") for urn in urns)
    assert body["identity"]["status"] == "provider-scoped-surrogate"
    assert body["identity"]["canonical_identity"] is False

    evidence = body["provider_ids"]
    assert {item["resolution_method"] for item in evidence} == {
        "declared",
        "provider-native",
    }
    competition = next(
        item for item in evidence if item["evidence"] == "snapshot.competition.constant"
    )
    assert competition["provider_id"] == "nfl"
    assert competition["resolution_method"] == "declared"
    season = next(item for item in evidence if item["evidence"] == "report.season")
    assert season["provider_id"] == "2025"
    assert season["resolution_method"] == "declared"
    native = [
        item
        for item in evidence
        if item["evidence"] == "report.team"
        or re.fullmatch(r"report\.players\[\d+\]\.(?:player_id|team)", item["evidence"])
    ]
    assert native
    assert {item["entity_type"] for item in native} == {"player", "team"}
    assert all(item["resolution_method"] == "provider-native" for item in native)
    assert len(evidence) == 2 + len(native)
    assert not any(key in item for item in evidence for key in ("sameAs", "exactMatch"))
    assert not any(item["provider_namespace"] == "espn" for item in evidence)


def test_provider_evidence_schema_enforces_cardinality_and_resolution_methods():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    body = contract["properties"]["machina_workload_snapshot"]
    provider_ids = body["properties"]["provider_ids"]

    assert provider_ids["uniqueItems"] is True
    contains_constraints = {
        constraint["contains"]["properties"]["entity_type"]["const"]: constraint
        for constraint in provider_ids["allOf"]
    }
    assert set(contains_constraints) == {"competition", "season"}
    for entity_type in ("competition", "season"):
        constraint = contains_constraints[entity_type]
        assert constraint["contains"]["required"] == ["entity_type"]
        assert constraint["minContains"] == 1
        assert constraint["maxContains"] == 1

    provider_id = contract["$defs"]["providerId"]
    method_constraints = {
        frozenset(constraint["if"]["properties"]["entity_type"]["enum"]): constraint[
            "then"
        ]["properties"]["resolution_method"]["const"]
        for constraint in provider_id["allOf"]
    }
    assert method_constraints == {
        frozenset({"competition", "season"}): "declared",
        frozenset({"player", "team"}): "provider-native",
    }


def test_real_produced_snapshot_validates_against_public_schema():
    public_schema_validator().validate(project(load_connector()))


def test_public_schema_rejects_malformed_provider_resolution_method():
    snapshot = project(load_connector())
    snapshot["machina_workload_snapshot"]["provider_ids"][0]["resolution_method"] = (
        "provider-native"
    )

    with pytest.raises(ValidationError):
        public_schema_validator().validate(snapshot)


def test_public_schema_rejects_duplicate_provider_evidence():
    snapshot = project(load_connector())
    evidence = snapshot["machina_workload_snapshot"]["provider_ids"]
    evidence.append(deepcopy(evidence[0]))

    with pytest.raises(ValidationError):
        public_schema_validator().validate(snapshot)


def test_public_schema_rejects_missing_provider_evidence_field():
    snapshot = project(load_connector())
    snapshot["machina_workload_snapshot"]["provider_ids"][0].pop("evidence")

    with pytest.raises(ValidationError):
        public_schema_validator().validate(snapshot)


def test_runtime_refuses_duplicate_provider_evidence():
    module = load_connector()
    snapshot = project(module)
    evidence = snapshot["machina_workload_snapshot"]["provider_ids"]
    evidence.append(deepcopy(evidence[0]))

    assert "provider_ids must not contain duplicate evidence" in (
        module._snapshot_contract_findings(snapshot)
    )


@pytest.mark.parametrize("entity_type", ["competition", "season"])
def test_runtime_requires_exactly_one_declared_scope_evidence(entity_type):
    module = load_connector()
    snapshot = project(module)
    body = snapshot["machina_workload_snapshot"]
    body["provider_ids"] = [
        item for item in body["provider_ids"] if item["entity_type"] != entity_type
    ]

    assert "provider_ids must contain exactly one competition and one season item" in (
        module._snapshot_contract_findings(snapshot)
    )


@pytest.mark.parametrize("entity_type", ["competition", "season", "player", "team"])
def test_runtime_requires_evidence_for_every_emitted_surrogate(entity_type):
    module = load_connector()
    snapshot = project(module)
    body = snapshot["machina_workload_snapshot"]
    target = next(
        item for item in body["provider_ids"] if item["entity_type"] == entity_type
    )
    body["provider_ids"] = [
        item
        for item in body["provider_ids"]
        if (item["entity_type"], item["machina_id"])
        != (target["entity_type"], target["machina_id"])
    ]

    assert "provider evidence is missing for an emitted surrogate" in (
        module._snapshot_contract_findings(snapshot)
    )


def test_runtime_refuses_evidence_for_an_unemitted_surrogate():
    module = load_connector()
    snapshot = project(module)
    evidence = snapshot["machina_workload_snapshot"]["provider_ids"]
    extra = deepcopy(next(item for item in evidence if item["entity_type"] == "player"))
    extra.update(
        {
            "machina_id": surrogate_resolver("nflverse")("player", "00-0000000"),
            "provider_id": "00-0000000",
            "evidence": "injected.extra.player_id",
        }
    )
    evidence.append(extra)

    assert "provider evidence references an unemitted surrogate" in (
        module._snapshot_contract_findings(snapshot)
    )


def test_runtime_refuses_conflicting_evidence_for_one_surrogate():
    module = load_connector()
    snapshot = project(module)
    evidence = snapshot["machina_workload_snapshot"]["provider_ids"]
    conflict = deepcopy(
        next(item for item in evidence if item["entity_type"] == "player")
    )
    conflict.update(
        {
            "provider_id": "conflicting-player-id",
            "evidence": "injected.conflict.player_id",
        }
    )
    evidence.append(conflict)

    assert "provider evidence conflicts for an emitted surrogate" in (
        module._snapshot_contract_findings(snapshot)
    )


def test_exact_curie_mapping_and_custom_metrics_are_separate():
    module = load_connector()
    player = project(module)["machina_workload_snapshot"]["players"][0]

    assert player["statistics"] == {
        "spamfstat:receptionsLooks": "70",
        "spamfstat:receptionsTotal": "52",
        "spamfstat:rushesAttempts": "2",
    }
    assert set(player["statistics"]) == {
        "spamfstat:receptionsLooks",
        "spamfstat:receptionsTotal",
        "spamfstat:rushesAttempts",
    }
    for metric in (
        "wopr",
        "target_share",
        "air_yards_share",
        "rush_share",
        "opportunities",
        "rz_touches",
        "total_epa",
        "epa_per_opportunity",
        "target_share_delta",
        "wopr_delta",
        "rush_share_delta",
    ):
        assert metric in player["metrics"]
        assert metric not in player["statistics"]

    second = project(module)["machina_workload_snapshot"]["players"][1]
    assert "target_share" not in second["metrics"]
    assert "target_share_delta" not in second["metrics"]
    assert "unused_provider_payload" not in json.dumps(project(module))
    assert "must-not-leak" not in json.dumps(project(module))


def test_rights_provenance_capabilities_and_contract_validate():
    module = load_connector()
    snapshot = project(module)
    body = snapshot["machina_workload_snapshot"]

    assert body["rights"] == RIGHTS
    assert body["observed_at"] == OBSERVED_AT
    assert body["provenance"] == {
        "provider": "nflverse",
        "adapter": {"name": "nflreadpy", "version": "0.1.5"},
        "method_version": "workload-v0",
        "dependencies": DEPS,
        "source_refs": [
            {"kind": "dataset", "value": "nflverse-play-by-play"},
            {"kind": "library", "value": "nflreadpy"},
        ],
        "determinism": surrogate_resolver("nflverse").strategy,
    }
    assert all(
        "://" not in source_ref["value"]
        for source_ref in body["provenance"]["source_refs"]
    )

    capabilities = body["capabilities"]
    known = set(ALL_CAPABILITIES)
    assert set(capabilities) == {"present", "absent", "not_expressible"}
    assert set(capabilities["present"]) == {
        "participant.player_statistics",
        "provenance",
    }
    assert set(capabilities["present"]) | set(capabilities["absent"]) == known
    assert set(capabilities["not_expressible"]) <= set(capabilities["absent"])
    assert all(name in known for values in capabilities.values() for name in values)
    assert module._snapshot_contract_findings(snapshot) == []


def test_public_schema_pins_exact_runtime_capability_arrays():
    snapshot = project(load_connector())
    capabilities = snapshot["machina_workload_snapshot"]["capabilities"]
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    properties = contract["$defs"]["capabilities"]["properties"]

    for field in ("present", "absent", "not_expressible"):
        assert properties[field]["const"] == capabilities[field]


def test_public_schema_rejects_overclaimed_event_capability():
    snapshot = project(load_connector())
    capabilities = snapshot["machina_workload_snapshot"]["capabilities"]
    capabilities["absent"].remove("event.score")
    capabilities["present"].append("event.score")
    capabilities["present"].sort()

    with pytest.raises(ValidationError):
        public_schema_validator().validate(snapshot)


def test_snapshot_v1_refuses_capability_vocabulary_drift():
    module = load_connector()

    with pytest.raises(ValueError, match="capability vocabulary"):
        module._project_machina_workload_snapshot(
            deepcopy(REPORT),
            OBSERVED_AT,
            dict(DEPS),
            id_resolver=surrogate_resolver("nflverse"),
            rights=deepcopy(RIGHTS),
            capability_names=ALL_CAPABILITIES + ("event.invented",),
            contract_findings_fn=module._snapshot_contract_findings,
        )


def test_contract_guard_refuses_extra_dependency_property():
    module = load_connector()
    snapshot = project(module)
    snapshot["machina_workload_snapshot"]["provenance"]["dependencies"]["extra"] = "1"

    assert "provenance dependencies must match the closed contract" in (
        module._snapshot_contract_findings(snapshot)
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("player_display_name", 123, "name label"),
        ("opportunities", 72.5, "integer metrics"),
    ],
)
def test_projection_refuses_schema_invalid_injected_player_types(field, value, message):
    module = load_connector()
    report = deepcopy(REPORT)
    report["players"][0][field] = value

    with pytest.raises(ValueError, match=message):
        project(module, report=report)


def test_through_week_18_fails_closed_in_runtime_and_public_schema():
    module = load_connector()
    report = deepcopy(REPORT)
    report["through_week"] = 18

    with pytest.raises(
        ValueError, match="scope is missing a bounded native report coordinate"
    ):
        project(module, report=report)

    snapshot = project(module)
    snapshot["machina_workload_snapshot"]["scope"]["through_week"] = 18
    with pytest.raises(ValidationError):
        public_schema_validator().validate(snapshot)


def test_week_17_fantasy_scope_is_explicitly_documented():
    text = " ".join((PACKAGE / "SKILL.md").read_text(encoding="utf-8").split())

    assert "FANTASY_LAST_WEEK = 17" in text
    assert "Week 18 is part of the NFL schedule but outside this fantasy scope" in text
    assert (
        "`through_week: 18` fails closed in both runtime and the public schema" in text
    )


@pytest.mark.parametrize("observed_at", [None, "", "2026-08-15T12:30:00", "now"])
def test_missing_or_offsetless_observed_at_fails_closed(observed_at):
    module = load_connector()

    with pytest.raises(ValueError, match="observed_at"):
        project(module, observed_at=observed_at)


@pytest.mark.parametrize(
    "observed_at",
    [
        "2016-12-31T23:59:60Z",
        "2016-12-31T23:59:60+00:00",
        "2016-12-31T23:59:60-05:30",
        "2016-12-31T23:59:60.123+14:00",
    ],
)
def test_rfc3339_second_60_fails_closed_in_runtime_and_schema(observed_at):
    module = load_connector()

    with pytest.raises(ValueError, match="second 60 is not accepted"):
        project(module, observed_at=observed_at)

    snapshot = project(module)
    snapshot["machina_workload_snapshot"]["observed_at"] = observed_at
    with pytest.raises(ValidationError):
        public_schema_validator().validate(snapshot)


def test_timestamp_contract_documents_strict_seconds():
    text = " ".join((PACKAGE / "SKILL.md").read_text(encoding="utf-8").split())

    assert "seconds `00` through `59`" in text
    assert "Leap-second values with second `60` fail closed" in text


def test_rfc3339_z_is_accepted_by_runtime_and_public_schema():
    module = load_connector()
    observed_at = "2026-08-15T12:30:00Z"

    snapshot = project(module, observed_at=observed_at)

    assert snapshot["machina_workload_snapshot"]["observed_at"] == observed_at
    public_schema_validator().validate(snapshot)


@pytest.mark.parametrize(
    "observed_at",
    ["2026-08-15T12:30:00+05:30", "2026-08-15T12:30:00-04:00"],
)
def test_rfc3339_numeric_offsets_are_accepted_by_runtime_and_public_schema(observed_at):
    module = load_connector()

    snapshot = project(module, observed_at=observed_at)

    assert snapshot["machina_workload_snapshot"]["observed_at"] == observed_at
    public_schema_validator().validate(snapshot)


@pytest.mark.parametrize(
    "observed_at",
    [
        "2026-00-15T12:30:00Z",
        "2026-13-15T12:30:00+00:00",
        "2026-01-00T12:30:00-04:00",
        "2026-01-32T12:30:00Z",
        "2026-00-00T12:30:00+05:30",
        "2026-13-32T12:30:00Z",
        "2026-02-30T12:30:00Z",
        "2026-04-31T12:30:00+00:00",
    ],
)
def test_public_schema_rejects_invalid_months_and_days_without_format_checker(
    observed_at,
):
    module = load_connector()
    snapshot = project(module)
    snapshot["machina_workload_snapshot"]["observed_at"] = observed_at
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    with pytest.raises(ValidationError):
        Draft202012Validator(contract).validate(snapshot)


@pytest.mark.parametrize(
    "observed_at",
    [
        "2026-02-30T12:30:00+00:00",
        "2026-02-30T12:30:00Z",
        "2026-08-15T25:30:00+00:00",
        "2026-08-15T12:30:00+24:00",
        "2026-08-15T12:30:00+23:60",
    ],
)
def test_invalid_rfc3339_calendar_values_fail_closed(observed_at):
    module = load_connector()

    with pytest.raises(ValueError, match="observed_at"):
        project(module, observed_at=observed_at)

    snapshot = project(module)
    snapshot["machina_workload_snapshot"]["observed_at"] = observed_at
    with pytest.raises(ValidationError):
        public_schema_validator().validate(snapshot)


@pytest.mark.parametrize(
    "rights",
    [
        {},
        {
            "data_class": "open-public",
            "prototype_only": "true",
            "commercial_use": False,
        },
        {"data_class": "open-public", "prototype_only": True},
        {"data_class": "licensed", "prototype_only": True, "commercial_use": False},
        {"data_class": "open-public", "prototype_only": False, "commercial_use": True},
    ],
)
def test_missing_or_unreadable_rights_fail_closed(rights):
    module = load_connector()

    with pytest.raises(ValueError, match="rights"):
        project(module, rights=rights)


def test_contract_is_public_strict_json_schema():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert contract["$id"].endswith("machina-player-workload-snapshot-v1.json")
    assert contract["additionalProperties"] is False
    assert contract["required"] == ["machina_workload_snapshot"]
    body = contract["properties"]["machina_workload_snapshot"]
    assert body["properties"]["schema_version"]["const"] == (
        "machina-player-workload-snapshot/1"
    )
    assert body["additionalProperties"] is False


def test_players_are_unique_but_may_be_empty_in_public_schema():
    module = load_connector()
    empty_report = deepcopy(REPORT)
    empty_report["players"] = []
    empty_snapshot = project(module, report=empty_report)
    validator = public_schema_validator()

    players_schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))[
        "properties"
    ]["machina_workload_snapshot"]["properties"]["players"]
    assert players_schema["uniqueItems"] is True
    validator.validate(empty_snapshot)

    duplicate_snapshot = project(module)
    players = duplicate_snapshot["machina_workload_snapshot"]["players"]
    players.append(deepcopy(players[0]))
    with pytest.raises(ValidationError):
        validator.validate(duplicate_snapshot)


def test_package_registration_and_team_document_identity():
    connector = load_yaml(PACKAGE / "connectors" / "nfl-workload.yml")["connector"]
    commands = {command["value"] for command in connector["commands"]}
    assert "generate_machina_workload_snapshot" in commands

    install = load_yaml(PACKAGE / "_install.yml")["datasets"]
    install_paths = {item["path"] for item in install}
    assert "workflows/nfl-workload-machina-snapshot.yml" in install_paths

    skill = load_yaml(PACKAGE / "skill.yml")["skill"]
    assert any(
        reference["filename"] == "contracts/machina-player-workload-snapshot-v1.json"
        for reference in skill["references"]
    )
    assert any(
        workflow["name"] == "nfl-workload-machina-snapshot"
        for workflow in skill["workflows"]
    )

    report = load_yaml(PACKAGE / "workflows" / "nfl-workload-report.yml")["workflow"]
    latest = load_yaml(PACKAGE / "workflows" / "nfl-workload-latest.yml")["workflow"]
    assert report["inputs"]["team"] == "$.get('team', '')"
    assert report["tasks"][-1]["metadata"]["team"] == "$.get('team', 'ALL')"
    assert latest["inputs"]["team"] == "$.get('team', 'ALL')"
    assert latest["tasks"][0]["filters"]["metadata.team"] == "$.get('team', 'ALL')"
    legacy = latest["tasks"][1]
    assert legacy["name"] == "fetch-legacy-all-workload-report"
    assert "metadata.team" not in legacy["filters"]
    assert legacy["filters"]["value.team"] == "'ALL'"
    assert "$.get('team', 'ALL') == 'ALL'" in legacy["condition"]


def test_path_scoped_ci_reaches_every_snapshot_input():
    workflow = load_yaml(CI_PATH)
    pull_paths = workflow[True]["pull_request"]["paths"]
    push_paths = workflow[True]["push"]["paths"]

    assert pull_paths == push_paths
    for path in (
        "skills/nfl-workload/**",
        "tests/test_nfl_workload_package.py",
        "tests/test_nfl_workload_snapshot.py",
        ".github/workflows/test-nfl-workload.yml",
    ):
        assert path in pull_paths
    run_commands = "\n".join(
        str(step.get("run", ""))
        for job in workflow["jobs"].values()
        for step in job["steps"]
    )
    assert "tests/test_nfl_workload_snapshot.py" in run_commands
    assert "tests/test_nfl_workload_package.py" in run_commands
    assert "jsonschema==4.23.0" in run_commands
