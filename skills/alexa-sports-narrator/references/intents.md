# Alexa Intents Reference

Complete reference for all Alexa intents used in the Sports Narrator skill.

## Built-in Intents

### AMAZON.HelpIntent

**Purpose**: Provide help information when user asks for help

**Sample Utterances**:
- "help"
- "help me"
- "what can I do"
- "what can you do"

**Handler Response**:
- Lists example commands
- Asks follow-up question
- Keeps session open

**Example**:
```
User: "Alexa, ask Sports Narrator for help"
Alexa: "You can ask me things like: What were the NFL scores today? How are the Lakers doing this season? Give me my personalized sports update. What would you like to know?"
```

---

### AMAZON.CancelIntent

**Purpose**: Cancel current action

**Sample Utterances**:
- "cancel"
- "never mind"
- "forget it"

**Handler Response**:
- Says goodbye
- Ends session

---

### AMAZON.StopIntent

**Purpose**: Stop the skill

**Sample Utterances**:
- "stop"
- "exit"
- "quit"

**Handler Response**:
- Says goodbye
- Ends session

---

## Custom Sports Intents

### GetNFLScoresIntent

**Purpose**: Get NFL game scores and results

**Slots**:
- `team` (AMAZON.SportsTeam) - Optional team name
- `date` (AMAZON.DATE) - Optional date for historical queries

**Sample Utterances**:
```
"what were the NFL scores today"
"tell me the NFL results"
"NFL scores"
"how did {team} do today"
"how did {team} do"
"did {team} win today"
"what was the {team} score"
"give me NFL scores for {date}"
"what were yesterday's NFL games"
"NFL results from {date}"
```

**Example Interactions**:

**General scores**:
```
User: "What were the NFL scores today?"
Alexa: "Here are today's NFL scores:
        Kansas City Chiefs defeated Buffalo Bills 27-24
        San Francisco 49ers beat Dallas Cowboys 42-10
        Green Bay Packers lost to Detroit Lions 31-29
        Would you like details on any specific game?"
```

**Specific team**:
```
User: "How did the Chiefs do today?"
Alexa: "The Kansas City Chiefs won today, defeating the Buffalo Bills 27 to 24. Patrick Mahomes threw for 320 yards and 3 touchdowns."
```

**Historical query**:
```
User: "What were the NFL scores last Sunday?"
Alexa: "Last Sunday's NFL games included..."
```

---

### GetNBAScoresIntent

**Purpose**: Get NBA game scores and results

**Slots**:
- `team` (AMAZON.SportsTeam) - Optional team name
- `date` (AMAZON.DATE) - Optional date

**Sample Utterances**:
```
"what were the NBA scores today"
"tell me the NBA results"
"NBA scores"
"how did the {team} do in basketball"
"basketball scores"
"NBA games today"
"who won in the NBA"
"NBA results from {date}"
```

**Example**:
```
User: "What were the NBA scores today?"
Alexa: "Today's NBA scores:
        Lakers defeated Warriors 112-108
        Celtics beat Heat 120-117
        Bucks won against Nets 125-110"
```

---

### GetSoccerScoresIntent

**Purpose**: Get soccer/football match results

**Slots**:
- `team` (AMAZON.SportsTeam) - Optional team name
- `date` (AMAZON.DATE) - Optional date

**Sample Utterances**:
```
"what were the soccer scores"
"tell me the soccer results"
"soccer scores today"
"football scores"
"how did {team} do in soccer"
"premier league scores"
"champions league results"
```

**Example**:
```
User: "What were the Premier League scores?"
Alexa: "Today's Premier League results:
        Manchester United drew 2-2 with Arsenal
        Liverpool defeated Chelsea 3-1
        Manchester City won 4-0 against Newcastle"
```

---

### GetTeamStatsIntent

**Purpose**: Get team statistics and season performance

**Slots**:
- `team` (AMAZON.SportsTeam) - Required team name
- `sport` (SportType - custom) - Optional sport type

**Sample Utterances**:
```
"how is {team} doing this season"
"tell me about {team}"
"what are {team}'s stats"
"{team} statistics"
"how are the {team} doing"
"{team} season stats"
"how is {team} performing"
"tell me about the {team} season"
```

**Example**:
```
User: "How are the Lakers doing this season?"
Alexa: "The Los Angeles Lakers currently have a 35-20 record, placing them 3rd in the Western Conference. They've won 7 of their last 10 games. LeBron James is averaging 25 points per game."
```

---

### GetPlayerStatsIntent

**Purpose**: Get individual player statistics

**Slots**:
- `player` (AMAZON.Person) - Required player name

**Sample Utterances**:
```
"how is {player} doing"
"tell me about {player}"
"what are {player}'s stats"
"{player} statistics"
"{player} performance"
"how many points does {player} have"
```

**Example**:
```
User: "How is Patrick Mahomes doing?"
Alexa: "Patrick Mahomes has thrown for 4,200 yards this season with 35 touchdowns and 8 interceptions. His passer rating is 105.3, and he's led the Chiefs to a 12-3 record."
```

---

### GetPersonalizedUpdateIntent

**Purpose**: Get personalized update for user's favorite teams

**Slots**: None

**Sample Utterances**:
```
"give me my sports update"
"my personalized update"
"my sports news"
"what's happening with my teams"
"update me on my teams"
"how are my teams doing"
```

**Example**:
```
User: "Give me my personalized sports update"
Alexa: "Here's your update:
        Your Chiefs won today 27-24 against Buffalo
        Your Lakers play tomorrow at 7 PM against the Celtics
        Your Manchester United drew 2-2 with Arsenal"
```

