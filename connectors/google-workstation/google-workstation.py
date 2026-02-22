def invoke_list_clusters(request_data):
    from google.cloud import workstations_v1
    from google.oauth2 import service_account
    import json

    request_data = {**request_data, **request_data.get('params', {})}
    credential = request_data.get("credential")
    if not credential:
        return {"status": False, "message": "credential is required (service account JSON)."}
    if isinstance(credential, str):
        credential = json.loads(credential)

    project_id = request_data.get("project_id")
    location = request_data.get("location", "us-central1")
    if not project_id:
        return {"status": False, "message": "project_id is required."}

    try:
        creds = service_account.Credentials.from_service_account_info(credential)
        client = workstations_v1.WorkstationsClient(credentials=creds)
        parent = f"projects/{project_id}/locations/{location}"

        clusters = list(client.list_workstation_clusters(
            request=workstations_v1.ListWorkstationClustersRequest(parent=parent)
        ))
        return {
            "status": True,
            "data": [{
                "name": c.name, "display_name": c.display_name, "uid": c.uid,
                "reconciling": c.reconciling, "network": c.network,
                "subnetwork": c.subnetwork, "control_plane_ip": c.control_plane_ip,
                "degraded": c.degraded,
            } for c in clusters],
            "message": f"Found {len(clusters)} cluster(s).",
        }
    except Exception as e:
        return {"status": False, "message": f"Error listing clusters: {e}"}


def invoke_list_configs(request_data):
    from google.cloud import workstations_v1
    from google.oauth2 import service_account
    import json

    request_data = {**request_data, **request_data.get('params', {})}
    credential = request_data.get("credential")
    if not credential:
        return {"status": False, "message": "credential is required (service account JSON)."}
    if isinstance(credential, str):
        credential = json.loads(credential)

    project_id = request_data.get("project_id")
    location = request_data.get("location", "us-central1")
    cluster = request_data.get("cluster")
    if not project_id:
        return {"status": False, "message": "project_id is required."}
    if not cluster:
        return {"status": False, "message": "cluster is required."}

    try:
        creds = service_account.Credentials.from_service_account_info(credential)
        client = workstations_v1.WorkstationsClient(credentials=creds)
        parent = f"projects/{project_id}/locations/{location}/workstationClusters/{cluster}"

        configs = list(client.list_workstation_configs(
            request=workstations_v1.ListWorkstationConfigsRequest(parent=parent)
        ))

        data = []
        for cfg in configs:
            item = {
                "name": cfg.name, "display_name": cfg.display_name, "uid": cfg.uid,
                "reconciling": cfg.reconciling,
                "idle_timeout": str(cfg.idle_timeout) if cfg.idle_timeout else None,
                "running_timeout": str(cfg.running_timeout) if cfg.running_timeout else None,
                "replica_zones": list(cfg.replica_zones) if cfg.replica_zones else [],
            }
            if cfg.host and cfg.host.gce_instance:
                item["host"] = {"gce_instance": {
                    "machine_type": cfg.host.gce_instance.machine_type,
                    "pool_size": cfg.host.gce_instance.pool_size,
                    "disable_public_ip_addresses": cfg.host.gce_instance.disable_public_ip_addresses,
                }}
            if cfg.container:
                item["container"] = {
                    "image": cfg.container.image,
                    "command": list(cfg.container.command) if cfg.container.command else [],
                    "args": list(cfg.container.args) if cfg.container.args else [],
                    "run_as_user": cfg.container.run_as_user,
                }
            data.append(item)

        return {"status": True, "data": data, "message": f"Found {len(configs)} config(s)."}
    except Exception as e:
        return {"status": False, "message": f"Error listing configs: {e}"}


