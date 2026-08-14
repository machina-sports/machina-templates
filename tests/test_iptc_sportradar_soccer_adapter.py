"""Tests for the Sportradar soccer canonical adapter (PR 2, task A15a.1).

Run from the repository root:

    python3 tests/test_iptc_sportradar_soccer_adapter.py -v

Run the file directly, for the same reason as
``tests/test_iptc_canonical_serializer.py``: ``tests/`` is a namespace directory
with no ``__init__.py``, so ``-m unittest tests.<module>`` can be shadowed by an
installed distribution that ships a top-level regular ``tests`` package.

A focused file per provider, on purpose: a failure here names Sportradar rather
than "the canonical suite", and the four-layer assertion block is deliberately
repeated rather than factored into a shared loop (A14 handoff item 1).

What is defended here, beyond what A13 already proved for API-Football:

1. **The source is the raw provider payload, not this repository's own output.**
   ``agent-templates/iptc-mappings/example-sportradar.json`` is Sportradar's
   ``sport_event`` / ``sport_event_status`` summary shape, already checked in. No
   Sportradar endpoint was called and no credential exists in this process.
2. **Sportradar states facts API-Football does not, and each one is read from the
   field that states it** — a standalone season identifier, a venue country that
   is genuinely the venue's, an attendance count, and a ``winner_id`` naming the
   competitor rather than flagging each side.
3. **Sportradar also states less in places, and those stay absent** — no round
   identifier, no competition type, no clock, no actions.
4. **A provider status with no defensible canonical reading raises**, including
   Sportradar's own ``unknown``, which is a placeholder rather than a status.
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
from tools.iptc.canonical.adapters import sportradar_soccer  # noqa: E402
from tools.iptc.canonical.ids import surrogate_resolver  # noqa: E402
from tools.iptc.canonical.observation import validate_observation  # noqa: E402
from tools.iptc.canonical.serialize import canonical_envelope  # noqa: E402
from tools.iptc.validate import validate_document  # noqa: E402

#: The source evidence: a sanitized Sportradar summary payload already checked
#: into this repository. Read-only here — this task changes no provider mapping,
#: no example and no connector.
NATIVE_PATH = REPO_ROOT / "agent-templates/iptc-mappings/example-sportradar.json"

OBSERVATION_PATH = (REPO_ROOT
                    / "tools/iptc/fixtures/observations"
                    / "sportradar-soccer-observation.json")
GRAPH_PATH = (REPO_ROOT / "tools/iptc/fixtures/corrected"
              / "sportradar-soccer-graph.json")
ENVELOPE_PATH = (REPO_ROOT / "tools/iptc/fixtures/corrected"
                 / "sportradar-soccer-envelope.json")

#: Fixed, so the corrected fixtures are reproducible. Nothing in the adapter or
#: the serializer reads the clock; this is the one time value, and it is an input.
OBSERVED_AT = "2026-03-01T22:05:00+00:00"

NATIVE = json.loads(NATIVE_PATH.read_text(encoding="utf-8"))


def observation():
    return sportradar_soccer.to_observation(NATIVE, observed_at=OBSERVED_AT)


def envelope():
    return canonical_envelope(observation(),
                              id_resolver=surrogate_resolver("sportradar-soccer"))


def serialized(document):
    """The exact bytes a corrected fixture is checked in as."""
    return json.dumps(document, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


class TestAdapterOutputIsAValidObservation(unittest.TestCase):
    """``validate_observation`` is the adapter's acceptance test (RFC 002 §1)."""

    def test_the_observation_is_valid(self):
        self.assertEqual(validate_observation(observation()), [])

    def test_the_document_claims_the_canonical_observation_contract(self):
        self.assertEqual(observation()["schema_version"], "canonical-observation/1.1")

    def test_the_top_level_document_carries_nothing_but_the_observation(self):
        self.assertEqual(sorted(observation()), ["observation", "schema_version"])

    def test_observed_at_is_the_caller_input_and_is_keyword_only(self):
        self.assertEqual(observation()["observation"]["observed_at"], OBSERVED_AT)
        with self.assertRaises(TypeError):
            sportradar_soccer.to_observation(NATIVE, OBSERVED_AT)

    def test_the_adapter_reads_the_payload_without_mutating_it(self):
        before = copy.deepcopy(NATIVE)
        sportradar_soccer.to_observation(NATIVE, observed_at=OBSERVED_AT)
        self.assertEqual(NATIVE, before)


