from elevenlabs.client import ElevenLabs

client = ElevenLabs(
  api_key='YOUR_API_KEY',
)

def get_text_to_speech(request_data):
    try:
        text = request_data.get('text')
        voice_id = request_data.get('voice_id')
        model_id = request_data.get('model_id')
        response = client.text_to_speech.convert(
            text=text,
            voice_id=voice_id,
            model_id=model_id
        )
        return response
    except Exception as e:
        print(f"Error getting text to speech: {e}")
        return None
