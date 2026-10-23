# ProphetX Affiliate API Connector + Direct Play Demo — Design Log

> **Status: PROPOSED — approval gate.** Per ClickUp `86ak0a1jm` acceptance
> criteria, implementation does not start until this design log is approved
> (this document's PR review is the approval mechanism). No code in this PR.

**Goal:** a Machina connector for the ProphetX **Affiliate API** (authenticated,
read-only market data with odds/liquidity) plus a demo where a user browses
sandbox markets on an odds screen and launches the official ProphetX handoff —
**Machina never executes a wager**.

**Companion (already delivered, separate track):** keyless read-only
`sports_skills.prophetx` catalog skill (machina-sports/sports-skills,
branch `feat/prophetx`). Live verification there proved the public surface
exposes **no odds** — odds/liquidity exist only behind this authenticated API,
which cleanly justifies both tracks.

---

## 1. Findings that correct the task brief (verified 2026-08-13)

1. **The sandbox host in the brief is dead.** `partner-docs-ss-sandbox.betprophet.co`
   CNAMEs to a removed CloudFront distribution (NOERROR, zero A/AAAA on 8.8.8.8
   and 1.1.1.1). The sandbox moved to `*.sandbox.prophetx.dev`:
   - Swagger UI: `https://partner-docs.sandbox.prophetx.dev/swagger/affiliate/index.html`
   - Spec JSON: `https://partner-docs.sandbox.prophetx.dev/swagger/affiliate/doc.json`
   - API host: `api.sandbox.prophetx.dev`, basePath `/partner`
   (Official "Market Data Integration" guide §2 confirms the new domain; its §7
   still shows the old host in examples — upstream doc inconsistency.)
2. **The Medium "Direct Play" guide is legacy and non-compliant for us.** The
   flow it describes is NOT a deep link: the partner manages a ProphetX user
   session (email/password login → private `/api/v1/auth/login`), runs
   GeoComply, and **POSTs the wager itself** to a private endpoint
   (`/trade/private/api/v2/wagers`) — reverse-engineered ("open the network
   tab to get more details", the article says), and it even hardcodes a leaked
   Customer.io `Authorization: Basic` credential. Executing wagers is
   explicitly forbidden by this task ("Machina must not execute a wager/trade
   itself"). **Decision: the demo handoff uses the official Auto-Fill deep
   links instead** (docs.prophetx.co "Auto-Fill Integration Guide",
   2026-08-04): `prophetx://addtobetslip?line_id={line_id}&line_ids={line_ids}&partner_id={partner_id}&odds={odds}`,
   the OneLink wrapper (app-store fallback), and the web fallback
   `https://www.prophetx.co/?action=addtobetslip&...` — attribution via
   `partner_id`, no user session on our side, no wager execution.
3. **Public catalog has no odds** (verified live incl. an in-progress MLB game
   with 89 active markets — all selections `[null,null]`). The Affiliate API's
   `Selection` carries `odds`, `stake`, `line_id` — it is the odds source.

## 2. API facts (from the official specs, pinned copies saved)

- **Spec:** Swagger 2.0, title "External Affiliate API"; sandbox and prod specs
  are **identical except `host`** (`api.sandbox.prophetx.dev` vs
  `cash.api.prophetx.co`), basePath `/partner`. 47 `$ref`s, **0 dangling, 0
  orphans** (validated) — but the 4 `*ListWithMultipleEventResponse*` schemas
  are empty `{"type":"object"}`; the real shape (per the official guide) is a
  dict keyed by event_id **that may occasionally arrive as a flat list** →
  defensive dual-shape parsing is mandatory.
- **Endpoints (10, all GET — zero write surface):**
  `/affiliate/get_tournaments` (`has_active_events`),
  `/affiliate/get_sport_events` (`tournament_id`, `event_ids[]`),
  and `get_markets` + `get_multiple_markets` in **v1/v2/v3/v4**
  (`event_id` required; `get_all_market`, `market_types` CSV, `min_liquidity`).
  Known tournament ids documented upstream: MLB=109, NFL=31, NBA=132, NHL=234.
- **Versions:** v1 flat selections (deprecated per guide); v2 adds
  category/sub_type/player_id; **v3 recommended** — `selections` is
  array-of-arrays (per-side groups, each group = liquidity levels =
  order-book depth); **v4 = CFTC naming** (`strike_id`≙line_id, `price`≙odds,
  `strike`≙line, `quantity`≙stake). Opt-in header `X-CFTC-Terminology: true`
  exists on v3 (documented only in the Auto-Fill guide).
- **Auth:** `securityDefinitions` = apiKey named `Authorization` (header) on
  all 10 endpoints. Two documented modes: (A) single raw API key in the
  header — guide says **"No `Bearer` prefix — just the raw key"**; (B)
  `access_key`+`secret_key` → `POST /partner/auth/login` → `access_token`
  (**expires in 10 minutes**) + `refresh_token` (`POST /partner/auth/refresh`);
  guide says tokens are not auto-refreshed — on 401, login again. **Documented
  contradiction:** the spec's own description says `Bearer ACCESS_TOKEN` while
  the guide forbids the prefix → the connector makes the prefix configurable
  and the sandbox smoke resolves it empirically. Caps: 20 key pairs, 20
  concurrent sessions (403 `keypair_num_exceed` / `session_num_exceed`).
- **Pagination: none** on the Affiliate API (no page/limit/cursor anywhere);
  `event_ids` batches capped at **50** (`market_event_limit_exceeded`).
- **Rate limit:** `rate_limit_reached` → 429, "up to 50 requests per second";
  backoff guidance in the guide; limit negotiable with ProphetX.
- **Errors:** `{error, message}`; endpoints declare 200/400/500 but the error
  table includes 401/403/404/429 — handle all. Relevant codes:
  `invalid_request`, `unauthorized`, `data_not_found`, `rate_limit_reached`,
  `market_invalid_event`, `market_event_limit_exceeded`, `sport_event_not_found`.
- **Gotchas to validate in the sandbox smoke:** `updated_at` appears to be
  epoch **nanoseconds** in official examples; odds format is shown as American
  (`price: -470`) in one guide and called "decimal price" (`1.95`) in another
  — resolve per version empirically; prod host duality (`cash.api.prophetx.co/partner`
  in the spec vs `api.prophetx.co` in the Auto-Fill guide) — treat the spec's
  host as canonical until the smoke proves otherwise.
- **Real-time:** none on the Affiliate surface (polling only). Pusher
  websockets belong to the **Market Maker** API; webhooks belong to the
  **ISV** API — both are different credentials/partnerships, out of scope.

## 3. Connector design (machina-templates)

- **Shape:** pyscript connector `connectors/prophetx/` (`prophetx.py` +
  `prophetx.yml` + `_install.yml` + `test-credentials.yml` + `tests/`).
  Pyscript (not declarative JSON) because of the dual-mode auth, 10-minute
  token refresh, dual-shape multiple-markets parsing, and v3 nested
  selections normalization.
- **Commands (read-only):** `get_tournaments`, `get_sport_events`,
  `get_markets` (default **v3**; `api_version` option v1–v4 with
  `X-CFTC-Terminology` opt-in on v3), `get_multiple_markets` (≤50 ids,
  dual-shape tolerant), `build_autofill_link` (pure function: line_id(s) +
  partner_id + odds → the three official Auto-Fill URLs; no network), `health`.
  **No wager/order/balance commands — they don't exist on this API and would
  not be added anyway.**
- **Normalization:** provider-neutral market schema shared with the
  sports-skills track (event/tournament ids+names, sport, scheduled ISO-8601,
  status, market id/type/subtype, selections with odds + available `stake`
  per liquidity level, `line_id`/`strike_id` preserved verbatim — it is the
  handoff currency — plus `_raw`, source URL, retrieval timestamp). v4 CFTC
  field names mapped onto the same neutral fields. No invented fields.
- **Credentials — vault only:** two logical connections,
  `prophetx-affiliate-sandbox` and `prophetx-affiliate-production`, each
  holding either the single API key or access/secret pair, referenced as
  `$MACHINA_CONTEXT_VARIABLE_PROPHETX_*` from operator config. Tokens are in
  André's Outlook email "ProphetX API Information" (Anthony Fradella,
  2026-01-05) — retrieved via secure handoff and entered into the vault by
  the operator. **Never in code, Git, ClickUp, chat, logs, screenshots, or
  generated artifacts.** Connector receipts/logs are sanitized (no header
  echo, no credential fragments).
- **Resilience:** conservative client-side budget well under 50 req/s;
  backoff+jitter on 429/5xx; fail-closed on 401 (one re-login attempt for
  mode B, then typed `credential_invalid`); typed empty-market and
  upstream-unavailable results; session reuse to respect the 20-session cap.
- **Repo guardrails:** committed workflows carry no credentials/endpoints
  (`scripts/check-no-openai.sh all` and `scripts/check-machina-ai-policy.py`
  stay green; this connector is sports-data, not an AI provider, so the
  machina-ai policy is untouched).

## 4. Demo design ("odds screen → handoff")

1. Workflow(s) in the connector template: sandbox market discovery
   (`get_tournaments` → `get_sport_events` → `get_markets` v3) rendering an
   odds screen (event, market, selections with odds/stake).
2. Each selection carries its `line_id` → `build_autofill_link` produces the
   official deep link (`prophetx://addtobetslip?...`), the OneLink wrapper,
   and the web fallback with our `partner_id` for attribution.
3. The user clicks out to ProphetX; account, geolocation, wallet, and wager
   placement are entirely ProphetX's. Machina's involvement ends at the link.
4. Demo script documents: sandbox first; the bounded read-only production
   smoke (few GETs, no user data) runs only after separate approval.
5. Failure-state coverage in the demo/tests: invalid credentials (401),
   rate limit (429 + backoff), empty markets, upstream unavailability (5xx),
   dual-shape multiple-markets response, empty-schema drift.

## 5. Validation plan

- **Unit (offline, CI):** mocked HTTP for auth modes (raw key / login+refresh
  / Bearer-prefix toggle), 401 re-login, 429 backoff, ≤50 batch enforcement,
  dual-shape parsing, v1–v4 normalization (incl. v4 CFTC renames and v3
  liquidity levels), sanitized errors, no-credential-in-receipt assertions.
- **Sandbox smoke (needs vault credentials):** login, tournaments → events →
  markets v3+v4, empirical resolution of the Bearer-prefix and odds-format
  questions, `updated_at` unit check, multiple-markets shape check.
- **Production smoke:** read-only, bounded (≤10 GETs), separately approved,
  after sandbox passes.

## 6. Open questions (blockers for implementation, answered by smoke or ProphetX)

1. Which prod host is canonical for partners: `cash.api.prophetx.co/partner`
   (spec) or `api.prophetx.co` (Auto-Fill guide)?
2. Bearer prefix or raw key (docs contradict each other)?
3. Odds format per version (American vs decimal)?
4. Our `partner_id` value for Auto-Fill attribution (request from
   ProphetX/Anthony if not in the credential email).
5. Do the shared tokens map to mode A (single key) or mode B (access/secret)?
   (Determines which auth path the smoke exercises first — the operator can
   see this from the email without pasting values anywhere.)

## 7. Rollout

PR 1 = this design log (approval gate) → PR 2 = connector + unit tests +
docs (no credentials) → operator loads vault connections → sandbox smoke
evidence attached to ClickUp → PR 3 = demo workflows/script → approved
bounded prod smoke → task closure with links/evidence.
