# NFL Workload

Derived NFL fantasy opportunity metrics and roster context, plus a start/sit
explainer grounded strictly in those numbers.

No third-party projections or consensus rankings exist on this platform, so
opportunity is **derived** from nflverse play-by-play rather than consumed:
target share, air yards share, WOPR, rush share, red-zone touches, EPA per
opportunity, and a recent-window-vs-season trend.

The organising principle throughout is that **an answer must say what it does
not know**. An absent name, an ambiguous surname, a week ESPN cannot describe,
and a traded player's team split are all reported in the payload rather than
papered over.

## What it does

1. **Workload** (`nflverse` play-by-play via `nflreadpy`, read directly rather
   than through the sports-skills wrapper so `air_yards`, `epa`, `yardline_100`
   and receiver/rusher ids survive intact across a season)

   - `generate_workload_report` — the ranked leaderboard for a
     (season, through_week, position).
   - `get_player_workload` — one player's row out of that same report, built
     unfiltered so a real but low-usage player is not reported as missing.
   - `get_player_pair_workload` — two players off a **single** season load. The
     load dominates runtime, so calling the single-player command twice pays
     full price to learn nothing new (measured ~54 ms per pair call against
     ~53 ms per single call).

2. **Context** (ESPN via `sports-skills`)

   - `get_player_context` — depth-chart role and injury status for one player on
     one team. Resolves the team through `get_teams()` **first**, then narrows
     the league-wide injury feed to that team before matching any name, so a
     same-surname player on another roster cannot answer for this one.

3. **Explanation** — `fantasy-explain-reasoning` resolves two players, enriches
   each with context, and asks `fantasy-explain-prompt` for a start/sit call
   with explicit caveats.

## Four things that are easy to get wrong

**Traded players hold one row per team.** Usage is grouped on
`(player_id, team)`, so a name alone does not name a row. Supply `team`
(`player_a_team` / `player_b_team` on the pair command) to scope to a stint;
omit it and the busiest stint wins, tie-broken on the most recent week. Either
way the response carries `selected_team` and `other_stints`, so the choice is
visible. Rashid Shaheed's 2025 week 17 lookup returns his NO stint — 68 of 100
opportunities — and says so.

**A shared `team` on the pair command is refused.** One team cannot scope two
players, and quietly applying it to both would answer about the wrong roster.
`get_player_workload` takes `team` because it resolves one name.

**Misses are data, not errors.** A `not_found` or `ambiguous` query returns
`status: True` with an explicit `reason`, `message` and `candidates`. This is
operational, not stylistic: these commands run under `continue_on_error`, which
preserves a `status: True` payload and **discards the message** of a
`status: False` one. Reporting a miss as `False` made *"'Brown' matches five
players"* and *"Mahomes is not in this report"* arrive downstream as the same
empty output.

**Context is current-state only.** ESPN's depth-chart and injury endpoints serve
present state; there is no historical equivalent. Pass `season` and `week` and
the command checks them against the live coordinate from `get_scoreboard()`,
returning `reason: "historical"` rather than stapling today's roster onto a past
week. Omit them and the previous current-state behaviour is preserved exactly.

## How to run

```bash
# Leaderboard, and store it
POST /workflow/executor/nfl-workload-report
{ "season": 2025, "through_week": 17, "position": "WR",
  "min_opportunities": 10, "limit": 5 }

# Read back what was stored (computes nothing, writes nothing)
POST /workflow/executor/nfl-workload-latest
{ "season": 2025, "week": 17, "position": "WR" }

# Start/sit call
POST /workflow/executor/fantasy-explain-reasoning
{ "season": 2025, "week": 17, "position": "WR",
  "player_a_name": "Shaheed", "player_b_name": "Chase" }
```

`nfl-workload-report` upserts on name **plus metadata**, so each distinct
(season, week, position) becomes its own document row rather than overwriting a
single rolling doc. Readers should filter on `metadata.season` / `metadata.week`
/ `metadata.position`, or sort `updated` descending.

## Dependencies

`_PIP_PACKAGES` pins exact versions (`nflreadpy==0.1.5`, `polars==1.43.2`) and
the bootstrap **enforces** them: the gate compares each pinned package's
resident `__version__` against its pin and treats a mismatch as absence, so the
pin holds on a warm pod as well as a cold one. The `sys.modules` purge covers a
package's private compiled runtime — polars loads its binary from
`polars-runtime-32`, imported as `_polars_runtime_32` — because a reinstall that
left the old binary cached produced `Polars binary is missing!` while pip
reported success.

Every response carries `deps: {nflreadpy, polars}` **as actually loaded**, so
the build that computed a number is visible in the number's own payload rather
than inferred from call latency. On `get_player_context` read it as the worker's
state, not what produced the answer: that command touches neither package and
skips the bootstrap.

## Regression suite

Five self-asserting workflows. Each exposes a `result` output of `PASS` / `FAIL`
computed from individual `assert_*` booleans, so a runner reads one field and
gets the detail for free when it fails.

| workflow | asserts |
|---|---|
| `test-historical-week` | Chase/Olave at 2025 wk17 both return `reason: historical`, no role leaks |
| `test-ambiguous-name` | `Brown` yields exactly 5 candidates; Chase still resolves alongside it |
| `test-duplicate-alias` | Michael Wilson collapses to one ARI row of 118 opportunities, `other_stints` empty |
| `test-traded-player` | `selected_team` differs NO/CIN; caveat names the 68-of-100 split; every cited Shaheed figure carries a stint marker |
| `test-missing-inputs` | `season` without `week` fails closed naming **both** parameters |

Two caveats a runner must respect:

- **`test-traded-player` layer 3 is LLM-enforced.** Assertions are
  *substring*-based on `stint`, not exact strings: phrasing varies run to run
  (`"0.305 (Shaheed's NO stint)"` vs `"(0.305, NO stint)"`) while the marker
  does not. Three consecutive passes were observed; that is evidence, not
  proof. Treat a single failure as worth re-running before calling it a
  regression.
- **`test-missing-inputs` is only partly self-asserting.** It runs with
  `continue_on_error: false` on purpose, because `continue_on_error` discards a
  `status: False` message and the message is the point. The workflow therefore
  **fails by design**, and `result` reads `PASS-partial`. The message lives in
  `tasks[0].audit.reason` and `outputs['workflow-error'].message` — a runner
  must read the execution record rather than trusting `result`.

## Limitations

- **No historical roster context.** Serving past weeks properly needs a source
  that carries history; ESPN's endpoints cannot. The temporal gate refuses the
  question instead of answering the wrong one, which means that during the
  offseason *every* context lookup is `historical` and the depth-chart and
  injury paths are unreachable until `season.type` flips to 2.
- **A traded player's row is one stint, not a season.** `other_stints` discloses
  what is excluded, but the metrics themselves are not summed across stints —
  by design, because shares computed against two different team denominators do
  not add.
- **Deltas are null where windows do not align.** A stint the recent window does
  not cover gets `null` trend deltas rather than a cross-team number. Downstream
  arithmetic must handle `None`.
- **`sports-skills` User-Agent stopgap.** The connector patches a spoofed
  browser UA that ESPN 403s. Fixed upstream in `sports-skills` 0.30.0 (commit
  `e6a5870`, #101); the block becomes a silent no-op there and can be removed
  once the pod pins `>=0.30.1`.

## Related

- `connectors/sports-skills` — the ESPN/nflverse wrapper this connector
  deliberately bypasses for play-by-play (see the DEVIATION note in the source).
- `skills/manifest-generator` — the pyscript-in-a-skill packaging precedent this
  package follows.
