"""Offline contract tests for the Fight Analytics REST connector."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from typing import Any, Iterator, Tuple

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
CONNECTOR_DIR = REPO_ROOT / "connectors" / "fight-analytics"
INSTALL_PATH = CONNECTOR_DIR / "_install.yml"
DESCRIPTOR_PATH = CONNECTOR_DIR / "fight-analytics.yml"
OPENAPI_PATH = CONNECTOR_DIR / "fight-analytics.json"

EXPECTED_PATHS = {
    "/promotions",
    "/promotions/{id}",
    "/venues",
    "/venues/{id}",
    "/teams",
    "/teams/{id}",
    "/events",
    "/events/{id}",
    "/fighters",
    "/fighters/{id}",
    "/fights",
    "/fights/{id}",
}
EXPECTED_OPERATION_IDS = {
    "/promotions": "listPromotions",
    "/promotions/{id}": "getPromotion",
    "/venues": "listVenues",
    "/venues/{id}": "getVenue",
    "/teams": "listTeams",
    "/teams/{id}": "getTeam",
    "/events": "listEvents",
    "/events/{id}": "getEvent",
    "/fighters": "listFighters",
    "/fighters/{id}": "getFighter",
    "/fights": "listFights",
    "/fights/{id}": "getFight",
}
HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
CREDENTIAL_KEYS = {
    "authorization",
    "token",
    "access_token",
    "api_key",
    "apikey",
    "credential",
    "credentials",
    "secret",
    "password",
}


def read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return yaml.safe_load(stream)


def read_openapi() -> dict:
    with OPENAPI_PATH.open(encoding="utf-8") as stream:
        return json.load(stream)


def walk(value: Any, location: str = "$") -> Iterator[Tuple[str, Any]]:
    yield location, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk(child, f"{location}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, f"{location}[{index}]")


def resolve_json_pointer(document: Any, pointer: str) -> Any:
    if not pointer.startswith("#/"):
        raise AssertionError(f"non-internal reference: {pointer}")
    target = document
    for token in pointer[2:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        target = target[int(token)] if isinstance(target, list) else target[token]
    return target


class TestFightAnalyticsConnector(unittest.TestCase):
    def test_descriptor_and_install_manifest_register_connectors(self):
        self.assertTrue(DESCRIPTOR_PATH.is_file(), f"absent: {DESCRIPTOR_PATH}")
        self.assertTrue(INSTALL_PATH.is_file(), f"absent: {INSTALL_PATH}")

        descriptor = read_yaml(DESCRIPTOR_PATH)
        connector = descriptor["connector"]
        self.assertEqual(connector["name"], "fight-analytics")
        self.assertEqual(connector["filename"], OPENAPI_PATH.name)
        self.assertEqual(connector["filetype"], "restapi")

        install = read_yaml(INSTALL_PATH)
        self.assertEqual(
            install["datasets"],
            [
                {"type": "connector", "path": DESCRIPTOR_PATH.name},
                {"type": "connector", "path": "fight-analytics-canonical.yml"},
            ],
        )

    def test_openapi_json_parses(self):
        self.assertTrue(OPENAPI_PATH.is_file(), f"absent: {OPENAPI_PATH}")
        self.assertIsInstance(read_openapi(), dict)

    def test_surface_is_exactly_the_documented_get_operations(self):
        document = read_openapi()
        self.assertEqual(set(document["paths"]), EXPECTED_PATHS)
        for path, path_item in document["paths"].items():
            methods = set(path_item) & HTTP_METHODS
            with self.subTest(path=path):
                self.assertEqual(methods, {"get"})

    def test_operation_ids_are_stable_and_unique(self):
        document = read_openapi()
        operation_ids = {
            path: path_item["get"].get("operationId")
            for path, path_item in document["paths"].items()
        }
        self.assertEqual(operation_ids, EXPECTED_OPERATION_IDS)
        self.assertEqual(len(set(operation_ids.values())), 12)

    def test_operation_parameter_composition_keywords_are_inside_schema(self):
        document = read_openapi()
        composition_keywords = {"oneOf", "anyOf", "allOf"}
        for path, path_item in document["paths"].items():
            for method in set(path_item) & HTTP_METHODS:
                for parameter in path_item[method].get("parameters", []):
                    with self.subTest(
                        path=path,
                        method=method,
                        parameter=parameter.get("name"),
                    ):
                        self.assertTrue(
                            composition_keywords.isdisjoint(parameter),
                            "schema composition keyword found at Parameter Object level",
                        )

    def test_schema_types_and_date_formats_are_valid_openapi_30(self):
        document = read_openapi()
        valid_types = {"array", "boolean", "integer", "number", "object", "string"}

        def schema_objects(
            schema: dict, location: str
        ) -> Iterator[Tuple[str, dict]]:
            yield location, schema
            for keyword in ("items", "additionalProperties", "not"):
                child = schema.get(keyword)
                if isinstance(child, dict):
                    yield from schema_objects(child, f"{location}.{keyword}")
            for name, child in schema.get("properties", {}).items():
                yield from schema_objects(child, f"{location}.properties.{name}")
            for keyword in ("oneOf", "anyOf", "allOf"):
                for index, child in enumerate(schema.get(keyword, [])):
                    yield from schema_objects(child, f"{location}.{keyword}[{index}]")

        schemas = []
        for path, path_item in document["paths"].items():
            for method in set(path_item) & HTTP_METHODS:
                for index, parameter in enumerate(
                    path_item[method].get("parameters", [])
                ):
                    schema = parameter.get("schema")
                    if isinstance(schema, dict):
                        schemas.extend(
                            schema_objects(
                                schema,
                                f"$.paths.{path}.{method}.parameters[{index}].schema",
                            )
                        )
        for name, schema in document["components"]["schemas"].items():
            schemas.extend(
                schema_objects(schema, f"$.components.schemas.{name}")
            )

        for location, schema in schemas:
            if "type" in schema:
                with self.subTest(location=location):
                    self.assertIn(schema["type"], valid_types)

        parameters = {
            (path, parameter["name"]): parameter["schema"]
            for path in ("/events", "/fights")
            for parameter in document["paths"][path]["get"]["parameters"]
        }
        date_schemas = {
            "GET /events date": parameters[("/events", "date")],
            "GET /events dateFrom": parameters[("/events", "dateFrom")],
            "GET /events dateTo": parameters[("/events", "dateTo")],
            "GET /fights date": parameters[("/fights", "date")],
            "CreateEventDto.date": document["components"]["schemas"]
            ["CreateEventDto"]["properties"]["date"],
            "UpdateEventDto.date": document["components"]["schemas"]
            ["UpdateEventDto"]["properties"]["date"],
        }
        for location, schema in date_schemas.items():
            with self.subTest(location=location):
                self.assertEqual(schema.get("type"), "string")
                self.assertEqual(schema.get("format"), "date")

    def test_null_schema_defaults_are_nullable(self):
        document = read_openapi()

        def schema_objects(
            schema: dict, location: str
        ) -> Iterator[Tuple[str, dict]]:
            yield location, schema
            for keyword in ("items", "additionalProperties", "not"):
                child = schema.get(keyword)
                if isinstance(child, dict):
                    yield from schema_objects(child, f"{location}.{keyword}")
            for name, child in schema.get("properties", {}).items():
                yield from schema_objects(child, f"{location}.properties.{name}")
            for keyword in ("oneOf", "anyOf", "allOf"):
                for index, child in enumerate(schema.get(keyword, [])):
                    yield from schema_objects(child, f"{location}.{keyword}[{index}]")

        offenders = [
            location
            for name, schema in document["components"]["schemas"].items()
            for location, schema in schema_objects(
                schema, f"$.components.schemas.{name}"
            )
            if schema.get("default", object()) is None
            and schema.get("nullable") is not True
        ]
        self.assertEqual(
            offenders,
            [],
            f"{len(offenders)} Schema Objects declare default:null without "
            f"nullable:true:\n" + "\n".join(offenders),
        )

    def test_schema_default_and_example_values_match_declared_types(self):
        document = read_openapi()
        python_types = {
            "array": (list,),
            "boolean": (bool,),
            "integer": (int,),
            "number": (int, float),
            "object": (dict,),
            "string": (str,),
        }
        mismatches = []

        for location, schema in walk(document):
            if not isinstance(schema, dict) or schema.get("type") not in python_types:
                continue
            schema_type = schema["type"]
            for annotation in ("default", "example"):
                if annotation not in schema or schema[annotation] is None:
                    continue
                value = schema[annotation]
                matches = isinstance(value, python_types[schema_type])
                if schema_type in {"integer", "number"} and isinstance(value, bool):
                    matches = False
                if not matches:
                    mismatches.append(
                        f"{location}.{annotation}: expected {schema_type}, "
                        f"got {type(value).__name__} ({value!r})"
                    )

        self.assertEqual(
            mismatches,
            [],
            f"{len(mismatches)} default/example type mismatches:\n"
            + "\n".join(mismatches),
        )

    def test_preserves_all_41_vendor_schemas(self):
        document = read_openapi()
        self.assertEqual(len(document["components"]["schemas"]), 41)

    def test_uses_only_the_explicit_vendor_server(self):
        document = read_openapi()
        self.assertEqual(
            document["servers"],
            [{"url": "https://fight-api-v2.herokuapp.com"}],
        )

    def test_declares_bearer_jwt_and_requires_it_on_every_operation(self):
        document = read_openapi()
        self.assertEqual(
            document["components"]["securitySchemes"],
            {
                "bearer": {
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "type": "http",
                }
            },
        )
        for path, path_item in document["paths"].items():
            with self.subTest(path=path):
                self.assertEqual(path_item["get"].get("security"), [{"bearer": []}])

    def test_all_references_are_internal_and_resolve(self):
        document = read_openapi()
        references = [
            value
            for _, node in walk(document)
            if isinstance(node, dict)
            for key, value in node.items()
            if key == "$ref"
        ]
        self.assertTrue(references)
        for reference in references:
            with self.subTest(reference=reference):
                self.assertIsNotNone(resolve_json_pointer(document, reference))

    def test_contains_no_hardcoded_authorization_or_credential_secret(self):
        artifacts = {
            path.name: path.read_text(encoding="utf-8")
            for path in (INSTALL_PATH, DESCRIPTOR_PATH, OPENAPI_PATH)
        }
        for name, text in artifacts.items():
            with self.subTest(artifact=name):
                self.assertIsNone(
                    re.search(r"(?i)authorization\s*[:=]\s*bearer\s+\S+", text)
                )
                self.assertIsNone(re.search(r"\beyJ[A-Za-z0-9_-]+\.", text))

        document = read_openapi()
        credential_fields = [
            location
            for location, node in walk(document)
            if isinstance(node, dict)
            for key in node
            if key.casefold() in CREDENTIAL_KEYS
        ]
        self.assertEqual(credential_fields, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
