---
name: alexa-sports-narrator
description: Alexa skill for narrating sports data in real-time using Machina sports templates and voice synthesis. Use when users ask for "sports updates", "game results", "team stats", "NFL scores", or any sports-related voice queries via Alexa.
---

# Alexa Sports Narrator

End-to-end Alexa skill that narrates sports data using Sportradar APIs, LLM content generation, and optional voice synthesis with ElevenLabs.

## Overview

This skill integrates with Amazon Alexa to provide voice-based sports updates across multiple sports:
- **NFL**: Games, scores, team stats, player performance
- **NBA**: Basketball games and statistics
- **Soccer**: Match results and standings
- **MLB, NHL**: Baseball and hockey data

## Architecture

```
Alexa Device → Lambda Function → Machina Workflow → Response
                                        ↓
                                [Sportradar API]
                                        ↓
                                [LLM Generation]
                                        ↓
                                [Alexa Response]
```

## Features

- **Multi-Sport Support**: NFL, NBA, Soccer, MLB, NHL via Sportradar
- **Natural Language**: LLM-generated conversational responses
- **Real-Time Data**: Live game scores and statistics
- **Personalization**: User preferences for favorite teams
- **Voice Synthesis**: Optional ElevenLabs TTS for custom voices
- **Multi-Language**: Support for pt-BR and en-US

## References

| Reference | Description |
|-----------|-------------|
| [setup.md](references/setup.md) | Alexa skill setup and Lambda deployment |
| [intents.md](references/intents.md) | Alexa intents and slot definitions |
| [workflows.md](references/workflows.md) | Workflow integration guide |
| [lambda.md](references/lambda.md) | Lambda handler implementation |

## Schemas

| Schema | Entity |
|--------|--------|
| [alexa-request.md](schemas/alexa-request.md) | Alexa request format |
| [alexa-response.md](schemas/alexa-response.md) | Alexa response format |
| [sports-intents.md](schemas/sports-intents.md) | Sports-specific intents |

## Workflows

### 1. `alexa-sports-query`

Main workflow for handling sports queries from Alexa.

**Inputs:**
- `intent_name`: Alexa intent (e.g., "GetNFLScoresIntent")
- `sport`: Sport type (nfl, nba, soccer, mlb, nhl)
- `team`: Optional team name or ID
- `date`: Optional date for historical queries
- `language`: Language code (default: en-US)

**Outputs:**
- `response_text`: Natural language response for Alexa
- `card_text`: Text for Alexa card display
- `should_end_session`: Boolean for session management

### 2. `alexa-personalized-update`

Personalized sports update based on user profile.

**Inputs:**
- `user_id`: Alexa user ID
- `language`: Language code

**Outputs:**
- `response_text`: Personalized update
- `favorite_teams`: User's favorite teams

## Alexa Intents

### Built-in Intents
- `AMAZON.HelpIntent`: Show help message
- `AMAZON.CancelIntent`: Cancel current action
- `AMAZON.StopIntent`: Stop skill

### Custom Intents

#### GetNFLScoresIntent
**Utterances:**
- "What were the NFL scores today"
- "Tell me the NFL results"
- "How did {team} do today"

**Slots:**
- `team` (AMAZON.SportsTeam)
- `date` (AMAZON.DATE)

#### GetTeamStatsIntent
**Utterances:**
- "How is {team} doing this season"
- "Tell me about {team}"
- "What are {team}'s stats"

**Slots:**
- `team` (AMAZON.SportsTeam)
- `sport` (SportType - custom)

#### GetPlayerStatsIntent
**Utterances:**
- "How is {player} doing"
- "Tell me about {player}"
- "What are {player}'s stats"

**Slots:**
- `player` (AMAZON.Person)

#### SetFavoriteTeamIntent
**Utterances:**
- "My favorite team is {team}"
- "I follow {team}"
- "Add {team} to my favorites"

**Slots:**
- `team` (AMAZON.SportsTeam)

