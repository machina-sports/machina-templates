"""Synthetic transport receipts must satisfy the same schema consumers load."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("projection", HERE / "test_event_data_projection.py")
projection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(projection)
SCHEMA = json.loads((HERE.parents[1] / "machina-sports-canonical/machina-event-evidence-1.schema.json").read_text())
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA, format_checker=jsonschema.FormatChecker())


def documents():
    return projection.project(endpoint_provenance=projection.endpoint_receipts())["data"]["evidence_documents"]


@pytest.mark.parametrize("document", documents(), ids=lambda d: d["value"]["kind"])
def test_all_fresh_http_projections_satisfy_consumer_schema(document):
    VALIDATOR.validate(document)


@pytest.mark.parametrize("changes", [
    {"synthetic": "false"}, {"synthetic": None}, {"synthetic": True},
    {"retrieval": None}, {"retrieval": {}},
    {"retrieval": {"mode": "replay"}},
])
def test_malformed_or_conflicting_attestation_is_rejected(changes):
    document = deepcopy(documents()[0])
    document["value"]["provenance"].update(changes)
    assert list(VALIDATOR.iter_errors(document))


def test_real_declaration_requires_receipt_but_unknown_origin_remains_readable():
    document = deepcopy(documents()[0])
    del document["value"]["provenance"]["retrieval"]
    assert list(VALIDATOR.iter_errors(document))
    del document["value"]["provenance"]["synthetic"]
    VALIDATOR.validate(document)
    document["value"]["provenance"]["synthetic"] = True
    VALIDATOR.validate(document)


def test_receipt_fields_are_closed_and_timestamps_are_zoned():
    for patch in [{"token": "synthetic-test-value"}, {"observed_at": "yesterday"}, {"mode": "replay"}]:
        document = deepcopy(documents()[0])
        document["value"]["provenance"]["retrieval"].update(patch)
        assert list(VALIDATOR.iter_errors(document))
