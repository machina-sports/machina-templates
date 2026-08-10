"""Tests for the ``validate_graph.py`` rights gate (PR 2, task A12 closure).

Run from the repository root:

    python3 tests/test_iptc_cli_rights_gate.py -v

Run the file directly, for the same reason as
``tests/test_iptc_validation_harness.py``: ``tests/`` is a namespace directory
with no ``__init__.py``, so ``-m unittest tests.<module>`` can be shadowed by an
installed distribution that ships a top-level regular ``tests`` package.

A12 shipped ``rights_findings`` and a ``--consumer-tier`` flag that argparse
accepted and nothing called: the library gate was correct and the command never
consulted it, so a production consumer running the documented command was told
its refused envelope was fine. A13 recorded that as a caveat. What is defended
here is the closure, through ``main`` rather than through the library:

1. **The flag decides an exit status.** ``--consumer-tier production`` on the
   checked-in envelope exits nonzero and names ``rights-prototype-only`` once.
2. **An envelope is validated, not bounced.** Its inner ``sport_schema_graph``
   goes through the same layers as the standalone graph document and produces
   the same verdict, under the path the caller actually named.
3. **Unreadable rights refuse.** No rights block, or non-boolean flags, is the
   absence of a licence claim and fails closed.
4. **A graph document invents no rights decision.** Rights live in the envelope
   (RFC 002 §9); a graph document reports that rather than a fabricated pass.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.iptc import validate_graph  # noqa: E402

ENVELOPE_PATH = (REPO_ROOT / "tools/iptc/fixtures/corrected"
                 / "api-football-soccer-envelope.json")
GRAPH_PATH = (REPO_ROOT / "tools/iptc/fixtures/corrected"
              / "api-football-soccer-graph.json")

ENVELOPE_ARG = str(ENVELOPE_PATH.relative_to(REPO_ROOT))
GRAPH_ARG = str(GRAPH_PATH.relative_to(REPO_ROOT))

ENVELOPE = json.loads(ENVELOPE_PATH.read_text(encoding="utf-8"))


def run(argv: list[str]) -> tuple[int, str]:
    """``main`` with its stdout captured. The command, not the library."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        status = validate_graph.main(argv)
    return status, buffer.getvalue()


def run_json(argv: list[str]) -> tuple[int, dict]:
    status, out = run([*argv, "--json"])
    payload = json.loads(out)
    return status, payload[0]


def written(directory: Path, name: str, document) -> str:
    """A document inside the repository, because results are repo-relative."""
    path = Path(directory) / name
    path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    return str(path.relative_to(REPO_ROOT))


class TestProductionConsumerIsRefused(unittest.TestCase):
    """The gap A13 found, stated as an exit status."""

    def test_a_production_consumer_is_refused_the_checked_in_envelope(self):
        status, out = run(["--consumer-tier", "production", ENVELOPE_ARG])
        self.assertEqual(status, 1, out)
        self.assertIn("rights-prototype-only", out)

    def test_the_refusal_names_one_code_and_never_cascades(self):
        """``prototype_only`` and ``commercial_use: false`` travel together on
        every open-data envelope. Printing both buries the line naming the fix."""
        status, out = run(["--consumer-tier", "production", ENVELOPE_ARG])
        self.assertEqual(status, 1)
        self.assertEqual(out.count("rights-prototype-only"), 1, out)
        self.assertNotIn("rights-non-commercial", out)

    def test_the_json_refusal_carries_exactly_that_code(self):
        status, entry = run_json(["--consumer-tier", "production", ENVELOPE_ARG])
        self.assertEqual(status, 1)
        rights = entry["rights_gate"]
        self.assertFalse(rights["ok"])
        self.assertEqual([f["code"] for f in rights["detail"]["findings"]],
                         ["rights-prototype-only"])
        self.assertEqual(rights["detail"]["consumer_tier"], "production")

    def test_the_refused_envelope_fails_overall_though_its_graph_conforms(self):
        """The refusal is the only reason it fails. A rights gate that only bit
        on already-broken documents would prove nothing."""
        status, entry = run_json(["--consumer-tier", "production", ENVELOPE_ARG])
        self.assertEqual(status, 1)
        self.assertFalse(entry["ok"])
        for layer in validate_graph.LAYERS:
            with self.subTest(layer=layer):
                self.assertTrue(entry["layers"][layer]["ok"])

    def test_the_refusal_is_printed_with_the_reason_at_either_verbosity(self):
        """A refusal is never hidden behind ``-v``: the reader who did not pass
        the flag is exactly the reader who needs to know why the run failed."""
        reason = "must refuse it rather than downgrade quietly"
        for argv in ([], ["--verbose"]):
            with self.subTest(argv=argv):
                _, out = run(["--consumer-tier", "production", *argv, ENVELOPE_ARG])
                self.assertIn(reason, out)


class TestPrototypeConsumerPasses(unittest.TestCase):

    def test_a_prototype_consumer_passes_the_rights_gate(self):
        status, entry = run_json(["--consumer-tier", "prototype", ENVELOPE_ARG])
        self.assertEqual(status, 0)
        self.assertTrue(entry["ok"])
        self.assertTrue(entry["rights_gate"]["ok"])
        self.assertEqual(entry["rights_gate"]["detail"]["findings"], [])

    def test_the_default_tier_is_still_prototype(self):
        """Every checked-in fixture predates the gate; the default may not start
        failing them."""
        status, entry = run_json([ENVELOPE_ARG])
        self.assertEqual(status, 0)
        self.assertEqual(entry["rights_gate"]["detail"]["consumer_tier"], "prototype")


