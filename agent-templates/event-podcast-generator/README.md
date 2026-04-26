# Event Podcast Generator Agent Template

This agent template produces a 5-minute podcast episode for a given sports event ID.

## How it works

The agent takes a sports event ID as input and then performs the following steps:

1.  **Generate Script**: It uses a large language model to generate a 5-minute podcast script based on the provided event ID.
2.  **Synthesize Audio**: It uses a Text-to-Speech (TTS) service to convert the generated script into an audio file.
3.  **Upload Audio**: It uploads the synthesized audio file to a cloud storage provider.

The agent then returns the public URL of the uploaded audio file.

## Required Configuration

This agent requires the following project-level configurations:

*   **machina-ai**: API key for the Machina AI service, used for script generation.
*   **google-genai**: API key for Google's Generative AI service, used for audio synthesis.
*   **google-storage**: Credentials for Google Cloud Storage, used for uploading the podcast episode. The bucket name must be configured in the connector settings.

## Usage

To use this agent, simply provide a sports event ID as input. The agent will then generate the podcast and return the URL.
