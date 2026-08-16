"""Fight Analytics REST API v2 fight -> ``canonical-observation/1.1``.

The input is a ``GetOneFightDto``-shaped object from ``GET /fights/{id}``.
Fight Analytics supplies the hosting card as ``event`` and the two athletes as
``redCorner`` and ``blueCorner``.  The card is the canonical competition and the
bout is the canonical event.

This adapter fails closed where the provider does not state enough information:

* a terminal ``result`` is evidence that a bout is closed, but
  ``NOT_AVAILABLE_YET`` is not evidence that it is merely not started;
* the documented event date and clock time have no UTC offset, so they cannot be
  represented by the canonical temporal contract unless the time actually
  carries ``Z`` or ``+/-HH:MM``; and
* ``winner`` is unconstrained provider text, so outcomes are emitted only for a
  draw result or when it exactly names one corner's provider identifier.

Fighter career totals and measurements describe the athlete, not participation
in this bout, and therefore remain only in ``raw``.  The source payload is never
modified.  This module is Python 3.9-compatible, standard-library only, and does
not import repository-local packages or tools.
"""

from __future__ import annotations

import datetime
import re

import machina_sports_canonical
from machina_sports_canonical import SCHEMA_VERSION
from machina_sports_canonical.ids import surrogate_resolver
from machina_sports_canonical.serialize import canonical_envelope


ADAPTER_NAME = "connectors.fight_analytics.fight_analytics_adapter"
ADAPTER_VERSION = "1"
PROVIDER_NAMESPACE = "fight-analytics"
PROVIDER_FAMILY = "licensed"
RIGHTS_DATA_CLASS = "licensed-provider-example-fixture"

ENDPOINT_CLASS = "fight-analytics/fights"


# Every code is backed by a concept in the repository's pinned IPTC MediaTopic
# vocabulary.  The broad martial-arts concept is used only where the pin has no
# narrower Muay Thai or submission-grappling concept; the provider detail remains
# available in ``sport.key`` and ``raw``.
SPORT_BY_CODE = {
    "MMA": ("20001231", "mma"),
    "BOXING": ("20000856", "boxing"),
    "KICKBOXING": ("20001310", "kickboxing"),
    "MUAY_THAI": ("20001157", "muay-thai"),
    "WRESTLING": ("20001098", "wrestling"),
    "SUBMISSION": ("20001157", "submission"),
    "SUBMISSION_GRAPPLING": ("20001157", "submission-grappling"),
}


EVENT_STATUS_BY_CODE = {
    "SCHEDULED": "not_started",
    "NOT_STARTED": "not_started",
    "UPCOMING": "not_started",
    "LIVE": "in_progress",
    "IN_PROGRESS": "in_progress",
    "COMPLETED": "closed",
    "COMPLETE": "closed",
    "FINISHED": "closed",
    "CLOSED": "closed",
    "POSTPONED": "postponed",
    "CANCELLED": "cancelled",
    "CANCELED": "cancelled",
    "SUSPENDED": "suspended",
    "ABANDONED": "abandoned",
    "DELAYED": "delayed",
    "RESCHEDULED": "rescheduled",
}


TERMINAL_RESULTS = frozenset({
    "DRAW",
    "MAJORITY_DECISION",
    "MAJORITY_DRAW",
    "NO_CONTEST",
    "SPLIT_DECISION",
    "SUBMISSION",
    "SUBMISSION_ATTP",
    "TKO",
    "KO",
    "UNANIMOUS_DECISION",
    "POINTS",
    "PIN_FALL",
    "DEFAULT",
    "FORFEIT",
    "DQ",
    "TECHNICAL_FALL",
    "TECHNICAL_SUPERIORITY",
    "INJURY",
})
DRAW_RESULTS = frozenset({"DRAW", "MAJORITY_DRAW"})
OUTCOME_TYPE_BY_RESULT = {
    "MAJORITY_DECISION": "authority_decision",
    "SPLIT_DECISION": "authority_decision",
    "POINTS": "authority_decision",
    "UNANIMOUS_DECISION": "unanimous_decision",
}