class TestTheEnvelopeIsValidatedThroughItsGraph(unittest.TestCase):
    """An envelope is not a JSON-LD document, and refusing it for that is not a
    rights answer — it is the harness declining to look."""

    def test_the_inner_graph_reaches_every_layer_with_the_graph_documents_verdict(self):
        _, envelope = run_json(["--consumer-tier", "prototype", ENVELOPE_ARG])
        _, graph = run_json(["--consumer-tier", "prototype", GRAPH_ARG])
        self.assertEqual(envelope["layers"], graph["layers"])

    def test_layer_two_is_exercised_rather_than_vacuously_passed(self):
        _, entry = run_json([ENVELOPE_ARG])
        shacl = entry["layers"]["official_shacl"]["detail"]
        self.assertTrue(entry["layers"]["official_shacl"]["ok"])
        self.assertFalse(shacl["vacuous"])
        self.assertGreater(shacl["official_class_instances"], 0)

    def test_the_result_keeps_the_path_the_caller_named(self):
        """The caller asked about the envelope. Reporting the graph's path, or a
        temporary file's, would make the result untraceable to the input."""
        _, entry = run_json([ENVELOPE_ARG])
        self.assertEqual(entry["path"], ENVELOPE_ARG)
        self.assertEqual(entry["fixture"], ENVELOPE_ARG)

    def test_validating_an_envelope_leaves_nothing_behind(self):
        """No transient file survives the run: the repository is the artifact."""
        before = sorted(p.name for p in REPO_ROOT.iterdir())
        run(["--consumer-tier", "production", ENVELOPE_ARG])
        self.assertEqual(sorted(p.name for p in REPO_ROOT.iterdir()), before)


class TestUnreadableRightsFailClosed(unittest.TestCase):
    """An absent licence claim is not a permissive one."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=str(REPO_ROOT))
        self.addCleanup(self.temporary.cleanup)

    def envelope_without(self, mutate) -> str:
        document = json.loads(json.dumps(ENVELOPE))
        mutate(document["machina_sports_schema"])
        return written(self.temporary.name, "envelope.json", document)

    def test_an_envelope_with_no_rights_block_is_refused(self):
        def drop(block):
            del block["rights"]

        status, entry = run_json(["--consumer-tier", "production",
                                  self.envelope_without(drop)])
        self.assertEqual(status, 1)
        self.assertEqual([f["code"] for f in entry["rights_gate"]["detail"]["findings"]],
                         ["rights-unreadable"])

    def test_non_boolean_rights_flags_are_refused(self):
        def corrupt(block):
            block["rights"] = {"data_class": "licensed-redistributable",
                               "prototype_only": "no", "commercial_use": "yes"}

        status, entry = run_json(["--consumer-tier", "production",
                                  self.envelope_without(corrupt)])
        self.assertEqual(status, 1)
        self.assertEqual([f["code"] for f in entry["rights_gate"]["detail"]["findings"]],
                         ["rights-unreadable"])

    def test_missing_rights_are_refused_at_the_prototype_tier_too(self):
        """Unreadability is not a production-only question: no tier may consume
        an envelope whose licence nobody can read."""
        def drop(block):
            del block["rights"]

        status, _ = run(["--consumer-tier", "prototype",
                         self.envelope_without(drop)])
        self.assertEqual(status, 1)

    def test_an_envelope_with_no_graph_fails_rather_than_passing_emptily(self):
        """A missing ``sport_schema_graph`` must not read as 'nothing to check'."""
        def drop(block):
            del block["sport_schema_graph"]

        status, entry = run_json(["--consumer-tier", "prototype",
                                  self.envelope_without(drop)])
        self.assertEqual(status, 1)
        self.assertFalse(entry["layers"]["jsonld_parse"]["ok"])


class TestGraphDocumentsInventNoRightsDecision(unittest.TestCase):
    """Rights live in the envelope (RFC 002 §9). A graph document says so."""

    def test_a_graph_document_still_passes_at_the_strictest_tier(self):
        status, entry = run_json(["--consumer-tier", "production", GRAPH_ARG])
        self.assertEqual(status, 0)
        self.assertTrue(entry["ok"])

    def test_no_rights_verdict_is_fabricated_for_a_graph_document(self):
        _, entry = run_json(["--consumer-tier", "production", GRAPH_ARG])
        self.assertIsNone(entry["rights_gate"])

    def test_the_human_output_says_why_there_is_no_verdict(self):
        _, out = run(["--consumer-tier", "production", GRAPH_ARG])
        self.assertIn("rights_gate", out)
        self.assertIn("not applicable", out)
        self.assertIn("envelope", out)


class TestExistingBehaviourIsUnchanged(unittest.TestCase):
    """The flag is additive. Everything A12 documented still holds."""

    def test_all_still_reports_the_recorded_baseline_failure(self):
        status, _ = run(["--all", "--json"])
        self.assertEqual(status, 1)

    def test_section_still_selects_the_corrected_fixtures_and_they_pass(self):
        status, out = run(["--all", "--section", "corrected"])
        self.assertEqual(status, 0, out)

    def test_the_json_shape_a_caller_already_parses_is_intact(self):
        _, entry = run_json([GRAPH_ARG])
        self.assertEqual(sorted(entry),
                         ["fixture", "layers", "ok", "path", "rights_gate"])
        self.assertEqual(sorted(entry["layers"]), sorted(validate_graph.LAYERS))

    def test_the_flag_still_rejects_a_tier_the_gate_does_not_know(self):
        with self.assertRaises(SystemExit):
            validate_graph.build_parser().parse_args(["--consumer-tier", "prod"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
