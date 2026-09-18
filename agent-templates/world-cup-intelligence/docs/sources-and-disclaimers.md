# Sources and Disclaimers

Canonical truth hierarchy:

1. API-Football fixture truth
2. IPTC/Sportschema normalized event data
3. Provider URNs and same-pod document cache
4. Sports Skills context
5. Kalshi/Polymarket market data
6. Google GenAI grounded reasoning
7. xAI/Grok social/news pulse

For the eleven completed-tournament storefront endpoints, the serving source is
the active hash-verified `worldcup:final-archive` version. Its per-row
`source_manifest` records which items from the hierarchy above were used.
Valid archive hits never invoke provider, search, or model connectors. During
canary migration, a clean miss retains the original endpoint path; archive
errors fail closed. Current squad or injury output is not historical evidence
unless its manifest explicitly proves World Cup 2026 or fixture-historical
scope.

The inactive v3 local candidate is derived only from the verified v2 evidence,
all 104 raw local player captures, and the exact FIFA squad-list PDF published
19 July 2026. The FIFA section is complete for that 48-team, 26-player-per-team
published snapshot, not for fixture-date lineups, eligibility changes, injuries,
or replacement history. FIFA caps/goals remain labeled international totals.
Its `coverage` object distinguishes recorded evidence from unsupported fields:
an empty injury feed is `unavailable`, retrospective sports context is not
prematch research, and unresolved identity evidence is never guessed. The v3
ledger retains 14 source DOB conflicts on stable legacy URNs and quarantines the
corrupt Mario/Marco mapping. `snapshot_as_of` is an actual source capture, model
computation, or original editorial generation time; derived content creation is
labeled separately and is never presented as source freshness.

Required disclaimer:

> Informational sports market intelligence only. Not betting, trading, financial, or investment advice.
