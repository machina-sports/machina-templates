"""The generic multi-participant contract fixture (PR 2, task A16d).

Run from the repository root:

    python3 tests/test_iptc_multi_participant_contract.py -v

Run the file directly, for the same reason as the other IPTC suites: ``tests/``
is a namespace directory with no ``__init__.py``, so ``-m unittest
tests.<module>`` can be shadowed by an installed distribution that ships a
top-level regular ``tests`` package.

**The gap this row fills.** Every corrected fixture in the set until now is two
competitors facing each other: six team-versus-team rows and one tennis singles
match. Two is a special case the serializer happens to handle by handling *any*
number, and nothing proved that — a bug that silently kept only the first two
participants, or that read participant order as home-then-away, would pass all
seven existing rows. This row is three individuals in one event, so the
list-shaped path is exercised as a list.

It is also the set's only row with **no home and no away at all**. Six rows carry
``alignment``, the tennis row carries it on individuals where it means very
little, and a reader could reasonably conclude the canonical shape requires it.
It does not: ``alignment`` is mandatory on a ``TeamParticipation`` and meaningless
in a stroke-play field, and inventing one here would be exactly the fiction this
programme refuses. So there is none, and the event view has no ``participants``
block as a result — only ``players``.

**No adapter is created for it, and that is deliberate.** There is no provider
behind this document. It is hand-authored against the canonical contract, which
makes it the honest home for two things the provider rows cannot carry:

- a ``rights.data_class`` of ``mapping-contract-synthetic``, which the A14
  reference contract could **not** use, because that class is stamped by a
  published adapter onto live ESPN reads and would call real matches synthetic.
  Nothing here is ever emitted off a real feed, so the class is true in every
  document that will ever carry it.
- ``resolution_method: "declared"`` on every identity. A16c added the field; here
  it is the whole truth about every identifier in the file, because a hand-
  authored identifier is supplied by its author by definition. ``provider-native``
  would be the strongest possible overstatement: there is no provider.

The sport is golf, ``medtop:20000940``, checked against the pinned mediatopic
scheme. It was chosen because a stroke count is unambiguously a score — three
runners' finishing times would have needed ``sport:score`` to mean something it
does not — and because ``speventoutcome:`` pins ``win``, ``place`` and ``show``,
which is exactly a three-way finishing order expressed in official terms rather
than in a number a consumer has to rank itself.
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

OBSERVATION_PATH = FIXTURES / "observations/mapping-contract-synthetic-observation.json"
GRAPH_PATH = FIXTURES / "corrected/mapping-contract-synthetic-graph.json"
ENVELOPE_PATH = FIXTURES / "corrected/mapping-contract-synthetic-envelope.json"

FIXTURE_NAME = "corrected-mapping-contract-synthetic"

#: Announces itself. Not a provider, and not mistakable for one.
PROVIDER_NAMESPACE = "synthetic/mapping-contract"

#: The evidence class. The only row in the set whose runtime rights class and
#: fixture evidence class are the same string, because no adapter emits it off a
#: real feed — see this module's docstring.
RIGHTS_DATA_CLASS = "mapping-contract-synthetic"

OBSERVED_AT = "2026-03-01T22:05:00+00:00"
START_TIME = "2026-02-28T12:00:00+00:00"

#: Golf. Pinned in the mediatopic scheme, and a stroke count is a score.
SPORT_MEDTOP = "20000940"
SPORT_KEY = "golf"

#: The three competitors, in finishing order: provider id, name, score, outcome.
FIELD = (
    ("9811", "Synthetic Golfer A", "68", "win"),
    ("9812", "Synthetic Golfer B", "70", "place"),
    ("9813", "Synthetic Golfer C", "71", "show"),
)

#: Every identifier this document states. All declared, all synthetic.
PROVIDER_IDS = ("synthetic-tour-1", "synthetic-tour-1-2026",
                "synthetic-course-1", "9801", "9811", "9812", "9813")


def observation_document():
    return json.loads(OBSERVATION_PATH.read_text(encoding="utf-8"))


def envelope():
    return canonical_envelope(observation_document(),
                              id_resolver=surrogate_resolver(PROVIDER_NAMESPACE))


def serialized(document):
    return json.dumps(document, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def run_cli(argv):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        status = validate_graph.main(argv)
    return status, buffer.getvalue()


class TestTheObservationIsObviouslySyntheticAndValid(unittest.TestCase):

    def setUp(self):
        self.document = observation_document()
        self.observation = self.document["observation"]
        self.blob = OBSERVATION_PATH.read_text(encoding="utf-8")

    def test_the_observation_is_valid(self):
        self.assertEqual(validate_observation(self.document), [])

    def test_the_document_claims_the_canonical_observation_contract(self):
        self.assertEqual(self.document["schema_version"], "canonical-observation/1.1")
        self.assertEqual(sorted(self.document), ["observation", "schema_version"])

    def test_every_name_announces_itself_as_synthetic(self):
        self.assertIn("Synthetic", self.blob)
        for token in ("Augusta", "St Andrews", "Masters", "PGA", "Ryder",
                      "http", "://"):
            with self.subTest(token=token):
                self.assertNotIn(token, self.blob)

    def test_the_provider_namespace_cannot_be_mistaken_for_a_provider(self):
        self.assertEqual(self.observation["provider"]["namespace"],
                         PROVIDER_NAMESPACE)
        self.assertIn("synthetic", PROVIDER_NAMESPACE)

    def test_the_file_is_checked_in_as_canonical_bytes(self):
        self.assertEqual(self.blob, serialized(self.document))


class TestThePinnedSportIsDefensible(unittest.TestCase):
    """A sport code nothing can check would fail layer 4 closed, and a sport whose
    scoring model does not fit ``sport:score`` would make the row a bad example
    for the thing it exists to demonstrate."""

    def setUp(self):
        self.observation = observation_document()["observation"]

    def test_the_sport_is_golf_by_medtop_code_and_key(self):
        self.assertEqual(self.observation["sport"],
                         {"medtop": SPORT_MEDTOP, "key": SPORT_KEY})

    def test_the_medtop_code_is_a_concept_in_the_pinned_mediatopic_scheme(self):
        from tools.iptc.reference import load_reference

        scheme = load_reference().schemes[
            "http://cv.iptc.org/newscodes/mediatopic/"]
        self.assertIn(
            "http://cv.iptc.org/newscodes/mediatopic/{0}".format(SPORT_MEDTOP),
            scheme.concepts)

    def test_the_three_finishing_positions_are_pinned_speventoutcome_codes(self):
        for _, _, _, outcome in FIELD:
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, vocab.EVENT_OUTCOME)

    def test_the_competition_type_is_a_pinned_spct_code(self):
        self.assertEqual(self.observation["competition"]["type"], "tournament")
        self.assertIn("tournament", vocab.COMPETITION_TYPE)


class TestThreeIndividualsAndNoTeamFiction(unittest.TestCase):
    """The property this row exists for."""

    def setUp(self):
        self.observation = observation_document()["observation"]
        self.participants = self.observation["participants"]

    def test_there_are_three_participants_and_all_three_are_individuals(self):
        self.assertEqual(len(self.participants), 3)
        self.assertEqual([p["kind"] for p in self.participants],
                         ["individual", "individual", "individual"])

    def test_the_field_is_exactly_the_three_competitors_in_finishing_order(self):
        self.assertEqual(
            [(p["provider_id"], p["name"], p["score"], p["outcome"])
             for p in self.participants],
            [tuple(entry) for entry in FIELD],
        )

    def test_no_participant_carries_an_alignment(self):
        """``alignment`` is mandatory on a ``TeamParticipation`` and meaningless in
        a stroke-play field. Inventing a home side here would be fiction."""
        for participant in self.participants:
            with self.subTest(competitor=participant["provider_id"]):
                self.assertNotIn("alignment", participant)

    def test_no_participant_belongs_to_a_team_and_no_team_is_described(self):
        for participant in self.participants:
            with self.subTest(competitor=participant["provider_id"]):
                self.assertNotIn("team_provider_id", participant)
        self.assertNotIn("memberships", self.observation)

    def test_the_scores_are_strings_and_the_three_differ(self):
        scores = [p["score"] for p in self.participants]
        for score in scores:
            with self.subTest(score=score):
                self.assertIsInstance(score, str)
        self.assertEqual(len(set(scores)), 3)

    def test_no_statistic_no_action_and_no_clock_is_invented(self):
        for key in ("actions",):
            with self.subTest(key=key):
                self.assertNotIn(key, self.observation)
        self.assertNotIn("clock", self.observation["event"])
        for participant in self.participants:
            with self.subTest(competitor=participant["provider_id"]):
                self.assertNotIn("statistics", participant)

    def test_there_is_no_raw_payload_because_there_is_no_provider_payload(self):
        """Every other corrected row carries ``raw``. This one must not: a ``raw``
        block here would be a provider record of an observation no provider made."""
        self.assertNotIn("raw", self.observation)


class TestEveryIdentityIsDeclaredNotProviderNative(unittest.TestCase):
    """A16c's field, used for what it is for. There is no provider, so
    ``provider-native`` would be the strongest possible overstatement."""

    def setUp(self):
        self.observation = observation_document()["observation"]
        self.entries = envelope()["machina_sports_schema"]["provider_ids"]

    def test_every_identity_bearing_section_states_declared(self):
        sections = {
            "competition": self.observation["competition"],
            "season": self.observation["competition"]["season"],
            "site": self.observation["site"],
            "event": self.observation["event"],
        }
        for name, section in sorted(sections.items()):
            with self.subTest(section=name):
                self.assertEqual(section["resolution_method"], "declared")
        for participant in self.observation["participants"]:
            with self.subTest(competitor=participant["provider_id"]):
                self.assertEqual(participant["resolution_method"], "declared")

    def test_no_crosswalk_entry_claims_provider_native_evidence(self):
        for entry in self.entries:
            with self.subTest(entity=entry["entity_type"]):
                self.assertEqual(entry["resolution_method"], "declared")

    def test_the_crosswalk_holds_every_identifier_the_document_states(self):
        self.assertEqual([e["entity_type"] for e in self.entries],
                         ["competition", "season", "site", "event",
                          "athlete", "athlete", "athlete"])
        self.assertEqual(sorted(e["provider_id"] for e in self.entries),
                         sorted(PROVIDER_IDS))

    def test_the_three_competitors_crosswalk_as_athletes_and_never_as_teams(self):
        kinds = {e["entity_type"] for e in self.entries}
        self.assertIn("athlete", kinds)
        self.assertNotIn("team", kinds)

    def test_every_entry_cites_the_observation_field_it_came_from(self):
        by_type = {}
        for entry in self.entries:
            by_type.setdefault(entry["entity_type"], []).append(entry["evidence"])
        self.assertEqual(by_type["event"], ["observation.event.provider_id"])
        self.assertEqual(by_type["athlete"], [
            "observation.participants[0].provider_id",
            "observation.participants[1].provider_id",
            "observation.participants[2].provider_id",
        ])


class TestTheGraphIsNonVacuousAndInstantiatesTheRightClasses(unittest.TestCase):

    def setUp(self):
        self.graph = envelope()["machina_sports_schema"]["sport_schema_graph"]
        self.nodes = self.graph["@graph"]

    def test_the_document_is_one_inline_context_and_one_flat_graph(self):
        self.assertEqual(sorted(self.graph), ["@context", "@graph"])
        self.assertTrue(all("@context" not in node for node in self.nodes))

    def test_three_distinct_athletes_and_three_distinct_participations(self):
        """The claim in one assertion: three of each, with three different
        identifiers, so nothing collapsed a list into its first element."""
        types = [node["@type"] for node in self.nodes]
        self.assertEqual(types.count("sport:Athlete"), 3)
        self.assertEqual(types.count("sport:IndividualParticipation"), 3)
        for wanted in ("sport:Athlete", "sport:IndividualParticipation"):
            identifiers = {n["@id"] for n in self.nodes if n["@type"] == wanted}
            with self.subTest(resource=wanted):
                self.assertEqual(len(identifiers), 3)

    def test_no_team_and_no_team_participation_is_emitted(self):
        types = [node["@type"] for node in self.nodes]
        for forbidden in ("sport:Team", "sport:TeamParticipation"):
            with self.subTest(resource=forbidden):
                self.assertNotIn(forbidden, types)

    def test_the_event_references_all_three_participations(self):
        event = next(n for n in self.nodes if n["@type"] == "sport:Event")
        references = {r["@id"] for r in event["sport:participation"]}
        participations = {n["@id"] for n in self.nodes
                          if n["@type"] == "sport:IndividualParticipation"}
        self.assertEqual(references, participations)
        self.assertEqual(len(references), 3)

    def test_each_participation_names_its_own_athlete_score_and_outcome(self):
        by_label = {n["rdfs:label"]: n for n in self.nodes
                    if n["@type"] == "sport:IndividualParticipation"}
        athletes = {n["rdfs:label"]: n["@id"] for n in self.nodes
                    if n["@type"] == "sport:Athlete"}
        for _, name, score, outcome in FIELD:
            node = next(n for label, n in by_label.items() if label.startswith(name))
            with self.subTest(competitor=name):
                self.assertEqual(node["sport:participationBy"],
                                 {"@id": athletes[name]})
                self.assertEqual(node["sport:score"], score)
                self.assertEqual(node["sport:eventOutcome"],
                                 {"@id": "speventoutcome:{0}".format(outcome)})
                self.assertNotIn("sport:alignment", node)
                self.assertNotIn("sport:teamParticipation", node)

    def test_no_participation_carries_a_position_or_a_player_status(self):
        """``spsocposition:`` is a soccer scheme and this is a golf event. The
        serializer only emits what the observation states, and it states neither."""
        for node in self.nodes:
            if node["@type"] != "sport:IndividualParticipation":
                continue
            with self.subTest(node=node["@id"]):
                self.assertNotIn("sport:positionEvent", node)
                self.assertNotIn("sport:playerStatus", node)

    def test_the_official_classes_the_document_supports_are_all_instantiated(self):
        types = [node["@type"] for node in self.nodes]
        for expected in ("sport:Competition", "sport:Site", "sport:Athlete",
                         "sport:Event", "sport:IndividualParticipation",
                         "machina:ProviderIdentifier",
                         "machina:ObservationProvenance"):
            with self.subTest(expected=expected):
                self.assertIn(expected, types)
        self.assertEqual(types.count("sport:Competition"), 2)

    def test_no_stub_resource_is_emitted(self):
        for node in self.nodes:
            with self.subTest(node=node["@id"]):
                self.assertGreater(len(node), 2)

    def test_no_official_resource_carries_a_machina_property(self):
        for node in self.nodes:
            if str(node["@type"]).startswith("sport:"):
                with self.subTest(resource=node["@type"]):
                    self.assertEqual([k for k in node if k.startswith("machina:")], [])

    def test_every_resource_id_is_a_marked_machina_surrogate(self):
        for node in self.nodes:
            with self.subTest(node=node["@type"]):
                self.assertRegex(node["@id"],
                                 r"^urn:machina:sports:[a-z-]+:x[0-9a-f]{32}$")

    def test_no_stated_identifier_is_used_as_a_resource_id(self):
        identifiers = [node["@id"] for node in self.nodes]
        for provider_id in PROVIDER_IDS:
            with self.subTest(provider_id=provider_id):
                for node_id in identifiers:
                    self.assertNotIn(provider_id, node_id)

    def test_no_provider_namespace_token_survives_in_a_resource_id(self):
        for node in self.nodes:
            with self.subTest(node=node["@id"]):
                self.assertIsNone(
                    profile_module.provider_namespace_in_id(node["@id"]))

    def test_every_newscode_is_a_node_reference_in_a_pinned_scheme(self):
        pinned = set(vocab.SCHEME_PATH) | {"medtop"}
        codes = []
        for node in self.nodes:
            for value in node.values():
                if isinstance(value, dict) and set(value) == {"@id"} \
                        and ":" in value["@id"] and not value["@id"].startswith("urn:"):
                    codes.append(value["@id"])
        self.assertTrue(codes)
        for code in codes:
            with self.subTest(code=code):
                self.assertIn(code.split(":", 1)[0], pinned)

    def test_nothing_fabricated_reaches_the_graph(self):
        blob = json.dumps(self.graph)
        self.assertNotIn("null", blob)
        self.assertNotIn('""', blob)
        for value in sorted(profile_module.PLACEHOLDER_VALUES):
            if value:
                with self.subTest(placeholder=value):
                    self.assertNotIn('"{0}"'.format(value), blob)


class TestTheEventViewHasPlayersAndNoParticipantsBlock(unittest.TestCase):
    """``role`` means alignment for a team, so a field with no alignment has no
    ``participants`` block at all rather than one full of empty roles."""

    def setUp(self):
        self.view = envelope()["machina_sports_schema"]["event_view"]

    def test_there_is_no_participants_block(self):
        self.assertNotIn("participants", self.view)

    def test_all_three_competitors_are_in_players_with_no_team_id(self):
        self.assertEqual([p["name"] for p in self.view["players"]],
                         [name for _, name, _, _ in FIELD])
        for player in self.view["players"]:
            with self.subTest(player=player["name"]):
                self.assertNotIn("team_id", player)

    def test_the_site_city_and_country_travel_in_the_view(self):
        """``SiteShape`` is ``sh:closed`` with no property shapes, so these are
        facts the graph has nowhere to put."""
        self.assertEqual(self.view["site"]["city"], "Synthetic City")
        self.assertEqual(self.view["site"]["country"], "Syntheticland")

    def test_there_is_no_provider_raw_block(self):
        self.assertNotIn("raw", self.view.get("provider", {}))

    def test_nothing_fabricated_reaches_the_view(self):
        blob = json.dumps(self.view)
        self.assertNotIn("null", blob)
        self.assertNotIn('""', blob)


class TestCheckedInOutputsAreReproducible(unittest.TestCase):
    """A checked-in fixture that cannot be regenerated is a screenshot."""

    def test_the_envelope_fixture_is_reproducible_byte_for_byte(self):
        self.assertEqual(ENVELOPE_PATH.read_text(encoding="utf-8"),
                         serialized(envelope()))

    def test_the_graph_fixture_is_exactly_the_envelope_graph(self):
        self.assertEqual(
            json.loads(GRAPH_PATH.read_text(encoding="utf-8")),
            envelope()["machina_sports_schema"]["sport_schema_graph"])

    def test_two_runs_agree(self):
        self.assertEqual(serialized(envelope()), serialized(envelope()))

    def test_the_envelope_carries_every_rfc_002_part(self):
        block = envelope()["machina_sports_schema"]
        self.assertEqual(sorted(block), [
            "capabilities", "event_view", "profile", "provenance", "provider_ids",
            "rights", "schema_version", "sport_schema_graph",
        ])


class TestCorrectedGraphConformance(unittest.TestCase):
    """Four layers, non-vacuous layer 2, four gates at zero, no unverifiable
    NewsCode. Run against the **checked-in** file, because that file is a
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


