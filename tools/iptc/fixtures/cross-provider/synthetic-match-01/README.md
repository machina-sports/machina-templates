# `synthetic-match-01` — one match, two providers

One obviously synthetic 2-1 closed soccer match, expressed in two provider
payload shapes so that `tests/test_iptc_cross_provider_equivalence.py` can check
that both readings land on the same canonical facts.

| Side | File |
|---|---|
| API-Football `/fixtures` element | `api-football.json` (here) |
| sports-skills `_normalize_espn_event` output | `../../source/sports-skills-espn-soccer-native.json` |

**The sports-skills payload is deliberately NOT copied into this directory.** It
is the input to the A14 reference contract, it is published byte-identically in
two repositories, and a second copy here would drift from the first the day
either is corrected. It would also make the comparison partly self-referential:
the point is to compare two independently authored payloads, not one payload
against itself. The test reads it by path.

Everything in both files is invented. No API-Football endpoint was called, no
ESPN endpoint was called, no credential exists in this repository and there is no
network access in this harness. The provider identifiers are deliberately
different on the two sides (`9501`/`9601`/`9701`/`9511`/`9512` here against
`9001`/`synthetic-league-1`/`9101`/`9011`/`9012` there), because the property
under test is that two providers observing one match agree about the *match*
while agreeing about nothing at all about *identity*.

`league.season` is `2026` rather than a `9xxx` token on purpose: API-Football has
no standalone season identifier, so a season is its year, and inventing a tidier
one would have put a string the provider never uses into the crosswalk.
