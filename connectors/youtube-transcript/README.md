# YouTube Transcript Connector

Extract transcripts from YouTube videos using yt-dlp for content analysis, RAG workflows, and AI processing.

## 📋 Overview

This connector enables extraction of transcripts from YouTube videos, supporting both auto-generated and manual subtitles in multiple languages. Perfect for:

- 📝 Content analysis with LLMs
- 🎯 RAG (Retrieval-Augmented Generation) workflows
- 📊 Automated summaries and insights extraction
- 🎙️ Podcast and live stream transcription
- 🔍 Multi-language content processing

## ⚙️ Features

- ✅ Extract clean transcripts (timestamps removed)
- ✅ Extract with timestamps (VTT format)
- ✅ Multi-language support (PT, EN, ES, etc.)
- ✅ Auto-generated and manual subtitles
- ✅ Video metadata extraction
- ✅ Duplicate line detection
- ✅ Word count and duration metrics
- ✅ Error handling for private/unavailable videos

## 🚀 Installation

```python
# Import connector via MCP
mcp__machina_client_dev__import_templates_from_git(
    repositories=[{
        "repo_url": "https://github.com/machina-sports/machina-templates",
        "template": "connectors/youtube-transcript",
        "repo_branch": "main"
    }]
)
```

## 📝 Commands

### 1. Extract Transcript

Extract clean transcript without timestamps.

**Input:**
```json
{
  "params": {
    "video_url": "https://www.youtube.com/watch?v=Q2k9dHN93kA",
    "language": "pt",
    "format": "text"
  }
}
```

**Output:**
```json
{
  "status": true,
  "data": {
    "transcript": "Full clean transcript text...",
    "video_id": "Q2k9dHN93kA",
    "language": "pt",
    "word_count": 13161,
    "duration_seconds": 7200,
    "title": "Video Title",
    "format": "text"
  },
  "message": "Transcript extracted successfully"
}
```

**Workflow Example:**
```yaml
- type: "connector"
  name: "extract-youtube-transcript"
  connector:
    name: "youtube-transcript"
    command: "extract_transcript"
  inputs:
    video_url: "https://www.youtube.com/watch?v=Q2k9dHN93kA"
    language: "pt"
  outputs:
    transcript: "$.get('data').get('transcript')"
    word_count: "$.get('data').get('word_count')"
```

### 2. Extract Transcript with Timestamps

Extract transcript in VTT format with timestamps preserved.

**Input:**
```json
{
  "params": {
    "video_url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "language": "en"
  }
}
```

**Output:**
```json
{
  "status": true,
  "data": {
    "vtt_content": "WEBVTT\\n\\n00:00:00.000 --> 00:00:03.000\\nTranscript text...",
    "transcript_clean": "Transcript text...",
    "video_id": "VIDEO_ID",
    "language": "en",
    "word_count": 5000
  },
  "message": "Transcript extracted successfully"
}
```

**Use Case: RAG with Timestamps**
```yaml
- type: "connector"
  name: "extract-with-timestamps"
  connector:
    name: "youtube-transcript"
    command: "extract_transcript_with_timestamps"
  inputs:
    video_url: "$.get('video_url')"
    language: "pt"
  outputs:
    vtt_content: "$.get('data').get('vtt_content')"
    
- type: "document"
  name: "save-to-vector-db"
  config:
    action: "save"
  document_name: "youtube:Transcript"
  content:
    video_id: "$.get('data').get('video_id')"
    transcript: "$.get('vtt_content')"
    language: "$.get('data').get('language')"
```

### 3. Get Available Languages

List all available subtitle languages for a video.

**Input:**
```json
{
  "params": {
    "video_url": "https://www.youtube.com/watch?v=VIDEO_ID"
  }
}
```

**Output:**
```json
{
  "status": true,
  "data": {
    "languages": ["pt", "en", "es"],
    "auto_generated": ["pt"],
    "manual": ["en", "es"],
    "video_id": "VIDEO_ID"
  },
  "message": "Languages retrieved successfully"
}
```

## 🎯 Use Cases

### 1. Sports Live Analysis

Extract and analyze 2-hour football live streams:

```yaml
workflow:
  name: "analyze-sports-live"
  tasks:
    - type: "connector"
      name: "extract-youtube-transcript"
      connector:
        name: "youtube-transcript"
        command: "extract_transcript"
      inputs:
        video_url: "https://www.youtube.com/watch?v=Q2k9dHN93kA"
        language: "pt"
      outputs:
        transcript: "$.get('data').get('transcript')"
        
    - type: "prompt"
      name: "summarize-live"
      connector:
        name: "openai"
        command: "invoke_prompt"
        model: "gpt-4o"
      inputs:
        messages: |
          [{
            "role": "user",
            "content": "Summarize this football live: " + $.get('transcript')
          }]
      outputs:
        summary: "$.get('choices')[0].get('message').get('content')"
```

**Tested with:**
- **Video**: 2h football live (Fominhas - Pré-Brasileirão 2025)
- **Output**: 13,161 words, 71KB clean text
- **Result**: ✅ Perfect LLM analysis

