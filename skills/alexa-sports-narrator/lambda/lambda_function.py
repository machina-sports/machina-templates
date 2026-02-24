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
    """Call Machina workflow via REST API"""
    try:
        url = f"{MACHINA_BASE_URL}/workflow/executor/{workflow_name}"
        headers = {
            'Content-Type': 'application/json',
            'X-Api-Token': MACHINA_API_KEY
        }

        logger.info(f"Calling workflow: {workflow_name} at {url}")
        logger.info(f"Inputs: {json.dumps(inputs)}")

        response = requests.post(url, json=inputs, headers=headers, timeout=25)
        response.raise_for_status()

        data = response.json()
        logger.info(f"Workflow response: {json.dumps(data)}")

        # Machina API returns {'status': True, 'data': {'outputs': {...}, 'totals': {...}}}
        # Extract the workflow outputs so handlers can read keys directly
        if isinstance(data, dict) and 'data' in data:
            outputs = data.get('data', {}).get('outputs', {})
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

    # Route to appropriate handler
    intent_handlers = {
        'GetNFLScoresIntent': handle_sports_query,
        'GetNBAScoresIntent': handle_sports_query,
        'GetSoccerScoresIntent': handle_sports_query,
        'GetTeamStatsIntent': handle_sports_query,
        'GetPlayerStatsIntent': handle_sports_query,
        'GetPersonalizedUpdateIntent': handle_personalized_update,
        'SetFavoriteTeamIntent': handle_set_favorite_team,
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
        'season_id': 'sr:season:128461'  # Brasileirao Serie A
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
        should_end_session=True
    )


def handle_set_favorite_team(intent: Dict[str, Any], user_id: str, language: str) -> Dict[str, Any]:
    """Handle set favorite team intent"""
    slots = intent.get('slots', {})
    team = slots.get('team', {}).get('value', 'your team')
    sport = slots.get('sport', {}).get('value', 'soccer')

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
