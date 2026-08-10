"""Tests for the Stats Perform / Opta canonical adapter (PR 2, task A15a.2).

Run from the repository root:

    python3 tests/test_iptc_stats_perform_opta_adapter.py -v

Run the file directly, for the same reason as
``tests/test_iptc_canonical_serializer.py``: ``tests/`` is a namespace directory
with no ``__init__.py``, so ``-m unittest tests.<module>`` can be shadowed by an
installed distribution that ships a top-level regular ``tests`` package.

A focused file per provider, on purpose: a failure here names Stats Perform
rather than "the canonical suite", and the four-layer assertion block is
deliberately repeated rather than factored into a shared loop (A14 handoff
item 1).

**The source is a legacy mapping-contract shape, and this file exists partly to
keep that label honest.** No Stats Perform sample is checked into this
repository at all — not a payload, not a captured response. The closest evidence
is ``tools/iptc/fixtures/baseline/stats-perform-opta-event.json``, which PR 1
hand-authored from the literal key set of ``iptc-opta-event-mapping``. It is
therefore evidence of what *Machina's own mapping emits*, one step removed from
what Opta sends, and it is synthetic throughout. Calling it provider data would
be a claim nothing here supports.

What is defended beyond A13 and A15a.1:

1. **The source is labelled for what it is.** ``legacy-mapping-contract-shape``,
   with a limitation naming the two removes from provider data.
2. **Actions reach the graph, and the unpinned soccer action vocabulary does
   not.** The embedded timeline carries an Opta action type and an unverifiable
   ``spsocaction`` NewsCode IRI. The action's *class* maps to pinned
   ``spactionclass:``; the type and the IRI survive only in ``event_view`` and
   ``raw``.
3. **An action whose type has no defensible class is still not dropped** — it
   loses its ``sport:Action`` and keeps its place in the view.
4. **Machina's own internal keys never escape ``raw``.** The legacy document
   carries a ``version_control`` block, which is neither Opta's nor IPTC's.
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

from tools.iptc import cli_support  # noqa: E402
from tools.iptc import profile as profile_module  # noqa: E402
from tools.iptc import report as report_module  # noqa: E402
from tools.iptc.canonical.adapters import stats_perform_opta  # noqa: E402
from tools.iptc.canonical.ids import surrogate_resolver  # noqa: E402
from tools.iptc.canonical.observation import validate_observation  # noqa: E402
from tools.iptc.canonical.serialize import canonical_envelope  # noqa: E402
from tools.iptc.validate import validate_document  # noqa: E402

#: The source evidence: PR 1's frozen baseline fixture for this mapping. READ
#: ONLY — it is the "before" document the corrected output is measured against,
#: and this task does not edit it.
SOURCE_PATH = (REPO_ROOT / "tools/iptc/fixtures/baseline"
               / "stats-perform-opta-event.json")

OBSERVATION_PATH = (REPO_ROOT
                    / "tools/iptc/fixtures/observations"
                    / "stats-perform-opta-soccer-observation.json")
GRAPH_PATH = (REPO_ROOT / "tools/iptc/fixtures/corrected"
              / "stats-perform-opta-soccer-graph.json")
ENVELOPE_PATH = (REPO_ROOT / "tools/iptc/fixtures/corrected"
                 / "stats-perform-opta-soccer-envelope.json")

#: Fixed, so the corrected fixtures are reproducible. Nothing in the adapter or
#: the serializer reads the clock; this is the one time value, and it is an input.
OBSERVED_AT = "2026-03-01T22:05:00+00:00"

SOURCE = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))


def observation():
    return stats_perform_opta.to_observation(SOURCE, observed_at=OBSERVED_AT)


def envelope():
    return canonical_envelope(observation(),
                              id_resolver=surrogate_resolver("stats-perform-opta"))


def serialized(document):
    """The exact bytes a corrected fixture is checked in as."""
    return json.dumps(document, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


class TestAdapterOutputIsAValidObservation(unittest.TestCase):
    """``validate_observation`` is the adapter's acceptance test (RFC 002 §1)."""

    def test_the_observation_is_valid(self):
        self.assertEqual(validate_observation(observation()), [])

    def test_the_document_claims_the_canonical_observation_contract(self):
        self.assertEqual(observation()["schema_version"], "canonical-observation/1")

    def test_the_top_level_document_carries_nothing_but_the_observation(self):
        self.assertEqual(sorted(observation()), ["observation", "schema_version"])

    def test_observed_at_is_the_caller_input_and_is_keyword_only(self):
        self.assertEqual(observation()["observation"]["observed_at"], OBSERVED_AT)
        with self.assertRaises(TypeError):
            stats_perform_opta.to_observation(SOURCE, OBSERVED_AT)

    def test_the_adapter_reads_the_payload_without_mutating_it(self):
        before = copy.deepcopy(SOURCE)
        stats_perform_opta.to_observation(SOURCE, observed_at=OBSERVED_AT)
        self.assertEqual(SOURCE, before)