def invoke_list_workstations(request_data):
    from google.cloud import workstations_v1
    from google.oauth2 import service_account
    import json

    request_data = {**request_data, **request_data.get('params', {})}
    credential = request_data.get("credential")
    if not credential:
        return {"status": False, "message": "credential is required (service account JSON)."}
    if isinstance(credential, str):
        credential = json.loads(credential)

    project_id = request_data.get("project_id")
    location = request_data.get("location", "us-central1")
    cluster = request_data.get("cluster")
    config = request_data.get("config")
    if not project_id:
        return {"status": False, "message": "project_id is required."}
    if not cluster:
        return {"status": False, "message": "cluster is required."}
    if not config:
        return {"status": False, "message": "config is required."}

    try:
        creds = service_account.Credentials.from_service_account_info(credential)
        client = workstations_v1.WorkstationsClient(credentials=creds)
        parent = f"projects/{project_id}/locations/{location}/workstationClusters/{cluster}/workstationConfigs/{config}"

        workstations = list(client.list_workstations(
            request=workstations_v1.ListWorkstationsRequest(parent=parent)
        ))
        return {
            "status": True,
            "data": [{
                "name": ws.name, "display_name": ws.display_name, "uid": ws.uid,
                "state": ws.state.name if ws.state else None,
                "host": ws.host, "reconciling": ws.reconciling,
            } for ws in workstations],
            "message": f"Found {len(workstations)} workstation(s).",
        }
    except Exception as e:
        return {"status": False, "message": f"Error listing workstations: {e}"}


def invoke_get_workstation(request_data):
    from google.cloud import workstations_v1
    from google.oauth2 import service_account
    import json

    request_data = {**request_data, **request_data.get('params', {})}
    credential = request_data.get("credential")
    if not credential:
        return {"status": False, "message": "credential is required (service account JSON)."}
    if isinstance(credential, str):
        credential = json.loads(credential)

    project_id = request_data.get("project_id")
    location = request_data.get("location", "us-central1")
    cluster = request_data.get("cluster")
    config = request_data.get("config")
    workstation = request_data.get("workstation")
    if not project_id:
        return {"status": False, "message": "project_id is required."}
    if not cluster:
        return {"status": False, "message": "cluster is required."}
    if not config:
        return {"status": False, "message": "config is required."}
    if not workstation:
        return {"status": False, "message": "workstation is required."}

    try:
        creds = service_account.Credentials.from_service_account_info(credential)
        client = workstations_v1.WorkstationsClient(credentials=creds)
        name = f"projects/{project_id}/locations/{location}/workstationClusters/{cluster}/workstationConfigs/{config}/workstations/{workstation}"

        ws = client.get_workstation(request=workstations_v1.GetWorkstationRequest(name=name))
        return {
            "status": True,
            "data": {
                "name": ws.name, "display_name": ws.display_name, "uid": ws.uid,
                "state": ws.state.name if ws.state else None,
                "host": ws.host, "reconciling": ws.reconciling,
            },
            "message": f"Workstation state: {ws.state.name if ws.state else 'UNKNOWN'}",
        }
    except Exception as e:
        return {"status": False, "message": f"Error getting workstation: {e}"}


