def football(request_data):
    return {
        "status": True,
        "result": {"ping": "pong", "received_type": type(request_data).__name__, "received_repr": repr(request_data)[:300]},
        "data": {"ping": "pong", "received_type": type(request_data).__name__, "received_repr": repr(request_data)[:300]},
        "ping": "pong",
        "received_type": type(request_data).__name__,
        "received_repr": repr(request_data)[:300],
    }
