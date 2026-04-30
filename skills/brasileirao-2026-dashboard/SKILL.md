---
output_kind: html
entry: index.html
---

# Brasileirão 2026 Dashboard

Static, self-contained HTML dashboard that renders four charts about the 2026
Brazilian football league using mock data embedded directly in the page.

## What it ships

A single file — `index.html` — that loads Chart.js from a public CDN and
renders a dark-themed responsive dashboard with the platform accent color
`#fe591f`.

## Charts

1. **Top 10 artilheiros** (vertical bar) — leading scorers and their goal
   counts.
2. **Aproveitamento por time** (horizontal bar) — points won as a percentage
   of points disputed, sorted from best to worst.
3. **Gols pró × sofridos** (scatter) — one point per club, plotting goals
   scored against goals conceded.
4. **Total de gols por rodada** (line) — total goals per round across all
   matches.

## Teams covered

Flamengo, Palmeiras, Corinthians, Botafogo, São Paulo, Fluminense,
Internacional, Grêmio, Atlético-MG, Cruzeiro.

## How to use

Open `index.html` in any modern browser, or serve the folder over HTTP. The
page is fully static — no build step, no server, no external data calls
beyond the Chart.js CDN script tag.

All data is illustrative (mock) and lives inline in the `<script>` block
near the bottom of the file. Edit those arrays (`SCORERS`, `STANDINGS`,
`GOALS_PER_ROUND`) to update the charts.

## Layout

A 12-column responsive CSS grid. Each chart sits in a card spanning 6
columns on desktop and collapses to 12 columns under 980px width. Dark
background (`#0c0d10`), card surfaces (`#15171c`/`#1c1f26`), accent
(`#fe591f`).