def invoke_create_workstation(request_data):
    from google.cloud import workstations_v1
    from google.oauth2 import service_account
    import json

    request_data = {**request_data, **request_data.get('params', {})}
    credential = request_data.get("credential")
    if not credential:
        return {"status": False, "message": "credential is required (service account JSON)."}
    if isinstance(credential, str):
        credential = json.loads(credential)

    project_id = request_data.get("project_id")
    location = request_data.get("location", "us-central1")
    cluster = request_data.get("cluster")
    config = request_data.get("config")
    workstation_id = request_data.get("workstation_id")
    if not project_id:
        return {"status": False, "message": "project_id is required."}
    if not cluster:
        return {"status": False, "message": "cluster is required."}
    if not config:
        return {"status": False, "message": "config is required."}
    if not workstation_id:
        return {"status": False, "message": "workstation_id is required."}

    display_name = request_data.get("display_name", workstation_id)
    labels = request_data.get("labels") or {}
    wait = request_data.get("wait", True)

    try:
        creds = service_account.Credentials.from_service_account_info(credential)
        client = workstations_v1.WorkstationsClient(credentials=creds)
        parent = f"projects/{project_id}/locations/{location}/workstationClusters/{cluster}/workstationConfigs/{config}"

        operation = client.create_workstation(
            request=workstations_v1.CreateWorkstationRequest(
                parent=parent,
                workstation_id=workstation_id,
                workstation=workstations_v1.Workstation(display_name=display_name, labels=labels),
            )
        )

        if wait:
            result = operation.result()
            return {
                "status": True,
                "data": {
                    "name": result.name, "display_name": result.display_name, "uid": result.uid,
                    "state": result.state.name if result.state else None,
                    "host": result.host, "reconciling": result.reconciling,
                },
                "message": f"Workstation '{workstation_id}' created successfully.",
            }
        return {
            "status": True,
            "data": {"operation_name": operation.operation.name},
            "message": f"Workstation '{workstation_id}' creation started.",
        }
    except Exception as e:
        return {"status": False, "message": f"Error creating workstation: {e}"}


def invoke_start_workstation(request_data):
    from google.cloud import workstations_v1
    from google.oauth2 import service_account
    import json

    request_data = {**request_data, **request_data.get('params', {})}
    credential = request_data.get("credential")
    if not credential:
        return {"status": False, "message": "credential is required (service account JSON)."}
    if isinstance(credential, str):
        credential = json.loads(credential)

    project_id = request_data.get("project_id")
    location = request_data.get("location", "us-central1")
    cluster = request_data.get("cluster")
    config = request_data.get("config")
    workstation = request_data.get("workstation")
    if not project_id:
        return {"status": False, "message": "project_id is required."}
    if not cluster:
        return {"status": False, "message": "cluster is required."}
    if not config:
        return {"status": False, "message": "config is required."}
    if not workstation:
        return {"status": False, "message": "workstation is required."}

    wait = request_data.get("wait", True)

    try:
        creds = service_account.Credentials.from_service_account_info(credential)
        client = workstations_v1.WorkstationsClient(credentials=creds)
        name = f"projects/{project_id}/locations/{location}/workstationClusters/{cluster}/workstationConfigs/{config}/workstations/{workstation}"

        operation = client.start_workstation(request=workstations_v1.StartWorkstationRequest(name=name))

        if wait:
            result = operation.result()
            return {
                "status": True,
                "data": {
                    "name": result.name, "display_name": result.display_name, "uid": result.uid,
                    "state": result.state.name if result.state else None,
                    "host": result.host, "reconciling": result.reconciling,
                },
                "message": "Workstation started successfully.",
            }
        return {
            "status": True,
            "data": {"operation_name": operation.operation.name},
            "message": "Workstation start initiated.",
        }
    except Exception as e:
        return {"status": False, "message": f"Error starting workstation: {e}"}


def invoke_stop_workstation(request_data):
    from google.cloud import workstations_v1
    from google.oauth2 import service_account
    import json

    request_data = {**request_data, **request_data.get('params', {})}
    credential = request_data.get("credential")
    if not credential:
        return {"status": False, "message": "credential is required (service account JSON)."}
    if isinstance(credential, str):
        credential = json.loads(credential)

    project_id = request_data.get("project_id")
    location = request_data.get("location", "us-central1")
    cluster = request_data.get("cluster")
    config = request_data.get("config")
    workstation = request_data.get("workstation")
    if not project_id:
        return {"status": False, "message": "project_id is required."}
    if not cluster:
        return {"status": False, "message": "cluster is required."}
    if not config:
        return {"status": False, "message": "config is required."}
    if not workstation:
        return {"status": False, "message": "workstation is required."}

    wait = request_data.get("wait", True)

    try:
        creds = service_account.Credentials.from_service_account_info(credential)
        client = workstations_v1.WorkstationsClient(credentials=creds)
        name = f"projects/{project_id}/locations/{location}/workstationClusters/{cluster}/workstationConfigs/{config}/workstations/{workstation}"

        operation = client.stop_workstation(request=workstations_v1.StopWorkstationRequest(name=name))

        if wait:
            result = operation.result()
            return {
                "status": True,
                "data": {
                    "name": result.name, "display_name": result.display_name, "uid": result.uid,
                    "state": result.state.name if result.state else None,
                    "host": result.host, "reconciling": result.reconciling,
                },
                "message": "Workstation stopped successfully.",
            }
        return {
            "status": True,
            "data": {"operation_name": operation.operation.name},
            "message": "Workstation stop initiated.",
        }
    except Exception as e:
        return {"status": False, "message": f"Error stopping workstation: {e}"}


