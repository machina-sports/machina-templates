"""Regression tests for API-Football workflow safety and observability."""

from pathlib import Path

import yaml


CONNECTOR_ROOT = Path(__file__).resolve().parents[1]
SAFE_BUILTINS = {
    "all": all,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "str": str,
    "tuple": tuple,
}


def load_yaml(relative_path):
    return yaml.safe_load(
        (CONNECTOR_ROOT / relative_path).read_text(encoding="utf-8")
    )


def evaluate(expression, context):
    namespace = {"__builtins__": {}, **SAFE_BUILTINS, "context": context}
    return eval(expression.replace("$.get", "context.get"), namespace, namespace)


def task(workflow, name):
    return next(item for item in workflow["tasks"] if item["name"] == name)


def evaluate_outputs(outputs, context):
    return {key: evaluate(expression, context) for key, expression in outputs.items()}


def provider_fixture(fixture_id=1390823):
    return {
        "fixture": {
            "id": fixture_id,
            "date": "2025-08-17T19:30:00+00:00",
            "status": {"short": "FT"},
        },
        "league": {"id": 140, "name": "La Liga", "season": 2025},
        "teams": {
            "home": {"id": 540, "name": "Espanyol"},
            "away": {"id": 530, "name": "Atletico Madrid"},
        },
        "goals": {"home": 2, "away": 1},
        "score": {"fulltime": {"home": 2, "away": 1}},
    }


def test_get_fixtures_exposes_bounded_provider_diagnostics():
    workflow = load_yaml("get-fixtures.yml")["workflow"]
    connector_outputs = task(workflow, "api-football-get-fixtures")["outputs"]
    payload = {
        "response": [provider_fixture(i) for i in range(150)],
        "errors": {f"error-{i}": "provider error" for i in range(30)},
        "results": 150,
    }

    state = evaluate_outputs(connector_outputs, payload)
    outputs = evaluate_outputs(workflow["outputs"], state)

    assert len(outputs["response"]) == 100
    assert len(outputs["errors"]) == 20
    assert outputs["results"] == 150
    assert outputs["workflow-status"] == "failed"


def test_get_fixtures_rejects_an_invalid_response_shape():
    workflow = load_yaml("get-fixtures.yml")["workflow"]
    connector_outputs = task(workflow, "api-football-get-fixtures")["outputs"]

    state = evaluate_outputs(
        connector_outputs,
        {"response": {"unexpected": "shape"}, "errors": [], "results": 1},
    )
    outputs = evaluate_outputs(workflow["outputs"], state)

    assert outputs["response"] == []
    assert outputs["workflow-status"] == "failed"


def test_sync_fixtures_fails_closed_on_errors_and_invalid_payloads():
    workflow = load_yaml("sync-fixtures.yml")["workflow"]
    connector_outputs = task(workflow, "api-football-get-fixtures")["outputs"]
    canonicalize = task(workflow, "canonicalize-fixtures")
    save = task(workflow, "task-bulk-save-fixtures")

    for payload in (
        {"response": [provider_fixture()], "errors": ["quota"], "results": 1},
        {"response": {}, "errors": [], "results": 1},
        {"response": [provider_fixture()], "errors": [], "results": 2},
    ):
        state = evaluate_outputs(connector_outputs, payload)
        with_state = {
            **state,
            "canonical-envelopes": [],
            "canonical-envelope-validity": [],
        }
        assert evaluate(workflow["outputs"]["workflow-status"], with_state) == "failed"
        assert not evaluate(canonicalize["condition"], with_state)
        assert not evaluate(save["condition"], {**with_state, "fixtures": []})