### 2. RAG with Video Content

Build searchable knowledge base from YouTube content:

```yaml
workflow:
  name: "youtube-rag-indexing"
  tasks:
    - type: "connector"
      name: "extract-transcript"
      connector:
        name: "youtube-transcript"
        command: "extract_transcript_with_timestamps"
      inputs:
        video_url: "$.get('video_url')"
        language: "pt"
      outputs:
        vtt_content: "$.get('data').get('vtt_content')"
        video_id: "$.get('data').get('video_id')"
        
    - type: "document"
      name: "save-to-db"
      config:
        action: "save"
        embed-vector: true
      document_name: "youtube:Content"
      content:
        video_id: "$.get('video_id')"
        transcript: "$.get('vtt_content')"
        source: "youtube"
```

### 3. Multi-Language Content Processing

Process videos in multiple languages:

```yaml
- type: "connector"
  name: "check-languages"
  connector:
    name: "youtube-transcript"
    command: "get_available_languages"
  inputs:
    video_url: "$.get('video_url')"
  outputs:
    available_langs: "$.get('data').get('languages')"

- type: "connector"
  name: "extract-pt"
  condition: "'pt' in $.get('available_langs')"
  connector:
    name: "youtube-transcript"
    command: "extract_transcript"
  inputs:
    video_url: "$.get('video_url')"
    language: "pt"
```

## 🧪 Parameters

### extract_transcript / extract_transcript_with_timestamps

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `video_url` | string | ✅ Yes | - | Full YouTube URL |
| `language` | string | ❌ No | `"en"` | Subtitle language (pt, en, es, etc.) |
| `format` | string | ❌ No | `"text"` | Output format: `text` or `vtt` |

### get_available_languages

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `video_url` | string | ✅ Yes | - | Full YouTube URL |

## 🔧 Technical Details

### Dependencies
- `yt-dlp>=2025.12.8` - YouTube download and subtitle extraction

### Supported Video Types
- ✅ Regular YouTube videos
- ✅ YouTube Shorts
- ✅ Live streams (finished)
- ✅ Premieres
- ❌ Private videos
- ❌ Deleted videos
- ❌ Videos without subtitles

### Supported Languages
Any language supported by YouTube auto-captions or manual subtitles:
- Portuguese (pt)
- English (en)
- Spanish (es)
- French (fr)
- German (de)
- And many more...

### Transcript Cleaning
The connector automatically:
- Removes VTT metadata (WEBVTT, Kind, Language)
- Strips timestamps (`00:00:00.000 --> 00:00:03.000`)
- Removes HTML tags (`<c>`, `</c>`)
- Eliminates duplicate consecutive lines
- Normalizes whitespace
- Joins lines into clean text

### Error Handling
- **Invalid URL**: Returns error with validation message
- **No subtitles**: Returns error indicating subtitles unavailable
- **Private video**: Returns error from yt-dlp
- **Timeout**: 60s timeout for downloads, 30s for metadata
- **Rate limiting**: Handled by yt-dlp automatically

## 📊 Performance

**Tested with 2h live stream:**
- Raw VTT: 658KB
- Clean text: 71KB
- Words: 13,161
- Processing time: ~10-15 seconds
- LLM-ready: ✅ Yes

## ⚠️ Limitations

1. **No real-time transcription**: Only works with finished videos
2. **Depends on YouTube subtitles**: Video must have auto-captions or manual subtitles
3. **Language accuracy**: Auto-generated captions may have errors
4. **Rate limiting**: YouTube may rate-limit excessive requests

## 🔗 Integration Examples

### With OpenAI GPT-4
```yaml
- type: "connector"
  connector:
    name: "youtube-transcript"
    command: "extract_transcript"
  inputs:
    video_url: "URL"
    
- type: "prompt"
  connector:
    name: "openai"
    model: "gpt-4o"
  inputs:
    messages: |
      [{"role": "user", "content": $.get('transcript')}]
```

### With Document Storage
```yaml
- type: "connector"
  connector:
    name: "youtube-transcript"
    command: "extract_transcript_with_timestamps"
    
- type: "document"
  config:
    action: "save"
  document_name: "youtube:Video"
  content:
    transcript: "$.get('vtt_content')"
    metadata: "$.get('data')"
```

## 📚 Related Connectors

- **temp-downloader**: Download files from web
- **google-speech-to-text**: Audio transcription
- **elevenlabs**: Text-to-speech generation

## 🤝 Support

For issues or questions:
1. Check YouTube video has subtitles available
2. Verify video URL format is correct
3. Ensure yt-dlp is installed (`pip install yt-dlp`)
4. Check connector logs for detailed error messages

## 📝 Version History

### v1.0.0 (2026-01-24)
- ✅ Initial release
- ✅ Three core commands
- ✅ Multi-language support
- ✅ VTT format support
- ✅ Timestamp cleaning
- ✅ Error handling
- ✅ Validation and testing

