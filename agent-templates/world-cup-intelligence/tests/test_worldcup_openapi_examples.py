"""Every example embedded in docs/openapi.json must validate against its schema.

The 200 examples are real bodies captured from the production archive
(2026-09-18), wrapped in the transport envelope {status, meta, data} exactly as
api.machina.gg and the ZeroClick storefront deliver them (1.5.0 — ZeroClick
noticed the 1.4.0 schemas described only the inner `data` block). The error
examples are real 4xx bodies captured through the storefront on 2026-09-22.
This document is what ZeroClick imports into the storefront catalog, so a
schema/example drift here is a buyer-facing contract bug.
"""

from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

DOCS = Path(__file__).resolve().parents[1] / "docs"
SPEC = json.loads((DOCS / "openapi.json").read_text(encoding="utf-8"))
IMPORT_SOURCE = json.loads((DOCS / "openapi-import-source.json").read_text(encoding="utf-8"))

GATEWAY_ERROR_REF = {"$ref": "#/components/schemas/GatewayError"}
# The six endpoints ZeroClick called without a body on 2026-09-16; each ships a
# real captured 400 so buyers see the unserved shape, not just a description.
REPORTED_ENDPOINTS = (
    "/world-cup/v1/get-standings",
    "/world-cup/v1/get-squads",
    "/world-cup/v1/get-injuries",
    "/world-cup/v1/get-player-performance-context",
    "/world-cup/v1/get-match-forecast",
    "/world-cup/v1/backtest-forecasts",
)


def _validate(schema, instance):
    full = dict(schema)
    full["components"] = SPEC["components"]
    jsonschema.Draft202012Validator(full).validate(instance)


@pytest.mark.parametrize("path", sorted(SPEC["paths"]))
def test_every_operation_has_request_fields_a_200_schema_and_a_real_example(path):
    op = SPEC["paths"][path]["post"]
    body = op["requestBody"]["content"]["application/json"]
    assert body["schema"], path
    assert "captured" in body["examples"], path
    _validate(body["schema"], body["examples"]["captured"]["value"])
    ok = op["responses"]["200"]["content"]["application/json"]
    assert ok["schema"], path
    assert ok["examples"], path
    for example in ok["examples"].values():
        _validate(ok["schema"], example["value"])
    for code in ("400", "404", "502", "503"):
        assert "Never billed" in op["responses"][code]["description"], (path, code)


@pytest.mark.parametrize("path", sorted(SPEC["paths"]))
def test_every_200_describes_the_transport_envelope(path):
    ok = SPEC["paths"][path]["post"]["responses"]["200"]["content"]["application/json"]
    schema = ok["schema"]
    assert schema["required"] == ["status", "data", "meta"], path
    assert schema["properties"]["status"] == {"const": "success"}, path
    assert schema["properties"]["meta"]["properties"]["code"] == {"const": 200}, path
    # the endpoint payload keeps its own schema under `data`
    assert "anyOf" in schema["properties"]["data"], path
    for name, example in ok["examples"].items():
        value = example["value"]
        assert value["status"] == "success", (path, name)
        assert value["meta"] == {"code": 200}, (path, name)
        assert {"archive", "coverage"} <= set(value["data"]), (path, name)


@pytest.mark.parametrize("path", sorted(SPEC["paths"]))
def test_every_non_2xx_is_a_gateway_error_and_captured_errors_validate(path):
    op = SPEC["paths"][path]["post"]
    for code, response in op["responses"].items():
        if code == "200":
            continue
        content = response["content"]["application/json"]
        assert content["schema"] == GATEWAY_ERROR_REF, (path, code)
        for name, example in content.get("examples", {}).items():
            value = example["value"]
            _validate(GATEWAY_ERROR_REF, value)
            assert value["status"] == "error", (path, code, name)
            assert value["meta"]["code"] == int(code), (path, code, name)
            assert value["data"] == {}, (path, code, name)
            assert value["error"]["code"] == int(code), (path, code, name)
            assert value["error"]["billed"] is False, (path, code, name)
            assert value["error"]["reason_code"] in SPEC["components"]["schemas"]["Coverage"]["properties"]["reason_code"]["enum"]
            assert value["error"]["accepted_fields"], (path, code, name)


@pytest.mark.parametrize("path", REPORTED_ENDPOINTS)
def test_reported_endpoints_ship_a_real_captured_400(path):
    examples = SPEC["paths"][path]["post"]["responses"]["400"]["content"]["application/json"]["examples"]
    assert examples, path
    assert any("captured through the ZeroClick storefront" in e["summary"] for e in examples.values()), path


def test_coverage_reason_codes_match_the_connector():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "worldcup_openapi_examples_connector", DOCS.parent / "worldcup-market-intelligence.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    codes = set(SPEC["components"]["schemas"]["Coverage"]["properties"]["reason_code"]["enum"])
    assert codes == module.UNSERVED_REQUEST_REASONS | module.UNSERVED_ARCHIVE_REASONS


def test_import_source_mirrors_the_buyer_facing_spec():
    def strip(document):
        document = json.loads(json.dumps(document))
        document.pop("servers", None)
        document.pop("x-publication", None)
        return document

    assert strip(IMPORT_SOURCE) == strip(SPEC)
    assert IMPORT_SOURCE["servers"][0]["url"] == "https://api.machina.gg"
    assert SPEC["servers"][0]["url"].startswith("https://agents.machina.gg/")
    assert SPEC["info"]["version"] == "1.5.0"
