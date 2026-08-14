"""Reduced-precision temporal evidence: RFC 002 §12.

Run from the repository root:

    python3 tests/test_iptc_temporal_evidence.py -v

Run the file directly, for the same reason as every other IPTC suite: ``tests/``
is a namespace directory with no ``__init__.py``, so ``-m unittest
tests.<module>`` can be shadowed by an installed distribution that ships a
top-level regular ``tests`` package.

**What this suite defends.** A reduced-precision timestamp is not an instant. It
denotes a half-open interval, and the contract keeps three concerns apart: the
lexical value the source stated, the precision it declared, and the bounds that
value admits. Collapsing them is what makes an invented ``:00`` indistinguishable
from a stated one, forever, below every gate.

Nothing here reads a timezone database, and one test proves it: bounds are fixed
-offset arithmetic over an explicit offset carried by the source value itself.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.iptc import canonical  # noqa: E402
from tools.iptc.canonical.capabilities import (  # noqa: E402
    ALL_CAPABILITIES,
    GRAPH_UNAVAILABLE_REASONS,
    NOT_EXPRESSIBLE,
    TIER_OPTIONAL,
    TIER_ORDER,
    TIER_REQUIRED,
    capability_report,
    check_compatibility,
)
from tools.iptc.canonical.ids import surrogate_resolver  # noqa: E402
from tools.iptc.canonical.observation import (  # noqa: E402
    derive_bounds,
    validate_observation,
)
from tools.iptc.canonical.serialize import (  # noqa: E402
    GraphUnavailable,
    canonical_envelope,
    event_view,
    sport_schema_graph,
)

#: The proposed capability name, fixed by this implementation.
BOUNDED = "event.start_time.bounded"

#: The proposed refusal token, fixed by this implementation.
EXACT_REQUIRED = "exact-event-start-time-required"

#: The smallest exact observation that is genuinely valid, at the successor
#: identifier. Every case below is this document with exactly one thing changed,
#: so a failure names the rule it broke.
EXACT = {
    "schema_version": "canonical-observation/1.1",
    "observation": {
        "provider": {"namespace": "sports-skills/espn", "family": "public"},
        "observed_at": "2030-01-02T04:00:00+00:00",
        "adapter": {"name": "sports_skills.canonical.adapters.espn_nba",
                    "version": "0.1.0"},
        "rights": {"data_class": "public-non-commercial", "prototype_only": True,
                   "commercial_use": False},
        "sport": {"medtop": "20000851", "key": "basketball"},
        "competition": {
            "provider_id": "46",
            "name": "Synthetic Basketball League",
            "type": "recurring-competition",
        },
        "event": {
            "provider_id": "7001",
            "label": "H vs A",
            "start_time": "2030-01-02T03:05:00Z",
            "status": "closed",
        },
        "participants": [
            {"kind": "team", "provider_id": "7011", "name": "H",
             "alignment": "home", "score": "101"},
            {"kind": "team", "provider_id": "7012", "name": "A",
             "alignment": "away", "score": "99"},
        ],
    },
}

#: The reduced-precision counterpart: the same event, as a source that published
#: no second-of-minute actually stated it.
EVIDENCE = {
    "kind": "start",
    "source_value": "2030-01-02T03:05Z",
    "precision": "minute",
    "lower_inclusive": "2030-01-02T03:05:00Z",
    "upper_exclusive": "2030-01-02T03:06:00Z",
    "provenance": {
        "normalizer": "sports_skills.canonical.adapters.espn_nba",
        "normalizer_version": "0.1.0",
        "canonical_version": "0.2.0",
        "derivation": "declared_precision_interval",
    },
}


def reduced(**evidence_overrides):
    """:data:`EXACT` with its exact instant replaced by temporal evidence."""
    document = copy.deepcopy(EXACT)
    del document["observation"]["event"]["start_time"]
    evidence = copy.deepcopy(EVIDENCE)
    for key, value in evidence_overrides.items():
        if value is _ABSENT:
            evidence.pop(key, None)
        else:
            evidence[key] = value
    document["observation"]["event"]["temporal_evidence"] = evidence
    return document


class _Absent:
    def __repr__(self):
        return "<absent>"


#: Sentinel for "this key is not in the document at all", which is a different
#: document from one where the key holds ``None``.
_ABSENT = _Absent()


class TestBoundDerivation(unittest.TestCase):
    """G2/G6 — bounds are a pure, recomputable function of value and precision."""

    def test_a_utc_minute_value_denotes_the_minute_that_follows_it(self):
        self.assertEqual(
            derive_bounds("2030-01-02T03:05Z", "minute"),
            ("2030-01-02T03:05:00Z", "2030-01-02T03:06:00Z"),
        )

    def test_a_negative_offset_is_normalised_forward_to_utc(self):
        """RFC 002 §12.1's worked example: 03:05-03:00 is 06:05Z."""
        self.assertEqual(
            derive_bounds("2030-01-02T03:05-03:00", "minute"),
            ("2030-01-02T06:05:00Z", "2030-01-02T06:06:00Z"),
        )

    def test_a_positive_offset_is_normalised_backward_to_utc(self):
        self.assertEqual(
            derive_bounds("2030-01-02T09:05+02:00", "minute"),
            ("2030-01-02T07:05:00Z", "2030-01-02T07:06:00Z"),
        )

    def test_a_non_hour_positive_offset_derives_correct_bounds(self):
        """G6 — ``+05:45`` (Nepal). An hours-only implementation loses 45 minutes."""
        self.assertEqual(
            derive_bounds("2030-01-02T09:05+05:45", "minute"),
            ("2030-01-02T03:20:00Z", "2030-01-02T03:21:00Z"),
        )

    def test_a_non_hour_negative_offset_derives_correct_bounds(self):
        """G6 — ``-09:30`` (Marquesas)."""
        self.assertEqual(
            derive_bounds("2030-01-02T09:05-09:30", "minute"),
            ("2030-01-02T18:35:00Z", "2030-01-02T18:36:00Z"),
        )

    def test_utc_normalisation_rolls_the_date_forward(self):
        """G6 — a late local evening at a negative offset is the next UTC day."""
        self.assertEqual(
            derive_bounds("2030-01-02T22:05-03:00", "minute"),
            ("2030-01-03T01:05:00Z", "2030-01-03T01:06:00Z"),
        )

    def test_utc_normalisation_rolls_the_date_backward(self):
        """G6 — and an early local morning at a positive offset is the day before."""
        self.assertEqual(
            derive_bounds("2030-01-02T01:05+05:45", "minute"),
            ("2030-01-01T19:20:00Z", "2030-01-01T19:21:00Z"),
        )

    def test_the_upper_bound_rolls_the_date_when_the_minute_is_the_last_of_the_day(self):
        """``23:59`` + 60 s is tomorrow, and the year with it."""
        self.assertEqual(
            derive_bounds("2030-12-31T23:59Z", "minute"),
            ("2030-12-31T23:59:00Z", "2031-01-01T00:00:00Z"),
        )

    def test_the_interval_is_exactly_sixty_seconds_wide(self):
        """G2/D2 — never zero-width, never anything but 60 s for ``minute``."""
        lower, upper = derive_bounds("2030-01-02T03:05-03:00", "minute")
        self.assertLess(lower, upper)
        self.assertEqual(seconds_between(lower, upper), 60)

    def test_derivation_is_pure(self):
        """G2 — repeated derivation is identical, and nothing is memoised wrongly."""
        first = derive_bounds("2030-02-28T23:59+00:00", "minute")
        second = derive_bounds("2030-02-28T23:59+00:00", "minute")
        self.assertEqual(first, second)
        self.assertEqual(first, ("2030-02-28T23:59:00Z", "2030-03-01T00:00:00Z"))


