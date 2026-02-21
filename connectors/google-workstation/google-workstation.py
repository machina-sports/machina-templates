from google.cloud import workstations_v1
from google.oauth2 import service_account

import json
import requests
import time


def _get_client(request_data):
    """
    Shared auth logic: parse credential, create WorkstationsClient.

    Expects request_data keys:
    - credential: Service account JSON (str or dict)

    Returns (client, error_dict). On success error_dict is None.
    """
    credential = request_data.get("credential")

    if not credential:
        return None, {"status": False, "message": "credential is required (service account JSON)."}

    if isinstance(credential, str):
        try:
            credential = json.loads(credential)
        except json.JSONDecodeError:
            return None, {"status": False, "message": "credential must be valid JSON."}

    try:
        creds = service_account.Credentials.from_service_account_info(credential)
        client = workstations_v1.WorkstationsClient(credentials=creds)
        return client, None
    except Exception as e:
        return None, {"status": False, "message": f"Failed to create client: {e}"}


def _build_parent(request_data, level="cluster"):
    """
    Build GCW resource parent string.

    Levels:
    - "location":  projects/{project_id}/locations/{location}
    - "cluster":   .../workstationClusters/{cluster}
    - "config":    .../workstationConfigs/{config}
    - "workstation": .../workstations/{workstation}
    """
    project_id = request_data.get("project_id")
    location = request_data.get("location", "us-central1")

    if not project_id:
        return None, {"status": False, "message": "project_id is required."}

    parent = f"projects/{project_id}/locations/{location}"

    if level == "location":
        return parent, None

    cluster = request_data.get("cluster")
    if not cluster:
        return None, {"status": False, "message": "cluster is required."}
    parent = f"{parent}/workstationClusters/{cluster}"

    if level == "cluster":
        return parent, None

    config = request_data.get("config")
    if not config:
        return None, {"status": False, "message": "config is required."}
    parent = f"{parent}/workstationConfigs/{config}"

    if level == "config":
        return parent, None

    workstation = request_data.get("workstation")
    if not workstation:
        return None, {"status": False, "message": "workstation is required."}
    parent = f"{parent}/workstations/{workstation}"

    return parent, None


def _serialize_cluster(cluster):
    """Serialize a WorkstationCluster to a dict."""
    return {
        "name": cluster.name,
        "display_name": cluster.display_name,
        "uid": cluster.uid,
        "reconciling": cluster.reconciling,
        "network": cluster.network,
        "subnetwork": cluster.subnetwork,
        "control_plane_ip": cluster.control_plane_ip,
        "degraded": cluster.degraded,
    }


def _serialize_config(config):
    """Serialize a WorkstationConfig to a dict."""
    result = {
        "name": config.name,
        "display_name": config.display_name,
        "uid": config.uid,
        "reconciling": config.reconciling,
        "idle_timeout": str(config.idle_timeout) if config.idle_timeout else None,
        "running_timeout": str(config.running_timeout) if config.running_timeout else None,
        "replica_zones": list(config.replica_zones) if config.replica_zones else [],
    }
    if config.host:
        result["host"] = {
            "gce_instance": {
                "machine_type": config.host.gce_instance.machine_type if config.host.gce_instance else None,
                "pool_size": config.host.gce_instance.pool_size if config.host.gce_instance else None,
                "disable_public_ip_addresses": config.host.gce_instance.disable_public_ip_addresses if config.host.gce_instance else None,
            } if config.host.gce_instance else None,
        }
    if config.container:
        result["container"] = {
            "image": config.container.image,
            "command": list(config.container.command) if config.container.command else [],
            "args": list(config.container.args) if config.container.args else [],
            "run_as_user": config.container.run_as_user,
        }
    return result


def _serialize_workstation(ws):
    """Serialize a Workstation to a dict."""
    return {
        "name": ws.name,
        "display_name": ws.display_name,
        "uid": ws.uid,
        "state": ws.state.name if ws.state else None,
        "host": ws.host,
        "reconciling": ws.reconciling,
    }


