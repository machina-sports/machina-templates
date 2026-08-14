"""Shared locations and loaders for the greenfield canonical suites.

Revised PR3-D, **Approved Amendment C** (approved 2026-08-13). Amendment C
declines to mutate the historical World Cup runtime at all: the World Cup is
finished, so WCI and ``worldcup:event`` are historical regression evidence, not a
migration target. Nothing in this module may reference a World Cup path, the
legacy document name, a legacy alias, or the historical provider-identifier
shape — the canary is canonical-first from its first line, and a support module
that still knew the legacy shape would be the seam quietly keeping a second
vocabulary alive.

Not a suite. The name deliberately does **not** match ``tests/test_iptc_*.py``,
because that glob is the manifest gate's definition of "a suite"
(``tests/test_iptc_test_manifest.py``): a helper registered there would have to
be run as a suite, and a helper that is not registered would break set equality.

Loaded by path rather than imported as ``tests.iptc_canonical_support``.
``tests/`` has no ``__init__.py``, and the manifest suite already records why
that matters — an installed distribution shipping a top-level ``tests`` package
shadows it. The path form is the pattern this repository already uses for
``tools/iptc/run_test_suites.py``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# Canonical package access
# --------------------------------------------------------------------------

#: The authoritative source directory. ``pyproject.toml`` maps the import
#: namespace ``machina_sports_canonical`` onto exactly this path (PR3-B task 3),
#: and ``tests/test_iptc_canonical_package.py`` case 5 proves the installed wheel
#: is byte-equal to it. So loading it under the distribution's import name is
#: faithful rather than a substitute.
CANONICAL_SOURCE = REPO_ROOT / "tools/iptc/canonical"

#: Deliberately NOT ``from tools.iptc.canonical import ...``. That import
#: executes ``tools/iptc/__init__.py``, which imports ``rdflib`` — a dependency
#: of the *validation harness*, not of the canonical runtime, and absent on a
#: plain interpreter. A suite that died there would be reporting the harness's
#: dependencies rather than the canary's behaviour.
PACKAGE_NAME = "machina_sports_canonical"


def canonical_package():
    """The canonical package: the installed distribution if there is one.

    Prefers a real install, because that is what the client-api image executes
    (§B3). Falls back to the authoritative source bytes under the same import
    name so these suites still run on an interpreter that has not installed the
    wheel — never onto a second copy of the logic.
    """
    if PACKAGE_NAME in sys.modules:
        return sys.modules[PACKAGE_NAME]
    try:
        return importlib.import_module(PACKAGE_NAME)
    except ImportError:
        pass
    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME, CANONICAL_SOURCE / "__init__.py",
        submodule_search_locations=[str(CANONICAL_SOURCE)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = module
    spec.loader.exec_module(module)
    return module


def canonical_module(name: str):
    """One submodule of the canonical package, e.g. ``"capabilities"``."""
    canonical_package()
    return importlib.import_module("{0}.{1}".format(PACKAGE_NAME, name))


# --------------------------------------------------------------------------
# Artifact locations
# --------------------------------------------------------------------------

CONNECTOR_DIR = REPO_ROOT / "connectors/machina-sports-canonical"
CONNECTOR_YAML = CONNECTOR_DIR / "machina-sports-canonical.yml"
CONNECTOR_PYSCRIPT = CONNECTOR_DIR / "machina-sports-canonical.py"
CONNECTOR_INSTALL = CONNECTOR_DIR / "_install.yml"

#: The greenfield canary template, §C4. The name is fixed by the amendment and
#: is not a placeholder.
CANARY = REPO_ROOT / "agent-templates/machina-sports-canonical-canary"
CANARY_INSTALL = CANARY / "_install.yml"
CANARY_WORKFLOW = CANARY / "workflows/canonical-canary-event.yml"

#: §C6: the migration-guide deliverable is *replaced by* a forward adoption
#: guide. Not renamed — replaced, because a migration guide implies a legacy
#: alias-removal programme and Amendment C implies none.
ADOPTION_GUIDE = REPO_ROOT / "docs/iptc/CANONICAL-ADOPTION-GUIDE.md"

FIXTURES = REPO_ROOT / "tools/iptc/fixtures"

#: The equivalent-match tree that already exists, extended rather than replaced.
#: ``synthetic-match-01`` is where the cross-provider equivalence suite already
#: expresses one match twice. Starting a parallel fixture tree would mean two
#: answers to "what is the synthetic match".
CROSS_PROVIDER_MATCH = FIXTURES / "cross-provider/synthetic-match-01"

#: The four §C4 legs, keyed by the **canonical provider namespace** each already
#: emits in ``event_view.provider.namespace``. §C4 names the providers in prose
#: as "sports-skills, API-Football, Sportradar, and Opta"; the namespace is the
#: machine-readable spelling this repository already uses, and adopting a second
#: set of short names here would be the shorthand-alias mistake §B9 forbids for
#: capabilities, applied to providers.
#:
#: **The sports-skills leg enters one step later than the other three, and that
#: asymmetry is load-bearing.** There is no in-repo sports-skills adapter and
#: revised PR3-D may not add one: canonical mode for sports-skills is owned
#: upstream (``sports_skills.canonical``), the canonical layer is frozen, and a
#: connector that grew its own sports-skills adapter would be the seam taking
#: ownership of vocabulary. So this leg is read as the **already-canonical
#: observation** the reference contract checked in, while the other three are
#: read as native provider payloads their adapters convert. Both are existing
#: checked-in fixtures, read by reference; neither is copied.
FOUR_PROVIDER_LEGS = {
    "sports-skills/espn":
        FIXTURES / "observations/sports-skills-espn-soccer-observation.json",
    "api-football": CROSS_PROVIDER_MATCH / "api-football.json",
    "sportradar-soccer": CROSS_PROVIDER_MATCH / "sportradar-soccer.json",
    "stats-perform-opta": CROSS_PROVIDER_MATCH / "stats-perform-opta.json",
}

#: Per-provider corrected envelopes already checked in. Not the equivalent-match
#: legs — each describes its own adapter-contract match — but they are the
#: authoritative statement of what an envelope for that provider looks like.
CORRECTED_ENVELOPES = {
    "sports-skills/espn":
        FIXTURES / "corrected/sports-skills-espn-soccer-envelope.json",
    "api-football": FIXTURES / "corrected/api-football-soccer-envelope.json",
    "sportradar-soccer": FIXTURES / "corrected/sportradar-soccer-envelope.json",
    "stats-perform-opta":
        FIXTURES / "corrected/stats-perform-opta-soccer-envelope.json",
}

#: ``None`` means "this leg is already a ``canonical-observation/1`` document and
#: needs no adapter". Recorded rather than omitted, so a reader cannot mistake
#: the asymmetry for a missing entry, and so the seam's dispatch has one table to
#: consult rather than a provider name to branch on.
LEG_ADAPTERS = {
    "sports-skills/espn": None,
    "api-football": "api_football",
    "sportradar-soccer": "sportradar_soccer",
    "stats-perform-opta": "stats_perform_opta",
}

#: Existing per-provider observation fixtures, used by the identity cases. Each
#: is the adapter's own acceptance fixture, already checked in and already
#: validated by that adapter's suite. Reused rather than re-expressed: a
#: crosswalk test written against a hand-built observation would be asserting
#: that the resolver agrees with the test author, not with the adapters.
OBSERVATIONS = {
    "sports-skills/espn":
        FIXTURES / "observations/sports-skills-espn-soccer-observation.json",
    "api-football": FIXTURES / "observations/api-football-soccer-observation.json",
    "sportradar-soccer":
        FIXTURES / "observations/sportradar-soccer-observation.json",
    "stats-perform-opta":
        FIXTURES / "observations/stats-perform-opta-soccer-observation.json",
}

ENVELOPE_KEY = "machina_sports_schema"

#: The canonical observation contract's own version string, as a leg that arrives
#: pre-canonicalized declares it. The seam recognizes an observation by this,
#: never by the provider's name.
OBSERVATION_SCHEMA_VERSION = "canonical-observation/1"


# --------------------------------------------------------------------------
# Readers
# --------------------------------------------------------------------------

def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_yaml(path: Path):
    import yaml  # local: only the YAML-reading suites pay for it
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def envelope(provider: str) -> dict:
    """The ``machina_sports_schema`` block of a corrected envelope fixture."""
    return read_json(CORRECTED_ENVELOPES[provider])[ENVELOPE_KEY]


def event_view(provider: str) -> dict:
    return envelope(provider)["event_view"]


def observation(provider: str) -> dict:
    """One provider's checked-in ``canonical-observation/1`` document."""
    return read_json(OBSERVATIONS[provider])


