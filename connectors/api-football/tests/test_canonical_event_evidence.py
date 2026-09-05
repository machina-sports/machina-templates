"""Adversarial contract tests for the canonical event-evidence dual-write.

Two properties are under test and neither is negotiable:

1. The five legacy ``api-football-event-*`` projections keep the exact bytes
   they had before the dual-write existed. ``fixtures/legacy-projection-golden.json``
   was captured from the producer at commit ``2f19aae``, before this file, and a
   single reordered key or added field fails the comparison.
2. The new ``canonical-event-evidence`` family says nothing the provider did not
   say. Every canonical identifier in it comes from the source event's crosswalk
   by exact equality — never from a URN prefix, never minted, never inferred from
   a provider allowlist — every unavailable endpoint stays unavailable, and the
   upsert identity is the tuple the store actually keys on.

The workflow expressions are evaluated the way ``machina-client-api`` evaluates
them (``core/workflow/context.py::_save_outputs`` for task outputs, where ``$.get``
reads the task *response* and ``$.context`` reads accumulated state, and
``core/workflow/runner/mapping.py::retrieve_from_context`` for workflow-level
outputs, where ``$.get`` reads accumulated state), and validated against the AST
whitelist in ``core/workflow/safe_eval.py``.
"""

from __future__ import annotations

import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

import pytest
import yaml

# jsonschema is not a dependency of this repository's runtime and is absent from a
# plain interpreter. The contract tests that need a validator skip without it; every
# other test in this file — legacy byte-identity, exact binding, unavailability,
# upsert identity, expression safety — runs regardless, because those are the
# properties that must hold on any machine.
try:  # pragma: no cover - import shape, not behaviour
    import jsonschema as _jsonschema

    jsonschema = _jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

requires_jsonschema = pytest.mark.skipif(
    jsonschema is None, reason="jsonschema is not installed on this interpreter"
)


CONNECTOR_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CONNECTOR_ROOT.parents[1]
MODULE_PATH = CONNECTOR_ROOT / "api-football-event-data.py"
ENRICH_WORKFLOW = CONNECTOR_ROOT / "api-football-enrich-event-data.yml"
SCHEMA_PATH = (
    REPO_ROOT
    / "connectors"
    / "machina-sports-canonical"
    / "machina-event-evidence-1.schema.json"
)
LEGACY_GOLDEN = Path(__file__).parent / "fixtures" / "legacy-projection-golden.json"
ADMISSIBILITY_PATH = (
    REPO_ROOT / "tools" / "iptc" / "canonical" / "data"
    / "official_statistic_admissibility_v1.json"
)

EVIDENCE_DOCUMENT_NAME = "canonical-event-evidence"
EVIDENCE_SCHEMA_VERSION = "machina-event-evidence/1"
EVIDENCE_KINDS = [
    "actions",
    "head_to_head",
    "lineups",
    "player_statistics",
    "team_statistics",
]
LEGACY_NAME_BY_KIND = {
    "actions": "api-football-event-actions",
    "lineups": "api-football-event-lineups",
    "team_statistics": "api-football-event-team-statistics",
    "player_statistics": "api-football-event-player-statistics",
    "head_to_head": "api-football-event-head-to-head",
}