# ---------------------------------------------------------------------------
# 1. List Clusters
# ---------------------------------------------------------------------------

def invoke_list_clusters(request_data):
    """
    List workstation clusters in a project/location.

    Required: credential, project_id
    Optional: location (default: us-central1)
    """
    client, err = _get_client(request_data)
    if err:
        return err

    parent, err = _build_parent(request_data, level="location")
    if err:
        return err

    try:
        clusters = list(client.list_workstation_clusters(
            request=workstations_v1.ListWorkstationClustersRequest(parent=parent)
        ))
        return {
            "status": True,
            "data": [_serialize_cluster(c) for c in clusters],
            "message": f"Found {len(clusters)} cluster(s).",
        }
    except Exception as e:
        return {"status": False, "message": f"Error listing clusters: {e}"}


# ---------------------------------------------------------------------------
# 2. List Configs
# ---------------------------------------------------------------------------

def invoke_list_configs(request_data):
    """
    List workstation configs in a cluster.

    Required: credential, project_id, cluster
    Optional: location (default: us-central1)
    """
    client, err = _get_client(request_data)
    if err:
        return err

    parent, err = _build_parent(request_data, level="cluster")
    if err:
        return err

    try:
        configs = list(client.list_workstation_configs(
            request=workstations_v1.ListWorkstationConfigsRequest(parent=parent)
        ))
        return {
            "status": True,
            "data": [_serialize_config(c) for c in configs],
            "message": f"Found {len(configs)} config(s).",
        }
    except Exception as e:
        return {"status": False, "message": f"Error listing configs: {e}"}


# ---------------------------------------------------------------------------
# 3. List Workstations
# ---------------------------------------------------------------------------

def invoke_list_workstations(request_data):
    """
    List workstations in a config.

    Required: credential, project_id, cluster, config
    Optional: location (default: us-central1)
    """
    client, err = _get_client(request_data)
    if err:
        return err

    parent, err = _build_parent(request_data, level="config")
    if err:
        return err

    try:
        workstations = list(client.list_workstations(
            request=workstations_v1.ListWorkstationsRequest(parent=parent)
        ))
        return {
            "status": True,
            "data": [_serialize_workstation(ws) for ws in workstations],
            "message": f"Found {len(workstations)} workstation(s).",
        }
    except Exception as e:
        return {"status": False, "message": f"Error listing workstations: {e}"}


# ---------------------------------------------------------------------------
# 4. Get Workstation
# ---------------------------------------------------------------------------

def invoke_get_workstation(request_data):
    """
    Get details of a specific workstation.

    Required: credential, project_id, cluster, config, workstation
    Optional: location (default: us-central1)
    """
    client, err = _get_client(request_data)
    if err:
        return err

    name, err = _build_parent(request_data, level="workstation")
    if err:
        return err

    try:
        ws = client.get_workstation(
            request=workstations_v1.GetWorkstationRequest(name=name)
        )
        return {
            "status": True,
            "data": _serialize_workstation(ws),
            "message": f"Workstation state: {ws.state.name if ws.state else 'UNKNOWN'}",
        }
    except Exception as e:
        return {"status": False, "message": f"Error getting workstation: {e}"}


# ---------------------------------------------------------------------------
# 5. Create Workstation
# ---------------------------------------------------------------------------

def invoke_create_workstation(request_data):
    """
    Create a new workstation.

    Required: credential, project_id, cluster, config, workstation_id
    Optional: location, display_name, labels, wait (default: True)
    """
    client, err = _get_client(request_data)
    if err:
        return err

    parent, err = _build_parent(request_data, level="config")
    if err:
        return err

    workstation_id = request_data.get("workstation_id")
    if not workstation_id:
        return {"status": False, "message": "workstation_id is required."}

    display_name = request_data.get("display_name", workstation_id)
    labels = request_data.get("labels") or {}
    wait = request_data.get("wait", True)

    try:
        ws = workstations_v1.Workstation(
            display_name=display_name,
            labels=labels,
        )

        operation = client.create_workstation(
            request=workstations_v1.CreateWorkstationRequest(
                parent=parent,
                workstation_id=workstation_id,
                workstation=ws,
            )
        )

        if wait:
            result = operation.result()
            return {
                "status": True,
                "data": _serialize_workstation(result),
                "message": f"Workstation '{workstation_id}' created successfully.",
            }
        else:
            return {
                "status": True,
                "data": {"operation_name": operation.operation.name},
                "message": f"Workstation '{workstation_id}' creation started.",
            }
    except Exception as e:
        return {"status": False, "message": f"Error creating workstation: {e}"}


