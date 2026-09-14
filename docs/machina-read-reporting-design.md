# Machina Read reporting connector

`machina-read-reporting` is a narrow native connector for public ESPN Story API
reporting. It accepts one of nine Machina Read sport IDs and maps that ID to one
fixed `https://now.core.api.espn.com/v1/sports/.../news?limit=3` path. Callers
cannot supply a URL, endpoint, proxy, redirect policy, or credential.

The connector disables environment proxies, refuses redirects, times out after
six seconds, and reads at most 262,144 response bytes. It accepts only current,
non-premium `Story` or `HeadlineNews` records whose public web URL is an HTTPS
`www.espn.com` story path for the requested sport and contains the same numeric
article ID. `HTMLParser` removes `script`, `style`, and `embed` content. Plain
article text is capped at 6,000 characters and carries a visible truncation
notice when shortened. Failures use the native `{status, data|message}` envelope
and expose stable error types rather than exception details.

The connector only collects and normalizes. `machina-read-multisport` remains a
pure no-I/O transform: it validates the normalized shape again, emits `article`
evidence only for v4, builds bounded article-first candidate packets, and binds
publication citations and numbers to the selected packet. V3 behavior and
stored v4 cache admission remain unchanged. A reporting failure or a pool made
only of RSS headlines produces no new edition, so the existing stored edition
is not overwritten.
