# Creating Quizzes with Machina

## Overview

Machina can generate sports quizzes, trivia questions, and interactive content using LLMs. This guide covers quiz generation, storage, and retrieval.

## Basic Quiz Generation

### Simple Quiz Workflow

```yaml
workflow:
  name: "generate-quiz"
  title: "Generate Sports Quiz"
  description: "Create a sports quiz from event data"
  
  context-variables:
    machina-ai:
      api_key: "$TEMP_CONTEXT_VARIABLE_SDK_OPENAI_API_KEY"
  
  inputs:
    event_code: "$.get('event_code')"
    difficulty: "$.get('difficulty', 'medium')"
    num_questions: "$.get('num_questions', 5)"
  
  tasks:
    # Load event data
    - type: document
      name: load-event
      config:
        action: search
        search-vector: false
      filters:
        name: "'sport:Event'"
      inputs:
        metadata.event_code: "$.get('event_code')"
      outputs:
        event_data: "$.get('documents')[0].get('value', {})"
    
    # Generate quiz
    - type: prompt
      name: generate-quiz-prompt
      connector:
        name: "machina-ai"
        command: "invoke_prompt"
        model: "gpt-4o"
      inputs:
        event_data: "$.get('event_data')"
        difficulty: "$.get('difficulty')"
        num_questions: "$.get('num_questions')"
      outputs:
        quiz_data: "$"
    
    # Save quiz to database
    - type: document
      name: save-quiz
      config:
        action: save
        embed-vector: true
      documents:
        content-quiz: "$.get('quiz_data')"
      metadata:
        event_code: "$.get('event_code')"
        difficulty: "$.get('difficulty')"
        created_at: "datetime.now().isoformat()"
```

## Quiz Prompt with Structured Output

Define a schema for consistent quiz format:

```yaml
prompts:
  - type: prompt
    name: "quiz-generator-prompt"
    title: "Quiz Generator"
    instruction: |
      Generate a sports quiz based on the provided event data.
      
      REQUIREMENTS:
      - Create engaging, factual questions
      - Include a mix of question types
      - Ensure correct answers are accurate
      - Provide plausible wrong answers
      - Add interesting explanations
      
      DIFFICULTY LEVELS:
      - easy: Basic facts, obvious answers
      - medium: Requires some sports knowledge
      - hard: Deep statistics and historical context
      
      Generate exactly the number of questions requested.
    
    schema:
      title: SportsQuiz
      type: object
      required: ["title", "description", "questions", "metadata"]
      properties:
        title:
          type: string
          description: "Engaging quiz title"
        description:
          type: string
          description: "Brief description of the quiz topic"
        questions:
          type: array
          minItems: 1
          items:
            type: object
            required: ["question", "options", "correct_answer", "explanation"]
            properties:
              question:
                type: string
                description: "The quiz question"
              question_type:
                type: string
                enum: ["multiple_choice", "true_false", "numeric"]
                description: "Type of question"
              options:
                type: array
                items:
                  type: string
                description: "Answer options (for multiple choice)"
              correct_answer:
                type: string
                description: "The correct answer"
              explanation:
                type: string
                description: "Explanation of the correct answer"
              difficulty:
                type: string
                enum: ["easy", "medium", "hard"]
              points:
                type: integer
                description: "Points awarded for correct answer"
        metadata:
          type: object
          properties:
            total_questions:
              type: integer
            total_points:
              type: integer
            estimated_time_minutes:
              type: integer
            tags:
              type: array
              items:
                type: string
```

## Quiz Types

### 1. Match-Based Quiz

```yaml
inputs:
  match_info: |
    {
      'home_team': 'Manchester United',
      'away_team': 'Liverpool',
      'date': '2025-01-15',
      'competition': 'Premier League'
    }

# Prompt instruction:
"Generate a quiz about the upcoming match between {home_team} and {away_team}.
Include questions about:
- Team history and head-to-head records
- Current form and standings
- Key players
- Recent performances"
```

### 2. Player Quiz

```yaml
inputs:
  player_info: |
    {
      'name': 'Lionel Messi',
      'team': 'Inter Miami',
      'position': 'Forward',
      'nationality': 'Argentina'
    }

# Focus areas:
- Career achievements
- Statistics and records
- Famous moments
- Personal background
```

### 3. Competition Quiz