class TestProviderAndRightsHonesty(unittest.TestCase):
    """A checked-in provider example is shape evidence, not an entitlement."""

    def test_the_provider_namespace_and_family_are_recorded(self):
        self.assertEqual(observation()["observation"]["provider"],
                         {"namespace": "sportradar-soccer", "family": "licensed"})

    def test_the_rights_block_refuses_a_commercial_reading(self):
        rights = observation()["observation"]["rights"]
        self.assertIs(rights["prototype_only"], True)
        self.assertIs(rights["commercial_use"], False)

    def test_the_data_class_names_the_evidence_rather_than_a_licence(self):
        rights = observation()["observation"]["rights"]
        self.assertEqual(rights["data_class"], sportradar_soccer.RIGHTS_DATA_CLASS)
        self.assertEqual(rights["data_class"], "licensed-provider-example-fixture")
        self.assertNotIn("redistributable", rights["data_class"])

    def test_the_adapter_identifies_itself_and_its_endpoint_class(self):
        adapter = observation()["observation"]["adapter"]
        self.assertEqual(adapter["name"],
                         "tools.iptc.canonical.adapters.sportradar_soccer")
        self.assertTrue(adapter["version"])
        self.assertEqual([ref["kind"] for ref in adapter["source_refs"]],
                         ["endpoint-class"])

    def test_no_source_ref_is_request_shaped(self):
        for ref in observation()["observation"]["adapter"]["source_refs"]:
            for marker in ("://", "?", "&", "key=", "token=", "secret"):
                with self.subTest(marker=marker):
                    self.assertNotIn(marker, ref["value"])


class TestProviderFactsAreReadCorrectly(unittest.TestCase):
    """Every value below is traceable to one key of the checked-in payload."""

    def setUp(self):
        self.observation = observation()["observation"]

    def test_the_event_is_read_from_the_sport_event_block(self):
        event = self.observation["event"]
        self.assertEqual(event["provider_id"], "sr:sport_event:61623432")
        self.assertEqual(event["start_time"], "2025-08-17T19:30:00+00:00")

    def test_the_status_is_the_canonical_key_not_the_provider_code(self):
        self.assertEqual(self.observation["event"]["status"], "closed")

    def test_the_season_carries_sportradars_own_standalone_identifier(self):
        """Unlike API-Football, Sportradar addresses a season by an identifier of
        its own, so the crosswalk records that rather than the year."""
        competition = self.observation["competition"]
        self.assertEqual(competition["provider_id"], "sr:competition:8")
        self.assertEqual(competition["name"], "LaLiga")
        self.assertEqual(competition["season"]["provider_id"], "sr:season:130805")
        self.assertEqual(competition["season"]["name"], "LaLiga 25/26")

    def test_the_venue_country_is_the_venues_own(self):
        """``venue.country_name`` is the venue's country. API-Football's
        ``league.country`` is the competition's, which is why A13 omits it and
        this adapter records it."""
        site = self.observation["site"]
        self.assertEqual(site["provider_id"], "sr:venue:1307")
        self.assertEqual(site["name"], "RCDE Stadium")
        self.assertEqual(site["city"], "Cornella")
        self.assertEqual(site["country"], "Spain")

    def test_the_attendance_is_the_stated_count(self):
        self.assertEqual(self.observation["event"]["attendance"], "29612")

    def test_the_sport_is_declared_as_the_medtop_code_and_a_key(self):
        self.assertEqual(self.observation["sport"],
                         {"medtop": "20001065", "key": "soccer"})

    def test_home_comes_first_and_both_teams_carry_alignment_and_score(self):
        """A16 compares three providers on ``[home, away]`` order. An adapter that
        emitted payload order would fail that on ordering rather than on the
        concept alignment it exists to check."""
        self.assertEqual(
            [(p["kind"], p["provider_id"], p["name"], p["alignment"], p["score"])
             for p in self.observation["participants"]],
            [("team", "sr:competitor:2814", "Espanyol Barcelona", "home", "2"),
             ("team", "sr:competitor:2836", "Atletico Madrid", "away", "1")],
        )

    def test_home_is_emitted_first_even_when_the_payload_lists_away_first(self):
        payload = copy.deepcopy(NATIVE)
        payload["sport_event"]["competitors"].reverse()
        reordered = sportradar_soccer.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(
            [p["alignment"] for p in reordered["observation"]["participants"]],
            ["home", "away"],
        )

    def test_the_winner_id_names_one_competitor_and_the_other_loses(self):
        """Sportradar states the winner by identifier rather than by a flag per
        side, so both outcomes fall out of one stated fact."""
        self.assertEqual([p["outcome"] for p in self.observation["participants"]],
                         ["win", "loss"])

    def test_the_scoreline_is_full_time_not_the_period_scores(self):
        self.assertEqual([p["score"] for p in self.observation["participants"]],
                         ["2", "1"])

    def test_the_raw_payload_is_carried_verbatim_and_only_under_raw(self):
        self.assertEqual(self.observation["raw"], NATIVE)
        for section in sorted(set(self.observation) - {"raw"}):
            with self.subTest(section=section):
                self.assertNotIn("ball_locations",
                                 json.dumps(self.observation[section]))


