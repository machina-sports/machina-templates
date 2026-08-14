"""Thin shared canonical seam for Machina templates (PR3-D, Amendment B §B15).

**This file owns nothing.** It dispatches, it resolves an injected crosswalk, and
it returns what the installed ``machina_sports_canonical`` distribution answers.
Every term, every property name, every serialization rule and every rights
decision lives in that package. A vocabulary table, a status map or a second
serializer appearing here would make the seam a second source of truth, which is
the drift the whole programme exists to remove — so the connector suite reads
this file's source and import graph and fails on any of them.

Four commands, and no fifth:

``provider_preflight``
    The gate, §B13. Runs **before** retrieval and costs nothing when it refuses.
``canonicalize_event``
    Preflight, then dispatch a provider payload to its adapter, then serialize
    through the package with the injected resolver.
``validate_event``
    Read an envelope somebody else produced and say whether it is the contract
    this repository claims.
``capability_rights_gate``
    The post-render **drift check**, §B13. It reports; it never authorizes.

**Why preflight can decide rights without calling anybody.** The gate needs a
rights claim, not data. Each adapter states the class of evidence it emits as a
module constant, and the flags that actually gate are declared below with their
evidence. The decision itself is never made here: it is handed to the package's
``rights_findings``, which is the one implementation allowed to render it.

**Scope honesty.** Every adapter reachable from here emits prototype-only
evidence today, so every production-tier request refuses. That is the gate
working, not a defect, and it is not a licence position about any provider.
"""

from machina_sports_canonical import MACHINA_SCHEMA_VERSION
from machina_sports_canonical import PROFILE_VERSION
from machina_sports_canonical import SCHEMA_VERSION
from machina_sports_canonical import capabilities as _capabilities
from machina_sports_canonical import ids as _ids
from machina_sports_canonical import rights as _rights
from machina_sports_canonical import serialize as _serialize
from machina_sports_canonical.adapters import api_football as _api_football
from machina_sports_canonical.adapters import sportradar_soccer as _sportradar
from machina_sports_canonical.adapters import stats_perform_opta as _opta

#: Provider namespace -> the adapter that reads that provider's native payload.
#: This is the allowlist: a namespace absent from it is refused before anything
#: else happens, so an unrecognised feed cannot reach a retrieval path by being
#: passed a payload that happens to parse.
#:
#: ``None`` means "arrives already canonical and needs no adapter". sports-skills
#: owns its canonical mode upstream; implementing a fourth adapter here would be
#: this connector taking ownership of vocabulary it is forbidden to own.
_ADAPTERS = {
    "api-football": _api_football,
    "sportradar-soccer": _sportradar,
    "sports-skills/espn": None,
    "stats-perform-opta": _opta,
}

#: Providers whose evidence supports a production consumer. **Empty, by
#: evidence**: every adapter above emits ``prototype_only`` and
#: ``commercial_use: False`` on every observation it produces. Promoting a
#: provider out of this default is a rights decision with Amendment B authority
#: behind it, never a test convenience — so the set is stated rather than
#: inferred, and the default is refusal.
_PRODUCTION_RIGHTS_PROVIDERS = frozenset()

#: The evidence class for a leg with no in-repo adapter constant to read.
_DEFAULT_DATA_CLASS = "open-public"

#: How the injected resolver describes itself to provenance. The package's own
#: strategy is extended rather than replaced: the digest and the
#: canonical-identity-service note are still true, and only the identity story
#: changes — resolved from a crosswalk where one exists, surrogate where none
#: does. A resolver that reported the bare surrogate strategy would make the
#: document claim identities were minted when they were looked up.
_INJECTED_STRATEGY = "injected-crosswalk-with-provider-scoped-surrogate"


def _params(request_data):
    return dict((request_data or {}).get("params") or {})


def _refusal(code, detail, **evidence):
    finding = {"code": code, "detail": detail}
    finding.update(evidence)
    return finding


