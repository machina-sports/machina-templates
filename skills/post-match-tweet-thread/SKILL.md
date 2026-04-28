# Post-Match Tweet Thread Skill

Receives a raw match object and returns a structured 5-tweet thread in
Brazilian Portuguese ready to be scheduled on the team's social account.

## Workflow: `generate-tweet-thread`

Takes a single input `match_data` (a JSON object with the match facts)
and returns a thread of exactly 5 perspective-tagged tweets. Each tweet
is character-counted server-side so the publisher doesn't have to.

### Tweet positions

| # | role             | content angle                                            |
|---|------------------|----------------------------------------------------------|
| 1 | hook             | placar + momento decisivo, gancho pra reter o leitor     |
| 2 | key_moment       | gol/lance mais importante com contexto narrativo         |
| 3 | stat_spike       | número que surpreende (xG, distância percorrida, posse)  |
| 4 | talking_point    | controvérsia / debate (arbitragem, escalação, lance)     |
| 5 | call_to_action   | próximo jogo, engajamento ("conta pra gente…")            |

### Inputs

- `match_data` (object): payload da partida. Mínimo: `home_team`,
  `away_team`, `score`, `scorers[]`. Extras opcionais que melhoram o
  resultado: `key_moments[]`, `xg`, `possession`, `competition`,
  `next_match`.

**Example input:**

```json
{
  "competition": "Brasileirão Série A",
  "home_team": "Palmeiras",
  "away_team": "Corinthians",
  "score": "2-1",
  "scorers": [
    { "name": "Estêvão", "minute": 22, "team": "Palmeiras" },
    { "name": "Yuri Alberto", "minute": 58, "team": "Corinthians" },
    { "name": "Endrick", "minute": 89, "team": "Palmeiras" }
  ],
  "key_moments": [
    { "minute": 71, "type": "red_card", "player": "Cacá", "team": "Corinthians" }
  ],
  "xg": { "Palmeiras": 2.4, "Corinthians": 1.1 },
  "possession": { "Palmeiras": 58, "Corinthians": 42 },
  "next_match": { "team": "Palmeiras", "vs": "São Paulo", "when": "domingo" }
}
```

### Outputs

```json
{
  "tweet_thread": {
    "thread": [
      { "position": 1, "role": "hook",            "tweet": "...", "char_count": 144 },
      { "position": 2, "role": "key_moment",      "tweet": "...", "char_count": 220 },
      { "position": 3, "role": "stat_spike",      "tweet": "...", "char_count": 178 },
      { "position": 4, "role": "talking_point",   "tweet": "...", "char_count": 199 },
      { "position": 5, "role": "call_to_action",  "tweet": "...", "char_count": 132 }
    ]
  },
  "workflow-status": "executed"
}
```

### Tone rules

- Brazilian Portuguese, voz informal de torcedor sem ser chapa-branca.
- Cada tweet ≤ 280 caracteres; o `char_count` retornado é checado pelo
  prompt antes de emitir.
- Sem emojis em sequência (no máximo 1 por tweet); sem hashtags
  artificiais.
- Não inventar estatísticas: se o campo não veio em `match_data`, não
  use o número.

## When to use vs siblings

| Use this skill when…             | Use the other one instead                                |
|----------------------------------|----------------------------------------------------------|
| You need a thread for X/Twitter  | `match-stats-formatter` for plain-prose chat summaries   |
| Output should be Brazilian PT    | `match-headline-generator` for English headline variants |
| You want 5 perspective-tagged    | (single-shot caption tools — not in this repo yet)       |