class TestTheSourceIsLabelledForWhatItIs(unittest.TestCase):
    """A legacy mapping output is not raw provider data, and the difference is
    the whole reason this fixture's rights line reads differently from A13's."""

    def test_the_data_class_says_legacy_mapping_contract_shape(self):
        rights = observation()["observation"]["rights"]
        self.assertEqual(rights["data_class"], "legacy-mapping-contract-shape")
        self.assertEqual(rights["data_class"],
                         stats_perform_opta.RIGHTS_DATA_CLASS)

    def test_the_data_class_is_not_the_one_a_real_provider_example_earns(self):
        """A13 and A15a.1 read checked-in *provider examples*. This does not, and
        the audit has to be able to tell the two apart."""
        self.assertNotEqual(stats_perform_opta.RIGHTS_DATA_CLASS,
                            "licensed-provider-example-fixture")
        for word in ("redistributable", "provider-example", "production"):
            with self.subTest(word=word):
                self.assertNotIn(word, stats_perform_opta.RIGHTS_DATA_CLASS)

    def test_the_source_ref_names_the_mapping_rather_than_an_endpoint(self):
        """There is no endpoint class to cite: nothing here came from one."""
        refs = observation()["observation"]["adapter"]["source_refs"]
        self.assertEqual([ref["kind"] for ref in refs], ["legacy-mapping-output"])
        self.assertEqual(refs[0]["value"], "iptc-opta-event-mapping")
        self.assertIn("not raw provider data", refs[0]["note"])

    def test_no_source_ref_is_request_shaped(self):
        for ref in observation()["observation"]["adapter"]["source_refs"]:
            for marker in ("://", "?", "&", "key=", "token=", "secret"):
                with self.subTest(marker=marker):
                    self.assertNotIn(marker, ref["value"])

    def test_the_rights_block_refuses_a_commercial_reading(self):
        rights = observation()["observation"]["rights"]
        self.assertIs(rights["prototype_only"], True)
        self.assertIs(rights["commercial_use"], False)

    def test_the_provider_namespace_and_family_are_recorded(self):
        self.assertEqual(observation()["observation"]["provider"],
                         {"namespace": "stats-perform-opta", "family": "licensed"})

    def test_the_adapter_identifies_itself(self):
        adapter = observation()["observation"]["adapter"]
        self.assertEqual(adapter["name"],
                         "tools.iptc.canonical.adapters.stats_perform_opta")
        self.assertTrue(adapter["version"])