CARD_NAME_BY_CODE = {
    "MAIN": "Main card",
    "PRELIMINARY": "Preliminary card",
}


_PLACEHOLDERS = frozenset({
    "",
    "unknown",
    "unk",
    "tbd",
    "n/a",
    "not available yet",
    "not finished yet",
    "unknown player",
    "unknown team",
    "unknown venue",
    "unknown city",
    "unknown country",
    "unknown competition",
    "unknown season",
    "unknown round",
    "unknown phase",
    "unknown category",
    "unknown group",
    "unknown channel",
    "unknown title",
})

_EXACT_DATETIME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})"
    r"(?:\.\d+)?(?:[Zz]|([+-])(\d{2}):(\d{2}))$"
)
_MINUTE_DATETIME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2})"
    r"(?:[Zz]|([+-])(\d{2}):(\d{2}))$"
)
_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_TIME_WITH_OFFSET_RE = re.compile(
    r"^(\d{1,2}):(\d{2})(?::(\d{2})(\.\d+)?)?\s*"
    r"(AM|PM)?\s*([Zz]|[+-]\d{2}:\d{2})$",
    re.IGNORECASE,
)


def _section(node, key):
    value = node.get(key) if isinstance(node, dict) else None
    return value if isinstance(value, dict) else {}


def _text(value):
    """Return a non-placeholder scalar as text, otherwise ``None``."""
    if value is None or isinstance(value, (bool, dict, list, tuple, set)):
        return None
    text = value.strip() if isinstance(value, str) else str(value)
    if not text or text.casefold() in _PLACEHOLDERS:
        return None
    return text


def _put(node, key, value):
    """Set ``key`` only when ``value`` is an observed fact."""
    if value is not None:
        node[key] = value


def _code(value):
    text = _text(value)
    if text is None:
        return None
    return re.sub(r"[^A-Z0-9]+", "_", text.upper()).strip("_")


def _required_text(value, path):
    text = _text(value)
    if text is None:
        raise ValueError(
            "Fight Analytics payload has no usable {0}; no observation was "
            "produced".format(path)
        )
    return text


def _coherent_id(embedded, embedded_key, payload, reference_key, entity):
    """Return one provider ID, refusing contradictory embedded/reference IDs."""
    embedded_id = _text(embedded.get(embedded_key))
    reference_id = _text(payload.get(reference_key))
    if (embedded_id is not None and reference_id is not None
            and embedded_id != reference_id):
        raise ValueError(
            "Fight Analytics {0} identifiers disagree between {1} and {2}; no "
            "observation was produced".format(entity, embedded_key, reference_key)
        )
    provider_id = embedded_id or reference_id
    if provider_id is None:
        raise ValueError(
            "Fight Analytics payload has no provider identifier for {0}; no "
            "observation was produced".format(entity)
        )
    return provider_id


def _sport(payload):
    code = _code(payload.get("sport"))
    if code is None:
        raise ValueError(
            "Fight Analytics payload has no fight sport; no observation was "
            "produced"
        )
    mapped = SPORT_BY_CODE.get(code)
    if mapped is None:
        raise ValueError(
            "Fight Analytics sport '{0}' has no pinned IPTC MediaTopic mapping "
            "in this adapter; no observation was produced".format(code)
        )
    medtop, key = mapped
    return {"medtop": medtop, "key": key}


def _result_code(payload):
    code = _code(payload.get("result"))
    return None if code == "NOT_AVAILABLE_YET" else code


def _explicit_status(payload, event):
    stated = []
    for value in (payload.get("status"), event.get("status")):
        code = _code(value)
        if code is None:
            continue
        if code not in EVENT_STATUS_BY_CODE:
            raise ValueError(
                "Fight Analytics status '{0}' has no canonical event-status "
                "mapping in this adapter; no observation was produced".format(code)
            )
        stated.append(EVENT_STATUS_BY_CODE[code])
    if len(set(stated)) > 1:
        raise ValueError(
            "Fight Analytics top-level and embedded event statuses disagree; no "
            "observation was produced"
        )
    return stated[0] if stated else None


