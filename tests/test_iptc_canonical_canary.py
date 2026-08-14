"""The greenfield canonical canary template (revised PR3-D, Approved Amendment C).

Run from the repository root:

    python3 tests/test_iptc_canonical_canary.py -v

Run the file directly, for the same reason as the other IPTC suites: ``tests/``
is a namespace directory with no ``__init__.py``, so ``-m unittest
tests.<module>`` can be shadowed by an installed distribution that ships a
top-level regular ``tests`` package.

**What Amendment C changed, and why this suite exists.** The Task 13 assessment
found that making the historical World Cup document shape work would need either
a design exception to the frozen canonical layer or a wider legacy migration than
PR 3 authorizes. Amendment C takes neither: the World Cup is finished, so that
runtime is left byte-unchanged and revised PR3-D is **greenfield**. This suite is
the structural contract for the canary template that replaces the migration —
`machina-sports-canonical-canary`.

**The negative half is the substance.** A greenfield template proves nothing if
it quietly reintroduces the vocabulary it was created to avoid, and that
reintroduction always arrives as a convenience: one legacy alias "so the old
dashboard still works", one provider-shaped field "just for debugging". So the
template's source is read for World Cup names, legacy alias spellings, storage
predicates and provider-shaped output fields, and any of them fails.

**Scope honesty.** Nothing here calls a provider or a network. The canary is a
synthetic-fixture proof of shape and behaviour at the **prototype tier**; it is
not live parity and not a rights position (§B10, §A8).
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_SUPPORT_PATH = REPO_ROOT / "tests/iptc_canonical_support.py"
_spec = importlib.util.spec_from_file_location("iptc_canonical_support",
                                               _SUPPORT_PATH)
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)

_CONNECTOR_SUITE = REPO_ROOT / "tests/test_iptc_canonical_connector.py"

#: The template directory name, fixed by §C4. Not a placeholder.
CANARY_NAME = "machina-sports-canonical-canary"

#: The shared connector every canonical consumer installs, referenced across
#: templates rather than copied.
SHARED_CONNECTOR_REFERENCE = (
    "../../connectors/machina-sports-canonical/machina-sports-canonical.yml")

#: The workflow's declared inputs, exactly. ``include_graph`` is the explicit
#: opt-in §B6/§C3 require: ``event_view`` is the default consumption path and the
#: interchange document is requested, never served by default.
DECLARED_INPUTS = ("consumer_tier", "crosswalk", "include_graph", "observed_at",
                   "payload", "provider")

#: The default output contract. Envelope metadata, the default view, and the
#: three blocks that must travel on every path (§B6): capabilities, rights,
#: provenance. Plus the workflow status every Machina workflow reports.
REQUIRED_OUTPUTS = ("capabilities", "event_view", "profile", "provenance",
                    "refusals", "rights", "schema_version", "workflow-status")

#: Requested explicitly, so it is an output name but never the default view.
OPT_IN_OUTPUT = "sport_schema_graph"

#: The two tasks, in the only order §B13 permits.
PREFLIGHT_TASK = "preflight"
CANONICALIZE_TASK = "canonicalize"

#: Language that must not appear anywhere in the canary template. The World Cup
#: names are §C2; the alias spellings and the storage-predicate prefix are the
#: legacy shape Amendment C declines to carry forward.
FORBIDDEN_LANGUAGE = (
    "worldcup", "world-cup", "world cup", "wci",
    "sport:status", "schema:startDate", "sport:competitors", "sport:competition",
    "sport:venue", "provider_ids.", "value.", "compatibility", "legacy",
    "deprecated_since", "removal_owner",
)

#: Provider-shaped output fields. Above the seam there is no fixture id, no
#: competitor qualifier and no provider status string (§B6). A canary that
#: emitted one would be the contract violation it exists to detect.
PROVIDER_SHAPED = re.compile(
    r"""\b(fixture|sport_event|contestant|competitor|goals|matchDate|"""
    r"""homeContestantId|awayContestantId|api_football|apisports)\b""")

#: The condition-10 audit. A deterministic command, not a unit test: the question
#: it answers is about the working tree against a ref, and a unit test that shells
#: out to git reports "no git context" as a failure of the thing under test.
NO_MUTATION_AUDIT = REPO_ROOT / "scripts/check-no-wci-mutation.sh"


def template_dir() -> Path:
    return REPO_ROOT / "agent-templates" / CANARY_NAME


def install_document() -> dict:
    if not support.CANARY_INSTALL.is_file():
        raise AssertionError("canary install manifest is absent: {0}".format(
            support.CANARY_INSTALL.relative_to(REPO_ROOT)))
    return support.read_yaml(support.CANARY_INSTALL)


def workflow() -> dict:
    if not support.CANARY_WORKFLOW.is_file():
        raise AssertionError("canary workflow is absent: {0}".format(
            support.CANARY_WORKFLOW.relative_to(REPO_ROOT)))
    return support.read_yaml(support.CANARY_WORKFLOW)["workflow"]


def workflow_source() -> str:
    if not support.CANARY_WORKFLOW.is_file():
        raise AssertionError("canary workflow is absent: {0}".format(
            support.CANARY_WORKFLOW.relative_to(REPO_ROOT)))
    return support.CANARY_WORKFLOW.read_text(encoding="utf-8")


def task_named(name: str) -> dict:
    for task in workflow().get("tasks", []):
        if task.get("name") == name:
            return task
    raise AssertionError("no task named {0!r}; the canary has {1}".format(
        name, [t.get("name") for t in workflow().get("tasks", [])]))


def template_text() -> str:
    """Every checked-in byte of the template, as one string."""
    return "\n".join(path.read_text(encoding="utf-8")
                     for path in sorted(template_dir().rglob("*"))
                     if path.is_file())


class TestTheCanaryTemplateExistsWhereAmendmentCNamesIt(unittest.TestCase):
    """§C4 fixes the name. A canary at a different path is a different artifact
    from the one the amendment approved."""

    def test_canary_template_directory_has_the_exact_approved_name(self):
        self.assertTrue(template_dir().is_dir(),
                        "absent: agent-templates/{0}".format(CANARY_NAME))

    def test_canary_ships_one_install_manifest_and_one_workflow(self):
        self.assertTrue(support.CANARY_INSTALL.is_file())
        workflows = sorted((template_dir() / "workflows").glob("*.yml"))
        self.assertEqual([path.name for path in workflows],
                         [support.CANARY_WORKFLOW.name])

    def test_canary_install_references_the_shared_connector(self):
        """Referenced, never copied. One connector reaches the canonical package
        and every consumer installs that one."""
        paths = [entry.get("path")
                 for entry in install_document().get("datasets", [])]
        self.assertIn(SHARED_CONNECTOR_REFERENCE, paths)

    def test_canary_install_references_the_one_canary_workflow(self):
        paths = [entry.get("path")
                 for entry in install_document().get("datasets", [])]
        self.assertIn("workflows/{0}".format(support.CANARY_WORKFLOW.name), paths)

    def test_canary_every_install_reference_resolves(self):
        """A manifest entry pointing at nothing fails at import time in the pod,
        which is the least useful place to discover it."""
        missing = [entry["path"]
                   for entry in install_document().get("datasets", [])
                   if not (template_dir() / entry["path"]).is_file()]
        self.assertEqual(missing, [])

    def test_canary_install_declares_the_setup_block_the_importer_reads(self):
        setup = install_document().get("setup", {})
        for field in ("title", "description", "status", "value", "version"):
            with self.subTest(field=field):
                self.assertTrue(str(setup.get(field, "")).strip(), field)
        self.assertEqual(setup.get("value"),
                         "agent-templates/{0}".format(CANARY_NAME))


class TestOneWorkflowSourceParameterisedByConfiguration(unittest.TestCase):
    """§C4: one unchanged workflow source across all four legs. If the workflow
    differed per provider, four equal envelopes would prove only that four
    different programs can be written to agree."""

    def test_canary_declares_exactly_the_documented_inputs(self):
        self.assertEqual(sorted(workflow().get("inputs", {})),
                         sorted(DECLARED_INPUTS))

    def test_canary_takes_the_provider_as_an_input_not_a_hardcoded_value(self):
        """Provider selection is configuration. The moment it is a literal in the
        body, the substitution proof is over."""
        declared = workflow()["inputs"]["provider"]
        self.assertIn("$.get('provider'", str(declared))

    def test_canary_names_no_provider_in_its_body(self):
        source = workflow_source()
        for namespace in support.FOUR_PROVIDER_LEGS:
            with self.subTest(namespace=namespace):
                self.assertNotIn(namespace, source)

    def test_canary_graph_opt_in_is_declared_and_defaults_off(self):
        """§B6/§C3: ``sport_schema_graph`` is opt-in. A default that served the
        interchange document would make every consumer pay for it and would make
        the default view a lie."""
        declared = str(workflow()["inputs"]["include_graph"])
        self.assertIn("include_graph", declared)
        self.assertRegex(declared, r"False|'false'|\"false\"")


class TestPreflightStrictlyPrecedesCanonicalize(unittest.TestCase):
    """§B13, retained unchanged by §C3. A gate that runs second is not a gate."""

    def test_canary_preflight_uses_the_shared_connector(self):
        task = task_named(PREFLIGHT_TASK)
        self.assertEqual(task.get("type"), "connector")
        self.assertEqual(task["connector"]["name"], "machina-sports-canonical")
        self.assertEqual(task["connector"]["command"], "provider_preflight")

    def test_canary_canonicalize_uses_the_shared_connector(self):
        task = task_named(CANONICALIZE_TASK)
        self.assertEqual(task.get("type"), "connector")
        self.assertEqual(task["connector"]["name"], "machina-sports-canonical")
        self.assertEqual(task["connector"]["command"], "canonicalize_event")

    def test_canary_task_order_is_preflight_then_canonicalize(self):
        order = [task.get("name") for task in workflow()["tasks"]]
        self.assertLess(order.index(PREFLIGHT_TASK),
                        order.index(CANONICALIZE_TASK))

    def test_canary_canonicalize_is_conditioned_on_an_allowed_preflight(self):
        """Ordering alone is not a gate: an unconditioned second task still runs
        after a refusal."""
        condition = task_named(CANONICALIZE_TASK).get("condition", "")
        self.assertIn("preflight", condition)
        self.assertIn("allowed", condition)

    def test_canary_declares_capabilities_from_the_existing_vocabulary(self):
        """§B9: the canary consumes the capability contract, it does not extend
        it."""
        known = set(support.canonical_module("capabilities").ALL_CAPABILITIES)
        rendered = json.dumps(task_named(PREFLIGHT_TASK).get("inputs", {}))
        declared = re.findall(r"'((?:event|participant)\.[a-z_]+|provenance)'",
                              rendered)
        self.assertTrue(declared, "the preflight declares no capabilities")
        self.assertEqual(sorted(set(declared) - known), [])


class TestTheDefaultOutputContract(unittest.TestCase):
    """§B6/§C3: ``event_view`` is the default, and ``capabilities``, ``rights``
    and ``provenance`` travel on every path. A projection served without its
    rights block is an unlicensed payload wearing a licensed one's shape."""

    def test_canary_exposes_the_required_default_outputs(self):
        declared = workflow().get("outputs", {})
        for name in REQUIRED_OUTPUTS:
            with self.subTest(output=name):
                self.assertIn(name, declared)

    def test_canary_exposes_the_graph_as_an_opt_in_output(self):
        self.assertIn(OPT_IN_OUTPUT, workflow().get("outputs", {}))

    def test_canary_graph_output_is_gated_on_the_opt_in_input(self):
        """Present as a name, empty unless asked for. That is what "opt-in"
        means; an always-populated graph output is the default in disguise."""
        expression = str(workflow()["outputs"][OPT_IN_OUTPUT])
        self.assertIn("include_graph", expression)

    def test_canary_default_view_is_event_view_not_the_graph(self):
        outputs = workflow().get("outputs", {})
        self.assertNotIn("include_graph", str(outputs["event_view"]),
                         "event_view must be served unconditionally; gating it "
                         "would make the interchange document the default")


