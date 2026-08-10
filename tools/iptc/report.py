"""Deterministic machine-readable results, plus the human-readable audit.

Both outputs are checked in and compared in CI. That is the whole point: the
baseline is expected to FAIL conformance, so the only honest CI gate is "the
recorded failure report is still exactly reproducible", not "the outputs pass".

Nothing here may depend on wall-clock time, the working directory, dict insertion
order or a random seed, or the snapshot comparison becomes a coin toss.
"""

from __future__ import annotations

import json
from pathlib import Path

from .context import CONTEXT_PATH, check_context_against_reference
from .fileio import atomic_write_text, markdown_document
from .reference import PACKAGE_ROOT, REFERENCE_ROOT, REPO_ROOT
from .validate import DocumentResult, pin_metadata

FIXTURES_ROOT = PACKAGE_ROOT / "fixtures"
PROVENANCE_PATH = FIXTURES_ROOT / "provenance.json"

JSON_REPORT_PATH = REPO_ROOT / "docs" / "iptc" / "baseline-audit.json"
MARKDOWN_REPORT_PATH = REPO_ROOT / "docs" / "iptc" / "BASELINE-AUDIT.md"
INVENTORY_JSON_PATH = REPO_ROOT / "docs" / "iptc" / "inventory.json"
INVENTORY_MARKDOWN_PATH = REPO_ROOT / "docs" / "iptc" / "INVENTORY.md"

GATES = (
    ("unknown_sport_terms", "unknown `sport:` terms"),
    ("invalid_newscode_values", "invalid NewsCode values"),
    ("duplicate_resource_ids", "duplicate resource IDs"),
    ("provider_properties_in_iptc_namespace", "provider properties in the IPTC namespace"),
)


def load_provenance() -> dict:
    return json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))


def resolve(entry: dict) -> Path:
    """A provenance `path` is relative to the repository root.

    Repo-relative rather than package-relative because fixtures live under
    ``tools/iptc/fixtures/`` while the vendored positive controls live under
    ``agent-templates/iptc-mappings/references/``, and one base has to cover both.
    """
    return REPO_ROOT / entry["path"]


def build_report(results: dict[str, list[DocumentResult]]) -> dict:
    """The machine-readable report. Deterministic given the same inputs."""
    provenance = load_provenance()
    by_fixture = {
        section: {r.fixture: r.as_dict() for r in items}
        for section, items in results.items()
    }

    def totals(section: str) -> dict:
        entries = by_fixture.get(section, {})
        out = {"documents": len(entries), "conforming": 0}
        for key, _ in GATES:
            out[key] = 0
            out[f"{key}_unknown"] = 0
        out["layer_pass"] = {
            "jsonld_parse": 0, "official_shacl": 0,
            "machina_profile": 0, "controlled_vocabulary": 0,
        }
        out["unverifiable_newscode_values"] = 0
        for entry in entries.values():
            if entry["conforms"]:
                out["conforming"] += 1
            for layer in out["layer_pass"]:
                if entry["layers"].get(layer, {}).get("ok"):
                    out["layer_pass"][layer] += 1
            for key, _ in GATES:
                value = entry["counters"].get(key)
                if value is None:
                    out[f"{key}_unknown"] += 1
                else:
                    out[key] += value
            out["unverifiable_newscode_values"] += entry["counters"].get(
                "unverifiable_newscode_values") or 0
        return out

    return {
        "report_version": "1",
        "report_kind": "iptc-sport-schema-1.1-baseline-audit",
        "reproduce": "python3 -m tools.iptc --check",
        "note": (
            "The baseline set is EXPECTED to fail conformance. This report is the "
            "'before' figure: the corrected serializers land in a later PR and are "
            "measured against it. Recording it accurately is the deliverable, not "
            "minimising it."
        ),
        "pin": pin_metadata(),
        "shared_context": {
            "path": str(CONTEXT_PATH.relative_to(REPO_ROOT)),
            "drift_against_pin": check_context_against_reference(),
        },
        "fixture_set_version": provenance["fixture_set_version"],
        "totals": {section: totals(section) for section in sorted(results)},
        "documents": {
            section: dict(sorted(entries.items()))
            for section, entries in sorted(by_fixture.items())
        },
    }


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def _tick(ok: bool | None) -> str:
    if ok is None:
        return "n/a"
    return "pass" if ok else "**FAIL**"


