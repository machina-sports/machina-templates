"""Honest identity resolution method (PR 2, task A16c).

Run from the repository root:

    python3 tests/test_iptc_identity_resolution_method.py -v

Run the file directly, for the same reason as the other IPTC suites: ``tests/``
is a namespace directory with no ``__init__.py``, so ``-m unittest
tests.<module>`` can be shadowed by an installed distribution that ships a
top-level regular ``tests`` package.

**The defect this task closes.** Until now the serializer wrote the literal
``provider-native`` onto *every* crosswalk entry it emitted, for every adapter,
unconditionally. RFC 002 §5 defines three methods — ``provider-native`` (the
provider stated it), ``ordinal-derived`` (no stable provider identifier;
positional) and ``declared`` (supplied by the caller) — and hard-coding the
first one turns the field into decoration. Worse, it turns it into a *false*
claim exactly where this repository already knew better: the Sportradar NFL and
MLB adapters have carried ``MAPPING_CONSTANT_IDENTIFIERS = ("competition",
"season")`` since A15, and their own docstrings say the schedule payload
"carries no competition entity and no season entity at all". Four crosswalk
entries were therefore asserting that Sportradar states an identifier Sportradar
never states.

So the fix is not a new feature. It is making an existing field able to tell the
truth, and then making two adapters tell it:

- ``resolution_method`` becomes an **optional** key on the canonical
  observation's identity-bearing sections, validated fail-closed against exactly
  the three RFC 002 values.
- Absence means ``provider-native``. That default is what keeps every
  already-checked-in corrected fixture byte-identical, and it is defensible on
  its own terms: an adapter that read a provider field and said nothing about it
  did read a provider field.
- The NFL and MLB adapters mark their two mapping constants ``declared``, which
  deliberately changes those two rows' bytes. That change is the deliverable.

**What is deliberately NOT here.** No ``sameAs``, no ``owl:sameAs``, no identity
service, no fuzzy matching and no confidence spread. The crosswalk stays what
RFC 002 says it is — evidence attached to a Machina identity — and this task only
makes it state its own provenance accurately. A test below asserts the absence,
because "we did not build an identity service" is a claim a reader should be able
to check rather than take on trust.
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

from tools.iptc.canonical import observation as observation_module  # noqa: E402
from tools.iptc.canonical import serialize as serialize_module  # noqa: E402
from tools.iptc.canonical.adapters import sportradar_mlb, sportradar_nfl  # noqa: E402
from tools.iptc.canonical.ids import surrogate_resolver  # noqa: E402
from tools.iptc.canonical.observation import validate_observation  # noqa: E402
from tools.iptc.canonical.serialize import (  # noqa: E402
    canonical_envelope,
    provider_identifiers,
    sport_schema_graph,
)

OBSERVATIONS = REPO_ROOT / "tools/iptc/fixtures/observations"

#: The three values RFC 002 §5 defines, in the order the RFC lists them. There is
#: no fourth, and this tuple is what "fail closed" is measured against.
RFC_002_METHODS = ("provider-native", "ordinal-derived", "declared")

#: Every checked-in canonical observation, by the provider namespace it carries.
#: Named rather than globbed: a file appearing here without a line in this table
#: is an observation nobody decided about.
OBSERVATION_FILES = {
    "sports-skills/espn": "sports-skills-espn-soccer-observation.json",
    "api-football": "api-football-soccer-observation.json",
    "sportradar-soccer": "sportradar-soccer-observation.json",
    "stats-perform-opta": "stats-perform-opta-soccer-observation.json",
    "sportradar-tennis": "sportradar-tennis-observation.json",
    "sportradar-nfl": "sportradar-nfl-observation.json",
    "sportradar-mlb": "sportradar-mlb-observation.json",
}

#: The two adapters that inject an identifier no provider field supplies, and the
#: entity kinds they inject it for. Read off the adapters themselves rather than
#: restated, so this table cannot drift from the modules it describes.
CONSTANT_INJECTING_ADAPTERS = {
    "sportradar-nfl": sportradar_nfl.MAPPING_CONSTANT_IDENTIFIERS,
    "sportradar-mlb": sportradar_mlb.MAPPING_CONSTANT_IDENTIFIERS,
}


def load(namespace):
    path = OBSERVATIONS / OBSERVATION_FILES[namespace]
    return json.loads(path.read_text(encoding="utf-8"))


def envelope(namespace):
    return canonical_envelope(load(namespace),
                              id_resolver=surrogate_resolver(namespace))


def crosswalk(namespace):
    return envelope(namespace)["machina_sports_schema"]["provider_ids"]


def serialized(document):
    return json.dumps(document, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


class TestTheThreeMethodsAreNamedOnce(unittest.TestCase):
    """One table, in the vendorable module, matching the RFC exactly."""

    def test_the_canonical_contract_names_exactly_the_rfc_002_methods(self):
        self.assertEqual(tuple(observation_module.RESOLUTION_METHODS),
                         RFC_002_METHODS)

    def test_the_default_is_provider_native(self):
        self.assertEqual(observation_module.RESOLUTION_DEFAULT, "provider-native")
        self.assertIn(observation_module.RESOLUTION_DEFAULT, RFC_002_METHODS)

    def test_the_serializer_reads_the_table_rather_than_holding_a_second_copy(self):
        """Two copies of a closed value set is two chances for one to gain a
        fourth member. The serializer is vendored beside the validator, so it can
        and must import it."""
        self.assertIs(serialize_module.RESOLUTION_METHODS,
                      observation_module.RESOLUTION_METHODS)
        self.assertIs(serialize_module.RESOLUTION_DEFAULT,
                      observation_module.RESOLUTION_DEFAULT)

    def test_the_identity_bearing_sections_are_the_crosswalked_ones(self):
        """A resolution method on a section that mints no crosswalk entry would be
        a fact with nowhere to go. These are exactly the sections
        ``_crosswalk_entries`` reads, minus participants, which are a list."""
        self.assertEqual(
            tuple(observation_module.IDENTITY_BEARING_SECTIONS),
            (("competition",), ("competition", "season"), ("phase",), ("site",),
             ("event",)),
        )


class TestTheValidatorFailsClosedOnAFourthValue(unittest.TestCase):
    """The whole point of a closed set is that nothing else gets in.

    Every mutation is applied to a copy; no checked-in fixture is touched.
    """

    def setUp(self):
        self.document = load("api-football")

    def mutated(self, section, value):
        """``section`` is a path under ``observation``, as
        :data:`IDENTITY_BEARING_SECTIONS` spells them."""
        document = copy.deepcopy(self.document)
        node = document["observation"]
        for key in section:
            node = node[key]
        node["resolution_method"] = value
        return validate_observation(document)

    def test_each_of_the_three_methods_is_accepted_on_every_section(self):
        for section in observation_module.IDENTITY_BEARING_SECTIONS:
            for method in RFC_002_METHODS:
                with self.subTest(section=".".join(section), method=method):
                    self.assertEqual(self.mutated(section, method), [])

    def test_a_fourth_value_is_one_error_naming_the_section_and_the_value(self):
        errors = self.mutated(("competition",), "fuzzy-name-match")
        self.assertEqual(errors, [
            "observation.competition.resolution_method: 'fuzzy-name-match' is not "
            "one of provider-native, ordinal-derived, declared"
        ])

    def test_the_reading_a_future_identity_service_would_want_is_refused_today(self):
        """``fuzzy`` and ``same-as`` are the two values a reader would reach for
        first, and both are exactly what RFC 002 §5 says this phase does not do."""
        for value in ("fuzzy", "same-as", "sameAs", "inferred", "provider_native"):
            with self.subTest(value=value):
                errors = self.mutated(("event",), value)
                self.assertEqual(len(errors), 1)
                self.assertIn("is not one of", errors[0])

    def test_a_non_string_method_is_refused_rather_than_coerced(self):
        errors = self.mutated(("site",), True)
        self.assertEqual(len(errors), 1)
        self.assertIn("observation.site.resolution_method", errors[0])

    def test_a_participant_method_is_validated_at_its_own_index(self):
        document = copy.deepcopy(self.document)
        document["observation"]["participants"][1]["resolution_method"] = "guessed"
        errors = validate_observation(document)
        self.assertEqual(len(errors), 1)
        self.assertIn("observation.participants[1].resolution_method", errors[0])

    def test_a_participant_may_state_any_of_the_three(self):
        for method in RFC_002_METHODS:
            with self.subTest(method=method):
                document = copy.deepcopy(self.document)
                document["observation"]["participants"][0][
                    "resolution_method"] = method
                self.assertEqual(validate_observation(document), [])

    def test_the_serializer_refuses_an_observation_with_a_fourth_value(self):
        """The gate that matters. A conformance envelope is a claim, and a claim
        carrying a resolution method nobody defined is worse than none."""
        document = copy.deepcopy(self.document)
        document["observation"]["competition"]["resolution_method"] = "vibes"
        with self.assertRaises(ValueError) as raised:
            canonical_envelope(document,
                               id_resolver=surrogate_resolver("api-football"))
        self.assertIn("resolution_method", str(raised.exception))


class TestAbsenceMeansProviderNative(unittest.TestCase):
    """The default, and the reason every already-checked-in fixture is stable."""

    def test_an_observation_that_states_nothing_crosswalks_as_provider_native(self):
        for namespace in ("sports-skills/espn", "api-football",
                          "sportradar-soccer", "stats-perform-opta",
                          "sportradar-tennis"):
            with self.subTest(provider=namespace):
                methods = {e["resolution_method"] for e in crosswalk(namespace)}
                self.assertEqual(methods, {"provider-native"})

    def test_no_observation_that_states_nothing_carries_the_key_at_all(self):
        """Omission over a written-out default: a file that spells out
        ``provider-native`` on every section says nothing a reader can act on and
        buries the two places that do."""
        for namespace in ("sports-skills/espn", "api-football",
                          "sportradar-soccer", "stats-perform-opta",
                          "sportradar-tennis"):
            with self.subTest(provider=namespace):
                blob = json.dumps(
                    {k: v for k, v in load(namespace)["observation"].items()
                     if k != "raw"})
                self.assertNotIn("resolution_method", blob)


class TestAStatedMethodReachesBothCrosswalkViews(unittest.TestCase):
    """The envelope block and the graph resources are two projections of one
    entry list. A method that reached one and not the other would make either
    view unciteable."""

    def setUp(self):
        self.document = load("api-football")
        self.document["observation"]["competition"][
            "resolution_method"] = "declared"
        self.document["observation"]["competition"]["season"][
            "resolution_method"] = "ordinal-derived"
        self.resolver = surrogate_resolver("api-football")

    def test_the_envelope_entry_carries_the_stated_method(self):
        entries = provider_identifiers(self.document, id_resolver=self.resolver)
        by_type = {e["entity_type"]: e for e in entries}
        self.assertEqual(by_type["competition"]["resolution_method"], "declared")
        self.assertEqual(by_type["season"]["resolution_method"], "ordinal-derived")
        self.assertEqual(by_type["event"]["resolution_method"], "provider-native")

    def test_the_graph_resource_carries_the_same_method(self):
        graph = sport_schema_graph(self.document, id_resolver=self.resolver)
        resources = [n for n in graph["@graph"]
                     if n["@type"] == "machina:ProviderIdentifier"]
        entries = provider_identifiers(self.document, id_resolver=self.resolver)
        self.assertEqual([n["machina:resolutionMethod"] for n in resources],
                         [e["resolution_method"] for e in entries])

    def test_a_participant_method_reaches_its_own_crosswalk_entry(self):
        self.document["observation"]["participants"][0][
            "resolution_method"] = "declared"
        entries = provider_identifiers(self.document, id_resolver=self.resolver)
        teams = [e for e in entries if e["entity_type"] == "team"]
        self.assertEqual([e["resolution_method"] for e in teams],
                         ["declared", "provider-native"])

    def test_the_method_changes_no_identifier_and_no_official_resource(self):
        """A resolution method is a statement *about* an identifier, so minting
        must not read it. If it did, correcting a method would silently re-mint
        every downstream reference."""
        plain = sport_schema_graph(load("api-football"), id_resolver=self.resolver)
        stated = sport_schema_graph(self.document, id_resolver=self.resolver)
        official = lambda g: [n for n in g["@graph"]  # noqa: E731
                              if not str(n["@type"]).startswith("machina:")]
        self.assertEqual(official(plain), official(stated))
        self.assertEqual([n["@id"] for n in plain["@graph"]],
                         [n["@id"] for n in stated["@graph"]])

    def test_confidence_stays_one_for_every_method(self):
        """``confidence`` measures the strength of the *link*, not the strength of
        the evidence behind it — and all three methods are exact statements about
        where a string came from, so there is nothing here that a lower number
        would be measuring. The field that carries the weakness is
        ``resolution_method``, which is the change this task makes. Inventing a
        spread would be the false precision the profile exists to keep out."""
        self.document["observation"]["participants"][0][
            "resolution_method"] = "declared"
        for entry in provider_identifiers(self.document, id_resolver=self.resolver):
            with self.subTest(entity=entry["entity_type"]):
                self.assertEqual(entry["confidence"], 1.0)


class TestNoCrosswalkOverstatesProviderNativeEvidence(unittest.TestCase):
    """The claim this task exists to make true, checked against the adapters'
    own record of where they inject a constant rather than against a list
    retyped here."""

    def test_every_mapping_constant_is_marked_declared_not_provider_native(self):
        for namespace, kinds in sorted(CONSTANT_INJECTING_ADAPTERS.items()):
            by_type = {e["entity_type"]: e for e in crosswalk(namespace)}
            for kind in kinds:
                with self.subTest(provider=namespace, entity=kind):
                    self.assertIn(kind, by_type)
                    self.assertEqual(by_type[kind]["resolution_method"], "declared")

    def test_every_genuinely_provider_read_identifier_stays_provider_native(self):
        """The other half. Marking everything ``declared`` would be as dishonest
        as marking everything ``provider-native``, in the opposite direction: the
        event, venue and team identifiers really are Sportradar's own."""
        for namespace, kinds in sorted(CONSTANT_INJECTING_ADAPTERS.items()):
            for entry in crosswalk(namespace):
                if entry["entity_type"] in kinds:
                    continue
                with self.subTest(provider=namespace,
                                  entity=entry["entity_type"]):
                    self.assertEqual(entry["resolution_method"],
                                     "provider-native")

    def test_the_observation_states_the_method_rather_than_the_serializer_guessing(self):
        """The serializer must not learn which providers hardcode what. The fact
        belongs to the adapter that injected the constant, and it travels in the
        observation the adapter emits."""
        for namespace, kinds in sorted(CONSTANT_INJECTING_ADAPTERS.items()):
            observation = load(namespace)["observation"]
            sections = {"competition": observation["competition"],
                        "season": observation["competition"]["season"]}
            for kind in kinds:
                with self.subTest(provider=namespace, entity=kind):
                    self.assertEqual(sections[kind]["resolution_method"],
                                     "declared")

    def test_the_adapters_reproduce_the_declared_method_from_their_source(self):
        """Byte-level: the checked-in observations are what the adapters emit, so
        the marking is adapter behaviour and not a fixture someone hand-edited."""
        for namespace, module, source in (
            ("sportradar-nfl", sportradar_nfl,
             "tools/iptc/fixtures/baseline/sportradar-nfl-event.json"),
            ("sportradar-mlb", sportradar_mlb,
             "tools/iptc/fixtures/baseline/sportradar-mlb-event.json"),
        ):
            with self.subTest(provider=namespace):
                payload = json.loads(
                    (REPO_ROOT / source).read_text(encoding="utf-8"))
                produced = module.to_observation(
                    payload, observed_at="2026-03-01T22:05:00+00:00")
                self.assertEqual(produced, load(namespace))

    def test_the_checked_in_observation_files_are_canonical_bytes(self):
        for namespace in sorted(CONSTANT_INJECTING_ADAPTERS):
            with self.subTest(provider=namespace):
                path = OBSERVATIONS / OBSERVATION_FILES[namespace]
                self.assertEqual(path.read_text(encoding="utf-8"),
                                 serialized(load(namespace)))

    def test_no_other_provider_gained_a_declared_entry(self):
        """A blast radius check. Four entries change, across two adapters, and
        nothing else moves."""
        declared = sorted(
            (namespace, entry["entity_type"])
            for namespace in OBSERVATION_FILES
            for entry in crosswalk(namespace)
            if entry["resolution_method"] != "provider-native"
        )
        self.assertEqual(declared, [
            ("sportradar-mlb", "competition"), ("sportradar-mlb", "season"),
            ("sportradar-nfl", "competition"), ("sportradar-nfl", "season"),
        ])