class TestTheCanaryCarriesNoLegacyOrProviderVocabulary(unittest.TestCase):
    """§C2 and §B6, enforced on the template's own bytes.

    This is the case that would catch the friendly regression: someone adds one
    legacy alias to the canary so an old dashboard keeps working, and the
    greenfield template becomes a second legacy producer.
    """

    def test_canary_template_contains_no_forbidden_legacy_language(self):
        text = template_text().lower()
        found = sorted({term for term in FORBIDDEN_LANGUAGE
                        if term.lower() in text})
        self.assertEqual(found, [])

    def test_canary_workflow_emits_no_provider_shaped_field(self):
        offenders = []
        for number, line in enumerate(workflow_source().splitlines(), start=1):
            match = PROVIDER_SHAPED.search(line)
            if match:
                offenders.append("{0}:{1}".format(number, match.group(0)))
        self.assertEqual(offenders, [])

    def test_canary_declares_no_document_storage(self):
        """The canary computes; it does not persist. No storage means no storage
        predicate, which is the coupling class Amendment C declines to create."""
        types = {task.get("type") for task in workflow()["tasks"]}
        self.assertNotIn("document", types)

    def test_canary_contains_no_canonical_logic(self):
        """§C3: the template is a call site. Vocabulary and serialization live in
        the package, reached through the one shared connector."""
        text = template_text()
        for owned_by_the_package in ("canonical_envelope", "capability_report",
                                     "rights_findings", "surrogate_resolver"):
            with self.subTest(symbol=owned_by_the_package):
                self.assertNotIn(owned_by_the_package, text)