class TestCapabilityReportCarriesOnlyWhatTheDocumentStates(unittest.TestCase):

    def setUp(self):
        self.capabilities = envelope()["machina_sports_schema"]["capabilities"]

    def test_the_tier_is_core_and_no_higher_tier_is_claimed(self):
        self.assertEqual(self.capabilities["tier"], "core")
        self.assertEqual(self.capabilities["tiers_satisfied"], ["core"])

    def test_present_is_exactly_what_the_document_supports(self):
        self.assertEqual(self.capabilities["present"], [
            "event.competition", "event.identity", "event.lineups",
            "event.participants", "event.result", "event.score",
            "event.start_time", "event.status", "provenance",
        ])

    def test_lineups_is_present_because_the_participants_are_people(self):
        self.assertIn("event.lineups", self.capabilities["present"])

    def test_no_player_statistic_is_claimed(self):
        self.assertIn("participant.player_statistics", self.capabilities["absent"])

    def test_a_closed_event_with_a_scoreline_raises_no_violation(self):
        self.assertEqual(self.capabilities["violations"], [])


class TestRightsAreStatedAndTheGateRefusesProduction(unittest.TestCase):
    """The one row whose runtime class and fixture evidence class are the same
    string, and the reason that is honest here and was not in A14."""

    def setUp(self):
        self.checked_in = json.loads(ENVELOPE_PATH.read_text(encoding="utf-8"))
        self.observation = observation_document()["observation"]

    def test_the_data_class_names_the_evidence_and_claims_no_entitlement(self):
        rights = self.observation["rights"]
        self.assertEqual(rights["data_class"], RIGHTS_DATA_CLASS)
        self.assertIs(rights["prototype_only"], True)
        self.assertIs(rights["commercial_use"], False)
        for word in ("licensed", "redistributable", "entitlement", "production"):
            with self.subTest(word=word):
                self.assertNotIn(word, rights["data_class"])

    def test_calling_this_document_synthetic_is_true_of_every_copy_of_it(self):
        """The A14 lesson, applied in the direction it actually points. That
        contract could not use this class because a published adapter stamps it
        onto live reads. No adapter emits this one, so the word is safe."""
        self.assertIn("synthetic", RIGHTS_DATA_CLASS)
        self.assertFalse(
            (REPO_ROOT / "tools/iptc/canonical/adapters"
             / "mapping_contract_synthetic.py").exists())

    def test_the_library_gate_refuses_production_with_exactly_one_finding(self):
        findings = validate_graph.rights_findings(self.checked_in,
                                                  consumer_tier="production")
        self.assertEqual([f["code"] for f in findings], ["rights-prototype-only"])
        self.assertEqual(findings[0]["data_class"], RIGHTS_DATA_CLASS)

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


