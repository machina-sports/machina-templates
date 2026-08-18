"""Offline contract tests for the Fight Analytics REST connector."""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import unittest
from pathlib import Path
from typing import Any, Iterator, Tuple
from urllib.parse import urlsplit
from unittest.mock import patch

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
CONNECTOR_DIR = REPO_ROOT / "connectors" / "fight-analytics"
INSTALL_PATH = CONNECTOR_DIR / "_install.yml"
DESCRIPTOR_PATH = CONNECTOR_DIR / "fight-analytics.yml"
OPENAPI_PATH = CONNECTOR_DIR / "fight-analytics.json"
AUTH_DESCRIPTOR_PATH = CONNECTOR_DIR / "fight-analytics-auth.yml"
AUTH_OPENAPI_PATH = CONNECTOR_DIR / "fight-analytics-auth.json"
STATISTICS_DESCRIPTOR_PATH = CONNECTOR_DIR / "fight-analytics-statistics.yml"
STATISTICS_OPENAPI_PATH = CONNECTOR_DIR / "fight-analytics-statistics.json"
SMOKE_DESCRIPTOR_PATH = CONNECTOR_DIR / "fight-analytics-certified.yml"
SMOKE_SCRIPT_PATH = CONNECTOR_DIR / "fight-analytics-certified.py"
SMOKE_WORKFLOW_PATH = CONNECTOR_DIR / "fight-analytics-certified-smoke.yml"
FANTASY_WORKFLOW_PATH = CONNECTOR_DIR / "fight-analytics-fantasy-canary.yml"
FANTASY_SHAPE_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "fight-analytics-sanitized-shapes.json"

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
    "/one/events",
    "/one/events/{oneEventId}",
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
    "/one/events": "listOneEvents",
    "/one/events/{oneEventId}": "getOneEvent",
}
AUTH_OPERATIONS = {
    "/auth/login": ("post", "AuthController_login"),
    "/auth/login/api-key": ("post", "AuthController_loginViaApiKey"),
    "/auth/refresh": ("post", "AuthController_refresh"),
    "/auth/me": ("get", "AuthController_me"),
    "/health": ("get", "HealthController_check"),
}
STATISTICS_OPERATIONS = {
    "/actions": "ActionsController_getActions",
    "/fighters/{id}": "FightersController_getFighterStats",
    "/fighters/{id}/career": "FightersController_getCareerSummary",
    "/fights/{id}": "FightsController_getFight",
    "/fights/{id}/totals": "FightsController_getFightTotals",
    "/fights/{id}/rounds": "FightsController_getFightRounds",
    "/fights/{id}/rounds/{roundNumber}": "FightsController_getFightRound",
}
EXPECTED_NULLABLE_PROPERTIES = {
    ("DuplicateFighterItemDto", "country"),
    ("DuplicateFighterItemDto", "legacyId"),
    ("DuplicateFighterItemDto", "nickname"),
    ("DuplicateFighterItemDto", "profileImageUrl"),
    ("DuplicateFighterItemDto", "sport"),
    ("DuplicateFighterItemDto", "weightClass"),
    ("Event", "deletedAt"),
    ("Event", "deletedBy"),
    ("Event", "oneEventId"),
    ("Event", "syncError"),
    ("Fight", "deletedAt"),
    ("Fight", "deletedBy"),
    ("Fight", "finishedAtRound"),
    ("Fight", "oneFightId"),
    ("Fight", "roundTime"),
    ("Fight", "syncError"),
    ("Fight", "weightClass"),
    ("Fighter", "age"),
    ("Fighter", "createdBy"),
    ("Fighter", "dateOfBirth"),
    ("Fighter", "deletedAt"),
    ("Fighter", "deletedBy"),
    ("Fighter", "fullBodyImageUrl"),
    ("Fighter", "nickname"),
    ("Fighter", "pictures"),
    ("Fighter", "profileImageUrl"),
    ("Fighter", "promotionId"),
    ("Fighter", "syncError"),
    ("Fighter", "teamId"),
    ("Fighter", "weight"),
    ("Fighter", "weightClass"),
    ("Fighter", "yearOfBirth"),
    ("GetOneEventDto", "deletedAt"),
    ("GetOneEventDto", "deletedBy"),
    ("GetOneEventDto", "oneEventId"),
    ("GetOneEventDto", "syncError"),
    ("GetOneFightDto", "deletedAt"),
    ("GetOneFightDto", "deletedBy"),
    ("GetOneFightDto", "finishedAtRound"),
    ("GetOneFightDto", "oneFightId"),
    ("GetOneFightDto", "roundTime"),
    ("GetOneFightDto", "syncError"),
    ("GetOneFightDto", "weightClass"),
    ("GetOneFighterDto", "deletedAt"),
    ("GetOneFighterDto", "deletedBy"),
    ("GetOneFighterDto", "fullBodyImageUrl"),
    ("GetOneFighterDto", "pictures"),
    ("GetOneFighterDto", "profileImageUrl"),
    ("GetOneFighterDto", "syncError"),
    ("GetOneFighterDto", "teamId"),
    ("GetOneFighterDto", "yearOfBirth"),
    ("PaginationPropsDto", "nextPage"),
    ("PaginationPropsDto", "prevPage"),
    ("Promotion", "createdBy"),
    ("Promotion", "deletedAt"),
    ("Promotion", "deletedBy"),
    ("Promotion", "label"),
    ("Promotion", "syncError"),
    ("Promotion", "updatedBy"),
    ("Team", "deletedAt"),
    ("Team", "deletedBy"),
    ("Team", "syncError"),
    ("Venue", "createdBy"),
    ("Venue", "deletedAt"),
    ("Venue", "deletedBy"),
    ("Venue", "syncError"),
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


def read_openapi(path: Path = OPENAPI_PATH) -> dict:
    with path.open(encoding="utf-8") as stream:
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
    def test_descriptor_and_install_manifest_register_connector(self):
        self.assertTrue(DESCRIPTOR_PATH.is_file(), f"absent: {DESCRIPTOR_PATH}")
        self.assertTrue(INSTALL_PATH.is_file(), f"absent: {INSTALL_PATH}")

        descriptor = read_yaml(DESCRIPTOR_PATH)
        connector = descriptor["connector"]
        self.assertEqual(connector["name"], "fight-analytics")
        self.assertEqual(connector["filename"], OPENAPI_PATH.name)
        self.assertEqual(connector["filetype"], "restapi")

        install = read_yaml(INSTALL_PATH)
        self.assertEqual(install["datasets"], [
            {"type": "connector", "path": "fight-analytics.yml"},
            {"type": "connector", "path": "fight-analytics-auth.yml"},
            {"type": "connector", "path": "fight-analytics-statistics.yml"},
            {"type": "connector", "path": "fight-analytics-certified.yml"},
            {"type": "workflow", "path": "fight-analytics-certified-smoke.yml"},
            {"type": "workflow", "path": "fight-analytics-fantasy-canary.yml"},
        ])

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
        self.assertEqual(len(set(operation_ids.values())), 14)

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

    def test_null_example_schemas_are_nullable(self):
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
            if "example" in schema and schema["example"] is None
            and schema.get("nullable") is not True
        ]
        self.assertEqual(
            offenders,
            [],
            f"{len(offenders)} Schema Objects declare example:null without "
            f"nullable:true:\n" + "\n".join(offenders),
        )

    def test_swagger_documentation_fixture_validates_against_get_one_fight_dto(self):
        document = read_openapi()
        fixture_path = CONNECTOR_DIR / "swagger-documentation-evidence-fight-dto.json"
        with fixture_path.open(encoding="utf-8") as f:
            fixture = json.load(f)

        from jsonschema import RefResolver, Draft7Validator
        import copy

        document_js = copy.deepcopy(document)

        def make_nullable_compatible(schema):
            if not isinstance(schema, dict):
                return
            if schema.get("nullable") is True and "type" in schema:
                t = schema["type"]
                if isinstance(t, list):
                    if "null" not in t:
                        schema["type"] = t + ["null"]
                else:
                    schema["type"] = [t, "null"]
            for k, v in schema.items():
                if isinstance(v, dict):
                    make_nullable_compatible(v)
                elif isinstance(v, list):
                    for item in v:
                        make_nullable_compatible(item)

        make_nullable_compatible(document_js)

        schema = document_js["components"]["schemas"]["GetOneFightDto"]
        resolver = RefResolver.from_schema(document_js)
        validator = Draft7Validator(schema, resolver=resolver)

        errors = list(validator.iter_errors(fixture))
        error_msgs = [f"{err.message} at {list(err.path)}" for err in errors]
        self.assertEqual(
            errors,
            [],
            f"Swagger documentation fixture has {len(errors)} validation errors:\n"
            + "\n".join(error_msgs),
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

    def test_preserves_all_49_vendor_schemas(self):
        document = read_openapi()
        self.assertEqual(len(document["components"]["schemas"]), 49)

    def test_uses_only_the_explicit_vendor_server(self):
        document = read_openapi()
        self.assertEqual(
            document["servers"],
            [{"url": "https://api.fightanalytics.cc"}],
        )

    def test_nullable_normalization_is_limited_to_documented_vendor_fields_and_authenticated_evidence(self):
        document = read_openapi()
        actual = {
            (schema_name, property_name)
            for schema_name, schema in document["components"]["schemas"].items()
            for property_name, prop in schema.get("properties", {}).items()
            if prop.get("nullable") is True
        }
        self.assertEqual(actual, EXPECTED_NULLABLE_PROPERTIES)

    def test_one_event_operations_are_documented_but_not_certified_for_scope(self):
        document = read_openapi()
        self.assertEqual(
            document["paths"]["/one/events"]["get"]["x-certification"],
            {"status": "unverified-forbidden", "failureCode": "SCOPE_FORBIDDEN"},
        )
        self.assertEqual(
            document["paths"]["/one/events/{oneEventId}"]["get"]["x-certification"],
            {"status": "unverified", "failureCode": "SCOPE_UNVERIFIED"},
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


class TestFightAnalyticsAdditionalRestConnectors(unittest.TestCase):
    def test_descriptors_parse_and_reference_their_openapi_documents(self):
        expected = {
            AUTH_DESCRIPTOR_PATH: ("fight-analytics-auth", AUTH_OPENAPI_PATH),
            STATISTICS_DESCRIPTOR_PATH: (
                "fight-analytics-statistics",
                STATISTICS_OPENAPI_PATH,
            ),
        }
        for descriptor_path, (name, openapi_path) in expected.items():
            with self.subTest(descriptor=descriptor_path.name):
                descriptor = read_yaml(descriptor_path)["connector"]
                self.assertEqual(descriptor["name"], name)
                self.assertEqual(descriptor["filename"], openapi_path.name)
                self.assertEqual(descriptor["filetype"], "restapi")
                self.assertEqual(read_openapi(openapi_path)["openapi"], "3.0.0")

    def test_auth_surface_and_bearer_contract_match_public_spec(self):
        document = read_openapi(AUTH_OPENAPI_PATH)
        self.assertEqual(
            document["servers"],
            [{"url": "https://auth-api.fightanalytics.cc"}],
        )
        self.assertEqual(len(document["components"]["schemas"]), 3)
        self.assertEqual(set(document["paths"]), set(AUTH_OPERATIONS))
        for path, (method, operation_id) in AUTH_OPERATIONS.items():
            operation = document["paths"][path][method]
            self.assertEqual(operation["operationId"], operation_id)
            expected_security = [{"bearer": []}] if path == "/auth/me" else None
            self.assertEqual(operation.get("security"), expected_security)
        self.assertEqual(document["components"]["securitySchemes"]["bearer"], {
            "scheme": "bearer", "bearerFormat": "JWT", "type": "http"
        })

    def test_statistics_surface_and_bearer_contract_match_public_spec(self):
        document = read_openapi(STATISTICS_OPENAPI_PATH)
        self.assertEqual(
            document["servers"],
            [{"url": "https://mike-goldberg-v2.fightanalytics.cc"}],
        )
        self.assertEqual(len(document["components"]["schemas"]), 9)
        self.assertEqual(set(document["paths"]), set(STATISTICS_OPERATIONS))
        for path, operation_id in STATISTICS_OPERATIONS.items():
            operation = document["paths"][path]["get"]
            self.assertEqual(operation["operationId"], operation_id)
            self.assertEqual(operation.get("security"), [{"bearer": []}])

    def test_bearer_secured_operations_do_not_declare_authorization_headers(self):
        for openapi_path in (OPENAPI_PATH, AUTH_OPENAPI_PATH, STATISTICS_OPENAPI_PATH):
            document = read_openapi(openapi_path)
            for path, path_item in document["paths"].items():
                for method in set(path_item) & HTTP_METHODS:
                    operation = path_item[method]
                    if {"bearer": []} not in operation.get("security", []):
                        continue
                    authorization_headers = [
                        parameter
                        for parameter in operation.get("parameters", [])
                        if parameter.get("in") == "header"
                        and parameter.get("name", "").casefold() == "authorization"
                    ]
                    with self.subTest(
                        document=openapi_path.name, path=path, method=method
                    ):
                        self.assertEqual(authorization_headers, [])

    def test_every_reference_in_all_openapi_documents_resolves(self):
        for path in (OPENAPI_PATH, AUTH_OPENAPI_PATH, STATISTICS_OPENAPI_PATH):
            document = read_openapi(path)
            for _, node in walk(document):
                if isinstance(node, dict) and "$ref" in node:
                    self.assertIsNotNone(resolve_json_pointer(document, node["$ref"]))

    def test_all_documents_use_valid_openapi_schema_types_and_annotations(self):
        valid_types = {"array", "boolean", "integer", "number", "object", "string"}
        python_types = {
            "array": (list,), "boolean": (bool,), "integer": (int,),
            "number": (int, float), "object": (dict,), "string": (str,),
        }
        for path in (OPENAPI_PATH, AUTH_OPENAPI_PATH, STATISTICS_OPENAPI_PATH):
            document = read_openapi(path)
            for location, node in walk(document):
                if (
                    not isinstance(node, dict)
                    or "type" not in node
                    or ".securitySchemes." in location
                ):
                    continue
                with self.subTest(document=path.name, location=location):
                    self.assertIn(node["type"], valid_types)
                schema_type = node["type"]
                for annotation in ("default", "example"):
                    value = node.get(annotation)
                    if value is None:
                        continue
                    matches = isinstance(value, python_types[schema_type])
                    if schema_type in {"integer", "number"} and isinstance(value, bool):
                        matches = False
                    with self.subTest(
                        document=path.name, location=location, annotation=annotation
                    ):
                        self.assertTrue(matches)


class FakeResponse:
    def __init__(self, status_code: int, payload: Any):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class TestFightAnalyticsCertifiedSmoke(unittest.TestCase):
    USERNAME = "cert-user-canary"
    PASSWORD = "cert-password-canary"
    ACCESS = "access-token-canary"
    REFRESH = "refresh-token-canary"
    NEW_ACCESS = "new-access-token-canary"
    NEW_REFRESH = "new-refresh-token-canary"
    SAFE_FAILURE_CODES = {
        "BAD_REQUEST", "UNAUTHORIZED", "FORBIDDEN", "NOT_FOUND", "CONFLICT",
        "INVALID_REQUEST", "RATE_LIMITED", "SERVER_ERROR", "UNEXPECTED_STATUS",
        "NETWORK_ERROR", "INVALID_RESPONSE", "MISSING_REQUIRED_ID",
        "MISSING_CREDENTIALS", "INVALID_AUTH_RESPONSE", "SCOPE_FORBIDDEN",
        "SCOPE_UNVERIFIED",
    }

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "fight_analytics_certified", SMOKE_SCRIPT_PATH
        )
        cls.smoke = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.smoke)

    def fake_request(self, method, url, **kwargs):
        path = urlsplit(url).path
        if (method, path) == ("POST", "/auth/login"):
            self.assertEqual(kwargs["json"], {
                "username": self.USERNAME,
                "password": self.PASSWORD,
            })
            return FakeResponse(201, {
                "accessToken": self.ACCESS,
                "refreshToken": self.REFRESH,
            })
        if (method, path) == ("GET", "/auth/me"):
            self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {self.ACCESS}")
            return FakeResponse(200, {"id": "user-id", "role": "reader"})
        if (method, path) == ("POST", "/auth/refresh"):
            self.assertEqual(kwargs["json"], {"token": self.REFRESH})
            return FakeResponse(201, {
                "accessToken": self.NEW_ACCESS,
                "refreshToken": self.NEW_REFRESH,
            })
        self.assertEqual(
            kwargs["headers"]["Authorization"], f"Bearer {self.NEW_ACCESS}"
        )
        if path == "/one/events":
            return FakeResponse(403, {"message": self.PASSWORD})
        if path.startswith("/stats/") or path == "/actions":
            return FakeResponse(200, [])
        if path.count("/") == 1:
            resource = path[1:]
            return FakeResponse(200, {
                "data": [{"id": f"{resource}-id"}],
                "pagination": {"total": 1},
            })
        return FakeResponse(200, {"id": path.rsplit("/", 1)[-1]})

    def test_static_command_and_flat_vault_backed_workflow_inputs(self):
        descriptor = read_yaml(SMOKE_DESCRIPTOR_PATH)["connector"]
        self.assertEqual(descriptor["name"], "fight-analytics-certified")
        self.assertEqual(descriptor["filename"], SMOKE_SCRIPT_PATH.name)
        self.assertEqual(descriptor["filetype"], "pyscript")
        self.assertEqual(
            descriptor["commands"],
            [
                {"name": "Certified smoke", "value": "run_certified_smoke"},
                {
                    "name": "Fantasy scenarios canary",
                    "value": "run_fantasy_scenarios",
                },
            ],
        )

        workflow = read_yaml(SMOKE_WORKFLOW_PATH)["workflow"]
        self.assertEqual(workflow["name"], "fight-analytics-certified-smoke")
        task = workflow["tasks"][0]
        connector_name = task["connector"]["name"]
        non_debug_context_keys = set(workflow["context-variables"]) - {"debugger"}
        self.assertEqual(non_debug_context_keys, {connector_name})
        self.assertEqual(workflow["context-variables"][connector_name], {
            "username": "$TEMP_CONTEXT_VARIABLE_FIGHT_ANALYTICS_USERNAME",
            "password": "$TEMP_CONTEXT_VARIABLE_FIGHT_ANALYTICS_PASSWORD",
        })
        self.assertNotIn("agent", workflow)
        self.assertNotIn("schedule", workflow)
        self.assertEqual(len(workflow["tasks"]), 1)
        self.assertEqual(task["connector"], {
            "name": "fight-analytics-certified",
            "command": "run_certified_smoke",
        })
        self.assertEqual(set(task["inputs"]), {"username", "password"})
        self.assertTrue(all(not isinstance(value, dict) for value in task["inputs"].values()))

    def test_success_covers_auth_authorized_metadata_forbidden_one_and_all_statistics(self):
        with patch.object(self.smoke.requests, "request", side_effect=self.fake_request) as request:
            result = self.smoke.run_certified_smoke({"params": {
                "username": self.USERNAME,
                "password": self.PASSWORD,
            }})

        self.assertIs(result["status"], True)
        receipts = result["data"]["operations"]
        expected = [
            "POST /auth/login", "GET /auth/me", "POST /auth/refresh",
            "GET /promotions", "GET /promotions/{id}",
            "GET /venues", "GET /venues/{id}",
            "GET /teams", "GET /teams/{id}",
            "GET /events", "GET /events/{id}",
            "GET /fighters", "GET /fighters/{id}",
            "GET /fights", "GET /fights/{id}",
            "GET /one/events", "GET /one/events/{oneEventId}",
            "GET /stats/actions", "GET /stats/fighters/{id}",
            "GET /stats/fighters/{id}/career", "GET /stats/fights/{id}",
            "GET /stats/fights/{id}/totals", "GET /stats/fights/{id}/rounds",
            "GET /stats/fights/{id}/rounds/{roundNumber}",
        ]
        receipt_operations = [receipt["operation"] for receipt in receipts]
        self.assertEqual(len(receipts), 24)
        self.assertEqual(len(set(receipt_operations)), 24)
        self.assertEqual(receipt_operations, expected)
        expected_urls = [
            "https://auth-api.fightanalytics.cc/auth/login",
            "https://auth-api.fightanalytics.cc/auth/me",
            "https://auth-api.fightanalytics.cc/auth/refresh",
            "https://api.fightanalytics.cc/promotions",
            "https://api.fightanalytics.cc/promotions/promotions-id",
            "https://api.fightanalytics.cc/venues",
            "https://api.fightanalytics.cc/venues/venues-id",
            "https://api.fightanalytics.cc/teams",
            "https://api.fightanalytics.cc/teams/teams-id",
            "https://api.fightanalytics.cc/events",
            "https://api.fightanalytics.cc/events/events-id",
            "https://api.fightanalytics.cc/fighters",
            "https://api.fightanalytics.cc/fighters/fighters-id",
            "https://api.fightanalytics.cc/fights",
            "https://api.fightanalytics.cc/fights/fights-id",
            "https://api.fightanalytics.cc/one/events",
            "https://mike-goldberg-v2.fightanalytics.cc/actions",
            "https://mike-goldberg-v2.fightanalytics.cc/fighters/fighters-id",
            "https://mike-goldberg-v2.fightanalytics.cc/fighters/fighters-id/career",
            "https://mike-goldberg-v2.fightanalytics.cc/fights/fights-id",
            "https://mike-goldberg-v2.fightanalytics.cc/fights/fights-id/totals",
            "https://mike-goldberg-v2.fightanalytics.cc/fights/fights-id/rounds",
            "https://mike-goldberg-v2.fightanalytics.cc/fights/fights-id/rounds/1",
        ]
        self.assertEqual(
            [call.args[1] for call in request.call_args_list], expected_urls
        )
        one_receipts = [r for r in receipts if r["operation"].startswith("GET /one/")]
        self.assertEqual(
            [r.get("failureCode") for r in one_receipts],
            ["SCOPE_FORBIDDEN", "SCOPE_UNVERIFIED"],
        )
        self.assertEqual(request.call_count, 23)
        self.assert_secret_free(result)

    def test_secrets_never_escape_network_or_invalid_json_failures(self):
        def fail(method, url, **kwargs):
            if url.endswith("/auth/login"):
                raise RuntimeError(
                    f"request failed {self.USERNAME} {self.PASSWORD} {self.ACCESS}"
                )
            return FakeResponse(500, ValueError(self.REFRESH))

        with patch.object(self.smoke.requests, "request", side_effect=fail):
            result = self.smoke.run_certified_smoke({"params": {
                "username": self.USERNAME,
                "password": self.PASSWORD,
            }})
        self.assertIs(result["status"], False)
        self.assert_secret_free(result)

    def test_issued_tokens_never_escape_a_later_secret_bearing_failure(self):
        def fail_after_login(method, url, **kwargs):
            if url.endswith("/auth/login"):
                return FakeResponse(201, {
                    "accessToken": self.ACCESS,
                    "refreshToken": self.REFRESH,
                })
            raise RuntimeError(
                f"failed with {self.PASSWORD} {self.ACCESS} {self.REFRESH}"
            )

        with patch.object(self.smoke.requests, "request", side_effect=fail_after_login):
            result = self.smoke.run_certified_smoke({"params": {
                "username": self.USERNAME,
                "password": self.PASSWORD,
            }})
        self.assertIs(result["status"], False)
        self.assert_secret_free(result)

    def test_refresh_requires_both_access_and_refresh_tokens(self):
        for missing_key in ("accessToken", "refreshToken"):
            with self.subTest(missing_key=missing_key):
                def missing_refresh_token(method, url, **kwargs):
                    response = self.fake_request(method, url, **kwargs)
                    if url.endswith("/auth/refresh"):
                        payload = {
                            "accessToken": self.NEW_ACCESS,
                            "refreshToken": self.NEW_REFRESH,
                        }
                        payload.pop(missing_key)
                        return FakeResponse(201, payload)
                    return response

                with patch.object(
                    self.smoke.requests,
                    "request",
                    side_effect=missing_refresh_token,
                ):
                    result = self.smoke.run_certified_smoke({"params": {
                        "username": self.USERNAME,
                        "password": self.PASSWORD,
                    }})

                self.assertIs(result["status"], False)
                self.assertEqual(
                    result["data"]["operations"][-1]["failureCode"],
                    "INVALID_AUTH_RESPONSE",
                )
                self.assert_secret_free(result)

    def test_refresh_requires_both_access_and_refresh_tokens(self):
        def missing_refresh_token(method, url, **kwargs):
            response = self.fake_request(method, url, **kwargs)
            if urlsplit(url).path == "/auth/refresh":
                return FakeResponse(201, {"accessToken": self.NEW_ACCESS})
            return response

        with patch.object(
            self.smoke.requests, "request", side_effect=missing_refresh_token
        ):
            result = self.smoke.run_certified_smoke({"params": {
                "username": self.USERNAME,
                "password": self.PASSWORD,
            }})

        self.assertIs(result["status"], False)
        self.assertEqual(result["data"]["operations"][-1], {
            "operation": "POST /auth/refresh",
            "status": 201,
            "shape": "object",
            "count": 1,
            "failureCode": "INVALID_AUTH_RESPONSE",
        })
        self.assert_secret_free(result)

    def assert_secret_free(self, result):
        serialized = json.dumps(result, sort_keys=True)
        for secret in (
            self.USERNAME, self.PASSWORD, self.ACCESS, self.REFRESH,
            self.NEW_ACCESS, self.NEW_REFRESH,
        ):
            self.assertNotIn(secret, serialized)
        self.assertEqual(set(result["data"]), {"operations"})
        allowed_keys = {"operation", "status", "shape", "count", "failureCode"}
        for receipt in result["data"]["operations"]:
            self.assertLessEqual(set(receipt), allowed_keys)
            if "failureCode" in receipt:
                self.assertIn(receipt["failureCode"], self.SAFE_FAILURE_CODES)