def test_sync_fixtures_reports_executed_only_after_complete_canonicalization():
    workflow = load_yaml("sync-fixtures.yml")["workflow"]
    fixture = provider_fixture()
    block = {
        "provenance": {
            "provider": {"namespace": "api-football", "family": "licensed"}
        },
        "rights": {
            "data_class": "licensed-provider-example-fixture",
            "prototype_only": True,
            "commercial_use": False,
        },
    }
    context = {
        "provider-response-valid": True,
        "provider-errors": [],
        "provider-fixtures": [fixture],
        "fixtures": [{"@id": "urn:apifootball:sport_event:1390823"}],
        "canonical-envelopes": [{"machina_sports_schema": block}],
        "canonical-envelope-validity": [True],
    }

    assert evaluate(workflow["outputs"]["workflow-status"], context) == "executed"
    assert evaluate(
        workflow["outputs"]["workflow-status"], {**context, "fixtures": []}
    ) == "failed"


def test_sync_fixtures_uses_canonical_connector_for_each_exact_fixture():
    workflow = load_yaml("sync-fixtures.yml")["workflow"]
    install = load_yaml("_install.yml")
    canonicalize = task(workflow, "canonicalize-fixtures")
    fixture = provider_fixture()

    assert all(item.get("type") != "mapping" for item in workflow["tasks"])
    assert all(
        item.get("name") != "iptc-api-football-event-mapping"
        for item in workflow["tasks"]
    )
    assert canonicalize["connector"] == {
        "name": "machina-sports-canonical",
        "command": "canonicalize_event",
    }
    assert [
        item
        for item in install["datasets"]
        if item.get("type") == "connector"
        and item.get("path")
        == "../machina-sports-canonical/machina-sports-canonical.yml"
    ] == [
        {
            "type": "connector",
            "path": "../machina-sports-canonical/machina-sports-canonical.yml",
        }
    ]
    assert canonicalize["inputs"]["provider"] == "'api-football'"
    assert evaluate(
        canonicalize["inputs"]["payload"], {"provider-fixture": fixture}
    ) is fixture
    assert evaluate(
        canonicalize["inputs"]["observed_at"],
        {"observed_at": "2026-08-22T12:00:00+00:00"},
    ) == "2026-08-22T12:00:00+00:00"
    assert canonicalize["foreach"]["value"] == "$.get('provider-fixtures', [])"
    assert canonicalize["foreach"]["limit"] == 1000
    assert "concurrent" not in canonicalize["foreach"]


def test_sync_fixtures_builds_validated_canonical_event_documents():
    workflow = load_yaml("sync-fixtures.yml")["workflow"]
    canonicalize = task(workflow, "canonicalize-fixtures")
    save = task(workflow, "task-bulk-save-fixtures")
    fixture = provider_fixture()
    observed_at = "2026-08-22T12:00:00+00:00"
    event_view = {
        "event_id": "urn:machina:sports:event:x123",
        "label": "A vs B",
        "provider": {
            "namespace": "api-football",
            "family": "licensed",
            "raw": fixture,
        },
    }
    block = {
        "schema_version": "machina-sports-schema/1",
        "event_view": event_view,
        "provenance": {
            "provider": {"namespace": "api-football", "family": "licensed"},
            "observed_at": observed_at,
        },
        "rights": {
            "data_class": "licensed-provider-example-fixture",
            "prototype_only": True,
            "commercial_use": False,
        },
    }
    connector_context = {
        "allowed": True,
        "envelope": {"machina_sports_schema": block},
        "provider-fixture": fixture,
        "observed_at": observed_at,
    }

    canonical_outputs = evaluate_outputs(canonicalize["outputs"], connector_context)
    assert canonical_outputs["canonical-envelopes"] == [
        {"machina_sports_schema": block}
    ]
    assert canonical_outputs["canonical-envelope-validity"] == [True]
    assert canonical_outputs["fixtures"] == [
        {
            "@id": event_view["event_id"],
            "@type": "sport:Event",
            "name": event_view["label"],
            "event_view": event_view,
            "machina_sports_schema": block,
        }
    ]
    altered = {
        "machina_sports_schema": {
            **block,
            "rights": {**block["rights"], "commercial_use": True},
        }
    }
    assert evaluate_outputs(
        canonicalize["outputs"], {**connector_context, "envelope": altered}
    )["canonical-envelope-validity"] == [False]

    canonical_fixture = canonical_outputs["fixtures"][0]
    context = {"fixtures": [canonical_fixture]}
    items = evaluate(save["documents"]["items"], context)
    assert items[0]["machina_sports_schema"] == block
    assert items[0]["@id"] == event_view["event_id"]
    assert items[0]["@type"] == "sport:Event"
    assert items[0]["name"] == event_view["label"]
    assert items[0]["title"] == event_view["label"]
    assert items[0]["metadata"]["event_code"] == event_view["event_id"]
    assert items[0]["machina_sports_schema"]["provenance"]["provider"]["namespace"] == "api-football"
    assert items[0]["machina_sports_schema"]["rights"] == block["rights"]
    assert evaluate(save["documents"]["items"], context) == items


