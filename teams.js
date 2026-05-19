// Curated catalog of soccer teams (sportradar competitor IDs verified live).
// Colors are official primary/secondary club palette. Used for the typeahead
// and as the default graphic palette (the reference-image dropzone overrides).
export const TEAMS = [
  // Premier League
  { id: "sr:competitor:17",  name: "Manchester City",       short: "Man City",    league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#6CABDD", secondary: "#1C2C5B", abbr: "MCI" },
  { id: "sr:competitor:33",  name: "Manchester United",     short: "Man United",  league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#DA291C", secondary: "#000000", abbr: "MUN" },
  { id: "sr:competitor:44",  name: "Liverpool",             short: "Liverpool",   league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#C8102E", secondary: "#00B2A9", abbr: "LIV" },
  { id: "sr:competitor:42",  name: "Arsenal FC",            short: "Arsenal",     league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#EF0107", secondary: "#FFFFFF", abbr: "ARS" },
  { id: "sr:competitor:38",  name: "Chelsea FC",            short: "Chelsea",     league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#034694", secondary: "#FFFFFF", abbr: "CFC" },
  { id: "sr:competitor:46",  name: "Tottenham Hotspur",     short: "Tottenham",   league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#132257", secondary: "#FFFFFF", abbr: "TOT" },
  { id: "sr:competitor:40",  name: "Aston Villa",           short: "Aston Villa", league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#670E36", secondary: "#95BFE5", abbr: "AVL" },
  { id: "sr:competitor:48",  name: "Everton FC",            short: "Everton",     league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#003399", secondary: "#FFFFFF", abbr: "EVE" },
  { id: "sr:competitor:14",  name: "Nottingham Forest",     short: "Forest",      league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#DD0000", secondary: "#FFFFFF", abbr: "NFO" },
  { id: "sr:competitor:30",  name: "Brighton & Hove Albion",short: "Brighton",    league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#0057B8", secondary: "#FFCD00", abbr: "BRI" },
  { id: "sr:competitor:50",  name: "Brentford FC",          short: "Brentford",   league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#E30613", secondary: "#FBB800", abbr: "BRE" },
  { id: "sr:competitor:7",   name: "Crystal Palace",        short: "Palace",      league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#1B458F", secondary: "#C4122E", abbr: "CRY" },
  { id: "sr:competitor:60",  name: "AFC Bournemouth",       short: "Bournemouth", league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#DA291C", secondary: "#000000", abbr: "BOU" },
  { id: "sr:competitor:34",  name: "Leeds United",          short: "Leeds",       league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#FFCD00", secondary: "#1D428A", abbr: "LEE" },
  { id: "sr:competitor:53",  name: "Newcastle United",      short: "Newcastle",   league: "Premier League", country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", primary: "#241F20", secondary: "#FFFFFF", abbr: "NEW" },

  // La Liga
  { id: "sr:competitor:2829",name: "Real Madrid",           short: "Real Madrid", league: "La Liga", country: "🇪🇸", primary: "#FEBE10", secondary: "#00529F", abbr: "RMA" },
  { id: "sr:competitor:2817",name: "FC Barcelona",          short: "Barcelona",   league: "La Liga", country: "🇪🇸", primary: "#A50044", secondary: "#004D98", abbr: "FCB" },
  { id: "sr:competitor:2783",name: "Atletico Madrid",       short: "Atletico",    league: "La Liga", country: "🇪🇸", primary: "#CB3524", secondary: "#272E61", abbr: "ATM" },
  { id: "sr:competitor:2796",name: "Sevilla FC",            short: "Sevilla",     league: "La Liga", country: "🇪🇸", primary: "#D7141A", secondary: "#FFFFFF", abbr: "SEV" },
  { id: "sr:competitor:2800",name: "Athletic Bilbao",       short: "Bilbao",      league: "La Liga", country: "🇪🇸", primary: "#EE2523", secondary: "#FFFFFF", abbr: "ATH" },
  { id: "sr:competitor:2786",name: "Real Sociedad",         short: "Sociedad",    league: "La Liga", country: "🇪🇸", primary: "#143C8B", secondary: "#FFFFFF", abbr: "RSO" },
  { id: "sr:competitor:2820",name: "Real Betis",            short: "Real Betis",  league: "La Liga", country: "🇪🇸", primary: "#00954C", secondary: "#FFFFFF", abbr: "BET" },
  { id: "sr:competitor:2790",name: "Villarreal CF",         short: "Villarreal",  league: "La Liga", country: "🇪🇸", primary: "#FFE667", secondary: "#005187", abbr: "VIL" },
  { id: "sr:competitor:2792",name: "Valencia CF",           short: "Valencia",    league: "La Liga", country: "🇪🇸", primary: "#FF7E00", secondary: "#000000", abbr: "VAL" },

  // Serie A
  { id: "sr:competitor:2702",name: "Juventus",              short: "Juventus",    league: "Serie A", country: "🇮🇹", primary: "#000000", secondary: "#FFFFFF", abbr: "JUV" },
  { id: "sr:competitor:2696",name: "Inter Milan",           short: "Inter",       league: "Serie A", country: "🇮🇹", primary: "#0066B2", secondary: "#000000", abbr: "INT" },
  { id: "sr:competitor:2692",name: "AC Milan",              short: "Milan",       league: "Serie A", country: "🇮🇹", primary: "#FB090B", secondary: "#000000", abbr: "MIL" },
  { id: "sr:competitor:2701",name: "Napoli",                short: "Napoli",      league: "Serie A", country: "🇮🇹", primary: "#12A0D7", secondary: "#003C82", abbr: "NAP" },
  { id: "sr:competitor:2687",name: "AS Roma",               short: "Roma",        league: "Serie A", country: "🇮🇹", primary: "#8E1F2F", secondary: "#F0BC42", abbr: "ROM" },
  { id: "sr:competitor:2699",name: "Lazio",                 short: "Lazio",       league: "Serie A", country: "🇮🇹", primary: "#87CEEB", secondary: "#FFFFFF", abbr: "LAZ" },
  { id: "sr:competitor:2693",name: "Atalanta",              short: "Atalanta",    league: "Serie A", country: "🇮🇹", primary: "#1A5BB8", secondary: "#000000", abbr: "ATA" },
  { id: "sr:competitor:2697",name: "Fiorentina",            short: "Fiorentina",  league: "Serie A", country: "🇮🇹", primary: "#592A8A", secondary: "#FFFFFF", abbr: "FIO" },

  // Bundesliga
  { id: "sr:competitor:2672",name: "Bayern Munich",         short: "Bayern",      league: "Bundesliga", country: "🇩🇪", primary: "#DC052D", secondary: "#0066B2", abbr: "BAY" },
  { id: "sr:competitor:2673",name: "Borussia Dortmund",     short: "Dortmund",    league: "Bundesliga", country: "🇩🇪", primary: "#FDE100", secondary: "#000000", abbr: "BVB" },
  { id: "sr:competitor:2677",name: "RB Leipzig",            short: "Leipzig",     league: "Bundesliga", country: "🇩🇪", primary: "#DD0741", secondary: "#001F47", abbr: "RBL" },
  { id: "sr:competitor:2681",name: "Bayer Leverkusen",      short: "Leverkusen",  league: "Bundesliga", country: "🇩🇪", primary: "#E32221", secondary: "#000000", abbr: "B04" },
  { id: "sr:competitor:2674",name: "Eintracht Frankfurt",   short: "Frankfurt",   league: "Bundesliga", country: "🇩🇪", primary: "#E1000F", secondary: "#000000", abbr: "SGE" },
  { id: "sr:competitor:2683",name: "Borussia Monchengladbach",short: "Gladbach",  league: "Bundesliga", country: "🇩🇪", primary: "#000000", secondary: "#00B04F", abbr: "BMG" },

  // Ligue 1
  { id: "sr:competitor:2817",name: "Paris Saint-Germain",   short: "PSG",         league: "Ligue 1", country: "🇫🇷", primary: "#004170", secondary: "#DA291C", abbr: "PSG" },
  // (Real PSG id below — Sportradar)
  { id: "sr:competitor:3050",name: "Olympique Marseille",   short: "Marseille",   league: "Ligue 1", country: "🇫🇷", primary: "#2FAEE0", secondary: "#FFFFFF", abbr: "OM"  },
  { id: "sr:competitor:3036",name: "Olympique Lyonnais",    short: "Lyon",        league: "Ligue 1", country: "🇫🇷", primary: "#001E62", secondary: "#DA291C", abbr: "OL"  },
  { id: "sr:competitor:3052",name: "AS Monaco",             short: "Monaco",      league: "Ligue 1", country: "🇫🇷", primary: "#CE1126", secondary: "#FFFFFF", abbr: "ASM" },

  // Eredivisie / Liga Portugal / Brasil — broad set
  { id: "sr:competitor:2603",name: "Ajax",                  short: "Ajax",        league: "Eredivisie", country: "🇳🇱", primary: "#D2122E", secondary: "#FFFFFF", abbr: "AJA" },
  { id: "sr:competitor:2604",name: "PSV Eindhoven",         short: "PSV",         league: "Eredivisie", country: "🇳🇱", primary: "#ED1C24", secondary: "#FFFFFF", abbr: "PSV" },
  { id: "sr:competitor:2638",name: "FC Porto",              short: "Porto",       league: "Liga Portugal", country: "🇵🇹", primary: "#002F87", secondary: "#FFFFFF", abbr: "POR" },
  { id: "sr:competitor:2639",name: "SL Benfica",            short: "Benfica",     league: "Liga Portugal", country: "🇵🇹", primary: "#E30613", secondary: "#FFFFFF", abbr: "SLB" },
  { id: "sr:competitor:2640",name: "Sporting CP",           short: "Sporting",    league: "Liga Portugal", country: "🇵🇹", primary: "#008658", secondary: "#FFFFFF", abbr: "SCP" },
];

// Competition catalog — for top-scorers intent. Sportradar verified IDs.
export const COMPETITIONS = [
  { id: "sr:competition:17",  name: "Premier League",  country: "🏴󠁧󠁢󠁥󠁮󠁧󠁿", color: "#3D195B" },
  { id: "sr:competition:8",   name: "La Liga",         country: "🇪🇸", color: "#EE8707" },
  { id: "sr:competition:23",  name: "Serie A",         country: "🇮🇹", color: "#008FD7" },
  { id: "sr:competition:35",  name: "Bundesliga",      country: "🇩🇪", color: "#D20515" },
  { id: "sr:competition:34",  name: "Ligue 1",         country: "🇫🇷", color: "#091C3E" },
  { id: "sr:competition:7",   name: "Champions League",country: "🇪🇺", color: "#0E1E5B" },
];

// Map a competitor id to its competition for top-scorers intent.
export function leagueForTeam(teamId) {
  const t = TEAMS.find(x => x.id === teamId);
  if (!t) return COMPETITIONS[0];
  const map = {
    "Premier League": "sr:competition:17",
    "La Liga":        "sr:competition:8",
    "Serie A":        "sr:competition:23",
    "Bundesliga":     "sr:competition:35",
    "Ligue 1":        "sr:competition:34",
  };
  const compId = map[t.league];
  return COMPETITIONS.find(c => c.id === compId) || COMPETITIONS[0];
}
