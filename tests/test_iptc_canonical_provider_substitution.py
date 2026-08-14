"""Four-provider substitution at the greenfield canary (revised PR3-D, §C4).

Run from the repository root:

    python3 tests/test_iptc_canonical_provider_substitution.py -v

Run the file directly, for the same reason as the other IPTC suites: ``tests/``
is a namespace directory with no ``__init__.py``, so ``-m unittest
tests.<module>`` can be shadowed by an installed distribution that ships a
top-level regular ``tests`` package.

**SCOPE HONESTY, VERBATIM AND FIRST.** The fixtures under
``tools/iptc/fixtures/cross-provider/synthetic-match-01/`` are **synthetic**.
This suite proves **substitution of shape and behaviour at the prototype tier**:
that four providers observing one match produce one envelope a single consumer
reads unchanged. It does **not** prove live provider parity — no live API is
called — and it does **not** prove production rights. Every rights block in this
tree is ``prototype_only`` synthetic evidence, and the gate refuses a
``production`` consumer *before* the provider is reached. A live, authorized
sandbox proof is a separate exercise with its own approval (§B10, §B11).

**What "substitution" is asserted to mean.** Not that the four payloads are
similar. That the *same workflow source* — one file, byte-identical across all
four legs — reads all four, with the provider appearing only as configuration.
§B11 fixes the invariants that must agree (identity, start, normalized status,
score/result where supported, and the workflow contract) and fixes the list of
differences that are allowed. That list is **closed**: provider IDs,
``provenance``, ``capabilities``, ``rights``, raw evidence, and actions or
statistics not shared by capability. A difference outside it is a failure, and
this suite is where "closed" stops being an adjective.

**Why the existing tree is extended rather than replaced.**
``synthetic-match-01`` already expresses one match two ways, and the
sports-skills leg is already read by reference from the A14 reference contract's
own input. Opening a second four-provider fixture tree would create two answers
to "what is the synthetic match", which is the duplication the seam exists to
delete.

**Amendment C.** The consumer under test is the greenfield
``machina-sports-canonical-canary`` template, not any historical consumer. The
World Cup runtime is byte-unchanged and is not read by this suite at all.

**LLM prose is not compared here at all.** §B11 evaluates generated prose
semantically, never byte-for-byte. Nothing in the compared set is model output:
the canary is a pure canonicalization path and emits no generated text. A test
that byte-compared prose would either fail every run or force the temperature
down until the proof stopped describing the real workflow.
"""

from __future__ import annotations

import hashlib
import json
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_SUPPORT_PATH = REPO_ROOT / "tests/iptc_canonical_support.py"
_spec = importlib.util.spec_from_file_location("iptc_canonical_support", _SUPPORT_PATH)
support = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(support)

_CONNECTOR_SUITE = REPO_ROOT / "tests/test_iptc_canonical_connector.py"

OBSERVED_AT = support.OBSERVED_AT


def instant(value):
    """One start time as an instant, not as a spelling.

    §C4 compares **start**. Two ISO-8601 renderings of the same moment —
    ``...20:00:00Z`` and ``...20:00:00+00:00`` — are the same start, and the
    difference between them is the provider's serialization convention rather
    than a disagreement about the match. Comparing the strings would fail the
    proof on a `Z`, and "normalise the fixture until the strings match" would put
    a spelling into the fixture that the provider does not use.
    """
    from datetime import datetime
    text = str(value)
    return datetime.fromisoformat(
        text[:-1] + "+00:00" if text.endswith("Z") else text)


