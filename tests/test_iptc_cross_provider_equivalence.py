"""Cross-provider semantic equivalence for one match (PR 2, task A16a).

Run from the repository root:

    python3 tests/test_iptc_cross_provider_equivalence.py -v

Run the file directly, for the same reason as the other IPTC suites: ``tests/``
is a namespace directory with no ``__init__.py``, so ``-m unittest
tests.<module>`` can be shadowed by an installed distribution that ships a
top-level regular ``tests`` package.

**The question this file answers.** Every other suite in this programme checks
one provider against itself: the adapter reads a payload, the serializer emits a
document, the harness says it conforms. None of them can tell whether two
providers observing *the same match* land on the same canonical facts, and that
is the property a consumer actually depends on — the whole point of a canonical
observation is that a downstream reader does not have to know which provider it
came from.

So this file takes one synthetic 2-1 closed soccer match and expresses it twice:

- ``tools/iptc/fixtures/source/sports-skills-espn-soccer-native.json``, already
  checked in as the sports-skills reference contract's input, **read by reference
  and not copied**. A second copy of a payload published in two repositories is
  the drift this programme refuses everywhere else, and copying it here would
  also quietly make the comparison self-referential.
- ``tools/iptc/fixtures/cross-provider/synthetic-match-01/api-football.json``, a
  new payload in API-Football's ``/fixtures`` element shape describing the same
  match with **deliberately different provider identifiers**.

Three groups of assertions, and the split between them is the finding:

1. **What must agree** — sport, competition, season, status, start time, the
   home/away alignment *and its order*, and the score strings. These are the
   match, and if two providers disagree about them the canonical contract has
   failed at its job.
2. **What must differ** — the provider namespace, every provider identifier,
   every minted surrogate, the adapter block, the rights class and ``raw``.
   Identity here is provider-scoped by construction (``ids.surrogate_resolver``),
   and this file is where that stops being a docstring claim.
3. **What one provider states and the other does not** — API-Football states a
   winner and a minutes-elapsed reading; the sports-skills native shape states a
   venue country. None of the three is a disagreement about the match, and
   smoothing them over would be the fabrication the profile exists to prevent.

**What this file does NOT claim.** It does not claim the two observations
describe the same entity *in the model*. No ``sameAs`` is emitted, no crosswalk
entry references the other provider's identity, and the two graphs share zero
identifiers. A crosswalk records where a string came from; asserting that two
providers' strings denote one thing needs an identity service, which RFC 002 §5
says does not exist in this phase. That negative is asserted below rather than
left to the reader.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.iptc import profile as profile_module  # noqa: E402
from tools.iptc.canonical.adapters import api_football  # noqa: E402
from tools.iptc.canonical.ids import surrogate_resolver  # noqa: E402
from tools.iptc.canonical.observation import validate_observation  # noqa: E402
from tools.iptc.canonical.serialize import canonical_envelope  # noqa: E402

FIXTURES = REPO_ROOT / "tools/iptc/fixtures"

#: The API-Football expression of the match. New in A16.
API_FOOTBALL_PAYLOAD_PATH = (
    FIXTURES / "cross-provider/synthetic-match-01/api-football.json")

#: The sports-skills expression of the same match, BY REFERENCE. Both of these
#: belong to the A14 reference contract and neither is copied into the
#: cross-provider directory.
SPORTS_SKILLS_NATIVE_PATH = (
    FIXTURES / "source/sports-skills-espn-soccer-native.json")
SPORTS_SKILLS_OBSERVATION_PATH = (
    FIXTURES / "observations/sports-skills-espn-soccer-observation.json")

SPORTS_SKILLS_NAMESPACE = "sports-skills/espn"
API_FOOTBALL_NAMESPACE = "api-football"

#: Fixed, so nothing here reads a clock. The same value the A14 contract pins,
#: which is what lets the two observations be compared field by field at all.
OBSERVED_AT = "2026-03-01T22:05:00+00:00"

#: Every provider identifier the API-Football payload states, and the one that is
#: deliberately not a ``9xxx`` token: API-Football has no standalone season
#: identifier, so a season *is* its year and ``2026`` is what the provider
#: actually says. Inventing ``9602`` there would have made the fixture tidier and
#: the crosswalk a lie.
API_FOOTBALL_IDS = ("9501", "9601", "9701", "9511", "9512")
API_FOOTBALL_SEASON_ID = "2026"

SPORTS_SKILLS_IDS = ("9001", "9011", "9012", "9101",
                     "synthetic-league-1", "synthetic-league-1-2026")


def api_football_payload():
    return json.loads(API_FOOTBALL_PAYLOAD_PATH.read_text(encoding="utf-8"))


def api_football_observation():
    return api_football.to_observation(api_football_payload(),
                                       observed_at=OBSERVED_AT)


def sports_skills_observation():
    return json.loads(SPORTS_SKILLS_OBSERVATION_PATH.read_text(encoding="utf-8"))


def envelope(document, namespace):
    return canonical_envelope(document, id_resolver=surrogate_resolver(namespace))


def both():
    """``(api_football, sports_skills)`` observation bodies, in that order."""
    return (api_football_observation()["observation"],
            sports_skills_observation()["observation"])


def serialized(document):
    return json.dumps(document, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


class TestTheCrossProviderPayloadIsObviouslySynthetic(unittest.TestCase):
    """This file is published. If a reader has to check whether a name is a real
    club, the fixture has already failed at its job."""

    def setUp(self):
        self.payload = api_football_payload()
        self.blob = API_FOOTBALL_PAYLOAD_PATH.read_text(encoding="utf-8")

    def test_every_name_announces_itself_as_synthetic(self):
        self.assertIn("Synthetic", self.blob)
        for token in ("Arsenal", "Real Madrid", "Barcelona", "La Liga",
                      "Premier League", "apifootball", "rapidapi", "http"):
            with self.subTest(token=token):
                self.assertNotIn(token, self.blob)

    def test_every_stated_identifier_is_a_9xxx_token(self):
        stated = [self.payload["fixture"]["id"],
                  self.payload["league"]["id"],
                  self.payload["fixture"]["venue"]["id"],
                  self.payload["teams"]["home"]["id"],
                  self.payload["teams"]["away"]["id"]]
        for identifier in stated:
            with self.subTest(identifier=identifier):
                self.assertTrue(str(identifier).startswith("9"))
        self.assertEqual(sorted(str(i) for i in stated),
                         sorted(API_FOOTBALL_IDS))

    def test_the_season_is_the_year_the_provider_states_and_not_a_9xxx_token(self):
        """API-Football has no standalone season identifier. Making this one look
        like the others would have been tidier and would have put a string the
        provider never uses into the crosswalk."""
        self.assertEqual(str(self.payload["league"]["season"]),
                         API_FOOTBALL_SEASON_ID)
        self.assertFalse(API_FOOTBALL_SEASON_ID.startswith("9"))

    def test_the_shape_is_the_one_the_adapter_actually_receives(self):
        """A payload in a shape ``/fixtures`` never returns would prove nothing
        about the adapter that reads it."""
        self.assertEqual(sorted(self.payload),
                         ["fixture", "goals", "league", "score", "teams"])
        self.assertEqual(sorted(self.payload["teams"]), ["away", "home"])
        self.assertEqual(sorted(self.payload["score"]),
                         ["extratime", "fulltime", "halftime", "penalty"])
        self.assertEqual(sorted(self.payload["fixture"]["status"]),
                         ["elapsed", "long", "short"])

    def test_no_identifier_collides_with_the_sports_skills_expression(self):
        """The comparison is only meaningful if the two providers really do
        address the match differently."""
        overlap = set(API_FOOTBALL_IDS) & set(SPORTS_SKILLS_IDS)
        self.assertEqual(overlap, set())

    def test_the_sports_skills_side_is_referenced_and_not_copied(self):
        """Two copies of one payload is the drift this programme refuses
        everywhere else, and it would also make the comparison self-referential."""
        copies = sorted(p.name for p in API_FOOTBALL_PAYLOAD_PATH.parent.iterdir()
                        if p.suffix == ".json")
        self.assertEqual(copies, ["api-football.json"])
        self.assertTrue(SPORTS_SKILLS_NATIVE_PATH.is_file())
        self.assertNotIn("competitors", self.blob,
                         "'competitors' is the sports-skills native key set")

    def test_the_file_is_checked_in_as_canonical_bytes(self):
        self.assertEqual(self.blob, serialized(self.payload))


class TestBothObservationsAreValid(unittest.TestCase):
    """Neither side of a comparison is worth anything if it does not validate."""

    def test_the_api_football_observation_is_valid(self):
        self.assertEqual(validate_observation(api_football_observation()), [])

    def test_the_sports_skills_observation_is_valid(self):
        self.assertEqual(validate_observation(sports_skills_observation()), [])

    def test_both_claim_the_same_input_contract(self):
        self.assertEqual(api_football_observation()["schema_version"],
                         sports_skills_observation()["schema_version"])


class TestTheMatchIsTheSameMatch(unittest.TestCase):
    """Group 1: what two providers observing one fixture must agree about."""

    def setUp(self):
        self.api, self.skills = both()

    def test_the_sport_is_the_same_medtop_code_and_the_same_key(self):
        self.assertEqual(self.api["sport"], self.skills["sport"])
        self.assertEqual(self.api["sport"], {"medtop": "20001065", "key": "soccer"})

    def test_the_competition_is_the_same_competition_by_name(self):
        """By name, because the identifiers are deliberately different — which is
        exactly why a name is the only cross-provider handle this phase has, and
        exactly why it is evidence rather than identity."""
        self.assertEqual(self.api["competition"]["name"],
                         self.skills["competition"]["name"])

    def test_the_season_is_the_same_season_by_name(self):
        self.assertEqual(self.api["competition"]["season"]["name"],
                         self.skills["competition"]["season"]["name"])

    def test_the_status_is_the_same_canonical_key(self):
        """Two different provider vocabularies — ``FT`` and ``closed`` — read into
        one canonical key. That normalisation is the contract's whole job."""
        self.assertEqual(self.api["event"]["status"],
                         self.skills["event"]["status"])
        self.assertEqual(self.api["event"]["status"], "closed")

    def test_the_start_time_is_the_same_instant_with_an_explicit_offset(self):
        self.assertEqual(self.api["event"]["start_time"],
                         self.skills["event"]["start_time"])
        self.assertEqual(self.api["event"]["start_time"],
                         "2026-03-01T20:00:00+00:00")

    def test_the_event_label_is_the_same_rendering_of_the_same_two_teams(self):
        self.assertEqual(self.api["event"]["label"],
                         self.skills["event"]["label"])

    def test_home_and_away_are_aligned_the_same_way_in_the_same_order(self):
        """Order is load-bearing. A consumer that reads ``participants[0]`` as the
        home side must get the home side from either provider."""
        alignment = lambda o: [(p["kind"], p["alignment"])  # noqa: E731
                               for p in o["participants"]]
        self.assertEqual(alignment(self.api), alignment(self.skills))
        self.assertEqual(alignment(self.api), [("team", "home"), ("team", "away")])

    def test_the_two_teams_are_the_same_teams_by_name_in_the_same_order(self):
        names = lambda o: [p["name"] for p in o["participants"]]  # noqa: E731
        self.assertEqual(names(self.api), names(self.skills))

    def test_the_score_strings_are_identical_and_positionally_aligned(self):
        """Strings, not numbers: the pinned shapes declare ``sh:datatype
        xsd:string``, and the native payloads state ``2``/``1`` as integers on
        both sides."""
        scores = lambda o: [p["score"] for p in o["participants"]]  # noqa: E731
        self.assertEqual(scores(self.api), scores(self.skills))
        self.assertEqual(scores(self.api), ["2", "1"])
        for score in scores(self.api) + scores(self.skills):
            with self.subTest(score=score):
                self.assertIsInstance(score, str)

    def test_the_venue_is_the_same_venue_by_name_and_city(self):
        self.assertEqual(self.api["site"]["name"], self.skills["site"]["name"])
        self.assertEqual(self.api["site"]["city"], self.skills["site"]["city"])

    def test_neither_side_invents_a_competition_phase(self):
        """API-Football states an empty round and the native shape states an empty
        one too. Two providers agreeing to say nothing is still agreement."""
        for label, observation in (("api-football", self.api),
                                   ("sports-skills", self.skills)):
            with self.subTest(provider=label):
                self.assertNotIn("phase", observation)


