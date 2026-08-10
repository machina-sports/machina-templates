"""Serialize one canonical observation into the Machina Sports Schema outputs.

Two serializers read the observation and neither reads the other:
:func:`sport_schema_graph` produces RDF-compatible JSON-LD, :func:`event_view`
produces a compact non-RDF projection. Deriving one from the other would make a
bug in the first silently become a bug in the second, and would tie the shape a
product consumes to the shape a standards consumer consumes.

Three rules the whole module is arranged around:

**Nothing is fabricated.** :func:`_put` drops ``None``, ``""`` and every
placeholder rather than asserting it, and :func:`_resource` returns nothing at
all when a resource would carry an ``@id``, a ``@type`` and no facts. An absent
fact leaves no trace, which is the only honest representation of not knowing.

**No ``machina:`` property ever lands on an official resource.** The pinned
shapes are ``sh:closed`` (RFC 001 §5.4), so provenance and provider crosswalk are
separate ``machina:``-typed siblings that reference the official resource by
``@id``.

**Nothing is minted here.** ``id_resolver(kind, *parts) -> str`` is injected, so
RFC 001 §7.6 — "serializers and templates do not mint identifiers" — stays
literally true and a later phase can swap in the canonical identity service
without touching this file.

Vendored byte-exact into ``sports-skills``: Python 3.9-compatible, standard
library only, and no import of ``tools.*``. That is why the shared JSON-LD
context is read from ``shared-context.json`` next to this file rather than from
``tools.iptc.context`` — the vendored package has no such module. That file is a
byte-identical copy of the published context and a test in this repository
asserts it, so it is a copy rather than a second source of truth.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import SERIALIZER_VERSION
from .observation import PLACEHOLDERS
from .vocab import (
    ACTION_CLASS,
    COMPETITION_TYPE,
    EVENT_OUTCOME,
    EVENT_OUTCOME_TYPE,
    EVENT_STATUS,
    PLAYER_STATUS,
    SOCCER_POSITION,
    newscode,
)

#: The shared Machina JSON-LD context, packaged beside this module.
SHARED_CONTEXT_PATH = Path(__file__).resolve().parent / "shared-context.json"

#: How a provider identifier came to be attached to a Machina identity. There is
#: no fourth value and no fuzzy matching in this phase (RFC 002 §5).
RESOLUTION_PROVIDER_NATIVE = "provider-native"

_context_cache = None


def shared_context():
    """The prefix table every document produced here inlines by value.

    Returns a fresh copy each call: the table is handed straight to a caller
    inside ``@context``, and one caller mutating it would silently change the
    vocabulary of every later document.
    """
    global _context_cache
    if _context_cache is None:
        with SHARED_CONTEXT_PATH.open(encoding="utf-8") as handle:
            document = json.load(handle)
        _context_cache = {
            key: value
            for key, value in document["@context"].items()
            if isinstance(value, str)
        }
    return dict(_context_cache)


# ---------------------------------------------------------------------------
# Omission helpers
# ---------------------------------------------------------------------------

def _usable(value):
    """Whether ``value`` is a fact rather than a stand-in for one."""
    if value is None:
        return False
    if isinstance(value, str):
        return value not in PLACEHOLDERS
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _put(node, key, value):
    """Set ``key`` only when ``value`` is a fact. Omission over fabrication."""
    if _usable(value):
        node[key] = value


def _text(value):
    """``value`` as a string when it is a fact, else ``None``.

    Scores, counts, attendance and statistics are ``sh:datatype xsd:string`` in
    the pinned shapes, so ``0`` and ``"0"`` must both serialize to ``"0"`` — and
    ``0`` must stay a fact, which is why this is not a truthiness test.
    """
    if value is None or isinstance(value, (dict, list)):
        return None
    text = value if isinstance(value, str) else str(value)
    return text if text not in PLACEHOLDERS else None


def _datetime(value):
    """A typed ``xsd:dateTime`` value node, or nothing."""
    text = _text(value)
    return None if text is None else {"@value": text, "@type": "xsd:dateTime"}


def _reference(identifier):
    return None if not identifier else {"@id": identifier}


def _mapped(table, scheme, key):
    """A NewsCode node reference, or ``None`` when nothing defensible maps.

    An unmapped provider value is **omitted**, never guessed and never defaulted.
    The value itself survives in ``event_view`` and in ``observation.raw``, which
    is where a consumer can see what the provider actually said.
    """
    if not isinstance(key, str) or key not in table:
        return None
    return newscode(scheme, table[key])


def _resource(node_id, type_name, properties):
    """A graph node, or ``None`` when it would assert nothing.

    A resource carrying only an ``@id`` and a ``@type`` is a stub: it looks like
    a described entity to every consumer and describes nothing. Emitting none is
    the truthful outcome.
    """
    if not node_id or not properties:
        return None
    node = {"@id": node_id, "@type": type_name}
    node.update(properties)
    return node


class _Graph:
    """Accumulates resources in emission order, first description wins.

    Keying on ``@id`` makes a duplicate identifier structurally impossible rather
    than merely unlikely. Two descriptions of one identifier cannot both be
    authoritative, and the profile's ``duplicate-node-id`` gate exists precisely
    because that has happened in this repository before.
    """

    def __init__(self):
        self.nodes = []
        self._seen = set()

    def add(self, node):
        if node is None or node["@id"] in self._seen:
            return
        self._seen.add(node["@id"])
        self.nodes.append(node)


# ---------------------------------------------------------------------------
# Observation accessors
# ---------------------------------------------------------------------------

def _observation(document):
    value = document.get("observation") if isinstance(document, dict) else None
    return value if isinstance(value, dict) else {}


def _section(observation, key):
    value = observation.get(key)
    return value if isinstance(value, dict) else {}


def _list(observation, key):
    value = observation.get(key)
    return value if isinstance(value, list) else []


def _participants(observation):
    return [p for p in _list(observation, "participants") if isinstance(p, dict)]


def _namespace(observation):
    return _section(observation, "provider").get("namespace")


class _Identities:
    """Every Machina identifier this observation needs, minted once.

    Built before any resource is emitted, because the graph and ``event_view``
    both reference them and a second minting pass is a second chance to disagree.
    """

    def __init__(self, observation, id_resolver):
        competition = _section(observation, "competition")
        season = competition.get("season") if isinstance(
            competition.get("season"), dict) else {}
        phase = _section(observation, "phase")
        site = _section(observation, "site")
        event = _section(observation, "event")

        self.competition = None
        self.season = None
        self.phase = None
        self.site = None
        self.event = None
        self.teams = {}
        self.athletes = {}
        self.participations = {}

        if competition.get("provider_id"):
            self.competition = id_resolver("competition", competition["provider_id"])
            if season.get("provider_id"):
                self.season = id_resolver(
                    "competition", competition["provider_id"], season["provider_id"]
                )
            if phase.get("provider_id"):
                self.phase = id_resolver(
                    "phase", competition["provider_id"],
                    season.get("provider_id", ""), phase["provider_id"],
                )
        if site.get("provider_id"):
            self.site = id_resolver("site", site["provider_id"])
        if event.get("provider_id"):
            self.event = id_resolver("event", event["provider_id"])

        for participant in _participants(observation):
            provider_id = participant.get("provider_id")
            kind = participant.get("kind")
            if not provider_id or kind not in ("team", "individual"):
                continue
            if kind == "team":
                self.teams.setdefault(provider_id, id_resolver("team", provider_id))
            else:
                self.athletes.setdefault(provider_id, id_resolver("athlete", provider_id))
            if event.get("provider_id"):
                self.participations.setdefault(
                    (kind, provider_id),
                    id_resolver("participation", event["provider_id"], kind, provider_id),
                )

    #: The competition an event is *in*: the season when the provider supplies
    #: one, because that is the competition the fixture actually belongs to.
    @property
    def event_competition(self):
        return self.season or self.competition


# ---------------------------------------------------------------------------
# sport_schema_graph
# ---------------------------------------------------------------------------

def _medtop(observation):
    code = _section(observation, "sport").get("medtop")
    return _reference("medtop:{0}".format(code)) if _text(code) else None


def _competition_resources(graph, observation, ids):
    competition = _section(observation, "competition")
    sport = _medtop(observation)

    properties = {}
    _put(properties, "rdfs:label", _text(competition.get("name")))
    _put(properties, "sport:sport", sport)
    _put(properties, "sport:competitionType",
         _mapped(COMPETITION_TYPE, "spct", competition.get("type")))
    graph.add(_resource(ids.competition, "sport:Competition", properties))

    season = competition.get("season") if isinstance(competition.get("season"), dict) else {}
    season_properties = {}
    _put(season_properties, "rdfs:label", _text(season.get("name")))
    _put(season_properties, "sport:sport", sport)
    _put(season_properties, "sport:competitionType", _mapped(COMPETITION_TYPE, "spct", "season"))
    _put(season_properties, "sport:parent", _reference(ids.competition))
    graph.add(_resource(ids.season, "sport:Competition", season_properties))

    phase = _section(observation, "phase")
    phase_properties = {}
    _put(phase_properties, "rdfs:label", _text(phase.get("name")))
    _put(phase_properties, "sport:sport", sport)
    _put(phase_properties, "sport:phaseInCompetition", _reference(ids.event_competition))
    graph.add(_resource(ids.phase, "sport:CompetitionPhase", phase_properties))


def _site_resource(graph, observation, ids):
    site = _section(observation, "site")
    properties = {}
    # SiteShape is sh:closed with no property shapes at all, so rdfs:label (an
    # ignored property) is the only thing a Site may carry. City and country are
    # facts, and they travel in event_view rather than being forced into a shape
    # that would reject them.
    _put(properties, "rdfs:label", _text(site.get("name")))
    graph.add(_resource(ids.site, "sport:Site", properties))


def _competitor_resources(graph, observation, ids):
    for participant in _participants(observation):
        if participant.get("kind") != "team":
            continue
        properties = {}
        _put(properties, "rdfs:label", _text(participant.get("name")))
        graph.add(_resource(ids.teams.get(participant.get("provider_id")),
                            "sport:Team", properties))
    for participant in _participants(observation):
        if participant.get("kind") != "individual":
            continue
        properties = {}
        _put(properties, "rdfs:label", _text(participant.get("name")))
        graph.add(_resource(ids.athletes.get(participant.get("provider_id")),
                            "sport:Athlete", properties))


def _event_resource(graph, observation, ids):
    event = _section(observation, "event")
    properties = {}
    _put(properties, "rdfs:label", _text(event.get("label")))
    _put(properties, "sport:sport", _medtop(observation))
    _put(properties, "sport:eventInCompetition", _reference(ids.event_competition))
    _put(properties, "sport:eventInCompetitionPhase", _reference(ids.phase))
    _put(properties, "sport:location", _reference(ids.site))
    _put(properties, "sport:startDateTime", _datetime(event.get("start_time")))
    _put(properties, "sport:endDateTime", _datetime(event.get("end_time")))
    _put(properties, "sport:eventStatus",
         _mapped(EVENT_STATUS, "speventstatus", event.get("status")))
    _put(properties, "sport:eventOutcomeType",
         _mapped(EVENT_OUTCOME_TYPE, "speventoutcometype", event.get("outcome_type")))
    _put(properties, "sport:attendance", _text(event.get("attendance")))
    # The clock is deliberately absent: EventShape admits no clock property, and
    # RFC 001 forbids expressing a reading as a dateTime. It survives in
    # event_view, which is the projection built for consumers who need it.
    participations = [
        _reference(ids.participations[(p["kind"], p["provider_id"])])
        for p in _participants(observation)
        if (p.get("kind"), p.get("provider_id")) in ids.participations
    ]
    _put(properties, "sport:participation", participations)
    graph.add(_resource(ids.event, "sport:Event", properties))


def _participation_label(participant, observation):
    name = _text(participant.get("name"))
    if name is None:
        return None
    event_label = _text(_section(observation, "event").get("label"))
    if event_label is None:
        return "{0} participation".format(name)
    return "{0} participation in {1}".format(name, event_label)


def _statistics(participant):
    """Provider statistics as ``prefix:localName`` string literals.

    Sorted so output is byte-stable regardless of the order an adapter happened
    to build its dictionary in. Whether a given statistic is admissible on this
    participation class is the pinned ``sh:closed`` shape's decision, not this
    module's: a statistic on the wrong class must fail layer 2 loudly rather than
    be dropped quietly here.
    """
    statistics = participant.get("statistics")
    if not isinstance(statistics, dict):
        return []
    pairs = []
    for curie in sorted(statistics):
        value = _text(statistics[curie])
        if value is not None:
            pairs.append((curie, value))
    return pairs


def _participation_resources(graph, observation, ids):
    for participant in _participants(observation):
        if participant.get("kind") != "team":
            continue
        properties = {}
        _put(properties, "rdfs:label", _participation_label(participant, observation))
        _put(properties, "sport:participationBy",
             _reference(ids.teams.get(participant.get("provider_id"))))
        _put(properties, "sport:alignment", _text(participant.get("alignment")))
        _put(properties, "sport:score", _text(participant.get("score")))
        _put(properties, "sport:eventOutcome",
             _mapped(EVENT_OUTCOME, "speventoutcome", participant.get("outcome")))
        for curie, value in _statistics(participant):
            _put(properties, curie, value)
        graph.add(_resource(
            ids.participations.get(("team", participant.get("provider_id"))),
            "sport:TeamParticipation", properties))

    for participant in _participants(observation):
        if participant.get("kind") != "individual":
            continue
        properties = {}
        _put(properties, "rdfs:label", _participation_label(participant, observation))
        _put(properties, "sport:participationBy",
             _reference(ids.athletes.get(participant.get("provider_id"))))
        _put(properties, "sport:playerStatus",
             _mapped(PLAYER_STATUS, "spplayerstatus", participant.get("player_status")))
        _put(properties, "sport:positionEvent",
             _mapped(SOCCER_POSITION, "spsocposition", participant.get("position")))
        _put(properties, "sport:score", _text(participant.get("score")))
        _put(properties, "sport:eventOutcome",
             _mapped(EVENT_OUTCOME, "speventoutcome", participant.get("outcome")))
        _put(properties, "sport:uniformNumberEvent",
             _text(participant.get("uniform_number")))
        _put(properties, "sport:teamParticipation",
             _reference(ids.participations.get(("team", participant.get("team_provider_id")))))
        for curie, value in _statistics(participant):
            _put(properties, curie, value)
        graph.add(_resource(
            ids.participations.get(("individual", participant.get("provider_id"))),
            "sport:IndividualParticipation", properties))


def _membership_resources(graph, observation, ids, id_resolver):
    names = {
        (p.get("kind"), p.get("provider_id")): _text(p.get("name"))
        for p in _participants(observation)
    }
    for membership in _list(observation, "memberships"):
        if not isinstance(membership, dict):
            continue
        individual_id = membership.get("individual_provider_id")
        team_id = membership.get("team_provider_id")
        athlete = ids.athletes.get(individual_id)
        team = ids.teams.get(team_id)
        if not athlete or not team:
            # A membership between entities this observation never described is
            # an assertion about two things it cannot name. Omitted.
            continue
        properties = {}
        athlete_name = names.get(("individual", individual_id))
        team_name = names.get(("team", team_id))
        if athlete_name and team_name:
            _put(properties, "rdfs:label",
                 "{0} membership of {1}".format(athlete_name, team_name))
        _put(properties, "sport:member", _reference(athlete))
        _put(properties, "sport:membershipOf", _reference(team))
        _put(properties, "sport:uniformNumber", _text(membership.get("uniform_number")))
        graph.add(_resource(
            id_resolver("membership", individual_id, team_id),
            "sport:IndividualMembership", properties))


def _action_resources(graph, observation, ids, id_resolver):
    event = _section(observation, "event")
    for action in _list(observation, "actions"):
        if not isinstance(action, dict):
            continue
        ordinal = action.get("ordinal")
        action_class = _mapped(ACTION_CLASS, "spactionclass", action.get("class"))
        if ordinal is None or not event.get("provider_id") or action_class is None:
            # sport:class is mandatory on an Action (RFC 002 §2) and the only
            # pinned scheme for it is spactionclass:. An action whose class does
            # not map is carried by event_view and observation.raw instead of
            # being emitted as an Action that asserts no class.
            continue
        properties = {}
        _put(properties, "rdfs:label", _text(action.get("label")))
        _put(properties, "sport:actionInEvent", _reference(ids.event))
        properties["sport:class"] = action_class
        _put(properties, "sport:actionDateTime", _datetime(action.get("action_time")))
        _put(properties, "sport:minutesElapsed", _text(action.get("minute")))
        _put(properties, "sport:periodValue", _text(action.get("period")))
        _put(properties, "sport:sequenceNumber", _text(ordinal))
        participant_id = action.get("participant_provider_id")
        _put(properties, "sport:participation", _reference(
            ids.participations.get(("individual", participant_id))
            or ids.participations.get(("team", participant_id))
        ))
        graph.add(_resource(
            id_resolver("action", event["provider_id"], ordinal),
            "sport:Action", properties))


def _crosswalk_entries(observation, ids):
    """``(entity_kind, machina_id, provider_id, evidence)`` per identified entity.

    Participations, memberships and actions are absent on purpose: they are
    structures this serializer derives, not entities the provider named, so
    there is no provider identifier that could honestly be recorded for them.
    """
    competition = _section(observation, "competition")
    season = competition.get("season") if isinstance(competition.get("season"), dict) else {}
    entries = [
        ("competition", ids.competition, competition.get("provider_id"),
         "observation.competition.provider_id"),
        ("season", ids.season, season.get("provider_id"),
         "observation.competition.season.provider_id"),
        ("phase", ids.phase, _section(observation, "phase").get("provider_id"),
         "observation.phase.provider_id"),
        ("site", ids.site, _section(observation, "site").get("provider_id"),
         "observation.site.provider_id"),
        ("event", ids.event, _section(observation, "event").get("provider_id"),
         "observation.event.provider_id"),
    ]
    for index, participant in enumerate(_participants(observation)):
        provider_id = participant.get("provider_id")
        if participant.get("kind") == "team":
            entries.append(("team", ids.teams.get(provider_id), provider_id,
                            "observation.participants[{0}].provider_id".format(index)))
        elif participant.get("kind") == "individual":
            entries.append(("athlete", ids.athletes.get(provider_id), provider_id,
                            "observation.participants[{0}].provider_id".format(index)))
    return [
        (kind, machina_id, _text(provider_id), evidence)
        for kind, machina_id, provider_id, evidence in entries
        if machina_id and _text(provider_id) is not None
    ]


def _crosswalk_resources(graph, observation, ids, id_resolver):
    namespace = _text(_namespace(observation))
    if namespace is None:
        return
    for kind, machina_id, provider_id, _evidence in _crosswalk_entries(observation, ids):
        properties = {
            "rdfs:label": "{0} {1} {2}".format(namespace, kind, provider_id),
            "machina:identifies": {"@id": machina_id},
            "machina:providerNamespace": namespace,
            "machina:providerId": provider_id,
            "machina:resolutionMethod": RESOLUTION_PROVIDER_NATIVE,
        }
        graph.add(_resource(
            id_resolver("provider-identifier", kind, provider_id),
            "machina:ProviderIdentifier", properties))


def _provenance_resource(graph, observation, ids, id_resolver):
    event = _section(observation, "event")
    namespace = _text(_namespace(observation))
    if not ids.event or not event.get("provider_id") or namespace is None:
        return
    adapter = _section(observation, "adapter")
    rights = _section(observation, "rights")
    properties = {}
    _put(properties, "rdfs:label",
         "{0} observation of event {1}".format(namespace, ids.event.rsplit(":", 1)[-1]))
    properties["machina:describes"] = {"@id": ids.event}
    properties["machina:providerNamespace"] = namespace
    _put(properties, "machina:observedAt", _datetime(observation.get("observed_at")))
    _put(properties, "machina:adapterVersion", _text(adapter.get("version")))
    properties["machina:serializerVersion"] = SERIALIZER_VERSION
    _put(properties, "machina:rightsClass", _text(rights.get("data_class")))
    graph.add(_resource(
        id_resolver("observation-provenance", event["provider_id"]),
        "machina:ObservationProvenance", properties))


def sport_schema_graph(document, *, id_resolver):
    """One JSON-LD document: the shared context inlined, one flat ``@graph``.

    Resources are emitted in the fixed order of the RFC 002 §2 table, so the same
    observation always produces byte-identical output. Nothing here reads the
    clock, the environment or the network.
    """
    observation = _observation(document)
    ids = _Identities(observation, id_resolver)
    graph = _Graph()

    _competition_resources(graph, observation, ids)
    _site_resource(graph, observation, ids)
    _competitor_resources(graph, observation, ids)
    _event_resource(graph, observation, ids)
    _participation_resources(graph, observation, ids)
    _membership_resources(graph, observation, ids, id_resolver)
    _action_resources(graph, observation, ids, id_resolver)
    _crosswalk_resources(graph, observation, ids, id_resolver)
    _provenance_resource(graph, observation, ids, id_resolver)

    return {"@context": shared_context(), "@graph": graph.nodes}