class TestProviderFactsAreReadCorrectly(unittest.TestCase):
    """Every value below is traceable to one key of the checked-in document."""

    def setUp(self):
        self.observation = observation()["observation"]

    def test_the_opta_identifier_is_recovered_from_the_legacy_urn(self):
        """``urn:opta:sport_event:…`` is Machina's own wrapper around Opta's id.
        Recording the wrapper as a provider identifier would attribute this
        repository's URN scheme to Stats Perform."""
        self.assertEqual(self.observation["event"]["provider_id"],
                         "synthetic0matchid001")

    def test_the_event_start_time_is_read_from_schema_start_date(self):
        self.assertEqual(self.observation["event"]["start_time"],
                         "2026-03-01T20:00:00Z")

    def test_the_status_is_the_canonical_key_not_the_opta_word(self):
        self.assertEqual(self.observation["event"]["status"], "closed")

    def test_the_competition_season_and_stage_are_read_with_their_own_ids(self):
        competition = self.observation["competition"]
        self.assertEqual(competition["provider_id"], "synthetic0compid001")
        self.assertEqual(competition["name"], "Synthetic Premier Division")
        self.assertEqual(competition["season"]["provider_id"], "synthetic0tcalid001")
        self.assertEqual(competition["season"]["name"], "2025/2026")

    def test_the_stage_becomes_the_competition_phase(self):
        """Opta addresses a stage by an identifier of its own, unlike
        Sportradar's round ordinal, so a phase is provider-native evidence here
        and is not in A15a.1."""
        phase = self.observation["phase"]
        self.assertEqual(phase["provider_id"], "synthetic0stageid01")
        self.assertEqual(phase["name"], "Regular Season")

    def test_the_competition_format_becomes_a_pinned_competition_type(self):
        """``Domestic league`` is Opta stating the competition is a league. This
        is the one corrected fixture that reaches ``spct:league``."""
        self.assertEqual(self.observation["competition"]["type"], "league")

    def test_the_attendance_and_the_winner_are_read_from_match_info(self):
        self.assertEqual(self.observation["event"]["attendance"], "60123")
        self.assertEqual([p["outcome"] for p in self.observation["participants"]],
                         ["win", "loss"])

    def test_home_comes_first_and_both_teams_carry_alignment_and_score(self):
        self.assertEqual(
            [(p["kind"], p["provider_id"], p["name"], p["alignment"], p["score"])
             for p in self.observation["participants"]],
            [("team", "synthetic0teamid001", "Synthetic Home United", "home", "2"),
             ("team", "synthetic0teamid002", "Synthetic Away Town", "away", "1")],
        )

    def test_the_site_is_read_from_the_venue_block(self):
        site = self.observation["site"]
        self.assertEqual(site["provider_id"], "synthetic0venueid01")
        self.assertEqual(site["name"], "Synthetic Home Ground")

    def test_the_sport_is_declared_as_the_medtop_code_and_a_key(self):
        self.assertEqual(self.observation["sport"],
                         {"medtop": "20001065", "key": "soccer"})

    def test_the_raw_document_is_carried_verbatim(self):
        self.assertEqual(self.observation["raw"], SOURCE)


