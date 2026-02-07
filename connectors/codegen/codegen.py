"""
Codegen Connector - Claude Agent SDK Integration

This connector enables Machina workflows to interact with Claude Code for
autonomous coding tasks. It supports:
- Single-shot prompt execution
- Session management for multi-turn conversations
- Streaming response capture

Architecture:
- Uses subprocess to run `claude` CLI (Claude Code)
- Captures stdout for streaming responses
- Session IDs are managed via CLI's --resume flag

Requirements:
- Claude Code CLI installed (`npm install -g @anthropic-ai/claude-code`)
- ANTHROPIC_API_KEY environment variable set
- Working directory with codebase access

Usage in workflows:
  connector: codegen
  command: execute
  params:
    prompt: "Find and fix the bug in auth.py"
    working_directory: "/app/my-project"
    allowed_tools: ["Read", "Edit", "Bash"]
"""

import subprocess
import json
import os
import uuid
import threading
import queue
from typing import Optional, Dict, Any, List


def _extract_params(request_data: Dict) -> Dict:
    """Extract parameters from various input formats."""
    params = request_data.get("params") or request_data.get("inputs") or {}
    headers = request_data.get("headers") or {}
    path_attr = request_data.get("path_attribute") or {}

    # Merge all sources, preferring params > path_attr > headers
    merged = {**headers, **path_attr, **params}
    return merged


def _get_api_key(params: Dict) -> Optional[str]:
    """Get Anthropic API key from params or environment."""
    return (
        params.get("api_key") or
        params.get("anthropic_api_key") or
        os.getenv("ANTHROPIC_API_KEY")
    )


def _build_claude_command(
    prompt: str,
    working_directory: Optional[str] = None,
    allowed_tools: Optional[List[str]] = None,
    session_id: Optional[str] = None,
    max_turns: Optional[int] = None,
    output_format: str = "json"
) -> List[str]:
    """Build the claude CLI command with appropriate flags."""
    cmd = ["claude", "--print", "--output-format", output_format]

    # Add prompt
    cmd.extend(["--prompt", prompt])

    # Add session resume if provided
    if session_id:
        cmd.extend(["--resume", session_id])

    # Add allowed tools
    if allowed_tools:
        for tool in allowed_tools:
            cmd.extend(["--allowedTools", tool])

    # Add max turns limit
    if max_turns:
        cmd.extend(["--max-turns", str(max_turns)])

    return cmd


def _run_claude_subprocess(
    cmd: List[str],
    working_directory: Optional[str],
    api_key: Optional[str],
    timeout: int = 600
) -> Dict[str, Any]:
    """
    Execute claude CLI and capture output.

    Returns dict with:
    - status: bool
    - data: response data
    - messages: list of streamed messages
    - session_id: session ID for resumption
    """
    env = os.environ.copy()
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key

    cwd = working_directory or os.getcwd()

    messages = []
    session_id = None
    result_text = ""

    try:
        # Run with subprocess and capture output
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            text=True,
            bufsize=1  # Line buffered for streaming
        )

        # Capture stdout line by line
        stdout_lines = []
        for line in process.stdout:
            stdout_lines.append(line)
            # Try to parse as JSON for session info
            try:
                data = json.loads(line.strip())
                if isinstance(data, dict):
                    if data.get("type") == "system" and data.get("subtype") == "init":
                        session_id = data.get("session_id")
                    elif data.get("type") == "result":
                        result_text = data.get("result", "")
                    messages.append(data)
            except json.JSONDecodeError:
                # Plain text output
                messages.append({"type": "text", "content": line.strip()})

        # Wait for completion
        process.wait(timeout=timeout)

        stderr_output = process.stderr.read()

        if process.returncode != 0:
            return {
                "status": False,
                "data": {},
                "error": {
                    "code": process.returncode,
                    "message": stderr_output or "Claude CLI execution failed"
                },
                "messages": messages
            }

        # Extract final result from messages
        if not result_text:
            for msg in reversed(messages):
                if isinstance(msg, dict):
                    if msg.get("type") == "assistant" and msg.get("message"):
                        content = msg["message"].get("content", [])
                        for block in content:
                            if block.get("type") == "text":
                                result_text = block.get("text", "")
                                break
                    elif msg.get("type") == "text":
                        result_text = msg.get("content", "")
                if result_text:
                    break

        return {
            "status": True,
            "data": {
                "result": result_text,
                "session_id": session_id,
                "message_count": len(messages)
            },
            "messages": messages,
            "session_id": session_id
        }

    except subprocess.TimeoutExpired:
        process.kill()
        return {
            "status": False,
            "data": {},
            "error": {"code": 408, "message": f"Execution timed out after {timeout}s"},
            "messages": messages
        }
    except FileNotFoundError:
        return {
            "status": False,
            "data": {},
            "error": {
                "code": 404,
                "message": "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code"
            },
            "messages": []
        }
    except Exception as e:
        return {
            "status": False,
            "data": {},
            "error": {"code": 500, "message": str(e)},
            "messages": messages
        }