class TestAbsenceStaysAbsent(unittest.TestCase):
    """The payload's real absences, confirmed against provider data."""

    def setUp(self):
        self.observation = observation()["observation"]

    def test_no_phase_is_invented_from_a_round_number(self):
        """``sport_event_context.round`` is ``{"number": 1}`` — an ordinal inside a
        season, not something Sportradar addresses a round by — and ``stage``
        carries no identifier at all. A13's ``league.round`` is different because
        that API takes that exact string as a round key."""
        self.assertNotIn("phase", self.observation)

    def test_no_competition_type_is_inferred_from_the_stage_type(self):
        """``stage.type: "league"`` describes the stage, and this observation
        carries no stage. Reading it as the competition's type would put a
        NewsCode on the graph nothing in the payload says."""
        self.assertNotIn("type", self.observation["competition"])

    def test_no_clock_and_no_period_are_invented(self):
        """The summary payload carries ``period_scores``, which are scores per
        period, not a clock reading."""
        self.assertNotIn("clock", self.observation["event"])

    def test_no_outcome_type_is_inferred_from_absent_extra_time(self):
        self.assertNotIn("outcome_type", self.observation["event"])

    def test_no_end_time_is_invented(self):
        self.assertNotIn("end_time", self.observation["event"])

    def test_no_action_and_no_player_is_invented_from_a_payload_with_neither(self):
        """The summary payload has no timeline. The checked-in
        ``sportradar-soccer-timeline`` baseline fixture is a *different*,
        synthetic match, so joining the two would fabricate a timeline for a real
        fixture."""
        for key in ("actions", "memberships"):
            with self.subTest(key=key):
                self.assertNotIn(key, self.observation)
        self.assertEqual([p["kind"] for p in self.observation["participants"]],
                         ["team", "team"])

    def test_a_payload_with_no_winner_yields_no_participant_outcome(self):
        """``winner_id`` is absent on a draw *and* on an unfinished fixture, so it
        cannot tell those apart. The scoreline and the status still travel."""
        payload = copy.deepcopy(NATIVE)
        del payload["sport_event_status"]["winner_id"]
        payload["sport_event_status"]["home_score"] = 1
        payload["sport_event_status"]["away_score"] = 1
        drawn = sportradar_soccer.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(drawn), [])
        for participant in drawn["observation"]["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("outcome", participant)
                self.assertEqual(participant["score"], "1")

    def test_a_pre_match_payload_omits_the_scoreline_rather_than_emitting_zero(self):
        payload = copy.deepcopy(NATIVE)
        payload["sport_event_status"] = {"status": "not_started"}
        pre_match = sportradar_soccer.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual(validate_observation(pre_match), [])
        self.assertEqual(pre_match["observation"]["event"]["status"], "not_started")
        for participant in pre_match["observation"]["participants"]:
            with self.subTest(team=participant["provider_id"]):
                self.assertNotIn("score", participant)
                self.assertNotIn("outcome", participant)

    def test_a_genuine_nil_nil_scoreline_survives(self):
        """``0`` is knowledge, ``None`` is not, so omission cannot be a truthiness
        test."""
        payload = copy.deepcopy(NATIVE)
        payload["sport_event_status"]["home_score"] = 0
        payload["sport_event_status"]["away_score"] = 0
        nil_nil = sportradar_soccer.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertEqual([p["score"] for p in nil_nil["observation"]["participants"]],
                         ["0", "0"])

    def test_an_absent_attendance_is_omitted_rather_than_zeroed(self):
        payload = copy.deepcopy(NATIVE)
        del payload["sport_event"]["sport_event_conditions"]
        thin = sportradar_soccer.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertNotIn("attendance", thin["observation"]["event"])


class TestUnmappableProviderValuesFailLoudly(unittest.TestCase):
    """A provider value with no defensible canonical reading is an error, not a
    default. The message has to name the code, or the fix lands by guesswork."""

    def test_an_unmapped_status_raises_and_names_it(self):
        payload = copy.deepcopy(NATIVE)
        payload["sport_event_status"]["status"] = "zzz"
        with self.assertRaises(ValueError) as raised:
            sportradar_soccer.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertIn("zzz", str(raised.exception))

    def test_sportradars_own_unknown_status_raises_rather_than_mapping(self):
        """``unknown`` is Sportradar declining to state a status. Mapping it to
        any canonical key would turn a declined statement into an asserted one."""
        payload = copy.deepcopy(NATIVE)
        payload["sport_event_status"]["status"] = "unknown"
        with self.assertRaises(ValueError):
            sportradar_soccer.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertNotIn("unknown", sportradar_soccer.EVENT_STATUS_BY_CODE)

    def test_a_missing_status_raises_rather_than_defaulting(self):
        payload = copy.deepcopy(NATIVE)
        payload["sport_event_status"] = {}
        with self.assertRaises(ValueError):
            sportradar_soccer.to_observation(payload, observed_at=OBSERVED_AT)

    def test_every_mapped_status_reaches_a_pinned_event_status_newscode(self):
        from tools.iptc.canonical.vocab import EVENT_STATUS

        self.assertTrue(sportradar_soccer.EVENT_STATUS_BY_CODE)
        for code, canonical in sorted(sportradar_soccer.EVENT_STATUS_BY_CODE.items()):
            with self.subTest(code=code):
                self.assertIn(canonical, EVENT_STATUS)

    def test_a_payload_with_no_event_identifier_raises(self):
        payload = copy.deepcopy(NATIVE)
        del payload["sport_event"]["id"]
        with self.assertRaises(ValueError):
            sportradar_soccer.to_observation(payload, observed_at=OBSERVED_AT)

    def test_a_payload_stating_a_different_sport_raises(self):
        """This adapter asserts ``medtop`` 20001065. A tennis payload read by it
        would emit association football for a tennis match, and nothing
        downstream could tell."""
        payload = copy.deepcopy(NATIVE)
        payload["sport_event"]["sport_event_context"]["sport"] = {
            "id": "sr:sport:5", "name": "Tennis"}
        with self.assertRaises(ValueError) as raised:
            sportradar_soccer.to_observation(payload, observed_at=OBSERVED_AT)
        self.assertIn("sr:sport:5", str(raised.exception))


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
        self.assertEqual(block["profile"], "machina-iptc-profile/1.2")

    def test_the_capability_tier_is_core_and_says_why(self):
        """No clock, no period and no actions, so ``live`` is correctly not
        claimed. Reporting it would tell a consumer it can rely on play-by-play it
        will never get from this payload."""
        capabilities = envelope()["machina_sports_schema"]["capabilities"]
        self.assertEqual(capabilities["tier"], "core")
        self.assertEqual(capabilities["tiers_satisfied"], ["core"])
        self.assertEqual(capabilities["violations"], [])
        self.assertIn("event.actions", capabilities["absent"])
        self.assertIn("event.clock", capabilities["absent"])
        self.assertIn("event.score", capabilities["present"])
        self.assertIn("event.result", capabilities["present"])


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
                         sportradar_soccer.RIGHTS_DATA_CLASS)

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

    def test_no_provider_urn_stem_or_sr_identifier_survives_in_the_graph(self):
        """The legacy mapping emits ``urn:sportradar:…`` resource ids built from
        ``sr:`` identifiers. A corrected document carrying either would be the old
        identity model in new clothes."""
        graph = self.block["sport_schema_graph"]
        for node in graph["@graph"]:
            with self.subTest(node=node["@id"]):
                self.assertNotIn("urn:sportradar", node["@id"])
                self.assertNotIn("sr:", node["@id"])

    def test_provider_identifiers_appear_only_as_crosswalk_evidence(self):
        """``sr:competitor:2814`` is admissible as the *value* of a ``machina:``
        crosswalk property and nowhere else."""
        for node in self.block["sport_schema_graph"]["@graph"]:
            if node["@type"] == "machina:ProviderIdentifier":
                continue
            with self.subTest(node=node["@type"]):
                self.assertNotIn("sr:competitor", json.dumps(node))

    def test_the_crosswalk_holds_every_provider_identifier_the_payload_stated(self):
        entries = self.block["provider_ids"]
        self.assertEqual([e["entity_type"] for e in entries],
                         ["competition", "season", "site", "event", "team", "team"])
        self.assertEqual(
            sorted(e["provider_id"] for e in entries),
            sorted(["sr:competition:8", "sr:season:130805", "sr:venue:1307",
                    "sr:sport_event:61623432", "sr:competitor:2814",
                    "sr:competitor:2836"]),
        )
        for entry in entries:
            with self.subTest(entity=entry["entity_type"]):
                self.assertEqual(entry["provider_namespace"], "sportradar-soccer")
                self.assertEqual(entry["resolution_method"], "provider-native")

    def test_every_crosswalk_entry_names_the_field_it_came_from(self):
        by_type = {e["entity_type"]: e for e in self.block["provider_ids"]}
        self.assertEqual(by_type["event"]["evidence"],
                         "observation.event.provider_id")
        self.assertEqual(by_type["season"]["evidence"],
                         "observation.competition.season.provider_id")


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
        """``provider.raw`` is excluded deliberately: it is the provider's own
        bytes and rewriting it would destroy the one field whose value is being an
        unaltered record."""
        view = copy.deepcopy(self.block["event_view"])
        view.get("provider", {}).pop("raw", None)
        blob = json.dumps(view)
        self.assertNotIn("null", blob)
        self.assertNotIn('""', blob)
        for value in sorted(profile_module.PLACEHOLDER_VALUES):
            if value:
                with self.subTest(placeholder=value):
                    self.assertNotIn('"{0}"'.format(value), blob)

    def test_the_provider_detail_the_graph_drops_is_still_readable_in_raw(self):
        """The mirror of the two scans above. Ball locations, referees, weather,
        broadcast channels and the match situation are all real Sportradar facts
        this profile has nowhere to put; none is lost."""
        raw = self.block["event_view"]["provider"]["raw"]
        self.assertIn("ball_locations", raw["sport_event_status"])
        self.assertIn("referees", raw["sport_event"]["sport_event_conditions"])
        self.assertEqual(raw["sport_event_status"]["match_status"], "ended")

    def test_no_official_resource_carries_a_machina_property(self):
        for node in self.block["sport_schema_graph"]["@graph"]:
            if str(node["@type"]).startswith("sport:"):
                with self.subTest(resource=node["@type"]):
                    self.assertEqual([k for k in node if k.startswith("machina:")], [])

    def test_no_unpinned_soccer_action_vocabulary_is_asserted(self):
        """This payload has no timeline, so there is nothing to tempt an adapter
        into ``spsocaction:``/``spsocactiontype:``. Asserted anyway, because the
        legacy Sportradar timeline mapping emits exactly that.

        ``@graph`` rather than the whole document, on purpose: the shared context
        *binds* ``spsocactiontype`` because upstream declares it, and binding a
        prefix commits to nothing. Only an emitted value would be a claim.
        """
        blob = json.dumps(self.block["sport_schema_graph"]["@graph"])
        for token in ("spsocaction", "spsocactiontype"):
            with self.subTest(token=token):
                self.assertNotIn(token, blob)


