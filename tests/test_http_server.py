"""Tests for the remote HTTP surface: REST, OpenAPI, auth and OAuth."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.testclient import TestClient

from hk_criminal_law_mcp.db import connect
from hk_criminal_law_mcp.http_server import (
    CORE_TOOLS,
    HTTPSettings,
    _sanitize_schema,
    create_app,
)
from hk_criminal_law_mcp.ingest_legislation import upsert_document
from hk_criminal_law_mcp.legislation_xml import parse_document
from hk_criminal_law_mcp.server import TOOL_FUNCTIONS, mcp

from .test_legislation_xml import XML

INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "1"},
    },
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


@pytest.fixture()
def http_db(tmp_path, monkeypatch):
    path = tmp_path / "http.db"
    conn = connect(path)
    upsert_document(conn, parse_document(XML), "fixture.xml", "checksum")
    conn.commit()
    conn.close()
    monkeypatch.setenv("HK_LAW_DB", str(path))
    return path


def _settings(tmp_path, **overrides) -> HTTPSettings:
    base = dict(
        host="127.0.0.1",
        port=8765,
        rate_limit=0,
        allowed_hosts=("testserver",),
        oauth_store=tmp_path / "oauth.json",
    )
    base.update(overrides)
    return HTTPSettings(**base)


def _initialize(client: TestClient, token: str | None = None) -> None:
    headers = dict(MCP_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = client.post("/mcp", json=INIT, headers=headers)
    assert response.status_code == 200, response.text


def _sse_json(response):
    for line in response.text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    return response.json()


def test_mcp_tools_list_over_http(http_db, tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            headers=MCP_HEADERS,
        )
        assert response.status_code == 200, response.text
        payload = _sse_json(response)
        tools = {
            tool["name"]: tool for tool in payload["result"]["tools"]
        }
        assert len(tools) == 29
        assert "sync_doj" not in tools
        annotations = tools["search_legislation"].get("annotations") or {}
        assert annotations.get("readOnlyHint") is True


def test_tool_registry_matches_mcp():
    tools = asyncio.run(mcp.list_tools())
    assert {tool.name for tool in tools} == set(TOOL_FUNCTIONS)
    assert len(TOOL_FUNCTIONS) == 30


def _read_only_hint(tool) -> bool | None:
    annotations = tool.annotations
    if annotations is None:
        return None
    if isinstance(annotations, dict):
        return annotations.get("readOnlyHint")
    return getattr(annotations, "readOnlyHint", getattr(annotations, "read_only_hint", None))


def test_tool_annotations():
    tools = {tool.name: tool for tool in asyncio.run(mcp.list_tools())}
    assert _read_only_hint(tools["search_legislation"]) is True
    assert _read_only_hint(tools["search_cases"]) is True
    assert _read_only_hint(tools["sync_doj"]) is False


def test_public_routes_and_schema(http_db, tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        assert client.get("/healthz").json()["status"] == "ok"
        meta = client.get("/api/meta").json()
        assert meta["auth"] == "anonymous"
        assert meta["endpoints"]["mcp"].endswith("/mcp")
        assert meta["disclaimer"]

        index = client.get("/")
        assert index.status_code == 200
        assert "text/html" in index.headers["content-type"]
        assert "HK Criminal Law" in index.text
        assert "Content-Security-Policy" in index.headers
        assert client.get("/manifest.webmanifest").json()["display"] == "standalone"
        assert client.get("/icon.svg").status_code == 200

        tools = client.get("/api/tools").json()["tools"]
        names = {item["name"] for item in tools}
        assert "search_legislation" in names
        assert "sync_doj" not in names
        assert len(tools) == 29

        openai = client.get("/api/tools?format=openai").json()["tools"]
        assert openai[0]["type"] == "function"
        gemini = client.get("/api/tools?format=gemini").json()["functionDeclarations"]
        assert "name" in gemini[0]
        anthropic = client.get("/api/tools?format=anthropic").json()["tools"]
        assert "input_schema" in anthropic[0]

        spec = client.get("/openapi.json").json()
        assert spec["openapi"] == "3.0.3"
        assert "/api/search_legislation" in spec["paths"]
        assert len(spec["paths"]) == 29
        core = client.get("/openapi-core.json").json()
        assert len(core["paths"]) == len(CORE_TOOLS)


def test_rest_tool_calls(http_db, tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/api/search_legislation", json={"query": "bail conditions", "lang": "en"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] >= 1
        assert body["disclaimer"]

        citation = body["results"][0]["citation"]
        assert "Cap. 999" in citation
        section = client.post(
            "/api/get_section", json={"cap": "999", "section": "9"}
        ).json()
        assert section["found"] is True
        assert "admitted to bail" in section["text"]

        generic = client.post(
            "/api/call",
            json={"tool": "get_section", "arguments": {"cap": "999", "section": "9"}},
        )
        assert generic.status_code == 200
        assert generic.json()["found"] is True

        assert client.post("/api/corpus_status").status_code == 200
        assert client.post("/api/corpus_status", json=[]).status_code == 400
        assert client.post("/api/get_section", json={}).status_code == 400
        assert (
            client.post(
                "/api/search_legislation", json={"query": 5}
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/search_legislation", json={"query": "bail", "limit": "many"}
            ).status_code
            == 400
        )
        assert client.post("/api/nope", json={}).status_code == 404
        assert (
            client.post(
                "/api/call", json={"tool": "nope", "arguments": {}}
            ).status_code
            == 404
        )


def test_remote_status_redacts_operator_details(http_db, tmp_path, monkeypatch):
    monkeypatch.setenv("HK_LAW_CASE_PERMISSION_REF", "SECRET-REF")
    monkeypatch.setenv("HK_LAW_CASE_SOURCE_URL", "https://private.example/endpoint")
    monkeypatch.setenv("HK_LAW_CASE_IMPORT_DIR", "/srv/secret/judgments")
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        status = client.post("/api/sync_status", json={}).json()
        for key in (
            "case_import_dir",
            "case_citations_file",
            "case_source_url",
            "database",
        ):
            assert key not in status
        assert status["permission_configured"] is True

        corpus = client.post("/api/corpus_status", json={}).json()["corpus"]
        assert "case_source_url" not in corpus
        assert "case_import_dir" not in corpus
        assert "database" not in corpus

        # The same wrapper backs the remote MCP tool.
        wrapped = app.state.remote_tools["sync_status"]()
        assert "case_source_url" not in wrapped
        assert "case_import_dir" not in wrapped


def test_one_click_connect_and_open_oauth(http_db, tmp_path):
    app = create_app(
        _settings(
            tmp_path,
            public_url="http://127.0.0.1:8765",
            allow_anonymous=True,
        )
    )
    with TestClient(app) as client:
        meta = client.get("/api/meta").json()
        assert meta["oauth"] is True
        assert meta["oauth_open"] is True
        assert meta["auth_required"] is False
        assert meta["open_access_token"] == "open-access"

        page = client.get("/connect")
        assert page.status_code == 200
        assert "Add to Claude" in page.text
        assert "Add to ChatGPT" in page.text
        assert "Open Gemini connectors" in page.text
        assert "DeepSeek Harness" in page.text

        manifest = client.get("/server.json").json()
        assert manifest["remotes"][0]["type"] == "streamable-http"
        assert manifest["remotes"][0]["url"].endswith("/mcp")
        assert (
            client.get("/.well-known/mcp/server.json").status_code == 200
        )

        script = client.get("/connect/dsh.sh")
        assert script.status_code == 200
        assert "/mcp" in script.text
        assert "open-access" in script.text
        assert "HK_LAW_KEY" not in script.text

        # A header-only harness can use the non-secret open-access token.
        _initialize(client, "open-access")

        registration = {
            "client_name": "One Click",
            "redirect_uris": ["http://127.0.0.1:9999/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        }
        response = client.post("/register", json=registration)
        assert response.status_code == 201, response.text
        client_id = response.json()["client_id"]

        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        params = {
            "client_id": client_id,
            "redirect_uri": "http://127.0.0.1:9999/callback",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "one-click",
            "scope": "hk-law",
        }
        # Open OAuth auto-approves: no consent page, straight back to the client.
        response = client.get("/authorize", params=params, follow_redirects=False)
        assert response.status_code == 302
        location = response.headers["location"]
        assert location.startswith("http://127.0.0.1:9999/callback")
        query = parse_qs(urlparse(location).query)
        assert query["state"] == ["one-click"]
        code = query["code"][0]

        token_response = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1:9999/callback",
            },
        )
        assert token_response.status_code == 200, token_response.text
        _initialize(client, token_response.json()["access_token"])


def test_connect_page_never_exposes_the_key(http_db, tmp_path):
    secret = "do-not-render-this-key"
    app = create_app(_settings(tmp_path, access_keys=(secret,)))
    with TestClient(app) as client:
        page = client.get("/connect")
        assert page.status_code == 200
        assert "Add to Claude" in page.text
        assert secret not in page.text
        script = client.get("/connect/dsh.sh")
        assert script.status_code == 200
        assert secret not in script.text
        assert "HK_LAW_KEY" in script.text


def test_key_auth(http_db, tmp_path):
    app = create_app(_settings(tmp_path, access_keys=("correct horse",)))
    with TestClient(app) as client:
        assert client.get("/api/meta").status_code == 200
        assert client.post("/api/corpus_status", json={}).status_code == 401
        assert (
            client.post(
                "/api/corpus_status",
                json={},
                headers={"Authorization": "Bearer wrong"},
            ).status_code
            == 401
        )
        ok = client.post(
            "/api/corpus_status",
            json={},
            headers={"Authorization": "Bearer correct horse"},
        )
        assert ok.status_code == 200
        assert ok.json()["status"] == "ok"

        assert client.post("/mcp", json=INIT, headers=MCP_HEADERS).status_code == 401
        _initialize(client, "correct horse")

        # X-API-Key is accepted for simple harnesses that cannot set Authorization.
        assert (
            client.post(
                "/api/corpus_status", json={}, headers={"X-API-Key": "correct horse"}
            ).status_code
            == 200
        )


def test_oauth_flow_and_refresh(http_db, tmp_path):
    key = "operator-secret"
    app = create_app(
        _settings(
            tmp_path,
            access_keys=(key,),
            public_url="http://127.0.0.1:8765",
            allowed_hosts=("testserver",),
        )
    )
    with TestClient(app) as client:
        assert client.get("/api/meta").json()["auth"] == "oauth"
        assert (
            client.get("/.well-known/oauth-authorization-server").status_code == 200
        )
        # MCP 1.x serves the resource metadata without the /mcp suffix.
        assert any(
            client.get(path).status_code == 200
            for path in (
                "/.well-known/oauth-protected-resource/mcp",
                "/.well-known/oauth-protected-resource",
            )
        )

        registration = {
            "client_name": "Claude",
            "redirect_uris": ["http://127.0.0.1:9999/callback"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "hk-law",
        }
        response = client.post("/register", json=registration)
        assert response.status_code == 201, response.text
        client_info = response.json()
        client_id = client_info["client_id"]

        verifier = secrets.token_urlsafe(48)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        params = {
            "client_id": client_id,
            "redirect_uri": "http://127.0.0.1:9999/callback",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": "state-123",
            "scope": "hk-law",
        }
        response = client.get("/authorize", params=params, follow_redirects=False)
        assert response.status_code == 302
        location = response.headers["location"]
        request_id = parse_qs(urlparse(location).query)["request"][0]

        consent = client.get("/oauth/consent", params={"request": request_id})
        assert consent.status_code == 200
        assert "Authorise access" in consent.text

        # A wrong key must not consume the pending request.
        wrong = client.post(
            "/oauth/consent", data={"request": request_id, "key": "wrong"}
        )
        assert wrong.status_code == 401

        approved = client.post(
            "/oauth/consent",
            data={"request": request_id, "key": key},
            follow_redirects=False,
        )
        assert approved.status_code == 302
        redirect = approved.headers["location"]
        query = parse_qs(urlparse(redirect).query)
        assert query["state"] == ["state-123"]
        code = query["code"][0]

        token_response = client.post(
            "/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "client_id": client_id,
                "redirect_uri": "http://127.0.0.1:9999/callback",
            },
        )
        assert token_response.status_code == 200, token_response.text
        tokens = token_response.json()
        assert tokens["token_type"] == "Bearer"
        assert tokens["refresh_token"]

        access = tokens["access_token"]
        _initialize(client, access)
        assert (
            client.post(
                "/api/corpus_status", json={}, headers={"Authorization": f"Bearer {access}"}
            ).status_code
            == 200
        )

        refreshed = client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": client_id,
            },
        )
        assert refreshed.status_code == 200, refreshed.text
        new_access = refreshed.json()["access_token"]
        assert new_access != access

        reused = client.post(
            "/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": tokens["refresh_token"],
                "client_id": client_id,
            },
        )
        assert reused.status_code == 400


def test_static_key_also_works_in_oauth_mode(http_db, tmp_path):
    app = create_app(
        _settings(
            tmp_path,
            access_keys=("operator-secret",),
            public_url="http://127.0.0.1:8765",
        )
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/corpus_status",
            json={},
            headers={"Authorization": "Bearer operator-secret"},
        )
        assert response.status_code == 200
        _initialize(client, "operator-secret")


def test_rate_limit(http_db, tmp_path):
    app = create_app(_settings(tmp_path, rate_limit=2, rate_window=60))
    with TestClient(app) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/healthz").status_code == 200
        limited = client.get("/healthz")
        assert limited.status_code == 429
        assert limited.headers["Retry-After"] == "60"


def test_mcp_json_response_mode(http_db, tmp_path):
    app = create_app(_settings(tmp_path, json_response=True))
    with TestClient(app) as client:
        response = client.post("/mcp", json=INIT, headers=MCP_HEADERS)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["jsonrpc"] == "2.0"


def test_transport_security_rejects_unlisted_host(http_db, tmp_path):
    app = create_app(_settings(tmp_path, allowed_hosts=("allowed.example",)))
    with TestClient(app) as client:
        response = client.post("/mcp", json=INIT, headers=MCP_HEADERS)
        assert response.status_code == 421


def test_non_loopback_bind_guard():
    with pytest.raises(ValueError, match="without authentication"):
        HTTPSettings(host="0.0.0.0").validate()
    HTTPSettings(host="0.0.0.0", access_keys=("key",)).validate()
    HTTPSettings(host="0.0.0.0", allow_anonymous=True).validate()


def test_public_url_requires_key_or_explicit_anonymous():
    with pytest.raises(ValueError, match="access key"):
        HTTPSettings(public_url="https://hk-law.example.com").validate()
    HTTPSettings(public_url="https://hk-law.example.com", allow_anonymous=True).validate()


def test_nullable_schema_sanitised():
    schema = {
        "type": "object",
        "properties": {
            "cap": {
                "anyOf": [{"type": "string"}, {"type": "null"}],
                "default": None,
                "title": "Cap",
            }
        },
    }
    cleaned = _sanitize_schema(schema)
    assert cleaned["properties"]["cap"]["type"] == "string"
    assert cleaned["properties"]["cap"]["nullable"] is True
    assert "title" not in cleaned["properties"]["cap"]


def test_sync_tool_can_be_enabled(http_db, tmp_path):
    app = create_app(_settings(tmp_path, allow_sync_tools=True))
    with TestClient(app) as client:
        names = {item["name"] for item in client.get("/api/tools").json()["tools"]}
        assert "sync_doj" in names
        assert len(names) == 30


def test_json_error_shape(http_db, tmp_path):
    app = create_app(_settings(tmp_path))
    with TestClient(app) as client:
        response = client.post(
            "/api/get_section", content=b"not json", headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400
        assert response.json()["error"] == "BadRequest"
        assert response.json()["disclaimer"]