def invoke_delete_workstation(request_data):
    from google.cloud import workstations_v1
    from google.oauth2 import service_account
    import json

    request_data = {**request_data, **request_data.get('params', {})}
    credential = request_data.get("credential")
    if not credential:
        return {"status": False, "message": "credential is required (service account JSON)."}
    if isinstance(credential, str):
        credential = json.loads(credential)

    project_id = request_data.get("project_id")
    location = request_data.get("location", "us-central1")
    cluster = request_data.get("cluster")
    config = request_data.get("config")
    workstation = request_data.get("workstation")
    if not project_id:
        return {"status": False, "message": "project_id is required."}
    if not cluster:
        return {"status": False, "message": "cluster is required."}
    if not config:
        return {"status": False, "message": "config is required."}
    if not workstation:
        return {"status": False, "message": "workstation is required."}

    wait = request_data.get("wait", True)

    try:
        creds = service_account.Credentials.from_service_account_info(credential)
        client = workstations_v1.WorkstationsClient(credentials=creds)
        name = f"projects/{project_id}/locations/{location}/workstationClusters/{cluster}/workstationConfigs/{config}/workstations/{workstation}"

        operation = client.delete_workstation(request=workstations_v1.DeleteWorkstationRequest(name=name))

        if wait:
            operation.result()
            return {"status": True, "data": {"deleted": name}, "message": "Workstation deleted successfully."}
        return {
            "status": True,
            "data": {"operation_name": operation.operation.name},
            "message": "Workstation deletion initiated.",
        }
    except Exception as e:
        return {"status": False, "message": f"Error deleting workstation: {e}"}


def invoke_generate_access_token(request_data):
    from google.cloud import workstations_v1
    from google.oauth2 import service_account
    import json

    request_data = {**request_data, **request_data.get('params', {})}
    credential = request_data.get("credential")
    if not credential:
        return {"status": False, "message": "credential is required (service account JSON)."}
    if isinstance(credential, str):
        credential = json.loads(credential)

    project_id = request_data.get("project_id")
    location = request_data.get("location", "us-central1")
    cluster = request_data.get("cluster")
    config = request_data.get("config")
    workstation = request_data.get("workstation")
    if not project_id:
        return {"status": False, "message": "project_id is required."}
    if not cluster:
        return {"status": False, "message": "cluster is required."}
    if not config:
        return {"status": False, "message": "config is required."}
    if not workstation:
        return {"status": False, "message": "workstation is required."}

    try:
        creds = service_account.Credentials.from_service_account_info(credential)
        client = workstations_v1.WorkstationsClient(credentials=creds)
        name = f"projects/{project_id}/locations/{location}/workstationClusters/{cluster}/workstationConfigs/{config}/workstations/{workstation}"

        response = client.generate_access_token(request=workstations_v1.GenerateAccessTokenRequest(workstation=name))
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