class TestTheForwardAdoptionGuide(unittest.TestCase):
    """§C6: the migration guide is **replaced**, not renamed. A migration guide
    implies a legacy alias-removal programme, and Amendment C implies none."""

    def guide(self) -> str:
        if not support.ADOPTION_GUIDE.is_file():
            raise AssertionError("forward adoption guide is absent: {0}".format(
                support.ADOPTION_GUIDE.relative_to(REPO_ROOT)))
        return support.ADOPTION_GUIDE.read_text(encoding="utf-8")

    def test_adoption_guide_exists(self):
        self.assertTrue(support.ADOPTION_GUIDE.is_file())

    def test_adoption_guide_tells_new_consumers_to_start_canonical(self):
        text = self.guide().lower()
        self.assertIn("event_view", text)
        self.assertIn("new consumer", text)

    def test_adoption_guide_records_the_historical_runtime_as_untouched(self):
        text = self.guide().lower()
        self.assertTrue("untouched" in text or "byte-unchanged" in text, text[:0])

    def test_adoption_guide_states_the_synthetic_prototype_scope_limit(self):
        text = self.guide().lower()
        for phrase in ("synthetic", "prototype", "not live parity"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, text)

    def test_adoption_guide_implies_no_alias_removal_programme(self):
        text = self.guide().lower()
        self.assertIn("no legacy alias-removal", text)


