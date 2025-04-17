import os

import tempfile

import uuid

import elevenlabs

from pathlib import Path


def get_text_to_speech(request_data):

    headers = request_data.get("headers", {})

    params = request_data.get("params", {})

    path_attr = request_data.get("path_attribute", {})

    api_key = headers.get("api_key") or params.get("api_key", "")

    if not api_key:
        return {"status": False, "message": "Missing ElevenLabs API key."}

    try:

        client = elevenlabs.client.ElevenLabs(api_key=api_key)

        text = path_attr.get("text")

        voice_id = path_attr.get("voice_id", "pNInz6obpgDQGcFmaJgB")

        model_id = path_attr.get("model_id", "eleven_turbo_v2")

        optimize_streaming_latency = path_attr.get("optimize_streaming_latency", "0")

        output_format = path_attr.get("output_format", "mp3_22050_32")

        if not text:
            return {"status": False, "message": "Missing text parameter."}

        temp_dir = tempfile.mkdtemp()

        save_file_path = str(Path(temp_dir) / f"{uuid.uuid4()}.mp3")

        response = client.text_to_speech.convert(
            voice_id=voice_id,
            optimize_streaming_latency=optimize_streaming_latency,
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

        with open(save_file_path, "wb") as f:
            for chunk in response:
                if chunk:
                    f.write(chunk)

        print(f"Audio saved to: {save_file_path}")

        return {
            "status": True,
            "data": {
                "file_path": save_file_path,
            },
            "message": "Text to speech converted and saved successfully.",
        }

    except Exception as e:
        print(f"Error getting text to speech: {e}")
        return {"status": False, "message": f"Error getting text to speech: {str(e)}"}