def invoke_execute_claude(request_data):
    from google.cloud import workstations_v1
    from google.oauth2 import service_account
    import json
    import requests

    request_data = {**request_data, **request_data.get('params', {})}
    credential = request_data.get("credential")
    if not credential:
        return {"status": False, "message": "credential is required (service account JSON)."}
    if isinstance(credential, str):
        credential = json.loads(credential)

    project_id = request_data.get("project_id")
    location = request_data.get("location", "us-central1")
    cluster = request_data.get("cluster")
    config = request_data.get("config")
    workstation = request_data.get("workstation")
    prompt = request_data.get("prompt")
    if not project_id:
        return {"status": False, "message": "project_id is required."}
    if not cluster:
        return {"status": False, "message": "cluster is required."}
    if not config:
        return {"status": False, "message": "config is required."}
    if not workstation:
        return {"status": False, "message": "workstation is required."}
    if not prompt:
        return {"status": False, "message": "prompt is required."}

    output_format = request_data.get("output_format", "json")
    timeout = int(request_data.get("timeout", 300))

    try:
        creds = service_account.Credentials.from_service_account_info(credential)
        client = workstations_v1.WorkstationsClient(credentials=creds)
        name = f"projects/{project_id}/locations/{location}/workstationClusters/{cluster}/workstationConfigs/{config}/workstations/{workstation}"

        ws = client.get_workstation(request=workstations_v1.GetWorkstationRequest(name=name))
        if (ws.state.name if ws.state else "UNKNOWN") != "STATE_RUNNING":
            client.start_workstation(request=workstations_v1.StartWorkstationRequest(name=name)).result()

        access_token = client.generate_access_token(
            request=workstations_v1.GenerateAccessTokenRequest(workstation=name)
        ).access_token

        exec_url = f"https://80-{workstation}.{cluster}.{location}.cloudworkstations.dev"
        response = requests.post(
            f"{exec_url}/api/exec",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={"command": f'claude -p "{prompt}" --output-format {output_format}'},
            timeout=timeout,
        )

        if response.status_code != 200:
            return {"status": False, "message": f"Exec failed (HTTP {response.status_code}): {response.text}"}

        result = response.json() if response.headers.get("content-type", "").startswith("application/json") else {"output": response.text}
        return {
            "status": True,
            "data": {"result": result, "workstation_url": exec_url, "output_format": output_format},
            "message": "Claude execution completed.",
        }
    except Exception as e:
        return {"status": False, "message": f"Error executing Claude: {e}"}


def invoke_list_sessions(request_data):
    from google.cloud import workstations_v1
    from google.oauth2 import service_account
    import json
    import requests

    request_data = {**request_data, **request_data.get('params', {})}
    credential = request_data.get("credential")
    if not credential:
        return {"status": False, "message": "credential is required (service account JSON)."}
    if isinstance(credential, str):
        credential = json.loads(credential)

    project_id = request_data.get("project_id")
    location = request_data.get("location", "us-central1")
    cluster = request_data.get("cluster")
    config = request_data.get("config")
    workstation = request_data.get("workstation")
    if not project_id:
        return {"status": False, "message": "project_id is required."}
    if not cluster:
        return {"status": False, "message": "cluster is required."}
    if not config:
        return {"status": False, "message": "config is required."}
    if not workstation:
        return {"status": False, "message": "workstation is required."}

    try:
        creds = service_account.Credentials.from_service_account_info(credential)
        client = workstations_v1.WorkstationsClient(credentials=creds)
        name = f"projects/{project_id}/locations/{location}/workstationClusters/{cluster}/workstationConfigs/{config}/workstations/{workstation}"

        ws = client.get_workstation(request=workstations_v1.GetWorkstationRequest(name=name))
        state = ws.state.name if ws.state else "UNKNOWN"

        if state != "STATE_RUNNING":
            return {
                "status": True,
                "data": {"sessions": [], "session_count": 0, "workstation_state": state},
                "message": f"Workstation is {state} — no sessions running.",
            }

        access_token = client.generate_access_token(
            request=workstations_v1.GenerateAccessTokenRequest(workstation=name)
        ).access_token
        relay_url = f"https://8080-{ws.host}"

        response = requests.get(
            f"{relay_url}/api/sessions",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )

        if response.status_code != 200:
            return {"status": False, "message": f"Relay error (HTTP {response.status_code}): {response.text}"}

        result = response.json()
        return {
            "status": True,
            "data": {
                "sessions": result.get("sessions", []),
                "session_count": result.get("session_count", 0),
                "workstation_state": state, "relay_url": relay_url,
            },
            "message": f"Found {result.get('session_count', 0)} Claude session(s) running.",
        }
    except Exception as e:
        return {"status": False, "message": f"Error listing sessions: {e}"}