class TestWhatDiffersIsProviderIdentityNotTheMatch(unittest.TestCase):
    """Group 2: everything that must NOT be shared."""

    def setUp(self):
        self.api, self.skills = both()

    def test_the_provider_namespace_and_family_differ(self):
        self.assertEqual(self.api["provider"]["namespace"], API_FOOTBALL_NAMESPACE)
        self.assertEqual(self.skills["provider"]["namespace"],
                         SPORTS_SKILLS_NAMESPACE)
        self.assertNotEqual(self.api["provider"], self.skills["provider"])

    def test_no_provider_identifier_is_shared_by_the_two_observations(self):
        identifiers = lambda o: {  # noqa: E731
            o["competition"]["provider_id"],
            o["competition"]["season"]["provider_id"],
            o["site"]["provider_id"],
            o["event"]["provider_id"],
        } | {p["provider_id"] for p in o["participants"]}
        self.assertEqual(identifiers(self.api) & identifiers(self.skills), set())

    def test_the_adapter_block_names_a_different_owner_on_each_side(self):
        """One reading is owned here, the other by the repository that publishes
        it. A crosswalk that could not say which code made a claim is anonymous."""
        self.assertTrue(self.api["adapter"]["name"].startswith("tools.iptc."))
        self.assertTrue(self.skills["adapter"]["name"].startswith("sports_skills."))

    def test_the_rights_class_differs_because_the_evidence_differs(self):
        """A sanitized licensed-provider example and a public-endpoint reading are
        two different entitlements, and one canonical shape must not blur them."""
        self.assertEqual(self.api["rights"]["data_class"],
                         "licensed-provider-example-fixture")
        self.assertEqual(self.skills["rights"]["data_class"], "open-public")
        for observation in (self.api, self.skills):
            with self.subTest(provider=observation["provider"]["namespace"]):
                self.assertIs(observation["rights"]["prototype_only"], True)
                self.assertIs(observation["rights"]["commercial_use"], False)

    def test_the_raw_payloads_are_each_providers_own_bytes(self):
        self.assertEqual(self.api["raw"], api_football_payload())
        self.assertEqual(
            self.skills["raw"],
            json.loads(SPORTS_SKILLS_NATIVE_PATH.read_text(encoding="utf-8")))
        self.assertNotEqual(self.api["raw"], self.skills["raw"])

    def test_the_source_refs_name_different_endpoint_classes(self):
        refs = lambda o: [r["value"] for r in o["adapter"]["source_refs"]]  # noqa: E731
        self.assertEqual(refs(self.api), ["api-football/fixtures"])
        self.assertEqual(refs(self.skills), ["espn/summary"])