def provider_ids(provider: str) -> dict:
    """The provider-native identifiers that observation states, by kind.

    Read off the fixture rather than transcribed, so a fixture edit cannot leave
    a crosswalk test mapping identifiers nothing observes any more.
    """
    document = observation(provider)["observation"]
    competition = document.get("competition") or {}
    return {
        "event": (document.get("event") or {}).get("provider_id"),
        "competition": competition.get("provider_id"),
        "teams": [participant.get("provider_id")
                  for participant in document.get("participants") or []
                  if participant.get("kind") == "team"],
    }


def dotted(document, path: str):
    """``dotted(view, "competition.name")``. Raises ``KeyError`` on a miss.

    Raising is the point: a path that does not exist must fail with the path in
    the message rather than resolve to ``None``, which reads exactly like a
    provider that did not state the fact.
    """
    node = document
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise KeyError(path)
        node = node[part]
    return node


# --------------------------------------------------------------------------
# The canonical contract the canary consumes
# --------------------------------------------------------------------------

#: §B11's closed list, retained unchanged by §C4. A difference outside it is a
#: failure, not a provider quirk.
ALLOWED_CROSS_PROVIDER_DIFFERENCES = (
    "provider_ids",
    "provenance",
    "capabilities",
    "rights",
    "raw",
    "unshared_actions_or_statistics",
)

