"""Regression tests for API-Football workflow safety and observability."""

import importlib.util

from datetime import datetime, timedelta, timezone

from pathlib import Path

import yaml


CONNECTOR_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CONNECTOR_ROOT.parents[1]
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


def evaluate(expression, response, workflow_context=None):
    if expression.strip() == "$":
        return response
    namespace = {
        "__builtins__": {"__import__": __import__},
        **SAFE_BUILTINS,
        "datetime": datetime,
        "timedelta": timedelta,
        # The engine always binds `context` to accumulated workflow state, never
        # to the task response (core/workflow/context.py::_save_outputs). Default
        # to empty state so a test only sees state it deliberately models.
        "context": workflow_context if workflow_context is not None else {},
    }
    expression = expression.replace("$.context", "context")
    expression = expression.replace("$.get", "response.get")
    namespace["response"] = response
    return eval(expression, namespace, namespace)


def task(workflow, name):
    return next(item for item in workflow["tasks"] if item["name"] == name)


def evaluate_outputs(outputs, response, workflow_context=None):
    # Mirrors core/workflow/context.py::_save_outputs: `$.get` reads the task's
    # connector response, `$.context` reads accumulated workflow state.
    return {
        key: evaluate(expression, response, workflow_context)
        for key, expression in outputs.items()
    }


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


