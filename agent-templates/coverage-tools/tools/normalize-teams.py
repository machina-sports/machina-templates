def invoke_normalize_teams(request_data):
    """
    Normalize team names and map competition IDs to league codes.
    
    Examples:
        Input: {"team_a_name": "Cagliari Calcio", "team_b_name": "Genoa CFC", 
                "competition_id": "sr:competition:23"}
        Output: {"team_a_name_normalized": "Cagliari", 
                 "team_b_name_normalized": "Genoa",
                 "league_code": "ita-serie-a"}
    """
    params = request_data.get("params", {})
    
    team_a_name = params.get("team_a_name", "")
    team_b_name = params.get("team_b_name", "")
    competition_id = params.get("competition_id", "")
    default_league = params.get("league_code", "bra-serie-a")
    
    # Define team name suffixes to remove
    suffixes = [
        ' Calcio', ' CFC', ' FC', ' SC', ' EC', ' AC', ' CF', ' SV',
        ' United', ' City', ' Town', ' Wanderers', ' Rovers',
        ' FBPA', ' MG', ' RJ', ' SP', ' RS', ' BA', ' PE', ' CE', ' GO', ' PR',
        ' de Futebol', ' Futebol Clube', ' Esporte Clube', ' Sport Club',
        ' Football Club', ' Association', ' Fußball-Club', ' Fußballclub',
        ' Foot', ' Fodbold', ' Fotball', ' 1. FC'
    ]
    
    # Normalize team A name
    team_a_normalized = team_a_name
    if team_a_name:
        for suffix in suffixes:
            if team_a_name.endswith(suffix):
                team_a_normalized = team_a_name[:-len(suffix)].strip()
                break
        else:
            team_a_normalized = team_a_name.strip()
    
    # Normalize team B name
    team_b_normalized = team_b_name
    if team_b_name:
        for suffix in suffixes:
            if team_b_name.endswith(suffix):
                team_b_normalized = team_b_name[:-len(suffix)].strip()
                break
        else:
            team_b_normalized = team_b_name.strip()
    
    # Map competition ID to league code (only Tallysight available competitions)
    league_code = default_league
    if competition_id:
        # Remove URN prefix if present
        comp_id = competition_id.replace('urn:sportradar:competition:', '')
        
        # Competition to league mapping (based on Tallysight available leagues)
        competition_mapping = {
            'sr:competition:17': 'premier-league',         # Premier League (ENG)
            'sr:competition:23': 'serie-a',                # Serie A (ITA)
            'sr:competition:325': 'bra-serie-a',           # Brasileiro Serie A
            'sr:competition:7': 'uefa-champions-league',   # UEFA Champions League
            'sr:competition:384': 'copa-libertadores',     # CONMEBOL Libertadores
            'sr:competition:480': 'copa-sudamericana',     # CONMEBOL Sudamericana
            'sr:competition:373': 'copa-do-brasil',        # Copa do Brasil
            'sr:competition:92': 'cariocao-serie-a',       # Campeonato Carioca Serie A
            'sr:competition:372': 'paulista-serie-a1'      # Campeonato Paulista Serie A1
        }
        
        league_code = competition_mapping.get(comp_id, default_league)
    
    return {
        "status": True,
        "message": "Team names normalized successfully",
        "data": {
            "team_a_name_normalized": team_a_normalized,
            "team_b_name_normalized": team_b_normalized,
            "league_code": league_code
        }
    }