# ---------------------------------------------------------------------------
# 6. Start Workstation
# ---------------------------------------------------------------------------

def invoke_start_workstation(request_data):
    """
    Start a workstation.

    Required: credential, project_id, cluster, config, workstation
    Optional: location, wait (default: True)
    """
    client, err = _get_client(request_data)
    if err:
        return err

    name, err = _build_parent(request_data, level="workstation")
    if err:
        return err

    wait = request_data.get("wait", True)

    try:
        operation = client.start_workstation(
            request=workstations_v1.StartWorkstationRequest(name=name)
        )

        if wait:
            result = operation.result()
            return {
                "status": True,
                "data": _serialize_workstation(result),
                "message": "Workstation started successfully.",
            }
        else:
            return {
                "status": True,
                "data": {"operation_name": operation.operation.name},
                "message": "Workstation start initiated.",
            }
    except Exception as e:
        return {"status": False, "message": f"Error starting workstation: {e}"}


# ---------------------------------------------------------------------------
# 7. Stop Workstation
# ---------------------------------------------------------------------------

def invoke_stop_workstation(request_data):
    """
    Stop a workstation.

    Required: credential, project_id, cluster, config, workstation
    Optional: location, wait (default: True)
    """
    client, err = _get_client(request_data)
    if err:
        return err

    name, err = _build_parent(request_data, level="workstation")
    if err:
        return err

    wait = request_data.get("wait", True)

    try:
        operation = client.stop_workstation(
            request=workstations_v1.StopWorkstationRequest(name=name)
        )

        if wait:
            result = operation.result()
            return {
                "status": True,
                "data": _serialize_workstation(result),
                "message": "Workstation stopped successfully.",
            }
        else:
            return {
                "status": True,
                "data": {"operation_name": operation.operation.name},
                "message": "Workstation stop initiated.",
            }
    except Exception as e:
        return {"status": False, "message": f"Error stopping workstation: {e}"}


# ---------------------------------------------------------------------------
# 8. Delete Workstation
# ---------------------------------------------------------------------------

def invoke_delete_workstation(request_data):
    """
    Delete a workstation.

    Required: credential, project_id, cluster, config, workstation
    Optional: location, wait (default: True)
    """
    client, err = _get_client(request_data)
    if err:
        return err

    name, err = _build_parent(request_data, level="workstation")
    if err:
        return err

    wait = request_data.get("wait", True)

    try:
        operation = client.delete_workstation(
            request=workstations_v1.DeleteWorkstationRequest(name=name)
        )

        if wait:
            operation.result()
            return {
                "status": True,
                "data": {"deleted": name},
                "message": "Workstation deleted successfully.",
            }
        else:
            return {
                "status": True,
                "data": {"operation_name": operation.operation.name},
                "message": "Workstation deletion initiated.",
            }
    except Exception as e:
        return {"status": False, "message": f"Error deleting workstation: {e}"}


# ---------------------------------------------------------------------------
# 9. Generate Access Token
# ---------------------------------------------------------------------------

def invoke_generate_access_token(request_data):
    """
    Generate a short-lived access token for a workstation.

    Required: credential, project_id, cluster, config, workstation
    Optional: location
    """
    client, err = _get_client(request_data)
    if err:
        return err

    name, err = _build_parent(request_data, level="workstation")
    if err:
        return err

    try:
        response = client.generate_access_token(
            request=workstations_v1.GenerateAccessTokenRequest(workstation=name)
        )
        return {
            "status": True,
            "data": {
                "access_token": response.access_token,
                "expire_time": response.expire_time.isoformat() if response.expire_time else None,
            },
            "message": "Access token generated.",
        }
    except Exception as e:
        return {"status": False, "message": f"Error generating access token: {e}"}