def _canonical_connector():
    """The real machina-sports-canonical connector and package.

    Loaded exactly the way this repository's own canonical suites load it
    (tests/iptc_canonical_support.py), so these guards are proved against the
    envelope the seam actually emits rather than against a hand-written stub
    that can drift from it.
    """
    support_spec = importlib.util.spec_from_file_location(
        "iptc_canonical_support", REPO_ROOT / "tests/iptc_canonical_support.py"
    )
    support = importlib.util.module_from_spec(support_spec)
    support_spec.loader.exec_module(support)
    support.canonical_package()

    spec = importlib.util.spec_from_file_location(
        "machina_sports_canonical_connector",
        REPO_ROOT / "connectors/machina-sports-canonical/machina-sports-canonical.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonicalize_through_the_seam(fixture, observed_at, consumer_tier=None):
    """The connector response the canonicalize-fixture task would receive.

    `requires`/`optional`/`consumer_tier` are read off the workflow itself, so a
    change to what the task asks for is a change to what these tests prove.
    """
    canonicalize = task(
        load_yaml("workflows/event-synchronize.yml")["workflow"], "canonicalize-fixture"
    )
    inputs = canonicalize["inputs"]
    return _canonical_connector().canonicalize_event(
        {
            "params": {
                "provider": evaluate(inputs["provider"], {}),
                "consumer_tier": consumer_tier or evaluate(inputs["consumer_tier"], {}),
                "requires": evaluate(inputs["requires"], {}),
                "optional": evaluate(inputs["optional"], {}),
                "observed_at": observed_at,
                "payload": fixture,
            }
        }
    )["data"]


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
    connector_response = {
        "allowed": True,
        "envelope": {"machina_sports_schema": block},
    }
    workflow_state = {
        "provider-fixture": fixture,
        "observed_at": observed_at,
    }

    canonical_outputs = evaluate_outputs(
        canonicalize["outputs"], connector_response, workflow_state
    )
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
        canonicalize["outputs"],
        {**connector_response, "envelope": altered},
        workflow_state,
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


def test_sync_fixtures_persists_structured_events_without_embeddings():
    workflow = load_yaml("sync-fixtures.yml")["workflow"]
    save = task(workflow, "task-bulk-save-fixtures")

    assert save["config"]["embed-vector"] is False
    assert "embed-selector" not in save["config"]
    assert "connector" not in save
    assert "google-genai" not in workflow.get("context-variables", {})


def test_populate_is_inactive_with_a_bounded_recurring_frequency():
    agent = load_yaml("agents/populate.yml")["agent"]

    assert agent["context"]["status"] == "inactive"
    assert agent["context"]["config-frequency"] == 360
    assert 0 < agent["context"]["config-frequency"] <= 1440


def test_leagues_config_defaults_and_bounds_each_enabled_sync_window():
    workflow = load_yaml("load-leagues-config.yml")["workflow"]
    outputs = task(workflow, "load-config")["outputs"]
    leagues = [
        {"league_id": 39, "name": "Premier League", "season": 2026, "enabled": True},
        {
            "league_id": 140,
            "name": "La Liga",
            "season": 2026,
            "enabled": True,
            "lookback_days": 7,
            "lookahead_days": 45,
        },
        {"league_id": 78, "name": "Bundesliga", "season": 2026, "enabled": False},
        {
            "league_id": 135,
            "name": "Serie A",
            "season": 2026,
            "enabled": True,
            "lookback_days": -1,
        },
        {
            "league_id": 61,
            "name": "Ligue 1",
            "season": 2026,
            "enabled": True,
            "lookahead_days": 91,
        },
        {
            "league_id": "2",
            "name": "Champions League",
            "season": 2026,
            "enabled": True,
        },
    ]

    state = evaluate_outputs(outputs, {"documents": [{"value": {"leagues": leagues}}]})

    assert state["enabled_leagues"] == [
        {**leagues[0], "lookback_days": 3, "lookahead_days": 30},
        leagues[1],
    ]
    assert evaluate(
        workflow["outputs"]["enabled_league_ids"], state
    ) == [39, 140]


def test_leagues_config_fails_closed_for_malformed_document_containers():
    outputs = task(
        load_yaml("load-leagues-config.yml")["workflow"], "load-config"
    )["outputs"]

    for payload in (
        {"documents": [{"value": None}]},
        {"documents": [{"value": {"leagues": None}}]},
        {"documents": [{"value": {"leagues": {"league_id": 39}}}]},
        {"documents": [{"value": {"leagues": "39"}}]},
    ):
        state = evaluate_outputs(outputs, payload)
        assert state["leagues_config"] == []
        assert state["enabled_leagues"] == []


def test_populate_passes_date_window_configuration_without_datetime_expressions():
    agent_path = CONNECTOR_ROOT / "agents/populate.yml"
    agent_text = agent_path.read_text(encoding="utf-8")
    agent = yaml.safe_load(agent_text)["agent"]
    sync = next(
        item
        for item in agent["workflows"]
        if item["name"] == "api-football-sync-fixtures"
    )

    assert sync["inputs"] == {
        "league": "$.get('league').get('league_id')",
        "season": "$.get('league').get('season')",
        "lookback_days": "$.get('league').get('lookback_days')",
        "lookahead_days": "$.get('league').get('lookahead_days')",
        "timezone": "'UTC'",
    }
    assert "datetime" not in agent_text
    assert "timedelta" not in agent_text


def test_sync_fixtures_computes_default_and_override_utc_date_windows():
    inputs = load_yaml("sync-fixtures.yml")["workflow"]["inputs"]

    assert inputs["lookback_days"] == "$.get('lookback_days', 3)"
    assert inputs["lookahead_days"] == "$.get('lookahead_days', 30)"
    today = datetime.now(timezone.utc).date()

    default_from = evaluate(inputs["from"], {})
    default_to = evaluate(inputs["to"], {})
    assert default_from == (today - timedelta(days=3)).isoformat()
    assert default_to == (today + timedelta(days=30)).isoformat()
    datetime.strptime(default_from, "%Y-%m-%d")
    datetime.strptime(default_to, "%Y-%m-%d")

    overrides = {"lookback_days": "7", "lookahead_days": "45"}
    override_from = evaluate(inputs["from"], overrides)
    override_to = evaluate(inputs["to"], overrides)
    assert override_from == (today - timedelta(days=7)).isoformat()
    assert override_to == (today + timedelta(days=45)).isoformat()
    datetime.strptime(override_from, "%Y-%m-%d")
    datetime.strptime(override_to, "%Y-%m-%d")


def test_sync_fixtures_honors_explicit_date_window():
    inputs = load_yaml("sync-fixtures.yml")["workflow"]["inputs"]
    context = {
        "from": "2026-09-01",
        "to": "2026-09-09",
        "lookback_days": 7,
        "lookahead_days": 45,
    }

    assert evaluate(inputs["from"], context) == "2026-09-01"
    assert evaluate(inputs["to"], context) == "2026-09-09"


def test_event_synchronize_never_updates_without_a_provider_fixture():
    workflow = load_yaml("workflows/event-synchronize.yml")["workflow"]
    update = task(workflow, "version-control-update")
    base = {
        "event_exists": True,
        "provider-response-valid": True,
        "provider-errors": [],
        "canonical-envelope-valid": True,
        "event_updated": {"@id": "urn:machina:sports:event:x1390823"},
    }

    assert not evaluate(update["condition"], {**base, "fixture_exists": False})
    assert not evaluate(update["condition"], {**base, "fixture_exists": True, "canonical-envelope-valid": False})
    assert evaluate(update["condition"], {**base, "fixture_exists": True})

    fetch_outputs = task(workflow, "fetch-fixture-details")["outputs"]
    empty = evaluate_outputs(
        fetch_outputs, {"response": [], "errors": [], "results": 0}
    )
    assert empty["provider-response-valid"] is True
    assert empty["fixture_exists"] is False


def test_event_synchronize_resolves_canonical_provider_fixture_id_exactly():
    workflow = load_yaml("workflows/event-synchronize.yml")["workflow"]
    resolver = task(workflow, "resolve-provider-fixture-id")
    fetch = task(workflow, "fetch-fixture-details")

    assert all(
        item.get("name") != "iptc-api-football-id-conversion-mapping"
        for item in workflow["tasks"]
    )
    assert resolver["type"] == "connector"
    assert resolver["connector"] == {
        "name": "api-football-event-data",
        "command": "resolve_provider_fixture_id",
    }
    assert resolver["inputs"] == {
        "event_document_value": "$.get('event_value', {})"
    }
    assert resolver["outputs"] == {
        "provider_fixture_id": "$.get('provider_fixture_id')"
    }
    assert fetch["condition"] == "$.get('provider_fixture_id') is not None"
    assert fetch["inputs"] == {"id": "$.get('provider_fixture_id')"}
    assert not evaluate(fetch["condition"], {"event_exists": True})
    assert evaluate(
        fetch["inputs"]["id"], {"provider_fixture_id": 1390823}
    ) == 1390823


def test_successful_event_synchronization_reaches_event_data_enrichment():
    synchronize = load_yaml("workflows/event-synchronize.yml")["workflow"]
    synchronized = {
        "event_exists": True,
        "provider-response-valid": True,
        "provider-errors": [],
        "fixture_exists": True,
        "event_updated": {"@id": "urn:machina:sports:event:x123"},
    }

    status = evaluate(synchronize["outputs"]["workflow-status"], synchronized)
    assert status == "executed"

    for path in ("agents/event-prelive-update.yml", "agents/event-live-update.yml"):
        agent = load_yaml(path)["agent"]
        enrich = next(
            item
            for item in agent["workflows"]
            if item["name"] == "api-football-enrich-event-data"
        )
        assert evaluate(
            enrich["condition"],
            {"event_exists": True, "event-synchronize-status": status},
        )


def test_event_data_enrichment_requires_existing_event_and_completed_sync():
    expected = (
        "$.get('event_exists') is True and "
        "$.get('event-synchronize-status') in ('executed', 'skipped')"
    )
    allowed = (
        {"event_exists": True, "event-synchronize-status": "executed"},
        {"event_exists": True, "event-synchronize-status": "skipped"},
    )
    blocked = (
        {"event_exists": True, "event-synchronize-status": "failed"},
        {"event_exists": True},
        {"event-synchronize-status": "executed"},
        {"event-synchronize-status": "skipped"},
        {"event_exists": False, "event-synchronize-status": "executed"},
        {"event_exists": False, "event-synchronize-status": "skipped"},
    )

    for path in ("agents/event-prelive-update.yml", "agents/event-live-update.yml"):
        agent = load_yaml(path)["agent"]
        enrich = next(
            item
            for item in agent["workflows"]
            if item["name"] == "api-football-enrich-event-data"
        )

        assert enrich["condition"] == expected
        assert all(evaluate(enrich["condition"], context) for context in allowed)
        assert not any(evaluate(enrich["condition"], context) for context in blocked)


def test_event_data_enrichment_snapshots_complete_provider_envelopes_safely():
    workflow = load_yaml("api-football-enrich-event-data.yml")["workflow"]
    envelope_outputs = {
        "fetch-fixture": "fixture-envelope",
        "fetch-events": "events-envelope",
        "fetch-lineups": "lineups-envelope",
        "fetch-team-statistics": "team-statistics-envelope",
        "fetch-player-statistics": "player-statistics-envelope",
        "fetch-head-to-head": "head-to-head-envelope",
    }
    payload = {
        "get": "fixtures",
        "parameters": {"fixture": "1390823"},
        "errors": [],
        "results": 1,
        "paging": {"current": 1, "total": 1},
        "response": [provider_fixture()],
        "provider-extension": {"retained": True},
    }

    for task_name, output_name in envelope_outputs.items():
        outputs = task(workflow, task_name)["outputs"]
        assert "dict($.items())" not in outputs.values()
        assert outputs[output_name] == "$"

        envelope = evaluate(outputs[output_name], payload)
        assert envelope == payload
        assert set(envelope) >= {
            "get",
            "parameters",
            "errors",
            "results",
            "paging",
            "response",
        }
        assert isinstance(envelope["parameters"], dict)
        assert isinstance(envelope["errors"], (list, dict))
        assert isinstance(envelope["results"], int)
        assert isinstance(envelope["paging"], dict)
        assert isinstance(envelope["response"], list)
        assert envelope["provider-extension"] == {"retained": True}


def test_event_data_enrichment_validates_fixture_against_workflow_context():
    workflow = load_yaml("api-football-enrich-event-data.yml")["workflow"]
    fixture_valid = task(workflow, "fetch-fixture")["outputs"]["fixture-valid"]
    response = {
        "response": [provider_fixture(1557375)],
        "errors": [],
        "results": 1,
    }

    assert evaluate(
        fixture_valid, response, {"provider-fixture-id": 1557375}
    ) is True
    assert evaluate(
        fixture_valid, response, {"provider-fixture-id": 1557376}
    ) is False


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
        {"response": [provider_fixture(999)], "errors": [], "results": 1},
        {"provider_fixture_id": 1390823},
    )

    assert state["provider-response-valid"] is True
    assert state["fixture_exists"] is False