def _event_status(payload, event, result_code):
    explicit = _explicit_status(payload, event)
    terminal = result_code in TERMINAL_RESULTS
    if explicit is not None:
        if terminal and explicit != "closed":
            raise ValueError(
                "Fight Analytics payload states a terminal result and a non-closed "
                "status; no observation was produced"
            )
        return explicit
    if terminal:
        return "closed"
    raise ValueError(
        "Fight Analytics payload has neither a mapped status nor a terminal "
        "result, so canonical event status cannot be determined; no observation "
        "was produced"
    )


def _valid_calendar(groups, has_seconds):
    values = [int(value) for value in groups[:6 if has_seconds else 5]]
    if not has_seconds:
        values.append(0)
    try:
        datetime.datetime(*values)
    except ValueError:
        return False
    return True


def _offset_is_valid(match, exact):
    offset_hour = match.group(8 if exact else 7)
    offset_minute = match.group(9 if exact else 8)
    return (offset_hour is None
            or (int(offset_hour) <= 23 and int(offset_minute) <= 59))


def _temporal_kind(value):
    """Return ``exact`` or ``minute`` for an admissible RFC 3339 value."""
    exact = _EXACT_DATETIME_RE.match(value)
    if exact is not None:
        if _valid_calendar(exact.groups(), True) and _offset_is_valid(exact, True):
            return "exact"
        return None
    minute = _MINUTE_DATETIME_RE.match(value)
    if minute is not None:
        if (_valid_calendar(minute.groups(), False)
                and _offset_is_valid(minute, False)):
            return "minute"
    return None


def _utc_instant(moment):
    return "{0:04d}-{1:02d}-{2:02d}T{3:02d}:{4:02d}:{5:02d}Z".format(
        moment.year,
        moment.month,
        moment.day,
        moment.hour,
        moment.minute,
        moment.second,
    )


def _minute_evidence(source_value):
    match = _MINUTE_DATETIME_RE.match(source_value)
    values = [int(value) for value in match.groups()[:5]]
    local = datetime.datetime(*values)
    sign, offset_hour, offset_minute = match.group(6), match.group(7), match.group(8)
    if offset_hour is None:
        offset = datetime.timedelta(0)
    else:
        offset = datetime.timedelta(
            hours=int(offset_hour), minutes=int(offset_minute)
        )
        if sign == "-":
            offset = -offset
    lower = local - offset
    upper = lower + datetime.timedelta(minutes=1)
    return {
        "kind": "start",
        "source_value": source_value,
        "precision": "minute",
        "lower_inclusive": _utc_instant(lower),
        "upper_exclusive": _utc_instant(upper),
        "provenance": {"derivation": "declared_precision_interval"},
    }


def _temporal_member(value, path):
    text = _text(value)
    kind = _temporal_kind(text) if text is not None else None
    if kind == "exact":
        return "start_time", text
    if kind == "minute":
        return "temporal_evidence", _minute_evidence(text)
    raise ValueError(
        "Fight Analytics {0} is not an RFC 3339 start value with an explicit "
        "offset; no observation was produced".format(path)
    )


