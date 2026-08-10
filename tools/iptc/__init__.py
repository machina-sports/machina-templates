"""Offline IPTC Sport Schema 1.1 conformance harness for machina-templates.

Four validation layers plus four hard counters, all against a pinned, vendored
copy of the official IPTC Sport Schema. No network. No credentials. No provider
calls.

Entry point: ``python3 -m tools.iptc``. See ``docs/iptc/BASELINE-AUDIT.md`` for
the recorded baseline and
``docs/rfcs/001-machina-iptc-sport-schema-profile.md`` for the normative profile.
"""

from .reference import TARGET_VERSION, UPSTREAM_COMMIT

__all__ = ["TARGET_VERSION", "UPSTREAM_COMMIT"]