class TestBoundDerivationRefusesWhatItCannotDerive(unittest.TestCase):
    """G8 — a value the contract refuses must never acquire a bound.

    ``derive_bounds`` is a public function, so "the validator has already run" is
    not a property it can rely on: a caller that skipped validation would
    otherwise get bounds for a naive value, and those bounds would be a guess at
    an offset nobody stated.
    """

    def test_an_unknown_precision_is_refused(self):
        with self.assertRaises(ValueError):
            derive_bounds("2030-01-02T03:05Z", "hour")

    def test_a_missing_precision_is_refused(self):
        with self.assertRaises(ValueError):
            derive_bounds("2030-01-02T03:05Z", None)

    def test_an_exact_value_is_refused(self):
        """D2 — seconds belong in ``event.start_time``, never in the evidence."""
        with self.assertRaises(ValueError):
            derive_bounds("2030-01-02T03:05:00Z", "minute")

    def test_a_naive_value_is_refused(self):
        with self.assertRaises(ValueError):
            derive_bounds("2030-01-02T03:05", "minute")

    def test_a_space_separated_naive_value_is_refused(self):
        """One of RFC 002 §12.2's refused shapes."""
        with self.assertRaises(ValueError):
            derive_bounds("2030-01-02 03:05", "minute")

    def test_a_zone_name_without_an_explicit_offset_is_refused(self):
        with self.assertRaises(ValueError):
            derive_bounds("2030-01-02T03:05 America/Sao_Paulo", "minute")

    def test_a_non_string_is_refused(self):
        with self.assertRaises(ValueError):
            derive_bounds(1893456300, "minute")

    def test_an_out_of_range_offset_is_refused(self):
        with self.assertRaises(ValueError):
            derive_bounds("2030-01-02T03:05+99:00", "minute")

    def test_an_out_of_range_offset_minute_is_refused(self):
        with self.assertRaises(ValueError):
            derive_bounds("2030-01-02T03:05+05:75", "minute")

    def test_an_impossible_date_is_refused(self):
        with self.assertRaises(ValueError):
            derive_bounds("2030-02-30T03:05Z", "minute")

    def test_an_impossible_hour_is_refused(self):
        with self.assertRaises(ValueError):
            derive_bounds("2030-01-02T25:05Z", "minute")