class TestSurrogateIdentityIsDeliberatelyProviderScoped(unittest.TestCase):
    """The identifiers are different on purpose, and that is a property of the
    resolver rather than an accident of the fixtures."""

    def setUp(self):
        self.api = envelope(api_football_observation(),
                            API_FOOTBALL_NAMESPACE)["machina_sports_schema"]
        self.skills = envelope(sports_skills_observation(),
                               SPORTS_SKILLS_NAMESPACE)["machina_sports_schema"]

    def graph_ids(self, block):
        return {node["@id"] for node in block["sport_schema_graph"]["@graph"]}

    def test_the_two_graphs_share_no_resource_identifier_at_all(self):
        self.assertEqual(self.graph_ids(self.api) & self.graph_ids(self.skills),
                         set())

    def test_both_graphs_mint_the_same_kinds_of_resource(self):
        """Different identifiers, same classes: the difference is identity, not
        modelling."""
        types = lambda b: sorted(  # noqa: E731
            {n["@type"] for n in b["sport_schema_graph"]["@graph"]})
        self.assertEqual(types(self.api), types(self.skills))

    def test_the_same_event_mints_two_identifiers_because_scoping_is_by_provider(self):
        """Stated as a property of the resolver: even given the *same* provider
        identifier, two namespaces mint two surrogates. Nothing here can link
        them, and nothing here tries."""
        shared = "9001"
        self.assertNotEqual(
            surrogate_resolver(API_FOOTBALL_NAMESPACE)("event", shared),
            surrogate_resolver(SPORTS_SKILLS_NAMESPACE)("event", shared))

    def test_every_identifier_on_both_sides_is_a_marked_machina_surrogate(self):
        for label, block in (("api-football", self.api),
                             ("sports-skills", self.skills)):
            for node_id in sorted(self.graph_ids(block)):
                with self.subTest(provider=label, node=node_id):
                    self.assertRegex(
                        node_id, r"^urn:machina:sports:[a-z-]+:x[0-9a-f]{32}$")

    def test_no_provider_namespace_token_survives_in_any_identifier(self):
        for label, block in (("api-football", self.api),
                             ("sports-skills", self.skills)):
            for node_id in sorted(self.graph_ids(block)):
                with self.subTest(provider=label, node=node_id):
                    self.assertIsNone(
                        profile_module.provider_namespace_in_id(node_id))

    def test_neither_graph_carries_the_other_providers_identifier(self):
        api_blob = json.dumps(self.api["sport_schema_graph"])
        skills_blob = json.dumps(self.skills["sport_schema_graph"])
        for provider_id in SPORTS_SKILLS_IDS:
            with self.subTest(provider_id=provider_id):
                self.assertNotIn('"{0}"'.format(provider_id), api_blob)
        for provider_id in API_FOOTBALL_IDS:
            with self.subTest(provider_id=provider_id):
                self.assertNotIn('"{0}"'.format(provider_id), skills_blob)


