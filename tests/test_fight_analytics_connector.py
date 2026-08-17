"""Offline contract tests for the Fight Analytics REST connector."""

from __future__ import annotations

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
            [{"name": "Certified smoke", "value": "run_certified_smoke"}],
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
