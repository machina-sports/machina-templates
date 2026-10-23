# fact-articles

Universal, fact-anchored sports article generator. Every sentence of an article cites the facts it
came from, and a verifier removes the ones that say anything those facts do not. Output is local
HTML/JSON only; nothing is published.

**pt-BR only in this phase.** Fact text, verifier rules and writer prompt are Portuguese; a client config
with any other `language` is refused with an error (`verify.require_ptbr`).

## How it works

| Step | File | What it does |
|---|---|---|
| fetch | `connectors/sports_skills_football.py` | one competition, a local date range -> dataset (`events`, `results`, `standings`) |
| 1 facts | `scripts/facts.py` | facts per match from the contract's kinds; missing mandatory fact -> connector error, no article |
| 2 rank | `scripts/rank.py` | `score` = how far the fact is from normal, from the fact's own value |
| 3 plan | `scripts/plan.py` | `norm` = score / best of the same kind in the round; each kind leads at most `lead_cap`; sections from the contract |
| 4 write | `scripts/write.py` | `write(facts_doc, client) -> article`; backend `claude-cli` (local). Prompt: `prompts/writer.md` |
| 5 verify | `scripts/verify.py` | deterministic rules, then an entailment judge (see below) |
| 6 publish | `scripts/publish.py` | failing sentences out, empty sections out, `removed` lists them |
| render | `scripts/render.py` | full HTML doc with JSON-LD |

Every script exposes plain functions plus `invoke_<step>(request_data) -> {"status", "data"|"message"}`
and a `.yml` (`filetype: pyscript`), the engine's connector convention. No engine workflow yet.

Writer input (what `prompts/writer.md` reads):
`{"facts": [{"id","kind","subject","text"}], "plan": {...}, "client": {...}}`.
The connector keeps only games not yet played: `not_started`/`scheduled`, `postponed`, `cancelled`,
`suspended`. Match fact `value.status` keeps that sports-skills word; anything but `not_started` is also
stated in the match fact text ("Partida adiada.", "Partida suspensa.").

## What the verifier checks

Every item the reader sees goes through it: headline, meta description, section titles, sentences.
The meta description cites every fact the article cites; a section title cites what its sentences cite.

Deterministic layer (always, offline):
- each headline/sentence cites 1 to 4 existing fact ids (the cap is also in `prompts/writer.md` rule 1);
- dates (`dd/mm`, `dd/mm/yyyy`), times (`HHhMM`), scores (`AxB`, either order) and numbers (comma decimals,
  digits, `15º`, number words up to 100, ordinals before a position noun such as "terceiro colocado"
  but not "primeira vitória/derrota/gol/jogo/ponto",
  "dois/duas/um/uma" only before a countable noun) appear as whole tokens in the cited facts' text.
  "Z-4"/"G-4" are terms. A dot decimal ("1.2") only matches itself;
- weekday (`-feira`, sábado, domingo) and month words appear in the cited facts; relative dates
  ("amanhã", "nesta sexta") fail;
- any team, venue or city the dataset knows needs a cited fact that names it (accent-insensitive). So a
  city or venue other than the match's fails, and so does the match's own without the match fact;
- a sentence naming only one of the two teams cites a fact about that team;
- headline and meta "A x B" keep the match fact's home x away;
- nicknames from `client.nicknames`, terms from `client.compliance.forbidden` (case-, accent- and
  invisible-character-insensitive), a pt-BR style blocklist and dashes (— – ―) fail; the headline also
  fails on generic words (prévia, duelo, confronto, "jogo em", "Série A em").

Entailment judge (one call per article, claude CLI isolated like the writer, model `client.verifier_model`,
default sonnet): every item that passed the first layer goes with the text of its cited facts; an item
the judge does not support fails. It is the net for reversed results, numbers given to the wrong team,
computed gaps, predictions ("placar provável"), betting advice ("vale a pena arriscar"), invented status,
a team called by a nickname, gentílico or colour, home and away swapped. Who won a game is the judge's call
only (a regex rule for it removed true sentences in two runs). The verdict is the LAST JSON in the reply;
no parseable verdict twice means no page (fail closed, `dropped` says why).
`round_report.json` `verifier_hash` covers this module's rules, the judge prompt and the judge model.
`local/judge_check.py` runs QA's false sentences through it.

What it does NOT check, without the judge: who won, nicknames outside the client list; a number that is present in
the cited facts but used for the wrong thing, without the judge (numbers are compared as a set per
sentence); bare weekdays ("sexta") outside a relative phrase; the judge's own errors (it is a model).

A failing sentence is removed. A failing headline, meta description or section title regenerates the
article once; failing again, the match gets no page and `round_report.json` says why (`dropped`).

## Run locally

From the worktree root (there is no `python` binary; uv brings the deps):

```sh
cd agent-templates/fact-articles
# facts and plan only, no writer
uv run --no-project --with sports-skills==0.33.0 --with pyyaml python local/run.py --from 2026-10-23 --to 2026-10-26 --offline
# full round: writer (claude CLI, sonnet), verify, publish, render
uv run --no-project --with sports-skills==0.33.0 --with pyyaml python local/run.py --from 2026-10-23 --to 2026-10-26
# --no-judge: deterministic layer only; --max-claude-calls N caps writer + judge calls (default 25)
# measures: anchored %, max lead-kind share, blind identification (judge via claude CLI)
uv run --no-project --with pyyaml python local/measure.py <out_dir>
# tests (offline)
uv run --no-project --with pytest --with pyyaml python -m pytest tests -q
```

Output goes to `output_dir/<client>/<from>_<to>/`: `<event_id>.{facts,article,verify,pub}.json`, `.html`,
`dataset.json`, `round_report.json` (with the verifier's hash: rules stay frozen during a run),
`measure.json`.

Blind identification (`measure.py`): from each published article it drops the headline, the meta
description and every sentence citing the match fact, and replaces both team names (short names as in the
facts) with TIME_A/TIME_B and the venue/city with ESTADIO/CIDADE. Opponents named in other facts stay. The
judge gets the non-match facts of every match in the round and must name the match.

## A new client

1. `clients/<name>.yml`: copy `demo-ptbr.yml`. Keys: `site_name`, `language`, `author`, `data_source_label`,
   `disclosure`, `client`, `connector`, `contract`, `sport`, `verifier_model`, `competition_id`, `competition_name`,
   `timezone_offset_hours`, `timezone_label`, `relegation_spots`, `nicknames` (regex), `compliance.forbidden`
   (regex), `writer`, `output_dir`.
2. Another data source: a connector returning the same dataset shape.
3. Another article type or sport: a contract in `contracts/` plus fact builders and scorers for its kinds.