def invoke_send_message(request_data):
    from google.cloud import workstations_v1
    from google.oauth2 import service_account
    import json
    import requests
    import redis as redis_lib

    request_data = {**request_data, **request_data.get('params', {})}
    credential = request_data.get("credential")
    if not credential:
        return {"status": False, "message": "credential is required (service account JSON)."}
    if isinstance(credential, str):
        credential = json.loads(credential)

    project_id = request_data.get("project_id")
    location = request_data.get("location", "us-central1")
    cluster = request_data.get("cluster")
    config = request_data.get("config")
    workstation = request_data.get("workstation")
    prompt = request_data.get("prompt")
    if not project_id:
        return {"status": False, "message": "project_id is required."}
    if not cluster:
        return {"status": False, "message": "cluster is required."}
    if not config:
        return {"status": False, "message": "config is required."}
    if not workstation:
        return {"status": False, "message": "workstation is required."}
    if not prompt:
        return {"status": False, "message": "prompt is required."}

    session_id = request_data.get("session_id")
    thread_id = request_data.get("thread_id")
    output_format = request_data.get("output_format", "stream-json")
    timeout = int(request_data.get("timeout", 300))

    try:
        creds = service_account.Credentials.from_service_account_info(credential)
        client = workstations_v1.WorkstationsClient(credentials=creds)
        name = f"projects/{project_id}/locations/{location}/workstationClusters/{cluster}/workstationConfigs/{config}/workstations/{workstation}"

        ws = client.get_workstation(request=workstations_v1.GetWorkstationRequest(name=name))
        state = ws.state.name if ws.state else "UNKNOWN"

        if state != "STATE_RUNNING":
            return {"status": False, "data": {"workstation_state": state}, "message": f"Workstation is {state} — cannot send message."}

        access_token = client.generate_access_token(
            request=workstations_v1.GenerateAccessTokenRequest(workstation=name)
        ).access_token
        relay_url = f"https://8080-{ws.host}"

        # Redis pub/sub for real-time streaming
        redis_client = None
        redis_channel = None
        if thread_id:
            redis_channel = f"thread:{thread_id}:stream"
            try:
                redis_url = request_data.get("redis_url", "redis://redis:6379/0")
                redis_client = redis_lib.from_url(redis_url, decode_responses=True)
            except Exception:
                redis_client = None

        payload = {"prompt": prompt, "output_format": output_format}
        if session_id:
            payload["session_id"] = session_id

        response = requests.post(
            f"{relay_url}/api/sessions/message",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=payload, stream=True, timeout=timeout,
        )

        if response.status_code != 200:
            return {"status": False, "message": f"Relay error (HTTP {response.status_code}): {response.text}"}

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

            if chunk_type == "system" and chunk.get("subtype") == "init":
                result_session_id = chunk.get("session_id", session_id)

            elif chunk_type == "assistant":
                # stream-json: content is in message.content[].text
                msg = chunk.get("message", {})
                content_blocks = msg.get("content", [])
                for block in content_blocks:
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        if text:
                            full_content.append(text)
                            if redis_client and redis_channel:
                                try:
                                    redis_client.publish(redis_channel, json.dumps({
                                        "type": "content", "content": text,
                                        "metadata": {"session_id": result_session_id or session_id},
                                    }))
                                except Exception:
                                    pass

            elif chunk_type == "result":
                result_session_id = chunk.get("session_id", result_session_id or session_id)
                # result.result contains the full text as fallback
                if not full_content and chunk.get("result"):
                    full_content.append(chunk["result"])
                if chunk.get("subtype") == "error" and redis_client and redis_channel:
                    try:
                        redis_client.publish(redis_channel, json.dumps({
                            "type": "error", "content": chunk.get("error", "Unknown error"),
                            "metadata": {"session_id": result_session_id},
                        }))
                    except Exception:
                        pass

            elif chunk_type == "error" and redis_client and redis_channel:
                try:
                    redis_client.publish(redis_channel, json.dumps({
                        "type": "error", "content": chunk.get("error", "Unknown relay error"),
                        "metadata": {"session_id": result_session_id or session_id},
                    }))
                except Exception:
                    pass

        full_text = "".join(full_content)

        if redis_client and redis_channel:
            try:
                redis_client.publish(redis_channel, json.dumps({
                    "type": "done", "content": full_text,
                    "metadata": {"session_id": result_session_id or session_id},
                }))
            except Exception:
                pass

        if redis_client:
            try:
                redis_client.close()
            except Exception:
                pass

        return {
            "status": True,
            "data": {
                "response": full_text,
                "session_id": result_session_id or session_id,
                "relay_url": relay_url, "workstation_state": state,
            },
            "message": "Claude response received.",
        }
    except requests.exceptions.Timeout:
        return {"status": False, "message": f"Request timed out after {timeout}s."}
    except Exception as e:
        return {"status": False, "message": f"Error sending message: {e}"}