def test_event_synchronize_accepts_equivalent_string_and_integer_fixture_ids():
    workflow = load_yaml("workflows/event-synchronize.yml")["workflow"]
    fetch_outputs = task(workflow, "fetch-fixture-details")["outputs"]

    for response_id, provider_fixture_id in (
        (1570353, "1570353"),
        ("1570353", 1570353),
    ):
        state = evaluate_outputs(
            fetch_outputs,
            {"response": [provider_fixture(response_id)], "errors": [], "results": 1},
            {"provider_fixture_id": provider_fixture_id},
        )

        assert state["provider-response-valid"] is True
        assert state["fixture_exists"] is True


def test_event_synchronize_rejects_empty_boolean_and_invalid_fixture_ids():
    workflow = load_yaml("workflows/event-synchronize.yml")["workflow"]
    fetch_outputs = task(workflow, "fetch-fixture-details")["outputs"]

    for response_id, provider_fixture_id in (
        (None, "1570353"),
        ("", ""),
        ("   ", "   "),
        (True, "True"),
        ("True", True),
        ([], "[]"),
        ({}, "{}"),
        (1570353, []),
        (1570353, {}),
    ):
        state = evaluate_outputs(
            fetch_outputs,
            {"response": [provider_fixture(response_id)], "errors": [], "results": 1},
            {"provider_fixture_id": provider_fixture_id},
        )

        assert state["provider-response-valid"] is True
        assert state["fixture_exists"] is False