def _requested(params):
    return (list(params.get("requires") or []),
            list(params.get("optional") or []))


def _unknown_capability_names(requires, optional):
    """Capability names the contract does not know, isolated from presence.

    Asking the package with everything present is what separates "you named a
    capability that does not exist" from "the payload has not been fetched yet".
    The first is knowable before retrieval and fails closed; the second is not
    knowable before retrieval and must not be guessed at.
    """
    report = _capabilities.check_compatibility(
        {"present": _capabilities.ALL_CAPABILITIES},
        requires=requires, optional=optional)
    return report["unknown_capabilities"]


def _rights_evidence(provider):
    """The rights claim preflight decides on, assembled without a provider call.

    ``data_class`` is the adapter's own constant. The two booleans are the
    declaration above. Neither is a decision: both are handed to the package.
    """
    adapter = _ADAPTERS.get(provider)
    production = provider in _PRODUCTION_RIGHTS_PROVIDERS
    return {
        "data_class": getattr(adapter, "RIGHTS_DATA_CLASS", _DEFAULT_DATA_CLASS),
        "prototype_only": not production,
        "commercial_use": production,
    }


def _preflight(params):
    """Every reason to refuse that is knowable before retrieval."""
    provider = params.get("provider")
    consumer_tier = params.get("consumer_tier") or _rights.STRICT_CONSUMER_TIER
    requires, optional = _requested(params)
    refusals = []

    if provider not in _ADAPTERS:
        refusals.append(_refusal(
            "provider-not-allowlisted",
            "The provider is not one this seam is configured to reach, so no "
            "retrieval was attempted.",
            provider=provider))

    unknown = _unknown_capability_names(requires, optional)
    if unknown:
        refusals.append(_refusal(
            "capability-unknown",
            "A declared capability name is outside the contract's vocabulary. "
            "Refused rather than read as absent.",
            unknown_capabilities=unknown))

    if provider in _ADAPTERS:
        refusals.extend(_rights.rights_findings(
            {_rights.ENVELOPE_KEY: {"rights": _rights_evidence(provider)}},
            consumer_tier=consumer_tier))

    return {
        "allowed": not refusals,
        "provider": provider,
        "consumer_tier": consumer_tier,
        "refusals": refusals,
        "stage": "pre-retrieval",
    }


def _crosswalk_index(crosswalk):
    """``(kind, provider, provider_id) -> machina urn`` from the caller's entries.

    The injected shape is one entry per
    resource, carrying the provider identifiers that denote it. Indexing it is
    the only transformation this connector performs on identity, and it performs
    no other: no minting, no inference, no matching by name.
    """
    index = {}
    for entry in crosswalk or []:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        urn = entry.get("urn") or entry.get("_id") or entry.get("@id")
        identifiers = entry.get("provider_ids")
        if not kind or not urn or not isinstance(identifiers, dict):
            continue
        for provider, provider_id in identifiers.items():
            if provider_id is None:
                continue
            index[(kind, provider, str(provider_id))] = urn
    return index


def _resolver(crosswalk, provider):
    """The injected resolver, §B12.

    Crosswalk first; the package's provider-scoped surrogate resolver for
    everything the crosswalk does not map. Composite identity tuples — a season,
    a phase, a participation — are structural derivations no crosswalk entry
    denotes, so they always take the surrogate path and keep its marker. A
    surrogate has to be recognisable as a surrogate on sight.
    """
    index = _crosswalk_index(crosswalk)
    fallback = _ids.surrogate_resolver(provider)

    def resolve(kind, *parts):
        if len(parts) == 1:
            mapped = index.get((kind, provider, str(parts[0])))
            if mapped is not None:
                return mapped
        return fallback(kind, *parts)

    resolve.strategy = dict(getattr(fallback, "strategy", None) or {})
    resolve.strategy["id_strategy"] = _INJECTED_STRATEGY
    return resolve


