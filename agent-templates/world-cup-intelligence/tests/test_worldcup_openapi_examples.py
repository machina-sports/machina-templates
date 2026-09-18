"""Every example embedded in docs/openapi.json must validate against its schema.

The examples are real 200 bodies captured from the production archive
(2026-09-18) and are what ZeroClick imports into the storefront catalog, so a
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