def test_event_synchronize_requires_exactly_one_well_formed_fixture():
    workflow = load_yaml("workflows/event-synchronize.yml")["workflow"]
    fetch_outputs = task(workflow, "fetch-fixture-details")["outputs"]

    for response in (
        [],
        [provider_fixture(1570353), provider_fixture(1570353)],
        ["not-a-fixture"],
        [{"fixture": []}],
    ):
        state = evaluate_outputs(
            fetch_outputs,
            {"response": response, "errors": [], "results": len(response)},
            {"provider_fixture_id": "1570353"},
        )

        assert state["fixture_exists"] is False


def test_event_synchronize_provider_response_validation_stays_bounded():
    workflow = load_yaml("workflows/event-synchronize.yml")["workflow"]
    fetch_outputs = task(workflow, "fetch-fixture-details")["outputs"]

    valid_payloads = (
        {"response": [], "errors": [], "results": 0},
        {"response": [provider_fixture()], "errors": {}, "results": 1},
    )
    invalid_payloads = (
        {
            "response": [provider_fixture(1), provider_fixture(2)],
            "errors": [],
            "results": 2,
        },
        {"response": [provider_fixture()], "errors": [], "results": True},
        {"response": [provider_fixture()], "errors": [], "results": 0},
        {"response": {}, "errors": [], "results": 0},
    )

    assert all(
        evaluate_outputs(fetch_outputs, payload)["provider-response-valid"] is True
        for payload in valid_payloads
    )
    assert all(
        evaluate_outputs(fetch_outputs, payload)["provider-response-valid"] is False
        for payload in invalid_payloads
    )


