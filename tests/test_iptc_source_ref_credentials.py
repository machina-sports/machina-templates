"""Credential-shaped ``source_refs`` are refused whatever their casing.

Run from the repository root:

    python3 tests/test_iptc_source_ref_credentials.py -v

Run the file directly, for the same reason as the other IPTC suites: ``tests/``
is a namespace directory with no ``__init__.py``, so ``-m unittest
tests.<module>`` can be shadowed by an installed distribution that ships a
top-level regular ``tests`` package.

**The defect this closes.** ``observation._REQUEST_SHAPED`` matched raw
substrings, so the check was case-sensitive on every marker that carries a
letter. ``Authorization: Bearer …`` was refused and ``authorization: Bearer …``
was accepted; ``token=abc`` was refused and ``TOKEN=abc`` was accepted;
``key=abc`` was refused and ``API_KEY=abc`` was accepted. Accepted means
serialized: the string reaches ``provenance.source_refs`` in the envelope and is
committed to whatever fixture records it. A credential filter that depends on
the casing an attacker or a careless adapter picked is not a filter.

Three things are asserted here, and the third is what stops the bug returning in
a different shape:

1. **Detection is case-insensitive**, over the markers RFC 002 §1.1 names plus
   the credential words a request header actually uses.
2. **Safe opaque refs still validate.** Every value checked into
   ``tools/iptc/fixtures/observations`` is listed below by hand. A filter that
   also rejected ``api-football/fixtures`` would be replaced within a week.
3. **Validation and serialization read one rule.** Every marker in the shared
   tuple is driven through ``validate_observation`` *and* through the three
   serializers with validation bypassed, so a serializer that grew its own copy
   of the list — or trusted the validator to have run — fails here.
4. **The refusal does not repeat what it refused.** The first fix rejected the
   entry and then interpolated it into the error, so the credential travelled
   out through ``validate_observation``'s findings and through the
   ``canonical_envelope`` ValueError instead of through the envelope — into
   whatever CI log, ticket or terminal read them. Every shape above is driven
   through every surface and the raw text must appear on none of them.
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.iptc.canonical.ids import surrogate_resolver  # noqa: E402
from tools.iptc.canonical.observation import (  # noqa: E402
    CREDENTIAL_MARKERS,
    SOURCE_REF_TEXT_FIELDS,
    credential_marker,
    source_ref_credential_findings,
    validate_observation,
)
from tools.iptc.canonical.serialize import (  # noqa: E402
    canonical_envelope,
    event_view,
    provenance_block,
    sport_schema_graph,
)

OBSERVATION = (REPO_ROOT / "tools/iptc/fixtures/observations"
               / "api-football-soccer-observation.json")

#: Values that must be refused. The casing is the point: each line pairs a form
#: the old tuple happened to catch with one it did not.
CREDENTIAL_SHAPED = (
    # Authorization, in every casing a header or a log line produces.
    "Authorization: Bearer abc",
    "authorization: Bearer ***",
    "AUTHORIZATION: Bearer ***",
    "AuThOrIzAtIoN: Bearer ***",
    "Bearer eyJhbGciOiJIUzI1NiJ9",
    # Token.
    "token=abc",
    "TOKEN=abc",
    "Token=abc",
    "access_token",
    "ACCESS_TOKEN",
    # API key, with and without the '=' the old tuple depended on.
    "api_key=abc",
    "API_KEY=abc",
    "api-key: abc",
    "API-KEY: abc",
    "apikey/abc",
    "ApiKey/abc",
    "APIKEY/abc",
    # Password and secret.
    "password=hunter2",
    "PASSWORD=hunter2",
    "PassWord",
    "secret=abc",
    "SECRET=abc",
    "Secret",
    "client_secret",
    # Cookies.
    "cookie: session=abc",
    "Cookie: session=abc",
    "set-cookie: session=abc",
    "Set-Cookie: session=abc",
    "SET-COOKIE: session=abc",
    # Request-shaped: scheme, query, parameter separator.
    "https://v3.football.api-sports.io/fixtures?id=9001",
    "HTTPS://V3.FOOTBALL.API-SPORTS.IO/FIXTURES",
    "http://example.invalid/summary",
    "HTTP://EXAMPLE.INVALID/SUMMARY",
    "fixtures?id=9001",
    "fixtures&season=2026",
)

#: Values that must keep validating. The first seven are every ``value`` checked
#: into ``tools/iptc/fixtures/observations`` today, listed literally rather than
#: read from the files: this is the list a future marker must not break, so it
#: has to be readable in the failure output.
SAFE_REFS = (
    "api-football/fixtures",
    "espn/summary",
    "sportradar-soccer/sport_event_summary",
    "machina-sports-schema/canonical-observation-1",
    "iptc-sportradar-event-mlb-mapping",
    "iptc-sportradar-event-nfl-mapping",
    "iptc-sportradar-tennis-event-mapping",
    "iptc-opta-event-mapping",
    # Opaque endpoint classes an adapter could reasonably add next.
    "sportradar-nfl/schedule",
    "stats-perform/matchstats",
    "espn/scoreboard",
)

#: The one note the checked-in fixtures carry. It contains the word "credential"
#: on purpose — saying "no credential exists" must not read as carrying one.
FIXTURE_NOTE = ("legacy mapping-contract shape, not raw provider data; no "
                "Sportradar endpoint was called and no credential exists")


def document(*refs):
    """The api-football fixture with ``source_refs`` replaced by ``refs``."""
    doc = json.loads(OBSERVATION.read_text(encoding="utf-8"))
    doc["observation"]["adapter"]["source_refs"] = [copy.deepcopy(r) for r in refs]
    return doc


def endpoint_ref(value):
    return {"kind": "endpoint-class", "value": value}


def ref_carrying(field, text):
    """A ``source_refs`` entry whose ``field`` holds ``text``, rest safe.

    One entry shape per published field, so a refusal can be attributed to the
    field under test rather than to the rest of the record.
    """
    ref = {"kind": "endpoint-class", "value": "api-football/fixtures"}
    ref[field] = text
    return ref


def refusal(index, field, marker):
    """The one message a rejected entry produces, whatever it held.

    Deterministic in the pointer and the marker and in nothing else: the value is
    the material being refused, so naming it in the error hands it to every log
    the error reaches.
    """
    return ("observation.adapter.source_refs[{0}].{1}: request- or "
            "credential-shaped material was redacted (contains '{2}'). Record "
            "the endpoint class only; no URL, query or credential.".format(
                index, field, marker))


def resolver():
    return surrogate_resolver("api-football")


class TestTheFixtureIsAValidStartingPoint(unittest.TestCase):
    """Every rejection below has to be attributable to the ref, not the fixture."""

    def test_the_unmodified_fixture_validates(self):
        self.assertEqual(
            validate_observation(json.loads(
                OBSERVATION.read_text(encoding="utf-8"))), [])

    def test_the_fixture_with_its_own_ref_reinstated_validates(self):
        self.assertEqual(
            validate_observation(document(endpoint_ref("api-football/fixtures"))),
            [])


class TestCredentialShapedValuesAreRefused(unittest.TestCase):
    """Case-insensitively, and with a pointer naming the entry and the field."""

    def test_every_credential_shaped_value_is_one_deterministic_error(self):
        for value in CREDENTIAL_SHAPED:
            with self.subTest(value=value):
                errors = validate_observation(document(endpoint_ref(value)))
                self.assertEqual(len(errors), 1, errors)
                self.assertTrue(
                    errors[0].startswith("observation.adapter.source_refs[0].value:"),
                    errors[0])
                self.assertIn("endpoint class", errors[0])

    def test_the_error_names_the_marker_that_matched(self):
        errors = validate_observation(document(endpoint_ref("API_KEY=abc")))
        self.assertEqual(len(errors), 1, errors)
        marker = credential_marker("API_KEY=abc")
        self.assertIsNotNone(marker)
        self.assertIn("'{0}'".format(marker), errors[0])

    def test_the_same_input_always_produces_the_same_error(self):
        first = validate_observation(document(endpoint_ref("TOKEN=abc")))
        second = validate_observation(document(endpoint_ref("TOKEN=abc")))
        self.assertEqual(first, second)

    def test_each_bad_entry_is_reported_against_its_own_index(self):
        errors = validate_observation(document(
            endpoint_ref("api-football/fixtures"),
            endpoint_ref("authorization: Bearer ***"),
            endpoint_ref("SET-COOKIE: session=abc"),
        ))
        self.assertEqual(len(errors), 2, errors)
        self.assertTrue(errors[0].startswith(
            "observation.adapter.source_refs[1].value:"), errors[0])
        self.assertTrue(errors[1].startswith(
            "observation.adapter.source_refs[2].value:"), errors[1])

    def test_a_credential_in_the_kind_is_refused_too(self):
        """``kind`` is published beside ``value``; a filter that reads one field
        of a two-field record is a filter with a documented way round it."""
        errors = validate_observation(document(
            {"kind": "AUTHORIZATION", "value": "api-football/fixtures"}))
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith(
            "observation.adapter.source_refs[0].kind:"), errors[0])

    def test_a_credential_in_the_note_is_refused_too(self):
        errors = validate_observation(document(
            {"kind": "endpoint-class", "value": "api-football/fixtures",
             "note": "called with API_KEY=abc"}))
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith(
            "observation.adapter.source_refs[0].note:"), errors[0])


class TestSafeRefsAreStillAccepted(unittest.TestCase):
    """The filter is worthless if it costs the adapters their real refs."""

    def test_every_checked_in_and_plausible_ref_validates(self):
        for value in SAFE_REFS:
            with self.subTest(value=value):
                self.assertEqual(
                    validate_observation(document(endpoint_ref(value))), [])

    def test_the_fixture_note_saying_no_credential_exists_is_not_a_credential(self):
        self.assertIsNone(credential_marker(FIXTURE_NOTE))
        self.assertEqual(validate_observation(document(
            {"kind": "legacy-mapping-output",
             "value": "iptc-opta-event-mapping",
             "note": FIXTURE_NOTE})), [])

    def test_the_serializer_default_note_is_not_a_credential(self):
        from tools.iptc.canonical.serialize import SOURCE_REF_NOTE

        self.assertIsNone(credential_marker(SOURCE_REF_NOTE))

    def test_a_safe_ref_is_serialized_unchanged(self):
        block = provenance_block(document(endpoint_ref("api-football/fixtures")),
                                 id_resolver=resolver())["provenance"]
        self.assertEqual(block["source_refs"], [{
            "kind": "endpoint-class",
            "value": "api-football/fixtures",
            "note": "endpoint class only; no URL, query or credential is recorded",
        }])


class TestOneRuleNotTwo(unittest.TestCase):
    """Validation and serialization are driven off the same marker tuple."""

    def test_every_marker_is_matched_case_insensitively(self):
        for marker in CREDENTIAL_MARKERS:
            with self.subTest(marker=marker):
                self.assertEqual(credential_marker(marker), marker)
                self.assertEqual(credential_marker(marker.upper()), marker)
                self.assertEqual(
                    credential_marker("endpoint/{0}/x".format(marker.upper())),
                    marker)

    def test_every_marker_is_refused_by_the_validator(self):
        for marker in CREDENTIAL_MARKERS:
            with self.subTest(marker=marker):
                value = "endpoint/{0}/x".format(marker.upper())
                self.assertEqual(
                    len(validate_observation(document(endpoint_ref(value)))), 1)

    def test_every_marker_is_dropped_by_the_serializer(self):
        """With validation bypassed. ``provenance_block`` is a public function and
        a caller that skipped ``validate_observation`` must still not publish a
        credential — the filter fails closed rather than trusting its caller."""
        for marker in CREDENTIAL_MARKERS:
            with self.subTest(marker=marker):
                value = "endpoint/{0}/x".format(marker.upper())
                block = provenance_block(document(endpoint_ref(value)),
                                         id_resolver=resolver())["provenance"]
                self.assertNotIn("source_refs", block)

    def test_findings_name_the_field_and_the_marker(self):
        self.assertEqual(
            source_ref_credential_findings(endpoint_ref("API_KEY=abc")),
            [("value", credential_marker("API_KEY=abc"))])
        self.assertEqual(
            source_ref_credential_findings(endpoint_ref("espn/summary")), [])

    def test_a_non_dict_entry_has_no_findings(self):
        self.assertEqual(source_ref_credential_findings("espn/summary"), [])
        self.assertEqual(source_ref_credential_findings(None), [])

    def test_a_non_string_field_is_not_scanned(self):
        self.assertIsNone(credential_marker(None))
        self.assertIsNone(credential_marker(7))
        self.assertIsNone(credential_marker({"value": "token="}))


class TestNoUnsafeRefReachesAnyOutput(unittest.TestCase):
    """event_view, the graph and the envelope, all three fail closed."""

    SECRET = "authorization: Bearer sk-live-abc123"

    def bad(self):
        return document(endpoint_ref(self.SECRET),
                        endpoint_ref("api-football/fixtures"))

    def test_the_envelope_refuses_to_build_at_all(self):
        with self.assertRaises(ValueError) as raised:
            canonical_envelope(self.bad(), id_resolver=resolver())
        message = str(raised.exception)
        self.assertIn("observation.adapter.source_refs[0].value", message)
        self.assertNotIn("sk-live-abc123",
                         message.split("source_refs[0].value:")[0])

    def test_the_provenance_block_keeps_only_the_safe_entry(self):
        block = provenance_block(self.bad(), id_resolver=resolver())["provenance"]
        self.assertEqual([ref["value"] for ref in block["source_refs"]],
                         ["api-football/fixtures"])
        self.assertNotIn("sk-live-abc123", json.dumps(block))

    def test_the_event_view_carries_no_source_ref_at_all(self):
        view = event_view(self.bad(), id_resolver=resolver())
        self.assertNotIn("sk-live-abc123", json.dumps(view))
        self.assertNotIn("source_refs", json.dumps(view))

    def test_the_graph_provenance_resource_carries_no_source_ref(self):
        graph = sport_schema_graph(self.bad(), id_resolver=resolver())
        self.assertNotIn("sk-live-abc123", json.dumps(graph))
        self.assertNotIn("source_refs", json.dumps(graph))

    def test_the_adapter_block_never_carries_the_raw_list(self):
        """``provenance.adapter`` is the observation's adapter block copied. It
        must not smuggle in the unfiltered ``source_refs`` it was copied from."""
        block = provenance_block(self.bad(), id_resolver=resolver())["provenance"]
        self.assertNotIn("source_refs", block["adapter"])


class TestTheRefusalNeverRepeatsWhatItRefused(unittest.TestCase):
    """A rejected value is named by its path, never by its text.

    Rejecting an entry and then quoting it in the error moves the credential from
    one published surface to another: ``validate_observation`` returns the
    findings to whatever printed them, and ``canonical_envelope`` raises them as a
    ValueError that a caller logs, prints or attaches to a ticket. The pointer is
    what an adapter author fixes the bug with; the value is what an adapter author
    already has.
    """

    def test_the_error_is_the_same_redacted_message_whatever_the_value(self):
        for value in CREDENTIAL_SHAPED:
            with self.subTest(value=value):
                self.assertEqual(
                    validate_observation(document(endpoint_ref(value))),
                    [refusal(0, "value", credential_marker(value))])

    def test_no_rejected_text_reaches_the_validation_findings(self):
        for field in SOURCE_REF_TEXT_FIELDS:
            for text in CREDENTIAL_SHAPED:
                with self.subTest(field=field, text=text):
                    errors = validate_observation(
                        document(ref_carrying(field, text)))
                    self.assertEqual(
                        errors, [refusal(0, field, credential_marker(text))])
                    self.assertNotIn(text, "\n".join(errors))

    def test_no_rejected_text_reaches_the_envelope_exception(self):
        for text in CREDENTIAL_SHAPED:
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as raised:
                    canonical_envelope(document(endpoint_ref(text)),
                                       id_resolver=resolver())
                message = str(raised.exception)
                self.assertIn("observation.adapter.source_refs[0].value", message)
                self.assertNotIn(text, message)

    def test_no_rejected_text_reaches_any_serialized_output(self):
        """With validation bypassed, as in ``TestOneRuleNotTwo``: each builder is
        public and must hold on its own."""
        for text in CREDENTIAL_SHAPED:
            with self.subTest(text=text):
                doc = document(endpoint_ref(text))
                for name, built in (
                    ("provenance", provenance_block(doc, id_resolver=resolver())),
                    ("event_view", event_view(doc, id_resolver=resolver())),
                    ("graph", sport_schema_graph(doc, id_resolver=resolver())),
                ):
                    self.assertNotIn(text, json.dumps(built), name)

    def test_the_pointer_and_the_marker_survive_the_redaction(self):
        """Redacting the value must not cost the two things that make the error
        actionable: which entry and field, and why it was refused."""
        errors = validate_observation(document(
            endpoint_ref("api-football/fixtures"),
            {"kind": "endpoint-class", "value": "api-football/fixtures",
             "note": "called with API_KEY=hunter2"},
        ))
        self.assertEqual(
            errors, [refusal(1, "note", "api_key")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