# Reproduced from machina-client-api core/workflow/safe_eval.py. A local copy is
# how this suite runs on a checkout that does not have the runtime beside it; the
# copy is asserted to be a *subset* discipline — anything this list rejects, the
# runtime rejects too.
SAFE_EVAL_NODES = (
    ast.Expression,
    ast.Constant, ast.Tuple, ast.List, ast.Set, ast.Dict,
    ast.Name, ast.Load, ast.Store, ast.Attribute, ast.Subscript, ast.Slice,
    ast.Starred,
    ast.BoolOp, ast.And, ast.Or,
    ast.UnaryOp, ast.Not, ast.USub, ast.UAdd,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.FloorDiv,
    ast.Compare,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.Is, ast.IsNot, ast.In, ast.NotIn,
    ast.IfExp,
    ast.Call, ast.keyword,
    ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension,
)


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_projector():
    spec = importlib.util.spec_from_file_location("api_football_event_data", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_baseline():
    """The existing projection suite, reused rather than re-described.

    Its ``METADATA``/``project()`` are the exact identity fixture the legacy
    golden was captured under. Restating them here would let the two drift and
    turn the byte comparison into a comparison of two different inputs.
    """
    spec = importlib.util.spec_from_file_location(
        "api_football_event_data_projection_baseline",
        Path(__file__).parent / "test_event_data_projection.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASELINE = load_baseline()
EVENT_CODE = BASELINE.EVENT_CODE
HOME_TEAM_ID = BASELINE.HOME_TEAM_ID
AWAY_TEAM_ID = BASELINE.AWAY_TEAM_ID
SOURCE_DOCUMENT_ID = BASELINE.METADATA["source_event_document_id"]


def project(**overrides):
    return BASELINE.project(**overrides)


def evidence_documents(result):
    return result["data"]["evidence_documents"]


def evidence_by_kind(result):
    return {
        document["metadata"]["evidence_kind"]: document
        for document in evidence_documents(result)
    }


def legacy_by_name(result):
    return {document["name"]: document for document in result["data"]["documents"]}


def workflow():
    return yaml.safe_load(ENRICH_WORKFLOW.read_text(encoding="utf-8"))["workflow"]


def task(name):
    return next(item for item in workflow()["tasks"] if item["name"] == name)


def schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def owner_canonical_package():
    """The canonical package through the repository's own loader.

    ``tests/iptc_canonical_support.py`` prefers the installed distribution and
    falls back to the authoritative source bytes under the same import name. A
    bare ``import machina_sports_canonical`` here would pass on a machine that
    happens to have the wheel and fail on one that does not — which is a fact
    about the interpreter, not about the contract.
    """
    spec = importlib.util.spec_from_file_location(
        "iptc_canonical_support", REPO_ROOT / "tests" / "iptc_canonical_support.py"
    )
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)
    return support.canonical_package()


# --------------------------------------------------------------------------
# The runtime's own two evaluation semantics, reproduced
# --------------------------------------------------------------------------


def evaluate_response(expression, response, state=None):
    """``core/workflow/context.py::_save_outputs`` — a *task's* ``outputs`` block.

    ``$.get`` reads the task response; ``$.context`` reads accumulated state. The
    runtime calls bare ``eval`` with a globals dict that carries no
    ``__builtins__`` key, so Python injects the full builtins — reproduced here
    rather than narrowed, because a test with fewer builtins than the runtime
    would reject expressions the runtime accepts.
    """
    if expression.strip() == "$":
        return response
    prepared = expression.replace("$.context", "context").replace("$.get", "response.get")
    return eval(  # noqa: S307 - mirrors the runtime under test
        prepared.replace("\n", ""),
        {"context": state if state is not None else {}, "response": response,
         "json": json},
    )


def evaluate_state(expression, state):
    """``retrieve_from_context`` (workflow outputs, task inputs) and
    ``_evaluate_condition`` (task conditions): ``$.get`` reads accumulated state."""
    return eval(  # noqa: S307 - mirrors the runtime under test
        expression.replace("$.get", "context.get").replace("\n", ""),
        {"context": state, "json": json},
    )


# --------------------------------------------------------------------------
# The contract document itself
# --------------------------------------------------------------------------


@requires_jsonschema
def test_the_schema_file_is_a_valid_json_schema():
    jsonschema.Draft202012Validator.check_schema(schema())


def test_the_schema_pins_the_contract_version_and_document_name():
    document = schema()
    assert document["properties"]["name"]["const"] == EVIDENCE_DOCUMENT_NAME
    assert (
        document["properties"]["value"]["properties"]["schema_version"]["const"]
        == EVIDENCE_SCHEMA_VERSION
    )


def test_the_schema_keys_the_upsert_identity_and_nothing_else():
    """The store upserts on the whole ``metadata`` subdocument (``document_update_bulk``
    filters ``{"metadata": metadata, "name": name}``). A volatile field in there is
    a new document per refresh, so the schema closes the object to the identity."""
    metadata = schema()["properties"]["metadata"]
    assert metadata["additionalProperties"] is False
    assert list(metadata["properties"]) == [
        "event_code",
        "source_event_document_id",
        "provider_namespace",
        "evidence_kind",
    ]
    assert sorted(metadata["required"]) == sorted(metadata["properties"])


def test_the_schema_binds_season_form_to_the_owner_longitudinal_contract():
    """``season_form`` is the longitudinal kind and it has an owner. This
    contract names the owner's constant rather than minting a second one; no
    Phase 1 producer emits the kind."""
    longitudinal = owner_canonical_package().LONGITUDINAL_SCHEMA_VERSION

    document = schema()
    assert document["properties"]["metadata"]["properties"]["evidence_kind"] == {
        "$ref": "#/$defs/evidence_kind"
    }
    assert "season_form" in document["$defs"]["evidence_kind"]["enum"]
    binding = next(
        rule
        for rule in document["allOf"]
        if rule["if"]["properties"]["metadata"]["properties"]["evidence_kind"]["const"]
        == "season_form"
    )
    assert (
        binding["then"]["properties"]["value"]["properties"][
            "longitudinal_schema_version"
        ]["const"]
        == longitudinal
    )


def test_the_schema_admits_only_owner_published_statistic_schemes():
    """A CURIE this repository invented would validate against a free-text field.
    The pattern is the fence; the admissibility test below is the gate."""
    statistic = schema()["$defs"]["statistic"]
    assert statistic["properties"]["curie"]["pattern"]
    assert statistic["additionalProperties"] is False


# --------------------------------------------------------------------------
# Legacy compatibility
# --------------------------------------------------------------------------


def test_the_five_legacy_documents_are_byte_identical_to_the_recorded_baseline():
    recorded = json.loads(LEGACY_GOLDEN.read_text(encoding="utf-8"))
    produced = project()["data"]["documents"]
    assert json.dumps(produced, ensure_ascii=False) == json.dumps(
        recorded, ensure_ascii=False
    )


def test_the_golden_is_what_the_reviewed_producer_actually_emitted():
    """A golden captured from already-edited code proves nothing.

    This re-runs the projection against the producer as the *last commit* has
    it and compares. It is the only check that can catch a golden regenerated
    to match a regression instead of the other way round. Skipped where the git
    object is not reachable — a checkout without history is not a failure.
    """
    completed = subprocess.run(
        ["git", "show", "HEAD:connectors/api-football/api-football-event-data.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if completed.returncode != 0:
        pytest.skip("producer not reachable at HEAD")

    committed = Path(tempfile.mkdtemp()) / "api-football-event-data.py"
    committed.write_text(completed.stdout, encoding="utf-8")
    baseline = load_baseline()
    baseline.MODULE_PATH = committed

    recorded = json.loads(LEGACY_GOLDEN.read_text(encoding="utf-8"))
    assert baseline.project()["data"]["documents"] == recorded


def test_the_legacy_result_keys_the_workflow_reads_are_unchanged():
    data = project()["data"]
    assert data["valid"] is True
    assert data["workflow_status"] == "executed"
    assert data["requirements_unavailable"] == []
    assert data["diagnostics"] == {}
    assert [document["name"] for document in data["documents"]] == [
        LEGACY_NAME_BY_KIND[kind]
        for kind in (
            "actions",
            "lineups",
            "team_statistics",
            "player_statistics",
            "head_to_head",
        )
    ]


# --------------------------------------------------------------------------
# The canonical family
# --------------------------------------------------------------------------


def test_the_dual_write_emits_exactly_the_five_kinds_the_provider_supplies():
    documents = evidence_documents(project())
    assert [document["name"] for document in documents] == [EVIDENCE_DOCUMENT_NAME] * 5
    assert sorted(document["metadata"]["evidence_kind"] for document in documents) == (
        EVIDENCE_KINDS
    )


@requires_jsonschema
def test_every_evidence_document_validates_against_the_contract():
    validator = jsonschema.Draft202012Validator(schema())
    for document in evidence_documents(project()):
        errors = sorted(validator.iter_errors(document), key=str)
        assert errors == [], (document["metadata"]["evidence_kind"], errors)


def test_the_upsert_identity_is_event_source_provider_and_kind():
    for kind, document in evidence_by_kind(project()).items():
        assert list(document["metadata"]) == [
            "event_code",
            "source_event_document_id",
            "provider_namespace",
            "evidence_kind",
        ]
        assert document["metadata"] == {
            "event_code": EVENT_CODE,
            "source_event_document_id": SOURCE_DOCUMENT_ID,
            "provider_namespace": "api-football",
            "evidence_kind": kind,
        }


def test_a_retry_is_idempotent_on_identity_and_still_refreshes_the_observation():
    first = evidence_by_kind(project())
    later = {
        key: value.replace("20:01:0", "21:01:0")
        for key, value in BASELINE.OBSERVED_AT.items()
    }
    second = evidence_by_kind(project(endpoint_observed_at=later))

    for kind in EVIDENCE_KINDS:
        assert first[kind]["metadata"] == second[kind]["metadata"]
        assert first[kind]["value"]["projection_key"] == (
            second[kind]["value"]["projection_key"]
        )
        assert first[kind]["value"]["observed_at"] != (
            second[kind]["value"]["observed_at"]
        )


def test_the_five_identities_do_not_collide_with_each_other():
    documents = evidence_documents(project())
    identities = [json.dumps(document["metadata"], sort_keys=True) for document in documents]
    keys = [document["value"]["projection_key"] for document in documents]
    assert len(set(identities)) == 5
    assert len(set(keys)) == 5


def test_the_canonical_identity_does_not_collide_with_the_legacy_projection_key():
    """Both families are keyed off the same event and source document. If the
    canonical key were the legacy key, Phase 5's deletion of the legacy family
    would delete the canonical one with it."""
    result = project()
    legacy_keys = {
        document["value"]["@id"] for document in result["data"]["documents"]
    }
    canonical_keys = {
        document["value"]["projection_key"] for document in evidence_documents(result)
    }
    assert legacy_keys.isdisjoint(canonical_keys)


# --------------------------------------------------------------------------
# Exact binding: source, event, provider, entity, time, rights, capability
# --------------------------------------------------------------------------


def test_every_document_binds_the_exact_source_event_and_endpoint():
    for kind, document in evidence_by_kind(project()).items():
        value = document["value"]
        assert value["event_id"] == EVENT_CODE
        assert value["event_code"] == EVENT_CODE
        assert value["source_event_document_id"] == SOURCE_DOCUMENT_ID
        assert value["kind"] == kind
        assert {"kind": "source-event-document", "value": SOURCE_DOCUMENT_ID} in (
            value["provenance"]["source_refs"]
        )
        endpoints = [
            ref["value"]
            for ref in value["provenance"]["source_refs"]
            if ref["kind"] == "endpoint-class"
        ]
        assert endpoints == [
            BASELINE.ENDPOINTS[LEGACY_NAME_BY_KIND[kind]]
        ]


def test_the_provider_block_is_copied_from_the_source_event_not_asserted_here():
    source_provider = BASELINE.METADATA["source_event_provenance"]["provider"]
    for document in evidence_documents(project()):
        assert document["value"]["provider"] == source_provider
        assert document["metadata"]["provider_namespace"] == source_provider["namespace"]
        assert "raw" not in document["value"]["provider"]


def test_each_document_carries_the_observation_time_of_its_own_endpoint():
    documents = evidence_by_kind(project())
    observed = {kind: documents[kind]["value"]["observed_at"] for kind in EVIDENCE_KINDS}
    expected = {
        "actions": BASELINE.OBSERVED_AT["events"],
        "lineups": BASELINE.OBSERVED_AT["lineups"],
        "team_statistics": BASELINE.OBSERVED_AT["team_statistics"],
        "player_statistics": BASELINE.OBSERVED_AT["player_statistics"],
        "head_to_head": BASELINE.OBSERVED_AT["head_to_head"],
    }
    assert observed == expected
    assert len(set(observed.values())) == 5


def test_rights_are_the_source_events_rights_and_say_where_they_came_from():
    for document in evidence_documents(project()):
        rights = document["value"]["rights"]
        assert rights["terms"] == BASELINE.METADATA["source_event_rights"]
        assert rights["source_event_rights_ref"] == {
            "kind": "source-event-document",
            "value": SOURCE_DOCUMENT_ID,
            "path": "value.machina_sports_schema.rights",
        }


def test_the_capability_binding_is_the_legacy_one_unrenamed():
    result = project()
    legacy = legacy_by_name(result)
    for kind, document in evidence_by_kind(result).items():
        assert document["value"]["projection_capability"] == (
            legacy[LEGACY_NAME_BY_KIND[kind]]["metadata"]["projection_capability"]
        )
        assert document["value"]["status"] == (
            legacy[LEGACY_NAME_BY_KIND[kind]]["metadata"]["status"]
        )


def test_the_request_context_that_produced_each_document_travels_with_it():
    documents = evidence_by_kind(project())
    assert documents["head_to_head"]["value"]["request_context"] == (
        BASELINE.REQUEST_CONTEXTS["head_to_head"]
    )
    assert documents["actions"]["value"]["request_context"] == (
        BASELINE.REQUEST_CONTEXTS["events"]
    )


# --------------------------------------------------------------------------
# Facts agree with the legacy family and invent no identity
# --------------------------------------------------------------------------


def test_the_two_families_describe_the_same_facts():
    result = project()
    legacy = legacy_by_name(result)
    canonical = evidence_by_kind(result)

    for kind in ("actions", "lineups", "team_statistics", "head_to_head"):
        assert len(canonical[kind]["value"]["facts"]) == len(
            legacy[LEGACY_NAME_BY_KIND[kind]]["value"]["facts"]
        )

    # player_statistics is the one kind whose canonical grain differs on purpose:
    # the legacy fact is per team, the claim is per athlete participation.
    legacy_players = sum(
        len(fact["players"])
        for fact in legacy["api-football-event-player-statistics"]["value"]["facts"]
    )
    assert len(canonical["player_statistics"]["value"]["facts"]) == legacy_players


def test_every_canonical_team_id_came_from_the_crosswalk():
    canonical = evidence_by_kind(project())
    seen = set()
    for document in canonical.values():
        for fact in document["value"]["facts"]:
            for key in ("team_id", "home_team_id", "away_team_id"):
                if key in fact:
                    seen.add(fact[key])
    assert seen == {HOME_TEAM_ID, AWAY_TEAM_ID}


def test_an_athlete_absent_from_the_crosswalk_gets_no_canonical_identifier():
    """The source event of this fixture crosswalks no players. A ``urn:machina:sports:player:``
    prefix check would happily accept a minted id here; exact crosswalk equality
    refuses to produce one at all."""
    for document in evidence_documents(project()):
        for fact in document["value"]["facts"]:
            assert "athlete_id" not in fact
            assert "assist_athlete_id" not in fact
            for member in fact.get("starting", []) + fact.get("substitutes", []):
                assert "athlete_id" not in member


def test_a_crosswalked_athlete_is_carried_through_by_exact_equality():
    crosswalk = deepcopy(BASELINE.METADATA["provider_ids"]) + [
        {
            "entity_type": "athlete",
            "provider_namespace": "api-football",
            "provider_id": "101",
            "machina_id": "urn:machina:sports:athlete:canonical-101",
        }
    ]
    canonical = evidence_by_kind(project(provider_ids=crosswalk))
    athletes = {
        fact["athlete_id"]
        for fact in canonical["player_statistics"]["value"]["facts"]
        if "athlete_id" in fact
    }
    assert athletes == {"urn:machina:sports:athlete:canonical-101"}


def test_every_fact_declares_what_it_claims_and_about_what():
    expected = {
        "actions": ("action", "event-action"),
        "lineups": ("lineup", "team-participation"),
        "team_statistics": ("team_statistics", "team-participation"),
        "player_statistics": ("player_statistics", "athlete-participation"),
        "head_to_head": ("prior_meeting", "prior-meeting"),
    }
    for kind, document in evidence_by_kind(project()).items():
        claims = {
            (fact["claim_type"], fact["claim_scope"])
            for fact in document["value"]["facts"]
        }
        assert claims == {expected[kind]}


def test_provider_identifiers_travel_as_evidence_and_never_as_identity():
    for document in evidence_documents(project()):
        for fact in document["value"]["facts"]:
            assert fact["provider_evidence"]
            # One quarantine key, and every provider identifier inside it. A
            # `provider_team_id` beside `team_id` is how a consumer starts
            # keying on provider shape again without noticing.
            assert {key for key in fact if key.startswith("provider_")} == (
                {"provider_evidence"}
            )
            for member in fact.get("starting", []) + fact.get("substitutes", []):
                assert {key for key in member if key.startswith("provider_")} == (
                    {"provider_evidence"}
                )


# --------------------------------------------------------------------------
# Statistics: the owner's vocabulary or nothing
# --------------------------------------------------------------------------


def test_the_producer_owns_no_iptc_statistic_vocabulary():
    """The seam suite forbids IPTC property literals in the canonical connector
    for the same reason: two places that know what ``spsocstat:shotsTotal`` means
    is the drift this programme exists to remove."""
    source = MODULE_PATH.read_text(encoding="utf-8")
    for scheme in ("spsocstat:", "spamfstat:", "spbkbstat:", "spbslstat:", "spcorstat:"):
        assert scheme not in source


def test_every_emitted_statistic_curie_is_admitted_by_the_owners_manifest():
    admissibility = json.loads(ADMISSIBILITY_PATH.read_text(encoding="utf-8"))
    admitted = {
        (entry["curie"], entry["participation_kind"])
        for entry in admissibility["entries"]
        if entry.get("admitted")
    }
    kind_of_scope = {
        "team-participation": "team",
        "athlete-participation": "individual",
    }
    for document in evidence_documents(project()):
        for fact in document["value"]["facts"]:
            for statistic in fact.get("statistics", []):
                key = (statistic["curie"], kind_of_scope[fact["claim_scope"]])
                assert key in admitted, key


def test_non_expressible_provider_metrics_are_labelled_by_the_provider_and_bounded():
    canonical = evidence_by_kind(project())
    team = canonical["team_statistics"]["value"]["facts"][0]
    assert team["statistics"] == []
    assert {"provider_label": "Shots on Goal", "value": 3} in team["metrics"]

    player = canonical["player_statistics"]["value"]["facts"][0]
    assert player["statistics"] == []
    assert {"provider_label": "games.minutes", "value": 31} in player["metrics"]
    assert all(
        not isinstance(metric["value"], (dict, list)) for metric in player["metrics"]
    )


def test_two_grouped_rows_that_compare_equal_keep_distinct_ordinals():
    """Two players with identical measurements are still two measurements.

    An equality-based lookup gives both rows ordinal 0, so the second row's
    labels collide with the first's and one player's minutes silently overwrite
    the other's downstream. The same dict appearing twice is the harder case:
    it defeats an identity-based lookup too. The ordinal has to follow the
    row's position, not its value and not its object."""
    row = {"games": {"minutes": 31}}
    metrics = load_projector()._metrics([row, row])
    assert metrics == [
        {"provider_label": "0.games.minutes", "value": 31},
        {"provider_label": "1.games.minutes", "value": 31},
    ]


def test_a_label_value_row_with_a_non_scalar_value_yields_no_metric():
    """API-Football's fixture-statistics rows are {type, value}. If a value ever
    arrives as a container, the row has no scalar measurement in it — and reading
    its keys as if they were labels would mint `type` and `value.*` metrics that
    the provider never reported."""
    payload = deepcopy(BASELINE.load_payload())
    payload["team_statistics"]["response"][0]["statistics"] = [
        {"type": "Ball Possession", "value": {"percent": 61}},
        {"type": "Shots on Goal", "value": 3},
    ]
    fact = evidence_by_kind(project(payload=payload))["team_statistics"]["value"][
        "facts"
    ][0]
    assert fact["metrics"] == [{"provider_label": "Shots on Goal", "value": 3}]
    assert fact["provider_evidence"]["statistics"][0] == {
        "type": "Ball Possession",
        "value": {"percent": 61},
    }


def test_a_nested_provider_metric_is_never_flattened_past_one_level():
    payload = deepcopy(BASELINE.load_payload())
    payload["player_statistics"]["response"][0]["players"][0]["statistics"] = [
        {"passes": {"detail": {"progressive": 4}, "total": 30}}
    ]
    fact = evidence_by_kind(project(payload=payload))["player_statistics"]["value"][
        "facts"
    ][0]
    labels = {metric["provider_label"] for metric in fact["metrics"]}
    assert labels == {"passes.total"}
    assert fact["provider_evidence"]["statistics"] == [
        {"passes": {"detail": {"progressive": 4}, "total": 30}}
    ]


# --------------------------------------------------------------------------
# Adversarial: wrong event, wrong provider, failure, unavailability
# --------------------------------------------------------------------------


def test_a_fixture_that_maps_to_a_different_event_produces_no_evidence():
    crosswalk = deepcopy(BASELINE.METADATA["provider_ids"])
    crosswalk[0]["machina_id"] = "urn:machina:sports:event:canonical-9999"
    result = project(provider_ids=crosswalk)
    assert result["data"]["valid"] is False
    assert result["data"]["documents"] == []
    assert result["data"].get("evidence_documents", []) == []


def test_a_source_event_from_another_provider_produces_no_evidence():
    result = project(
        source_event_provenance={
            "provider": {"namespace": "sportradar-soccer", "family": "licensed"},
            "source_refs": [{"kind": "endpoint-class", "value": "sportradar/fixtures"}],
        }
    )
    assert result["data"]["valid"] is False
    assert result["data"].get("evidence_documents", []) == []


def test_a_fixture_response_for_another_fixture_produces_no_evidence():
    payload = deepcopy(BASELINE.load_payload())
    payload["fixture"]["fixture"]["id"] = 7002
    result = project(payload=payload)
    assert result["data"]["valid"] is False
    assert result["data"].get("evidence_documents", []) == []


def test_an_unavailable_endpoint_stays_unavailable_in_both_families():
    payload = deepcopy(BASELINE.load_payload())
    payload["lineups"] = {
        "parameters": {"fixture": "7001"},
        "errors": ["Too many requests"],
        "results": 0,
        "response": [],
    }
    result = project(payload=payload)
    legacy = legacy_by_name(result)["api-football-event-lineups"]
    canonical = evidence_by_kind(result)["lineups"]

    assert legacy["metadata"]["status"] == "unavailable"
    assert canonical["value"]["status"] == "unavailable"
    assert canonical["value"]["facts"] == []
    assert canonical["value"]["unavailable_reason"] == legacy["value"]["unavailable_reason"]
    assert result["data"]["workflow_status"] == "partial"


def test_a_missing_endpoint_response_fabricates_nothing():
    payload = deepcopy(BASELINE.load_payload())
    payload["team_statistics"] = None
    canonical = evidence_by_kind(project(payload=payload))["team_statistics"]
    assert canonical["value"]["status"] == "unavailable"
    assert canonical["value"]["facts"] == []
    assert canonical["value"]["unavailable_reason"]


def test_an_available_document_never_carries_an_unavailable_reason():
    for document in evidence_documents(project()):
        assert document["value"]["status"] == "available"
        assert "unavailable_reason" not in document["value"]


def test_a_head_to_head_row_outside_the_exact_pair_makes_the_kind_unavailable():
    payload = deepcopy(BASELINE.load_payload())
    payload["head_to_head"]["response"][1]["teams"]["home"]["id"] = 99
    canonical = evidence_by_kind(project(payload=payload))["head_to_head"]
    assert canonical["value"]["status"] == "unavailable"
    assert canonical["value"]["facts"] == []


def test_every_endpoint_unavailable_still_emits_five_documents():
    payload = deepcopy(BASELINE.load_payload())
    for key in ("events", "lineups", "team_statistics", "player_statistics", "head_to_head"):
        payload[key] = {
            "parameters": payload[key]["parameters"],
            "errors": [],
            "results": 0,
            "response": [],
        }
    result = project(payload=payload)
    documents = evidence_documents(result)
    assert len(documents) == 5
    assert {document["value"]["status"] for document in documents} == {"unavailable"}
    assert result["data"]["workflow_status"] == "unavailable"


# --------------------------------------------------------------------------
# The workflow that persists it
# --------------------------------------------------------------------------


def test_the_projection_task_exposes_both_families_to_the_workflow():
    outputs = task("project-event-data")["outputs"]
    result = project()["data"]
    assert evaluate_response(outputs["evidence-documents"], result) == (
        result["evidence_documents"]
    )


def test_the_dual_write_task_upserts_the_canonical_family_by_identity():
    save = task("save-canonical-event-evidence")
    assert save["config"]["action"] == "bulk-update"
    assert save["config"]["embed-vector"] is False
    assert save["document_name"] == "'{0}'".format(EVIDENCE_DOCUMENT_NAME)

    result = project()["data"]
    items = evaluate_response(
        task("project-event-data")["outputs"]["evidence-items"], result
    )
    state = {"evidence-items": items}
    # document_update_bulk pops `metadata` off each item and stores the rest as
    # `value`, filtering on {"metadata": metadata, "name": name}.
    assert len(items) == 5
    for item in items:
        metadata = dict(item["metadata"])
        assert list(metadata) == [
            "event_code",
            "source_event_document_id",
            "provider_namespace",
            "evidence_kind",
        ]
    assert evaluate_state(save["documents"]["items"], state) == items


def test_the_dual_write_only_runs_when_all_five_documents_were_built():
    condition = task("save-canonical-event-evidence")["condition"]
    complete = {"projection-valid": True, "evidence-items": [{}] * 5}
    assert evaluate_state(condition, complete) is True
    for broken in (
        {"projection-valid": False, "evidence-items": [{}] * 5},
        {"projection-valid": True, "evidence-items": [{}] * 4},
        {"projection-valid": True},
    ):
        assert evaluate_state(condition, broken) is not True


def test_the_persistence_receipt_is_what_the_store_echoed_back():
    outputs = task("save-canonical-event-evidence")["outputs"]
    stored = {
        "documents": [
            {
                "name": EVIDENCE_DOCUMENT_NAME,
                "metadata": document["metadata"],
                "value": document["value"],
            }
            for document in evidence_documents(project())
        ]
    }
    assert evaluate_response(outputs["evidence-saved-kinds"], stored) == EVIDENCE_KINDS

    partial = {"documents": stored["documents"][:3]}
    assert evaluate_response(outputs["evidence-saved-kinds"], partial) != EVIDENCE_KINDS
    foreign = {"documents": [{"name": "something-else", "metadata": {"evidence_kind": "actions"}}]}
    assert evaluate_response(outputs["evidence-saved-kinds"], foreign) == []


def test_a_partial_persistence_is_reported_as_a_failed_workflow():
    outputs = workflow()["outputs"]
    executed = {
        "projection-valid": True,
        "projections-saved": True,
        "projection-workflow-status": "executed",
        "evidence-saved-kinds": EVIDENCE_KINDS,
    }
    assert evaluate_state(outputs["workflow-status"], executed) == "executed"
    assert evaluate_state(outputs["evidence-dual-write"], executed) is True

    for partial in (
        {**executed, "evidence-saved-kinds": EVIDENCE_KINDS[:4]},
        {**executed, "evidence-saved-kinds": []},
        {key: value for key, value in executed.items() if key != "evidence-saved-kinds"},
    ):
        assert evaluate_state(outputs["workflow-status"], partial) == "failed"
        assert evaluate_state(outputs["evidence-dual-write"], partial) is False


def test_a_failed_legacy_write_still_fails_the_workflow():
    outputs = workflow()["outputs"]
    state = {
        "projection-valid": True,
        "projections-saved": False,
        "projection-workflow-status": "executed",
        "evidence-saved-kinds": EVIDENCE_KINDS,
    }
    assert evaluate_state(outputs["workflow-status"], state) == "failed"


def test_the_dual_write_does_not_disturb_the_five_legacy_save_tasks():
    names = [item["name"] for item in workflow()["tasks"]]
    legacy = [
        "save-actions",
        "save-lineups",
        "save-team-statistics",
        "save-player-statistics",
        "save-head-to-head",
    ]
    assert [name for name in names if name in legacy] == legacy
    assert names.index("save-canonical-event-evidence") > names.index("save-head-to-head")
    for name in legacy:
        assert task(name)["config"]["action"] == "update"


# --------------------------------------------------------------------------
# Expression safety, evaluated the way the runtime evaluates it
# --------------------------------------------------------------------------


def workflow_expressions():
    found = []

    def walk(node, path):
        if isinstance(node, dict):
            for key, value in node.items():
                walk(value, path + [str(key)])
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, path + [str(index)])
        elif isinstance(node, str) and ("$." in node or path[-1] == "condition"):
            found.append(("/".join(path), node))

    walk(workflow(), [])
    return found


def test_every_expression_in_the_enrich_workflow_survives_the_runtime_whitelist():
    expressions = workflow_expressions()
    assert len(expressions) > 40
    for path, expression in expressions:
        # core/workflow/context.py rewrites these before eval and strips newlines.
        prepared = (
            expression.replace("$.context", "context")
            .replace("$.get", "response.get")
            .replace("\n", "")
        )
        if prepared.strip() == "$":
            continue
        tree = ast.parse(prepared, mode="eval")
        for node in ast.walk(tree):
            assert isinstance(node, SAFE_EVAL_NODES), (path, type(node).__name__)
            if isinstance(node, ast.Attribute):
                assert not node.attr.startswith("_"), (path, node.attr)


def test_no_expression_relies_on_a_newline_the_runtime_strips():
    for path, expression in workflow_expressions():
        collapsed = expression.replace("\n", "")
        if "\n" in expression:
            ast.parse(collapsed.strip() or "None", mode="eval")


@pytest.mark.parametrize(
    "name",
    ["evidence-documents", "evidence-items"],
)
def test_the_new_projection_outputs_are_not_none_so_the_runtime_stores_them(name):
    """``_save_outputs`` drops any output whose expression evaluates to ``None``.
    An output that silently vanishes reads downstream as 'never ran'."""
    value = evaluate_response(
        task("project-event-data")["outputs"][name], project()["data"]
    )
    assert value is not None
    assert len(value) == 5