```yaml
inputs:
  competition_info: |
    {
      'name': 'UEFA Champions League',
      'season': '2024-25',
      'stage': 'Round of 16'
    }

# Topics:
- Competition history
- Past winners
- Current standings
- Interesting facts
```

### 4. Topic-Based Quiz

```yaml
inputs:
  topic: "'Premier League history'"
  subtopics: "['legendary players', 'memorable matches', 'records']"
  era: "'1990s-2000s'"
```

## Dynamic Quiz Generation

Generate quizzes based on user preferences:

```yaml
workflow:
  name: "personalized-quiz"
  
  tasks:
    # Analyze user's favorite topics
    - type: prompt
      name: analyze-user-preferences
      connector:
        name: "machina-ai"
        command: "invoke_prompt"
        model: "gpt-4o-mini"
      inputs:
        user_history: "$.get('user_quiz_history')"
        favorite_teams: "$.get('favorite_teams')"
      outputs:
        quiz_topics: "$.get('recommended_topics')"
    
    # Generate personalized quiz
    - type: prompt
      name: generate-personalized-quiz
      connector:
        name: "machina-ai"
        command: "invoke_prompt"
        model: "gpt-4o"
      inputs:
        topics: "$.get('quiz_topics')"
        difficulty: "$.get('user_level', 'medium')"
      outputs:
        quiz: "$"
```

## Quiz Retrieval

Search for existing quizzes:

```yaml
tasks:
  # Search by topic
  - type: document
    name: search-quizzes
    config:
      action: search
      search-vector: true
      search-limit: 10
    connector:
      name: "machina-ai"
      command: "invoke_embedding"
      model: "text-embedding-3-small"
    inputs:
      name: "'content-quiz'"
      search-query: "'Premier League 2024 quiz'"
    filters:
      metadata.difficulty: "'medium'"
    outputs:
      available_quizzes: "$.get('documents', [])"
```

## Quiz Validation

Validate quiz quality before saving:

```yaml
tasks:
  # Generate quiz
  - type: prompt
    name: generate-quiz
    outputs:
      raw_quiz: "$"
  
  # Validate quiz structure
  - type: connector
    name: validate-quiz
    connector:
      name: "quiz-validator"
      command: "validate"
    inputs:
      quiz_data: "$.get('raw_quiz')"
    outputs:
      is_valid: "$.get('valid')"
      validation_errors: "$.get('errors', [])"
  
  # Save only if valid
  - type: document
    name: save-quiz
    condition: "$.get('is_valid') is True"
    config:
      action: save
    documents:
      content-quiz: "$.get('raw_quiz')"
```

## Multi-Language Quizzes

Generate quizzes in different languages:

```yaml
tasks:
  # Generate in English
  - type: prompt
    name: generate-quiz-en
    connector:
      name: "machina-ai"
      command: "invoke_prompt"
      model: "gpt-4o"
    inputs:
      language: "'English'"
      event_data: "$.get('event_data')"
    outputs:
      quiz_en: "$"
  
  # Translate to Portuguese
  - type: prompt
    name: translate-quiz-pt
    connector:
      name: "machina-ai"
      command: "invoke_prompt"
      model: "gpt-4o"
    inputs:
      quiz: "$.get('quiz_en')"
      target_language: "'Portuguese'"
    outputs:
      quiz_pt: "$"
```

## Quiz Analytics

Track quiz performance:

```yaml
documents:
  quiz-analytics: |
    {
      'quiz_id': $.get('quiz_id'),
      'total_attempts': 0,
      'average_score': 0,
      'completion_rate': 0,
      'question_stats': [
        {
          'question_id': 'q1',
          'correct_rate': 0,
          'average_time_seconds': 0
        }
      ]
    }

metadata:
  quiz_id: "$.get('quiz_id')"
  created_at: "datetime.now().isoformat()"
```

## Best Practices

1. **Fact-check answers**: Ensure accuracy of sports facts
2. **Balanced difficulty**: Mix easy and hard questions
3. **Clear questions**: Avoid ambiguous phrasing
4. **Plausible distractors**: Wrong answers should be believable
5. **Rich explanations**: Help users learn from mistakes
6. **Time limits**: Set appropriate time per question
7. **Progressive difficulty**: Start easy, get harder
8. **Regular updates**: Keep content fresh and current
9. **User feedback**: Collect and incorporate feedback
10. **Test quizzes**: Review generated content before publishing

