# Creating Podcasts with Machina

## Overview

Machina supports podcast generation through text-to-speech integration and content generation workflows. You can create sports podcasts, news podcasts, and personalized audio content.

## Basic Podcast Workflow

A typical podcast generation workflow has these steps:
1. **Content Generation**: Use LLMs to create the podcast script
2. **Speech Synthesis**: Convert text to speech using TTS services
3. **Audio Assembly**: Combine segments and add effects

## Example: Bundesliga Podcast

Here's how to create a sports podcast:

### 1. Content Generation Workflow

```yaml
workflow:
  name: "podcast-content-generation"
  title: "Podcast Content Generation"
  description: "Generate podcast script from sports data"
  
  tasks:
    # Load event data
    - type: "document"
      name: "load-game-data"
      config:
        action: "search"
        search-vector: false
      inputs:
        name: "'sport:Event'"
        filters:
          event_code: "$.get('event_code')"
      outputs:
        game_data: "$.get('documents')[0]"
    
    # Generate podcast script
    - type: "prompt"
      name: "generate-podcast-script"
      connector:
        name: "machina-ai"
        command: "invoke_prompt"
        model: "gpt-4o"
      inputs:
        game_data: "$.get('game_data')"
        style: "'conversational and engaging'"
      outputs:
        podcast_script: "$.get('choices')[0].get('message').get('content')"
```

### 2. Speech Generation Workflow

```yaml
workflow:
  name: "podcast-speech-generation"
  title: "Podcast Speech Generation"
  description: "Convert script to speech"
  
  context-variables:
    openai:
      api_key: "$MACHINA_CONTEXT_VARIABLE_OPENAI_API_KEY"
  
  tasks:
    # Convert to speech
    - type: "connector"
      name: "generate-speech"
      connector:
        name: "openai"
        command: "text_to_speech"
      inputs:
        text: "$.get('podcast_script')"
        voice: "alloy"  # or "echo", "fable", "onyx", "nova", "shimmer"
        model: "tts-1-hd"
      outputs:
        audio_url: "$.get('audio_url')"
```

## Podcast Prompts

Create engaging podcast scripts with well-designed prompts:

```yaml
prompts:
  - type: prompt
    name: "podcast-script-generator"
    title: "Podcast Script Generator"
    instruction: |
      You are a sports podcast host creating an engaging episode.
      
      STYLE:
      - Conversational and enthusiastic
      - Use storytelling techniques
      - Include interesting facts and statistics
      - Add natural transitions between topics
      
      STRUCTURE:
      1. Hook: Start with an exciting moment or question
      2. Context: Provide background information
      3. Analysis: Deep dive into key points
      4. Conclusion: Summarize and tease next episode
      
      TONE: Professional yet friendly, passionate about sports
      
      Generate a podcast script based on the provided game data.
    schema:
      title: PodcastScript
      type: object
      required: ["introduction", "main_content", "conclusion"]
      properties:
        introduction:
          type: string
          description: "Opening hook and introduction (30-60 seconds)"
        main_content:
          type: array
          items:
            type: object
            properties:
              segment_title:
                type: string
              content:
                type: string
              duration_estimate:
                type: string
        conclusion:
          type: string
          description: "Wrap-up and call to action"
        total_duration_estimate:
          type: string
```

## Advanced: Multi-Voice Podcasts

Create podcasts with multiple speakers:

```yaml
tasks:
  # Generate dialogue script
  - type: "prompt"
    name: "generate-dialogue"
    connector:
      name: "machina-ai"
      command: "invoke_prompt"
      model: "gpt-4o"
    outputs:
      dialogue: "$.get('dialogue_segments')"
  
  # Generate speech for each speaker
  - type: "connector"
    name: "generate-host-audio"
    connector:
      name: "openai"
      command: "text_to_speech"
    inputs:
      text: "$.get('dialogue').get('host_lines')"
      voice: "alloy"
    outputs:
      host_audio: "$"
  
  - type: "connector"
    name: "generate-guest-audio"
    connector:
      name: "openai"
      command: "text_to_speech"
    inputs:
      text: "$.get('dialogue').get('guest_lines')"
      voice: "echo"
    outputs:
      guest_audio: "$"
```

## Personalized Podcasts

Create user-specific podcast content:

```yaml
workflow:
  name: "personalized-podcast"
  inputs:
    user_preferences: "$.get('user_preferences')"
    favorite_teams: "$.get('favorite_teams')"
  
  tasks:
    # Analyze user preferences
    - type: "prompt"
      name: "analyze-preferences"
      connector:
        name: "machina-ai"
        command: "invoke_prompt"
        model: "gpt-4o-mini"
      inputs:
        preferences: "$.get('user_preferences')"
        teams: "$.get('favorite_teams')"
      outputs:
        content_focus: "$.get('content_recommendations')"
    
    # Generate personalized content
    - type: "prompt"
      name: "generate-personalized-script"
      connector:
        name: "machina-ai"
        command: "invoke_prompt"
        model: "gpt-4o"
      inputs:
        focus_areas: "$.get('content_focus')"
        recent_games: "$.get('recent_games')"
      outputs:
        personalized_script: "$.get('choices')[0].get('message').get('content')"
```

## TTS Options

### OpenAI TTS
- **Models**: `tts-1` (standard), `tts-1-hd` (high quality)
- **Voices**: alloy, echo, fable, onyx, nova, shimmer
- **Formats**: mp3, opus, aac, flac

### Google Cloud TTS
- Wide variety of voices and languages
- Neural2 voices for more natural speech
- WaveNet voices for highest quality

## Storage and Distribution

Store generated podcasts:

```yaml
tasks:
  # Save to storage
  - type: "connector"
    name: "save-podcast"
    connector:
      name: "storage"
      command: "upload_file"
    inputs:
      file_data: "$.get('audio_data')"
      file_name: "f\"podcast-{$.get('episode_id')}.mp3\""
      bucket: "'machina-podcasts'"
    outputs:
      public_url: "$.get('url')"
```

## Best Practices

1. **Script Quality**: Invest time in prompt engineering for engaging scripts
2. **Voice Selection**: Choose voices that match your content style
3. **Audio Length**: Aim for 5-15 minutes for social media, 20-45 for full episodes
4. **Background Music**: Consider adding intro/outro music
5. **Consistency**: Maintain consistent style and structure across episodes
6. **Testing**: Always review generated content before publishing