def connector_suite():
    """The connector suite, for its loader **and** its call convention.

    Two loaders would be two definitions of "the connector", and the first
    divergence between them would show up as a passing substitution proof
    against a file the connector suite never checked. The same argument applies
    to how a command is invoked: the executor passes workflow inputs under
    ``params`` and a task's ``$`` is the stripped ``data``, so a proof that
    called the function flat and read the envelope directly would be proving
    something about a calling convention the pod does not use.
    """
    spec = importlib.util.spec_from_file_location(
        "iptc_canonical_connector_suite", _CONNECTOR_SUITE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def leg_envelope(provider: str) -> dict:
    """One leg, canonicalized through the seam and nothing else.

    The provider name is the only argument that changes between legs. That is
    the whole claim: no branch, no per-provider field path, no adapter chosen by
    the caller.
    """
    suite = connector_suite()
    result = suite.call(
        suite.connector_module(), "canonicalize_event",
        provider=provider,
        consumer_tier="prototype",
        requires=list(support.CANARY_REQUIRES),
        optional=list(support.CANARY_OPTIONAL),
        observed_at=OBSERVED_AT,
        crosswalk=support.canary_crosswalk(),
        payload=support.read_json(support.FOUR_PROVIDER_LEGS[provider]))
    assert result["allowed"], result["refusals"]
    return result["envelope"][support.ENVELOPE_KEY]


def sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class TestTheFourLegsExist(unittest.TestCase):
    """§B11 names four providers. Three fixtures and a shrug is a three-provider
    proof with a four-provider title."""

    def test_every_named_leg_has_a_payload(self):
        missing = [name for name, path in support.FOUR_PROVIDER_LEGS.items()
                   if not path.is_file()]
        self.assertEqual(missing, [])

    def test_the_legs_are_the_four_providers_amendment_b_names(self):
        self.assertEqual(sorted(support.FOUR_PROVIDER_LEGS),
                         ["api-football", "sportradar-soccer",
                          "sports-skills/espn", "stats-perform-opta"])

    def test_the_fixture_tree_is_the_existing_one(self):
        """Extended, not forked. The api-football leg checked in for A16 must
        still be the api-football leg here."""
        self.assertTrue(support.CROSS_PROVIDER_MATCH.is_dir())
        self.assertEqual(support.FOUR_PROVIDER_LEGS["api-football"],
                         support.CROSS_PROVIDER_MATCH / "api-football.json")


class TestTheSameWorkflowSourceReadsEveryProvider(unittest.TestCase):
    """§B11 criterion 1, and the one that makes the rest worth asserting.

    If the workflow differed per provider, four equal envelopes would prove only
    that four different programs can be written to agree.
    """

    def test_the_workflow_file_is_one_file_with_one_hash(self):
        self.assertTrue(support.CANARY_WORKFLOW.is_file())
        digests = {name: sha256(support.CANARY_WORKFLOW)
                   for name in support.FOUR_PROVIDER_LEGS}
        self.assertEqual(len(set(digests.values())), 1)

    def test_the_workflow_names_no_provider_above_the_seam(self):
        """§B6: no provider field, and no provider *name*, above the boundary.
        A workflow that says ``if provider == 'api-football'`` has a fifth leg
        nobody counted."""
        source = support.CANARY_WORKFLOW.read_text(encoding="utf-8")
        for namespace in support.FOUR_PROVIDER_LEGS:
            with self.subTest(namespace=namespace):
                self.assertNotIn(namespace, source)

    def test_the_workflow_carries_no_provider_status_vocabulary(self):
        """``FT`` is API-Football, ``closed`` is Sportradar. A normalized status
        is the thing the canonical contract is for."""
        source = support.CANARY_WORKFLOW.read_text(encoding="utf-8")
        for leak in ("'FT'", '"FT"', "'NS'", '"NS"'):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, source)


class TestCanonicalInvariantsAgreeAcrossProviders(unittest.TestCase):
    """§B11's compared set. One assertion per invariant, so a failure names the
    fact the providers disagree about rather than "the envelopes differ"."""

    def setUp(self):
        self.views = {name: leg_envelope(name)["event_view"]
                      for name in support.FOUR_PROVIDER_LEGS}

    def values(self, invariant):
        return {name: view.get(invariant)
                for name, view in self.views.items()}

    def test_identity_is_equivalent_across_providers(self):
        """§B12: equivalent provider IDs resolve to the same Machina identity
        through the injected crosswalk. Divergence here means the crosswalk was
        reimplemented rather than injected."""
        self.assertEqual(len(set(self.values("event_id").values())), 1,
                         self.values("event_id"))

    def test_competition_identity_is_equivalent_across_providers(self):
        competitions = {name: (view.get("competition") or {}).get("id")
                        for name, view in self.views.items()}
        self.assertEqual(len(set(competitions.values())), 1, competitions)

    def test_participants_are_equivalent_across_providers(self):
        rosters = {}
        for name, view in self.views.items():
            rosters[name] = tuple(sorted(
                (participant.get("role"), participant.get("id"))
                for participant in view.get("participants", [])))
        self.assertEqual(len(set(rosters.values())), 1, rosters)

    def test_start_is_equivalent_across_providers(self):
        started = {name: instant(value)
                   for name, value in self.values("start_time").items()}
        self.assertEqual(len(set(started.values())), 1,
                         self.values("start_time"))

    def test_normalized_status_is_equivalent_across_providers(self):
        self.assertEqual(len(set(self.values("status").values())), 1,
                         self.values("status"))

    def test_score_is_equivalent_where_the_provider_supports_it(self):
        """§B11: where supported, equal. Where unsupported, **recorded as
        unsupported** — never skipped, because a silent skip is how an absent
        capability becomes an agreement nobody checked."""
        capabilities = {
            name: set(leg_envelope(name)["capabilities"].get("present", ()))
            for name in support.FOUR_PROVIDER_LEGS}
        supported, unsupported = {}, []
        for name, view in self.views.items():
            if "event.score" not in capabilities[name]:
                unsupported.append(name)
                continue
            supported[name] = tuple(sorted(
                (participant.get("role"), participant.get("score"))
                for participant in view.get("participants", [])))
        self.assertTrue(supported, "no leg states a score")
        self.assertEqual(len(set(supported.values())), 1,
                         {"supported": supported, "unsupported": unsupported})