def test_event_synchronize_reads_resolved_fixture_id_from_workflow_state_not_response():
    # Regression for the Aug 28 - Sep 4 outage: API-Football's /fixtures response
    # never carries `provider_fixture_id`; that value lives in workflow state from
    # the resolve task. Reading it via `$.get` made `fixture_exists` False on every
    # real response, so the mapping and update tasks never ran and every
    # synchronize reported `skipped`.
    workflow = load_yaml("workflows/event-synchronize.yml")["workflow"]
    fetch_outputs = task(workflow, "fetch-fixture-details")["outputs"]

    assert "$.get('provider_fixture_id')" not in fetch_outputs["fixture_exists"]
    assert "$.context.get('provider_fixture_id')" in fetch_outputs["fixture_exists"]

    real_response = {
        "get": "fixtures",
        "parameters": {"id": "1557404"},
        "errors": [],
        "results": 1,
        "paging": {"current": 1, "total": 1},
        "response": [provider_fixture(1557404)],
    }
    state = evaluate_outputs(fetch_outputs, real_response, {"provider_fixture_id": 1557404})
    assert state["provider-response-valid"] is True
    assert state["fixture_exists"] is True

    state = evaluate_outputs(fetch_outputs, real_response, {})
    assert state["fixture_exists"] is False


def test_event_synchronize_refreshes_through_the_canonical_seam_only():
    # The per-event refresh must write the same canonical sport:Event shape that
    # sync-fixtures writes. The legacy IPTC mapping (urn:apifootball ids,
    # sport:competitors) overwrote the canonical block every consumer reads.
    workflow = load_yaml("workflows/event-synchronize.yml")["workflow"]
    names = [item["name"] for item in workflow["tasks"]]
    assert "iptc-api-football-event-mapping" not in names
    assert all(item.get("type") != "mapping" for item in workflow["tasks"])

    canonicalize = task(workflow, "canonicalize-fixture")
    assert canonicalize["connector"] == {"name": "machina-sports-canonical", "command": "canonicalize_event"}
    assert canonicalize["inputs"]["provider"] == "'api-football'"
    assert canonicalize["inputs"]["payload"] == "$.get('fixture_data', {})"
    assert canonicalize["inputs"]["observed_at"] == "$.get('observed_at')"
    assert "$.get('observed_at'" in workflow["inputs"]["observed_at"]

    # Proved against the envelope the real seam emits, not a stub of it. A
    # microsecond-bearing observed_at is the workflow's own default shape
    # (datetime.utcnow().isoformat() + '+00:00'), and the gate compares it by
    # string equality — so the seam has to echo it back byte for byte.
    fixture = provider_fixture(1557404)
    observed_at = "2026-09-04T23:24:08.123456+00:00"
    response = canonicalize_through_the_seam(fixture, observed_at)
    block = response["envelope"]["machina_sports_schema"]
    event_id = block["event_view"]["event_id"]
    state = {
        "event_value": {"machina_sports_schema": {"event_view": {"event_id": event_id}}},
        "fixture_data": fixture,
        "observed_at": observed_at,
    }

    outputs = evaluate_outputs(canonicalize["outputs"], response, state)
    assert outputs["canonical-envelope-valid"] is True
    assert outputs["canonical-refusals"] == []
    assert outputs["event_updated"]["@id"] == event_id
    assert outputs["event_updated"]["@type"] == "sport:Event"
    assert outputs["event_updated"]["machina_sports_schema"]["provenance"]["observed_at"] == observed_at
    assert "sport:competitors" not in outputs["event_updated"]
    assert not str(outputs["event_updated"]["@id"]).startswith("urn:apifootball:")

    # What the gate is actually asserting about the real envelope: the consumer
    # (lib/event-evidence.ts) rejects anything that is not a licensed
    # api-football observation carrying provider-native crosswalk entries.
    assert block["event_view"]["provider"]["family"] == "licensed"
    assert block["event_view"]["provider"]["raw"] == fixture
    assert block["provenance"]["provider"] == {"namespace": "api-football", "family": "licensed"}
    assert block["rights"]["data_class"] == "licensed-provider-example-fixture"
    assert {entry["resolution_method"] for entry in block["provider_ids"]} == {"provider-native"}

    # A canonical envelope for a different event never overwrites this document.
    outputs = evaluate_outputs(
        canonicalize["outputs"],
        canonicalize_through_the_seam(provider_fixture(1557405), observed_at),
        state,
    )
    assert outputs["canonical-envelope-valid"] is False
    assert outputs["event_updated"] is None

    # A real refusal from the seam produces no update and surfaces its refusals.
    refused = canonicalize_through_the_seam(fixture, observed_at, consumer_tier="production")
    assert refused["allowed"] is False
    outputs = evaluate_outputs(canonicalize["outputs"], refused, state)
    assert outputs["canonical-envelope-valid"] is False
    assert outputs["event_updated"] is None
    assert outputs["canonical-refusals"] == refused["refusals"]
    assert outputs["canonical-refusals"]

    # An envelope that is well formed but carries refusals never writes.
    outputs = evaluate_outputs(
        canonicalize["outputs"],
        {**response, "refusals": [{"code": "capability-incompatible"}]},
        state,
    )
    assert outputs["canonical-envelope-valid"] is False