# ---------------------------------------------------------------------------
# 10. Execute Claude (composite)
# ---------------------------------------------------------------------------

def invoke_execute_claude(request_data):
    """
    Execute Claude Code headless inside a workstation.

    Composite operation:
    1. Check workstation state
    2. Start if stopped (waits for RUNNING)
    3. Generate access token
    4. HTTP POST to workstation exec endpoint
    5. Run `claude -p "{prompt}" --output-format {output_format}`
    6. Return Claude output

    Required: credential, project_id, cluster, config, workstation, prompt
    Optional: location, output_format (default: json), timeout (default: 300)
    """
    client, err = _get_client(request_data)
    if err:
        return err

    name, err = _build_parent(request_data, level="workstation")
    if err:
        return err

    prompt = request_data.get("prompt")
    if not prompt:
        return {"status": False, "message": "prompt is required."}

    output_format = request_data.get("output_format", "json")
    timeout = int(request_data.get("timeout", 300))

    cluster = request_data.get("cluster")
    workstation = request_data.get("workstation")
    location = request_data.get("location", "us-central1")

    try:
        # Step 1: Check workstation state
        print(f"Checking workstation state...")
        ws = client.get_workstation(
            request=workstations_v1.GetWorkstationRequest(name=name)
        )
        state = ws.state.name if ws.state else "UNKNOWN"
        print(f"Workstation state: {state}")

        # Step 2: Start if not running
        if state != "STATE_RUNNING":
            print(f"Starting workstation (current state: {state})...")
            operation = client.start_workstation(
                request=workstations_v1.StartWorkstationRequest(name=name)
            )
            ws = operation.result()
            print("Workstation is now RUNNING.")

        # Step 3: Generate access token
        print("Generating access token...")
        token_response = client.generate_access_token(
            request=workstations_v1.GenerateAccessTokenRequest(workstation=name)
        )
        access_token = token_response.access_token

        # Step 4: Build workstation URL and execute command
        # Workstation URL format: https://{port}-{workstation}.{cluster}.{location}.cloudworkstations.dev
        workstation_host = f"{workstation}.{cluster}.{location}.cloudworkstations.dev"
        # Port 80 is the default web interface
        exec_url = f"https://80-{workstation_host}"

        # Step 5: Execute Claude via the workstation
        # Use the workstation's exec/terminal endpoint
        claude_cmd = f'claude -p "{prompt}" --output-format {output_format}'

        print(f"Executing Claude on workstation: {exec_url}")
        print(f"Command: {claude_cmd}")

        response = requests.post(
            f"{exec_url}/api/exec",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={"command": claude_cmd},
            timeout=timeout,
        )

        if response.status_code != 200:
            return {
                "status": False,
                "message": f"Exec failed (HTTP {response.status_code}): {response.text}",
                "data": {
                    "workstation_url": exec_url,
                    "workstation_state": "STATE_RUNNING",
                },
            }

        # Step 6: Return output
        result = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"output": response.text}

        return {
            "status": True,
            "data": {
                "result": result,
                "workstation_url": exec_url,
                "workstation_state": "STATE_RUNNING",
                "output_format": output_format,
            },
            "message": "Claude execution completed.",
        }

    except Exception as e:
        return {"status": False, "message": f"Error executing Claude: {e}"}


# ---------------------------------------------------------------------------
# Relay helpers
# ---------------------------------------------------------------------------