class TestTheNoMutationAuditExists(unittest.TestCase):
    """Condition 10, discharged by §C6 as a **no-mutation proof**.

    Deliberately a script rather than a unit test. The question is "does the diff
    against the base ref touch the historical template", which is a question about
    a git working tree; a unit test that shells out to git turns "this checkout
    has no upstream ref" into a failure of the thing under test. The script is the
    audit; this case only proves the audit ships and checks the right path.
    """

    def test_no_mutation_audit_script_exists_and_is_executable(self):
        self.assertTrue(NO_MUTATION_AUDIT.is_file(),
                        "absent: {0}".format(
                            NO_MUTATION_AUDIT.relative_to(REPO_ROOT)))
        import os
        self.assertTrue(os.access(NO_MUTATION_AUDIT, os.X_OK),
                        "not executable")

    def test_no_mutation_audit_checks_the_historical_template_path(self):
        text = NO_MUTATION_AUDIT.read_text(encoding="utf-8")
        self.assertIn("agent-templates/world-cup-intelligence", text)
        self.assertIn("git diff", text)

    def test_no_mutation_audit_checks_untracked_files_too(self):
        """A new file under the historical template is a mutation that
        ``git diff`` alone does not see — which is exactly how the pre-pivot
        artifacts landed there.

        Asserted on the property rather than on one spelling: either
        ``ls-files --others`` or ``status --porcelain`` answers "what is here
        that git is not tracking", and pinning one of them would make this case
        a test of the implementation I happened to write first.
        """
        text = NO_MUTATION_AUDIT.read_text(encoding="utf-8")
        self.assertTrue("ls-files --others" in text or "status --porcelain" in text,
                        "the audit does not query untracked files")


if __name__ == "__main__":
    unittest.main(verbosity=2)
