// Data layer — resolves a (team, intent) tuple to a list of rows the
// graphic composer can render.
//
// Strategy:
//   1. If `window.MACHINA_DEPLOY` is wired up at runtime (the Factory deploy
//      step injects it), call the right sport-skill workflow via the proxy
//      and use the live result.
//   2. Otherwise, fall back to a deterministic seeded sample tied to the
//      team + intent so the preview pane shows real-shaped data.
//
// Workflow names follow the sport-skill convention:
//   football-data → workflow `football-team-{intent}`
//   nba-data      → workflow `nba-team-{intent}` (etc.)
// The Factory build is expected to have those workflows installed on the
// project pod when the customer deploys; the SPA fails open with seeded
// content otherwise so the page is never blank.

const PROXY_TIMEOUT_MS = 12_000;

// Workflow name resolution per skill. Kept loose: we try the most natural
// name first and treat any 404 the same as "no workflow installed yet".
function workflowFor(team, intent) {
  const skillToPrefix = {
    "football-data": "football",
    "nfl-data":      "nfl",
    "nba-data":      "nba",
    "mlb-data":      "mlb",
    "nhl-data":      "nhl",
    "tennis-data":   "tennis",
    "golf-data":     "golf",
    "fastf1":        "f1",
  };
  const prefix = skillToPrefix[team.skill] || team.skill.replace(/-data$/, "");
  return `${prefix}-team-${intent.intent}`;
}