def _get_relay_url_and_token(client, request_data):
    """
    Get relay URL and access token for a running workstation.

    Returns (relay_url, access_token, workstation_state, error_dict).
    On success error_dict is None.
    """
    name, err = _build_parent(request_data, level="workstation")
    if err:
        return None, None, None, err

    try:
        ws = client.get_workstation(
            request=workstations_v1.GetWorkstationRequest(name=name)
        )
        state = ws.state.name if ws.state else "UNKNOWN"

        if state != "STATE_RUNNING":
            return None, None, state, None

        token_response = client.generate_access_token(
            request=workstations_v1.GenerateAccessTokenRequest(workstation=name)
        )

        relay_url = f"https://8080-{ws.host}"
        return relay_url, token_response.access_token, state, None

    except Exception as e:
        return None, None, None, {"status": False, "message": f"Error accessing workstation: {e}"}


# ---------------------------------------------------------------------------
# 11. List Claude Sessions (via relay)
# ---------------------------------------------------------------------------

def invoke_list_sessions(request_data):
    """
    List running Claude Code sessions via the cockpit relay.

    Required: credential, project_id, cluster, config, workstation
    Optional: location (default: us-central1)
    """
    client, err = _get_client(request_data)
    if err:
        return err

    relay_url, access_token, state, err = _get_relay_url_and_token(client, request_data)
    if err:
        return err

    if state != "STATE_RUNNING":
        return {
            "status": True,
            "data": {"sessions": [], "session_count": 0, "workstation_state": state},
            "message": f"Workstation is {state} — no sessions running.",
        }

    try:
        response = requests.get(
            f"{relay_url}/api/sessions",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )

        if response.status_code != 200:
            return {
                "status": False,
                "message": f"Relay error (HTTP {response.status_code}): {response.text}",
                "data": {"relay_url": relay_url, "workstation_state": state},
            }

        result = response.json()
        return {
            "status": True,
            "data": {
                "sessions": result.get("sessions", []),
                "session_count": result.get("session_count", 0),
                "workstation_state": state,
                "relay_url": relay_url,
            },
            "message": f"Found {result.get('session_count', 0)} Claude session(s) running.",
        }

    except Exception as e:
        return {"status": False, "message": f"Error listing sessions: {e}"}


# ---------------------------------------------------------------------------
# 12. Send Message (streaming via relay + Redis pub/sub)
# ---------------------------------------------------------------------------