class TestNoSameAsAndNoIdentityService(unittest.TestCase):
    """"We did not build an identity service" is a claim, so it is checked."""

    CANONICAL_MODULES = sorted(
        (REPO_ROOT / "tools/iptc/canonical").rglob("*.py"))

    FORBIDDEN = ("sameAs", "same_as", "owl:sameAs", "skos:exactMatch",
                 "identity_service", "IdentityService")

    def test_no_canonical_module_mentions_a_sameness_assertion(self):
        for path in self.CANONICAL_MODULES:
            text = path.read_text(encoding="utf-8")
            for token in self.FORBIDDEN:
                with self.subTest(module=path.name, token=token):
                    self.assertNotIn(token, text)

    def test_no_emitted_graph_asserts_sameness_between_two_identifiers(self):
        for namespace in sorted(OBSERVATION_FILES):
            blob = json.dumps(
                envelope(namespace)["machina_sports_schema"]["sport_schema_graph"])
            for token in self.FORBIDDEN:
                with self.subTest(provider=namespace, token=token):
                    self.assertNotIn(token, blob)

    def test_the_crosswalk_still_points_one_way_from_evidence_to_identity(self):
        """A crosswalk resource references the Machina identity it is evidence
        for. Nothing references a *second* identity, which is what a sameAs claim
        would need."""
        for namespace in sorted(OBSERVATION_FILES):
            graph = envelope(namespace)[
                "machina_sports_schema"]["sport_schema_graph"]["@graph"]
            for node in graph:
                if node["@type"] != "machina:ProviderIdentifier":
                    continue
                references = [k for k, v in node.items()
                              if isinstance(v, dict) and "@id" in v]
                with self.subTest(provider=namespace, node=node["@id"]):
                    self.assertEqual(references, ["machina:identifies"])

    def test_the_resolver_still_declares_no_canonical_identity_service(self):
        strategy = surrogate_resolver("api-football").strategy
        self.assertEqual(strategy["canonical_id_service"],
                         "not-available-in-this-phase")


if __name__ == "__main__":
    unittest.main(verbosity=2)