class TestActionsReachTheGraphAndTheirTypeDoesNot(unittest.TestCase):
    """The one corrected fixture with a timeline, and the whole point of it.

    RFC 001 §9.2: no soccer action-type NewsCode is emitted under any prefix,
    because no vocabulary TTL for the scheme exists at the pin and layer 4 fails
    closed on ``unverifiable``. The action *class* goes to pinned
    ``spactionclass:``; the provider's own action type survives in ``event_view``
    and ``raw``.
    """

    def setUp(self):
        self.observation = observation()["observation"]
        self.block = envelope()["machina_sports_schema"]

    def test_the_timeline_becomes_one_canonical_action(self):
        actions = self.observation["actions"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["ordinal"], 1)
        self.assertEqual(actions[0]["minute"], "23")
        self.assertEqual(actions[0]["period"], "1")
        self.assertEqual(actions[0]["action_time"], "2026-03-01T20:23:11Z")

    def test_the_opta_type_becomes_a_defensible_action_class(self):
        self.assertEqual(self.observation["actions"][0]["class"], "score")

    def test_the_provider_action_type_is_kept_beside_the_class(self):
        """Kept so ``event_view`` can carry what Opta actually said, and so the
        class is auditable against it rather than replacing it."""
        self.assertEqual(self.observation["actions"][0]["provider_type"], "G")

    def test_the_graph_emits_the_action_with_a_pinned_action_class(self):
        actions = [n for n in self.block["sport_schema_graph"]["@graph"]
                   if n["@type"] == "sport:Action"]
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["sport:class"], {"@id": "spactionclass:score"})

    def test_the_action_is_attached_to_the_scoring_teams_participation(self):
        """The scorer is named in the timeline but is not a match participant
        here. See ``test_no_scorer_is_promoted_to_a_match_participant``."""
        graph = {n["@id"]: n for n in self.block["sport_schema_graph"]["@graph"]}
        action = next(n for n in graph.values() if n["@type"] == "sport:Action")
        target = graph[action["sport:participation"]["@id"]]
        self.assertEqual(target["@type"], "sport:TeamParticipation")
        self.assertEqual(target["sport:alignment"], "home")

    def test_no_unpinned_soccer_action_vocabulary_is_asserted_in_the_graph(self):
        """The legacy document carries
        ``http://cv.iptc.org/newscodes/spsocaction/g`` as ``sport:actionType``.
        Layer 4 reports that scheme ``unverifiable`` and fails closed, so a
        corrected document that forwarded it would not conform.

        ``@graph`` rather than the whole document: the shared context *binds*
        ``spsocactiontype`` because upstream declares it, and binding a prefix
        commits to nothing. Only an emitted value would be a claim.
        """
        blob = json.dumps(self.block["sport_schema_graph"]["@graph"])
        for token in ("spsocaction", "spsocactiontype", "newscodes/spsocaction"):
            with self.subTest(token=token):
                self.assertNotIn(token, blob)
        self.assertNotIn("sport:actionType", blob)

    def test_the_provider_action_type_survives_in_the_view(self):
        """The mirror. Dropping the unverifiable NewsCode must not cost the fact
        that Opta called this action a ``G``."""
        actions = self.block["event_view"]["actions"]
        self.assertEqual([a["class"] for a in actions], ["score"])
        self.assertEqual([a["label"] for a in actions], ["G at 23' - Period 1"])

    def test_the_unverifiable_newscode_iri_is_still_readable_in_raw(self):
        raw = self.block["event_view"]["provider"]["raw"]
        self.assertEqual(raw["sport:timeline"][0]["sport:actionType"],
                         "http://cv.iptc.org/newscodes/spsocaction/g")

    def test_an_action_type_with_no_defensible_class_keeps_its_place_in_the_view(self):
        """Unlike a status, an action class is not required, so an unmapped type
        is an omission rather than a raise: the ``sport:Action`` is not emitted
        (``sport:class`` is mandatory on one) and the view still carries it."""
        payload = copy.deepcopy(SOURCE)
        payload["sport:timeline"][0]["type"] = "ZZZ"
        document = stats_perform_opta.to_observation(payload,
                                                     observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(document), [])
        action = document["observation"]["actions"][0]
        self.assertNotIn("class", action)
        self.assertEqual(action["provider_type"], "ZZZ")

        block = canonical_envelope(
            document, id_resolver=surrogate_resolver("stats-perform-opta")
        )["machina_sports_schema"]
        self.assertEqual([n for n in block["sport_schema_graph"]["@graph"]
                          if n["@type"] == "sport:Action"], [])
        self.assertEqual(len(block["event_view"]["actions"]), 1)

    def test_a_card_maps_to_the_infraction_class(self):
        """The second attested Opta code in this repository's evidence. The
        sibling baseline fixture ``stats-perform-opta-timeline.json`` carries it;
        it is exercised here over a mutated copy rather than by reading a second
        source document into one observation."""
        payload = copy.deepcopy(SOURCE)
        payload["sport:timeline"][0]["type"] = "YC"
        document = stats_perform_opta.to_observation(payload,
                                                     observed_at=OBSERVED_AT)
        self.assertEqual(document["observation"]["actions"][0]["class"],
                         "infraction")

    def test_every_mapped_action_class_is_a_pinned_action_class_code(self):
        from tools.iptc.canonical.vocab import ACTION_CLASS

        self.assertTrue(stats_perform_opta.ACTION_CLASS_BY_TYPE)
        for code, canonical in sorted(
                stats_perform_opta.ACTION_CLASS_BY_TYPE.items()):
            with self.subTest(code=code):
                self.assertIn(canonical, ACTION_CLASS)

    def test_the_action_table_holds_only_codes_this_repository_has_evidence_for(self):
        """Opta's real event vocabulary is far wider than two codes. This adapter
        reads a hand-authored mapping-contract shape, so the only codes it can
        honestly claim to have seen are the ones that shape carries. Guessing the
        rest would be inventing provider vocabulary."""
        self.assertEqual(sorted(stats_perform_opta.ACTION_CLASS_BY_TYPE),
                         ["G", "YC"])


