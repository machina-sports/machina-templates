"""Synthetic tests for the narrow public ESPN reporting connector.

Fixtures reproduce the observed 2026-09-14 response shape but contain no ESPN
article copy. Provider I/O is mocked except for the separate manual QA command.
"""
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
CONNECTOR = ROOT / "connectors/machina-read-reporting"
SOURCE = CONNECTOR / "machina-read-reporting.py"
NOW = datetime(2026, 9, 14, 15, 0, tzinfo=timezone.utc)


class Response:
    def __init__(self, payload, url, *, status=200, headers=None):
        self.body = io.BytesIO(payload)
        self.url = url
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}

    def read(self, size=-1):
        return self.body.read(size)

    def geturl(self):
        return self.url

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class Opener:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def open(self, request, timeout):
        self.calls.append((request.full_url, timeout, dict(request.header_items())))
        if self.error:
            raise self.error
        return self.response


def load_connector():
    namespace = {"__name__": "machina_read_reporting_exec_test"}
    exec(compile(SOURCE.read_text(), "<machina-read-reporting>", "exec"), namespace)
    namespace["_now"] = lambda: NOW
    return namespace


def record(**overrides):
    value = {
        "id": 49930014,
        "type": "Story",
        "premium": False,
        "headline": "Synthetic Harbor Wolves reporting headline",
        "description": "Synthetic description of the reported development.",
        "published": "2026-09-14T12:32:31Z",
        "lastModified": "2026-09-14T13:10:00Z",
        "story": "<p>" + ("Synthetic reporting detail. " * 350) + "</p>",
        "links": {"web": {"href": "https://www.espn.com/nfl/story/_/id/49930014/synthetic-report"}},
    }
    value.update(overrides)
    return value


def provider(*headlines):
    return json.dumps({
        "resultsCount": len(headlines), "resultsLimit": 3, "resultsOffset": 0,
        "headlines": list(headlines), "breakingNews": [],
        "timestamp": "2026-09-14T14:59:00Z", "status": "success",
    }).encode()


def invoke(namespace, payload, *, sport="americanfootball", final_url=None, headers=None):
    url = "https://now.core.api.espn.com/v1/sports/football/nfl/news?limit=3"
    response = Response(payload, final_url or url, headers=headers)
    opener = Opener(response)
    namespace["_OPENER"] = opener
    result = namespace["invoke_reporting"]({"params": {"sport": sport}})
    return result, opener


def test_exec_without_file_and_normalizes_bounded_plain_article_text():
    namespace = load_connector()
    dirty = ("<style>secret-style</style><script>secret-script</script>"
             "<embed>secret-embed</embed><p>Visible opening.</p><p>" + "A" * 7000 + "</p>")
    result, opener = invoke(namespace, provider(record(story=dirty)))

    assert result["status"] is True
    article = result["data"]["articles"][0]
    assert set(article) == {"id", "sport", "type", "headline", "description", "published",
                            "lastModified", "text", "textTruncated", "url"}
    assert article["sport"] == "americanfootball" and article["type"] == "Story"
    assert article["textTruncated"] is True and len(article["text"]) <= 6000
    assert "Visible opening" in article["text"]
    assert all(secret not in article["text"] for secret in ("secret-style", "secret-script", "secret-embed"))
    assert article["text"].endswith("[Reporting excerpt truncated.]")
    assert opener.calls == [("https://now.core.api.espn.com/v1/sports/football/nfl/news?limit=3",
                             namespace["TIMEOUT_SECONDS"],
                             {"Accept": "application/json", "User-agent": "machina-read-reporting/1.0"})]


