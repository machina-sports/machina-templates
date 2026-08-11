"""The one thing packaging is allowed to do to the canonical source: omit a file.

`tools/iptc/canonical/export_official_terms.py` is a generator, not runtime. It
regenerates `official-property-names.json` from the pinned upstream ontologies
under `agent-templates/iptc-mappings/references/`, which exist only in this
repository. Shipping it in the wheel would put a module in a published package
that raises the first time anyone calls it, so it stays here and does not ship.

**Why the exclusion list is closed rather than configurable.** A `build_py`
subclass that filters modules from a free-form list is a supply-chain hole: it
can drop `serialize.py` from a release and still produce a wheel that installs,
imports its package and passes a smoke test. So the list is one name, and
`validate_exclusions` refuses any other — including at build time, on every
package, so a later edit to `EXCLUDED_MODULES` fails the build rather than
quietly shrinking the distribution.

**No file is transformed.** This subclass overrides exactly one method, filters
its result, and changes nothing else. `setuptools` copies the remaining sources
byte-for-byte, which is what lets
`tests/test_iptc_canonical_package.py` hash the *installed* files against
`tools/iptc/vendored-manifest.json` and compare the installed adapters with their
authoritative source bytes.

Loaded by path from `setup.py` rather than imported as `packaging.…`: this
directory is deliberately not an importable package, because a regular
`packaging` package at a repository root would shadow the `packaging`
distribution that setuptools itself resolves.
"""

from __future__ import annotations

from setuptools.command.build_py import build_py as _build_py

#: The import namespace the distribution exposes.
IMPORT_NAME = "machina_sports_canonical"

#: The only module this build is permitted to leave out, ever. Widening this is a
#: reviewed change to what a published package contains, not a build detail.
ALLOWED_EXCLUSIONS = frozenset({
    "{0}.export_official_terms".format(IMPORT_NAME),
})

#: What this build actually leaves out. Kept separate from the allowlist so the
#: check below compares a decision against a rule instead of a constant against
#: itself.
EXCLUDED_MODULES = frozenset({
    "{0}.export_official_terms".format(IMPORT_NAME),
})


def validate_exclusions(names):
    """Return ``names`` as a frozenset, or raise if it excludes anything else.

    Raises ``ValueError`` naming every offending module, so a build that tried to
    drop a runtime module fails with the module name in the log rather than with a
    wheel that is quietly missing it.
    """
    requested = frozenset(names)
    forbidden = sorted(requested - ALLOWED_EXCLUSIONS)
    if forbidden:
        raise ValueError(
            "the canonical build filter may only exclude {0}; refusing to "
            "exclude {1}".format(sorted(ALLOWED_EXCLUSIONS), forbidden))
    return requested


class build_py(_build_py):
    """``build_py`` minus the repository-only generator, and nothing else.

    ``find_package_modules`` is the single point both the wheel and the sdist read
    their module list from — ``sdist`` reaches it through
    ``build_py.get_source_files`` — so filtering here keeps the two artefacts
    consistent by construction rather than by a second, drift-prone list.
    """

    def find_package_modules(self, package, package_dir):
        excluded = validate_exclusions(EXCLUDED_MODULES)
        return [
            (found_package, module, path)
            for found_package, module, path
            in super().find_package_modules(package, package_dir)
            if "{0}.{1}".format(found_package, module) not in excluded
        ]