def _count(value) -> str:
    return "n/a" if value is None else str(value)


def _fixture_meta(provenance: dict, fixture: str) -> dict:
    for section in ("baseline", "conforming", "negative"):
        for entry in provenance.get(section, []):
            if entry["fixture"] == fixture:
                return entry
    return {}


def render_markdown(report: dict) -> str:
    provenance = load_provenance()
    pin = report["pin"]
    lines: list[str] = []
    add = lines.append

    add("# IPTC Sport Schema 1.1 — baseline conformance audit")
    add("")
    add("<!-- GENERATED FILE. Do not edit by hand. -->")
    add(f"<!-- Regenerate with: {report['reproduce']} -->")
    add("")
    add("## What this document is")
    add("")
    add(
        "The exact, measured distance between what this repository's IPTC mappings "
        "currently emit and what IPTC Sport Schema 1.1 actually requires."
    )
    add("")
    add(
        "The Machina canonical domain model remains authoritative. IPTC Sport Schema "
        "is an **output projection** generated from it, never the storage model and "
        "never Machina identity."
    )
    add("")
    add(
        "**Every baseline fixture below is expected to fail.** That is the finding, "
        "not a defect in the harness. This PR is foundation-only and output-neutral: "
        "it changes no production mapping output, and instead makes the failure "
        "measurable so that a later conformance claim is checkable against a number "
        "rather than against a judgement. A conformance claim that does not "
        "reference this audit is not evidence."
    )
    add("")
    add("## The pin")
    add("")
    add("| Field | Value |")
    add("|---|---|")
    add(f"| Target version | {pin['target_version']} |")
    add(f"| Upstream | `{pin['upstream_repository']}` |")
    add(f"| Commit | `{pin['upstream_commit']}` |")
    add(f"| Licence | {pin['license']} |")
    add(f"| Reference files verified by sha256 | {pin['reference_files_verified']} |")
    add(f"| Official classes / properties in the pin | {pin['official_term_counts']['classes']} / {pin['official_term_counts']['properties']} |")
    add(f"| Pinned controlled-vocabulary schemes | {len(pin['pinned_vocabulary_schemes'])} |")
    add("")
    add(f"> {pin['upstream_ref_note']}")
    add("")
    shims = pin["upstream_shims_applied"]
    add("### Upstream defects worked around in memory")
    add("")
    add(
        f"- `{len(shims['unterminated_prefix_directive_repairs'])}` pinned Turtle "
        f"files need the missing `.` after their final `@prefix` directive before a "
        f"strict parser will read them."
    )
    add(
        f"- `{shims['orphan_sh_ignoredproperties_dropped']}` SHACL shapes declare "
        f"`sh:ignoredProperties` without an active `sh:closed`, which pyshacl "
        f"rejects at shape-load time."
    )
    add("")
    add(
        "Neither shim touches the vendored bytes; both are documented in "
        "`agent-templates/iptc-mappings/references/iptc-sport-schema-1.1/UPSTREAM.md`."
    )
    add("")

    drift = report["shared_context"]["drift_against_pin"]
    add("### Shared JSON-LD context")
    add("")
    add(f"`{report['shared_context']['path']}`")
    add("")
    if drift:
        add(f"**{len(drift)} binding(s) disagree with the pin:**")
        add("")
        for finding in drift:
            add(f"- `{finding['code']}` — `{finding.get('prefix')}`: {json.dumps(finding, sort_keys=True)}")
    else:
        add(
            "Every `sportschema.org` and `cv.iptc.org` prefix binding in the shared "
            "context is a verbatim copy of what the pinned artefacts declare. "
            "Verified mechanically, not by eye."
        )
    add("")

    # -- headline counters ----------------------------------------------------
    add("## The four gates, across the baseline set")
    add("")
    baseline = report["totals"].get("baseline", {})
    add("| Gate | Target | Baseline total |")
    add("|---|---|---|")
    for key, label in GATES:
        unknown = baseline.get(f"{key}_unknown", 0)
        suffix = f" (+{unknown} document(s) where nothing could be counted)" if unknown else ""
        add(f"| {label} | 0 | **{baseline.get(key, 0)}**{suffix} |")
    add("")
    add(
        f"Plus **{baseline.get('unverifiable_newscode_values', 0)}** NewsCode value(s) "
        f"that are *unverifiable* rather than invalid: upstream names the scheme but "
        f"ships no TTL for it at this commit, so no offline check is possible. These "
        f"are counted separately from invalid values, because the two need different "
        f"fixes — but **layer 4 fails closed on them**. The profile requires every "
        f"NewsCode to be provably present in a pinned vocabulary, and missing "
        f"evidence is not evidence of correctness. See `UPSTREAM.md`, 'Known gap'."
    )
    add("")
    add(
        "**Do not add the gate rows together.** Gates 1 and 4 overlap by "
        "construction: a provider field name emitted under `sport:` is both an "
        "undeclared term and an attributable provider leak, and it is counted once "
        "in each column because the two columns answer different questions."
    )
    add("")

    # -- per-section layer tables --------------------------------------------
    section_titles = {
        "conforming": ("Positive controls", (
            "The controlled claim here is **layer 2 only**: the four upstream samples "
            "are known to conform against the official SHACL shapes, so if an L2 cell "
            "regresses the harness is wrong rather than the data. They are NOT "
            "expected to satisfy the Machina profile, which is deliberately stricter "
            "than IPTC and imposes the Machina graph envelope, and they are not "
            "expected to satisfy layer 4 either — several of them carry codes from "
            "schemes upstream ships no TTL for, which layer 4 fails closed on. "
            "`machina-profile-conforming-minimal` is the only document in this "
            "repository expected to pass everything, and it is the target shape the "
            "corrected serializers aim at.")),
        "baseline": ("Baseline — current mapping outputs", (
            "One row per supported mapping output. `class` distinguishes a verbatim "
            "checked-in artefact from a fixture hand-authored against the mapping "
            "contract because no checked-in sample exists.")),
        "negative": ("Negative controls", (
            "Each row proves one detector actually fires. A green row here would mean "
            "the corresponding gate is decorative.")),
    }

    for section in ("conforming", "baseline", "negative"):
        entries = report["documents"].get(section, {})
        if not entries:
            continue
        title, blurb = section_titles[section]
        add(f"## {title}")
        add("")
        add(blurb)
        add("")
        add("| Fixture | L1 JSON-LD | L2 official SHACL | L3 Machina profile | L4 vocabulary | unknown `sport:` | invalid codes | dup IDs | provider leaks |")
        add("|---|---|---|---|---|---|---|---|---|")
        for fixture, entry in entries.items():
            layers = entry["layers"]
            counters = entry["counters"]
            shacl_cell = _tick(layers["official_shacl"]["ok"])
            if layers["official_shacl"]["detail"].get("vacuous"):
                shacl_cell = "**FAIL** (vacuous: 0 targets)"
            add(
                f"| `{fixture}` "
                f"| {_tick(layers['jsonld_parse']['ok'])} "
                f"| {shacl_cell} "
                f"| {_tick(layers['machina_profile']['ok'])} "
                f"| {_tick(layers['controlled_vocabulary']['ok'])} "
                f"| {_count(counters.get('unknown_sport_terms'))} "
                f"| {_count(counters.get('invalid_newscode_values'))} "
                f"| {_count(counters.get('duplicate_resource_ids'))} "
                f"| {_count(counters.get('provider_properties_in_iptc_namespace'))} |"
            )
        add("")

    # -- per-fixture detail ---------------------------------------------------
    add("## Per-mapping detail")
    add("")
    for section in ("baseline", "conforming", "negative"):
        entries = report["documents"].get(section, {})
        for fixture, entry in entries.items():
            meta = _fixture_meta(provenance, fixture)
            layers = entry["layers"]
            counters = entry["counters"]
            add(f"### `{fixture}`")
            add("")
            add(f"- **section:** {section}")
            add(f"- **document:** `{entry['path']}`")
            if meta.get("class"):
                add(f"- **fixture class:** {meta['class']}")
            if meta.get("source"):
                add(f"- **derived from:** `{meta['source']}`")
            if meta.get("provenance"):
                add(f"- **provenance:** {meta['provenance']}")
            if meta.get("transformation"):
                add(f"- **transformation:** {meta['transformation']}")
            if meta.get("emitted_by"):
                add(f"- **emitted by:** {meta['emitted_by']}")
            if meta.get("coverage"):
                add(f"- **coverage:** {meta['coverage']}")
            if meta.get("construction"):
                add(f"- **construction:** {meta['construction']}")
            if meta.get("asserts"):
                add(f"- **asserts:** {meta['asserts']}")
            if meta.get("role"):
                add(f"- **role:** {meta['role']}")
            if meta.get("limitation"):
                add(f"- **MISSING EVIDENCE:** {meta['limitation']}")
            if meta.get("profile_expectation"):
                add(f"- **profile expectation:** {meta['profile_expectation']}")
            if meta.get("note"):
                add(f"- **note:** {meta['note']}")
            consumers = meta.get("consumers")
            if consumers:
                add("- **known consumer dependencies:**")
                for consumer in consumers:
                    add(f"  - `{consumer}`")
            else:
                add(
                    "- **known consumer dependencies:** none recorded. For a negative "
                    "or positive control that is correct; for a baseline mapping it "
                    "would be an inventory defect."
                )
            add("")

            parse = layers["jsonld_parse"]
            if parse["ok"]:
                add(f"**Layer 1 — JSON-LD parse:** pass, {parse['detail']['triples']} triples.")
            else:
                add(
                    f"**Layer 1 — JSON-LD parse:** FAIL at the "
                    f"`{parse['detail'].get('stage')}` stage — "
                    f"`{parse['detail'].get('error')}`. Layers 2-4 were not run and the "
                    f"four counters are `null`, not `0`."
                )
                for blocked in parse["detail"].get("blocked_context_references") or []:
                    add(
                        f"- BLOCKED `{blocked['code']}` at `{blocked['pointer']}` → "
                        f"`{blocked['reference']}`. Rejected before the RDF parser ran; "
                        f"no request was made."
                    )
            add("")

            shacl = layers["official_shacl"]
            if shacl["detail"].get("skipped"):
                add(f"**Layer 2 — official SHACL:** {shacl['detail']['skipped']}.")
            elif shacl["ok"]:
                add(
                    f"**Layer 2 — official SHACL:** conforms, over "
                    f"{shacl['detail']['official_class_instances']} instance(s) of an "
                    f"official IPTC class."
                )
            elif shacl["detail"].get("vacuous"):
                add(
                    "**Layer 2 — official SHACL:** **VACUOUS** — pyshacl reports "
                    "`conforms=True`, but the document contains **0 instances of any "
                    "official IPTC class**, so every `sh:targetClass` matched nothing "
                    "and no shape was exercised. This is the wrong-namespace defect: "
                    "the document's `sport:` prefix does not point at "
                    "`https://sportschema.org/ontologies/main/`, so its `sport:Event`, "
                    "`sport:Team` and friends are not IPTC classes at all. Counted as "
                    "a layer-2 failure."
                )
            else:
                add(f"**Layer 2 — official SHACL:** {shacl['detail']['result_count']} violation(s).")
                add("")
                for result in shacl["detail"]["results"][:12]:
                    add(
                        f"- `{result.get('constraint', '?').rsplit('#', 1)[-1]}` on "
                        f"`{result.get('focus_node', '?')}`"
                        + (f" path `{result.get('path')}`" if result.get("path") else "")
                        + (f" — {result.get('message')}" if result.get("message") else "")
                    )
                if shacl["detail"]["result_count"] > 12:
                    add(f"- … {shacl['detail']['result_count'] - 12} more, in `baseline-audit.json`.")
            add("")

            prof = layers["machina_profile"]
            if prof["detail"].get("skipped"):
                add(f"**Layer 3 — Machina profile:** {prof['detail']['skipped']}.")
            elif prof["ok"]:
                add("**Layer 3 — Machina profile:** conforms.")
            else:
                by_code: dict[str, int] = {}
                for finding in prof["detail"]["findings"]:
                    by_code[finding["code"]] = by_code.get(finding["code"], 0) + 1
                add(f"**Layer 3 — Machina profile:** {prof['detail']['finding_count']} finding(s).")
                add("")
                for code, count in sorted(by_code.items()):
                    add(f"- `{code}` × {count}")
                bindings = prof["detail"].get("context_bindings") or {}
                if "sport" in bindings:
                    add(f"- context binds `sport:` to `{bindings['sport']}`")
            add("")

            vocab = layers["controlled_vocabulary"]
            if vocab["detail"].get("skipped"):
                add(f"**Layer 4 — controlled vocabulary:** {vocab['detail']['skipped']}.")
            else:
                detail = vocab["detail"]
                add(
                    f"**Layer 4 — controlled vocabulary:** "
                    f"{len(detail['valid'])} valid, {len(detail['invalid'])} invalid, "
                    f"{len(detail['undeclared_prefix'])} unresolvable prefix, "
                    f"{len(detail['unverifiable'])} unverifiable."
                )
                add("")
                for item in detail["invalid"]:
                    add(f"- INVALID `{item['value']}` — {item['reason']}")
                for item in detail["undeclared_prefix"]:
                    add(f"- UNRESOLVABLE `{item['value']}` on `{item['property']}` — {item['reason']}")
                for item in detail["unverifiable"]:
                    add(f"- UNVERIFIABLE `{item['value']}` — {item['reason']}")
            add("")

            counter_detail = layers.get("counter_detail") or {}
            unknown = counter_detail.get("unknown_sport_terms") or []
            if unknown:
                add(
                    f"**Unknown `sport:` terms — {counters['unknown_sport_terms']} "
                    f"occurrence(s) of {counters.get('unknown_sport_terms_distinct')} "
                    f"distinct term(s):**"
                )
                add("")
                add(", ".join(f"`{t['term']}`×{t['occurrences']}" for t in unknown))
                add("")
            leaks = counter_detail.get("provider_properties_in_iptc_namespace") or []
            if leaks:
                attribution: dict[str, set[str]] = {}
                for leak in leaks:
                    for provider in leak["providers"]:
                        attribution.setdefault(provider, set()).add(leak["term"])
                add("**Provider properties in the IPTC namespace:**")
                add("")
                for provider, terms in sorted(attribution.items()):
                    add(f"- {provider}: " + ", ".join(f"`{t}`" for t in sorted(terms)))
                add("")
            duplicates = counter_detail.get("duplicate_resource_ids") or []
            if duplicates:
                add("**Duplicate resource IDs:**")
                add("")
                for duplicate in duplicates:
                    add(f"- `{duplicate['@id']}` × {duplicate['occurrences']}")
                add("")

    add("## Coverage and what is missing")
    add("")
    add("| Required coverage | Fixture | Evidence class |")
    add("|---|---|---|")
    required = [
        ("API-Football soccer event", "api-football-soccer-event"),
        ("API-Football soccer event, null-bearing", "api-football-soccer-event-nulls"),
        ("API-Football actions", "api-football-actions"),
        ("API-Football team statistics", "api-football-team-stats"),
        ("API-Football player statistics", "api-football-player-stats"),
        ("Sportradar soccer event", "sportradar-soccer-event"),
        ("Sportradar soccer timeline", "sportradar-soccer-timeline"),
        ("Stats Perform / Opta event", "stats-perform-opta-event"),
        ("Stats Perform / Opta timeline", "stats-perform-opta-timeline"),
        ("Sportradar tennis", "sportradar-tennis-event"),
        ("Sportradar NFL", "sportradar-nfl-event"),
        ("Sportradar MLB", "sportradar-mlb-event"),
        ("American football", "american-football-event"),
        ("Generic custom event", "custom-event"),
    ]
    for label, fixture in required:
        meta = _fixture_meta(provenance, fixture)
        add(f"| {label} | `{fixture}` | {meta.get('class', 'MISSING')} |")
    add("")
    synthetic = [
        entry["fixture"] for entry in provenance["baseline"]
        if entry["class"] == "mapping-contract-synthetic"
    ]
    add(
        f"**{len(synthetic)} of {len(provenance['baseline'])} baseline fixtures are "
        f"`mapping-contract-synthetic`**, because no checked-in sample of those "
        f"mappings' output exists and this work may not call a licensed provider to "
        f"get one. Those fixtures faithfully reproduce the SHAPE each mapping emits — the "
        f"key set, the nesting, the context — but their values are synthetic. Read "
        f"their rows as statements about the mapping contract, not as production "
        f"volumes: "
        + ", ".join(f"`{f}`" for f in synthetic)
        + "."
    )
    add("")
    add("### Missing evidence, stated rather than papered over")
    add("")
    add(
        "1. **No `spsocaction` vocabulary exists upstream at the pinned commit.** "
        "`tools/prefixes.ttl` binds the prefix and the SHACL shapes reference the "
        "scheme, but there is no `vocabularies/spsocaction.ttl`. Soccer action-type "
        "codes therefore cannot be validated offline and are reported as "
        "`unverifiable`. The same applies to `spsocrole`, `spesaction` and the other "
        "per-sport action/result schemes. `unverifiable` is reported as its own "
        "category and never promoted to `valid`, and it **fails** layer 4 — the "
        "profile's requirement is provable membership in a pinned vocabulary, so a "
        "value nothing can check does not pass."
    )
    add(
        "2. **No baseline fixture is a captured production document.** The four "
        "verbatim fixtures are checked-in *examples*, which are themselves already "
        "drifted from what the mappings now emit (`custom-event` and "
        "`api-football-soccer-event` use `urn:apifootball:fixture:` while the mapping "
        "now emits `urn:apifootball:sport_event:`). Treat them as representative "
        "shapes, not as a snapshot of live output."
    )
    add(
        "3. **The provider-leak attribution table is reviewed, not inferred.** "
        "Nothing in the term `sport:doubleHeader` marks it as a Sportradar MLB "
        "field; that attribution lives in `tools/iptc/rules/provider-leak-terms.json` "
        "and is only as complete as the inventory behind it. Terms that are invented "
        "but not provider-branded are counted by gate 1 alone."
    )
    add(
        "4. **`worldcup-iptc-event-to-api-response` is a consumer, not an emitter, and "
        "is therefore not fixtured here.** It reads `sport:competition`, "
        "`schema:startDate`, `sport:status`, `sport:competitors` and `sport:venue` off "
        "whichever provider document it is given. Its response envelope is unchanged "
        "by this PR and is migrated with the other consumers."
    )
    add("")
    add("## Reproducing this report")
    add("")
    add("```bash")
    add("python3 -m pip install -r requirements-iptc-validator.txt")
    add("python3 -m tools.iptc --verify-pin   # vendored bytes vs upstream-commit.json")
    add("python3 -m tools.iptc                # regenerate both reports")
    add("python3 -m tools.iptc --check        # fail if the checked-in reports are stale")
    add("python3 tests/test_iptc_validation_harness.py -v")
    add("```")
    add("")
    add(
        "`--check` is what CI runs. CI stays green while the baseline fails "
        "conformance, because what is asserted is that the recorded failure report is "
        "still exactly reproducible — not that legacy output passes."
    )
    return markdown_document(lines)


def expected_artifacts(report: dict) -> dict[Path, str]:
    """Every generated file, mapped to the bytes it should currently contain.

    One place, so `python3 -m tools.iptc` and `--check` cannot disagree about
    which files are generated.
    """
    from . import inventory as inventory_module

    inventory = inventory_module.build_inventory()
    return {
        JSON_REPORT_PATH: json.dumps(report, indent=2, sort_keys=True) + "\n",
        MARKDOWN_REPORT_PATH: render_markdown(report),
        INVENTORY_JSON_PATH: json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        INVENTORY_MARKDOWN_PATH: inventory_module.render_markdown(inventory),
    }


def write_reports(report: dict) -> dict[Path, str]:
    """Write every generated artefact atomically.

    All four are snapshot-compared in CI, so a crash mid-write must not be able to
    leave a truncated file that then reads as a changed conformance result.
    """
    artifacts = expected_artifacts(report)
    for path, content in artifacts.items():
        atomic_write_text(path, content)
    return artifacts
