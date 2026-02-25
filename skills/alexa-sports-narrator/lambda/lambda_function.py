"""
Alexa Sports Narrator - Lambda Handler
Integrates with Machina workflows to provide sports updates via Alexa
"""

import os
import json
import logging
import requests
from datetime import datetime
from typing import Dict, Any

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Get Machina API configuration
MACHINA_BASE_URL = os.environ.get('MACHINA_BASE_URL', 'https://api.machina.sports')
MACHINA_API_KEY = os.environ.get('MACHINA_API_KEY', '')


def get_nfl_season_info():
    """Determine current NFL season year and type based on today's date."""
    now = datetime.utcnow()
    year, month = now.year, now.month
    if month <= 2:
        # Jan-Feb: postseason of the previous year's season
        return str(year - 1), 'POST'
    elif month <= 8:
        # Mar-Aug: offseason, show previous regular season
        return str(year - 1), 'REG'
    else:
        # Sep-Dec: current regular season
        return str(year), 'REG'


def get_nba_season_info():
    """Determine current NBA season year and type based on today's date."""
    now = datetime.utcnow()
    year, month = now.year, now.month
    if month >= 10:
        # Oct-Dec: new season started, use current year
        return str(year), 'REG'
    else:
        # Jan-Sep: previous season year
        return str(year - 1), 'REG'


def call_machina_workflow(workflow_name: str, inputs: Dict[str, Any]) -> Dict[str, Any]:
    """Call Machina workflow via REST API (synchronous via skip_delay=True)"""
    try:
        url = f"{MACHINA_BASE_URL}/workflow/executor/{workflow_name}"
        headers = {
            'Content-Type': 'application/json',
            'X-Api-Token': MACHINA_API_KEY
        }

        # skip_delay=True makes Machina execute synchronously and return outputs inline
        inputs['skip_delay'] = True

        logger.info(f"Calling workflow: {workflow_name} at {url}")
        logger.info(f"Inputs: {json.dumps(inputs)}")

        response = requests.post(url, json=inputs, headers=headers, timeout=25)
        response.raise_for_status()

        data = response.json()
        logger.info(f"Workflow response: {json.dumps(data)}")

        # With skip_delay=True the response is:
        # {"status": 200, "data": {"status": true, "data": {"workflow_run_id": "...", "outputs": {...}}}}
        if isinstance(data, dict) and 'data' in data:
            inner = data.get('data', {})
            outputs = inner.get('data', {}).get('outputs', {})
            if outputs:
                return outputs

        return data
    except Exception as e:
        logger.error(f"Error calling workflow {workflow_name}: {str(e)}", exc_info=True)
        return {"status": False, "error": str(e)}


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler for Alexa skill requests

    Args:
        event: Alexa request event
        context: Lambda context

    Returns:
        Alexa response format
    """
    logger.info(f"Received event: {json.dumps(event)}")

    try:
        request_type = event['request']['type']

        if request_type == 'LaunchRequest':
            return handle_launch_request(event)
        elif request_type == 'IntentRequest':
            return handle_intent_request(event)
        elif request_type == 'SessionEndedRequest':
            return handle_session_ended_request(event)
        else:
            logger.warning(f"Unknown request type: {request_type}")
            return build_response("Sorry, I didn't understand that request.")

    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        return build_response("Sorry, I encountered an error. Please try again.")


def handle_launch_request(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle LaunchRequest - when user opens the skill"""
    language = event.get('request', {}).get('locale', 'en-US')

    if language.startswith('pt'):
        speech_text = "Bem-vindo ao Narrador Esportivo! Você pode me perguntar sobre resultados da NFL, NBA, futebol e muito mais. O que você gostaria de saber?"
        card_title = "Narrador Esportivo"
    else:
        speech_text = "Welcome to Sports Narrator! You can ask me about NFL scores, NBA results, soccer matches, and more. What would you like to know?"
        card_title = "Sports Narrator"

    return build_response(
        speech_text=speech_text,
        card_title=card_title,
        card_text=speech_text,
        should_end_session=False
    )