#: §C4's compared set.
CANONICAL_INVARIANTS = (
    "event_id",
    "competition",
    "participants",
    "start_time",
    "status",
)

#: Which capability backs which ``event_view`` member. §B11's closed set allows a
#: difference in "actions or statistics **not shared by capability**", and that
#: clause is only checkable if the mapping from a view member to the capability
#: that states it is written down. A member absent from this map has no
#: capability to hide behind and must be equal across every leg — ``label``,
#: ``sport``, ``season``, ``phase`` and ``site`` are facts about the match.
#:
#: ``provider`` is deliberately absent and handled separately: it is
#: provider-scoped by construction, so it is an allowed difference outright.
EVENT_VIEW_CAPABILITY = {
    "clock": "event.clock",
    "competition": "event.competition",
    "event_id": "event.identity",
    "participants": "event.participants",
    "start_time": "event.start_time",
    "status": "event.status",
}

#: The canary's own capability declaration. A consumer declares what it needs;
#: the adapter declares what it can answer (§B9). These are the canonical dotted
#: names, unextended.
CANARY_REQUIRES = (
    "event.identity",
    "event.competition",
    "event.participants",
    "event.start_time",
    "event.status",
    "provenance",
)
CANARY_OPTIONAL = ("event.score", "event.lineups")

#: Fixed, so nothing reads a clock. The same instant
#: ``tests/test_iptc_cross_provider_equivalence.py`` pins, which is what lets the
#: legs be compared field by field at all.
OBSERVED_AT = "2026-03-01T22:05:00+00:00"


# --------------------------------------------------------------------------
# The canary's injected crosswalk
#
# §B12: identity is resolved from a crosswalk the consumer injects, never minted
# by the canonical layer from provider identifiers. These URNs are the canary's
# own neutral scheme — deliberately not the package's ``urn:machina:sports:``
# surrogate stem, so a resolved identity is recognisable on sight as *not* a
# surrogate, and deliberately not any existing consumer's scheme, so the canary
# borrows no other product's identity space.
# --------------------------------------------------------------------------

CANARY_EVENT_URN = "urn:example:canary:event:synthetic-match-01"
CANARY_COMPETITION_URN = (
    "urn:example:canary:competition:synthetic-premier-division")
CANARY_TEAM_URNS = {
    "home": "urn:example:canary:team:synthetic-home-united",
    "away": "urn:example:canary:team:synthetic-away-town",
}


def leg_observation(provider: str) -> dict:
    """One leg as a ``canonical-observation/1`` document.

    Dispatched exactly the way the seam dispatches: a leg that already carries
    the observation contract is used as it stands, everything else goes to the
    adapter :data:`LEG_ADAPTERS` names. No provider is branched on by name.
    """
    payload = read_json(FOUR_PROVIDER_LEGS[provider])
    module = LEG_ADAPTERS[provider]
    if module is None:
        return payload
    canonical_package()
    adapter = importlib.import_module(
        "{0}.adapters.{1}".format(PACKAGE_NAME, module))
    return adapter.to_observation(payload, observed_at=OBSERVED_AT)


def leg_provider_ids(provider: str) -> dict:
    """The provider-native identifiers one leg observes, by role.

    **Derived, never transcribed.** A hand-written table would drift from the
    fixtures the first time one is corrected, and the drift would show up as a
    crosswalk that silently stops resolving — which reads exactly like a
    provider that genuinely has no mapping.
    """
    document = leg_observation(provider)["observation"]
    competition = document.get("competition") or {}
    teams = {participant.get("alignment"): participant.get("provider_id")
             for participant in document.get("participants") or []
             if participant.get("kind") == "team"}
    return {
        "event": (document.get("event") or {}).get("provider_id"),
        "competition": competition.get("provider_id"),
        "home": teams.get("home"),
        "away": teams.get("away"),
    }


def canary_crosswalk() -> list:
    """The crosswalk the canary injects, in the connector's entry shape.

    One entry per resource, each carrying the identifier every provider uses for
    it. This is configuration, not logic: it is the only place that knows the
    four legs describe one match, and the connector reads it without knowing
    which provider any identifier came from.

    Only single-resource kinds appear. A season, a phase and a participation are
    structural derivations of a *pair* of provider identifiers, so no crosswalk
    entry denotes them and they keep the package's marked surrogate — which is
    the behaviour §B12 asks for, not a gap in this table.
    """
    by_kind = {"event": {}, "competition": {}, "home": {}, "away": {}}
    for provider in FOUR_PROVIDER_LEGS:
        identifiers = leg_provider_ids(provider)
        for role in by_kind:
            by_kind[role][provider] = identifiers[role]
    return [
        {"kind": "event", "urn": CANARY_EVENT_URN,
         "provider_ids": by_kind["event"]},
        {"kind": "competition", "urn": CANARY_COMPETITION_URN,
         "provider_ids": by_kind["competition"]},
        {"kind": "team", "urn": CANARY_TEAM_URNS["home"],
         "provider_ids": by_kind["home"]},
        {"kind": "team", "urn": CANARY_TEAM_URNS["away"],
         "provider_ids": by_kind["away"]},
    ]
