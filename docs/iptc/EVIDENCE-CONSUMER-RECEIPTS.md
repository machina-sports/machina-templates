# Evidence receipt contract and selected-fixture history

The existing `api-football-enrich-event-data` workflow remains the producer.
Deploy the merged `api-football-event-data.py` into its existing connector; do
not introduce an app-side fetcher, second service, new scheduler or data store.

## Contract correction

The HTTP-receipt producer added in #366 emits `provenance.synthetic` and
`provenance.retrieval`. The closed `machina-event-evidence/1` schema did not yet
declare those fields, so all five saved live evidence kinds failed validation.
The schema now admits a closed, typed `provider_http` receipt. An explicit
`synthetic: false` requires that receipt. Unknown origin and synthetic historical
documents remain schema-readable without a receipt, not eligible by default.

Consumers must still match the receipt's provider, operation and observed time
to the event, evidence kind, source references, crosswalk and rights. This is
transport attestation, not a cryptographic signature, rights clearance or proof
that an editorial claim is supported. Never manufacture receipts for replays.

## Head-to-head correction

The provider's last-five pair response can contain the selected fixture itself.
The shared projector now excludes that exact provider fixture ID before either
document family is generated. Team-pair validation still happens first. A
response containing only the selected fixture produces unavailable evidence
with an explicit no-prior-meetings reason, not a self-match or invented score.
The response envelope is retained unchanged for audit. Historical fact IDs keep
their original response ordinal; document upsert keys and observation times are
unchanged. The last-five response may legitimately leave four prior meetings.

## Release verification

1. Merge with green `Test API-Football Evidence` CI. Schema-only changes now also
   trigger that job. Run the connector suite and canonical Phase 1 tests.
2. Back up the existing connector definition privately through project MCP.
   Update only `filecontent`, preserving credentials and all other fields.
3. Read back exact connector bytes and unchanged enrichment workflow tasks.
4. Run the existing enrichment workflow for one explicitly selected fixture.
   Verify stable IDs, all five legacy and canonical kinds, unchanged rights,
   genuine observed-time receipts and exclusion of the selected history match.
5. Only then enable the app's canonical evidence reader. It must never fall back
   to legacy after a canonical schema, origin, identity or freshness refusal.

No pod execution or deployment is implied by this source change alone.
