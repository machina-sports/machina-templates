def format_chat_slack_messages(request_data):
    """
    Format chat conversation data into structured Slack messages for BotAndWin
    
    Takes document_content (messages array) and extracts:
    - Main message with user info and first message
    - Last user message
    - Chat reasoning summary from last user message
    - Chat response with suggested questions
    """
    params = request_data.get("params", {})
    
    document_content = params.get("document_content", [])
    username = params.get("username", "Anónimo")
    userid = params.get("userid", None)
    
    if not document_content or len(document_content) == 0:
        return {
            "status": False,
            "message": "No document content provided",
            "data": {}
        }
    
    # Extract first and last user messages
    user_messages = [msg for msg in document_content if msg.get("role") == "user"]
    first_user_message = user_messages[0] if user_messages else None
    last_user_message = user_messages[-1] if user_messages else None
    
    # Format main message (sucinta, sem labels, só valores e emoji)
    main_message_parts = []
    
    if username and username != "Anónimo":
        main_message_parts.append(username)
    
    if userid:
        main_message_parts.append(userid)
    
    if first_user_message:
        first_message_content = first_user_message.get("content", "").strip()
        if first_message_content:
            # Truncate if too long (max 80 chars)
            if len(first_message_content) > 80:
                first_message_content = first_message_content[:77] + "..."
            main_message_parts.append(first_message_content)
    
    # Join with spaces, add emoji at the beginning
    if main_message_parts:
        main_message = "💬 " + " ".join(main_message_parts)
    else:
        main_message = "💬 Nueva Conversación BotAndWin"
    
    # Extract last assistant message (response)
    assistant_messages = [msg for msg in document_content if msg.get("role") == "assistant"]
    last_assistant_message = assistant_messages[-1] if assistant_messages else None
    
    # Format user message
    user_message_text = ""
    if last_user_message:
        user_content = last_user_message.get("content", "")
        user_message_text = f"💬 *Mensaje del Usuario*\n\n{user_content}"
    
    # Format reasoning summary
    reasoning_summary_text = ""
    if last_user_message and last_user_message.get("reasoning"):
        reasoning = last_user_message.get("reasoning", {})
        
        # Extract key reasoning fields for summary
        analysis_mode = reasoning.get("analysis_mode", "")
        team_names = reasoning.get("team_names", [])
        market_types = reasoning.get("market_types", [])
        search_query = reasoning.get("search_query", "")
        short_message = reasoning.get("short_message", "")
        
        reasoning_parts = []
        
        if short_message:
            reasoning_parts.append(f"*Resumen:* {short_message}")
        
        if analysis_mode:
            reasoning_parts.append(f"*Modo de análisis:* {analysis_mode}")
        
        if team_names:
            teams_str = ", ".join(team_names)
            reasoning_parts.append(f"*Equipos mencionados:* {teams_str}")
        
        if market_types:
            markets_str = ", ".join(market_types)
            reasoning_parts.append(f"*Tipos de mercado:* {markets_str}")
        
        if search_query:
            reasoning_parts.append(f"*Consulta:* {search_query}")
        
        if reasoning_parts:
            reasoning_summary_text = f"🧠 *Chat Reasoning*\n\n" + "\n".join(reasoning_parts)
        else:
            reasoning_summary_text = f"🧠 *Chat Reasoning*\n\n*Estado:* Procesado"
    
    # Format assistant response
    response_text = ""
    if last_assistant_message:
        response_content = last_assistant_message.get("content", "")
        suggestions = last_assistant_message.get("suggestions", [])
        
        response_parts = [f"🤖 *Chat Response*\n\n{response_content}"]
        
        if suggestions:
            suggestions_text = "\n".join([f"• {sug}" for sug in suggestions])
            response_parts.append(f"\n*Preguntas sugeridas:*\n{suggestions_text}")
        
        response_text = "\n".join(response_parts)
    
    return {
        "status": True,
        "message": "Formatted Slack messages successfully",
        "data": {
            "main_message": main_message,
            "user_message": user_message_text,
            "reasoning_summary": reasoning_summary_text,
            "response_message": response_text
        }
    }