class TestTheRowIsRegisteredWithItsLimitations(unittest.TestCase):
    """A corrected fixture nothing runs is a corrected fixture nobody checks."""

    def setUp(self):
        self.entries = report_module.load_provenance()["corrected"]
        self.entry = next(e for e in self.entries if e["fixture"] == FIXTURE_NAME)

    def test_the_corrected_section_now_holds_eight_rows(self):
        self.assertEqual(len(self.entries), 8)

    def test_the_graph_is_registered_and_resolvable(self):
        self.assertEqual(self.entry["class"], "corrected-serializer-output")
        self.assertEqual(report_module.resolve(self.entry), GRAPH_PATH)
        self.assertTrue(report_module.resolve(self.entry).is_file())

    def test_the_entry_labels_its_evidence_and_its_limits(self):
        for key in ("source", "transformation", "emitted_by", "limitation",
                    "rights", "provenance", "coverage", "role"):
            with self.subTest(key=key):
                self.assertTrue(self.entry.get(key))

    def test_the_limitation_states_that_no_provider_and_no_adapter_exists(self):
        limitation = self.entry["limitation"]
        self.assertIn("no provider", limitation.lower())
        self.assertIn("adapter", limitation.lower())

    def test_the_rights_line_states_the_class_and_refuses_an_entitlement_reading(self):
        self.assertIn(RIGHTS_DATA_CLASS, self.entry["rights"])
        self.assertIn("prototype_only", self.entry["rights"])

    def test_the_provenance_line_says_the_document_is_hand_authored(self):
        self.assertIn("SYNTHETIC", self.entry["provenance"])
        self.assertIn("hand-authored", self.entry["provenance"])

    def test_the_fixture_is_reachable_through_registered_fixtures(self):
        registered = dict(cli_support.registered_fixtures(["corrected"]))
        self.assertEqual(registered[FIXTURE_NAME], GRAPH_PATH)


