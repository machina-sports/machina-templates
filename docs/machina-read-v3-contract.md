# Machina Read v3 contract

Fixed contract shared between the native `machina-read` workflow package and the
website consumer. It is not negotiable per deployment: a producer that cannot
satisfy it fails closed and stores nothing.

## Stored value

Valid editions are stored as native documents named `machina-read-edition`, with
metadata `edition_date` (UTC `YYYY-MM-DD`) and `source: machina-read-native-v3`.

```jsonc
{
  "schemaVersion": 3,
  "status": "available" | "partial",
  "publicApproved": true,                  // boolean admission, never a string
  "editionDate": "YYYY-MM-DD",             // UTC day of generation
  "scope": "string, <= 160 chars",
  "observedAt": "ISO 8601 UTC with milliseconds, Z suffix",
  "generatedAt": "ISO 8601 UTC",
  "expiresAt": "ISO 8601 UTC, at most 24h after observedAt",
  "story": {
    "headline": "<= 80 chars",
    "body": "<= 320 chars",
    "sourceIds": ["source ids"],
    "points": [                            // 2..3 entries
      { "text": "<= 350 chars", "sourceIds": ["source ids"] }
    ]
  },
  "sports":  [ { "id": "football", "label": "Football (soccer)" } ],   // 2..9
  "sources": [                                                        // 2..24
    {
      "id": "string <= 100",
      "sport": "one of sports[].id",
      "kind": "event" | "market" | "news headline",
      "label": "<= 180",
      "text": "<= 1800",
      "url": "https URL from the allowlist below",
      "observedAt": "ISO 8601 UTC",
      "publishedAt": "ISO 8601 UTC"        // optional, news headlines only
    }
  ],
  "engine": { "router": "machina-ai", "model": "gemini-3.5-flash-lite", "provider": "vertex_ai" },
  "marketSnapshots": [ /* <= 24 compact provider quotes */ ],
  "coverage": [ { "sport": "...", "status": "available" | "unavailable", "reason": "..." } ]  // <= 12
}
```

## Native projection

The value returned by `machina-read-produce-daily` and `machina-read-get-latest`
is the stored value with exactly three operator-only keys removed:
`publicApproved`, `marketSnapshots` and `coverage`. Nothing else is renamed,
reshaped or recomputed on read. There is no `teams` field in v3; team identity is
carried inside each source's `label` and `text` exactly as the provider
normalized it, and no cross-provider identity crosswalk is constructed.

## Invariants enforced before storage

- Every `sources[].sport` is one of the ids listed in `sports`.
- Allowed sport ids: `football`, `americanfootball`, `baseball`, `basketball`,
  `hockey`, `tennis`, `motorsport`, `golf`, `cricket`.
- Every citation in `story.sourceIds` and `story.points[].sourceIds` resolves to
  a retained source, and the union of cited sources covers **at least two**
  different sports. This is a deterministic check on cited source sports, not a
  judgement about the prose.
- Only cited sources (and their sports and market snapshots) are retained. Every
  other collected candidate is discarded.
- Numbers in the headline and body must appear in the sources that the headline
  and body themselves cite; numbers in a point must appear in the sources that
  the point cites. The permitted pool is built from source `text` and `label`
  only, so identifiers and URLs cannot launder a figure. No model arithmetic.
- When any market source was collected, at least one market source must be cited.
- A distinctive league or sport token in the prose (`NFL`, `NBA`, `MLB`, `NHL`,
  `ATP`, `PGA`, `F1`, `cricket`, ...) must belong to a cited sport.
- `finish_reason` must be `stop`, there must be no tool calls, and the reply must
  parse as the exact JSON object above with no extra fields.
- `publicApproved` is `true` only when the caller passes boolean `publish_public:
  True`. Anything else, including the string `"True"`, stays private.

## URL allowlist

HTTPS only, no credentials, no port and no fragment.

| Host | Allowed path prefixes |
| --- | --- |
| `www.espn.com` | `/nfl/`, `/nba/`, `/wnba/`, `/mlb/`, `/nhl/`, `/college-football/`, `/mens-college-basketball/`, `/soccer/`, `/tennis/`, `/golf/`, `/f1/` |
| `news.google.com` | `/rss/articles/` |
| `polymarket.com` | `/event/` |
| `kalshi.com` | `/markets/` |

Provider-observed URLs are used where the provider supplies one. ESPN event links
are derived deterministically from the observed event id and league.

## Status and coverage

`coverage` reports, per sport, whether that module produced **usable recent
evidence** in this run. It is not a transport health signal: a provider call that
succeeded but returned only off-season, stale or unverifiable rows is reported
`unavailable`. `status` is `available` only when every listed sport is covered,
and `partial` otherwise, which is the normal outcome on a single day.

## Cache and expiry

`machina-read-get-latest` and the producer's cache probe admit a stored edition
only when it is `schemaVersion: 3`, `publicApproved: true`, unexpired, and
(producer only) from the current UTC day. Reads never rewrite `expiresAt`, never
extend a TTL and never renew provider timestamps. A `schemaVersion: 2` MLB
edition can never satisfy a v3 read.
