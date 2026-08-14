"""The sports-skills canonical reference contract (PR 2, task A14).

Run from the repository root:

    python3 tests/test_iptc_sports_skills_reference_contract.py -v

Run the file directly, for the same reason as the other IPTC suites: ``tests/``
is a namespace directory with no ``__init__.py``, so ``-m unittest
tests.<module>`` can be shadowed by an installed distribution that ships a
top-level regular ``tests`` package.

**This task ships no adapter.** The native -> canonical adapter for
``sports-skills/espn`` is owned by the ``sports-skills`` repository, which
publishes it and vendors this repository's serializer byte-exact. A second
adapter here would be a second source of truth for one provider reading, and the
two would drift the first time either side fixed a bug. So what is checked in
here is the **contract** rather than an implementation:

1. a synthetic native payload in the exact shape ``sports-skills``' own
   ``_normalize_espn_event`` returns, which is the adapter's input;
2. the ``canonical-observation/1`` document that payload must produce, which is
   the adapter's output and its whole acceptance test;
3. the corrected graph and the full envelope this repository's serializer emits
   from that observation, byte-for-byte.

The future ``sports-skills`` PR reproduces (2) and (3) from (1) using its own
adapter and the vendored runtime. If its bytes differ from these, one of the two
repositories is wrong, and the diff says which field. That is a stronger
cross-repo gate than an adapter here could give, because an adapter here would
only ever prove that *this* repository agrees with itself.

What the tests defend, beyond "the fixtures exist":

- **The observation validates fail-closed**, and the validator is load-bearing on
  this document rather than merely tolerant of it.
- **A native placeholder is not a canonical fact.** The payload carries four
  (``matchday: null``, ``round: ""``, ``round_name: ""``, ``odds: null``) and none
  of them reaches the observation, the graph or the view.
- **Absent means absent.** No clock, no phase, no attendance, no outcome, no
  action and no competition type are invented, because the payload states none.
- **Every resource identifier is a Machina surrogate**; the synthetic provider
  identifiers survive only as ``machina:ProviderIdentifier`` crosswalk evidence.
- **The corrected graph passes the PR 1 harness** — four layers, non-vacuous
  layer 2, four gates at zero, no unverifiable NewsCode.
- **The envelope is refused for a production consumer** by the library gate and
  by the command, and accepted for a prototype one.
- **No sports-skills adapter module exists in this repository**, asserted rather
  than left to review.
"""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.iptc import cli_support  # noqa: E402
from tools.iptc import profile as profile_module  # noqa: E402
from tools.iptc import report as report_module  # noqa: E402
from tools.iptc import validate_graph  # noqa: E402
from tools.iptc.canonical import vocab  # noqa: E402
from tools.iptc.canonical.ids import surrogate_resolver  # noqa: E402
from tools.iptc.canonical.observation import validate_observation  # noqa: E402
from tools.iptc.canonical.serialize import canonical_envelope  # noqa: E402
from tools.iptc.validate import validate_document  # noqa: E402

FIXTURES = REPO_ROOT / "tools/iptc/fixtures"

#: The adapter's input: a synthetic payload in ``sports-skills``' native shape.
SOURCE_PATH = FIXTURES / "source/sports-skills-espn-soccer-native.json"

#: The adapter's output, and the contract PR B has to reproduce byte-for-byte.
OBSERVATION_PATH = FIXTURES / "observations/sports-skills-espn-soccer-observation.json"

GRAPH_PATH = FIXTURES / "corrected/sports-skills-espn-soccer-graph.json"
ENVELOPE_PATH = FIXTURES / "corrected/sports-skills-espn-soccer-envelope.json"

FIXTURE_NAME = "corrected-sports-skills-espn-soccer"

PROVIDER_NAMESPACE = "sports-skills/espn"

#: Fixed inputs. Nothing in the serializer reads the clock; ``observed_at`` is an
#: input field, which is what makes the checked-in bytes reproducible.
OBSERVED_AT = "2026-03-01T22:05:00+00:00"
START_TIME = "2026-03-01T20:00:00+00:00"

#: The keys ``sports-skills``' ``_normalize_espn_event`` returns, in the order it
#: builds them. Recorded so the source fixture stays a faithful native payload:
#: a fixture in a shape the adapter's real input never has would test nothing.
NATIVE_KEYS = (
    "id", "status", "start_time", "matchday", "round", "round_name",
    "competition", "season", "venue", "competitors", "scores", "odds",
    "referees",
)

#: The native fields that carry a stand-in rather than a fact, and what they
#: carry. The adapter contract is that every one of them is dropped.
NATIVE_PLACEHOLDERS = {
    "matchday": None,
    "round": "",
    "round_name": "",
    "odds": None,
}

#: Values ``sports-skills``' own ESPN status vocabulary can hold that are **not**
#: canonical status keys. Recorded here, not mapped: PR B's adapter must map its
#: status vocabulary explicitly and raise on an unmapped code, exactly as the
#: API-Football adapter does. Passing a native status through would put a value on
#: the graph that ``vocab.EVENT_STATUS`` has no NewsCode for.
NATIVE_STATUSES_THAT_ARE_NOT_CANONICAL = ("live", "1st_half", "2nd_half")

#: Every provider identifier the synthetic payload states. They are crosswalk
#: evidence and must never appear in a resource identifier.
PROVIDER_IDS = ("9001", "9011", "9012", "9101",
                "synthetic-league-1", "synthetic-league-1-2026")

#: The **runtime** rights classification: what the data an adapter emits actually
#: is. ``sports-skills`` reads ESPN's public endpoints, so every envelope its
#: adapter produces — in production, off real fixtures — carries this class. It is
#: therefore the only honest value for the observation this contract pins, because
#: PR B's adapter stamps one constant onto both this synthetic fixture and every
#: real match it ever reads. A class naming the fixture would travel out with real
#: events and call them synthetic, which is a false statement about live data and
#: exactly the kind of blurred fact this contract exists to prevent.
RUNTIME_RIGHTS_CLASS = "open-public"