class TestTheCrosswalkIsEvidenceAndNotASameAsClaim(unittest.TestCase):
    """The negative this whole file exists to keep honest.

    Two documents describing one match, side by side, is exactly the setting in
    which someone reaches for ``owl:sameAs``. RFC 002 §5 says there is no identity
    resolution in this phase, so the crosswalk records where a string came from
    and stops there.
    """

    def setUp(self):
        self.api = envelope(api_football_observation(),
                            API_FOOTBALL_NAMESPACE)["machina_sports_schema"]
        self.skills = envelope(sports_skills_observation(),
                               SPORTS_SKILLS_NAMESPACE)["machina_sports_schema"]

    def test_neither_envelope_mentions_a_sameness_predicate(self):
        for label, block in (("api-football", self.api),
                             ("sports-skills", self.skills)):
            blob = json.dumps(block)
            for token in ("sameAs", "owl:sameAs", "exactMatch", "same_as"):
                with self.subTest(provider=label, token=token):
                    self.assertNotIn(token, blob)

    def test_each_crosswalk_names_only_its_own_provider_namespace(self):
        for label, block, namespace in (
            ("api-football", self.api, API_FOOTBALL_NAMESPACE),
            ("sports-skills", self.skills, SPORTS_SKILLS_NAMESPACE),
        ):
            for entry in block["provider_ids"]:
                with self.subTest(provider=label, entity=entry["entity_type"]):
                    self.assertEqual(entry["provider_namespace"], namespace)

    def test_no_crosswalk_entry_points_at_the_other_providers_identity(self):
        api_ids = {e["machina_id"] for e in self.api["provider_ids"]}
        skills_ids = {e["machina_id"] for e in self.skills["provider_ids"]}
        self.assertEqual(api_ids & skills_ids, set())

    def test_every_entry_cites_the_observation_field_it_was_read_from(self):
        """Evidence means a pointer back to the fact, on both sides."""
        for label, block in (("api-football", self.api),
                             ("sports-skills", self.skills)):
            for entry in block["provider_ids"]:
                with self.subTest(provider=label, entity=entry["entity_type"]):
                    self.assertTrue(entry["evidence"].startswith("observation."))

    def test_both_sides_crosswalk_the_same_entity_kinds(self):
        """The shapes agree even though nothing links the contents. That is what
        makes a future identity service possible without making one exist now."""
        kinds = lambda b: [e["entity_type"] for e in b["provider_ids"]]  # noqa: E731
        self.assertEqual(kinds(self.api), kinds(self.skills))
        self.assertEqual(kinds(self.api),
                         ["competition", "season", "site", "event", "team", "team"])

    def test_every_entry_on_both_sides_is_provider_native(self):
        """Neither adapter injects a constant for this match, so A16c's resolution
        method is ``provider-native`` throughout — stated, not assumed."""
        for label, block in (("api-football", self.api),
                             ("sports-skills", self.skills)):
            for entry in block["provider_ids"]:
                with self.subTest(provider=label, entity=entry["entity_type"]):
                    self.assertEqual(entry["resolution_method"], "provider-native")