def legacy_poisoned_event_value(event_id, fixture):
    """A stored document as the retired IPTC mapping left it.

    The pre-canonical event-synchronize merged the mapping's output over the
    document, so a real production event carries the canonical block *and* the
    mapping's aliases for the same facts, alongside unrelated operator and
    market data that nothing in this workflow owns.
    """
    return {
        "@context": {"sport": "https://www.sportschema.org/ontologies/sport#"},
        "@id": "urn:apifootball:sport_event:{0}".format(fixture["fixture"]["id"]),
        "@type": ["sport:Event", "schema:SportsEvent"],
        "name": "Espanyol vs Atletico Madrid - La Liga",
        "schema:startDate": "2025-08-17T19:30:00+00:00",
        "sport:status": "NS",
        "status": "NS",
        "sport:score": {"sport:homeScore": None, "sport:awayScore": None},
        "sport:competitors": [{"@id": "urn:apifootball:team:540"}],
        "sport:competition": {"@id": "urn:apifootball:league:140"},
        "sport:venue": {"@id": "urn:apifootball:venue:1"},
        "machina_sports_schema": {"event_view": {"event_id": event_id}},
        # Everything below is owned by somebody else and must survive untouched.
        "markets": [{"provider": "entain", "market_id": "1x2"}],
        "editorial_notes": "desk copy",
        "metadata_hint": {"broadcast": "channel-4"},
        "version_control": {"counter": 7, "processing": True},
    }


CANONICAL_OWNED_ALIASES = (
    "@context",
    "schema:startDate",
    "sport:competition",
    "sport:competitors",
    "sport:score",
    "sport:status",
    "sport:venue",
    "status",
)


def persisted_event_document(state):
    """The document the update task actually writes, per the engine's rules.

    `documents` is evaluated by core/workflow/context.py::_retrieve_from_context,
    which binds `$.get` to accumulated workflow state.
    """
    workflow = load_yaml("workflows/event-synchronize.yml")["workflow"]
    return evaluate(task(workflow, "version-control-update")["documents"]["sport:Event"], state)


def refreshed_state(fixture, observed_at):
    """Workflow state after a successful canonicalize-fixture, over a document
    the retired mapping had already poisoned."""
    workflow = load_yaml("workflows/event-synchronize.yml")["workflow"]
    canonicalize = task(workflow, "canonicalize-fixture")
    response = canonicalize_through_the_seam(fixture, observed_at)
    event_id = response["envelope"]["machina_sports_schema"]["event_view"]["event_id"]
    state = {
        "event_document_id": "doc-1",
        "event_value": legacy_poisoned_event_value(event_id, fixture),
        "fixture_data": fixture,
        "observed_at": observed_at,
    }
    state.update(evaluate_outputs(canonicalize["outputs"], response, state))
    return state