class TestDstIndependence(unittest.TestCase):
    """G7 — no timezone database is consulted, and none can be."""

    def test_bounds_at_a_dst_transition_instant_are_ordinary_fixed_offset_bounds(self):
        """2030-03-10 02:30 does not exist as US Eastern wall time — the clock
        jumps 02:00 to 03:00. At a stated fixed offset it is simply 07:30Z, and
        anything that consulted a zone database would have to disagree."""
        self.assertEqual(
            derive_bounds("2030-03-10T02:30-05:00", "minute"),
            ("2030-03-10T07:30:00Z", "2030-03-10T07:31:00Z"),
        )

    def test_the_repeated_wall_hour_of_a_fall_back_is_decided_by_the_stated_offset(self):
        """01:30 happens twice on a fall-back date. The offset says which one,
        which is exactly why the offset has to be in the value."""
        self.assertEqual(
            derive_bounds("2030-11-03T01:30-04:00", "minute"),
            ("2030-11-03T05:30:00Z", "2030-11-03T05:31:00Z"),
        )
        self.assertEqual(
            derive_bounds("2030-11-03T01:30-05:00", "minute"),
            ("2030-11-03T06:30:00Z", "2030-11-03T06:31:00Z"),
        )

    def test_the_local_timezone_of_the_process_changes_nothing(self):
        """Run the same derivation under two very different local zones. A single
        naive-to-local conversion anywhere in the path would show up here."""
        import os
        import time

        values = ("2030-03-10T02:30-05:00", "2030-07-04T12:00+05:45",
                  "2030-01-02T03:05Z")
        original = os.environ.get("TZ")
        try:
            derived = {}
            for zone in ("UTC", "America/New_York", "Pacific/Chatham"):
                os.environ["TZ"] = zone
                time.tzset()
                derived[zone] = [derive_bounds(v, "minute") for v in values]
            self.assertEqual(derived["UTC"], derived["America/New_York"])
            self.assertEqual(derived["UTC"], derived["Pacific/Chatham"])
        finally:
            if original is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original
            time.tzset()

    def test_no_timezone_database_is_importable_from_the_contract_module(self):
        """Mechanical, so it survives a refactor that reintroduces one. A
        published zero-dependency package cannot carry ``dateutil`` or
        ``pendulum``, and ``zoneinfo`` would make bounds depend on the host's
        tzdata (G7, G11)."""
        import ast

        source = (REPO_ROOT / "tools/iptc/canonical/observation.py").read_text(
            encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level:
                imported.add((node.module or "").split(".")[0])
        for banned in ("zoneinfo", "dateutil", "pendulum", "pytz", "time", "calendar"):
            self.assertNotIn(banned, imported)


class TestTheTwoAdmissibleTemporalStates(unittest.TestCase):
    """D5 — an event carries exactly one of exact or reduced, never both, never
    neither."""

    def test_an_exact_observation_is_valid_and_unchanged(self):
        self.assertEqual(validate_observation(EXACT), [])

    def test_a_reduced_observation_is_valid(self):
        self.assertEqual(validate_observation(reduced()), [])

    def test_both_states_at_once_is_a_hard_failure(self):
        """RFC 002 §12.2's "inconsistent dual assertion": two contradictory claims
        about one instant, refused rather than reconciled."""
        document = reduced()
        document["observation"]["event"]["start_time"] = "2030-01-02T03:05:00Z"
        self.assertTrue(validate_observation(document))

    def test_neither_state_is_a_hard_failure(self):
        """D8's acceptance matrix: "both exact and reduced states, or neither"
        is a refusal. An event with no timing is not an event we can place."""
        document = copy.deepcopy(EXACT)
        del document["observation"]["event"]["start_time"]
        self.assertTrue(validate_observation(document))

    def test_the_exact_field_keeps_its_seconds_requirement(self):
        """Q3/D4 — ``event.start_time`` is not widened by any of this. A minute
        value in the exact field stays exactly as invalid as it is today."""
        document = copy.deepcopy(EXACT)
        document["observation"]["event"]["start_time"] = "2030-01-02T03:05Z"
        self.assertTrue(validate_observation(document))


class TestReducedTemporalEvidenceRefusalSet(unittest.TestCase):
    """G8 — every row is a hard failure with no partial or defaulted emission."""

    #: The path every finding in this class must name.
    MEMBER = "observation.event.temporal_evidence"

    def assertRefused(self, document, *, because):
        """Refused **for the stated reason**, not merely refused.

        Asserting "some error" would let every row here pass on an unrelated
        finding — which is exactly what they did while the schema identifier was
        still unknown to the validator, and it is how a refusal set comes to be
        green against a rule nobody implemented.
        """
        errors = validate_observation(document)
        self.assertTrue(errors, "expected a hard failure: {0}".format(because))
        self.assertTrue(
            any(self.MEMBER in error for error in errors),
            "refused, but not for the stated reason ({0}); findings were: {1}".format(
                because, errors),
        )
        return errors

    def test_a_missing_precision_is_refused(self):
        self.assertRefused(reduced(precision=_ABSENT),
                           because="precision is declared, never defaulted")

    def test_an_unknown_precision_is_refused(self):
        self.assertRefused(reduced(precision="fortnight"),
                           because="the enum is closed")

    def test_hour_precision_is_refused_in_this_version(self):
        """Q6 — ``date`` and ``hour`` are deliberately outside the initial enum."""
        self.assertRefused(reduced(precision="hour", source_value="2030-01-02T03Z"),
                           because="hour is not in the minute-only enum")

    def test_second_precision_inside_the_evidence_member_is_refused(self):
        """D2 — exact values have a home, and it is ``event.start_time``."""
        self.assertRefused(
            reduced(precision="second", source_value="2030-01-02T03:05:00Z",
                    upper_exclusive="2030-01-02T03:05:00Z"),
            because="an exact value smuggled into the evidence member")

    def test_a_fractional_second_value_is_refused(self):
        self.assertRefused(reduced(source_value="2030-01-02T03:05:00.500Z"),
                           because="fractional seconds are exact")

    def test_a_naive_source_value_is_refused(self):
        self.assertRefused(reduced(source_value="2030-01-02 03:05"),
                           because="no explicit offset")

    def test_a_zone_name_only_source_value_is_refused(self):
        self.assertRefused(reduced(source_value="2030-01-02T03:05 America/Sao_Paulo"),
                           because="an offset implied by a zone name is not stated")

    def test_a_missing_source_value_is_refused(self):
        self.assertRefused(reduced(source_value=_ABSENT),
                           because="the lexical value is the observed fact")

    def test_a_duplicated_offset_field_is_refused(self):
        """D5 — the offset lives in ``source_value`` and nowhere else. A second
        field stating it is a second source of truth that can disagree."""
        self.assertRefused(reduced(utc_offset="Z"),
                           because="a duplicate offset field")

    def test_any_unknown_member_key_is_refused(self):
        """The closed key set is how "any additional offset-bearing field" is
        detected mechanically rather than by a list of field names somebody has
        to keep guessing at."""
        self.assertRefused(reduced(timezone="America/Sao_Paulo"),
                           because="an unknown key in a closed member")

    def test_a_missing_lower_bound_is_refused(self):
        self.assertRefused(reduced(lower_inclusive=_ABSENT), because="bounds absent")

    def test_a_missing_upper_bound_is_refused(self):
        self.assertRefused(reduced(upper_exclusive=_ABSENT), because="bounds absent")

    def test_a_bound_that_is_not_utc_normalised_is_refused(self):
        """``+00:00`` is the same instant and a different spelling. Two spellings
        of one bound is the drift the ``Z`` rule exists to remove."""
        self.assertRefused(reduced(lower_inclusive="2030-01-02T03:05:00+00:00"),
                           because="bounds are Z-normalized")

    def test_a_minute_precision_bound_is_refused(self):
        self.assertRefused(reduced(lower_inclusive="2030-01-02T03:05Z"),
                           because="bounds are second-precision")

    def test_a_fractional_second_bound_is_refused(self):
        self.assertRefused(reduced(lower_inclusive="2030-01-02T03:05:00.000Z"),
                           because="bounds are second-precision")

    def test_a_non_rfc3339_bound_is_refused(self):
        self.assertRefused(reduced(upper_exclusive="tomorrow"),
                           because="bounds are RFC 3339")

    def test_inverted_bounds_are_refused(self):
        self.assertRefused(
            reduced(lower_inclusive="2030-01-02T03:06:00Z",
                    upper_exclusive="2030-01-02T03:05:00Z"),
            because="lower must be strictly less than upper")

    def test_zero_width_bounds_are_refused(self):
        """D2 — a degenerate interval is not a representation, it is an accident."""
        self.assertRefused(reduced(upper_exclusive="2030-01-02T03:05:00Z"),
                           because="a zero-width interval is not an interval")

    def test_a_width_other_than_sixty_seconds_is_refused(self):
        self.assertRefused(reduced(upper_exclusive="2030-01-02T03:07:00Z"),
                           because="minute means exactly 60 s")

    def test_bounds_that_do_not_recompute_from_the_source_value_are_refused(self):
        """G2 — the derivation is auditable because it is checked, not because it
        is documented. Both bounds here are well-formed, 60 s apart, and simply
        not the interval this source value denotes."""
        self.assertRefused(
            reduced(lower_inclusive="2031-06-07T08:09:00Z",
                    upper_exclusive="2031-06-07T08:10:00Z"),
            because="bounds must be recomputable from (source_value, precision)")

    def test_bounds_derived_at_the_wrong_offset_are_refused(self):
        """The specific way a hand-written adapter gets this wrong: it copies the
        wall-clock reading and forgets to normalize."""
        self.assertRefused(
            reduced(source_value="2030-01-02T03:05-03:00",
                    lower_inclusive="2030-01-02T03:05:00Z",
                    upper_exclusive="2030-01-02T03:06:00Z"),
            because="bounds must be UTC-normalized at the stated offset")

    def test_a_missing_kind_is_refused(self):
        self.assertRefused(reduced(kind=_ABSENT),
                           because="which instant this describes is not inferable")

    def test_an_unknown_kind_is_refused(self):
        """``end`` would otherwise grant ``event.start_time.bounded`` for an
        instant that is not the start."""
        self.assertRefused(reduced(kind="end"), because="the kind enum is closed")

    def test_a_missing_derivation_provenance_is_refused(self):
        self.assertRefused(reduced(provenance=_ABSENT),
                           because="a derived value with no stated derivation")

    def test_an_unknown_derivation_is_refused(self):
        self.assertRefused(
            reduced(provenance={"derivation": "best_effort"}),
            because="there is no best-effort branch")

    def test_credential_shaped_provenance_is_refused(self):
        """D3 — provenance carries identifiers and versions only. #027's PR 2
        fixed two refusal-path leaks of credential-shaped values; nothing here
        reopens that surface."""
        errors = self.assertRefused(
            reduced(provenance={"derivation": "declared_precision_interval",
                                "normalizer": "https://api.example/x?key=abc123"}),
            because="a request- or credential-shaped provenance value")
        self.assertNotIn("abc123", " ".join(errors),
                         "the refusal republished the material it refused")

    def test_a_non_object_member_is_refused(self):
        self.assertRefused(
            {"schema_version": "canonical-observation/1.1",
             "observation": dict(EXACT["observation"],
                                 event=dict(EXACT["observation"]["event"],
                                            temporal_evidence="03:05"))},
            because="the member is an object")

    def test_nothing_is_repaired(self):
        """The module's own rule: no default is filled in and the document is
        never mutated, so an invalid document stays exactly as invalid."""
        document = reduced(precision=_ABSENT)
        before = copy.deepcopy(document)
        validate_observation(document)
        self.assertEqual(document, before)


class TestTheClosedSchemaVersionAcceptanceMatrix(unittest.TestCase):
    """D8/G15 — the validator accepts a closed set of known identifiers.

    The version identifier is the only machine-detectable signal that a reader is
    looking at the temporal-evidence contract, so it is checked as a matrix
    rather than as a branch around one constant.
    """

    def test_the_successor_is_the_emitted_identifier(self):
        self.assertEqual(canonical.SCHEMA_VERSION, "canonical-observation/1.1")

    def test_the_predecessor_is_still_named(self):
        self.assertEqual(canonical.PREDECESSOR_SCHEMA_VERSION,
                         "canonical-observation/1")

    def test_the_accepted_set_is_exactly_the_two_known_identifiers(self):
        self.assertEqual(
            tuple(canonical.ACCEPTED_SCHEMA_VERSIONS),
            ("canonical-observation/1", "canonical-observation/1.1"),
        )

    def test_predecessor_with_an_exact_instant_is_accepted(self):
        """Existing documents stay readable across the bump."""
        document = copy.deepcopy(EXACT)
        document["schema_version"] = "canonical-observation/1"
        self.assertEqual(validate_observation(document), [])

    def test_predecessor_with_temporal_evidence_is_refused(self):
        """The predecessor contract does not define that member, so a document
        carrying it under ``/1`` is validated by a contract that does not
        describe it."""
        document = reduced()
        document["schema_version"] = "canonical-observation/1"
        self.assertTrue(validate_observation(document))

    def test_predecessor_with_temporal_evidence_and_a_start_time_is_also_refused(self):
        document = reduced()
        document["schema_version"] = "canonical-observation/1"
        document["observation"]["event"]["start_time"] = "2030-01-02T03:05:00Z"
        self.assertTrue(validate_observation(document))

    def test_successor_with_an_exact_instant_is_accepted(self):
        self.assertEqual(validate_observation(EXACT), [])

    def test_successor_with_valid_minute_evidence_is_accepted(self):
        self.assertEqual(validate_observation(reduced()), [])

    def test_an_unknown_identifier_is_refused(self):
        for unknown in ("canonical-observation/2", "canonical-observation/1.2",
                        "canonical-observation", "", None):
            with self.subTest(schema_version=unknown):
                document = copy.deepcopy(EXACT)
                document["schema_version"] = unknown
                self.assertTrue(validate_observation(document))

    def test_the_refusal_names_the_accepted_set(self):
        """An error that says only "unexpected" leaves the reader to guess which
        identifiers this build knows."""
        document = copy.deepcopy(EXACT)
        document["schema_version"] = "canonical-observation/2"
        joined = " ".join(validate_observation(document))
        self.assertIn("canonical-observation/1.1", joined)
        self.assertIn("canonical-observation/1", joined)


class TestTheBoundedCapabilityName(unittest.TestCase):
    """D6 — one new name, core-tier optional, and nothing else about the
    mechanism changes."""

    def test_the_name_is_known(self):
        self.assertIn(BOUNDED, ALL_CAPABILITIES)

    def test_the_name_is_core_tier_optional(self):
        self.assertIn(BOUNDED, TIER_OPTIONAL["core"])

    def test_the_name_is_required_by_no_tier(self):
        """Making it required would knock every existing exact observation out of
        the core tier — a breaking change wearing an additive costume."""
        for tier in TIER_ORDER:
            with self.subTest(tier=tier):
                self.assertNotIn(BOUNDED, TIER_REQUIRED[tier])

    def test_there_is_no_shorthand_alias(self):
        """A second spelling of a capability name is a second vocabulary."""
        aliases = [n for n in ALL_CAPABILITIES
                   if n != BOUNDED and "bounded" in n]
        self.assertEqual(aliases, [])

    def test_the_name_is_expressible(self):
        """It has a presence rule, so it is "absent" rather than "the contract
        cannot carry it"."""
        self.assertNotIn(BOUNDED, NOT_EXPRESSIBLE)

    def test_the_exact_name_keeps_its_exact_instant_meaning(self):
        report = capability_report(EXACT)["capabilities"]
        self.assertIn("event.start_time", report["present"])
        self.assertIn(BOUNDED, report["absent"])

    def test_a_reduced_record_presents_bounded_and_absents_exact(self):
        report = capability_report(reduced())["capabilities"]
        self.assertIn(BOUNDED, report["present"])
        self.assertNotIn("event.start_time", report["present"])

    def test_invalid_evidence_does_not_present_the_capability(self):
        """A report keyed on "the key is there" would advertise a bounded start
        for a member the validator is about to reject."""
        for broken in (reduced(precision="fortnight"),
                       reduced(source_value="2030-01-02 03:05"),
                       reduced(upper_exclusive="2030-01-02T03:05:00Z"),
                       reduced(kind="end")):
            with self.subTest(evidence=broken["observation"]["event"]):
                report = capability_report(broken)["capabilities"]
                self.assertNotIn(BOUNDED, report["present"])

    def test_a_reduced_record_reports_below_core(self):
        """D6's stated consequence, asserted rather than narrated: the record has
        no exact instant, so it does not reach the core tier and says which name
        is missing."""
        report = capability_report(reduced())["capabilities"]
        self.assertIsNone(report["tier"])
        self.assertEqual(report["tiers_satisfied"], [])
        self.assertIn("event.start_time", report["by_tier"]["core"]["required_absent"])
        self.assertIn(BOUNDED, report["by_tier"]["core"]["optional_present"])


class TestConsumerOutcomes(unittest.TestCase):
    """D6's outcome table. Both cells of each row are asserted, not narrated."""

    def exact(self):
        return capability_report(EXACT)["capabilities"]

    def bounded(self):
        return capability_report(reduced())["capabilities"]

    def test_a_consumer_requiring_the_exact_instant_accepts_an_exact_record(self):
        self.assertTrue(check_compatibility(
            self.exact(), requires=("event.start_time",))["compatible"])

    def test_a_consumer_requiring_the_exact_instant_fails_closed_on_a_reduced_record(self):
        result = check_compatibility(self.bounded(), requires=("event.start_time",))
        self.assertFalse(result["compatible"])
        self.assertEqual(result["missing_required"], ["event.start_time"])

    def test_a_consumer_requiring_bounds_accepts_a_reduced_record(self):
        self.assertTrue(check_compatibility(
            self.bounded(), requires=(BOUNDED,))["compatible"])

    def test_a_consumer_requiring_bounds_fails_closed_on_an_exact_record(self):
        result = check_compatibility(self.exact(), requires=(BOUNDED,))
        self.assertFalse(result["compatible"])
        self.assertEqual(result["missing_required"], [BOUNDED])

    def test_requiring_both_names_is_satisfiable_by_neither_record(self):
        """No OR semantics are added: ``requires`` stays a flat conjunction, so a
        consumer picks one requirement set rather than listing alternatives."""
        for report in (self.exact(), self.bounded()):
            with self.subTest(report=report["tier"]):
                self.assertFalse(check_compatibility(
                    report, requires=("event.start_time", BOUNDED))["compatible"])

    def test_an_unknown_name_still_fails_closed(self):
        result = check_compatibility(self.bounded(), requires=("event.start_time.bound",))
        self.assertFalse(result["compatible"])
        self.assertEqual(result["unknown_capabilities"], ["event.start_time.bound"])


class TestGraphUnavailabilityIsReportedStructurally(unittest.TestCase):
    """D7/G14 — the omission is structured, and the reason is enumerated."""

    def test_the_reason_vocabulary_is_closed(self):
        self.assertEqual(tuple(GRAPH_UNAVAILABLE_REASONS), (EXACT_REQUIRED,))

    def test_a_reduced_record_states_the_reason(self):
        report = capability_report(reduced())["capabilities"]
        self.assertEqual(report["graph_unavailable_reason"], EXACT_REQUIRED)

    def test_the_reason_is_an_enumerated_value_never_free_text(self):
        report = capability_report(reduced())["capabilities"]
        self.assertIn(report["graph_unavailable_reason"], GRAPH_UNAVAILABLE_REASONS)

    def test_an_exact_record_carries_no_such_key_at_all(self):
        """Omission over fabrication, and the reason it must be omission: a key
        present on every exact record would be a fifth item in D8's enumerated
        exact-observation diff."""
        self.assertNotIn("graph_unavailable_reason",
                         capability_report(EXACT)["capabilities"])


def mint():
    return surrogate_resolver("sports-skills/espn")


class TestGraphRefusalIsDeterministicAndStructured(unittest.TestCase):
    """D7/G14 — a reduced-precision observation emits no graph at all."""

    def test_a_direct_graph_request_raises_the_structured_refusal(self):
        with self.assertRaises(GraphUnavailable) as caught:
            sport_schema_graph(reduced(), id_resolver=mint())
        self.assertEqual(caught.exception.reason, EXACT_REQUIRED)

    def test_the_refusal_is_deterministic(self):
        """Same input, same refusal, every time — not an error that depends on
        which resource happened to be built first."""
        reasons = []
        for _ in range(3):
            try:
                sport_schema_graph(reduced(), id_resolver=mint())
            except GraphUnavailable as error:
                reasons.append(error.reason)
        self.assertEqual(reasons, [EXACT_REQUIRED] * 3)

    def test_the_refusal_is_not_an_unstructured_error(self):
        """A bare ``ValueError`` would force a consumer to match on message text.
        It stays a ``ValueError`` subclass so existing callers still catch it."""
        self.assertTrue(issubclass(GraphUnavailable, ValueError))

    def test_the_reason_token_travels_in_the_message_too(self):
        """So a log line that only carries ``str(error)`` still names the reason."""
        with self.assertRaises(GraphUnavailable) as caught:
            sport_schema_graph(reduced(), id_resolver=mint())
        self.assertIn(EXACT_REQUIRED, str(caught.exception))

    def test_no_empty_graph_is_returned_instead(self):
        """"Return ``{"@graph": []}``" is the failure mode this replaces: it
        looks like a conformant document that happens to describe nothing."""
        try:
            result = sport_schema_graph(reduced(), id_resolver=mint())
        except GraphUnavailable:
            return
        self.fail("returned a graph instead of refusing: {0}".format(result))

    def test_a_member_that_is_present_but_invalid_is_also_refused(self):
        """Fail closed: the rule is "this document carries the member", not
        "this document carries a member I could validate"."""
        with self.assertRaises(GraphUnavailable):
            sport_schema_graph(reduced(precision="fortnight"), id_resolver=mint())

    def test_the_exact_path_still_emits_the_graph_and_its_start_datetime(self):
        """D4 — exact observations project exactly as they do today."""
        graph = sport_schema_graph(EXACT, id_resolver=mint())
        events = [n for n in graph["@graph"] if n.get("@type") == "sport:Event"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["sport:startDateTime"],
                         {"@value": "2030-01-02T03:05:00Z", "@type": "xsd:dateTime"})


class TestTheEnvelopeUnderReducedPrecision(unittest.TestCase):
    """D7 — ``event_view`` normally, ``sport_schema_graph`` omitted."""

    def setUp(self):
        self.envelope = canonical_envelope(
            reduced(), id_resolver=mint())["machina_sports_schema"]

    def test_the_graph_member_is_absent_not_empty(self):
        self.assertNotIn("sport_schema_graph", self.envelope)

    def test_no_machina_temporal_resource_reaches_any_graph(self):
        """Explicitly excluded from this version: a ``machina:`` temporal
        property inside the interoperability document is the invented-precision
        leak one namespace over."""
        serialized = str(self.envelope)
        for banned in ("startDateTime", "temporalEvidence", "machina:lowerInclusive",
                       "machina:startBound"):
            with self.subTest(term=banned):
                self.assertNotIn(banned, serialized)

    def test_the_event_view_is_emitted_normally(self):
        self.assertIn("event_view", self.envelope)
        self.assertEqual(self.envelope["event_view"]["status"], "closed")

    def test_the_view_carries_no_start_time_key(self):
        """There is no exact instant, so there is no key asserting one."""
        self.assertNotIn("start_time", self.envelope["event_view"])

    def test_the_capability_report_states_the_reason(self):
        self.assertEqual(self.envelope["capabilities"]["graph_unavailable_reason"],
                         EXACT_REQUIRED)

    def test_provenance_provider_ids_and_rights_are_still_emitted(self):
        for member in ("provenance", "provider_ids", "rights"):
            with self.subTest(member=member):
                self.assertIn(member, self.envelope)


class TestSourceFidelityRoundTrip(unittest.TestCase):
    """G1 — the lexical value and its precision survive read-back unchanged."""

    def view(self):
        return event_view(reduced(), id_resolver=mint())["event_view"]

    def test_the_view_carries_the_evidence(self):
        self.assertIn("temporal_evidence", self.view())

    def test_the_source_value_survives_byte_for_byte_with_its_offset(self):
        document = reduced(source_value="2030-01-02T03:05-03:00",
                           lower_inclusive="2030-01-02T06:05:00Z",
                           upper_exclusive="2030-01-02T06:06:00Z")
        evidence = event_view(document, id_resolver=mint())[
            "event_view"]["temporal_evidence"]
        self.assertEqual(evidence["source_value"], "2030-01-02T03:05-03:00")
        self.assertEqual(evidence["precision"], "minute")

    def test_the_bounds_travel_with_it(self):
        evidence = self.view()["temporal_evidence"]
        self.assertEqual(evidence["lower_inclusive"], "2030-01-02T03:05:00Z")
        self.assertEqual(evidence["upper_exclusive"], "2030-01-02T03:06:00Z")

    def test_the_derivation_provenance_travels_with_it(self):
        self.assertEqual(self.view()["temporal_evidence"]["provenance"]["derivation"],
                         "declared_precision_interval")

    def test_it_survives_a_json_round_trip(self):
        """Serialization and read-back, not just a dict comparison: this is the
        boundary the contract actually crosses."""
        import json

        before = reduced(source_value="2030-01-02T03:05+05:45",
                         lower_inclusive="2030-01-01T21:20:00Z",
                         upper_exclusive="2030-01-01T21:21:00Z")
        after = json.loads(json.dumps(canonical_envelope(before, id_resolver=mint())))
        evidence = after["machina_sports_schema"]["event_view"]["temporal_evidence"]
        self.assertEqual(evidence,
                         before["observation"]["event"]["temporal_evidence"])

    def test_the_offset_is_stored_in_exactly_one_place(self):
        """G1 — no offset lives anywhere but inside ``source_value``. A second
        copy is a second source of truth that can disagree with the first."""
        import json
        import re

        document = reduced(source_value="2030-01-02T03:05-03:00",
                           lower_inclusive="2030-01-02T06:05:00Z",
                           upper_exclusive="2030-01-02T06:06:00Z")
        envelope = json.dumps(canonical_envelope(document, id_resolver=mint()))
        self.assertEqual(len(re.findall(r"-03:00", envelope)), 1)

    def test_the_exact_view_still_carries_start_time_and_no_evidence(self):
        view = event_view(EXACT, id_resolver=mint())["event_view"]
        self.assertEqual(view["start_time"], "2030-01-02T03:05:00Z")
        self.assertNotIn("temporal_evidence", view)


FIXTURES = REPO_ROOT / "tools/iptc/fixtures"
BASELINE_DIGESTS = json.loads(
    (FIXTURES / "exact-observation-0.1.0-digests.json").read_text(encoding="utf-8"))

#: The exact-observation diff, item by item, as RFC 002 §12.3 enumerates it. Item 1 is
#: about the adapter-produced *input* document and is asserted separately; items
#: 2-4 are envelope changes and are what :func:`as_0_1_0` undoes.
D8_ENVELOPE_ITEMS = (
    ("machina_sports_schema.profile", "machina-iptc-profile/1.2"),
    ("machina_sports_schema.capabilities.absent", BOUNDED),
    ("machina_sports_schema.capabilities.by_tier.core.optional_absent", BOUNDED),
)


def serialized(document):
    """The exact bytes a corrected fixture is checked in as."""
    return json.dumps(document, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def as_0_1_0(envelope):
    """``envelope`` with every intentional version-bearing change undone.

    Mechanical and total: if undoing exactly these produces the 0.1.0 bytes, then
    nothing else in the document changed. That is the whole of G3, and it is why
    this reconstruction is deliberately dumb — every line here is a diff item a
    reviewer can count.
    """
    block = copy.deepcopy(envelope)["machina_sports_schema"]
    block["profile"] = "machina-iptc-profile/1.1"
    # The fifth difference, and the one RFC 002 §12.3 does not enumerate: the
    # provenance block restates the profile it claims conformance to. See
    # TestTheUnenumeratedProvenanceProfileDifference below.
    block["provenance"]["profile"] = "machina-iptc-profile/1.1"
    capabilities = block["capabilities"]
    capabilities["absent"] = [n for n in capabilities["absent"] if n != BOUNDED]
    core = capabilities["by_tier"]["core"]
    core["optional_absent"] = [n for n in core["optional_absent"] if n != BOUNDED]
    return {"machina_sports_schema": block}


def built_envelope(observation_name):
    """The envelope this build produces for a checked-in observation fixture."""
    document = json.loads(
        (FIXTURES / "observations" / observation_name).read_text(encoding="utf-8"))
    namespace = document["observation"]["provider"]["namespace"]
    return canonical_envelope(document, id_resolver=surrogate_resolver(namespace))


#: ``observation fixture -> corrected envelope fixture``. Named rather than
#: derived from the filenames: two of the eight do not share a stem, and a
#: pairing rule that guessed would silently compare the wrong pair.
EXACT_PAIRS = (
    ("api-football-soccer-observation.json", "api-football-soccer-envelope.json"),
    ("mapping-contract-synthetic-observation.json",
     "mapping-contract-synthetic-envelope.json"),
    ("sportradar-mlb-observation.json", "sportradar-mlb-envelope.json"),
    ("sportradar-nfl-observation.json", "sportradar-nfl-envelope.json"),
    ("sportradar-soccer-observation.json", "sportradar-soccer-envelope.json"),
    ("sportradar-tennis-observation.json", "sportradar-tennis-envelope.json"),
    ("sports-skills-espn-soccer-observation.json",
     "sports-skills-espn-soccer-envelope.json"),
    ("stats-perform-opta-soccer-observation.json",
     "stats-perform-opta-soccer-envelope.json"),
)


class TestExactObservationDiffIsExactlyTheEnumeratedItems(unittest.TestCase):
    """G3 — for every existing exact fixture, the only differences from
    ``machina-sports-canonical`` 0.1.0 are the enumerated ones.

    Stated as an enumerated diff rather than as a blanket byte-identity claim,
    because a blanket claim is false the moment a version identifier is bumped.
    """

    def test_the_baseline_covers_every_corrected_envelope(self):
        """A fixture with no recorded 0.1.0 digest is a fixture this gate skips,
        and a silently skipped gate is worse than an absent one."""
        self.assertEqual(sorted(BASELINE_DIGESTS["envelopes"]),
                         sorted(envelope for _, envelope in EXACT_PAIRS))

    def test_undoing_the_enumerated_items_reproduces_the_0_1_0_bytes(self):
        """The gate. ``sport_schema_graph``, ``event_view``, ``provenance``,
        ``provider_ids`` and ``rights`` diff empty, for all eight, or this
        fails."""
        for observation_name, envelope_name in EXACT_PAIRS:
            with self.subTest(fixture=envelope_name):
                rebuilt = serialized(as_0_1_0(built_envelope(observation_name)))
                self.assertEqual(
                    hashlib.sha256(rebuilt.encode("utf-8")).hexdigest(),
                    BASELINE_DIGESTS["envelopes"][envelope_name],
                    "a difference outside the enumerated diff is a regression, "
                    "not a version artifact",
                )

    def test_item_1_the_input_document_declares_the_successor(self):
        for observation_name, _ in EXACT_PAIRS:
            with self.subTest(fixture=observation_name):
                document = json.loads((FIXTURES / "observations" / observation_name)
                                      .read_text(encoding="utf-8"))
                self.assertEqual(document["schema_version"],
                                 "canonical-observation/1.1")

    def test_item_2_the_envelope_declares_profile_1_2(self):
        envelope = built_envelope(EXACT_PAIRS[0][0])["machina_sports_schema"]
        self.assertEqual(envelope["profile"], "machina-iptc-profile/1.2")

    def test_item_3_the_absent_set_gains_the_bounded_name(self):
        envelope = built_envelope(EXACT_PAIRS[0][0])["machina_sports_schema"]
        self.assertIn(BOUNDED, envelope["capabilities"]["absent"])

    def test_item_4_the_core_optional_absent_list_gains_the_bounded_name(self):
        envelope = built_envelope(EXACT_PAIRS[0][0])["machina_sports_schema"]
        self.assertIn(
            BOUNDED,
            envelope["capabilities"]["by_tier"]["core"]["optional_absent"])

    def test_the_envelope_identifier_itself_is_unchanged(self):
        """The envelope gains no member for an exact observation, so its own
        contract identifier does not move."""
        envelope = built_envelope(EXACT_PAIRS[0][0])["machina_sports_schema"]
        self.assertEqual(envelope["schema_version"], "machina-sports-schema/1")

    def test_a_soccer_fixture_is_among_them(self):
        """G5 — at least one soccer second-precision fixture passes on the same
        code path under this rule."""
        soccer = [name for name, _ in EXACT_PAIRS if "soccer" in name]
        self.assertTrue(soccer)
        for name in soccer:
            with self.subTest(fixture=name):
                document = json.loads((FIXTURES / "observations" / name)
                                      .read_text(encoding="utf-8"))
                self.assertEqual(document["observation"]["sport"]["key"], "soccer")
                self.assertEqual(validate_observation(document), [])


class TestTheUnenumeratedProvenanceProfileDifference(unittest.TestCase):
    """A fifth intentional difference RFC 002 §12.3 does not list, gated here so it is
    recorded rather than silent.

    D8 says ``provenance`` is byte-identical for exact observations. It cannot
    be: ``provenance_block`` restates the profile the document claims conformance
    to, so bumping the profile necessarily bumps it there too. The alternative —
    freezing that one field at 1.1 — would make the package emit a conformance
    claim to a profile it no longer implements, and put two disagreeing spellings
    of one fact in one document.

    D4's own wording covers it ("what does change is limited to explicitly
    version-bearing metadata"); D8's "byte-identical" sentence is the over-broad
    restatement. Recorded for the step-2 review to rule on.
    """

    def test_the_provenance_block_restates_the_profile(self):
        envelope = built_envelope(EXACT_PAIRS[0][0])["machina_sports_schema"]
        self.assertEqual(envelope["provenance"]["profile"], "machina-iptc-profile/1.2")

    def test_it_agrees_with_the_envelope_it_travels_in(self):
        """The property that makes this the right call: one document, one profile
        claim, never two spellings that can disagree."""
        envelope = built_envelope(EXACT_PAIRS[0][0])["machina_sports_schema"]
        self.assertEqual(envelope["provenance"]["profile"], envelope["profile"])

    def test_it_is_the_only_other_place_the_profile_is_stated(self):
        envelope = built_envelope(EXACT_PAIRS[0][0])
        blob = json.dumps(envelope)
        self.assertEqual(blob.count("machina-iptc-profile/1.2"), 2)


#: The two checked-in reduced-precision fixtures, and the receipt each one's
#: refusal is recorded as. Both are **synthetic** and say so in their own bytes:
#: no provider payload was retrieved to build either, and neither is evidence
#: about a feed.
#:
#: Two sports rather than one, because provider-neutrality is the claim. The
#: defect was found on a basketball feed, but nothing about it is basketball-
#: shaped: any provider publishing schedules at minute granularity hits it the
#: moment its normalizer stops inventing a second-of-minute. The soccer row
#: carries a non-``Z`` offset so the fixture corpus exercises offset
#: normalization on the same code path rather than only in unit tests.
REDUCED_FIXTURES = (
    ("nba-reduced-precision-synthetic-observation.json",
     "nba-reduced-precision-synthetic-envelope.json", "basketball", "Z"),
    ("soccer-reduced-precision-synthetic-observation.json",
     "soccer-reduced-precision-synthetic-envelope.json", "soccer", "-03:00"),
)


def reduced_fixture(name):
    return json.loads(
        (FIXTURES / "observations" / name).read_text(encoding="utf-8"))


class TestReducedPrecisionFixtures(unittest.TestCase):
    """The reduced case, proven on checked-in bytes rather than on dicts built
    inside the suite that asserts them."""

    def test_both_fixtures_exist_and_validate(self):
        for observation_name, _, _, _ in REDUCED_FIXTURES:
            with self.subTest(fixture=observation_name):
                self.assertEqual(
                    validate_observation(reduced_fixture(observation_name)), [])

    def test_both_declare_the_successor_identifier(self):
        for observation_name, _, _, _ in REDUCED_FIXTURES:
            with self.subTest(fixture=observation_name):
                self.assertEqual(reduced_fixture(observation_name)["schema_version"],
                                 "canonical-observation/1.1")

    def test_both_are_obviously_synthetic_in_their_own_bytes(self):
        """A fixture a reader could mistake for a captured provider payload is a
        fixture that will eventually be cited as evidence about a provider."""
        for observation_name, _, _, _ in REDUCED_FIXTURES:
            with self.subTest(fixture=observation_name):
                document = reduced_fixture(observation_name)
                blob = json.dumps(document).lower()
                self.assertIn("synthetic", blob)
                self.assertIn("synthetic",
                              document["observation"]["provider"]["namespace"])

    def test_each_covers_the_sport_it_claims(self):
        for observation_name, _, sport, _ in REDUCED_FIXTURES:
            with self.subTest(fixture=observation_name):
                self.assertEqual(
                    reduced_fixture(observation_name)["observation"]["sport"]["key"],
                    sport)

    def test_the_two_sports_are_distinct(self):
        """Provider-neutrality is proven, not asserted: one sport twice would
        prove nothing about the second."""
        sports = {sport for _, _, sport, _ in REDUCED_FIXTURES}
        self.assertEqual(len(sports), len(REDUCED_FIXTURES))

    def test_each_carries_the_offset_it_claims_verbatim(self):
        for observation_name, _, _, offset in REDUCED_FIXTURES:
            with self.subTest(fixture=observation_name):
                evidence = (reduced_fixture(observation_name)["observation"]
                            ["event"]["temporal_evidence"])
                self.assertTrue(evidence["source_value"].endswith(offset))

    def test_at_least_one_carries_a_non_utc_offset(self):
        """A corpus that only ever says ``Z`` never exercises normalization."""
        self.assertTrue(any(offset != "Z" for _, _, _, offset in REDUCED_FIXTURES))

    def test_each_ones_bounds_are_recomputable_from_its_own_source_value(self):
        for observation_name, _, _, _ in REDUCED_FIXTURES:
            with self.subTest(fixture=observation_name):
                evidence = (reduced_fixture(observation_name)["observation"]
                            ["event"]["temporal_evidence"])
                lower, upper = derive_bounds(evidence["source_value"],
                                             evidence["precision"])
                self.assertEqual(evidence["lower_inclusive"], lower)
                self.assertEqual(evidence["upper_exclusive"], upper)
                self.assertEqual(seconds_between(lower, upper), 60)

    def test_neither_carries_an_exact_start_time(self):
        for observation_name, _, _, _ in REDUCED_FIXTURES:
            with self.subTest(fixture=observation_name):
                event = reduced_fixture(observation_name)["observation"]["event"]
                self.assertNotIn("start_time", event)

    def test_each_presents_the_bounded_capability_and_absents_the_exact_one(self):
        for observation_name, _, _, _ in REDUCED_FIXTURES:
            with self.subTest(fixture=observation_name):
                report = capability_report(
                    reduced_fixture(observation_name))["capabilities"]
                self.assertIn(BOUNDED, report["present"])
                self.assertNotIn("event.start_time", report["present"])

    def test_each_refuses_a_direct_graph_request_with_the_same_token(self):
        for observation_name, _, _, _ in REDUCED_FIXTURES:
            with self.subTest(fixture=observation_name):
                document = reduced_fixture(observation_name)
                namespace = document["observation"]["provider"]["namespace"]
                with self.assertRaises(GraphUnavailable) as caught:
                    sport_schema_graph(
                        document, id_resolver=surrogate_resolver(namespace))
                self.assertEqual(caught.exception.reason, EXACT_REQUIRED)


class TestReducedPrecisionEnvelopeReceipts(unittest.TestCase):
    """The checked-in envelope is the refusal receipt: it records, in bytes, that
    the graph was withheld and why."""

    def envelopes(self):
        for observation_name, envelope_name, _, _ in REDUCED_FIXTURES:
            document = reduced_fixture(observation_name)
            namespace = document["observation"]["provider"]["namespace"]
            built = canonical_envelope(
                document, id_resolver=surrogate_resolver(namespace))
            checked_in = json.loads(
                (FIXTURES / "corrected" / envelope_name).read_text(encoding="utf-8"))
            yield envelope_name, built, checked_in

    def test_each_checked_in_envelope_is_reproducible_byte_for_byte(self):
        for envelope_name, built, _ in self.envelopes():
            with self.subTest(fixture=envelope_name):
                self.assertEqual(
                    serialized(built),
                    (FIXTURES / "corrected" / envelope_name).read_text(
                        encoding="utf-8"))

    def test_no_checked_in_envelope_carries_a_graph(self):
        for envelope_name, _, checked_in in self.envelopes():
            with self.subTest(fixture=envelope_name):
                self.assertNotIn("sport_schema_graph",
                                 checked_in["machina_sports_schema"])

    def test_each_records_the_enumerated_reason(self):
        for envelope_name, _, checked_in in self.envelopes():
            with self.subTest(fixture=envelope_name):
                self.assertEqual(
                    checked_in["machina_sports_schema"]["capabilities"]
                    ["graph_unavailable_reason"],
                    EXACT_REQUIRED)

    def test_each_claims_profile_1_2(self):
        for envelope_name, _, checked_in in self.envelopes():
            with self.subTest(fixture=envelope_name):
                self.assertEqual(
                    checked_in["machina_sports_schema"]["profile"],
                    "machina-iptc-profile/1.2")

    def test_each_carries_the_bounds_in_the_event_view(self):
        for envelope_name, _, checked_in in self.envelopes():
            with self.subTest(fixture=envelope_name):
                view = checked_in["machina_sports_schema"]["event_view"]
                self.assertIn("temporal_evidence", view)
                self.assertNotIn("start_time", view)

    def test_no_iptc_start_datetime_survives_anywhere_in_either_receipt(self):
        """The whole point of the refusal: no invented instant reaches an
        interoperability document, and no ``machina:`` substitute either."""
        for envelope_name, _, checked_in in self.envelopes():
            with self.subTest(fixture=envelope_name):
                blob = json.dumps(checked_in)
                self.assertNotIn("startDateTime", blob)
                self.assertNotIn("@graph", blob)

    def test_both_run_the_same_code_path_as_the_exact_fixtures(self):
        """Same entry point, same resolver construction, same serializer — the
        reduced case is a branch inside the contract, not a parallel pipeline."""
        for _, built, _ in self.envelopes():
            block = built["machina_sports_schema"]
            with self.subTest(namespace=block["provenance"]["provider"]["namespace"]):
                self.assertEqual(block["schema_version"], "machina-sports-schema/1")
                self.assertEqual(sorted(block), [
                    "capabilities", "event_view", "profile", "provenance",
                    "provider_ids", "rights", "schema_version",
                ])


def seconds_between(lower: str, upper: str) -> float:
    """Width of ``[lower, upper)`` in seconds, parsed independently of the code
    under test — a helper that reused ``derive_bounds`` would prove nothing."""
    import datetime

    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (datetime.datetime.strptime(upper, fmt)
            - datetime.datetime.strptime(lower, fmt)).total_seconds()


if __name__ == "__main__":
    unittest.main(verbosity=2)
