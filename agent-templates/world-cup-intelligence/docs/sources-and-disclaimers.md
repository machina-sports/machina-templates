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

Required disclaimer:

> Informational sports market intelligence only. Not betting, trading, financial, or investment advice.
