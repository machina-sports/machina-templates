from slack_sdk import WebClient

from slack_sdk.errors import SlackApiError


def send_slack_message(request_data):

    headers = request_data.get('headers')
    params = request_data.get('params')

    api_key = headers.get("api_key", "")

    channel_id = params.get("channel_id")
    message = params.get("message")

    slack_emoji = params.get("slack_emoji")
    slack_username = params.get("slack_username")
    thread_id = params.get("thread-id", None)

    client = WebClient(token=api_key)

    response = {}

    try:
        response = client.chat_postMessage(
            channel=channel_id,
            username=slack_username,
            icon_emoji=slack_emoji,
            text=message,
            thread_ts=thread_id
        )

    except SlackApiError as e:

        assert e.response["ok"] is False

        err = e.response["error"]

        print(f"Got an error: {err}")

    thread_ts = response.get("ts")

    return {"status": True, "data": thread_ts, "message": "Message sended."}