def _observation(provider, payload, observed_at):
    """The payload as a canonical observation, dispatched by shape then table.

    A leg that already carries the observation contract's version string is
    already canonical and is used as it stands. Everything else goes to the
    adapter the allowlist names. Neither branch reads a provider field.
    """
    if isinstance(payload, dict) and payload.get("schema_version") == SCHEMA_VERSION:
        return payload
    adapter = _ADAPTERS.get(provider)
    if adapter is None:
        raise ValueError(
            "provider '{0}' supplies no adapter and the payload is not already a "
            "canonical observation".format(provider))
    return adapter.to_observation(payload, observed_at=observed_at)


def provider_preflight(request_data):
    """Refuse a (provider, tier, capability) combination before any retrieval."""
    return {"status": True, "data": _preflight(_params(request_data))}


def canonicalize_event(request_data):
    """Preflight, adapt, then serialize through the package."""
    params = _params(request_data)
    gate = _preflight(params)
    if not gate["allowed"]:
        return {"status": False,
                "data": {"allowed": False, "envelope": None,
                         "refusals": gate["refusals"], "stage": gate["stage"]}}

    provider = params.get("provider")
    requires, optional = _requested(params)
    document = _observation(provider, params.get("payload"),
                            params.get("observed_at"))
    envelope = _serialize.canonical_envelope(
        document, id_resolver=_resolver(params.get("crosswalk"), provider))

    report = _capabilities.check_compatibility(
        envelope[_rights.ENVELOPE_KEY]["capabilities"],
        requires=requires, optional=optional)
    if not report["compatible"]:
        return {"status": False,
                "data": {"allowed": False, "envelope": None,
                         "capabilities": report,
                         "refusals": [_refusal(
                             "capability-incompatible",
                             "The envelope does not satisfy the consumer's "
                             "declared requirements.",
                             missing_required=report["missing_required"])],
                         "stage": "post-render"}}

    return {"status": True,
            "data": {"allowed": True, "envelope": envelope,
                     "capabilities": report, "refusals": [],
                     "stage": "post-render"}}


def validate_event(request_data):
    """Whether an envelope is the contract this repository claims."""
    params = _params(request_data)
    envelope = params.get("envelope")
    block = envelope.get(_rights.ENVELOPE_KEY) if isinstance(envelope, dict) else None
    problems = []
    if not isinstance(block, dict):
        problems.append(_refusal("envelope-absent",
                                 "No canonical envelope was supplied."))
    else:
        if block.get("schema_version") != MACHINA_SCHEMA_VERSION:
            problems.append(_refusal(
                "envelope-schema-version",
                "The envelope does not claim the schema version this seam "
                "serves.", expected=MACHINA_SCHEMA_VERSION,
                found=block.get("schema_version")))
        if block.get("profile") != PROFILE_VERSION:
            problems.append(_refusal(
                "envelope-profile",
                "The envelope does not claim the profile this seam serves.",
                expected=PROFILE_VERSION, found=block.get("profile")))
    return {"status": not problems,
            "data": {"valid": not problems, "problems": problems}}


def capability_rights_gate(request_data):
    """Post-render drift check. Reports; never authorizes (§B13)."""
    params = _params(request_data)
    envelope = params.get("envelope") or {}
    consumer_tier = params.get("consumer_tier") or _rights.STRICT_CONSUMER_TIER
    requires, optional = _requested(params)
    block = envelope.get(_rights.ENVELOPE_KEY) if isinstance(envelope, dict) else {}
    findings = _rights.rights_findings(envelope, consumer_tier=consumer_tier)
    report = _capabilities.check_compatibility(
        (block or {}).get("capabilities") or {"present": []},
        requires=requires, optional=optional)
    return {"status": True,
            "data": {"role": "drift-check", "authorizes": False,
                     "consumer_tier": consumer_tier,
                     "rights_findings": findings, "capabilities": report,
                     "stage": params.get("stage") or "post-render"}}
