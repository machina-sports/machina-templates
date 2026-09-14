# Soccer v4 authentication

The official contract uses `x-api-key` in the request header:
https://developer.sportradar.com/getting-started/docs/authentication

The security scheme is named `api_key` because the Machina REST executor
resolves credentials by **scheme name** from the connector context. Existing
workflows keep `sportradar-soccer.api_key` and the existing secret binding.
The wire header is `x-api-key`; the key must not be a query parameter.

The production server URL, endpoint paths, IDs and non-auth parameters are
unchanged. Existing installations with an explicit trial URL retain that
access level during a scoped update. Do not switch access levels as a guess.

## Verification and remaining access failure

On 2026-09-14 the central Entain instance rejected all of these read-only
requests with HTTP 403, including requests made directly with the documented
header, independent of the installed REST schema:

| Request | trial | production |
| --- | --- | --- |
| `competitions.json` | 403 Authentication Error | 403 |
| `seasons/sr:season:137706/schedules.json` | 403 | 403 |
| `sport_events/sr:sport_event:66886998/summary.json` | 403 | 403 |

The event is Flamengo–Corinthians, scheduled for 2026-09-13. The season schedule
is a valid source of scores and status according to the official contract:
https://developer.sportradar.com/soccer/reference/soccer-season-schedule

Header migration alone does **not** demonstrate restored access. Revalidate
the application's Soccer v4 entitlement/key in the provider console, then run
`sportradar-soccer-test-credentials`, the season refresh and the tenant mirror.
Require a successful provider response and fresh score/status values in both
documents before closing the ingestion incident. A document timestamp changed
by odds refresh or mirroring is not evidence of fresh scores. Never include
keys in tickets or logs.

Run the credential-free regression check with:
`python -m unittest discover -s connectors/sportradar-soccer/tests -v`
