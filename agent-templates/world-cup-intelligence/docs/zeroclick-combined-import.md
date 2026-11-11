# Combined ZeroClick import source

`openapi-zeroclick-combined.json` (version 1.6.0) is one self-contained OpenAPI 3.1
document for a single ZeroClick dashboard import. It is the World Cup Intelligence
import source plus the Market Link Snapshot operation.

**Status: `import_source_awaiting_dashboard_import`.** This file has not been imported or
published, does not register meters or prices, and moves no money. Nothing here
says the snapshot operation is live or billable today.

## Files

| Path | Role |
|---|---|
| `docs/openapi-import-source.json` | World Cup import source (1.5.1). Copied in unchanged. |
| `docs/openapi-zeroclick-combined.json` | Self-contained combined import document. |
| `tests/test_zeroclick_combined_openapi.py` | Contract tests for the combined document. |

## Sources

- World Cup: `machina-sports/machina-templates`,
  commit `320c0c71829217205f719581624b6f62c2eca070`,
  `agent-templates/world-cup-intelligence/docs/openapi-import-source.json` (1.5.1).
  Every path, component and the root `security` (`payPerUse`) and `servers` are kept
  structurally identical (JSON-equal).
- Market Link Snapshot: `machina-sports/machina-client-api` at commit
  `c9c8743a8a96dd3b70546b6d7537bd587bf6707c`:
  - `docs/contracts/sports-markets/v1/openapi/market-link-snapshot-v1.yaml` (`sports-market-link-snapshot/1`)
  - `docs/contracts/sports-markets/v1/openapi/market-link-snapshot-v2.yaml` (`sports-market-link-snapshot/2`)

## What was combined

- One added path, `/markets/v1/link-snapshot`:
  - `GET` (`getMarketLinkSnapshotDiscovery`): anonymous discovery (`security: []`),
    v2 discovery schema.
  - `POST` (`getMarketLinkSnapshot`): `zeroclickSignature` security. ZeroClick signs the
    request; buyers never hold or supply a seller signing secret. Starts from v1 (responses
    200, 400, 401, 402, 404, 409, 422, 429, 503, the `zc-usage`/`zc-replay`/`Retry-After`
    headers, and the billing and replay text). v2 replaces the content and adds to the
    description of only the responses it lists. 200 and 422 accept
    `MarketLinkV2AnySnapshotResponse` (`/1` or `/2`). Request examples: the v1 Polymarket
    event link plus the v2 Polymarket `/sports/ucl/<slug>` and Kalshi UCL links.
- All v1/v2 components are bundled as `MarketLinkV1*` / `MarketLinkV2*` so none collide
  with World Cup names such as `Coverage`. External `market-link-snapshot-v1.yaml#...`
  refs are rewritten to local pointers. The bundled schemas are not edited. The new
  accepted-URL text sits on the request body and next to the request-schema `$ref`.
- `x-transport-contract` now limits the `{status, meta, data}` envelope to World Cup
  paths only. Snapshot responses are the bare documents.
- `servers` stays `https://api.machina.gg` (upstream; no other URL substituted).

## Maintain

When updating this bundle, use the pinned upstream sources and preserve the merge rules
above. Run
`pytest agent-templates/world-cup-intelligence/tests/test_zeroclick_combined_openapi.py`.
Also compare the bundled `MarketLinkV1*`/`MarketLinkV2*` schemas against the upstream
contracts at the commit above.

## Dashboard flow (manual, authorized operator only)

1. Publish the reviewed document and use its immutable commit-pinned URL:
   `https://raw.githubusercontent.com/machina-sports/machina-templates/<published-commit>/agent-templates/world-cup-intelligence/docs/openapi-zeroclick-combined.json`.
2. In the ZeroClick seller dashboard, an authorized operator points the catalog import at
   that URL and starts the import. Changing `openApiUrl` alone does not publish or
   overwrite the catalog.
3. After import, check that every World Cup route, price and envelope is unchanged and
   that both snapshot operations show the documented security (GET anonymous, POST
   signed).
4. Do not activate the snapshot listing, register its meter or set its price until the
   blocker below is cleared and the owner approves it separately.

## Blockers (separate from publishing this document)

- **Upstream enablement/routing:** on 2026-10-18 a public
  `GET https://api.machina.gg/markets/v1/link-snapshot` returned 404. The route is only
  registered with `SPORTS_SNAPSHOT_PUBLIC_ENABLED=1`, but the cause of this 404 has not
  been established. Resolve and recheck upstream availability separately; importing
  this file does not fix it.
- **Venue rights** and **provider settlement idempotency** are still open upstream
  (see the v1 contract).
- Billing is not verified end to end. No `zc-usage` settlement has been observed for
  this operation.