class TestFightAnalyticsFantasyCanary(unittest.TestCase):
    USERNAME = "fantasy-user-canary"
    PASSWORD = "fantasy-password-canary"
    ACCESS = "fantasy-access-token"
    REFRESH = "fantasy-refresh-token"
    NEW_ACCESS = "fantasy-new-access-token"
    NEW_REFRESH = "fantasy-new-refresh-token"
    PROVIDER_SECRET = "provider-secret-must-not-escape"
    RECEIPT_KEYS = {
        "endpoint", "classification", "httpStatus", "shape", "count",
        "failureCode", "providerEventId", "providerFightId", "providerFighterId",
    }
    COUNT_KEYS = {
        "dataSuccess", "providerEmpty", "unavailable", "failed", "classification",
    }
    METRIC_KEYS = {
        "score", "significantStrikes", "totalStrikes", "takedowns",
        "takedownAttempts", "submissionAttempts", "knockdowns",
        "elapsedControlTime",
    }

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "fight_analytics_fantasy", SMOKE_SCRIPT_PATH
        )
        cls.connector = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.connector)
        with FANTASY_SHAPE_FIXTURE_PATH.open(encoding="utf-8") as stream:
            cls.shapes = json.load(stream)

    def _fighter(self, fighter_id, first_name, last_name, wins, losses, draws):
        fighter = copy.deepcopy(self.shapes["fighter"])
        fighter.update({
            "id": fighter_id, "firstName": first_name, "lastName": last_name,
            "wins": wins, "losses": losses, "draws": draws,
            "accessToken": self.PROVIDER_SECRET,
        })
        return fighter

    def _fight(self, index):
        fight = copy.deepcopy(self.shapes["fight"])
        fight.update({
            "id": f"fight-{index:02d}",
            "eventId": "event-01",
            "event": self._event(),
            "redCornerId": "red-01",
            "blueCornerId": "blue-01",
            "redCorner": self._fighter("red-01", "Red", "Corner", 12, 2, 1),
            "blueCorner": self._fighter("blue-01", "Blue", "Corner", 10, 3, 0),
        })
        return fight

    def _event(self):
        event = copy.deepcopy(self.shapes["event"])
        event.update({
            "id": "event-01", "name": "Synthetic Event", "date": "2000-01-01",
            "password": self.PROVIDER_SECRET,
        })
        return event

    def _collection(self, data):
        collection = copy.deepcopy(self.shapes["collection"])
        collection["data"] = data
        collection["pagination"]["total"] = len(data)
        return collection

    def _fighter_stats(self, wins, losses, draws):
        stats = copy.deepcopy(self.shapes["fighterStats"])
        metrics = copy.deepcopy(stats["standing"])
        metrics["credentials"] = self.PROVIDER_SECRET
        stats.update({
            "wins": wins, "losses": losses, "draws": draws,
            "score": 90, "elapsedFightTime": 1234, "totalRounds": 20,
            "standing": copy.deepcopy(metrics), "ground": copy.deepcopy(metrics),
            "fence": copy.deepcopy(metrics), "riding": copy.deepcopy(metrics),
        })
        return stats

    def _fight_summary(self, fight_id):
        summary = copy.deepcopy(self.shapes["fightSummary"])
        summary.update({
            "fightNewId": fight_id, "status": "finished", "currentRound": 3,
            "currentStance": "standing",
        })
        return summary

    def fake_request(self, method, url, **kwargs):
        host = urlsplit(url).netloc
        path = urlsplit(url).path
        if host == "auth-api.fightanalytics.cc":
            if path == "/auth/login":
                return FakeResponse(201, {
                    "accessToken": self.ACCESS, "refreshToken": self.REFRESH,
                })
            if path == "/auth/me":
                return FakeResponse(200, {"id": "user-1"})
            if path == "/auth/refresh":
                return FakeResponse(201, {
                    "accessToken": self.NEW_ACCESS, "refreshToken": self.NEW_REFRESH,
                })
        self.assertEqual(kwargs["headers"]["Authorization"], f"Bearer {self.NEW_ACCESS}")
        if host == "api.fightanalytics.cc":
            if path == "/events":
                return FakeResponse(200, self._collection([self._event()]))
            if path == "/events/event-01":
                return FakeResponse(200, self._event())
            if path == "/fights":
                return FakeResponse(200, self._collection([self._fight(i) for i in range(12)]))
            if re.fullmatch(r"/fights/fight-\d{2}", path):
                return FakeResponse(200, self._fight(int(path.rsplit("-", 1)[-1])))
            if path == "/fighters/red-01":
                return FakeResponse(200, self._fighter("red-01", "Red", "Corner", 12, 2, 1))
            if path == "/fighters/blue-01":
                return FakeResponse(200, self._fighter("blue-01", "Blue", "Corner", 10, 3, 0))
        if host == "mike-goldberg-v2.fightanalytics.cc":
            if path == "/fighters/red-01":
                return FakeResponse(200, self._fighter_stats(12, 2, 1))
            if path == "/fighters/blue-01":
                return FakeResponse(200, self._fighter_stats(10, 3, 0))
            if path.endswith("/career"):
                return FakeResponse(200, {"author": {}, "token": self.PROVIDER_SECRET})
            if path == "/actions":
                return FakeResponse(200, self._collection([]))
            if re.fullmatch(r"/fights/fight-\d{2}/rounds/1", path):
                return FakeResponse(200, [])
            if path.endswith("/totals") or path.endswith("/rounds"):
                return FakeResponse(200, [])
            if re.fullmatch(r"/fights/fight-\d{2}", path):
                fight_id = path.rsplit("/", 1)[-1]
                return FakeResponse(200, self._fight_summary(fight_id))
        raise AssertionError(f"unexpected request: {method} {url}")

    def run_canary(self, side_effect=None, fight_id=None):
        with patch.object(
            self.connector.requests,
            "request",
            side_effect=side_effect or self.fake_request,
        ) as request:
            params = {
                "username": self.USERNAME,
                "password": self.PASSWORD,
            }
            if fight_id is not None:
                params["fight_id"] = fight_id
            result = self.connector.run_fantasy_scenarios({"params": params})
        return result, request

    def test_full_success_uses_verified_shapes_and_explicit_provider_empty(self):
        result, request = self.run_canary()

        self.assertIs(result["status"], True)
        packet = result["data"]
        self.assertEqual(packet["verdict"], "passed")
        self.assertIs(packet["fullPathExecuted"], True)
        self.assertEqual(packet["packetType"], "prototype_canary")
        self.assertEqual(packet["sampleLimit"], 10)
        self.assertEqual(packet["coverage"]["sampledFights"], 10)
        self.assertEqual(packet["coverage"]["fightSummary"], {
            "dataSuccess": 10, "providerEmpty": 0, "unavailable": 0,
            "failed": 0, "classification": "data_success",
        })
        for endpoint in ("totals", "rounds", "actions"):
            self.assertEqual(packet["coverage"][endpoint], {
                "dataSuccess": 0, "providerEmpty": 10, "unavailable": 0,
                "failed": 0, "classification": "provider_empty",
            })
        self.assertEqual(len(packet["fighters"]), 2)
        self.assertEqual(len(packet["fighterStats"]), 2)
        self.assertEqual(
            set(packet["fighterStats"][0]["metrics"]),
            {"standing", "ground", "fence", "riding"},
        )
        for metrics in packet["fighterStats"][0]["metrics"].values():
            self.assertEqual(set(metrics), self.METRIC_KEYS)
        self.assertEqual(packet["fightStats"]["finish"], {
            "type": "finish-label", "round": 3, "time": 245, "winnerId": 202,
        })
        self.assertEqual(packet["fightStats"]["fightersOutcomeCount"], 1)
        self.assertTrue(all(
            receipt["classification"] == "provider_empty"
            for receipt in packet["scenarios"]
            if receipt["endpoint"] in {"fight_totals", "fight_rounds", "fight_actions"}
        ))
        self.assertEqual(
            sum(1 for call in request.call_args_list if urlsplit(call.args[1]).path == "/actions"),
            10,
        )
        self.assertEqual(
            sum(
                1 for call in request.call_args_list
                if urlsplit(call.args[1]).path == "/events/event-01"
            ),
            1,
        )
        self.assert_secret_free(result)

    def test_populated_fight_summary_accepts_observed_numeric_finish_fields(self):
        summary = {
            "currentRound": 3,
            "currentStance": "standing",
            "fightId": 101,
            "fightNewId": "fight-03",
            "fightersOutcome": [{}],
            "finishRound": 3,
            "finishTime": 245,
            "finishType": "decision",
            "status": "finished",
            "winnerId": 202,
        }

        self.assertEqual(
            self.connector._fight_statistics(summary, "fight-03"),
            {
                "providerFightId": "fight-03",
                "status": "finished",
                "currentRound": 3,
                "currentStance": "standing",
                "finish": {
                    "type": "decision",
                    "round": 3,
                    "time": 245,
                    "winnerId": 202,
                },
                "fightersOutcomeCount": 1,
            },
        )

    def test_fight_summary_preserves_null_finish_fields_for_unfinished_fights(self):
        summary = copy.deepcopy(self.shapes["fightSummary"])
        summary.update({
            "fightNewId": "fight-03",
            "fightersOutcome": [],
            "finishRound": None,
            "finishTime": None,
            "finishType": None,
            "status": "in_progress",
            "winnerId": None,
        })

        projected = self.connector._fight_statistics(summary, "fight-03")

        self.assertEqual(projected["finish"], {
            "type": None, "round": None, "time": None, "winnerId": None,
        })
        self.assertEqual(projected["fightersOutcomeCount"], 0)

    def test_fight_summary_accepts_non_empty_string_finish_fields(self):
        summary = copy.deepcopy(self.shapes["fightSummary"])
        summary.update({
            "fightNewId": "fight-03",
            "finishTime": "04:05",
            "winnerId": "fighter-202",
        })

        projected = self.connector._fight_statistics(summary, "fight-03")

        self.assertEqual(projected["finish"]["time"], "04:05")
        self.assertEqual(projected["finish"]["winnerId"], "fighter-202")

    def test_fight_summary_accepts_integer_finish_time_without_float_coercion(self):
        summary = copy.deepcopy(self.shapes["fightSummary"])
        summary.update({
            "fightNewId": "fight-03",
            "finishTime": 10**400,
        })

        projected = self.connector._fight_statistics(summary, "fight-03")

        self.assertEqual(projected["finish"]["time"], 10**400)

    def test_fight_summary_rejects_invalid_finish_fields_and_outcomes(self):
        cases = (
            ("finishTime", float("inf")),
            ("finishTime", float("nan")),
            ("finishTime", ""),
            ("winnerId", -1),
            ("winnerId", 1.5),
            ("winnerId", ""),
            ("fightersOutcome", [None]),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                summary = copy.deepcopy(self.shapes["fightSummary"])
                summary["fightNewId"] = "fight-03"
                summary[field] = value

                self.assertIsNone(
                    self.connector._fight_statistics(summary, "fight-03")
                )

    def test_all_empty_fight_summaries_fail_the_verdict(self):
        def empty_summaries(method, url, **kwargs):
            path = urlsplit(url).path
            if urlsplit(url).netloc == "mike-goldberg-v2.fightanalytics.cc" and re.fullmatch(
                r"/fights/fight-\d{2}", path
            ):
                return FakeResponse(200, {})
            return self.fake_request(method, url, **kwargs)

        result, _ = self.run_canary(empty_summaries)
        self.assertIs(result["status"], False)
        self.assertEqual(result["data"]["verdict"], "failed")
        self.assertIs(result["data"]["fullPathExecuted"], False)
        self.assertEqual(result["data"]["coverage"]["fightSummary"], {
            "dataSuccess": 0, "providerEmpty": 10, "unavailable": 0,
            "failed": 0, "classification": "provider_empty",
        })
        self.assertIsNone(result["data"]["fightStats"]["status"])
        self.assert_secret_free(result)

    def test_missing_null_dict_and_list_variants_fail_closed_without_throwing(self):
        variants = [None, {}, {"data": None}, {"data": {}}, {"data": []}]
        for malformed in variants:
            with self.subTest(malformed=malformed):
                def malformed_events(method, url, **kwargs):
                    if urlsplit(url).netloc == "api.fightanalytics.cc" and urlsplit(url).path == "/events":
                        return FakeResponse(200, malformed)
                    return self.fake_request(method, url, **kwargs)

                result, _ = self.run_canary(malformed_events)
                self.assertIs(result["status"], False)
                self.assertIn(
                    result["data"]["scenarios"][-1]["failureCode"],
                    {"INVALID_SHAPE", "PROVIDER_EMPTY"},
                )
                self.assert_secret_free(result)

    def test_sanitized_structural_fixture_is_loaded_and_drives_responses(self):
        self.assertEqual(set(self.shapes), {
            "collection", "event", "fighter", "fight", "fighterStats", "fightSummary",
        })
        fixture_text = FANTASY_SHAPE_FIXTURE_PATH.read_text(encoding="utf-8")
        self.assertNotIn(self.PROVIDER_SECRET, fixture_text)
        self.assertNotRegex(
            fixture_text,
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        )
        self.assertEqual(self._fight(3)["id"], "fight-03")
        self.assertEqual(self._fight_summary("fight-03")["fightNewId"], "fight-03")

    def test_unpinned_selection_and_sample_are_stable_across_shuffled_provider_order(self):
        orders = [
            list(reversed(range(12))),
            [5, 1, 9, 0, 11, 3, 7, 2, 10, 4, 8, 6],
        ]
        selected = []
        queried = []
        for order in orders:
            def shuffled(method, url, **kwargs):
                if urlsplit(url).netloc == "api.fightanalytics.cc" and urlsplit(url).path == "/fights":
                    return FakeResponse(200, self._collection([self._fight(i) for i in order]))
                return self.fake_request(method, url, **kwargs)

            result, request = self.run_canary(shuffled)
            selected.append(result["data"]["fight"]["providerFightId"])
            queried.append([
                call.kwargs["params"]["fightNewId"]
                for call in request.call_args_list
                if urlsplit(call.args[1]).path == "/actions"
            ])

        self.assertEqual(selected, ["fight-00", "fight-00"])
        self.assertEqual(queried, [[f"fight-{index:02d}" for index in range(10)]] * 2)

    def test_flat_pinned_fight_id_is_repeatable_across_provider_order(self):
        selected = []
        for order in (list(range(12)), list(reversed(range(12)))):
            def shuffled(method, url, **kwargs):
                if urlsplit(url).netloc == "api.fightanalytics.cc" and urlsplit(url).path == "/fights":
                    return FakeResponse(200, self._collection([self._fight(i) for i in order]))
                return self.fake_request(method, url, **kwargs)

            result, _ = self.run_canary(shuffled, fight_id="fight-07")
            self.assertIs(result["status"], True)
            selected.append(result["data"]["fight"]["providerFightId"])

        self.assertEqual(selected, ["fight-07", "fight-07"])

    def test_event_detail_must_join_fight_event_id_and_embedded_event(self):
        def mismatched_event(method, url, **kwargs):
            if urlsplit(url).netloc == "api.fightanalytics.cc" and urlsplit(url).path == "/events/event-01":
                event = self._event()
                event["id"] = "different-event-id"
                return FakeResponse(200, event)
            return self.fake_request(method, url, **kwargs)

        result, _ = self.run_canary(mismatched_event)
        self.assertIs(result["status"], False)
        receipt = next(
            item for item in result["data"]["scenarios"]
            if item["endpoint"] == "event_detail"
        )
        self.assertEqual(receipt["failureCode"], "JOIN_MISMATCH")

    def test_collections_and_actions_require_dict_pagination(self):
        cases = (
            ("events", "/events", {"data": [self._event()]}),
            ("events", "/events", {"data": [self._event()], "pagination": []}),
            ("actions", "/actions", {"data": [], "pagination": None}),
        )
        for host_kind, path, payload in cases:
            with self.subTest(path=path, payload=payload):
                host = (
                    "api.fightanalytics.cc"
                    if host_kind == "events"
                    else "mike-goldberg-v2.fightanalytics.cc"
                )

                def malformed(method, url, **kwargs):
                    if urlsplit(url).netloc == host and urlsplit(url).path == path:
                        return FakeResponse(200, payload)
                    return self.fake_request(method, url, **kwargs)

                result, _ = self.run_canary(malformed)
                self.assertIs(result["status"], False)
                self.assertTrue(any(
                    item["failureCode"] == "INVALID_SHAPE"
                    for item in result["data"]["scenarios"]
                ))

    def test_non_empty_array_and_action_elements_must_be_objects(self):
        cases = (
            ("/actions", self._collection([None]), "fight_actions"),
            ("/fights/fight-00/totals", [None], "fight_totals"),
            ("/fights/fight-00/rounds", [None], "fight_rounds"),
        )
        for path, payload, endpoint in cases:
            with self.subTest(endpoint=endpoint):
                def malformed(method, url, **kwargs):
                    if (
                        urlsplit(url).netloc == "mike-goldberg-v2.fightanalytics.cc"
                        and urlsplit(url).path == path
                    ):
                        return FakeResponse(200, payload)
                    return self.fake_request(method, url, **kwargs)

                result, _ = self.run_canary(malformed)
                receipt = next(
                    item for item in result["data"]["scenarios"]
                    if item["endpoint"] == endpoint and item["providerFightId"] == "fight-00"
                )
                self.assertIs(result["status"], False)
                self.assertEqual(receipt["classification"], "failed")
                self.assertEqual(receipt["failureCode"], "INVALID_SHAPE")

    def test_unavailable_career_endpoint_fails_full_path(self):
        def unavailable_career(method, url, **kwargs):
            if (
                urlsplit(url).netloc == "mike-goldberg-v2.fightanalytics.cc"
                and urlsplit(url).path == "/fighters/red-01/career"
            ):
                return FakeResponse(404, {"message": "not available"})
            return self.fake_request(method, url, **kwargs)

        result, _ = self.run_canary(unavailable_career)
        self.assertIs(result["status"], False)
        self.assertEqual(result["data"]["verdict"], "failed")
        self.assertIs(result["data"]["fullPathExecuted"], False)

    def test_all_unavailable_fight_summaries_fail_the_verdict(self):
        def unavailable_summaries(method, url, **kwargs):
            if (
                urlsplit(url).netloc == "mike-goldberg-v2.fightanalytics.cc"
                and re.fullmatch(r"/fights/fight-\d{2}", urlsplit(url).path)
            ):
                return FakeResponse(404, {"message": "not available"})
            return self.fake_request(method, url, **kwargs)

        result, _ = self.run_canary(unavailable_summaries)
        self.assertIs(result["status"], False)
        self.assertEqual(result["data"]["coverage"]["fightSummary"], {
            "dataSuccess": 0, "providerEmpty": 0, "unavailable": 10,
            "failed": 0, "classification": "unavailable",
        })
        self.assertEqual(result["data"]["verdict"], "failed")
        self.assertIs(result["data"]["fullPathExecuted"], False)

    def test_refresh_requires_both_tokens_and_preserves_response_receipt(self):
        def missing_refresh_token(method, url, **kwargs):
            if urlsplit(url).path == "/auth/refresh":
                return FakeResponse(201, {"accessToken": self.NEW_ACCESS})
            return self.fake_request(method, url, **kwargs)

        result, _ = self.run_canary(missing_refresh_token)
        self.assertIs(result["status"], False)
        self.assertEqual(result["data"]["scenarios"][-1], {
            "endpoint": "fantasy refresh",
            "classification": "failed",
            "httpStatus": 201,
            "shape": "object",
            "count": 1,
            "failureCode": "INVALID_AUTH_RESPONSE",
            "providerEventId": None,
            "providerFightId": None,
            "providerFighterId": None,
        })

    def test_auth_failures_preserve_real_request_status_shape_and_count(self):
        cases = (
            ("/auth/login", 401, "fantasy authentication", "UNAUTHORIZED"),
            ("/auth/me", 403, "fantasy identity", "FORBIDDEN"),
            ("/auth/refresh", 500, "fantasy refresh", "SERVER_ERROR"),
        )
        for failed_path, status, endpoint, failure_code in cases:
            with self.subTest(path=failed_path):
                def auth_failure(method, url, **kwargs):
                    if urlsplit(url).path == failed_path:
                        return FakeResponse(status, {"message": "sanitized failure"})
                    return self.fake_request(method, url, **kwargs)

                result, _ = self.run_canary(auth_failure)
                self.assertIs(result["status"], False)
                self.assertEqual(result["data"]["scenarios"][-1], {
                    "endpoint": endpoint,
                    "classification": "failed",
                    "httpStatus": status,
                    "shape": "object",
                    "count": 1,
                    "failureCode": failure_code,
                    "providerEventId": None,
                    "providerFightId": None,
                    "providerFighterId": None,
                })

    def test_samples_at_most_ten_fights_and_sends_bounded_action_queries(self):
        result, request = self.run_canary()
        self.assertEqual(result["data"]["coverage"]["sampledFights"], 10)
        action_calls = [
            call for call in request.call_args_list
            if urlsplit(call.args[1]).netloc == "mike-goldberg-v2.fightanalytics.cc"
            and urlsplit(call.args[1]).path == "/actions"
        ]
        self.assertEqual(len(action_calls), 10)
        self.assertEqual(
            {call.kwargs["params"]["fightNewId"] for call in action_calls},
            {f"fight-{index:02d}" for index in range(10)},
        )

    def test_output_schema_is_stable_and_bounded(self):
        result, _ = self.run_canary()
        packet = result["data"]
        self.assertEqual(set(packet), {
            "packetType", "verdict", "fullPathExecuted", "sourceHosts", "limitations",
            "sampleLimit", "event", "fight", "fighters", "fighterStats",
            "fightStats", "scenarios", "coverage",
        })
        self.assertEqual(set(packet["event"]), {"providerEventId", "label", "date"})
        self.assertEqual(set(packet["fight"]), {
            "providerFightId", "providerEventId", "label", "redFighterId", "blueFighterId",
        })
        self.assertTrue(all(set(receipt) == self.RECEIPT_KEYS for receipt in packet["scenarios"]))
        self.assertLessEqual(len(packet["scenarios"]), 51)
        self.assertEqual(set(packet["coverage"]), {
            "sampledFights", "classification", "fightSummary", "totals", "rounds", "actions",
        })
        for key in ("fightSummary", "totals", "rounds", "actions"):
            self.assertEqual(set(packet["coverage"][key]), self.COUNT_KEYS)

    def test_workflow_uses_exact_vault_context_and_is_manual(self):
        workflow = read_yaml(FANTASY_WORKFLOW_PATH)["workflow"]
        self.assertEqual(workflow["name"], "fight-analytics-fantasy-canary")
        self.assertEqual(workflow["context-variables"], {
            "debugger": {"enabled": False},
            "fight-analytics-certified": {
                "username": "$TEMP_CONTEXT_VARIABLE_FIGHT_ANALYTICS_USERNAME",
                "password": "$TEMP_CONTEXT_VARIABLE_FIGHT_ANALYTICS_PASSWORD",
            },
        })
        self.assertNotIn("agent", workflow)
        self.assertNotIn("schedule", workflow)
        self.assertEqual(workflow["inputs"], {"fight_id": "$.get('fight_id', None)"})
        self.assertEqual(workflow["outputs"], {
            "canary_packet": "$.get('canary_packet', {})",
            "canary_verdict": "$.get('canary_verdict', 'failed')",
            "workflow-status": "'executed' if $.get('canary_verdict', 'failed') == 'passed' else 'failed'",
        })
        self.assertEqual(len(workflow["tasks"]), 1)
        task = workflow["tasks"][0]
        self.assertEqual(task["connector"], {
            "name": "fight-analytics-certified",
            "command": "run_fantasy_scenarios",
        })
        self.assertEqual(set(task["inputs"]), {"username", "password", "fight_id"})
        self.assertEqual(task["inputs"]["fight_id"], "$.get('fight_id', None)")
        self.assertEqual(task["outputs"], {
            "canary_packet": "$",
            "canary_verdict": "$.get('verdict', 'failed')",
        })

    def test_secrets_and_tokens_never_escape_success_or_failure(self):
        success, _ = self.run_canary()
        self.assert_secret_free(success)

        def secret_failure(method, url, **kwargs):
            if url.endswith("/auth/login"):
                return FakeResponse(201, {
                    "accessToken": self.ACCESS, "refreshToken": self.REFRESH,
                })
            raise RuntimeError(
                f"failure {self.PASSWORD} {self.ACCESS} {self.REFRESH} {self.PROVIDER_SECRET}"
            )

        failure, _ = self.run_canary(secret_failure)
        self.assertIs(failure["status"], False)
        self.assert_secret_free(failure)

    def test_certified_smoke_still_has_exactly_24_operations(self):
        smoke_case = TestFightAnalyticsCertifiedSmoke(methodName="test_success_covers_auth_authorized_metadata_forbidden_one_and_all_statistics")
        smoke_case.setUpClass()
        with patch.object(smoke_case.smoke.requests, "request", side_effect=smoke_case.fake_request):
            result = smoke_case.smoke.run_certified_smoke({"params": {
                "username": smoke_case.USERNAME,
                "password": smoke_case.PASSWORD,
            }})
        self.assertEqual(len(result["data"]["operations"]), 24)
        self.assertIs(result["status"], True)

    def assert_secret_free(self, result):
        serialized = json.dumps(result, sort_keys=True)
        for secret in (
            self.USERNAME, self.PASSWORD, self.ACCESS, self.REFRESH,
            self.NEW_ACCESS, self.NEW_REFRESH, self.PROVIDER_SECRET,
        ):
            self.assertNotIn(secret, serialized)
        self.assertNotRegex(serialized, r"(?i)authorization|bearer|access.?token|refresh.?token")


if __name__ == "__main__":
    unittest.main(verbosity=2)
