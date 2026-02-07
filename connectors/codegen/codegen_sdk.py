"""
Codegen Connector - Python SDK Version

This is an alternative implementation using the Python SDK directly
instead of subprocess + CLI. This approach:
- Requires only Python package (no Node.js)
- Provides native async support
- Better error handling
- But requires changes to the executor to support async

Requirements:
- pip install claude-agent-sdk
- ANTHROPIC_API_KEY environment variable

Note: This version requires an async-capable executor.
The current Machina connector executor uses sync exec(),
so this is provided for future enhancement.
"""

import asyncio
import os
import json
from typing import Optional, Dict, Any, List

# SDK imports - requires: pip install claude-agent-sdk
try:
    from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


def _extract_params(request_data: Dict) -> Dict:
    """Extract parameters from various input formats."""
    params = request_data.get("params") or request_data.get("inputs") or {}
    headers = request_data.get("headers") or {}
    path_attr = request_data.get("path_attribute") or {}
    merged = {**headers, **path_attr, **params}
    return merged


def _get_api_key(params: Dict) -> Optional[str]:
    """Get Anthropic API key from params or environment."""
    return (
        params.get("api_key") or
        params.get("anthropic_api_key") or
        os.getenv("ANTHROPIC_API_KEY")
    )


def health_check(request_data: Dict) -> Dict[str, Any]:
    """Check if Claude Agent SDK is available and configured."""
    api_key = os.getenv("ANTHROPIC_API_KEY")

    return {
        "status": SDK_AVAILABLE,
        "data": {
            "sdk_available": SDK_AVAILABLE,
            "api_key_configured": bool(api_key),
            "api_key_preview": f"{api_key[:8]}..." if api_key else None
        },
        "message": "SDK available" if SDK_AVAILABLE else "SDK not installed. Run: pip install claude-agent-sdk"
    }


async def _execute_query_async(
    prompt: str,
    working_directory: Optional[str],
    allowed_tools: List[str],
    session_id: Optional[str] = None,
    max_turns: int = 10,
    api_key: Optional[str] = None
) -> Dict[str, Any]:
    """Execute a query using the Claude Agent SDK (async)."""
    if not SDK_AVAILABLE:
        return {
            "status": False,
            "error": {"code": 500, "message": "SDK not installed"}
        }

    # Set API key if provided
    if api_key:
        os.environ["ANTHROPIC_API_KEY"] = api_key

    messages = []
    result_text = ""
    result_session_id = session_id

    options = ClaudeAgentOptions(
        allowed_tools=allowed_tools,
        max_turns=max_turns,
        permission_mode="bypassPermissions"
    )

    if session_id:
        options.resume = session_id

    if working_directory:
        options.cwd = working_directory

    try:
        async for message in query(prompt=prompt, options=options):
            messages.append(message)

            # Extract session ID
            if hasattr(message, 'subtype') and message.subtype == 'init':
                result_session_id = getattr(message, 'session_id', None)

            # Extract result
            if hasattr(message, 'result'):
                result_text = message.result

        return {
            "status": True,
            "data": {
                "result": result_text,
                "session_id": result_session_id,
                "message_count": len(messages)
            },
            "messages": [str(m) for m in messages],
            "session_id": result_session_id
        }

    except Exception as e:
        return {
            "status": False,
            "data": {},
            "error": {"code": 500, "message": str(e)},
            "messages": [str(m) for m in messages]
        }


def execute_prompt(request_data: Dict) -> Dict[str, Any]:
    """
    Execute a coding prompt with Claude Agent SDK.

    This wraps the async SDK in a sync function for compatibility
    with the current Machina connector executor.
    """
    if not SDK_AVAILABLE:
        return {
            "status": False,
            "error": {"code": 500, "message": "SDK not installed. Run: pip install claude-agent-sdk"}
        }

    params = _extract_params(request_data)

    prompt = params.get("prompt")
    if not prompt:
        return {
            "status": False,
            "error": {"code": 400, "message": "prompt is required"}
        }

    api_key = _get_api_key(params)
    working_directory = params.get("working_directory")
    allowed_tools = params.get("allowed_tools", ["Read", "Glob", "Grep"])
    max_turns = params.get("max_turns", 10)

    # Run async function in sync context
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(
        _execute_query_async(
            prompt=prompt,
            working_directory=working_directory,
            allowed_tools=allowed_tools,
            api_key=api_key,
            max_turns=max_turns
        )
    )


