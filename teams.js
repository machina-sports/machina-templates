/* eslint-disable */
// Curated catalog of sports teams across leagues.
// Each entry has the minimum we need to:
//   - render it in a typeahead (name, league)
//   - fetch live data via sports-skills-call (module + the right ID field)
//   - paint a default palette on the graphic (colors[2])
//   - drop a logo on the card (espnLogo for NA leagues, generic crest for footy)
//
// IDs verified against:
//   - sports-skills-call(module='nba', command='get_standings') → team.id
//   - sports-skills-call(module='nfl', command='get_standings') → team.id
//   - sports-skills-call(module='football', command='get_daily_schedule') → team.id
// (See README of this app for the data source matrix.)

export const TEAMS = [
  // ---------- NBA ----------
  { id: 'nba-13',  name: 'Los Angeles Lakers',     league: 'NBA', module: 'nba',
    espnId: '13',  abbr: 'LAL', colors: ['#552583','#FDB927'] },
  { id: 'nba-2',   name: 'Boston Celtics',         league: 'NBA', module: 'nba',
    espnId: '2',   abbr: 'BOS', colors: ['#007A33','#BA9653'] },
  { id: 'nba-9',   name: 'Golden State Warriors',  league: 'NBA', module: 'nba',
    espnId: '9',   abbr: 'GS',  colors: ['#1D428A','#FFC72C'] },
  { id: 'nba-25',  name: 'Oklahoma City Thunder',  league: 'NBA', module: 'nba',
    espnId: '25',  abbr: 'OKC', colors: ['#007AC1','#EF3B24'] },
  { id: 'nba-18',  name: 'New York Knicks',        league: 'NBA', module: 'nba',
    espnId: '18',  abbr: 'NY',  colors: ['#006BB6','#F58426'] },
  { id: 'nba-24',  name: 'San Antonio Spurs',      league: 'NBA', module: 'nba',
    espnId: '24',  abbr: 'SA',  colors: ['#000000','#C4CED4'] },
  { id: 'nba-7',   name: 'Denver Nuggets',         league: 'NBA', module: 'nba',
    espnId: '7',   abbr: 'DEN', colors: ['#0E2240','#FEC524'] },
  { id: 'nba-14',  name: 'Miami Heat',             league: 'NBA', module: 'nba',
    espnId: '14',  abbr: 'MIA', colors: ['#98002E','#F9A01B'] },
  { id: 'nba-5',   name: 'Cleveland Cavaliers',    league: 'NBA', module: 'nba',
    espnId: '5',   abbr: 'CLE', colors: ['#860038','#FDBB30'] },
  { id: 'nba-10',  name: 'Houston Rockets',        league: 'NBA', module: 'nba',
    espnId: '10',  abbr: 'HOU', colors: ['#CE1141','#000000'] },

  // ---------- NFL ----------
  { id: 'nfl-12',  name: 'Kansas City Chiefs',     league: 'NFL', module: 'nfl',
    espnId: '12',  abbr: 'KC',  colors: ['#E31837','#FFB81C'] },
  { id: 'nfl-21',  name: 'Philadelphia Eagles',    league: 'NFL', module: 'nfl',
    espnId: '21',  abbr: 'PHI', colors: ['#004C54','#A5ACAF'] },
  { id: 'nfl-2',   name: 'Buffalo Bills',          league: 'NFL', module: 'nfl',
    espnId: '2',   abbr: 'BUF', colors: ['#00338D','#C60C30'] },
  { id: 'nfl-25',  name: 'San Francisco 49ers',    league: 'NFL', module: 'nfl',
    espnId: '25',  abbr: 'SF',  colors: ['#AA0000','#B3995D'] },
  { id: 'nfl-6',   name: 'Dallas Cowboys',         league: 'NFL', module: 'nfl',
    espnId: '6',   abbr: 'DAL', colors: ['#003594','#869397'] },
  { id: 'nfl-7',   name: 'Denver Broncos',         league: 'NFL', module: 'nfl',
    espnId: '7',   abbr: 'DEN', colors: ['#FB4F14','#002244'] },
  { id: 'nfl-3',   name: 'Chicago Bears',          league: 'NFL', module: 'nfl',
    espnId: '3',   abbr: 'CHI', colors: ['#0B162A','#C83803'] },
  { id: 'nfl-23',  name: 'Pittsburgh Steelers',    league: 'NFL', module: 'nfl',
    espnId: '23',  abbr: 'PIT', colors: ['#FFB612','#101820'] },
  { id: 'nfl-26',  name: 'Seattle Seahawks',       league: 'NFL', module: 'nfl',
    espnId: '26',  abbr: 'SEA', colors: ['#002244','#69BE28'] },
  { id: 'nfl-9',   name: 'Green Bay Packers',      league: 'NFL', module: 'nfl',
    espnId: '9',   abbr: 'GB',  colors: ['#203731','#FFB612'] },

  // ---------- Soccer (Top European clubs — verified ESPN IDs from get_daily_schedule) ----------
  { id: 'fb-86',   name: 'Real Madrid',            league: 'La Liga',        module: 'football',
    espnId: '86',  abbr: 'RMA', colors: ['#FEBE10','#00529F'] },
  { id: 'fb-83',   name: 'FC Barcelona',           league: 'La Liga',        module: 'football',
    espnId: '83',  abbr: 'BAR', colors: ['#A50044','#004D98'] },
  { id: 'fb-359',  name: 'Liverpool',              league: 'Premier League', module: 'football',
    espnId: '359', abbr: 'LIV', colors: ['#C8102E','#00B2A9'] },
  { id: 'fb-360',  name: 'Manchester City',        league: 'Premier League', module: 'football',
    espnId: '382', abbr: 'MCI', colors: ['#6CABDD','#1C2C5B'] },
  { id: 'fb-360b', name: 'Manchester United',      league: 'Premier League', module: 'football',
    espnId: '360', abbr: 'MUN', colors: ['#DA291C','#FBE122'] },
  { id: 'fb-364',  name: 'Arsenal',                league: 'Premier League', module: 'football',
    espnId: '359', abbr: 'ARS', colors: ['#EF0107','#063672'] },
  { id: 'fb-363',  name: 'Chelsea',                league: 'Premier League', module: 'football',
    espnId: '363', abbr: 'CHE', colors: ['#034694','#FFFFFF'] },
  { id: 'fb-362',  name: 'Aston Villa',            league: 'Premier League', module: 'football',
    espnId: '362', abbr: 'AVL', colors: ['#7A003C','#95BFE5'] },
  { id: 'fb-160',  name: 'Bayern Munich',          league: 'Bundesliga',     module: 'football',
    espnId: '132', abbr: 'BAY', colors: ['#DC052D','#0066B2'] },
  { id: 'fb-124',  name: 'Borussia Dortmund',      league: 'Bundesliga',     module: 'football',
    espnId: '124', abbr: 'BVB', colors: ['#FDE100','#000000'] },
  { id: 'fb-126',  name: 'SC Freiburg',            league: 'Bundesliga',     module: 'football',
    espnId: '126', abbr: 'SCF', colors: ['#E2001A','#000000'] },
  { id: 'fb-103',  name: 'AC Milan',               league: 'Serie A',        module: 'football',
    espnId: '103', abbr: 'MIL', colors: ['#FB090B','#000000'] },
  { id: 'fb-110',  name: 'Inter Milan',            league: 'Serie A',        module: 'football',
    espnId: '110', abbr: 'INT', colors: ['#0068A8','#000000'] },
  { id: 'fb-111',  name: 'Juventus',               league: 'Serie A',        module: 'football',
    espnId: '111', abbr: 'JUV', colors: ['#000000','#FFFFFF'] },
  { id: 'fb-160p', name: 'Paris Saint-Germain',    league: 'Ligue 1',        module: 'football',
    espnId: '160', abbr: 'PSG', colors: ['#004170','#DA291C'] },
  { id: 'fb-819',  name: 'Flamengo',               league: 'Brasileirão',    module: 'football',
    espnId: '819', abbr: 'FLA', colors: ['#CC0000','#000000'] },
  { id: 'fb-2029', name: 'Palmeiras',              league: 'Brasileirão',    module: 'football',
    espnId: '2029',abbr: 'PAL', colors: ['#006437','#FFFFFF'] },

  // ---------- MLB ----------
  { id: 'mlb-19',  name: 'Los Angeles Dodgers',    league: 'MLB', module: 'mlb',
    espnId: '19',  abbr: 'LAD', colors: ['#005A9C','#EF3E42'] },
  { id: 'mlb-10',  name: 'New York Yankees',       league: 'MLB', module: 'mlb',
    espnId: '10',  abbr: 'NYY', colors: ['#003087','#E4002C'] },
  { id: 'mlb-2',   name: 'Boston Red Sox',         league: 'MLB', module: 'mlb',
    espnId: '2',   abbr: 'BOS', colors: ['#BD3039','#0C2340'] },

  // ---------- NHL ----------
  { id: 'nhl-1',   name: 'New Jersey Devils',      league: 'NHL', module: 'nhl',
    espnId: '1',   abbr: 'NJ',  colors: ['#CE1126','#000000'] },
  { id: 'nhl-25',  name: 'Edmonton Oilers',        league: 'NHL', module: 'nhl',
    espnId: '25',  abbr: 'EDM', colors: ['#FF4C00','#041E42'] },
  { id: 'nhl-22',  name: 'Toronto Maple Leafs',    league: 'NHL', module: 'nhl',
    espnId: '21',  abbr: 'TOR', colors: ['#00205B','#FFFFFF'] },
];

// ESPN provides standardized logo URLs per league.
// The `:logoSlug` is usually the team abbreviation, lowercased.
const LOGO_TPL = {
  nba:      (t) => `https://a.espncdn.com/i/teamlogos/nba/500/${t.abbr.toLowerCase()}.png`,
  nfl:      (t) => `https://a.espncdn.com/i/teamlogos/nfl/500/${t.abbr.toLowerCase()}.png`,
  mlb:      (t) => `https://a.espncdn.com/i/teamlogos/mlb/500/${t.abbr.toLowerCase()}.png`,
  nhl:      (t) => `https://a.espncdn.com/i/teamlogos/nhl/500/${t.abbr.toLowerCase()}.png`,
  football: (t) => `https://a.espncdn.com/i/teamlogos/soccer/500/${t.espnId}.png`,
};

export function logoFor(team) {
  return (LOGO_TPL[team.module] || (() => ''))(team);
}