def _split_event_start(event):
    date_text = _text(event.get("date"))
    time_text = _text(event.get("time"))
    if date_text is None or time_text is None:
        raise ValueError(
            "Fight Analytics event has no complete start date and time; no "
            "observation was produced"
        )
    date_match = _DATE_RE.match(date_text)
    time_match = _TIME_WITH_OFFSET_RE.match(time_text)
    if date_match is None or time_match is None:
        raise ValueError(
            "Fight Analytics event.date/event.time does not state a complete "
            "RFC 3339-compatible time with an explicit offset; no observation "
            "was produced"
        )

    year, month, day = (int(value) for value in date_match.groups())
    hour, minute = int(time_match.group(1)), int(time_match.group(2))
    second = time_match.group(3)
    fraction = time_match.group(4) or ""
    am_pm = time_match.group(5)
    offset = time_match.group(6).upper()

    if am_pm is not None:
        if not 1 <= hour <= 12:
            raise ValueError(
                "Fight Analytics event.time has an invalid 12-hour clock value; "
                "no observation was produced"
            )
        hour = hour % 12 + (12 if am_pm.upper() == "PM" else 0)
    try:
        datetime.datetime(year, month, day, hour, minute, int(second or 0))
    except ValueError as error:
        raise ValueError(
            "Fight Analytics event date/time is not a real calendar value; no "
            "observation was produced"
        ) from error

    if second is None:
        normalized = "{0}T{1:02d}:{2:02d}{3}".format(date_text, hour, minute, offset)
    else:
        normalized = "{0}T{1:02d}:{2:02d}:{3:02d}{4}{5}".format(
            date_text, hour, minute, int(second), fraction, offset
        )
    return _temporal_member(normalized, "event.date/event.time")


def _event_start(event):
    # Some deployments expose a normalized start field even though the published
    # GetOneFightDto does not.  Such a field is preferable to reconstructing the
    # documented split date/time pair.
    for key in (
        "startTime",
        "start_time",
        "startsAt",
        "starts_at",
        "startDateTime",
        "start_datetime",
    ):
        if _text(event.get(key)) is not None:
            return _temporal_member(event.get(key), "event.{0}".format(key))

    date_text = _text(event.get("date"))
    if date_text is not None and "T" in date_text.upper():
        return _temporal_member(date_text, "event.date")
    time_text = _text(event.get("time"))
    if time_text is not None and "T" in time_text.upper():
        return _temporal_member(time_text, "event.time")
    return _split_event_start(event)


def _fighter_name(fighter, corner):
    direct = _text(fighter.get("fullName")) or _text(fighter.get("name"))
    if direct is not None:
        return direct
    parts = [
        part for part in (
            _text(fighter.get("firstName")),
            _text(fighter.get("lastName")),
        ) if part is not None
    ]
    if parts:
        return " ".join(parts)
    nickname = _text(fighter.get("nickname"))
    if nickname is not None:
        return nickname
    raise ValueError(
        "Fight Analytics {0} fighter has no usable name; no observation was "
        "produced".format(corner)
    )


def _participant(provider_id, name, alignment, outcome):
    participant = {
        "kind": "individual",
        "provider_id": provider_id,
        "name": name,
        "alignment": alignment,
    }
    _put(participant, "outcome", outcome)
    return participant


def _participant_outcomes(payload, result_code, red_id, blue_id):
    if result_code in DRAW_RESULTS:
        return "draw", "draw"
    if result_code == "NO_CONTEST":
        return None, None
    winner = _text(payload.get("winner"))
    if winner == red_id:
        return "win", "loss"
    if winner == blue_id:
        return "loss", "win"
    return None, None


def _phase(payload):
    code = _code(payload.get("card"))
    if code is None:
        return None
    name = CARD_NAME_BY_CODE.get(code)
    if name is None:
        return None
    return {"provider_id": code, "name": name}


def _site(event):
    provider_id = _text(event.get("venueId"))
    name = _text(event.get("location"))
    if provider_id is None or name is None:
        return None
    site = {"provider_id": provider_id, "name": name}
    _put(site, "country", _text(event.get("country")))
    return site


