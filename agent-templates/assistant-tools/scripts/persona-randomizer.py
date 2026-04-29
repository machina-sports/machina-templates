import json
import random
import re

def create_persona_prompt(request_data):
    """
    Create a randomized persona prompt from character data.

    Args:
        request_data: Dictionary containing:
            - params: Dictionary with parameters
                - character_data: dict with character information
                - seed: optional int for deterministic output

    Returns:
        Dictionary with status and persona data
    """
    def _random_select_and_combine(arr, count_range):
        if not arr:
            return ""
        k = max(1, min(len(arr), random.randint(*count_range)))
        parts = random.sample(arr, k)
        return " ".join(parts).strip()

    def _random_select(arr, count_range):
        if not arr:
            return []
        k = max(1, min(len(arr), random.randint(*count_range)))
        return random.sample(arr, k)

    def _replace_user_placeholders(example):
        names = ["Alice", "Bruno", "Carla", "Diego", "Emilia", "Felipe", "Gi", "Hugo"]
        user_mapping = {}
        new_conv = []
        for message in example:
            user = message.get("user", "")
            for placeholder in re.findall(r"\{\{user\d+\}\}", user):
                if placeholder not in user_mapping:
                    user_mapping[placeholder] = random.choice(names)
                user = user.replace(placeholder, user_mapping[placeholder])
            content = message.get("content", {})
            new_conv.append({"user": user, "content": content})
        return new_conv

    def _minify_conversation(conv, max_chars=240):
        parts = [f"{m.get('user', '')}: {m.get('content', {}).get('text', '')}" for m in conv]
        s = " | ".join(p.strip() for p in parts if p.strip())
        return s[:max_chars]

    try:
        # Extract params from request_data
        params = request_data.get("params", {})
        character_data = params.get("character_data")
        seed = params.get("seed", None)

        if not character_data:
            return {
                "status": False,
                "error": "character_data not provided in params",
                "message": "Character data is required"
            }

        # Set seed if provided
        if seed is not None:
            random.seed(seed)

        # Use the character_data dict directly
        name = character_data.get("name", "TyltyHUB")
        bio = _random_select_and_combine(character_data.get("bio", []), (1, 3))
        lore = _random_select_and_combine(character_data.get("lore", []), (1, 2))

        style_all = _random_select((character_data.get("style", {}) or {}).get("all", []), (2, 3))
        style_chat = _random_select((character_data.get("style", {}) or {}).get("chat", []), (1, 2))

        # Optional: sample one message example, replace placeholders, and minify
        message_examples = character_data.get("messageExamples", [])
        message_example_str = ""
        if message_examples:
            conv = random.choice(message_examples)
            conv = _replace_user_placeholders(conv)
            message_example_str = _minify_conversation(conv, 220)

        adjectives = _random_select(character_data.get("adjectives", []), (1, 3))
        topics = _random_select(character_data.get("topics", []), (1, 3))

        # Keep persona_prompt short and focused on tone/style; facts come from insights
        persona_prompt = (
            f"PERSONA[{name}]: {bio} {lore} "
            f"Estilo: " + "; ".join(style_all + style_chat) + ". "
            + (f"Exemplo de fala: \"{message_example_str}\". " if message_example_str else "")
            + (f"Adjetivos: {', '.join(adjectives)}. " if adjectives else "")
            + (f"Tópicos: {', '.join(topics)}. " if topics else "")
        ).strip()

        return {
            "status": True,
            "data": {
                "persona_prompt": persona_prompt,
                "persona_meta": {
                    "name": name,
                    "bio": bio,
                    "lore": lore,
                    "style_all": style_all,
                    "style_chat": style_chat,
                    "adjectives": adjectives,
                    "topics": topics,
                    "message_example": message_example_str,
                }
            },
            "message": "Persona prompt generated successfully"
        }

    except Exception as e:
        return {
            "status": False,
            "error": str(e),
            "message": f"Error generating persona prompt: {str(e)}"
        }