def health_check(request_data: Dict) -> Dict[str, Any]:
    """
    Check if Claude Code CLI is available and properly configured.

    Returns:
        status: True if CLI is available
        data: Version info and configuration status
    """
    try:
        # Check CLI exists
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )

        if result.returncode != 0:
            return {
                "status": False,
                "message": "Claude CLI found but returned error",
                "data": {"stderr": result.stderr}
            }

        version = result.stdout.strip()

        # Check API key
        api_key = os.getenv("ANTHROPIC_API_KEY")
        has_api_key = bool(api_key)

        return {
            "status": True,
            "data": {
                "version": version,
                "api_key_configured": has_api_key,
                "api_key_preview": f"{api_key[:8]}..." if api_key else None
            },
            "message": "Claude Code CLI is available and configured."
        }

    except FileNotFoundError:
        return {
            "status": False,
            "message": "Claude CLI not found. Install with: npm install -g @anthropic-ai/claude-code",
            "data": {}
        }
    except Exception as e:
        return {
            "status": False,
            "message": f"Health check failed: {str(e)}",
            "data": {}
        }


def execute_prompt(request_data: Dict) -> Dict[str, Any]:
    """
    Execute a single coding prompt with Claude Agent SDK.

    Parameters (via params):
        prompt: str - The coding task to execute
        working_directory: str - Directory with codebase (optional)
        allowed_tools: list - Tools to allow ["Read", "Edit", "Bash", etc.] (optional)
        max_turns: int - Maximum agent turns (optional, default: 10)
        timeout: int - Execution timeout in seconds (optional, default: 600)

    Returns:
        status: bool
        data:
            result: Final response text
            session_id: Session ID for resumption
            message_count: Number of messages exchanged
        messages: List of all streamed messages
    """
    params = _extract_params(request_data)

    prompt = params.get("prompt")
    if not prompt:
        return {
            "status": False,
            "data": {},
            "error": {"code": 400, "message": "prompt is required"}
        }

    api_key = _get_api_key(params)
    working_directory = params.get("working_directory")
    allowed_tools = params.get("allowed_tools", ["Read", "Glob", "Grep"])
    max_turns = params.get("max_turns", 10)
    timeout = params.get("timeout", 600)

    cmd = _build_claude_command(
        prompt=prompt,
        working_directory=working_directory,
        allowed_tools=allowed_tools,
        max_turns=max_turns
    )

    return _run_claude_subprocess(
        cmd=cmd,
        working_directory=working_directory,
        api_key=api_key,
        timeout=timeout
    )


def execute_with_session(request_data: Dict) -> Dict[str, Any]:
    """
    Execute a prompt and return session_id for multi-turn conversations.

    Same parameters as execute_prompt.

    The session_id in the response can be used with resume_session()
    to continue the conversation with full context.
    """
    result = execute_prompt(request_data)

    if result.get("status") and result.get("session_id"):
        result["data"]["session_id"] = result["session_id"]
        result["message"] = f"Session created: {result['session_id']}"

    return result