def to_observation(payload, *, observed_at, consumer_tier="production"):
    """Map one Fight Analytics v2 fight payload to canonical observation 1.1.

    Fails closed for production/commercial tiers before adaptation (only 'prototype' is allowed).
    ``observed_at`` is caller-supplied and is never sampled from the clock.
    ``payload`` is retained unchanged under ``raw`` and is never mutated.
    """
    if consumer_tier != "prototype":
        raise ValueError(
            "Fight Analytics local connector fails closed for production/commercial tiers. "
            "Only the prototype tier is supported for adaptation."
        )

    if not isinstance(payload, dict):
        raise TypeError("Fight Analytics payload must be a JSON object")

    event = _section(payload, "event")
    red = _section(payload, "redCorner")
    blue = _section(payload, "blueCorner")
    if not event or not red or not blue:
        raise ValueError(
            "Fight Analytics payload must contain event, redCorner and blueCorner "
            "objects; no observation was produced"
        )

    fight_id = _required_text(payload.get("id"), "fight id")
    competition_id = _coherent_id(event, "id", payload, "eventId", "event card")
    competition_name = _required_text(event.get("name"), "event.name")
    red_id = _coherent_id(red, "id", payload, "redCornerId", "red-corner fighter")
    blue_id = _coherent_id(
        blue, "id", payload, "blueCornerId", "blue-corner fighter"
    )
    if red_id == blue_id:
        raise ValueError(
            "Fight Analytics red and blue corners have the same provider "
            "identifier; no observation was produced"
        )

    red_name = _fighter_name(red, "red-corner")
    blue_name = _fighter_name(blue, "blue-corner")
    result_code = _result_code(payload)
    status = _event_status(payload, event, result_code)
    red_outcome, blue_outcome = _participant_outcomes(
        payload, result_code, red_id, blue_id
    )
    temporal_key, temporal_value = _event_start(event)

    canonical_event = {
        "provider_id": fight_id,
        "label": "{0} vs {1}".format(red_name, blue_name),
        "status": status,
        temporal_key: temporal_value,
    }
    _put(canonical_event, "outcome_type", OUTCOME_TYPE_BY_RESULT.get(result_code))
    finished_round = _text(payload.get("finishedAtRound"))
    if finished_round is not None and status == "closed":
        canonical_event["clock"] = {"period": finished_round}

    observation = {
        "provider": {
            "namespace": PROVIDER_NAMESPACE,
            "family": PROVIDER_FAMILY,
        },
        "observed_at": observed_at,
        "adapter": {
            "name": ADAPTER_NAME,
            "version": ADAPTER_VERSION,
            "source_refs": [
                {"kind": "endpoint-class", "value": ENDPOINT_CLASS}
            ],
        },
        "rights": {
            "data_class": RIGHTS_DATA_CLASS,
            "prototype_only": True,
            "commercial_use": False,
        },
        "sport": _sport(payload),
        "competition": {
            "provider_id": competition_id,
            "name": competition_name,
        },
        "event": canonical_event,
        "participants": [
            _participant(red_id, red_name, "red", red_outcome),
            _participant(blue_id, blue_name, "blue", blue_outcome),
        ],
        "raw": payload,
    }
    _put(observation, "phase", _phase(payload))
    _put(observation, "site", _site(event))

    return {"schema_version": SCHEMA_VERSION, "observation": observation}


def to_envelope(payload, *, observed_at, consumer_tier="production"):
    """Produce a canonical envelope from the raw payload using the canonical package.

    Fails closed for production/commercial tiers before adaptation (only 'prototype' is allowed).
    Uses provider-scoped surrogates via the installed canonical resolver, and
    serializes through the canonical package.
    """
    if consumer_tier != "prototype":
        raise ValueError(
            "Fight Analytics local connector fails closed for production/commercial tiers. "
            "Only the prototype tier is supported for adaptation."
        )

    # 1. Adapt payload to observation
    observation = to_observation(payload, observed_at=observed_at, consumer_tier=consumer_tier)

    # 2. Retrieve provider-scoped surrogate resolver from installed package
    resolver = surrogate_resolver(PROVIDER_NAMESPACE)

    # 3. Serialize through the canonical package envelope builder
    return canonical_envelope(observation, id_resolver=resolver)