class TestAbsenceStaysAbsent(unittest.TestCase):
    """The document's real absences, kept absent."""

    def setUp(self):
        self.observation = observation()["observation"]

    def test_no_scorer_is_promoted_to_a_match_participant(self):
        """The timeline names ``Synthetic Scorer``. Adding them as an individual
        participant would make the capability report claim ``event.lineups`` off
        one scorer, which is exactly the "you can rely on data you will not get"
        failure the tier rules exist to prevent."""
        self.assertEqual([p["kind"] for p in self.observation["participants"]],
                         ["team", "team"])
        self.assertNotIn("memberships", self.observation)

    def test_no_outcome_type_is_inferred_from_null_penalties(self):
        """``sport:penalties`` and ``sport:aggregate`` are both null. That is the
        absence of a statement, not a statement of ``regular``."""
        self.assertNotIn("outcome_type", self.observation["event"])

    def test_no_clock_is_invented_from_the_match_info_period_length(self):
        """``numberOfPeriods`` and ``periodLength`` describe the format of the
        match, not how far into it play had reached."""
        self.assertNotIn("clock", self.observation["event"])

    def test_no_city_or_country_is_invented_from_the_venue_coordinates(self):
        for key in ("city", "country"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.observation["site"])

    def test_no_end_time_is_invented(self):
        self.assertNotIn("end_time", self.observation["event"])

    def test_a_document_with_no_winner_yields_no_participant_outcome(self):
        payload = copy.deepcopy(SOURCE)
        del payload["sport:matchInfo"]["sport:winner"]
        payload["sport:score"]["sport:homeScore"] = 1
        drawn = stats_perform_opta.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(drawn), [])
        for participant in drawn["observation"]["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("outcome", participant)

    def test_a_pre_match_document_omits_the_scoreline_rather_than_zeroing_it(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:status"] = "Fixture"
        payload["sport:score"] = {}
        payload["sport:matchInfo"] = {}
        del payload["sport:timeline"]
        pre_match = stats_perform_opta.to_observation(payload,
                                                      observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(pre_match), [])
        self.assertEqual(pre_match["observation"]["event"]["status"],
                         "not_started")
        self.assertNotIn("actions", pre_match["observation"])
        for participant in pre_match["observation"]["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("score", participant)

    def test_a_genuine_nil_nil_scoreline_survives(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:score"]["sport:homeScore"] = 0
        payload["sport:score"]["sport:awayScore"] = 0
        nil_nil = stats_perform_opta.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual([p["score"] for p in nil_nil["observation"]["participants"]],
                         ["0", "0"])

    def test_an_unmapped_competition_format_yields_no_type_rather_than_a_raise(self):
        """A competition type is not required, so an unrecognised format is an
        omission. Only ``event.status`` raises, because only it is required."""
        payload = copy.deepcopy(SOURCE)
        payload["sport:competition"]["sport:competitionFormat"] = "Exhibition"
        document = stats_perform_opta.to_observation(payload,
                                                     observed_at=OBSERVED_AT)
        self.assertNotIn("type", document["observation"]["competition"])


class TestUnmappableProviderValuesFailLoudly(unittest.TestCase):
    """A required provider value with no defensible reading is an error."""

    def test_an_unmapped_status_raises_and_names_it(self):
        payload = copy.deepcopy(SOURCE)
        payload["sport:status"] = "Zzz"
        with self.assertRaises(ValueError) as raised:
            stats_perform_opta.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertIn("Zzz", str(raised.exception))

    def test_a_missing_status_raises_rather_than_defaulting(self):
        payload = copy.deepcopy(SOURCE)
        del payload["sport:status"]
        with self.assertRaises(ValueError):
            stats_perform_opta.to_observation(payload, observed_at=OBSERVED_AT)

    def test_every_mapped_status_reaches_a_pinned_event_status_newscode(self):
        from tools.iptc.canonical.vocab import EVENT_STATUS

        self.assertTrue(stats_perform_opta.EVENT_STATUS_BY_MATCH_STATUS)
        for code, canonical in sorted(
                stats_perform_opta.EVENT_STATUS_BY_MATCH_STATUS.items()):
            with self.subTest(code=code):
                self.assertIn(canonical, EVENT_STATUS)

    def test_a_document_with_no_event_identifier_raises(self):
        payload = copy.deepcopy(SOURCE)
        del payload["@id"]
        with self.assertRaises(ValueError):
            stats_perform_opta.to_observation(payload, observed_at=OBSERVED_AT)

    def test_a_document_stating_a_different_sport_raises(self):
        payload = copy.deepcopy(SOURCE)
        payload["schema:sportName"] = "rugby union"
        with self.assertRaises(ValueError) as raised:
            stats_perform_opta.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertIn("rugby union", str(raised.exception))


class TestCorrectedFixturesAreReproducible(unittest.TestCase):
    """A checked-in fixture that cannot be regenerated is a screenshot."""

    def test_the_observation_fixture_is_reproducible_from_the_adapter(self):
        self.assertEqual(OBSERVATION_PATH.read_text(encoding="utf-8"),
                         serialized(observation()))

    def test_the_envelope_fixture_is_reproducible_byte_for_byte(self):
        self.assertEqual(ENVELOPE_PATH.read_text(encoding="utf-8"),
                         serialized(envelope()))

    def test_the_graph_fixture_is_exactly_the_envelope_graph(self):
        self.assertEqual(
            json.loads(GRAPH_PATH.read_text(encoding="utf-8")),
            envelope()["machina_sports_schema"]["sport_schema_graph"],
        )

    def test_two_runs_of_the_adapter_agree(self):
        self.assertEqual(serialized(envelope()), serialized(envelope()))

    def test_the_envelope_claims_both_versions_and_every_rfc_002_part(self):
        block = envelope()["machina_sports_schema"]
        self.assertEqual(sorted(block), [
            "capabilities", "event_view", "profile", "provenance", "provider_ids",
            "rights", "schema_version", "sport_schema_graph",
        ])
        self.assertEqual(block["schema_version"], "machina-sports-schema/1")
        self.assertEqual(block["profile"], "machina-iptc-profile/1.1")

    def test_the_capability_tier_is_core_despite_the_actions(self):
        """Actions alone do not reach ``live``: that tier also needs a clock and
        a period reading, and this document states neither. Tiers do not skip."""
        capabilities = envelope()["machina_sports_schema"]["capabilities"]
        self.assertEqual(capabilities["tier"], "core")
        self.assertEqual(capabilities["tiers_satisfied"], ["core"])
        self.assertEqual(capabilities["violations"], [])
        self.assertIn("event.actions", capabilities["present"])
        self.assertIn("event.clock", capabilities["absent"])


class TestRightsAreRefusedForProduction(unittest.TestCase):
    """Checked twice: the library gate RFC 002 §9 names, and the command an
    operator actually runs."""

    def test_the_library_gate_refuses_the_checked_in_envelope_once(self):
        from tools.iptc.validate_graph import rights_findings

        checked_in = json.loads(ENVELOPE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(rights_findings(checked_in, consumer_tier="prototype"), [])
        findings = rights_findings(checked_in, consumer_tier="production")
        self.assertEqual([f["code"] for f in findings], ["rights-prototype-only"])
        self.assertEqual(findings[0]["data_class"],
                         stats_perform_opta.RIGHTS_DATA_CLASS)

    def test_the_command_exits_zero_for_prototype_and_nonzero_for_production(self):
        import contextlib
        import io

        from tools.iptc import validate_graph

        argument = str(ENVELOPE_PATH.relative_to(REPO_ROOT))
        for tier, expected in (("prototype", 0), ("production", 1)):
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                status = validate_graph.main(["--consumer-tier", tier, argument])
            with self.subTest(tier=tier):
                self.assertEqual(status, expected)
        self.assertIn("rights-prototype-only", buffer.getvalue())


class TestIdentityIsASurrogate(unittest.TestCase):
    """Provider identifiers are crosswalk evidence; canonical identity is minted
    (RFC 001 §7.6)."""

    def setUp(self):
        self.block = envelope()["machina_sports_schema"]

    def test_every_graph_resource_id_is_a_marked_machina_surrogate(self):
        for node in self.block["sport_schema_graph"]["@graph"]:
            with self.subTest(node=node["@type"]):
                self.assertRegex(node["@id"],
                                 r"^urn:machina:sports:[a-z-]+:x[0-9a-f]{32}$")

    def test_no_legacy_opta_urn_survives_in_the_graph(self):
        """The source document's own resource ids are ``urn:opta:…``. A corrected
        document carrying one would be the old identity model in new clothes."""
        blob = json.dumps(self.block["sport_schema_graph"])
        self.assertNotIn("urn:opta", blob)

    def test_the_crosswalk_holds_every_provider_identifier_the_document_stated(self):
        entries = self.block["provider_ids"]
        self.assertEqual([e["entity_type"] for e in entries],
                         ["competition", "season", "phase", "site", "event",
                          "team", "team"])
        self.assertEqual(
            sorted(e["provider_id"] for e in entries),
            sorted(["synthetic0compid001", "synthetic0tcalid001",
                    "synthetic0stageid01", "synthetic0venueid01",
                    "synthetic0matchid001", "synthetic0teamid001",
                    "synthetic0teamid002"]),
        )
        for entry in entries:
            with self.subTest(entity=entry["entity_type"]):
                self.assertEqual(entry["provider_namespace"], "stats-perform-opta")
                self.assertEqual(entry["resolution_method"], "provider-native")

    def test_no_crosswalk_entry_carries_the_machina_urn_wrapper(self):
        """The recovered Opta identifier, not the legacy URN it was wrapped in."""
        for entry in self.block["provider_ids"]:
            with self.subTest(entity=entry["entity_type"]):
                self.assertNotIn("urn:", entry["provider_id"])

    def test_every_crosswalk_entry_names_the_field_it_came_from(self):
        by_type = {e["entity_type"]: e for e in self.block["provider_ids"]}
        self.assertEqual(by_type["event"]["evidence"],
                         "observation.event.provider_id")
        self.assertEqual(by_type["phase"]["evidence"],
                         "observation.phase.provider_id")


class TestNothingFabricatedReachesTheOutput(unittest.TestCase):
    """Scanned over emitted output rather than over a helper. A helper that drops
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
        view = copy.deepcopy(self.block["event_view"])
        view.get("provider", {}).pop("raw", None)
        blob = json.dumps(view)
        self.assertNotIn("null", blob)
        self.assertNotIn('""', blob)
        for value in sorted(profile_module.PLACEHOLDER_VALUES):
            if value:
                with self.subTest(placeholder=value):
                    self.assertNotIn('"{0}"'.format(value), blob)

    def test_machinas_own_version_control_block_never_escapes_raw(self):
        """The legacy document carries a ``version_control`` block, which is
        neither Opta's fact nor an IPTC term. It is the clearest marker that this
        source is Machina's output rather than a provider's."""
        view = copy.deepcopy(self.block["event_view"])
        view.get("provider", {}).pop("raw", None)
        for blob in (json.dumps(self.block["sport_schema_graph"]),
                     json.dumps(view)):
            with self.subTest(part=blob[:24]):
                self.assertNotIn("version_control", blob)
                self.assertNotIn("consumer-update-timestamp", blob)

    def test_the_version_control_block_is_still_readable_in_raw(self):
        raw = self.block["event_view"]["provider"]["raw"]
        self.assertIn("version_control", raw)
        self.assertIsNone(raw["version_control"]["consumer-update-timestamp"])

    def test_no_official_resource_carries_a_machina_property(self):
        for node in self.block["sport_schema_graph"]["@graph"]:
            if str(node["@type"]).startswith("sport:"):
                with self.subTest(resource=node["@type"]):
                    self.assertEqual([k for k in node if k.startswith("machina:")], [])


class TestCorrectedGraphConformance(unittest.TestCase):
    """The claim this task exists to make, checked by the PR 1 harness rather
    than by assertion: a corrected Opta document conforms, actions and all."""

    @classmethod
    def setUpClass(cls):
        cls.result = validate_document(GRAPH_PATH,
                                       "corrected-stats-perform-opta-soccer",
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

    def test_the_controlled_vocabulary_layer_checked_real_codes(self):
        detail = self.result.layers["controlled_vocabulary"]["detail"]
        self.assertGreater(len(detail["valid"]), 0)
        for key in ("invalid", "undeclared_prefix", "unverifiable"):
            with self.subTest(key=key):
                self.assertEqual(detail[key], [])

    def test_the_pinned_action_class_is_among_the_codes_layer_four_verified(self):
        """The corrected document's whole reason for carrying a timeline: the
        code it *does* emit is one layer 4 can check, unlike the one it drops."""
        detail = self.result.layers["controlled_vocabulary"]["detail"]
        self.assertIn("http://cv.iptc.org/newscodes/spactionclass/score",
                      [entry["value"] for entry in detail["valid"]])

    def test_the_document_conforms_overall(self):
        self.assertTrue(self.result.conforms)


class TestCorrectedSectionIsRegistered(unittest.TestCase):
    """A corrected fixture nothing runs is a corrected fixture nobody checks."""

    def setUp(self):
        self.entry = next(
            e for e in report_module.load_provenance()["corrected"]
            if e["fixture"] == "corrected-stats-perform-opta-soccer")

    def test_the_corrected_graph_is_registered_and_resolvable(self):
        self.assertEqual(self.entry["class"], "corrected-serializer-output")
        self.assertEqual(report_module.resolve(self.entry), GRAPH_PATH)
        self.assertTrue(report_module.resolve(self.entry).is_file())

    def test_the_entry_labels_its_evidence_and_its_limits(self):
        for key in ("source", "transformation", "emitted_by", "limitation",
                    "rights"):
            with self.subTest(key=key):
                self.assertTrue(self.entry.get(key))

    def test_the_entry_calls_the_source_a_legacy_mapping_shape_and_not_provider_data(self):
        """The honesty requirement, made mechanical. A reader must not be able to
        come away thinking a Stats Perform response is checked in here."""
        self.assertIn(str(SOURCE_PATH.relative_to(REPO_ROOT)), self.entry["source"])
        self.assertIn("legacy-mapping-contract-shape", self.entry["rights"])
        for phrase in ("legacy mapping", "not raw provider data"):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.entry["limitation"].lower()
                              + self.entry["transformation"].lower())

    def test_the_section_is_reachable_through_registered_fixtures(self):
        registered = dict(cli_support.registered_fixtures(["corrected"]))
        self.assertEqual(registered["corrected-stats-perform-opta-soccer"],
                         GRAPH_PATH)

    def test_the_baseline_opta_fixtures_are_untouched(self):
        """The source doubles as the "before" evidence. It stays a baseline row,
        read-only, so the audit still measures the corrected output against it."""
        for name in ("stats-perform-opta-event", "stats-perform-opta-timeline"):
            entry = next(e for e in report_module.load_provenance()["baseline"]
                         if e["fixture"] == name)
            with self.subTest(fixture=name):
                self.assertEqual(entry["class"], "mapping-contract-synthetic")
                self.assertTrue(report_module.resolve(entry).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
