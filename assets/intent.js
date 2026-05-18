// Intent parser — maps a freeform headline prompt to a structured query
// the data layer can execute. Keyword-heavy, no ML, lives in the browser.
//
// Returns: { intent, label, opponent?, range? }
//
// Intents:
//   schedule  → "Next 5 games", "upcoming fixtures", "next match"
//   results   → "Last 10 results", "recent form", "past games"
//   h2h       → "Head-to-head vs the Lakers"
//   leaders   → "Top scorers", "leading goalscorers", "best passer"
//   standings → "Where they sit", "league table", "current position"
//   stats     → fallback / catch-all "this month", "this season"

import { TEAMS } from "./teams.js";

const NUMBER_WORDS = { one:1, two:2, three:3, four:4, five:5, six:6, seven:7, eight:8, nine:9, ten:10 };

function extractNumber(text) {
  const digit = text.match(/\b(\d{1,3})\b/);
  if (digit) return parseInt(digit[1], 10);
  for (const [w, n] of Object.entries(NUMBER_WORDS)) {
    if (new RegExp(`\\b${w}\\b`, "i").test(text)) return n;
  }
  return null;
}

function findOpponent(text, selfId) {
  const lower = text.toLowerCase();
  // Try full names first (longer = more specific)
  const candidates = [...TEAMS].sort((a, b) => b.name.length - a.name.length);
  for (const t of candidates) {
    if (t.id === selfId) continue;
    if (lower.includes(t.name.toLowerCase())) return t;
  }
  // Fallback: short codes (only if at least 3 chars, to avoid false-positive)
  for (const t of candidates) {
    if (t.id === selfId) continue;
    if (t.short.length < 3) continue;
    if (new RegExp(`\\b${t.short.toLowerCase()}\\b`, "i").test(lower)) return t;
  }
  return null;
}

export function parseIntent(prompt, teamId) {
  const p = (prompt || "").toLowerCase().trim();
  if (!p) return { intent: "schedule", label: "Upcoming fixtures", count: 5 };

  // Head-to-head (look for opponent first; "vs", "against", "versus")
  if (/\b(vs\.?|versus|against|head[\s-]to[\s-]head|h2h|rivalry)\b/.test(p)) {
    const opponent = findOpponent(p, teamId);
    return {
      intent: "h2h",
      label: opponent ? `Head-to-head vs ${opponent.name}` : "Head-to-head record",
      opponent,
      count: extractNumber(p) || 5,
    };
  }

  // Leaders / top scorers / leading
  if (/\b(top\s+(scorer|scorers|goalscorers|points|passer|rebounders|assists)|leading|leaders?|mvp|best\s+(player|scorer))\b/.test(p)) {
    return {
      intent: "leaders",
      label: p.length > 60 ? "Team leaders" : capitalize(prompt),
      count: extractNumber(p) || 5,
    };
  }

  // Standings / table / position
  if (/\b(standings?|league\s+table|where\s+they\s+(sit|stand)|position|table|conference|division|championship)\b/.test(p)) {
    return {
      intent: "standings",
      label: "Standings",
      count: extractNumber(p) || 8,
    };
  }

  // Results / past / recent / last N
  if (/\b(last|past|previous|recent\s+(games?|matches?|results)|results|form|history|won|lost)\b/.test(p)) {
    return {
      intent: "results",
      label: capitalize(prompt),
      count: extractNumber(p) || 10,
    };
  }

  // Schedule / next / upcoming / fixtures
  if (/\b(next|upcoming|schedule|fixtures?|coming\s+up|this\s+week|this\s+month|future)\b/.test(p)) {
    return {
      intent: "schedule",
      label: capitalize(prompt),
      count: extractNumber(p) || 5,
    };
  }

  // Stats catchall
  return {
    intent: "stats",
    label: capitalize(prompt),
    count: extractNumber(p) || 5,
  };
}

function capitalize(s) {
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
}
