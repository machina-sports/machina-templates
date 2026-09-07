---
output_kind: html
entry: index.html
---

# Brasileirão 2026 Dashboard

Static HTML dashboard rendering mock Brasileirão 2026 data with Chart.js (loaded via CDN). Drop-in page — no build step, no backend.

## What it shows

1. **Top 10 artilheiros** — bar chart of goals per player.
2. **Aproveitamento por time** — horizontal bar chart of points percentage.
3. **Gols pró × gols sofridos** — scatter plot, one point per team.
4. **Gols por rodada** — line chart of total goals across the rounds played so far.

## Data

All values are mock / plausible — Flamengo, Palmeiras, Corinthians, Botafogo, São Paulo and friends. Edit the `DATA` constant at the top of `index.html` to wire real data later.

## Theme

Dark background, accent color `#fe591f`, responsive CSS grid (1 column on mobile, 2 columns on desktop).

## How to use

Open `index.html` in any modern browser, or serve the folder statically:

```bash
python3 -m http.server -d skills/brasileirao-2026-dashboard 8080
```

Then visit http://localhost:8080.