def handle_intent_request(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle IntentRequest - when user invokes a specific intent"""
    intent = event['request']['intent']
    intent_name = intent['name']
    session = event.get('session', {})
    user_id = session.get('user', {}).get('userId', 'unknown')
    language = event.get('request', {}).get('locale', 'en-US')

    logger.info(f"Processing intent: {intent_name}")

    # Inject Alexa API context into intent for handlers that need it (e.g. Reminders API)
    system = event.get('context', {}).get('System', {})
    intent['_event_context'] = {
        'api_access_token': system.get('apiAccessToken', ''),
        'api_endpoint': system.get('apiEndpoint', 'https://api.amazonalexa.com')
    }

    # Route to appropriate handler
    intent_handlers = {
        'GetNFLScoresIntent': handle_sports_query,
        'GetNBAScoresIntent': handle_sports_query,
        'GetSoccerScoresIntent': handle_sports_query,
        'GetTeamStatsIntent': handle_sports_query,
        'GetPlayerStatsIntent': handle_sports_query,
        'GetPersonalizedUpdateIntent': handle_personalized_update,
        'SetFavoriteTeamIntent': handle_set_favorite_team,
        'SetGameReminderIntent': handle_set_game_reminder,
        'AMAZON.HelpIntent': handle_help,
        'AMAZON.CancelIntent': handle_cancel,
        'AMAZON.StopIntent': handle_stop,
    }

    handler = intent_handlers.get(intent_name)
    if handler:
        return handler(intent, user_id, language)
    else:
        logger.warning(f"No handler for intent: {intent_name}")
        return build_response("I'm sorry, I don't know how to help with that yet.")


def handle_sports_query(intent: Dict[str, Any], user_id: str, language: str) -> Dict[str, Any]:
    """Handle sports query intents (NFL, NBA, Soccer, etc.)"""
    intent_name = intent['name']
    slots = intent.get('slots', {})

    # Extract slot values
    team = slots.get('team', {}).get('value')
    date = slots.get('date', {}).get('value')
    player = slots.get('player', {}).get('value')

    # Determine sport type
    sport_map = {
        'GetNFLScoresIntent': 'nfl',
        'GetNBAScoresIntent': 'nba',
        'GetSoccerScoresIntent': 'soccer',
    }
    sport = sport_map.get(intent_name, 'nfl')

    # Build workflow inputs
    workflow_inputs = {
        'intent_name': intent_name,
        'sport': sport,
        'team': team,
        'player': player,
        'date': date,
        'language': language,
        'user_id': user_id
    }

    # Pass season info dynamically so the workflow uses current data
    if sport == 'nfl':
        season_year, season_type = get_nfl_season_info()
        workflow_inputs['season_year'] = season_year
        workflow_inputs['season_type'] = season_type
    elif sport == 'nba':
        season_year, season_type = get_nba_season_info()
        workflow_inputs['season_year'] = season_year
        workflow_inputs['season_type'] = season_type

    result = call_machina_workflow('alexa-sports-query', workflow_inputs)

    # Extract the actual response produced by the workflow
    response_text = result.get('response_text') or "Sorry, I couldn't get the sports information right now. Please try again later."
    card_title = result.get('card_title', f"{sport.upper()} Update")
    card_text = result.get('card_text', '')
    should_end_session = result.get('should_end_session', True)

    return build_response(
        speech_text=response_text,
        card_title=card_title,
        card_text=card_text,
        should_end_session=should_end_session
    )


def handle_personalized_update(intent: Dict[str, Any], user_id: str, language: str) -> Dict[str, Any]:
    """Handle personalized sports update intent"""
    nfl_year, nfl_type = get_nfl_season_info()
    nba_year, nba_type = get_nba_season_info()

    workflow_inputs = {
        'user_id': user_id,
        'language': language,
        'nfl_season_year': nfl_year,
        'nfl_season_type': nfl_type,
        'nba_season_year': nba_year,
        'nba_season_type': nba_type,
    }

    result = call_machina_workflow('alexa-personalized-update', workflow_inputs)

    if language.startswith('pt'):
        fallback = "Não consegui buscar suas atualizações agora. Tente novamente em breve."
    else:
        fallback = "I couldn't get your updates right now. Please try again shortly."

    response_text = result.get('response_text') or fallback

    return build_response(
        speech_text=response_text,
        card_title="Personalized Update",
        card_text=response_text[:200],
        should_end_session=False
    )


NFL_TEAMS = {
    'chiefs', 'eagles', 'bills', 'ravens', 'lions', 'cowboys', 'packers', '49ers',
    'niners', 'dolphins', 'jets', 'patriots', 'steelers', 'bengals', 'browns',
    'texans', 'colts', 'jaguars', 'titans', 'broncos', 'chargers', 'raiders',
    'commanders', 'giants', 'bears', 'vikings', 'saints', 'falcons', 'buccaneers',
    'bucs', 'panthers', 'seahawks', 'rams', 'cardinals',
}

NBA_TEAMS = {
    'lakers', 'celtics', 'warriors', 'nuggets', 'heat', 'bucks', 'suns', 'nets',
    'knicks', 'sixers', '76ers', 'cavaliers', 'cavs', 'clippers', 'mavericks',
    'mavs', 'rockets', 'grizzlies', 'pelicans', 'hawks', 'raptors', 'bulls',
    'blazers', 'trail blazers', 'jazz', 'kings', 'timberwolves', 'wolves',
    'spurs', 'magic', 'pacers', 'pistons', 'hornets', 'wizards', 'thunder',
}


def infer_sport(team_name: str) -> str:
    """Infer sport from team name when no sport slot is provided."""
    name_lower = team_name.lower()
    for nfl_team in NFL_TEAMS:
        if nfl_team in name_lower:
            return 'nfl'
    for nba_team in NBA_TEAMS:
        if nba_team in name_lower:
            return 'nba'
    return 'soccer'


def handle_set_favorite_team(intent: Dict[str, Any], user_id: str, language: str) -> Dict[str, Any]:
    """Handle set favorite team intent"""
    slots = intent.get('slots', {})
    # en-US uses slot 'teamName' (AMAZON.SearchQuery), pt-BR uses 'team' (SportTeam)
    team = (slots.get('teamName', {}).get('value')
            or slots.get('team', {}).get('value')
            or 'your team')
    sport = slots.get('sport', {}).get('value') or infer_sport(team)

    workflow_inputs = {
        'user_id': user_id,
        'team_name': team,
        'sport': sport,
        'language': language
    }

    result = call_machina_workflow('alexa-save-favorite-team', workflow_inputs)

    response_text = result.get('response_text')
    if not response_text:
        if language.startswith('pt'):
            response_text = f"Ótimo! Salvei {team} como seu time favorito."
        else:
            response_text = f"Great! I've saved {team} as your favorite team."

    return build_response(
        speech_text=response_text,
        card_title="Favorite Team Saved",
        card_text=response_text,
        should_end_session=False
    )


def handle_set_game_reminder(intent: Dict[str, Any], user_id: str, language: str) -> Dict[str, Any]:
    """Handle set game reminder intent — finds next match and sets Alexa Reminder"""
    event_context = intent.get('_event_context', {})
    api_access_token = event_context.get('api_access_token', '')
    api_endpoint = event_context.get('api_endpoint', 'https://api.amazonalexa.com')

    nfl_year, nfl_type = get_nfl_season_info()
    nba_year, nba_type = get_nba_season_info()

    workflow_inputs = {
        'user_id': user_id,
        'language': language,
        'nfl_season_year': nfl_year,
        'nfl_season_type': nfl_type,
        'nba_season_year': nba_year,
        'nba_season_type': nba_type,
    }

    result = call_machina_workflow('alexa-next-match', workflow_inputs)
    next_match = result.get('next_match')

    if not next_match or not next_match.get('start_time'):
        if language.startswith('pt'):
            msg = "Não encontrei jogos agendados para seus times favoritos no momento."
        else:
            msg = "I couldn't find any upcoming games for your favorite teams right now."
        return build_response(speech_text=msg, card_title="Game Reminder", card_text=msg, should_end_session=True)

    team = next_match.get('team', 'Your team')
    opponent = next_match.get('opponent', 'TBD')
    venue = next_match.get('venue', '')
    start_time = next_match.get('start_time', '')  # ISO 8601 UTC
    competition = next_match.get('competition', '')

    # Set reminder 1 hour before match
    reminder_set = False
    if api_access_token and start_time:
        try:
            from datetime import timezone, timedelta
            match_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            reminder_dt = match_dt - timedelta(hours=1)
            # scheduledTime must be in UTC to match the timezone_id below
            scheduled_time = reminder_dt.strftime('%Y-%m-%dT%H:%M:%S.000')

            if language.startswith('pt'):
                reminder_text = f"{team} joga daqui a uma hora contra {opponent}{' em ' + venue if venue else ''}!"
            else:
                reminder_text = f"{team} plays in one hour against {opponent}{' at ' + venue if venue else ''}!"

            reminder_payload = {
                "requestTime": datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                "trigger": {
                    "type": "SCHEDULED_ABSOLUTE",
                    "scheduledTime": scheduled_time,
                    "timeZoneId": "UTC"
                },
                "alertInfo": {
                    "spokenInfo": {
                        "content": [{"locale": language, "text": reminder_text}]
                    }
                },
                "pushNotification": {"status": "ENABLED"}
            }

            reminder_response = requests.post(
                f"{api_endpoint}/v1/alerts/reminders",
                json=reminder_payload,
                headers={
                    'Authorization': f'Bearer {api_access_token}',
                    'Content-Type': 'application/json'
                },
                timeout=10
            )
            reminder_set = reminder_response.status_code in [200, 201]
            logger.info(f"Reminders API response: {reminder_response.status_code}")
        except Exception as e:
            logger.error(f"Failed to set reminder: {str(e)}", exc_info=True)

    # Build confirmation response
    match_date = start_time[:10] if start_time else 'TBD'
    match_time = start_time[11:16] + ' UTC' if len(start_time) >= 16 else ''

    if language.startswith('pt'):
        if reminder_set:
            speech = f"Tudo certo! {team} joga contra {opponent}{' em ' + venue if venue else ''} em {match_date}. Vou te lembrar uma hora antes!"
        else:
            speech = f"{team} joga contra {opponent}{' em ' + venue if venue else ''} em {match_date}{' às ' + match_time if match_time else ''}."
    else:
        if reminder_set:
            speech = f"Done! {team} plays against {opponent}{' at ' + venue if venue else ''} on {match_date}. I'll remind you one hour before!"
        else:
            speech = f"{team} plays against {opponent}{' at ' + venue if venue else ''} on {match_date}{' at ' + match_time if match_time else ''}."

    return build_response(
        speech_text=speech,
        card_title=f"Next Game: {team}",
        card_text=f"{team} vs {opponent} | {match_date} | {venue or competition}",
        should_end_session=True
    )


def handle_help(intent: Dict[str, Any], user_id: str, language: str) -> Dict[str, Any]:
    """Handle help intent"""
    if language.startswith('pt'):
        speech_text = "Você pode me perguntar sobre resultados de jogos, estatísticas de times, ou salvar seus times favoritos. Por exemplo, diga: Quais foram os resultados da NFL hoje?"
    else:
        speech_text = "You can ask me about game scores, team statistics, or save your favorite teams. For example, say: What were the NFL scores today?"

    return build_response(
        speech_text=speech_text,
        card_title="Help",
        card_text=speech_text,
        should_end_session=False
    )


def handle_cancel(intent: Dict[str, Any], user_id: str, language: str) -> Dict[str, Any]:
    """Handle cancel intent"""
    if language.startswith('pt'):
        speech_text = "Até logo!"
    else:
        speech_text = "Goodbye!"

    return build_response(speech_text=speech_text, should_end_session=True)


def handle_stop(intent: Dict[str, Any], user_id: str, language: str) -> Dict[str, Any]:
    """Handle stop intent"""
    if language.startswith('pt'):
        speech_text = "Até logo!"
    else:
        speech_text = "Goodbye!"

    return build_response(speech_text=speech_text, should_end_session=True)


def handle_session_ended_request(event: Dict[str, Any]) -> Dict[str, Any]:
    """Handle SessionEndedRequest"""
    logger.info("Session ended")
    return {}


def build_response(
    speech_text: str,
    card_title: str = "Sports Narrator",
    card_text: str = "",
    should_end_session: bool = True
) -> Dict[str, Any]:
    """
    Build Alexa response format

    Args:
        speech_text: Text for Alexa to speak
        card_title: Title for card display
        card_text: Text for card display
        should_end_session: Whether to end the session

    Returns:
        Alexa response dictionary
    """
    return {
        'version': '1.0',
        'response': {
            'outputSpeech': {
                'type': 'PlainText',
                'text': speech_text
            },
            'card': {
                'type': 'Simple',
                'title': card_title,
                'content': card_text or speech_text
            },
            'shouldEndSession': should_end_session
        }
    }