def test_filters_malformed_premium_stale_future_bad_type_url_and_empty_body():
    namespace = load_connector()
    values = [
        record(id=1, premium=True),
        record(id=2, published=(NOW - timedelta(hours=49)).isoformat().replace("+00:00", "Z")),
        record(id=3, published=(NOW + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")),
        record(id=4, type="Video"),
        record(id=5, story="<script>only script</script>"),
        record(id=6, links={"web": {"href": "https://evil.example/nfl/story/_/id/6"}}),
        record(id=7, lastModified=(NOW + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")),
        record(id="not-an-integer"),
        record(id=8, type="HeadlineNews", links={"web": {"href":
               "https://www.espn.com/nfl/story/_/id/8/synthetic-report"}}),
    ]
    result, _ = invoke(namespace, provider(*values))
    assert [article["id"] for article in result["data"]["articles"]] == ["8"]


@pytest.mark.parametrize("links", [[], "web", {"web": []}, {"web": "article"}])
def test_nonobject_link_containers_are_skipped(links):
    namespace = load_connector()
    result, _ = invoke(namespace, provider(record(id=1, links=links), record()))
    assert [article["id"] for article in result["data"]["articles"]] == ["49930014"]


@pytest.mark.parametrize("url", [
    "http://www.espn.com/nfl/story/_/id/49930014/x",
    "https://espn.com/nfl/story/_/id/49930014/x",
    "https://www.espn.com/nba/story/_/id/49930014/x",
    "https://www.espn.com/nfl/video/_/id/49930014/x",
    "https://www.espn.com/nfl/story/_/id/999/x",
    "https://user@www.espn.com/nfl/story/_/id/49930014/x",
    "https://www.espn.com:443/nfl/story/_/id/49930014/x",
    "https://www.espn.com/nfl/story/_/id/49930014/x#fragment",
])
def test_rejects_malicious_or_unbound_article_urls(url):
    namespace = load_connector()
    result, _ = invoke(namespace, provider(record(links={"web": {"href": url}})))
    assert result["status"] is True and result["data"]["articles"] == []


def test_redirects_are_forbidden_and_transport_failures_are_typed():
    namespace = load_connector()
    redirected, _ = invoke(namespace, provider(record()), final_url="https://www.espn.com/redirected")
    assert redirected == {"status": False, "message": "redirect_forbidden"}

    namespace["_OPENER"] = Opener(error=TimeoutError("sensitive network detail"))
    timed_out = namespace["invoke_reporting"]({"params": {"sport": "americanfootball"}})
    assert timed_out == {"status": False, "message": "upstream_timeout"}
    assert "sensitive" not in json.dumps(timed_out)


def test_response_byte_limit_applies_to_header_and_stream():
    namespace = load_connector()
    maximum = namespace["MAX_RESPONSE_BYTES"]
    oversized_header, _ = invoke(namespace, b"{}", headers={
        "Content-Type": "application/json", "Content-Length": str(maximum + 1)})
    assert oversized_header == {"status": False, "message": "response_too_large"}

    oversized_stream, _ = invoke(namespace, b" " * (maximum + 1))
    assert oversized_stream == {"status": False, "message": "response_too_large"}


def test_request_surface_is_fixed_to_allowlisted_sports_without_endpoint_or_proxy_override():
    namespace = load_connector()
    namespace["_OPENER"] = Opener(Response(provider(record()),
        "https://now.core.api.espn.com/v1/sports/football/nfl/news?limit=3"))
    bad = namespace["invoke_reporting"]({"params": {
        "sport": "americanfootball", "endpoint": "https://evil.example", "proxy": "http://evil.example"}})
    assert bad == {"status": False, "message": "invalid_request"}
    assert namespace["_OPENER"].calls == []
    assert namespace["invoke_reporting"]({"params": {"sport": "chess"}}) == {
        "status": False, "message": "unsupported_sport"}
    assert set(namespace["SPORT_PATHS"]) == {
        "football", "americanfootball", "baseball", "basketball", "hockey",
        "tennis", "motorsport", "golf", "cricket"}


@pytest.mark.parametrize("sport", [None, 1, True, [], {}])
def test_nonstring_and_unhashable_sports_return_typed_failure_without_io(sport):
    namespace = load_connector()
    namespace["_OPENER"] = Opener(Response(b"{}", "https://unused.example"))
    assert namespace["invoke_reporting"]({"params": {"sport": sport}}) == {
        "status": False, "message": "unsupported_sport"}
    assert namespace["_OPENER"].calls == []


def test_declaration_install_and_command_parity():
    namespace = load_connector()
    declaration = yaml.safe_load((CONNECTOR / "machina-read-reporting.yml").read_text())["connector"]
    install_doc = yaml.safe_load((CONNECTOR / "_install.yml").read_text())
    install = install_doc["setup"]
    commands = [command["value"] for command in declaration["commands"]]
    public = sorted(name for name, value in namespace.items()
                    if name.startswith("invoke_") and callable(value))
    assert declaration["name"] == "machina-read-reporting"
    assert declaration["filetype"] == "pyscript" and declaration["filename"] == SOURCE.name
    assert commands == public == ["invoke_reporting"]
    assert install["value"] == "connectors/machina-read-reporting"
    assert install_doc["datasets"] == [{"type": "connector", "path": "machina-read-reporting.yml"}]
