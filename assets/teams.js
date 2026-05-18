// Curated multi-sport team database.
// Colors sourced from official brand guidelines; abbreviated to a primary +
// secondary pair that drive the graphic palette. League gives us the skill
// to call when fetching live data.
//
// Format: { id, name, short, sport, league, skill, primary, secondary, accent }
// - skill: which @machina-sports/sports-skills/* workflow family handles this
// - primary/secondary/accent: HEX, no #

export const TEAMS = [
  // === Soccer (football-data) ===
  // Premier League
  { id: "arsenal",     name: "Arsenal",            short: "ARS", sport: "Soccer", league: "Premier League",  skill: "football-data", primary: "EF0107", secondary: "FFFFFF", accent: "9C824A" },
  { id: "liverpool",   name: "Liverpool",          short: "LIV", sport: "Soccer", league: "Premier League",  skill: "football-data", primary: "C8102E", secondary: "00B2A9", accent: "F6EB61" },
  { id: "mancity",     name: "Manchester City",    short: "MCI", sport: "Soccer", league: "Premier League",  skill: "football-data", primary: "6CABDD", secondary: "1C2C5B", accent: "FFC659" },
  { id: "manunited",   name: "Manchester United",  short: "MUN", sport: "Soccer", league: "Premier League",  skill: "football-data", primary: "DA291C", secondary: "FBE122", accent: "000000" },
  { id: "chelsea",     name: "Chelsea",            short: "CHE", sport: "Soccer", league: "Premier League",  skill: "football-data", primary: "034694", secondary: "FFFFFF", accent: "DBA111" },
  { id: "tottenham",   name: "Tottenham Hotspur",  short: "TOT", sport: "Soccer", league: "Premier League",  skill: "football-data", primary: "132257", secondary: "FFFFFF", accent: "DBA111" },
  { id: "newcastle",   name: "Newcastle United",   short: "NEW", sport: "Soccer", league: "Premier League",  skill: "football-data", primary: "241F20", secondary: "FFFFFF", accent: "F1BE48" },
  // La Liga
  { id: "realmadrid",  name: "Real Madrid",        short: "RMA", sport: "Soccer", league: "La Liga",         skill: "football-data", primary: "FEBE10", secondary: "00529F", accent: "FFFFFF" },
  { id: "barcelona",   name: "FC Barcelona",       short: "BAR", sport: "Soccer", league: "La Liga",         skill: "football-data", primary: "A50044", secondary: "004D98", accent: "EDBB00" },
  { id: "atletico",    name: "Atlético de Madrid", short: "ATM", sport: "Soccer", league: "La Liga",         skill: "football-data", primary: "CB3524", secondary: "FFFFFF", accent: "272E61" },
  // Serie A
  { id: "juventus",    name: "Juventus",           short: "JUV", sport: "Soccer", league: "Serie A",         skill: "football-data", primary: "000000", secondary: "FFFFFF", accent: "C2B173" },
  { id: "milan",       name: "AC Milan",           short: "MIL", sport: "Soccer", league: "Serie A",         skill: "football-data", primary: "FB090B", secondary: "000000", accent: "FFFFFF" },
  { id: "inter",       name: "Inter Milan",        short: "INT", sport: "Soccer", league: "Serie A",         skill: "football-data", primary: "010E80", secondary: "000000", accent: "FFE600" },
  // Bundesliga
  { id: "bayern",      name: "Bayern Munich",      short: "BAY", sport: "Soccer", league: "Bundesliga",      skill: "football-data", primary: "DC052D", secondary: "0066B2", accent: "FFFFFF" },
  { id: "dortmund",    name: "Borussia Dortmund",  short: "BVB", sport: "Soccer", league: "Bundesliga",      skill: "football-data", primary: "FDE100", secondary: "000000", accent: "FFFFFF" },
  // Ligue 1
  { id: "psg",         name: "Paris Saint-Germain",short: "PSG", sport: "Soccer", league: "Ligue 1",         skill: "football-data", primary: "004170", secondary: "DA291C", accent: "FFFFFF" },

  // === NFL (nfl-data) ===
  { id: "chiefs",      name: "Kansas City Chiefs", short: "KC",  sport: "NFL",    league: "NFL",             skill: "nfl-data",      primary: "E31837", secondary: "FFB81C", accent: "FFFFFF" },
  { id: "eagles",      name: "Philadelphia Eagles",short: "PHI", sport: "NFL",    league: "NFL",             skill: "nfl-data",      primary: "004C54", secondary: "A5ACAF", accent: "ACC0C6" },
  { id: "49ers",       name: "San Francisco 49ers",short: "SF",  sport: "NFL",    league: "NFL",             skill: "nfl-data",      primary: "AA0000", secondary: "B3995D", accent: "FFFFFF" },
  { id: "cowboys",     name: "Dallas Cowboys",     short: "DAL", sport: "NFL",    league: "NFL",             skill: "nfl-data",      primary: "003594", secondary: "869397", accent: "FFFFFF" },
  { id: "ravens",      name: "Baltimore Ravens",   short: "BAL", sport: "NFL",    league: "NFL",             skill: "nfl-data",      primary: "241773", secondary: "9E7C0C", accent: "000000" },
  { id: "bills",       name: "Buffalo Bills",      short: "BUF", sport: "NFL",    league: "NFL",             skill: "nfl-data",      primary: "00338D", secondary: "C60C30", accent: "FFFFFF" },
  { id: "packers",     name: "Green Bay Packers",  short: "GB",  sport: "NFL",    league: "NFL",             skill: "nfl-data",      primary: "203731", secondary: "FFB612", accent: "FFFFFF" },
  { id: "dolphins",    name: "Miami Dolphins",     short: "MIA", sport: "NFL",    league: "NFL",             skill: "nfl-data",      primary: "008E97", secondary: "FC4C02", accent: "005778" },
  { id: "seahawks",    name: "Seattle Seahawks",   short: "SEA", sport: "NFL",    league: "NFL",             skill: "nfl-data",      primary: "002244", secondary: "69BE28", accent: "A5ACAF" },

  // === NBA (nba-data) ===
  { id: "lakers",      name: "Los Angeles Lakers", short: "LAL", sport: "NBA",    league: "NBA",             skill: "nba-data",      primary: "552583", secondary: "FDB927", accent: "000000" },
  { id: "celtics",     name: "Boston Celtics",     short: "BOS", sport: "NBA",    league: "NBA",             skill: "nba-data",      primary: "007A33", secondary: "BA9653", accent: "FFFFFF" },
  { id: "warriors",    name: "Golden State Warriors",short:"GSW",sport: "NBA",    league: "NBA",             skill: "nba-data",      primary: "1D428A", secondary: "FFC72C", accent: "FFFFFF" },
  { id: "heat",        name: "Miami Heat",         short: "MIA", sport: "NBA",    league: "NBA",             skill: "nba-data",      primary: "98002E", secondary: "F9A01B", accent: "000000" },
  { id: "nuggets",     name: "Denver Nuggets",     short: "DEN", sport: "NBA",    league: "NBA",             skill: "nba-data",      primary: "0E2240", secondary: "FEC524", accent: "8B2131" },
  { id: "bucks",       name: "Milwaukee Bucks",    short: "MIL", sport: "NBA",    league: "NBA",             skill: "nba-data",      primary: "00471B", secondary: "EEE1C6", accent: "0077C0" },
  { id: "76ers",       name: "Philadelphia 76ers", short: "PHI", sport: "NBA",    league: "NBA",             skill: "nba-data",      primary: "006BB6", secondary: "ED174C", accent: "002B5C" },
  { id: "knicks",      name: "New York Knicks",    short: "NYK", sport: "NBA",    league: "NBA",             skill: "nba-data",      primary: "006BB6", secondary: "F58426", accent: "BEC0C2" },
  { id: "mavericks",   name: "Dallas Mavericks",   short: "DAL", sport: "NBA",    league: "NBA",             skill: "nba-data",      primary: "00538C", secondary: "002B5E", accent: "B8C4CA" },
  { id: "suns",        name: "Phoenix Suns",       short: "PHX", sport: "NBA",    league: "NBA",             skill: "nba-data",      primary: "1D1160", secondary: "E56020", accent: "F9AD1B" },

  // === MLB (mlb-data) ===
  { id: "yankees",     name: "New York Yankees",   short: "NYY", sport: "MLB",    league: "MLB",             skill: "mlb-data",      primary: "0C2340", secondary: "C4CED3", accent: "FFFFFF" },
  { id: "dodgers",     name: "Los Angeles Dodgers",short: "LAD", sport: "MLB",    league: "MLB",             skill: "mlb-data",      primary: "005A9C", secondary: "FFFFFF", accent: "EF3E42" },
  { id: "redsox",      name: "Boston Red Sox",     short: "BOS", sport: "MLB",    league: "MLB",             skill: "mlb-data",      primary: "BD3039", secondary: "0C2340", accent: "FFFFFF" },
  { id: "cubs",        name: "Chicago Cubs",       short: "CHC", sport: "MLB",    league: "MLB",             skill: "mlb-data",      primary: "0E3386", secondary: "CC3433", accent: "FFFFFF" },
  { id: "giants",      name: "San Francisco Giants",short:"SF",  sport: "MLB",    league: "MLB",             skill: "mlb-data",      primary: "FD5A1E", secondary: "27251F", accent: "AE8F6F" },
  { id: "astros",      name: "Houston Astros",     short: "HOU", sport: "MLB",    league: "MLB",             skill: "mlb-data",      primary: "002D62", secondary: "EB6E1F", accent: "F4911E" },
  { id: "braves",      name: "Atlanta Braves",     short: "ATL", sport: "MLB",    league: "MLB",             skill: "mlb-data",      primary: "CE1141", secondary: "13274F", accent: "EAAA00" },

  // === NHL (nhl-data) ===
  { id: "rangers",     name: "New York Rangers",   short: "NYR", sport: "NHL",    league: "NHL",             skill: "nhl-data",      primary: "0038A8", secondary: "CE1126", accent: "FFFFFF" },
  { id: "mapleleafs",  name: "Toronto Maple Leafs",short: "TOR", sport: "NHL",    league: "NHL",             skill: "nhl-data",      primary: "00205B", secondary: "FFFFFF", accent: "C8102E" },
  { id: "bruins",      name: "Boston Bruins",      short: "BOS", sport: "NHL",    league: "NHL",             skill: "nhl-data",      primary: "FFB81C", secondary: "000000", accent: "FFFFFF" },
  { id: "oilers",      name: "Edmonton Oilers",    short: "EDM", sport: "NHL",    league: "NHL",             skill: "nhl-data",      primary: "041E42", secondary: "FF4C00", accent: "FFFFFF" },
  { id: "panthers",    name: "Florida Panthers",   short: "FLA", sport: "NHL",    league: "NHL",             skill: "nhl-data",      primary: "041E42", secondary: "C8102E", accent: "B9975B" },
  { id: "avalanche",   name: "Colorado Avalanche", short: "COL", sport: "NHL",    league: "NHL",             skill: "nhl-data",      primary: "6F263D", secondary: "236192", accent: "A2AAAD" },

  // === Tennis (tennis-data) — top players ===
  { id: "djokovic",    name: "Novak Djokovic",     short: "DJO", sport: "Tennis", league: "ATP",             skill: "tennis-data",   primary: "003F87", secondary: "FFFFFF", accent: "DA291C" },
  { id: "alcaraz",     name: "Carlos Alcaraz",     short: "ALC", sport: "Tennis", league: "ATP",             skill: "tennis-data",   primary: "AA151B", secondary: "F1BF00", accent: "FFFFFF" },
  { id: "sinner",      name: "Jannik Sinner",      short: "SIN", sport: "Tennis", league: "ATP",             skill: "tennis-data",   primary: "008C45", secondary: "FFFFFF", accent: "CD212A" },
  { id: "swiatek",     name: "Iga Świątek",        short: "SWI", sport: "Tennis", league: "WTA",             skill: "tennis-data",   primary: "DC143C", secondary: "FFFFFF", accent: "1E2A5E" },
  { id: "sabalenka",   name: "Aryna Sabalenka",    short: "SAB", sport: "Tennis", league: "WTA",             skill: "tennis-data",   primary: "00714D", secondary: "FFD100", accent: "DA291C" },

  // === Golf (golf-data) — top players ===
  { id: "scheffler",   name: "Scottie Scheffler",  short: "SCH", sport: "Golf",   league: "PGA",             skill: "golf-data",     primary: "BF5700", secondary: "FFFFFF", accent: "333F48" },
  { id: "mcilroy",     name: "Rory McIlroy",       short: "MCI", sport: "Golf",   league: "PGA",             skill: "golf-data",     primary: "169B62", secondary: "FFFFFF", accent: "FF883E" },
  { id: "rahm",        name: "Jon Rahm",           short: "RAH", sport: "Golf",   league: "PGA",             skill: "golf-data",     primary: "AA151B", secondary: "F1BF00", accent: "FFFFFF" },

  // === F1 (fastf1) ===
  { id: "redbull",     name: "Red Bull Racing",    short: "RBR", sport: "F1",     league: "F1",              skill: "fastf1",        primary: "3671C6", secondary: "FFC906", accent: "DC0000" },
  { id: "mercedes",    name: "Mercedes-AMG",       short: "MER", sport: "F1",     league: "F1",              skill: "fastf1",        primary: "27F4D2", secondary: "000000", accent: "C0C0C0" },
  { id: "ferrari",     name: "Scuderia Ferrari",   short: "FER", sport: "F1",     league: "F1",              skill: "fastf1",        primary: "DC0000", secondary: "FFF200", accent: "000000" },
  { id: "mclaren",     name: "McLaren",            short: "MCL", sport: "F1",     league: "F1",              skill: "fastf1",        primary: "FF8000", secondary: "47C7FC", accent: "000000" },
  { id: "aston",       name: "Aston Martin",       short: "AMR", sport: "F1",     league: "F1",              skill: "fastf1",        primary: "229971", secondary: "000000", accent: "FFFFFF" },
];

// Fast lookup helpers
export const TEAMS_BY_ID = Object.fromEntries(TEAMS.map(t => [t.id, t]));

// Substring search for typeahead. Matches against name, short, sport, league.
export function searchTeams(query, limit = 8) {
  if (!query || !query.trim()) return TEAMS.slice(0, limit);
  const q = query.toLowerCase().trim();
  const scored = TEAMS.map(t => {
    const hay = `${t.name} ${t.short} ${t.sport} ${t.league}`.toLowerCase();
    if (!hay.includes(q)) return null;
    // Prefer name-starts-with over substring matches
    const starts = t.name.toLowerCase().startsWith(q) ? 0 : (t.short.toLowerCase() === q ? 0 : 1);
    return { team: t, score: starts };
  }).filter(Boolean);
  scored.sort((a, b) => a.score - b.score);
  return scored.slice(0, limit).map(s => s.team);
}