def resume_session(request_data: Dict) -> Dict[str, Any]:
    """
    Resume an existing session with a follow-up prompt.

    Parameters (via params):
        session_id: str - Session ID from previous execution (required)
        prompt: str - Follow-up prompt (required)
        working_directory: str - Directory with codebase (optional)
        allowed_tools: list - Tools to allow (optional)
        timeout: int - Execution timeout in seconds (optional)

    The resumed session maintains full context from previous turns.
    """
    params = _extract_params(request_data)

    session_id = params.get("session_id")
    if not session_id:
        return {
            "status": False,
            "data": {},
            "error": {"code": 400, "message": "session_id is required"}
        }

    prompt = params.get("prompt")
    if not prompt:
        return {
            "status": False,
            "data": {},
            "error": {"code": 400, "message": "prompt is required"}
        }

    api_key = _get_api_key(params)
    working_directory = params.get("working_directory")
    allowed_tools = params.get("allowed_tools", ["Read", "Glob", "Grep", "Edit", "Bash"])
    timeout = params.get("timeout", 600)

    cmd = _build_claude_command(
        prompt=prompt,
        working_directory=working_directory,
        allowed_tools=allowed_tools,
        session_id=session_id
    )

    result = _run_claude_subprocess(
        cmd=cmd,
        working_directory=working_directory,
        api_key=api_key,
        timeout=timeout
    )

    # Keep the original session_id for continued resumption
    if result.get("status"):
        result["data"]["session_id"] = session_id

    return result


# Streaming version for Celery integration (future enhancement)
def execute_streaming(request_data: Dict, publisher=None) -> Dict[str, Any]:
    """
    Execute prompt with real-time streaming via Redis publisher.

    This is designed to work with Machina's Celery streaming queue.
    The publisher parameter should be a RedisStreamPublisher instance.

    Parameters:
        request_data: Standard connector request data
        publisher: RedisStreamPublisher instance for streaming events

    Events published:
        - "start": Execution beginning
        - "content": Each message/chunk from Claude
        - "tool_use": Tool being used (Read, Edit, etc.)
        - "done": Execution complete with final result
        - "error": If execution fails
    """
    params = _extract_params(request_data)

    prompt = params.get("prompt")
    if not prompt:
        if publisher:
            publisher.publish("error", "prompt is required")
        return {
            "status": False,
            "data": {},
            "error": {"code": 400, "message": "prompt is required"}
        }

    api_key = _get_api_key(params)
    working_directory = params.get("working_directory")
    allowed_tools = params.get("allowed_tools", ["Read", "Glob", "Grep"])
    session_id = params.get("session_id")
    timeout = params.get("timeout", 600)

    cmd = _build_claude_command(
        prompt=prompt,
        working_directory=working_directory,
        allowed_tools=allowed_tools,
        session_id=session_id,
        output_format="stream-json"  # Use streaming JSON format
    )

    env = os.environ.copy()
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key

    cwd = working_directory or os.getcwd()

    if publisher:
        publisher.publish("start", f"Executing: {prompt[:100]}...")

    messages = []
    result_session_id = session_id
    result_text = ""

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env,
            text=True,
            bufsize=1
        )

        for line in process.stdout:
            line = line.strip()
            if not line:
                continue

            try:
                data = json.loads(line)
                messages.append(data)

                msg_type = data.get("type", "")

                if msg_type == "system" and data.get("subtype") == "init":
                    result_session_id = data.get("session_id")
                    if publisher:
                        publisher.publish("content", f"Session: {result_session_id}")

                elif msg_type == "assistant":
                    content = data.get("message", {}).get("content", [])
                    for block in content:
                        if block.get("type") == "text":
                            text = block.get("text", "")
                            result_text = text
                            if publisher:
                                publisher.publish("content", text)
                        elif block.get("type") == "tool_use":
                            tool_name = block.get("name", "")
                            if publisher:
                                publisher.publish("tool_use", f"Using tool: {tool_name}")

                elif msg_type == "result":
                    result_text = data.get("result", "")

            except json.JSONDecodeError:
                if publisher:
                    publisher.publish("content", line)
                messages.append({"type": "text", "content": line})

        process.wait(timeout=timeout)

        if process.returncode != 0:
            stderr = process.stderr.read()
            if publisher:
                publisher.publish("error", stderr or "Execution failed")
            return {
                "status": False,
                "data": {},
                "error": {"code": process.returncode, "message": stderr},
                "messages": messages
            }

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
            "messages": messages,
            "session_id": result_session_id
        }

    except subprocess.TimeoutExpired:
        process.kill()
        if publisher:
            publisher.publish("error", f"Timeout after {timeout}s")
        return {
            "status": False,
            "data": {},
            "error": {"code": 408, "message": f"Timeout after {timeout}s"},
            "messages": messages
        }
    except Exception as e:
        if publisher:
            publisher.publish("error", str(e))
        return {
            "status": False,
            "data": {},
            "error": {"code": 500, "message": str(e)},
            "messages": messages
        }