def test_sync_fixtures_bulk_update_fails_closed_on_canonical_drift():
    workflow = load_yaml("sync-fixtures.yml")["workflow"]
    save = task(workflow, "task-bulk-save-fixtures")
    base = {
        "provider-response-valid": True,
        "provider-errors": [],
        "provider-fixtures": [provider_fixture()],
        "fixtures": [{"@id": "urn:machina:sports:event:x123"}],
        "canonical-envelopes": [{"machina_sports_schema": {}}],
        "canonical-envelope-validity": [True],
    }

    assert save["config"]["action"] == "bulk-update"
    assert save["config"]["force-update"] is True
    assert save["document_name"] == "'sport:Event'"
    assert evaluate(save["condition"], base)
    assert not evaluate(
        save["condition"], {**base, "canonical-envelope-validity": [False]}
    )
    assert not evaluate(save["condition"], {**base, "fixtures": []})


def test_populate_is_inactive_with_a_bounded_recurring_frequency():
    agent = load_yaml("agents/populate.yml")["agent"]

    assert agent["context"]["status"] == "inactive"
    assert agent["context"]["config-frequency"] == 360
    assert 0 < agent["context"]["config-frequency"] <= 1440


def test_event_synchronize_never_updates_without_a_provider_fixture():
    workflow = load_yaml("workflows/event-synchronize.yml")["workflow"]
    update = task(workflow, "version-control-update")
    base = {
        "event_exists": True,
        "provider-response-valid": True,
        "provider-errors": [],
        "event_updated": {"@id": "urn:apifootball:sport_event:1390823"},
    }

    assert not evaluate(update["condition"], {**base, "fixture_exists": False})
    assert evaluate(update["condition"], {**base, "fixture_exists": True})

    fetch_outputs = task(workflow, "fetch-fixture-details")["outputs"]
    empty = evaluate_outputs(
        fetch_outputs, {"response": [], "errors": [], "results": 0}
    )
    assert empty["provider-response-valid"] is True
    assert empty["fixture_exists"] is False


def test_event_synchronize_rejects_provider_errors_and_malformed_payloads():
    workflow = load_yaml("workflows/event-synchronize.yml")["workflow"]
    fetch_outputs = task(workflow, "fetch-fixture-details")["outputs"]
    update = task(workflow, "version-control-update")

    for payload in (
        {"response": [provider_fixture()], "errors": ["quota"], "results": 1},
        {"response": {}, "errors": [], "results": 1},
    ):
        state = evaluate_outputs(fetch_outputs, payload)
        state.update({"event_exists": True, "event_updated": provider_fixture()})
        assert not evaluate(update["condition"], state)


def test_event_synchronize_rejects_a_different_fixture_id():
    workflow = load_yaml("workflows/event-synchronize.yml")["workflow"]
    fetch_outputs = task(workflow, "fetch-fixture-details")["outputs"]

    state = evaluate_outputs(
        fetch_outputs,
        {
            "response": [provider_fixture(999)],
            "errors": [],
            "results": 1,
            "original_fixture_id": "1390823",
        },
    )

    assert state["provider-response-valid"] is True
    assert state["fixture_exists"] is False