def execute_with_session(request_data: Dict) -> Dict[str, Any]:
    """Execute a prompt and return session_id for multi-turn conversations."""
    result = execute_prompt(request_data)

    if result.get("status") and result.get("session_id"):
        result["data"]["session_id"] = result["session_id"]
        result["message"] = f"Session created: {result['session_id']}"

    return result


def resume_session(request_data: Dict) -> Dict[str, Any]:
    """Resume an existing session with a follow-up prompt."""
    if not SDK_AVAILABLE:
        return {
            "status": False,
            "error": {"code": 500, "message": "SDK not installed"}
        }

    params = _extract_params(request_data)

    session_id = params.get("session_id")
    if not session_id:
        return {
            "status": False,
            "error": {"code": 400, "message": "session_id is required"}
        }

    prompt = params.get("prompt")
    if not prompt:
        return {
            "status": False,
            "error": {"code": 400, "message": "prompt is required"}
        }

    api_key = _get_api_key(params)
    working_directory = params.get("working_directory")
    allowed_tools = params.get("allowed_tools", ["Read", "Glob", "Grep", "Edit", "Bash"])

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    result = loop.run_until_complete(
        _execute_query_async(
            prompt=prompt,
            working_directory=working_directory,
            allowed_tools=allowed_tools,
            session_id=session_id,
            api_key=api_key
        )
    )

    if result.get("status"):
        result["data"]["session_id"] = session_id

    return result


# Streaming version for Celery integration
async def execute_streaming_async(
    prompt: str,
    working_directory: Optional[str],
    allowed_tools: List[str],
    session_id: Optional[str] = None,
    publisher=None
) -> Dict[str, Any]:
    """
    Execute with real-time streaming via Redis publisher.

    This is designed to work with Machina's Celery streaming queue.
    The publisher should be a RedisStreamPublisher instance.
    """
    if not SDK_AVAILABLE:
        if publisher:
            publisher.publish("error", "SDK not installed")
        return {"status": False, "error": {"message": "SDK not installed"}}

    if publisher:
        publisher.publish("start", f"Executing: {prompt[:100]}...")

    messages = []
    result_text = ""
    result_session_id = session_id

    options = ClaudeAgentOptions(
        allowed_tools=allowed_tools,
        permission_mode="bypassPermissions"
    )

    if session_id:
        options.resume = session_id

    if working_directory:
        options.cwd = working_directory

    try:
        async for message in query(prompt=prompt, options=options):
            messages.append(message)

            # Publish each message type
            if hasattr(message, 'subtype') and message.subtype == 'init':
                result_session_id = getattr(message, 'session_id', None)
                if publisher:
                    publisher.publish("content", f"Session: {result_session_id}")

            elif hasattr(message, 'type'):
                msg_type = message.type

                if msg_type == "assistant":
                    # Extract text content
                    if hasattr(message, 'message'):
                        content = message.message.get('content', [])
                        for block in content:
                            if block.get('type') == 'text':
                                text = block.get('text', '')
                                result_text = text
                                if publisher:
                                    publisher.publish("content", text)
                            elif block.get('type') == 'tool_use':
                                tool_name = block.get('name', '')
                                if publisher:
                                    publisher.publish("tool_use", f"Using: {tool_name}")

                elif msg_type == "result":
                    result_text = getattr(message, 'result', '')

        if publisher:
            publisher.publish("done", "", {
                "session_id": result_session_id,
                "message_count": len(messages)
            })

        return {
            "status": True,
            "data": {
                "result": result_text,
                "session_id": result_session_id,
                "message_count": len(messages)
            },
            "messages": [str(m) for m in messages],
            "session_id": result_session_id
        }

    except Exception as e:
        if publisher:
            publisher.publish("error", str(e))
        return {
            "status": False,
            "error": {"code": 500, "message": str(e)},
            "messages": [str(m) for m in messages]
        }