def test_event_synchronize_drops_only_the_aliases_the_canonical_block_now_owns():
    fixture = provider_fixture(1557404)
    state = refreshed_state(fixture, "2026-09-04T23:24:08.123456+00:00")
    assert state["canonical-envelope-valid"] is True

    document = persisted_event_document(state)

    # The stale aliases the canonical block now owns are gone, so no consumer
    # reads a fact this writer no longer refreshes.
    for alias in CANONICAL_OWNED_ALIASES:
        assert alias not in document, alias

    # The canonical refresh landed.
    block = document["machina_sports_schema"]
    assert document["@id"] == block["event_view"]["event_id"]
    assert document["@type"] == "sport:Event"
    assert document["event_view"] == block["event_view"]
    assert document["name"] == block["event_view"]["label"]
    assert document["title"] == block["event_view"]["label"]
    assert not str(document["@id"]).startswith("urn:apifootball:")

    # Everything this workflow does not own survives untouched.
    assert document["markets"] == [{"provider": "entain", "market_id": "1x2"}]
    assert document["editorial_notes"] == "desk copy"
    assert document["metadata_hint"] == {"broadcast": "channel-4"}
    assert document["version_control"] == {"counter": 7, "processing": True}


def test_event_synchronize_leaves_no_stale_state_across_the_match_lifecycle():
    # prelive -> live -> finished, and a kickoff that moves. Each refresh must
    # leave the document carrying exactly one answer for status, score and
    # kickoff: the canonical one.
    lifecycle = [
        ("2025-08-17T19:30:00+00:00", {"short": "NS"}, {"home": None, "away": None}),
        ("2025-08-17T19:30:00+00:00", {"short": "1H"}, {"home": 1, "away": 0}),
        ("2025-08-17T21:15:00+00:00", {"short": "FT"}, {"home": 2, "away": 1}),
    ]

    for kickoff, status, goals in lifecycle:
        fixture = provider_fixture(1557404)
        fixture["fixture"]["date"] = kickoff
        fixture["fixture"]["status"] = status
        fixture["goals"] = goals
        fixture["score"] = {"fulltime": goals}

        state = refreshed_state(fixture, "2026-09-04T23:24:08.123456+00:00")
        assert state["canonical-envelope-valid"] is True

        document = persisted_event_document(state)
        event_view = document["machina_sports_schema"]["event_view"]

        # The document never carries a second, unrefreshed answer.
        for alias in CANONICAL_OWNED_ALIASES:
            assert alias not in document, (alias, status["short"])

        # The canonical answer tracks the provider, including the moved kickoff.
        assert event_view["provider"]["raw"]["fixture"]["status"] == status
        assert event_view["provider"]["raw"]["fixture"]["date"] == kickoff
        assert event_view["start_time"] == kickoff
        assert document["version_control"] == {"counter": 7, "processing": True}


def test_event_synchronize_never_writes_when_the_envelope_gate_fails():
    # The gate is the only thing standing between a bad envelope and the
    # document, so a failed gate must stop the update task outright.
    workflow = load_yaml("workflows/event-synchronize.yml")["workflow"]
    update = task(workflow, "version-control-update")
    base = {
        "event_exists": True,
        "provider-response-valid": True,
        "provider-errors": [],
        "fixture_exists": True,
        "event_updated": {"@id": "urn:machina:sports:event:x1"},
    }

    assert evaluate(update["condition"], {**base, "canonical-envelope-valid": True})
    assert not evaluate(update["condition"], {**base, "canonical-envelope-valid": False})
    assert not evaluate(update["condition"], base)


def test_event_synchronize_gate_matches_its_sibling_writer():
    # One writer, one shape means one gate. Anything sync-fixtures refuses to
    # persist, the per-event refresh must refuse to persist too.
    synchronize = load_yaml("workflows/event-synchronize.yml")["workflow"]
    sync_fixtures = load_yaml("sync-fixtures.yml")["workflow"]
    gate = task(synchronize, "canonicalize-fixture")["outputs"]["canonical-envelope-valid"]
    sibling = task(sync_fixtures, "canonicalize-fixtures")["outputs"]["canonical-envelope-validity"]

    for claim in (
        "get('label'), str)",
        "get('provider', {}).get('family') == 'licensed'",
        "get('provenance', {}).get('provider', {}).get('namespace') == 'api-football'",
        "get('provenance', {}).get('provider', {}).get('family') == 'licensed'",
        "get('rights', {}).get('data_class') == 'licensed-provider-example-fixture'",
        "get('rights', {}).get('prototype_only') is True",
        "get('rights', {}).get('commercial_use') is False",
    ):
        assert claim in sibling, claim
        assert claim in gate, claim

    # And the per-event refresh additionally refuses on any refusal at all.
    assert "not $.get('refusals')" in gate
