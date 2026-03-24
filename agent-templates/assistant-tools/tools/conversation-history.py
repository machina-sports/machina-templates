"""
Conversation History Tool
Builds a compact conversation history from thread messages for the response LLM.
Extracts last Q&A pairs so the response can maintain conversational continuity.
"""


def build_conversation_history(request_data):
    """
    Build conversation history string from thread messages.

    Args:
        request_data: Dictionary containing:
            - params: Dictionary with parameters
                - messages: Full message array from thread document
                - max_pairs: Max number of Q&A pairs to include (default 3)

    Returns:
        Dictionary with conversation_history string
    """
    try:
        params = request_data.get("params", {})
        messages = params.get("messages", [])
        max_pairs = int(params.get("max_pairs", 3))

        if not messages or len(messages) < 2:
            return {
                "status": True,
                "message": "Not enough messages for history",
                "data": {
                    "conversation_history": ""
                }
            }

        # Exclude the last user message (that's the current question)
        history_messages = messages[:-1] if messages[-1].get("role") == "user" else messages

        # Collect Q&A pairs (user + assistant)
        pairs = []
        i = 0
        while i < len(history_messages):
            msg = history_messages[i]
            if msg.get("role") == "user":
                user_content = msg.get("content", "").strip()
                # Look for the next assistant message
                assistant_content = ""
                if i + 1 < len(history_messages) and history_messages[i + 1].get("role") == "assistant":
                    assistant_content = history_messages[i + 1].get("content", "").strip()
                    i += 2
                else:
                    i += 1

                if user_content:
                    # Truncate long responses to keep tokens reasonable
                    if len(assistant_content) > 400:
                        assistant_content = assistant_content[:400] + "..."
                    pairs.append({
                        "user": user_content,
                        "assistant": assistant_content
                    })
            else:
                i += 1

        # Take only the last N pairs
        recent_pairs = pairs[-max_pairs:] if len(pairs) > max_pairs else pairs

        if not recent_pairs:
            return {
                "status": True,
                "message": "No Q&A pairs found",
                "data": {
                    "conversation_history": ""
                }
            }

        # Build compact history string
        history_lines = []
        for pair in recent_pairs:
            history_lines.append(f"Usuario: {pair['user']}")
            if pair["assistant"]:
                history_lines.append(f"BotAndWin: {pair['assistant']}")

        conversation_history = "\n".join(history_lines)

        return {
            "status": True,
            "message": f"Built history with {len(recent_pairs)} Q&A pairs",
            "data": {
                "conversation_history": conversation_history
            }
        }

    except Exception as e:
        return {
            "status": False,
            "error": str(e),
            "message": f"Error building conversation history: {str(e)}",
            "data": {
                "conversation_history": ""
            }
        }