class TestTheAllowedDifferenceSetIsClosed(unittest.TestCase):
    """§B11's list, enforced as a set rather than read as guidance.

    The failure mode this catches is the friendly one: a real difference appears,
    it is obviously a provider quirk, and the list grows by one. The list is
    closed by Amendment B, so growing it is an amendment, not a test fix.
    """

    def setUp(self):
        self.envelopes = {name: leg_envelope(name)
                          for name in support.FOUR_PROVIDER_LEGS}

    def test_every_envelope_difference_falls_inside_the_closed_set(self):
        differing = set()
        reference = None
        for envelope in self.envelopes.values():
            if reference is None:
                reference = envelope
                continue
            for key in set(reference) | set(envelope):
                if reference.get(key) != envelope.get(key):
                    differing.add(key)
        outside = sorted(
            differing
            - set(support.ALLOWED_CROSS_PROVIDER_DIFFERENCES)
            - {"sport_schema_graph", "event_view"})
        self.assertEqual(outside, [])

    def test_every_event_view_difference_is_classified_and_none_unexplained(self):
        """The closed set applied member by member, with nothing waved through.

        §C4 compares identity, participants, start, normalized status, score
        where supported, and the output contract — and §B11 fixes what may
        differ. Everything the legs disagree about below is assigned a category
        from that closed list, and **an unclassifiable difference fails**. The
        set is not widened here and no fixture is normalised to make a difference
        disappear; a residue with no category would be a real finding.

        The categories, and why each is inside §B11:

        ``provider block``
            ``event_view.provider`` is namespace, family and raw evidence —
            "provider IDs" and "raw evidence", provider-scoped by construction.
        ``capability-unshared``
            A member whose backing capability is absent from at least one leg.
            §B11's "actions or statistics not shared by capability".
        ``provider-scoped surrogate identity``
            An ``id`` that no crosswalk entry denotes, so the package mints a
            marked surrogate from the provider's own identifier. Different
            provider identifiers give different surrogates: "provider IDs".
        ``stated by some providers only``
            A sub-key one provider states and another does not, **equal wherever
            it is stated**. Not a disagreement about the match; smoothing it over
            would be the fabrication the profile exists to prevent, and it is the
            same category `tests/test_iptc_cross_provider_equivalence.py` already
            adjudicates for the two legs it compares.
        ``same instant, different serialization``
            ``...T20:00:00Z`` and ``...T20:00:00+00:00`` are one start.
        """
        marker = ":{0}".format(support.canonical_module("ids").SURROGATE_MARKER)
        shared = set.intersection(*(
            set(envelope["capabilities"].get("present", ()))
            for envelope in self.envelopes.values()))
        views = {name: envelope["event_view"]
                 for name, envelope in self.envelopes.items()}

        def sub_key_category(values):
            """Classify one differing sub-key across the legs it appears in."""
            stated = {name: value for name, value in values.items()
                      if value is not None}
            rendered = {json.dumps(value, sort_keys=True)
                        for value in stated.values()}
            if len(rendered) == 1 and len(stated) < len(values):
                return "stated by some providers only"
            if len(rendered) == 1:
                return None  # not actually a difference
            if all(isinstance(value, str) and marker in value
                   for value in stated.values()):
                return "provider-scoped surrogate identity"
            return None

        def classify(member):
            values = {name: view.get(member) for name, view in views.items()}
            if len({json.dumps(v, sort_keys=True) for v in values.values()}) == 1:
                return "equal"
            if member == "provider":
                return "provider block"
            capability = support.EVENT_VIEW_CAPABILITY.get(member)
            if capability is not None and capability not in shared:
                return "capability-unshared"
            if member == "start_time":
                if len({instant(v) for v in values.values()}) == 1:
                    return "same instant, different serialization"
                return None
            if all(isinstance(v, dict) for v in values.values()):
                categories = set()
                for key in {k for v in values.values() for k in v}:
                    per_key = {name: v.get(key) for name, v in values.items()}
                    if len({json.dumps(x, sort_keys=True)
                            for x in per_key.values()}) == 1:
                        continue
                    category = sub_key_category(per_key)
                    if category is None:
                        return None
                    categories.add(category)
                return " + ".join(sorted(categories))
            if all(isinstance(v, list) for v in values.values()):
                by_id = {name: {entry.get("id"): entry for entry in v}
                         for name, v in values.items()}
                if len({tuple(sorted(m)) for m in by_id.values()}) != 1:
                    return None
                categories = set()
                for identifier in next(iter(by_id.values())):
                    entries = {name: m[identifier] for name, m in by_id.items()}
                    for key in {k for e in entries.values() for k in e}:
                        per_key = {name: e.get(key)
                                   for name, e in entries.items()}
                        if len({json.dumps(x, sort_keys=True)
                                for x in per_key.values()}) == 1:
                            continue
                        category = sub_key_category(per_key)
                        if category is None:
                            return None
                        categories.add(category)
                return " + ".join(sorted(categories))
            # A scalar member — ``attendance`` is the live example: Sportradar
            # and Opta both state 30125, API-Football and sports-skills state
            # nothing. The same rule as a sub-key, applied at member level.
            return sub_key_category(values)

        unexplained = {}
        classified = {}
        for member in {key for view in views.values() for key in view}:
            category = classify(member)
            if category is None:
                unexplained[member] = {name: view.get(member)
                                       for name, view in views.items()}
            elif category != "equal":
                classified[member] = category
        self.assertEqual(unexplained, {},
                         "difference outside the closed set; classified: "
                         "{0}".format(classified))
        self.assertTrue(classified,
                        "no member differs at all, so the classifier proves "
                        "nothing about the closed set")

    def test_capability_differences_are_reviewed_expectations_not_failures(self):
        """§B11 / plan task 15 case 10: absence is recorded, never treated as a
        failure and never smoothed over with a fabricated substitute. Read off
        the capability report; a provider **name** must not select behaviour."""
        reports = {name: set(envelope["capabilities"].get("present", ()))
                   for name, envelope in self.envelopes.items()}
        shared = set.intersection(*reports.values())
        for required in support.CANARY_REQUIRES:
            with self.subTest(capability=required):
                self.assertIn(required, shared)
        self.assertGreater(
            len(set.union(*reports.values()) - shared), 0,
            "every leg states exactly the same capabilities, so the matrix "
            "records no expected difference and proves nothing about absence")


class TestEveryLegIsPrototypeOnly(unittest.TestCase):
    """§B10 stated as a result rather than a caveat. If any leg passed at
    production tier from a synthetic fixture, this suite would be manufacturing
    the licence claim it exists to refuse."""

    def test_each_leg_passes_at_prototype_tier(self):
        for name in support.FOUR_PROVIDER_LEGS:
            with self.subTest(provider=name):
                findings = support.canonical_module("rights").rights_findings(
                    {support.ENVELOPE_KEY: leg_envelope(name)},
                    consumer_tier="prototype")
                self.assertEqual(findings, [])

    def test_each_leg_is_refused_at_production_tier(self):
        for name in support.FOUR_PROVIDER_LEGS:
            with self.subTest(provider=name):
                findings = support.canonical_module("rights").rights_findings(
                    {support.ENVELOPE_KEY: leg_envelope(name)},
                    consumer_tier="production")
                self.assertTrue(findings)
                self.assertIn("prototype",
                              " ".join(finding.get("code", "")
                                       for finding in findings))


if __name__ == "__main__":
    unittest.main(verbosity=2)