class TestNoAdapterIsCreatedForThisRow(unittest.TestCase):
    """The ownership decision, made mechanical: this row is a hand-authored
    contract document, and an adapter for it would invent a provider."""

    ADAPTERS = REPO_ROOT / "tools/iptc/canonical/adapters"

    def test_no_module_here_adapts_a_mapping_contract_or_a_synthetic_provider(self):
        offenders = sorted(
            path.name for path in self.ADAPTERS.glob("*.py")
            if "mapping_contract" in path.name or "synthetic" in path.name
            or "golf" in path.name
        )
        self.assertEqual(offenders, [])

    def test_no_such_module_is_importable(self):
        for name in ("tools.iptc.canonical.adapters.mapping_contract_synthetic",
                     "tools.iptc.canonical.adapters.golf"):
            with self.subTest(name=name):
                self.assertIsNone(importlib.util.find_spec(name))

    def test_the_adapter_block_names_no_module_because_none_produced_it(self):
        adapter = observation_document()["observation"]["adapter"]
        self.assertNotIn("tools.iptc.canonical.adapters", adapter["name"])
        self.assertIn("hand-authored", adapter["name"])
        self.assertTrue(adapter["version"])

    def test_no_source_ref_is_request_shaped(self):
        refs = observation_document()["observation"]["adapter"]["source_refs"]
        self.assertTrue(refs)
        for ref in refs:
            for marker in ("://", "?", "&", "key=", "token=", "secret",
                           "Authorization"):
                with self.subTest(marker=marker):
                    self.assertNotIn(marker, ref["value"])


