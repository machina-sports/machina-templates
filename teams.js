/* ===============================================================
 * teams.js — typeahead catalog across all sports the pod can query
 *
 * Each entry maps to the `sports-skills-call` workflow:
 *   { module, query_team, query_competition }
 *
 * Colors are the team's canonical brand pair (primary, secondary).
 * Used as fallback palette when no reference image is dropped.
 * =============================================================== */

window.TEAMS = [
  /* ── NBA ──────────────────────────────────────────────────── */
  { id: "nba-lakers",   name: "Los Angeles Lakers",      sport: "NBA", module: "nba", query: "Lakers",       colors: ["#552583", "#FDB927"] },
  { id: "nba-celtics",  name: "Boston Celtics",          sport: "NBA", module: "nba", query: "Celtics",      colors: ["#007A33", "#BA9653"] },
  { id: "nba-warriors", name: "Golden State Warriors",   sport: "NBA", module: "nba", query: "Warriors",     colors: ["#1D428A", "#FFC72C"] },
  { id: "nba-bulls",    name: "Chicago Bulls",           sport: "NBA", module: "nba", query: "Bulls",        colors: ["#CE1141", "#000000"] },
  { id: "nba-heat",     name: "Miami Heat",              sport: "NBA", module: "nba", query: "Heat",         colors: ["#98002E", "#F9A01B"] },
  { id: "nba-knicks",   name: "New York Knicks",         sport: "NBA", module: "nba", query: "Knicks",       colors: ["#006BB6", "#F58426"] },
  { id: "nba-nets",     name: "Brooklyn Nets",           sport: "NBA", module: "nba", query: "Nets",         colors: ["#000000", "#FFFFFF"] },
  { id: "nba-bucks",    name: "Milwaukee Bucks",         sport: "NBA", module: "nba", query: "Bucks",        colors: ["#00471B", "#EEE1C6"] },
  { id: "nba-nuggets",  name: "Denver Nuggets",          sport: "NBA", module: "nba", query: "Nuggets",      colors: ["#0E2240", "#FEC524"] },
  { id: "nba-suns",     name: "Phoenix Suns",            sport: "NBA", module: "nba", query: "Suns",         colors: ["#1D1160", "#E56020"] },
  { id: "nba-mavs",     name: "Dallas Mavericks",        sport: "NBA", module: "nba", query: "Mavericks",    colors: ["#00538C", "#002B5E"] },
  { id: "nba-76ers",    name: "Philadelphia 76ers",      sport: "NBA", module: "nba", query: "76ers",        colors: ["#006BB6", "#ED174C"] },
  { id: "nba-cavs",     name: "Cleveland Cavaliers",     sport: "NBA", module: "nba", query: "Cavaliers",    colors: ["#860038", "#FDBB30"] },
  { id: "nba-thunder",  name: "Oklahoma City Thunder",   sport: "NBA", module: "nba", query: "Thunder",      colors: ["#007AC1", "#EF3B24"] },
  { id: "nba-spurs",    name: "San Antonio Spurs",       sport: "NBA", module: "nba", query: "Spurs",        colors: ["#C4CED4", "#000000"] },
  { id: "nba-rockets",  name: "Houston Rockets",         sport: "NBA", module: "nba", query: "Rockets",      colors: ["#CE1141", "#000000"] },
  { id: "nba-grizzlies",name: "Memphis Grizzlies",       sport: "NBA", module: "nba", query: "Grizzlies",    colors: ["#5D76A9", "#12173F"] },
  { id: "nba-pelicans", name: "New Orleans Pelicans",    sport: "NBA", module: "nba", query: "Pelicans",     colors: ["#0C2340", "#C8102E"] },
  { id: "nba-kings",    name: "Sacramento Kings",        sport: "NBA", module: "nba", query: "Kings",        colors: ["#5A2D81", "#63727A"] },
  { id: "nba-raptors",  name: "Toronto Raptors",         sport: "NBA", module: "nba", query: "Raptors",      colors: ["#CE1141", "#000000"] },

  /* ── NFL ──────────────────────────────────────────────────── */
  { id: "nfl-chiefs",   name: "Kansas City Chiefs",      sport: "NFL", module: "nfl", query: "Chiefs",       colors: ["#E31837", "#FFB81C"] },
  { id: "nfl-eagles",   name: "Philadelphia Eagles",     sport: "NFL", module: "nfl", query: "Eagles",       colors: ["#004C54", "#A5ACAF"] },
  { id: "nfl-cowboys",  name: "Dallas Cowboys",          sport: "NFL", module: "nfl", query: "Cowboys",      colors: ["#003594", "#869397"] },
  { id: "nfl-niners",   name: "San Francisco 49ers",     sport: "NFL", module: "nfl", query: "49ers",        colors: ["#AA0000", "#B3995D"] },
  { id: "nfl-bills",    name: "Buffalo Bills",           sport: "NFL", module: "nfl", query: "Bills",        colors: ["#00338D", "#C60C30"] },
  { id: "nfl-packers",  name: "Green Bay Packers",       sport: "NFL", module: "nfl", query: "Packers",      colors: ["#203731", "#FFB612"] },
  { id: "nfl-ravens",   name: "Baltimore Ravens",        sport: "NFL", module: "nfl", query: "Ravens",       colors: ["#241773", "#9E7C0C"] },
  { id: "nfl-lions",    name: "Detroit Lions",           sport: "NFL", module: "nfl", query: "Lions",        colors: ["#0076B6", "#B0B7BC"] },
  { id: "nfl-bengals",  name: "Cincinnati Bengals",      sport: "NFL", module: "nfl", query: "Bengals",      colors: ["#FB4F14", "#000000"] },
  { id: "nfl-dolphins", name: "Miami Dolphins",          sport: "NFL", module: "nfl", query: "Dolphins",     colors: ["#008E97", "#FC4C02"] },
  { id: "nfl-steelers", name: "Pittsburgh Steelers",     sport: "NFL", module: "nfl", query: "Steelers",     colors: ["#FFB612", "#101820"] },
  { id: "nfl-jets",     name: "New York Jets",           sport: "NFL", module: "nfl", query: "Jets",         colors: ["#125740", "#FFFFFF"] },
  { id: "nfl-giants",   name: "New York Giants",         sport: "NFL", module: "nfl", query: "Giants",       colors: ["#0B2265", "#A71930"] },
  { id: "nfl-patriots", name: "New England Patriots",    sport: "NFL", module: "nfl", query: "Patriots",     colors: ["#002244", "#C60C30"] },
  { id: "nfl-rams",     name: "Los Angeles Rams",        sport: "NFL", module: "nfl", query: "Rams",         colors: ["#003594", "#FFA300"] },
  { id: "nfl-vikings",  name: "Minnesota Vikings",       sport: "NFL", module: "nfl", query: "Vikings",      colors: ["#4F2683", "#FFC62F"] },
  { id: "nfl-seahawks", name: "Seattle Seahawks",        sport: "NFL", module: "nfl", query: "Seahawks",     colors: ["#002244", "#69BE28"] },
  { id: "nfl-broncos",  name: "Denver Broncos",          sport: "NFL", module: "nfl", query: "Broncos",      colors: ["#FB4F14", "#002244"] },

  /* ── MLB ──────────────────────────────────────────────────── */
  { id: "mlb-yankees",  name: "New York Yankees",        sport: "MLB", module: "mlb", query: "Yankees",      colors: ["#0C2340", "#C4CED3"] },
  { id: "mlb-dodgers",  name: "Los Angeles Dodgers",     sport: "MLB", module: "mlb", query: "Dodgers",      colors: ["#005A9C", "#EF3E42"] },
  { id: "mlb-redsox",   name: "Boston Red Sox",          sport: "MLB", module: "mlb", query: "Red Sox",      colors: ["#BD3039", "#0C2340"] },
  { id: "mlb-cubs",     name: "Chicago Cubs",            sport: "MLB", module: "mlb", query: "Cubs",         colors: ["#0E3386", "#CC3433"] },
  { id: "mlb-giants",   name: "San Francisco Giants",    sport: "MLB", module: "mlb", query: "Giants",       colors: ["#FD5A1E", "#27251F"] },
  { id: "mlb-mets",     name: "New York Mets",           sport: "MLB", module: "mlb", query: "Mets",         colors: ["#002D72", "#FF5910"] },
  { id: "mlb-astros",   name: "Houston Astros",          sport: "MLB", module: "mlb", query: "Astros",       colors: ["#002D62", "#EB6E1F"] },
  { id: "mlb-braves",   name: "Atlanta Braves",          sport: "MLB", module: "mlb", query: "Braves",       colors: ["#CE1141", "#13274F"] },
  { id: "mlb-phillies", name: "Philadelphia Phillies",   sport: "MLB", module: "mlb", query: "Phillies",     colors: ["#E81828", "#002D72"] },
  { id: "mlb-cardinals",name: "St. Louis Cardinals",     sport: "MLB", module: "mlb", query: "Cardinals",    colors: ["#C41E3A", "#0C2340"] },

  /* ── NHL ──────────────────────────────────────────────────── */
  { id: "nhl-rangers",  name: "New York Rangers",        sport: "NHL", module: "nhl", query: "Rangers",      colors: ["#0038A8", "#CE1126"] },
  { id: "nhl-bruins",   name: "Boston Bruins",           sport: "NHL", module: "nhl", query: "Bruins",       colors: ["#FFB81C", "#000000"] },
  { id: "nhl-blackhawks", name: "Chicago Blackhawks",    sport: "NHL", module: "nhl", query: "Blackhawks",   colors: ["#CF0A2C", "#000000"] },
  { id: "nhl-mapleleafs", name: "Toronto Maple Leafs",   sport: "NHL", module: "nhl", query: "Maple Leafs",  colors: ["#00205B", "#FFFFFF"] },
  { id: "nhl-canadiens",name: "Montreal Canadiens",      sport: "NHL", module: "nhl", query: "Canadiens",    colors: ["#AF1E2D", "#192168"] },
  { id: "nhl-oilers",   name: "Edmonton Oilers",         sport: "NHL", module: "nhl", query: "Oilers",       colors: ["#FF4C00", "#041E42"] },
  { id: "nhl-redwings", name: "Detroit Red Wings",       sport: "NHL", module: "nhl", query: "Red Wings",    colors: ["#CE1126", "#FFFFFF"] },
  { id: "nhl-penguins", name: "Pittsburgh Penguins",     sport: "NHL", module: "nhl", query: "Penguins",     colors: ["#FCB514", "#000000"] },
  { id: "nhl-kings",    name: "Los Angeles Kings",       sport: "NHL", module: "nhl", query: "Kings",        colors: ["#111111", "#A2AAAD"] },
  { id: "nhl-lightning",name: "Tampa Bay Lightning",     sport: "NHL", module: "nhl", query: "Lightning",    colors: ["#002868", "#FFFFFF"] },

  /* ── Football (Soccer) ────────────────────────────────────── */
  { id: "f-realmadrid", name: "Real Madrid",                 sport: "La Liga",      module: "football", query: "Real Madrid",          competition: "la-liga",       colors: ["#FEBE10", "#FFFFFF"] },
  { id: "f-barcelona",  name: "FC Barcelona",                sport: "La Liga",      module: "football", query: "Barcelona",            competition: "la-liga",       colors: ["#A50044", "#004D98"] },
  { id: "f-atletico",   name: "Atlético Madrid",             sport: "La Liga",      module: "football", query: "Atletico Madrid",      competition: "la-liga",       colors: ["#CB3524", "#272E61"] },
  { id: "f-mancity",    name: "Manchester City",             sport: "Premier League", module: "football", query: "Manchester City",   competition: "premier-league",colors: ["#6CABDD", "#1C2C5B"] },
  { id: "f-manunited",  name: "Manchester United",           sport: "Premier League", module: "football", query: "Manchester United", competition: "premier-league",colors: ["#DA291C", "#FBE122"] },
  { id: "f-liverpool",  name: "Liverpool",                   sport: "Premier League", module: "football", query: "Liverpool",         competition: "premier-league",colors: ["#C8102E", "#00B2A9"] },
  { id: "f-arsenal",    name: "Arsenal",                     sport: "Premier League", module: "football", query: "Arsenal",           competition: "premier-league",colors: ["#EF0107", "#063672"] },
  { id: "f-chelsea",    name: "Chelsea",                     sport: "Premier League", module: "football", query: "Chelsea",           competition: "premier-league",colors: ["#034694", "#DBA111"] },
  { id: "f-tottenham",  name: "Tottenham Hotspur",           sport: "Premier League", module: "football", query: "Tottenham",         competition: "premier-league",colors: ["#132257", "#FFFFFF"] },
  { id: "f-newcastle",  name: "Newcastle United",            sport: "Premier League", module: "football", query: "Newcastle",         competition: "premier-league",colors: ["#241F20", "#F1BE48"] },
  { id: "f-bayern",     name: "Bayern Munich",               sport: "Bundesliga",   module: "football", query: "Bayern Munich",        competition: "bundesliga",    colors: ["#DC052D", "#0066B2"] },
  { id: "f-dortmund",   name: "Borussia Dortmund",           sport: "Bundesliga",   module: "football", query: "Borussia Dortmund",    competition: "bundesliga",    colors: ["#FDE100", "#000000"] },
  { id: "f-leverkusen", name: "Bayer Leverkusen",            sport: "Bundesliga",   module: "football", query: "Bayer Leverkusen",     competition: "bundesliga",    colors: ["#E32221", "#000000"] },
  { id: "f-juventus",   name: "Juventus",                    sport: "Serie A",      module: "football", query: "Juventus",             competition: "serie-a",       colors: ["#000000", "#FFFFFF"] },
  { id: "f-inter",      name: "Inter Milan",                 sport: "Serie A",      module: "football", query: "Inter Milan",          competition: "serie-a",       colors: ["#010E80", "#000000"] },
  { id: "f-milan",      name: "AC Milan",                    sport: "Serie A",      module: "football", query: "AC Milan",             competition: "serie-a",       colors: ["#FB090B", "#000000"] },
  { id: "f-napoli",     name: "Napoli",                      sport: "Serie A",      module: "football", query: "Napoli",               competition: "serie-a",       colors: ["#12A0D7", "#003C82"] },
  { id: "f-roma",       name: "AS Roma",                     sport: "Serie A",      module: "football", query: "Roma",                 competition: "serie-a",       colors: ["#8E1F2F", "#F0BC42"] },
  { id: "f-psg",        name: "Paris Saint-Germain",         sport: "Ligue 1",      module: "football", query: "PSG",                  competition: "ligue-1",       colors: ["#004170", "#DA291C"] },
  { id: "f-marseille",  name: "Olympique de Marseille",      sport: "Ligue 1",      module: "football", query: "Marseille",            competition: "ligue-1",       colors: ["#2FAEE0", "#FFFFFF"] },
  { id: "f-flamengo",   name: "Flamengo",                    sport: "Brasileirão",  module: "football", query: "Flamengo",             competition: "serie-a-brazil",colors: ["#D71920", "#000000"] },
  { id: "f-palmeiras",  name: "Palmeiras",                   sport: "Brasileirão",  module: "football", query: "Palmeiras",            competition: "serie-a-brazil",colors: ["#006437", "#FFFFFF"] },
  { id: "f-corinthians",name: "Corinthians",                 sport: "Brasileirão",  module: "football", query: "Corinthians",          competition: "serie-a-brazil",colors: ["#000000", "#FFFFFF"] },
  { id: "f-saopaulo",   name: "São Paulo",                   sport: "Brasileirão",  module: "football", query: "São Paulo",            competition: "serie-a-brazil",colors: ["#FE0000", "#000000"] },
  { id: "f-santos",     name: "Santos",                      sport: "Brasileirão",  module: "football", query: "Santos",               competition: "serie-a-brazil",colors: ["#000000", "#FFFFFF"] },
  { id: "f-fluminense", name: "Fluminense",                  sport: "Brasileirão",  module: "football", query: "Fluminense",           competition: "serie-a-brazil",colors: ["#7E0029", "#006437"] },
  { id: "f-boca",       name: "Boca Juniors",                sport: "Liga Argentina",module: "football",query: "Boca Juniors",         competition: "liga-argentina",colors: ["#003E7E", "#FCD116"] },
  { id: "f-river",      name: "River Plate",                 sport: "Liga Argentina",module: "football",query: "River Plate",          competition: "liga-argentina",colors: ["#FFFFFF", "#D2122E"] },
  { id: "f-ajax",       name: "Ajax",                        sport: "Eredivisie",   module: "football", query: "Ajax",                 competition: "eredivisie",    colors: ["#D2122E", "#FFFFFF"] },
  { id: "f-benfica",    name: "Benfica",                     sport: "Primeira Liga",module: "football", query: "Benfica",              competition: "primeira-liga", colors: ["#E80E1B", "#FFFFFF"] },
  { id: "f-porto",      name: "FC Porto",                    sport: "Primeira Liga",module: "football", query: "FC Porto",             competition: "primeira-liga", colors: ["#004A99", "#FFFFFF"] },

  /* ── F1 ───────────────────────────────────────────────────── */
  { id: "f1-ferrari",     name: "Ferrari",          sport: "F1", module: "f1", query: "Ferrari",          colors: ["#DC0000", "#FFEB00"] },
  { id: "f1-mercedes",    name: "Mercedes-AMG",     sport: "F1", module: "f1", query: "Mercedes",         colors: ["#00D2BE", "#000000"] },
  { id: "f1-redbull",     name: "Red Bull Racing",  sport: "F1", module: "f1", query: "Red Bull",         colors: ["#3671C6", "#FFC906"] },
  { id: "f1-mclaren",     name: "McLaren",          sport: "F1", module: "f1", query: "McLaren",          colors: ["#FF8000", "#47C7FC"] },
  { id: "f1-astonmartin", name: "Aston Martin",     sport: "F1", module: "f1", query: "Aston Martin",     colors: ["#229971", "#FFFFFF"] },
];

/* simple substring + word-prefix search */
window.searchTeams = function (q) {
  const query = (q || "").trim().toLowerCase();
  if (!query) return [];
  const out = [];
  for (const t of window.TEAMS) {
    const name = t.name.toLowerCase();
    const sport = t.sport.toLowerCase();
    let score = 0;
    if (name === query) score = 100;
    else if (name.startsWith(query)) score = 80;
    else if (name.split(/\s+/).some((w) => w.startsWith(query))) score = 60;
    else if (name.includes(query)) score = 40;
    else if (sport.includes(query)) score = 20;
    if (score > 0) out.push({ ...t, _score: score });
  }
  out.sort((a, b) => b._score - a._score);
  return out.slice(0, 8);
};
