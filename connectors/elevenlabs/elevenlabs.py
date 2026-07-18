"""ElevenLabs connector with sanitized errors and sandboxed outputs."""

import os
import uuid
from pathlib import Path

import elevenlabs


def _sources(request_data):
    request_data = request_data or {}
    return (
        request_data.get("headers") or {},
        request_data.get("params") or {},
        request_data.get("path_attribute") or {},
    )


def get_text_to_speech(request_data):
    headers, params, path_attr = _sources(request_data)
    api_key = headers.get("api_key") or params.get("api_key")
    if not api_key:
        return {"status": False, "data": None, "message": "Missing ElevenLabs API key."}
    text = path_attr.get("text") or params.get("text")
    if not text:
        return {"status": False, "data": None, "message": "Missing text parameter."}

    try:
        client = elevenlabs.client.ElevenLabs(api_key=api_key)
        voice_id = path_attr.get("voice_id") or params.get("voice_id") or "pNInz6obpgDQGcFmaJgB"
        model_id = path_attr.get("model_id") or params.get("model_id") or "eleven_flash_v2_5"
        output_format = path_attr.get("output_format") or params.get("output_format") or "mp3_22050_32"
        root = Path(os.getenv("MACHINA_WORK_DIR", os.getcwd())).expanduser().resolve()
        output_dir = root / "audio"
        output_dir.mkdir(parents=True, exist_ok=True)
        output = (output_dir / f"elevenlabs-{uuid.uuid4().hex}.mp3").resolve()
        response = client.text_to_speech.convert(
            voice_id=voice_id,
            optimize_streaming_latency=path_attr.get("optimize_streaming_latency", "0"),
            output_format=output_format,
            text=text,
            model_id=model_id,
            voice_settings=elevenlabs.VoiceSettings(
                stability=0.0,
                similarity_boost=1.0,
                style=0.0,
                use_speaker_boost=True,
            ),
        )
        with output.open("wb") as stream:
            for chunk in response:
                if chunk:
                    stream.write(chunk)
        return {
            "status": True,
            "data": {"file_path": str(output.relative_to(root)), "file_name": output.name},
            "message": "Text to speech converted and saved successfully.",
        }
    except Exception:
        return {"status": False, "data": None, "message": "The ElevenLabs provider could not synthesize speech."}


def get_voices(request_data):
    headers, params, _ = _sources(request_data)
    api_key = headers.get("api_key") or params.get("api_key")
    if not api_key:
        return {"status": False, "data": None, "message": "Missing ElevenLabs API key."}
    try:
        client = elevenlabs.client.ElevenLabs(api_key=api_key)
        response = client.voices.get_all()
        voices = [
            {"voice_id": voice.voice_id, "name": voice.name, "category": voice.category}
            for voice in response.voices[:10]
        ]
        return {
            "status": True,
            "data": {"voices": voices, "total_count": len(response.voices)},
            "message": "Voices retrieved successfully.",
        }
    except Exception:
        return {"status": False, "data": None, "message": "The ElevenLabs provider could not list voices."}