class TestColonDelimitedProviderIdsAreEvidenceNotCuries(unittest.TestCase):
    """Sportradar addresses every entity as ``sr:<kind>:<n>``, so its identifiers
    are colon-delimited and read as CURIEs to a scanner that only looks at shape.

    Layer 3's ``controlled-vocabulary-undeclared-prefix`` rule exists to catch the
    real in-repo defect, where a *term reference* uses a prefix nothing binds
    (``spsocaction:score-change``). ``machina:providerId`` is the one property
    whose entire purpose is to carry a provider's own identifier verbatim: it is
    foreign by construction and was never a term in our vocabulary. Flagging it
    would make the rule fire on the sanctioned fix for the defect it exists to
    report — the same trap A9 fenced off for ``provider-id-as-resource-id``, and
    fenced here the same way and no wider.
    """

    def test_a_provider_id_carrying_a_colon_is_not_an_undeclared_prefix(self):
        findings = profile_module.check(
            json.loads(GRAPH_PATH.read_text(encoding="utf-8"))).findings
        self.assertEqual(
            [f for f in findings
             if f["code"] == "controlled-vocabulary-undeclared-prefix"], [])

    def test_the_graph_still_carries_the_providers_own_identifier_verbatim(self):
        """The mirror. Exempting the property is only defensible while the value
        it protects is the provider's real identifier rather than a stripped one."""
        crosswalk = [node for node in envelope()["machina_sports_schema"]
                     ["sport_schema_graph"]["@graph"]
                     if node["@type"] == "machina:ProviderIdentifier"]
        self.assertIn("sr:competitor:2814",
                      [node["machina:providerId"] for node in crosswalk])

    def test_the_same_value_on_any_other_property_still_fires(self):
        """The fence is one property wide. A value shaped ``prefix:local`` under a
        prefix nothing binds is still broken everywhere else, including on the
        crosswalk resource's own sibling properties."""
        document = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        for property_name in ("machina:resolutionMethod", "rdfs:comment"):
            probe = copy.deepcopy(document)
            probe["@graph"][0][property_name] = "sr:competitor:2814"
            codes = [f["code"] for f in profile_module.check(probe).findings]
            with self.subTest(property=property_name):
                self.assertIn("controlled-vocabulary-undeclared-prefix", codes)

    def test_an_unbound_term_reference_the_rule_exists_for_still_fires(self):
        """``spsocaction:score-change`` is the defect in this repository's own
        Sportradar timeline mapping. The fence must not have switched it off."""
        probe = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
        probe["@graph"][0]["sport:actionType"] = "spsocaction:score-change"
        codes = [f["code"] for f in profile_module.check(probe).findings]
        self.assertIn("controlled-vocabulary-undeclared-prefix", codes)