#: The **fixture evidence** classification: what the checked-in payload behind
#: this row is. A different question from the one above, with a different answer,
#: and it stays recorded in ``provenance.json`` rather than in the envelope. The
#: match, the teams, the venue and the competition are invented, so this row is
#: evidence about the mapping contract and about nothing observed.
FIXTURE_EVIDENCE_CLASS = "mapping-contract-synthetic"


def source():
    return json.loads(SOURCE_PATH.read_text(encoding="utf-8"))


def observation_document():
    return json.loads(OBSERVATION_PATH.read_text(encoding="utf-8"))


def envelope():
    return canonical_envelope(observation_document(),
                              id_resolver=surrogate_resolver(PROVIDER_NAMESPACE))


def serialized(document):
    """The exact bytes every fixture in this contract is checked in as."""
    return json.dumps(document, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def run_cli(argv):
    """``validate_graph``'s command entry point, with stdout captured."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        status = validate_graph.main(argv)
    return status, buffer.getvalue()


class TestSourceFixtureIsObviouslySynthetic(unittest.TestCase):
    """No real entity, no real endpoint, and no doubt about which it is.

    This payload is published in two repositories. If a reader has to check
    whether a name is a real club, the fixture has already failed at its job.
    """

    def setUp(self):
        self.native = source()
        self.blob = SOURCE_PATH.read_text(encoding="utf-8")

    def test_every_name_announces_itself_as_synthetic(self):
        self.assertIn("Synthetic", self.blob)
        for token in ("Arsenal", "Real Madrid", "Manchester", "Liverpool",
                      "Premier League", "espn.com", "http"):
            with self.subTest(token=token):
                self.assertNotIn(token, self.blob)

    def test_every_identifier_is_a_9xxx_or_synthetic_token(self):
        identifiers = [
            self.native["id"],
            self.native["competition"]["id"],
            self.native["season"]["id"],
            self.native["venue"]["id"],
        ] + [c["team"]["id"] for c in self.native["competitors"]]
        for identifier in identifiers:
            with self.subTest(identifier=identifier):
                self.assertTrue(
                    identifier.startswith("9") or identifier.startswith("synthetic"),
                    "identifier {0!r} is neither 9xxx nor synthetic".format(identifier),
                )

    def test_the_shape_is_the_one_the_adapter_actually_receives(self):
        """A fixture in a shape ``_normalize_espn_event`` never returns would prove
        nothing about the adapter that reads it."""
        self.assertEqual(tuple(self.native), NATIVE_KEYS)
        self.assertEqual([c["qualifier"] for c in self.native["competitors"]],
                         ["home", "away"])
        self.assertEqual(sorted(self.native["venue"]),
                         ["city", "country", "id", "name"])
        self.assertEqual(sorted(self.native["competitors"][0]["team"]),
                         ["abbreviation", "id", "name", "short_name"])

    def test_the_payload_carries_the_native_placeholders_on_purpose(self):
        """They are the contract's evidence, not sloppiness: an adapter that
        forwards them puts ``null`` and ``""`` into a conforming document."""
        for key, value in sorted(NATIVE_PLACEHOLDERS.items()):
            with self.subTest(key=key):
                self.assertIn(key, self.native)
                self.assertEqual(self.native[key], value)

    def test_the_scoreline_is_the_native_integer_form(self):
        """Native scores are integers; the canonical contract is strings, because
        the pinned shapes declare ``sh:datatype xsd:string``."""
        self.assertEqual([c["score"] for c in self.native["competitors"]], [2, 1])
        self.assertEqual(self.native["scores"], {"home": 2, "away": 1})

    def test_the_file_is_checked_in_as_canonical_bytes(self):
        """``sports-skills`` ships a byte-identical copy of this file. Two copies
        that differ only in whitespace make a byte-comparison gate useless."""
        self.assertEqual(self.blob, serialized(self.native))


class TestObservationIsTheReferenceContract(unittest.TestCase):
    """``validate_observation`` is the acceptance test PR B's adapter must pass."""

    def setUp(self):
        self.document = observation_document()
        self.observation = self.document["observation"]

    def test_the_observation_is_valid(self):
        self.assertEqual(validate_observation(self.document), [])

    def test_the_document_claims_the_canonical_observation_contract(self):
        self.assertEqual(self.document["schema_version"], "canonical-observation/1.1")
        self.assertEqual(sorted(self.document), ["observation", "schema_version"])

    def test_the_provider_is_recorded_as_open_data(self):
        self.assertEqual(self.observation["provider"],
                         {"namespace": PROVIDER_NAMESPACE, "family": "open-data"})

    def test_the_adapter_block_names_the_sports_skills_owner(self):
        """Provenance with no adapter block is an anonymous claim. This one names
        the module in the repository that owns the reading, which is also how a
        reviewer knows no adapter here produced it."""
        adapter = self.observation["adapter"]
        self.assertEqual(adapter["name"], "sports_skills.canonical.adapters.football")
        self.assertTrue(adapter["version"])
        self.assertFalse(adapter["name"].startswith("tools."))

    def test_no_source_ref_is_request_shaped(self):
        refs = self.observation["adapter"]["source_refs"]
        self.assertEqual([ref["kind"] for ref in refs], ["endpoint-class"])
        for ref in refs:
            for marker in ("://", "?", "&", "key=", "token=", "secret",
                           "Authorization"):
                with self.subTest(marker=marker):
                    self.assertNotIn(marker, ref["value"])

    def test_the_rights_block_carries_the_runtime_open_data_classification(self):
        """The class describes the data the adapter emits, not the fixture it was
        demonstrated on. ``sports-skills`` reads ESPN's public endpoints, so
        ``open-public`` is what its envelopes carry — here and off real matches.

        The two flags are unchanged and still what the gate reads: the package is
        public and personal/non-commercial and can never emit anything else."""
        rights = self.observation["rights"]
        self.assertEqual(rights["data_class"], RUNTIME_RIGHTS_CLASS)
        self.assertIs(rights["prototype_only"], True)
        self.assertIs(rights["commercial_use"], False)
        for word in ("licensed", "redistributable"):
            with self.subTest(word=word):
                self.assertNotIn(word, rights["data_class"])

    def test_the_sport_is_soccer_by_medtop_code_and_key(self):
        self.assertEqual(self.observation["sport"],
                         {"medtop": "20001065", "key": "soccer"})

    def test_the_fixed_time_inputs_are_carried_verbatim(self):
        self.assertEqual(self.observation["observed_at"], OBSERVED_AT)
        self.assertEqual(self.observation["event"]["start_time"], START_TIME)

    def test_the_status_is_the_canonical_key_a_pinned_newscode_admits(self):
        self.assertEqual(self.observation["event"]["status"], "closed")
        self.assertIn("closed", vocab.EVENT_STATUS)

    def test_the_native_status_vocabulary_is_not_canonical_and_must_be_mapped(self):
        """The one value this payload carries happens to coincide with a canonical
        key. Three of its siblings do not, which is why PR B's adapter must map
        explicitly and raise on an unmapped code rather than pass the string
        through."""
        for native in NATIVE_STATUSES_THAT_ARE_NOT_CANONICAL:
            with self.subTest(native=native):
                self.assertNotIn(native, vocab.EVENT_STATUS)

    def test_home_comes_first_and_both_teams_carry_alignment_and_score(self):
        """Ordering is part of the contract: the cross-provider equivalence test
        compares ``[home, away]`` positionally across providers."""
        self.assertEqual(
            [(p["kind"], p["provider_id"], p["name"], p["alignment"], p["score"])
             for p in self.observation["participants"]],
            [("team", "9011", "Synthetic Home United", "home", "2"),
             ("team", "9012", "Synthetic Away Town", "away", "1")],
        )

    def test_the_scoreline_is_a_string_not_a_number(self):
        for participant in self.observation["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertIsInstance(participant["score"], str)

    def test_the_string_score_is_pinned_here_because_the_graph_cannot_reveal_it(self):
        """``validate_observation`` does not type-check a participant score and the
        serializer coerces, so the native integer ``2`` and the string ``"2"``
        produce the same ``sh:datatype xsd:string`` literal. The graph therefore
        cannot tell an adapter that forgot to convert from one that did — which is
        why the string form is pinned in *this* file, the one PR B's adapter output
        is compared to byte-for-byte."""
        document = observation_document()
        document["observation"]["participants"][0]["score"] = 2
        self.assertEqual(validate_observation(document), [])
        graph = canonical_envelope(
            document, id_resolver=surrogate_resolver(PROVIDER_NAMESPACE)
        )["machina_sports_schema"]["sport_schema_graph"]
        participation = next(n for n in graph["@graph"]
                            if n["@type"] == "sport:TeamParticipation")
        self.assertEqual(participation["sport:score"], "2")

    def test_the_competition_and_its_season_are_both_identified(self):
        competition = self.observation["competition"]
        self.assertEqual(competition["provider_id"], "synthetic-league-1")
        self.assertEqual(competition["name"], "Synthetic Premier Division")
        self.assertEqual(competition["season"]["provider_id"],
                         "synthetic-league-1-2026")

    def test_the_raw_payload_is_the_source_fixture_unaltered(self):
        """``raw`` is the only place the native payload survives, and it survives
        whole: that is what makes "we omitted it" checkable rather than asserted."""
        self.assertEqual(self.observation["raw"], source())

    def test_the_file_is_checked_in_as_canonical_bytes(self):
        self.assertEqual(OBSERVATION_PATH.read_text(encoding="utf-8"),
                         serialized(self.document))


class TestNativePlaceholdersBecomeNothing(unittest.TestCase):
    """The four native stand-ins, and where each one does not appear."""

    def setUp(self):
        self.observation = observation_document()["observation"]

    def test_no_placeholder_reaches_any_section_but_raw(self):
        sections = {k: v for k, v in self.observation.items() if k != "raw"}
        blob = json.dumps(sections)
        self.assertNotIn("null", blob)
        self.assertNotIn('""', blob)

    def test_no_phase_is_derived_from_the_round_fields(self):
        """``round`` and ``matchday`` are empty, and ``round_name`` is a display
        string with no identifier the provider addresses. Recording it as a
        provider identifier would invent provider-native evidence."""
        self.assertNotIn("phase", self.observation)

    def test_no_odds_or_referee_fact_is_claimed(self):
        for key in ("odds", "referees"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.observation)

    def test_the_placeholders_are_still_readable_in_raw(self):
        """The mirror. The absences above are not lost, they are where a reviewer
        can see exactly what the native payload said."""
        for key, value in sorted(NATIVE_PLACEHOLDERS.items()):
            with self.subTest(key=key):
                self.assertEqual(self.observation["raw"][key], value)


class TestAbsenceStaysAbsent(unittest.TestCase):
    """Facts this payload does not state, and does not gain."""

    def setUp(self):
        self.observation = observation_document()["observation"]

    def test_no_clock_reading_is_invented(self):
        """The normalized native shape has no elapsed minute or period at all."""
        self.assertNotIn("clock", self.observation["event"])

    def test_no_competition_type_is_invented(self):
        self.assertNotIn("type", self.observation["competition"])

    def test_no_outcome_is_derived_from_the_scoreline(self):
        """The native shape carries no winner flag. ``2-1`` plus ``closed`` makes a
        win obvious to a reader and is still an inference, and
        ``sport:eventOutcome`` is exactly the wrong place for one."""
        self.assertNotIn("outcome_type", self.observation["event"])
        for participant in self.observation["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("outcome", participant)

    def test_no_attendance_and_no_end_time_are_invented(self):
        for key in ("attendance", "end_time"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.observation["event"])

    def test_no_action_no_membership_and_no_individual_are_invented(self):
        for key in ("actions", "memberships"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.observation)
        self.assertEqual([p["kind"] for p in self.observation["participants"]],
                         ["team", "team"])

    def test_no_statistic_is_invented_for_a_summary_that_carries_none(self):
        for participant in self.observation["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("statistics", participant)


class TestTheContractFailsClosed(unittest.TestCase):
    """The validator is load-bearing on this document, not merely tolerant of it.

    Every mutation is applied to a copy; the checked-in fixture is never touched.
    """

    def mutated(self, mutate):
        document = observation_document()
        mutate(document["observation"])
        return validate_observation(document)

    def test_dropping_the_rights_block_is_one_deterministic_error(self):
        errors = self.mutated(lambda o: o.pop("rights"))
        self.assertEqual(errors, ["observation.rights: required field is missing"])

    def test_dropping_the_adapter_block_is_one_deterministic_error(self):
        errors = self.mutated(lambda o: o.pop("adapter"))
        self.assertEqual(errors, ["observation.adapter: required field is missing"])

    def test_a_request_shaped_source_ref_is_refused(self):
        def corrupt(observation):
            observation["adapter"]["source_refs"] = [
                {"kind": "endpoint-class",
                 "value": "https://site.api.espn.invalid/summary?event=9001"}
            ]
        errors = self.mutated(corrupt)
        self.assertTrue(errors)
        self.assertIn("endpoint class", " ".join(errors))

    def test_forwarding_a_native_placeholder_is_refused(self):
        """The failure an adapter that passed ``round: ""`` through would get."""
        errors = self.mutated(
            lambda o: o.__setitem__("phase", {"provider_id": "", "name": ""}))
        self.assertTrue(errors)
        self.assertIn("empty string is not a fact", " ".join(errors))

    def test_forwarding_a_native_null_is_refused(self):
        errors = self.mutated(
            lambda o: o["event"].__setitem__("attendance", None))
        self.assertEqual(
            errors, ["observation.event.attendance: null is not a fact; "
                     "omit the key instead"])

    def test_a_naive_start_time_is_refused(self):
        errors = self.mutated(
            lambda o: o["event"].__setitem__("start_time", "2026-03-01T20:00:00"))
        self.assertTrue(errors)
        self.assertIn("explicit offset", " ".join(errors))

    def test_the_serializer_refuses_an_invalid_observation_outright(self):
        """A conformance claim citing a profile and a pin, about a document nobody
        validated, is worse than no claim."""
        document = observation_document()
        document["observation"].pop("rights")
        with self.assertRaises(ValueError):
            canonical_envelope(document,
                               id_resolver=surrogate_resolver(PROVIDER_NAMESPACE))


class TestCheckedInOutputsAreReproducible(unittest.TestCase):
    """A checked-in fixture that cannot be regenerated is a screenshot."""

    def test_the_envelope_fixture_is_reproducible_byte_for_byte(self):
        self.assertEqual(ENVELOPE_PATH.read_text(encoding="utf-8"),
                         serialized(envelope()))

    def test_the_graph_fixture_is_exactly_the_envelope_graph(self):
        """One graph, checked in twice: once inside the envelope a consumer
        receives and once as the standalone JSON-LD the harness validates."""
        self.assertEqual(
            json.loads(GRAPH_PATH.read_text(encoding="utf-8")),
            envelope()["machina_sports_schema"]["sport_schema_graph"],
        )

    def test_two_runs_agree(self):
        self.assertEqual(serialized(envelope()), serialized(envelope()))

    def test_the_envelope_carries_every_rfc_002_part_and_both_versions(self):
        block = envelope()["machina_sports_schema"]
        self.assertEqual(sorted(block), [
            "capabilities", "event_view", "profile", "provenance", "provider_ids",
            "rights", "schema_version", "sport_schema_graph",
        ])
        self.assertEqual(block["schema_version"], "machina-sports-schema/1")
        self.assertEqual(block["profile"], "machina-iptc-profile/1.2")

    def test_the_provenance_block_cites_the_pin_and_the_adapter(self):
        provenance = envelope()["machina_sports_schema"]["provenance"]
        self.assertEqual(provenance["provider"]["namespace"], PROVIDER_NAMESPACE)
        self.assertEqual(provenance["adapter"]["name"],
                         "sports_skills.canonical.adapters.football")
        self.assertEqual(provenance["observed_at"], OBSERVED_AT)
        self.assertEqual(provenance["upstream_pin"]["target_version"], "1.1")
        self.assertEqual(provenance["determinism"]["id_strategy"],
                         "provider-scoped-surrogate")


class TestIdentityIsASurrogate(unittest.TestCase):
    """Provider identifiers are crosswalk evidence; identity is minted."""

    def setUp(self):
        self.block = envelope()["machina_sports_schema"]
        self.graph = self.block["sport_schema_graph"]["@graph"]

    def test_every_resource_id_is_a_marked_machina_surrogate(self):
        for node in self.graph:
            with self.subTest(node=node["@type"]):
                self.assertRegex(node["@id"],
                                 r"^urn:machina:sports:[a-z-]+:x[0-9a-f]{32}$")

    def test_no_provider_identifier_is_used_as_a_resource_id(self):
        identifiers = [node["@id"] for node in self.graph]
        for provider_id in PROVIDER_IDS:
            with self.subTest(provider_id=provider_id):
                for node_id in identifiers:
                    self.assertNotIn(provider_id, node_id)

    def test_no_provider_namespace_token_survives_in_a_resource_id(self):
        for node in self.graph:
            with self.subTest(node=node["@id"]):
                self.assertIsNone(
                    profile_module.provider_namespace_in_id(node["@id"]))

    def test_the_crosswalk_holds_every_identifier_the_payload_stated(self):
        entries = self.block["provider_ids"]
        self.assertEqual([e["entity_type"] for e in entries],
                         ["competition", "season", "site", "event", "team", "team"])
        self.assertEqual(sorted(e["provider_id"] for e in entries),
                         sorted(PROVIDER_IDS))
        for entry in entries:
            with self.subTest(entity=entry["entity_type"]):
                self.assertEqual(entry["provider_namespace"], PROVIDER_NAMESPACE)
                self.assertEqual(entry["resolution_method"], "provider-native")
                self.assertEqual(entry["confidence"], 1.0)

    def test_every_crosswalk_entry_names_the_field_it_came_from(self):
        by_type = {e["entity_type"]: e for e in self.block["provider_ids"]}
        self.assertEqual(by_type["event"]["evidence"],
                         "observation.event.provider_id")
        self.assertEqual(by_type["season"]["evidence"],
                         "observation.competition.season.provider_id")
        self.assertEqual(by_type["site"]["evidence"],
                         "observation.site.provider_id")

    def test_a_provider_identifier_appears_only_on_a_crosswalk_resource(self):
        """The rule stated positively: wherever a provider identifier is in the
        graph, it is the value of a ``machina:`` property on a
        ``machina:ProviderIdentifier``, which is the sanctioned place for it."""
        for node in self.graph:
            carried = [value for value in node.values()
                       if isinstance(value, str) and value in PROVIDER_IDS]
            if carried:
                with self.subTest(node=node["@id"]):
                    self.assertEqual(node["@type"], "machina:ProviderIdentifier")

    def test_the_two_crosswalk_views_agree(self):
        """The flat envelope block and the graph resources are two projections of
        one entry list. Two lists that could disagree would make either useless."""
        resources = [n for n in self.graph
                     if n["@type"] == "machina:ProviderIdentifier"]
        self.assertEqual(
            [(n["machina:providerNamespace"], n["machina:providerId"])
             for n in resources],
            [(e["provider_namespace"], e["provider_id"])
             for e in self.block["provider_ids"]],
        )


class TestNothingFabricatedReachesTheOutput(unittest.TestCase):
    """Scanned over emitted output, not over a helper: a helper that drops
    placeholders proves nothing if one call site bypasses it."""

    def setUp(self):
        self.block = envelope()["machina_sports_schema"]

    def test_no_null_no_empty_string_and_no_placeholder_in_the_graph(self):
        blob = json.dumps(self.block["sport_schema_graph"])
        self.assertNotIn("null", blob)
        self.assertNotIn('""', blob)
        for value in sorted(profile_module.PLACEHOLDER_VALUES):
            if value:
                with self.subTest(placeholder=value):
                    self.assertNotIn('"{0}"'.format(value), blob)

    def test_no_null_no_empty_string_and_no_placeholder_in_the_view(self):
        """``provider.raw`` is excluded deliberately: it is the native payload's own
        bytes, it genuinely carries two nulls and two empty strings, and rewriting
        it would destroy the one field whose value is being an unaltered record."""
        view = copy.deepcopy(self.block["event_view"])
        view.get("provider", {}).pop("raw", None)
        blob = json.dumps(view)
        self.assertNotIn("null", blob)
        self.assertNotIn('""', blob)
        for value in sorted(profile_module.PLACEHOLDER_VALUES):
            if value:
                with self.subTest(placeholder=value):
                    self.assertNotIn('"{0}"'.format(value), blob)

    def test_no_stub_resource_is_emitted(self):
        """A resource carrying only an ``@id`` and a ``@type`` reads as a described
        entity to every consumer and describes nothing."""
        for node in self.block["sport_schema_graph"]["@graph"]:
            with self.subTest(node=node["@id"]):
                self.assertGreater(len(node), 2)

    def test_no_official_resource_carries_a_machina_property(self):
        """The pinned shapes are ``sh:closed``, so one ``machina:`` key on a
        ``sport:`` resource fails layer 2 for the whole document."""
        for node in self.block["sport_schema_graph"]["@graph"]:
            if str(node["@type"]).startswith("sport:"):
                with self.subTest(resource=node["@type"]):
                    self.assertEqual([k for k in node if k.startswith("machina:")], [])

    def test_the_native_payload_survives_only_in_the_view_and_the_observation(self):
        self.assertEqual(self.block["event_view"]["provider"]["raw"], source())
        self.assertNotIn("raw", json.dumps(self.block["sport_schema_graph"]))
        self.assertNotIn("raw", self.block["provenance"])


class TestGraphIsNonVacuousAndUsesOnlyVerifiableTerms(unittest.TestCase):
    """The shape of the corrected graph, before the harness is asked about it."""

    def setUp(self):
        self.graph = envelope()["machina_sports_schema"]["sport_schema_graph"]

    def test_the_document_is_one_inline_context_and_one_flat_graph(self):
        self.assertEqual(sorted(self.graph), ["@context", "@graph"])
        self.assertIsInstance(self.graph["@context"], dict)
        self.assertTrue(all("@context" not in node for node in self.graph["@graph"]))

    def test_every_official_class_the_payload_supports_is_instantiated(self):
        types = [node["@type"] for node in self.graph["@graph"]]
        for expected in ("sport:Competition", "sport:Site", "sport:Team",
                         "sport:Event", "sport:TeamParticipation",
                         "machina:ProviderIdentifier",
                         "machina:ObservationProvenance"):
            with self.subTest(expected=expected):
                self.assertIn(expected, types)
        self.assertEqual(types.count("sport:Competition"), 2)
        self.assertEqual(types.count("sport:TeamParticipation"), 2)
        self.assertEqual(types.count("sport:Team"), 2)

    def test_no_phase_resource_is_emitted_for_a_payload_with_no_round(self):
        types = [node["@type"] for node in self.graph["@graph"]]
        self.assertNotIn("sport:CompetitionPhase", types)

    def test_the_event_carries_its_mandatory_properties(self):
        event = next(n for n in self.graph["@graph"] if n["@type"] == "sport:Event")
        self.assertEqual(event["sport:eventStatus"],
                         {"@id": "speventstatus:post-event"})
        self.assertEqual(event["sport:startDateTime"],
                         {"@value": START_TIME, "@type": "xsd:dateTime"})
        self.assertEqual(len(event["sport:participation"]), 2)
        self.assertTrue(all(set(r) == {"@id"} for r in event["sport:participation"]))

    def test_every_newscode_is_a_node_reference_in_a_pinned_scheme(self):
        """A bare string expands to a literal and fails layers 3 and 4; an unpinned
        scheme is ``unverifiable``, which fails layer 4 closed."""
        pinned = set(vocab.SCHEME_PATH) | {"medtop"}
        codes = []
        for node in self.graph["@graph"]:
            for key, value in node.items():
                if isinstance(value, dict) and set(value) == {"@id"} \
                        and ":" in value["@id"] and not value["@id"].startswith("urn:"):
                    codes.append(value["@id"])
        self.assertTrue(codes)
        for code in codes:
            with self.subTest(code=code):
                self.assertIn(code.split(":", 1)[0], pinned)

    def test_the_site_carries_a_label_and_nothing_the_closed_shape_rejects(self):
        """``SiteShape`` is ``sh:closed`` with no property shapes, so ``rdfs:label``
        is the only admissible key. City and country are real facts and travel in
        ``event_view`` rather than being forced into a shape that rejects them."""
        site = next(n for n in self.graph["@graph"] if n["@type"] == "sport:Site")
        self.assertEqual(sorted(site), ["@id", "@type", "rdfs:label"])
        view_site = envelope()["machina_sports_schema"]["event_view"]["site"]
        self.assertEqual(view_site["city"], "Synthetic City")
        self.assertEqual(view_site["country"], "SYN")


class TestCorrectedGraphConformance(unittest.TestCase):
    """The claim this task exists to make, checked by the PR 1 harness rather than
    by assertion. Run against the **checked-in** file, because that file is a
    registered fixture and ``--check`` runs it too: one document, two callers."""

    @classmethod
    def setUpClass(cls):
        cls.result = validate_document(GRAPH_PATH, FIXTURE_NAME,
                                       repo_root=REPO_ROOT)

    def test_all_four_layers_pass(self):
        for layer in ("jsonld_parse", "official_shacl", "machina_profile",
                      "controlled_vocabulary"):
            with self.subTest(layer=layer):
                self.assertTrue(self.result.layers[layer]["ok"],
                                self.result.layers[layer]["detail"])

    def test_the_shacl_pass_is_not_vacuous(self):
        shacl = self.result.layers["official_shacl"]["detail"]
        self.assertFalse(shacl["vacuous"])
        self.assertGreater(shacl["official_class_instances"], 0)
        self.assertEqual(shacl["result_count"], 0)

    def test_all_four_gates_are_zero(self):
        for gate in ("unknown_sport_terms", "invalid_newscode_values",
                     "duplicate_resource_ids",
                     "provider_properties_in_iptc_namespace"):
            with self.subTest(gate=gate):
                self.assertEqual(self.result.counters[gate], 0)

    def test_no_newscode_is_unverifiable(self):
        """An unverifiable code is one from a scheme upstream names but does not
        pin at this commit. Passing on one would be a conformance claim nothing
        could check."""
        self.assertEqual(self.result.counters["unverifiable_newscode_values"], 0)
        detail = self.result.layers["controlled_vocabulary"]["detail"]
        self.assertGreater(len(detail["valid"]), 0)
        for key in ("invalid", "undeclared_prefix", "unverifiable"):
            with self.subTest(key=key):
                self.assertEqual(detail[key], [])

    def test_the_profile_layer_found_nothing(self):
        self.assertEqual(self.result.layers["machina_profile"]["detail"]["findings"],
                         [])

    def test_the_document_conforms_overall(self):
        self.assertTrue(self.result.conforms)


class TestRightsGateRefusesAProductionConsumer(unittest.TestCase):
    """Prototype-only open data reaching a commercial surface is what the gate is
    for, and it is checked twice: as the library function RFC 002 §9 names, and as
    the command an operator actually runs."""

    def setUp(self):
        self.checked_in = json.loads(ENVELOPE_PATH.read_text(encoding="utf-8"))

    def test_the_library_gate_refuses_production_with_exactly_one_finding(self):
        """``prototype_only`` and ``commercial_use: false`` travel together on every
        open-data envelope, so reporting both buries the line that names the fix."""
        findings = validate_graph.rights_findings(self.checked_in,
                                                  consumer_tier="production")
        self.assertEqual([f["code"] for f in findings], ["rights-prototype-only"])
        self.assertEqual(findings[0]["data_class"],
                         self.checked_in["machina_sports_schema"]["rights"]["data_class"])

    def test_the_library_gate_accepts_a_prototype_consumer(self):
        self.assertEqual(
            validate_graph.rights_findings(self.checked_in,
                                           consumer_tier="prototype"), [])

    def test_the_command_refuses_production_and_exits_nonzero(self):
        argument = str(ENVELOPE_PATH.relative_to(REPO_ROOT))
        status, out = run_cli(["--consumer-tier", "production", argument])
        self.assertEqual(status, 1, out)
        self.assertIn("rights-prototype-only", out)

    def test_the_command_accepts_prototype_and_still_validates_the_graph(self):
        argument = str(ENVELOPE_PATH.relative_to(REPO_ROOT))
        status, out = run_cli(["--consumer-tier", "prototype", argument])
        self.assertEqual(status, 0, out)


class TestRuntimeRightsClassIsNotTheFixtureEvidenceClass(unittest.TestCase):
    """Two different questions, two different answers, and neither one may be
    read off the other.

    **What is this data?** is answered by the envelope, at runtime, by a class the
    adapter stamps on every document it emits. ``sports-skills`` reads ESPN's
    public endpoints, so that answer is ``open-public`` — for this fixture and for
    every real match the published adapter will ever read, because it is one
    constant in one module.

    **What is the checked-in evidence behind this audit row?** is answered by
    ``provenance.json``, and the answer is ``mapping-contract-synthetic``: the
    match, the teams, the venue and the competition are invented.

    The first class was previously ``mapping-contract-synthetic-open-prototype``,
    which answered the second question in the field that carries the first. Shipped
    downstream that class travels out attached to real ESPN fixtures and calls them
    synthetic — a false statement about live data, made by the contract that exists
    to keep such statements out. Reclassifying it does not weaken the gate: the two
    booleans are untouched and a production consumer is still refused, which is the
    other half of what these tests hold.
    """

    def setUp(self):
        self.observation = observation_document()["observation"]
        self.checked_in = json.loads(ENVELOPE_PATH.read_text(encoding="utf-8"))
        self.block = self.checked_in["machina_sports_schema"]
        self.entry = next(e for e in report_module.load_provenance()["corrected"]
                          if e["fixture"] == FIXTURE_NAME)

    def test_the_runtime_class_is_the_authoritative_open_data_classification(self):
        self.assertEqual(self.observation["rights"]["data_class"],
                         RUNTIME_RIGHTS_CLASS)

    def test_every_place_the_runtime_class_travels_carries_the_same_value(self):
        """The class is written three times into one envelope — the rights block a
        consumer reads, the provenance block an auditor reads, and the graph node a
        standards consumer reads. Three copies that can disagree are three chances
        to cite the wrong one."""
        graph_node = next(node for node in self.block["sport_schema_graph"]["@graph"]
                          if "machina:rightsClass" in node)
        for label, value in (
            ("envelope rights", self.block["rights"]["data_class"]),
            ("envelope provenance", self.block["provenance"]["rights"]["data_class"]),
            ("graph machina:rightsClass", graph_node["machina:rightsClass"]),
        ):
            with self.subTest(where=label):
                self.assertEqual(value, RUNTIME_RIGHTS_CLASS)

    def test_no_runtime_rights_class_calls_a_real_event_synthetic(self):
        """The load-bearing assertion. This class is emitted by a published
        adapter onto live ESPN reads; the word ``synthetic`` in it would be a lie
        about every one of them."""
        for label, value in (
            ("observation", self.observation["rights"]["data_class"]),
            ("envelope rights", self.block["rights"]["data_class"]),
            ("envelope provenance", self.block["provenance"]["rights"]["data_class"]),
        ):
            with self.subTest(where=label):
                self.assertNotIn("synthetic", value)
                self.assertNotIn("prototype", value)

    def test_the_fixture_evidence_class_is_still_recorded_as_synthetic(self):
        """The fact that moved out of the envelope did not evaporate. It is
        recorded where it was always true: the provenance of the checked-in row."""
        self.assertIn(FIXTURE_EVIDENCE_CLASS, self.entry["rights"])
        self.assertIn("SYNTHETIC", self.entry["provenance"])
        self.assertIn("INVENTED", self.entry["limitation"])

    def test_the_provenance_entry_names_both_classes_and_says_which_is_which(self):
        """A row naming one class leaves a reader to assume it answers both
        questions, which is the confusion this task removes."""
        rights = self.entry["rights"]
        self.assertIn(RUNTIME_RIGHTS_CLASS, rights)
        self.assertIn(FIXTURE_EVIDENCE_CLASS, rights)
        self.assertIn("runtime", rights)
        self.assertIn("fixture", rights)

    def test_the_two_classes_are_not_the_same_string(self):
        """The guard against 'simplifying' them back into one field. If these ever
        collapse, one of the two facts has been lost."""
        self.assertNotEqual(RUNTIME_RIGHTS_CLASS, FIXTURE_EVIDENCE_CLASS)
        self.assertNotIn(FIXTURE_EVIDENCE_CLASS, RUNTIME_RIGHTS_CLASS)

    def test_the_source_fixture_is_unchanged_and_still_obviously_synthetic(self):
        """Reclassifying the runtime rights of the reading must not touch the
        payload the reading was demonstrated on."""
        self.assertIn("Synthetic", SOURCE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(self.observation["raw"], source())

    def test_reclassifying_the_data_did_not_weaken_the_gate(self):
        """The other half. ``open-public`` is a truthful class and still
        prototype-only and non-commercial, so a production consumer is refused
        exactly once and a prototype consumer passes."""
        findings = validate_graph.rights_findings(self.checked_in,
                                                  consumer_tier="production")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["code"], "rights-prototype-only")
        self.assertEqual(findings[0]["data_class"], RUNTIME_RIGHTS_CLASS)
        self.assertEqual(
            validate_graph.rights_findings(self.checked_in,
                                           consumer_tier="prototype"), [])

    def test_the_gate_that_decides_is_the_vendorable_one(self):
        """``sports-skills`` runs this rule on its own envelopes and cannot import
        this repository, so the gate this contract is checked with has to be the
        module that crosses the boundary — not a copy of it that lives here."""
        from tools.iptc.canonical import rights as canonical_rights

        self.assertIs(validate_graph.rights_findings,
                      canonical_rights.rights_findings)


class TestCapabilityReportCarriesOnlyWhatTheFixtureStates(unittest.TestCase):
    """A capability report is a promise a consumer plans against. Claiming one
    this payload cannot keep is worse than claiming none."""

    def setUp(self):
        self.capabilities = envelope()["machina_sports_schema"]["capabilities"]

    def test_the_tier_is_core_and_no_higher_tier_is_claimed(self):
        self.assertEqual(self.capabilities["tier"], "core")
        self.assertEqual(self.capabilities["tiers_satisfied"], ["core"])
        self.assertEqual(self.capabilities["by_tier"]["core"]["required_absent"], [])

    def test_present_is_exactly_what_the_payload_supports(self):
        self.assertEqual(self.capabilities["present"], [
            "event.competition", "event.identity", "event.participants",
            "event.score", "event.start_time", "event.status", "provenance",
        ])

    def test_the_absences_a_consumer_would_plan_against_are_reported(self):
        for capability in ("event.clock", "event.period", "event.actions",
                           "event.result", "participant.player_statistics",
                           "event.lineups"):
            with self.subTest(capability=capability):
                self.assertIn(capability, self.capabilities["absent"])

    def test_a_started_event_with_a_scoreline_raises_no_violation(self):
        self.assertEqual(self.capabilities["violations"], [])


class TestCorrectedSectionIsRegistered(unittest.TestCase):
    """A corrected fixture nothing runs is a corrected fixture nobody checks."""

    def setUp(self):
        self.entries = report_module.load_provenance()["corrected"]
        self.entry = next(e for e in self.entries if e["fixture"] == FIXTURE_NAME)

    def test_the_section_holds_this_fixture_beside_the_api_football_one(self):
        """Membership, not the whole list. This test is about the reference
        contract taking its place beside the first corrected output; pinning the
        list would make every later provider fail a test about sports-skills."""
        registered = [e["fixture"] for e in self.entries]
        self.assertIn("corrected-api-football-soccer", registered)
        self.assertIn(FIXTURE_NAME, registered)

    def test_the_graph_is_registered_and_resolvable(self):
        self.assertEqual(self.entry["class"], "corrected-serializer-output")
        self.assertEqual(report_module.resolve(self.entry), GRAPH_PATH)
        self.assertTrue(report_module.resolve(self.entry).is_file())

    def test_the_entry_labels_its_evidence_and_its_limits(self):
        for key in ("source", "transformation", "emitted_by", "limitation",
                    "rights"):
            with self.subTest(key=key):
                self.assertTrue(self.entry.get(key))

    def test_the_entry_names_the_source_fixture_and_the_owning_repository(self):
        self.assertIn(str(SOURCE_PATH.relative_to(REPO_ROOT)), self.entry["source"])
        self.assertIn("sports-skills", self.entry["transformation"])
        self.assertIn("synthetic", self.entry["rights"])

    def test_the_fixture_is_reachable_through_registered_fixtures(self):
        registered = dict(cli_support.registered_fixtures(["corrected"]))
        self.assertEqual(registered[FIXTURE_NAME], GRAPH_PATH)


class TestNoSportsSkillsAdapterLivesHere(unittest.TestCase):
    """The ownership decision, made mechanical.

    The native -> canonical reading for ``sports-skills/espn`` belongs to the
    repository that publishes it. A copy here would be a second source of truth
    for one provider reading: both would look authoritative, and the day one is
    fixed the other silently disagrees. Review cannot hold that line across two
    repositories; a test can hold it in this one.
    """

    ADAPTERS = REPO_ROOT / "tools/iptc/canonical/adapters"

    def test_no_module_here_adapts_sports_skills_or_espn(self):
        offenders = sorted(
            path.name for path in self.ADAPTERS.glob("*.py")
            if "sports_skills" in path.name or "espn" in path.name
        )
        self.assertEqual(offenders, [])

    #: Every provider reading this repository owns. A15 extends it one adapter at
    #: a time, and that is the point: a module appearing here without a line in
    #: this list is a reading nobody decided to own.
    OWNED_ADAPTERS = ("__init__.py", "api_football.py", "sportradar_mlb.py",
                      "sportradar_nfl.py", "sportradar_soccer.py",
                      "sportradar_tennis.py", "stats_perform_opta.py")

    def test_the_adapter_package_holds_only_readings_this_repository_owns(self):
        """An inventory rather than a pin on two files. A15 adds provider
        adapters, so pinning the package contents would fail on planned growth
        while still not saying what the rule is; an explicit owned list fails on
        exactly the thing that matters — a module nobody decided to own."""
        self.assertEqual(sorted(p.name for p in self.ADAPTERS.glob("*.py")),
                         sorted(self.OWNED_ADAPTERS))

    def test_no_owned_adapter_is_a_sports_skills_or_espn_reading(self):
        """The list above cannot be extended into the thing this class forbids."""
        for name in self.OWNED_ADAPTERS:
            with self.subTest(name=name):
                self.assertNotIn("sports_skills", name)
                self.assertNotIn("espn", name)

    def test_no_such_module_is_importable(self):
        for name in ("tools.iptc.canonical.adapters.sports_skills_espn",
                     "tools.iptc.canonical.adapters.sports_skills"):
            with self.subTest(name=name):
                self.assertIsNone(importlib.util.find_spec(name))

    def test_the_contract_names_sports_skills_as_the_adapter_owner(self):
        """The positive half: the checked-in observation cites the module in the
        other repository, so the bytes here are a contract to reproduce rather
        than the output of code that lives here."""
        adapter = observation_document()["observation"]["adapter"]["name"]
        self.assertTrue(adapter.startswith("sports_skills."))
        self.assertNotIn("tools.iptc", adapter)


if __name__ == "__main__":
    unittest.main(verbosity=2)