## Lambda Handler

The Lambda function receives Alexa requests and routes them to Machina workflows:

```python
def lambda_handler(event, context):
    """
    Alexa skill Lambda handler
    Routes requests to Machina workflows
    """
    request_type = event['request']['type']

    if request_type == 'LaunchRequest':
        return handle_launch()
    elif request_type == 'IntentRequest':
        intent_name = event['request']['intent']['name']
        return handle_intent(intent_name, event)
    elif request_type == 'SessionEndedRequest':
        return handle_session_end()
```

## Example Interactions

### Example 1: NFL Scores
```
User: "Alexa, ask Sports Narrator for today's NFL scores"

Alexa: "Here are today's NFL scores:
        - Kansas City Chiefs defeated Buffalo Bills 27-24
        - San Francisco 49ers beat Dallas Cowboys 42-10
        - Green Bay Packers lost to Detroit Lions 31-29
        Would you like details on any specific game?"
```

### Example 2: Team Stats
```
User: "Alexa, ask Sports Narrator how the Lakers are doing"

Alexa: "The Los Angeles Lakers currently have a 35-20 record this season,
        placing them 3rd in the Western Conference. LeBron James is averaging
        25 points per game. Their next game is tomorrow against the Celtics."
```

### Example 3: Personalized Update
```
User: "Alexa, ask Sports Narrator for my sports update"

Alexa: "Here's your personalized update:
        Your Kansas City Chiefs won today 27-24 against Buffalo.
        Your Lakers play tomorrow at 7 PM against Boston.
        Your Manchester United draws 2-2 with Arsenal."
```

## Integration with Existing Templates

This skill leverages existing Machina templates:

- **sportradar-nfl**: NFL game data
- **sportradar-nba**: NBA game data
- **sportradar-soccer**: Soccer match data
- **machina-ai**: LLM response generation
- **google-genai**: Alternative LLM provider
- **elevenlabs**: Optional custom TTS (instead of Alexa voice)
- **voice-chat-completion**: Voice input processing pattern

## Configuration

### Required Secrets
```yaml
SPORTRADAR_NFL_API_KEY: Sportradar NFL API key
SPORTRADAR_NBA_API_KEY: Sportradar NBA API key
SPORTRADAR_SOCCER_API_KEY: Sportradar Soccer API key
OPENAI_API_KEY: OpenAI API key for LLM generation
```

### Optional Secrets
```yaml
ELEVENLABS_API_KEY: For custom voice synthesis
GOOGLE_GENAI_API_KEY: Alternative LLM provider
```

## Deployment

1. **Create Alexa Skill** in Amazon Developer Console
2. **Configure Interaction Model** with intents and slots
3. **Deploy Lambda Function** with Machina SDK
4. **Link Lambda ARN** to Alexa skill endpoint
5. **Configure Account Linking** (optional for personalization)
6. **Test** in Alexa Simulator

See [setup.md](references/setup.md) for detailed deployment steps.

## Development Workflow

1. **Modify Workflows**: Update YAML files in `workflows/`
2. **Test Locally**: Use Machina CLI to test workflows
3. **Update Lambda**: Deploy new Lambda version
4. **Test in Simulator**: Use Alexa Developer Console
5. **Submit for Certification**: Amazon certification process

## Feedback & Contributing

Found a bug or have an improvement idea?

- **Report issues**: [Open an issue](https://github.com/machina-sports/machina-templates/issues/new?labels=skill:alexa-sports-narrator)
- **Contribute**: Fork, fix, and open a PR against `main`
- **Include**: Expected vs actual behavior with example utterances

## Key Constraints

- **Response Time**: Lambda must respond within 8 seconds (Alexa timeout)
- **Response Length**: Alexa TTS limited to ~90 seconds of speech
- **Session Management**: Handle multi-turn conversations properly
- **Error Handling**: Always provide fallback responses
- **Rate Limits**: Respect Sportradar API rate limits (1000 req/month free tier)