class TestCorrectedGraphConformance(unittest.TestCase):
    """The claim this task exists to make, checked by the PR 1 harness rather
    than by assertion: Sportradar-derived data conforms."""

    @classmethod
    def setUpClass(cls):
        cls.result = validate_document(GRAPH_PATH, "corrected-sportradar-soccer",
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

    def test_the_document_conforms_overall(self):
        self.assertTrue(self.result.conforms)


class TestCorrectedSectionIsRegistered(unittest.TestCase):
    """A corrected fixture nothing runs is a corrected fixture nobody checks."""

    def test_the_corrected_graph_is_registered_and_resolvable(self):
        entries = report_module.load_provenance()["corrected"]
        self.assertIn("corrected-sportradar-soccer",
                      [entry["fixture"] for entry in entries])
        for entry in entries:
            with self.subTest(fixture=entry["fixture"]):
                self.assertEqual(entry["class"], "corrected-serializer-output")
                self.assertTrue(report_module.resolve(entry).is_file())

    def test_this_entry_labels_its_evidence_and_its_limits(self):
        entry = next(e for e in report_module.load_provenance()["corrected"]
                     if e["fixture"] == "corrected-sportradar-soccer")
        for key in ("source", "transformation", "emitted_by", "limitation",
                    "rights"):
            with self.subTest(key=key):
                self.assertTrue(entry.get(key))
        self.assertIn("example-sportradar.json", entry["source"])

    def test_the_section_is_reachable_through_registered_fixtures(self):
        registered = dict(cli_support.registered_fixtures(["corrected"]))
        self.assertEqual(registered["corrected-sportradar-soccer"], GRAPH_PATH)

    def test_the_baseline_sportradar_fixtures_are_untouched(self):
        """The 'before' evidence the audit is measured against. This task reads
        the raw provider example instead, and edits neither baseline file."""
        for name in ("sportradar-soccer-event", "sportradar-soccer-timeline"):
            entry = next(e for e in report_module.load_provenance()["baseline"]
                         if e["fixture"] == name)
            with self.subTest(fixture=name):
                self.assertNotEqual(entry["class"], "corrected-serializer-output")
                self.assertTrue(report_module.resolve(entry).is_file())


if __name__ == "__main__":
    unittest.main(verbosity=2)