async function callWorkflow(name, body) {
  if (typeof window === "undefined" || !window.MACHINA_DEPLOY?.proxyUrl) {
    return null;
  }
  const { proxyUrl } = window.MACHINA_DEPLOY;
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), PROXY_TIMEOUT_MS);
  try {
    const res = await fetch(`${proxyUrl}/workflow/execute/${name}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    if (!res.ok) return null;
    const data = await res.json();
    // Normalise: the proxy returns `{ outputs: {...} }` for executed
    // workflows. Empty outputs counts as "no data" and falls through to seed.
    const out = data?.outputs || data?.result || data;
    if (!out || Object.keys(out).length === 0) return null;
    return out;
  } catch {
    return null;
  } finally {
    clearTimeout(t);
  }
}

// ---------- Seeded sample shapes ----------
// All rows share { primary, secondary, meta?, accent? } so the composer
// stays sport-agnostic.

const MONTHS = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];

function dateRow(offsetDays, label, meta) {
  const d = new Date(Date.now() + offsetDays * 86400_000);
  const day = String(d.getDate()).padStart(2, "0");
  return { primary: `${MONTHS[d.getMonth()]} ${day}`, secondary: label, meta };
}

function seedSchedule(team, count) {
  const opponents = {
    "Soccer": ["away to West Ham","vs Brighton","away to Aston Villa","vs Crystal Palace","at Anfield","at Old Trafford","vs Fulham","at Goodison Park"],
    "NFL":    ["@ Bills","vs Patriots","@ Dolphins","vs Jets","@ Steelers","vs Browns","@ Bengals","vs Ravens"],
    "NBA":    ["vs Heat","@ Knicks","vs Celtics","@ Sixers","vs Bucks","@ Cavaliers","vs Pistons","@ Bulls"],
    "MLB":    ["@ Mets","vs Phillies","@ Braves","vs Marlins","@ Nationals","vs Cubs","@ Cardinals","vs Brewers"],
    "NHL":    ["@ Capitals","vs Flyers","@ Devils","vs Penguins","@ Islanders","vs Senators","@ Sabres","vs Hurricanes"],
    "Tennis": ["R32 — Indian Wells","R16 — Miami Open","QF — Monte-Carlo","SF — Madrid Open","Final — Rome","R32 — Roland-Garros"],
    "Golf":   ["The Players","Arnold Palmer Invit.","Valspar Championship","WGC Match Play","Masters Tournament","RBC Heritage"],
    "F1":     ["Bahrain Grand Prix","Saudi Arabian GP","Australian GP","Japanese GP","Chinese GP","Miami GP","Emilia Romagna GP","Monaco GP"],
  }[team.sport] || ["TBD opponent","TBD opponent","TBD opponent","TBD opponent","TBD opponent","TBD opponent"];
  const rows = [];
  for (let i = 0; i < count; i++) {
    rows.push(dateRow((i + 1) * 3, opponents[i % opponents.length], i === 0 ? "NEXT UP" : ""));
  }
  return rows;
}

function seedResults(team, count) {
  const samples = {
    "Soccer": [["W","3–1"],["W","2–0"],["D","1–1"],["L","0–2"],["W","4–2"],["W","1–0"],["D","2–2"],["W","2–1"],["L","1–3"],["W","3–0"]],
    "NFL":    [["W","27–20"],["L","17–24"],["W","31–14"],["W","21–17"],["L","14–28"],["W","34–10"],["W","24–21"]],
    "NBA":    [["W","118–106"],["W","112–98"],["L","104–119"],["W","127–113"],["W","109–101"],["L","98–105"],["W","121–116"],["W","134–122"]],
    "MLB":    [["W","6–3"],["L","2–4"],["W","8–1"],["W","5–4"],["L","1–7"],["W","3–2"],["W","9–0"]],
    "NHL":    [["W","4–2"],["W","3–1"],["L","1–4"],["W","5–2"],["OTL","3–4"],["W","2–1"],["W","6–3"]],
    "Tennis": [["W","6–3 6–2"],["W","7–6 6–4"],["L","4–6 3–6"],["W","6–2 6–1"],["W","6–4 7–5"]],
    "Golf":   [["T2","−12"],["1","−18"],["T8","−7"],["MC","+2"],["T4","−10"]],
    "F1":     [["P1","Win"],["P3","Podium"],["P5","Points"],["P2","Podium"],["DNF","Engine"],["P1","Win"]],
  }[team.sport] || [["–","–"]];
  return Array.from({ length: count }, (_, i) => {
    const [tag, score] = samples[i % samples.length];
    return { primary: tag, secondary: score, meta: i === 0 ? "MOST RECENT" : "" };
  });
}

function seedH2H(team, opponent, count) {
  // Aggregate H2H card: one summary row + last N meetings.
  const summary = { primary: "12–7–4", secondary: opponent ? `vs ${opponent.short}` : "all-time", meta: "W – D – L" };
  const meetings = seedResults(team, count - 1);
  return [summary, ...meetings];
}

function seedLeaders(team) {
  const rosters = {
    "Soccer": [["Erling Haaland","27 G"],["Mohamed Salah","19 G"],["Bukayo Saka","16 G"],["Cole Palmer","15 G"],["Phil Foden","14 G"]],
    "NFL":    [["Patrick Mahomes","4,183 YDS"],["Travis Kelce","984 YDS"],["Isiah Pacheco","935 YDS"],["Rashee Rice","938 YDS"],["Chris Jones","10.5 SK"]],
    "NBA":    [["Luka Dončić","33.9 PPG"],["Shai Gilgeous-Alexander","30.1 PPG"],["Giannis Antetokounmpo","30.4 PPG"],["Jayson Tatum","26.9 PPG"],["Nikola Jokić","26.4 PPG"]],
    "MLB":    [["Aaron Judge",".322 AVG"],["Shohei Ohtani","54 HR"],["Bobby Witt Jr.","32 SB"],["Juan Soto",".288 AVG"],["Tarik Skubal","2.39 ERA"]],
    "NHL":    [["Connor McDavid","132 PTS"],["Nathan MacKinnon","140 PTS"],["Auston Matthews","69 G"],["Nikita Kucherov","144 PTS"],["David Pastrnak","110 PTS"]],
    "Tennis": [["Carlos Alcaraz","#2 ATP"],["Jannik Sinner","#1 ATP"],["Iga Świątek","#1 WTA"],["Aryna Sabalenka","#2 WTA"],["Coco Gauff","#3 WTA"]],
    "Golf":   [["Scottie Scheffler","#1 OWGR"],["Rory McIlroy","#2 OWGR"],["Xander Schauffele","#3 OWGR"],["Wyndham Clark","#4 OWGR"],["Viktor Hovland","#5 OWGR"]],
    "F1":     [["Max Verstappen","437 PTS"],["Lando Norris","374 PTS"],["Charles Leclerc","356 PTS"],["Oscar Piastri","292 PTS"],["Carlos Sainz","290 PTS"]],
  }[team.sport] || [["Player","–"]];
  return rosters.map(([name, stat], i) => ({
    primary: stat, secondary: name, meta: i === 0 ? "LEADER" : "",
  }));
}

function seedStandings(team) {
  const tables = {
    "Soccer": [["1.","Liverpool","61 PTS"],["2.","Arsenal","53 PTS"],["3.","Nottingham Forest","47 PTS"],["4.","Chelsea","43 PTS"],["5.","Manchester City","41 PTS"]],
    "NFL":    [["1.","Detroit Lions","13–3"],["2.","Philadelphia Eagles","13–3"],["3.","Buffalo Bills","13–3"],["4.","Minnesota Vikings","14–2"],["5.","Kansas City Chiefs","15–1"]],
    "NBA":    [["1.","OKC Thunder","52–11"],["2.","Cleveland Cavaliers","48–13"],["3.","Boston Celtics","45–18"],["4.","Memphis Grizzlies","41–22"],["5.","Denver Nuggets","40–24"]],
    "MLB":    [["1.","LA Dodgers","98–64"],["2.","NY Yankees","94–68"],["3.","Cleveland Guardians","92–69"],["4.","Houston Astros","88–73"],["5.","Baltimore Orioles","91–71"]],
    "NHL":    [["1.","Winnipeg Jets","41–14–3"],["2.","Washington Capitals","40–13–6"],["3.","Edmonton Oilers","36–18–4"],["4.","Vegas Golden Knights","36–17–6"],["5.","Dallas Stars","37–19–2"]],
    "Tennis": [["1.","Jannik Sinner","11,830"],["2.","Alexander Zverev","8,135"],["3.","Carlos Alcaraz","7,010"],["4.","Taylor Fritz","5,250"],["5.","Casper Ruud","4,210"]],
    "Golf":   [["1.","Scottie Scheffler","12.84"],["2.","Rory McIlroy","8.97"],["3.","Xander Schauffele","8.51"],["4.","Collin Morikawa","6.94"],["5.","Ludvig Åberg","6.84"]],
    "F1":     [["1.","McLaren","666 PTS"],["2.","Ferrari","652 PTS"],["3.","Red Bull","589 PTS"],["4.","Mercedes","468 PTS"],["5.","Aston Martin","94 PTS"]],
  }[team.sport] || [["–","–","–"]];
  return tables.map(([pos, name, pts]) => ({
    primary: pos, secondary: name, meta: pts,
  }));
}

function seedStats(team) {
  // Generic season-overview tiles
  return [
    { primary: "12W–4L", secondary: "Season record", meta: "75% WR" },
    { primary: "+47",    secondary: "Goal / Point diff",   meta: "" },
    { primary: "8",      secondary: "Home wins streak",    meta: "" },
    { primary: "#2",     secondary: "League position",     meta: "" },
    { primary: "62%",    secondary: "Possession avg",      meta: "" },
  ];
}

function seedFor(team, intent) {
  switch (intent.intent) {
    case "schedule":  return seedSchedule(team, intent.count);
    case "results":   return seedResults(team, intent.count);
    case "h2h":       return seedH2H(team, intent.opponent, intent.count);
    case "leaders":   return seedLeaders(team);
    case "standings": return seedStandings(team);
    default:          return seedStats(team);
  }
}

// Translate a workflow output payload to row objects. The contract is
// loose: if a workflow returns `rows: [{primary, secondary, meta}, ...]`
// use it; otherwise try common shapes (`fixtures`, `results`, `players`,
// `standings`) and best-effort map; otherwise null → seed.
function rowsFromWorkflow(out) {
  if (!out) return null;
  if (Array.isArray(out.rows)) return out.rows;

  const tryShape = (arr, primary, secondary, meta) => {
    if (!Array.isArray(arr) || arr.length === 0) return null;
    return arr.map(item => ({
      primary:   item[primary]   ?? "",
      secondary: item[secondary] ?? "",
      meta:      meta ? (item[meta] ?? "") : "",
    }));
  };

  return (
    tryShape(out.fixtures,  "date",   "opponent", "competition") ||
    tryShape(out.results,   "result", "score",    "opponent") ||
    tryShape(out.players,   "stat",   "name",     "tag") ||
    tryShape(out.standings, "position","team",    "points") ||
    null
  );
}

/**
 * Resolve a (team, intent) pair to displayable rows.
 * Returns: { rows, source: "live" | "seed", warning?: string }
 */
export async function resolveData(team, intent) {
  const workflowName = workflowFor(team, intent);
  const body = {
    team_id: team.id,
    team_name: team.name,
    sport: team.sport,
    league: team.league,
    intent: intent.intent,
    count: intent.count,
    opponent_id: intent.opponent?.id,
  };

  const live = await callWorkflow(workflowName, body);
  const rows = rowsFromWorkflow(live);
  if (rows && rows.length) return { rows, source: "live" };

  // Empty live response → seed, with a small banner so the customer
  // knows the live path didn't return anything.
  const seeded = seedFor(team, intent);
  if (!seeded || seeded.length === 0) {
    return {
      rows: [],
      source: "seed",
      warning: intent.intent === "schedule"
        ? "No upcoming events found."
        : "No data available for this query.",
    };
  }
  return {
    rows: seeded,
    source: live ? "seed" : "seed",
    warning: live ? "Live data returned no usable rows — showing sample." : undefined,
  };
}
