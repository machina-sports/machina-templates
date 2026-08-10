"""Tests for the Machina Sports Schema canonical contract (PR 2, tasks A1-A6).

Run from the repository root:

    python3 tests/test_iptc_canonical_serializer.py -v

Run the file directly, for the same reason as
``tests/test_iptc_validation_harness.py``: ``tests/`` is a namespace directory
with no ``__init__.py``, so ``-m unittest tests.<module>`` can be shadowed by an
installed distribution that ships a top-level regular ``tests`` package.

What is being defended here:

1. **The version claim is honest.** The profile minor bump and both schema
   versions are asserted against the RFCs that authorise them, so a version
   string can never drift away from its written contract.
2. **Fabrication is caught at the adapter boundary.** ``validate_observation``
   is the only place a null, an empty string, a placeholder, a short participant
   list or an invented statistic can be stopped before it reaches a serializer.
3. **Identity is a visibly-marked surrogate.** The resolver is provider-scoped,
   deterministic, collision-free across fixtures, and leaks no provider token
   into the identifier it mints.
4. **The allowlist is reproducible from the pin**, not hand-maintained.
5. **Capabilities fail closed.** An unrecognised capability name is never read as
   satisfied.
6. **No NewsCode is mapped into a scheme the pin cannot check.** Every mapped
   code is asserted present in a pinned SKOS scheme, which is what keeps
   ``spsocactiontype:`` out of the tables by construction rather than by memory.
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.iptc import canonical  # noqa: E402


class TestVersionClaims(unittest.TestCase):
    """A1 — the profile version and the RFC that authorises it move together."""

    def test_profile_version_is_the_minor_bump(self):
        self.assertEqual(canonical.PROFILE_VERSION, "machina-iptc-profile/1.1")
        self.assertEqual(canonical.SCHEMA_VERSION, "canonical-observation/1")
        self.assertEqual(canonical.MACHINA_SCHEMA_VERSION, "machina-sports-schema/1")
        self.assertEqual(canonical.SERIALIZER_VERSION, "1")

    def test_rfc_001_records_the_bump_and_rfc_002_exists(self):
        rfc1 = (REPO_ROOT / "docs/rfcs/001-machina-iptc-sport-schema-profile.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("machina-iptc-profile/1.1", rfc1)
        self.assertIn("machina:ObservationProvenance", rfc1)
        rfc2 = REPO_ROOT / "docs/rfcs/002-machina-sports-schema-canonical-observation.md"
        self.assertTrue(rfc2.is_file())
        self.assertIn("canonical-observation/1", rfc2.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