def invoke_kill_session(request_data):
    from google.cloud import workstations_v1
    from google.oauth2 import service_account
    import json
    import requests

    request_data = {**request_data, **request_data.get('params', {})}
    credential = request_data.get("credential")
    if not credential:
        return {"status": False, "message": "credential is required (service account JSON)."}
    if isinstance(credential, str):
        credential = json.loads(credential)

    project_id = request_data.get("project_id")
    location = request_data.get("location", "us-central1")
    cluster = request_data.get("cluster")
    config = request_data.get("config")
    workstation = request_data.get("workstation")
    if not project_id:
        return {"status": False, "message": "project_id is required."}
    if not cluster:
        return {"status": False, "message": "cluster is required."}
    if not config:
        return {"status": False, "message": "config is required."}
    if not workstation:
        return {"status": False, "message": "workstation is required."}

    session_id = request_data.get("session_id")
    pid = request_data.get("pid")
    if not session_id and not pid:
        return {"status": False, "message": "session_id or pid is required."}

    try:
        creds = service_account.Credentials.from_service_account_info(credential)
        client = workstations_v1.WorkstationsClient(credentials=creds)
        name = f"projects/{project_id}/locations/{location}/workstationClusters/{cluster}/workstationConfigs/{config}/workstations/{workstation}"

        ws = client.get_workstation(request=workstations_v1.GetWorkstationRequest(name=name))
        state = ws.state.name if ws.state else "UNKNOWN"

        if state != "STATE_RUNNING":
            return {"status": False, "data": {"workstation_state": state}, "message": f"Workstation is {state} — cannot kill session."}

        access_token = client.generate_access_token(
            request=workstations_v1.GenerateAccessTokenRequest(workstation=name)
        ).access_token
        relay_url = f"https://8080-{ws.host}"

        payload = {}
        if session_id:
            payload["session_id"] = session_id
        if pid:
            payload["pid"] = pid

        response = requests.post(
            f"{relay_url}/api/sessions/kill",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json=payload, timeout=30,
        )

        result = response.json()
        if response.status_code != 200:
            return {"status": False, "message": result.get("message", f"Relay error (HTTP {response.status_code})")}

        return {
            "status": True,
            "data": {"result": result, "relay_url": relay_url, "workstation_state": state},
            "message": result.get("message", "Session killed."),
        }
    except Exception as e:
        return {"status": False, "message": f"Error killing session: {e}"}