class TestFactsOneProviderStatesAndTheOtherDoesNot(unittest.TestCase):
    """Group 3: the honest remainder.

    A cross-provider comparison that reported only agreement would be hiding its
    most useful output. These three differences are real, they are asymmetric, and
    each is a provider fact rather than an adapter defect.
    """

    def setUp(self):
        self.api, self.skills = both()

    def test_api_football_states_a_winner_and_the_native_shape_does_not(self):
        """``teams.*.winner`` is a provider field. The native shape has none, and
        deriving one from ``2-1`` would be inference in the one property —
        ``sport:eventOutcome`` — that must never carry one."""
        self.assertEqual([p.get("outcome") for p in self.api["participants"]],
                         ["win", "loss"])
        for participant in self.skills["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("outcome", participant)

    def test_api_football_states_a_clock_reading_and_the_native_shape_does_not(self):
        """``fixture.status.elapsed`` is a minutes-played reading. ``EventShape``
        has nowhere to put it, so it reaches ``event_view`` only — on one side."""
        self.assertEqual(self.api["event"]["clock"], {"minute": "90"})
        self.assertNotIn("clock", self.skills["event"])

    def test_the_native_shape_states_a_venue_country_and_api_football_does_not(self):
        """The asymmetry runs both ways. ``league.country`` is the competition's
        country, not the venue's, so the API-Football adapter declines to read it
        as one — which is a decision, and it costs a fact."""
        self.assertEqual(self.skills["site"]["country"], "SYN")
        self.assertNotIn("country", self.api["site"])

    def test_the_capability_reports_say_so_rather_than_leaving_it_to_a_reader(self):
        """The difference is not buried: a consumer reads it off the capability
        report before it parses anything."""
        api = envelope(api_football_observation(),
                       API_FOOTBALL_NAMESPACE)["machina_sports_schema"]["capabilities"]
        skills = envelope(sports_skills_observation(),
                          SPORTS_SKILLS_NAMESPACE)["machina_sports_schema"]["capabilities"]
        self.assertIn("event.result", api["present"])
        self.assertIn("event.result", skills["absent"])
        self.assertIn("event.clock", api["present"])
        self.assertIn("event.clock", skills["absent"])

    def test_the_extra_facts_do_not_change_the_tier_either_side_reaches(self):
        """A winner and a clock reading are not a live feed. Both sides are
        ``core``, and claiming otherwise would tell a consumer it can rely on
        timeline data neither payload contains."""
        for label, document, namespace in (
            ("api-football", api_football_observation(), API_FOOTBALL_NAMESPACE),
            ("sports-skills", sports_skills_observation(), SPORTS_SKILLS_NAMESPACE),
        ):
            capabilities = envelope(
                document, namespace)["machina_sports_schema"]["capabilities"]
            with self.subTest(provider=label):
                self.assertEqual(capabilities["tier"], "core")
                self.assertEqual(capabilities["violations"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