def invoke_send_message(request_data):
    """
    Send a prompt to Claude Code via the cockpit relay with streaming.

    Streams output in real-time via Redis pub/sub when thread_id is provided.
    Collects the full response and returns it as the connector result.

    Required: credential, project_id, cluster, config, workstation, prompt
    Optional: location, session_id, thread_id, output_format (default: stream-json),
              timeout (default: 300)
    """
    import redis as redis_lib

    client, err = _get_client(request_data)
    if err:
        return err

    relay_url, access_token, state, err = _get_relay_url_and_token(client, request_data)
    if err:
        return err

    if state != "STATE_RUNNING":
        return {
            "status": False,
            "data": {"workstation_state": state},
            "message": f"Workstation is {state} — cannot send message.",
        }

    prompt = request_data.get("prompt")
    if not prompt:
        return {"status": False, "message": "prompt is required."}

    session_id = request_data.get("session_id")
    thread_id = request_data.get("thread_id")
    output_format = request_data.get("output_format", "stream-json")
    timeout = int(request_data.get("timeout", 300))

    # Set up Redis publisher if thread_id is provided
    redis_client = None
    redis_channel = None
    if thread_id:
        redis_channel = f"thread:{thread_id}:stream"
        try:
            redis_url = request_data.get("redis_url", "redis://redis:6379/0")
            redis_client = redis_lib.from_url(redis_url, decode_responses=True)
        except Exception as e:
            print(f"[send_message] Redis connection failed: {e} — continuing without streaming")
            redis_client = None

    try:
        # POST to relay with streaming response
        payload = {
            "prompt": prompt,
            "output_format": output_format,
        }
        if session_id:
            payload["session_id"] = session_id

        response = requests.post(
            f"{relay_url}/api/sessions/message",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            stream=True,
            timeout=timeout,
        )

        if response.status_code != 200:
            return {
                "status": False,
                "message": f"Relay error (HTTP {response.status_code}): {response.text}",
                "data": {"relay_url": relay_url, "workstation_state": state},
            }

        # Stream response line by line
        full_content = []
        result_session_id = None

        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue

            try:
                chunk = json.loads(line)
            except json.JSONDecodeError:
                continue

            chunk_type = chunk.get("type", "")

            # Extract text content from assistant chunks
            if chunk_type == "assistant" and chunk.get("subtype") == "text":
                content = chunk.get("content", "")
                if content:
                    full_content.append(content)

                    # Publish to Redis for real-time frontend streaming
                    if redis_client and redis_channel:
                        try:
                            redis_client.publish(redis_channel, json.dumps({
                                "type": "content",
                                "content": content,
                                "metadata": {"session_id": session_id},
                            }))
                        except Exception:
                            pass

            # Capture session_id from result message
            elif chunk_type == "result":
                result_session_id = chunk.get("session_id", session_id)

                if chunk.get("subtype") == "error":
                    error_msg = chunk.get("error", "Unknown error")
                    if redis_client and redis_channel:
                        try:
                            redis_client.publish(redis_channel, json.dumps({
                                "type": "error",
                                "content": error_msg,
                                "metadata": {"session_id": result_session_id},
                            }))
                        except Exception:
                            pass

            # Relay errors
            elif chunk_type == "error":
                error_msg = chunk.get("error", "Unknown relay error")
                if redis_client and redis_channel:
                    try:
                        redis_client.publish(redis_channel, json.dumps({
                            "type": "error",
                            "content": error_msg,
                            "metadata": {"session_id": session_id},
                        }))
                    except Exception:
                        pass

        # Assemble full response
        full_text = "".join(full_content)

        # Publish "done" signal
        if redis_client and redis_channel:
            try:
                redis_client.publish(redis_channel, json.dumps({
                    "type": "done",
                    "content": full_text,
                    "metadata": {"session_id": result_session_id or session_id},
                }))
            except Exception:
                pass

        return {
            "status": True,
            "data": {
                "response": full_text,
                "session_id": result_session_id or session_id,
                "relay_url": relay_url,
                "workstation_state": state,
            },
            "message": "Claude response received.",
        }

    except requests.exceptions.Timeout:
        return {"status": False, "message": f"Request timed out after {timeout}s."}
    except Exception as e:
        return {"status": False, "message": f"Error sending message: {e}"}
    finally:
        if redis_client:
            try:
                redis_client.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 13. Kill Session (via relay)
# ---------------------------------------------------------------------------

def invoke_kill_session(request_data):
    """
    Kill a running Claude Code session on the workstation.

    Required: credential, project_id, cluster, config, workstation
    Required (one of): session_id or pid
    Optional: location (default: us-central1)
    """
    client, err = _get_client(request_data)
    if err:
        return err

    relay_url, access_token, state, err = _get_relay_url_and_token(client, request_data)
    if err:
        return err

    if state != "STATE_RUNNING":
        return {
            "status": False,
            "data": {"workstation_state": state},
            "message": f"Workstation is {state} — cannot kill session.",
        }

    session_id = request_data.get("session_id")
    pid = request_data.get("pid")

    if not session_id and not pid:
        return {"status": False, "message": "session_id or pid is required."}

    try:
        payload = {}
        if session_id:
            payload["session_id"] = session_id
        if pid:
            payload["pid"] = pid

        response = requests.post(
            f"{relay_url}/api/sessions/kill",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )

        result = response.json()

        if response.status_code != 200:
            return {
                "status": False,
                "message": result.get("message", f"Relay error (HTTP {response.status_code})"),
                "data": {"relay_url": relay_url, "workstation_state": state},
            }

        return {
            "status": True,
            "data": {
                "result": result,
                "relay_url": relay_url,
                "workstation_state": state,
            },
            "message": result.get("message", "Session killed."),
        }

    except Exception as e:
        return {"status": False, "message": f"Error killing session: {e}"}
