# Voice TTS Studio

End-to-end agent template for cloning a voice with **Google Custom Voice**
(Cloud Text-to-Speech) and synthesizing new lines from text. Two cloning
tiers are supported out of the box:

- **Instant Custom Voice** — a 10-30 second consented sample produces a
  reusable `voice_clone_key` in seconds.
- **Professional Custom Voice** — a curated multi-utterance dataset in
  GCS kicks off a server-side training job that returns a long-running
  operation; the resulting model name is reusable forever.

The same `synthesize-with-custom-voice` workflow handles both modes —
just pass either `voice_clone_key` (instant) or `custom_voice_model`
(pro), or a `speaker_label` we previously persisted.

## What's in this template

| File | Purpose |
| --- | --- |
| `_install.yml` | Template manifest. |
| `prompts.yml` | Gemini prompt that drafts a consent + training script per language. |
| `generate-training-script.yml` | Calls the prompt and returns text the speaker can read. |
| `capture-voice-sample.yml` | Uploads a base64 / local / URL sample to GCS. |
| `clone-instant-voice.yml` | Calls `invoke_clone_instant_voice` and stores the resulting key as a project document. |
| `train-pro-custom-voice.yml` | Calls `invoke_train_pro_voice` and stores the operation name. |
| `synthesize-with-custom-voice.yml` | Resolves the right voice and synthesizes audio, then uploads to GCS. |
| `agent.yml` | Wraps all five workflows behind a single agent. |

## Required credentials

The workflows expect the following entries in the project vault (the
defaults match the standard Machina naming):

| Secret | Used by |
| --- | --- |
| `TEMP_CONTEXT_VARIABLE_VERTEX_AI_CREDENTIAL` | All Custom Voice calls (service account JSON). |
| `TEMP_CONTEXT_VARIABLE_VERTEX_AI_PROJECT_ID` | All Custom Voice calls. |
| `TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_API_KEY` | Sample + synthesized audio uploads. |
| `TEMP_CONTEXT_VARIABLE_GOOGLE_STORAGE_BUCKET_NAME` | Sample + synthesized audio uploads. |

The Vertex service account needs the `Cloud Text-to-Speech API` enabled
on the project plus the `roles/texttospeech.editor` role (or a custom
role that grants `texttospeech.customVoices.create` and
`texttospeech.voices.synthesize`).

## End-to-end flow

```
1. machina workflow run generate-training-script \
     speaker_description="warm female podcast host, en-US" \
     language_code="en-US"
   # → returns consent_script + training_script. Speaker reads them
   #   into a 24kHz mono WAV.

2. machina workflow run capture-voice-sample \
     speaker_label="anchor-en-female-01" \
     audio_path="/tmp/sample.wav"
   # → uploads to GCS, returns sample_url.

3. machina workflow run clone-instant-voice \
     speaker_label="anchor-en-female-01" \
     reference_audio_path="<sample_url from step 2>" \
     consent_script="<consent_script from step 1>" \
     language_code="en-US"
   # → creates voice_clone_key, persists it under speaker_label.

4. machina workflow run synthesize-with-custom-voice \
     speaker_label="anchor-en-female-01" \
     text="Welcome back to the show."
   # → resolves the saved key, synthesizes, returns audio_url.
```

For Professional voices, replace step 3 with `train-pro-custom-voice`
(supplying a `dataset_uri` and `consent_audio_uri` in `gs://`) and pass
the resulting `custom_voice_model` (e.g.
`projects/<id>/locations/global/customVoices/<voice_name>`) into step 4.

## Notes & limits

- **Consent is mandatory.** The Custom Voice API rejects clone requests
  whose `consent_script` does not match the spoken audio.
- **Sample format.** Instant cloning expects 10-30 seconds of clean,
  mono, 24kHz LINEAR16 audio. Convert noisy or stereo recordings before
  passing them in.
- **Pro training is asynchronous.** `train-pro-custom-voice` returns
  immediately with an `operation_name`. Poll the standard
  `customVoices.operations.get` endpoint (or rerun later) before using
  the model in synthesis.
- **Document store.** Instant clones live under the
  `voice-tts-studio-instant-voice` document collection; pro voices live
  under `voice-tts-studio-pro-voice`. Both are looked up by
  `speaker_label` / `voice_name`.
