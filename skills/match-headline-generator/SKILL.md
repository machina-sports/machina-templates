# Match Headline Generator

Takes raw match facts and returns 5 differentiated headlines for various content team needs.

## When to use

Use this skill when you have structured data about a sports match and need a variety of headlines quickly. It provides several angles (neutral, analytical, fan-focused, clickbait) to cater to different audiences and platforms.

This contrasts with `match-stats-formatter`, which generates a single, neutral, prose-style summary of the match.

## Example Input (match object)

```json
{
  "home_team": "Manchester City",
  "away_team": "Arsenal",
  "score": "3-1",
  "scorers": [
    { "team": "Manchester City", "player": "K. De Bruyne", "minute": 7 },
    { "team": "Arsenal", "player": "B. Saka", "minute": 42, "type": "penalty" },
    { "team": "Manchester City", "player": "J. Grealish", "minute": 72 },
    { "team": "Manchester City", "player": "E. Haaland", "minute": 82 }
  ],
  "key_moments": [
    { "minute": 45, "description": "Yellow card for T. Partey (Arsenal)" }
  ],
  "xg": "Man City 2.1 - 0.9 Arsenal",
  "possession": "Man City 36% - 64% Arsenal"
}
```

## Example Output (array of headlines)

```json
[
  {
    "perspective": "neutral_news",
    "headline": "Manchester City defeat Arsenal 3-1 in a decisive clash"
  },
  {
    "perspective": "analytical",
    "headline": "Despite Arsenal's 64% possession, Man City's clinical finishing proves superior"
  },
  {
    "perspective": "winning_team_fan",
    "headline": "City on top! De Bruyne, Grealish, and Haaland secure massive win over Gunners"
  },
  {
    "perspective": "losing_team_fan",
    "headline": "Heartbreak for Arsenal as title hopes take a hit in 3-1 loss to City"
  },
  {
    "perspective": "clickbait",
    "headline": "Did Arsenal just bottle the league? City's dominant display says it all"
  }
]
```