**First time user**:
```
User: "Give me my personalized sports update"
Alexa: "You haven't set any favorite teams yet. Say: My favorite team is the Kansas City Chiefs, to add a team."
```

---

### SetFavoriteTeamIntent

**Purpose**: Add a team to user's favorites

**Slots**:
- `team` (AMAZON.SportsTeam) - Required team name
- `sport` (SportType - custom) - Optional sport type

**Sample Utterances**:
```
"my favorite team is {team}"
"I follow {team}"
"add {team} to my favorites"
"I'm a {team} fan"
"I like {team}"
"set {team} as my favorite"
"I support {team}"
"my team is {team}"
```

**Example**:
```
User: "My favorite team is the Chiefs"
Alexa: "Great! I've added the Kansas City Chiefs to your favorite teams. You can now ask for your personalized sports update."
```

**Adding multiple teams**:
```
User: "My favorite team is the Lakers"
Alexa: "Perfect! I've added the Los Angeles Lakers to your favorites."

User: "I also follow Manchester United"
Alexa: "Excellent! Manchester United has been added to your favorite teams."
```

---

## Custom Slot Types

### SportType

**Values**:
- `nfl` (synonyms: "football", "american football")
- `nba` (synonyms: "basketball")
- `soccer` (synonyms: "football", "futbol")
- `mlb` (synonyms: "baseball")
- `nhl` (synonyms: "hockey", "ice hockey")

**Usage**:
```
User: "How are the Lakers doing in basketball?"
       → sport = "nba"

User: "Tell me about the Chiefs in football"
       → sport = "nfl"
```

---

## Intent Resolution Flow

```
Alexa Request
    ↓
Lambda Handler
    ↓
Intent Router
    ↓
┌─────────────────────────────┐
│ GetNFLScoresIntent          │ → alexa-sports-query workflow
│ GetNBAScoresIntent          │ → alexa-sports-query workflow
│ GetSoccerScoresIntent       │ → alexa-sports-query workflow
│ GetTeamStatsIntent          │ → alexa-sports-query workflow
│ GetPlayerStatsIntent        │ → alexa-sports-query workflow
│ GetPersonalizedUpdateIntent │ → alexa-personalized-update workflow
│ SetFavoriteTeamIntent       │ → alexa-save-favorite-team workflow
│ AMAZON.HelpIntent           │ → handle_help()
│ AMAZON.CancelIntent         │ → handle_cancel()
│ AMAZON.StopIntent           │ → handle_stop()
└─────────────────────────────┘
    ↓
Response Builder
    ↓
Alexa Response
```

---

## Slot Value Resolution

### Team Slot Resolution

Alexa automatically resolves team names to canonical values:

```
User says: "the Lakers" → resolved to "Los Angeles Lakers"
User says: "KC Chiefs" → resolved to "Kansas City Chiefs"
User says: "Man U" → resolved to "Manchester United"
```

### Date Slot Resolution

Alexa resolves relative dates to ISO format:

```
User says: "today" → resolved to "2024-02-23"
User says: "yesterday" → resolved to "2024-02-22"
User says: "last Sunday" → resolved to "2024-02-18"
```

---

## Error Handling

### Missing Required Slots

If a required slot is missing, prompt the user:

```javascript
if (!team_name) {
    return build_response(
        "I didn't catch the team name. Which team are you asking about?",
        should_end_session=False
    )
}
```

### Invalid Slot Values

Handle unexpected values gracefully:

```javascript
if (sport not in ['nfl', 'nba', 'soccer', 'mlb', 'nhl']) {
    return build_response(
        "I'm sorry, I don't have data for that sport yet. Try NFL, NBA, or Soccer.",
        should_end_session=True
    )
}
```

### API Errors

Always provide fallback responses:

```javascript
try {
    // API call
} catch (error) {
    return build_response(
        "Sorry, I couldn't get the sports data right now. Please try again later.",
        should_end_session=True
    )
}
```

---

## Best Practices

1. **Keep responses concise**: Alexa users prefer brief updates
2. **Use natural language**: "The Chiefs won" vs "KC defeated BUF"
3. **Provide context**: Include score, key stats, next game
4. **Offer follow-ups**: "Would you like details on any game?"
5. **Handle errors gracefully**: Never leave user hanging
6. **Support variations**: "Lakers" vs "Los Angeles Lakers"
7. **Respect session state**: Keep relevant sessions open

---

## Testing Intents

### Via Alexa Simulator

1. Go to Test tab in Alexa Developer Console
2. Type or speak utterances
3. Check responses

### Via Lambda Test Events

Create test events in Lambda console:

```json
{
  "request": {
    "type": "IntentRequest",
    "intent": {
      "name": "GetNFLScoresIntent",
      "slots": {
        "team": {
          "value": "Chiefs"
        }
      }
    },
    "locale": "en-US"
  },
  "session": {
    "user": {
      "userId": "test-user-123"
    }
  }
}
```

### Via Machina CLI

Test workflows directly:

```bash
machina workflow run alexa-sports-query \
  --input '{
    "intent_name": "GetNFLScoresIntent",
    "sport": "nfl",
    "team": "Chiefs",
    "language": "en-US"
  }'
```

---

## Portuguese (pt-BR) Variations

All intents support Portuguese utterances:

```
"quais foram os resultados da NFL hoje" → GetNFLScoresIntent
"como está o Lakers nesta temporada" → GetTeamStatsIntent
"meu time favorito é o Flamengo" → SetFavoriteTeamIntent
```

See `alexa-model/pt-BR.json` for complete list.