class TestTheContractFailsClosed(unittest.TestCase):
    """The validator is load-bearing on this document rather than merely tolerant
    of it. Every mutation is applied to a copy."""

    def mutated(self, mutate):
        document = observation_document()
        mutate(document["observation"])
        return validate_observation(document)

    def test_dropping_a_competitor_to_one_is_refused(self):
        errors = self.mutated(lambda o: o["participants"].pop())
        self.assertEqual(validate_observation(observation_document()), [])
        self.assertEqual(errors, [])  # two is still a valid field size
        errors = self.mutated(
            lambda o: o.__setitem__("participants", o["participants"][:1]))
        self.assertEqual(errors, ["observation.participants: need at least 2"])

    def test_a_fourth_resolution_method_is_refused(self):
        errors = self.mutated(
            lambda o: o["event"].__setitem__("resolution_method", "assumed"))
        self.assertEqual(len(errors), 1)
        self.assertIn("resolution_method", errors[0])

    def test_giving_a_competitor_a_team_alignment_without_a_kind_change_is_ignored(self):
        """Stated so the absence of ``alignment`` is understood as a modelling
        decision rather than as something the validator would have caught. An
        ``individual`` with an alignment still validates — the serializer simply
        has nowhere to put it, which is why it is absent from the fixture."""
        errors = self.mutated(
            lambda o: o["participants"][0].__setitem__("alignment", "home"))
        self.assertEqual(errors, [])
        document = observation_document()
        document["observation"]["participants"][0]["alignment"] = "home"
        graph = canonical_envelope(
            document, id_resolver=surrogate_resolver(PROVIDER_NAMESPACE)
        )["machina_sports_schema"]["sport_schema_graph"]
        for node in graph["@graph"]:
            with self.subTest(node=node["@id"]):
                self.assertNotIn("sport:alignment", node)

    def test_a_naive_start_time_is_refused(self):
        errors = self.mutated(
            lambda o: o["event"].__setitem__("start_time", "2026-02-28T12:00:00"))
        self.assertTrue(errors)
        self.assertIn("explicit offset", " ".join(errors))

    def test_the_serializer_refuses_an_invalid_observation_outright(self):
        document = observation_document()
        document["observation"].pop("rights")
        with self.assertRaises(ValueError):
            canonical_envelope(document,
                               id_resolver=surrogate_resolver(PROVIDER_NAMESPACE))

    def test_the_checked_in_document_is_untouched_by_every_mutation_above(self):
        self.assertEqual(validate_observation(observation_document()), [])
        self.assertEqual(len(observation_document()["observation"]["participants"]),
                         3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
