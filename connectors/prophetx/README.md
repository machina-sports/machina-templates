# ProphetX Affiliate API connector

Authenticated, **read-only** market data from the ProphetX betting exchange
(tournaments, sport events, markets with odds and per-level liquidity), plus
official **Auto-Fill** deep links for bet-slip handoff. Machina never places,
modifies, or cancels wagers — the write surface (MM/ISV APIs) is intentionally
not implemented. Design: `docs/plans/2026-08-13-001-feat-prophetx-affiliate-connector-design-log.md`.

## Environments (fixed allowlist — arbitrary endpoints rejected)

| environment | Base URL |
|---|---|
| `sandbox` (default) | `https://api.sandbox.prophetx.dev/partner` |
| `production` | `https://cash.api.prophetx.co/partner` |

Note: the pre-2026 sandbox domain (`*-ss-sandbox.betprophet.co`) is dead.

## Credentials (vault only)

Store as two logical connections — `prophetx-affiliate-sandbox` and
`prophetx-affiliate-production` — and reference via context variables. Never
commit or log token values.

- **Mode A (single API key):** `MACHINA_CONTEXT_VARIABLE_PROPHETX_API_KEY` —
  sent in the `Authorization` header. Default is the **raw key without
  `Bearer`** (per the official Market Data guide); the spec text contradicts
  this, so `auth_scheme: bearer` is available as an opt-in and the sandbox
  smoke reports which one the environment accepts.
- **Mode B (login session):** `MACHINA_CONTEXT_VARIABLE_PROPHETX_ACCESS_KEY` +
  `..._SECRET_KEY` → `POST /auth/login` → access token (10-minute expiry,
  cached in-process, refresh-then-relogin on expiry, one re-login on 401).
- `MACHINA_CONTEXT_VARIABLE_PROPHETX_PARTNER_ID` — Auto-Fill attribution id.

## Commands

| Command | Purpose |
|---|---|
| `get_tournaments` | Tournaments (optionally only those with active events) |
| `get_sport_events` | Events by `tournament_id` (MLB=109, NFL=31, NBA=132, NHL=234) or explicit `event_ids` |
| `get_markets` | Markets for one event — `api_version` v1–v4, default **v3** (liquidity levels); v4 = CFTC naming mapped onto the same neutral fields; `cftc_terminology: true` sends the v3 opt-in header |
| `get_multiple_markets` | Markets for up to **50** events per call; tolerates the documented dual-shape response (dict keyed by event id OR flat list) |
| `build_autofill_link` | Pure: `line_id(s)` + `partner_id` (+ optional odds) → official app/OneLink/web handoff links |
| `health` | One bounded authenticated GET — credential + reachability check |

Normalized records preserve `_raw`, keep `line_id` **verbatim** (it is the
Auto-Fill handoff currency), and do **not** derive implied probability yet —
official examples disagree on the odds format (American vs decimal) and the
sandbox smoke settles it before any conversion is added.

Upstream limits honored: 50 req/s account budget (client backs off on 429 and
honors `Retry-After`), `event_ids` ≤ 50, no pagination on this API.

## Verify

```bash
# offline unit tests (no network, no credentials)
python3 -m pytest connectors/prophetx/tests/ -q

# bounded sandbox smoke (~8 GETs; requires the sandbox key in the environment)
PROPHETX_API_SANDBOX=... python3 connectors/prophetx/tests/smoke_sandbox.py

# in-platform credential check (after vault setup)
# run workflow: prophetx-test-credentials   (health, sandbox by default)
# run workflow: prophetx-market-discovery   (events + v3 markets)
```

The production smoke is read-only, bounded, and **separately approved** —
`python3 connectors/prophetx/tests/smoke_sandbox.py --environment production`
only after that approval.
