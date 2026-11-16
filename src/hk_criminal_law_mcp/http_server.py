"""Remote HTTP surface for the Hong Kong criminal law MCP.

One process serves four ways to use the same corpus:

* ``POST /mcp`` — MCP Streamable HTTP, for Claude, ChatGPT, Gemini, DeepSeek
  Harness and any other MCP-capable host.
* ``POST /api/<tool>`` and ``POST /api/call`` — plain JSON endpoints, for
  OpenAI/Gemini/DeepSeek function calling, custom GPT Actions, scripts and
  anything that can make an HTTPS request.
* ``GET /openapi.json`` (and ``/openapi-core.json``) — an OpenAPI schema for
  custom GPT Actions and other OpenAPI clients.
* ``GET /`` — a mobile-first web app for reading the corpus from a phone
  browser with no installation.

Authentication is optional for loopback-only use. A non-loopback bind requires
either an access key or an explicit anonymous deployment. When a public URL is
configured, the server also exposes a small OAuth 2.1 authorization server so
hosted assistants can register and connect without pasting a secret.
"""

from __future__ import annotations

import argparse
import functools
import hmac
import html
import inspect
import json
import logging
import os
import time
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import jsonschema
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from starlette.routing import Route
from starlette.types import ASGIApp, Message, Receive, Scope, Send

try:  # MCP SDK 1.x
    from mcp.server.fastmcp import FastMCP as _MCPServer
except ImportError:  # MCP SDK 2.x renamed FastMCP to MCPServer
    from mcp.server.mcpserver import MCPServer as _MCPServer

from mcp.server.auth.provider import construct_redirect_uri
from mcp.server.auth.settings import (
    AuthSettings,
    ClientRegistrationOptions,
    RevocationOptions,
)
from mcp.server.transport_security import TransportSecuritySettings

from .config import APP_NAME, DISCLAIMER, VERSION, home_dir
from .db import connect
from .hklii import CaseNotLocalError, HKLIIError
from .oauth_server import FileOAuthProvider, OPEN_ACCESS_TOKEN, SCOPE
from .server import INSTRUCTIONS, TOOL_ANNOTATIONS, TOOL_FUNCTIONS

logger = logging.getLogger(__name__)

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
MAX_RATE_BUCKETS = 10_000

ACCESS_KEY_ENV = "HK_LAW_HTTP_ACCESS_KEY"
PUBLIC_URL_ENV = "HK_LAW_HTTP_PUBLIC_URL"
ALLOW_ANONYMOUS_ENV = "HK_LAW_HTTP_ALLOW_ANONYMOUS"
ALLOWED_HOSTS_ENV = "HK_LAW_HTTP_ALLOWED_HOSTS"
ALLOWED_ORIGINS_ENV = "HK_LAW_HTTP_ALLOWED_ORIGINS"
RATE_LIMIT_ENV = "HK_LAW_HTTP_RATE_LIMIT"
RATE_WINDOW_ENV = "HK_LAW_HTTP_RATE_WINDOW"
TRUST_PROXY_ENV = "HK_LAW_HTTP_TRUST_PROXY"
STATELESS_ENV = "HK_LAW_HTTP_STATELESS"
JSON_RESPONSE_ENV = "HK_LAW_HTTP_JSON_RESPONSE"
ALLOW_SYNC_ENV = "HK_LAW_HTTP_ALLOW_SYNC"

# Tools that are useful for an interactive assistant. Operator maintenance
# tools are excluded from remote surfaces unless explicitly enabled.
SYNC_TOOLS = {"sync_doj"}

CORE_TOOLS = [
    "corpus_status",
    "sync_status",
    "search_legislation",
    "get_section",
    "statute_history",
    "search_cases",
    "get_case",
    "verify_citation",
    "verify_citations",
    "doctrine_research",
    "sentencing_research",
    "search_doj",
    "get_doj_document",
    "verify_doj",
]

PUBLIC_PATHS = {
    "/",
    "/index.html",
    "/connect",
    "/connect/",
    "/connect/dsh.sh",
    "/server.json",
    "/privacy",
    "/terms",
    "/healthz",
    "/api/meta",
    "/api/tools",
    "/openapi.json",
    "/openapi-core.json",
    "/manifest.webmanifest",
    "/icon.svg",
    "/favicon.ico",
    "/oauth/consent",
}
PUBLIC_PREFIXES = ("/.well-known/",)
AUTH_PROTOCOL_PATHS = {"/authorize", "/token", "/register", "/revoke"}


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _split_env(name: str) -> tuple[str, ...]:
    raw = os.environ.get(name, "")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class HTTPSettings:
    """Runtime settings for the remote server.

    The defaults are safe for local use. Passing an explicit instance makes the
    app easy to test without mutating process environment variables.
    """

    host: str = "127.0.0.1"
    port: int = 8765
    access_keys: tuple[str, ...] = ()
    public_url: str | None = None
    allow_anonymous: bool = False
    allowed_hosts: tuple[str, ...] = ()
    allowed_origins: tuple[str, ...] = ()
    rate_limit: int = 120
    rate_window: int = 60
    trust_proxy: bool = False
    stateless: bool = True
    json_response: bool = False
    allow_sync_tools: bool = False
    oauth_store: Path | None = None

    @classmethod
    def from_env(cls) -> "HTTPSettings":
        try:
            port = int(os.environ.get("HK_LAW_HTTP_PORT", "8765"))
        except ValueError:
            port = 8765
        try:
            rate_limit = int(os.environ.get(RATE_LIMIT_ENV, "120"))
        except ValueError:
            rate_limit = 120
        try:
            rate_window = int(os.environ.get(RATE_WINDOW_ENV, "60"))
        except ValueError:
            rate_window = 60
        return cls(
            host=os.environ.get("HK_LAW_HTTP_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=port,
            access_keys=_split_env(ACCESS_KEY_ENV),
            public_url=(os.environ.get(PUBLIC_URL_ENV, "").strip() or None),
            allow_anonymous=_env_bool(ALLOW_ANONYMOUS_ENV),
            allowed_hosts=_split_env(ALLOWED_HOSTS_ENV),
            allowed_origins=_split_env(ALLOWED_ORIGINS_ENV),
            rate_limit=rate_limit,
            rate_window=rate_window,
            trust_proxy=_env_bool(TRUST_PROXY_ENV),
            stateless=_env_bool(STATELESS_ENV, True),
            json_response=_env_bool(JSON_RESPONSE_ENV),
            allow_sync_tools=_env_bool(ALLOW_SYNC_ENV),
            oauth_store=home_dir() / "oauth_state.json",
        )

    @property
    def normalised_public_url(self) -> str | None:
        return self.public_url.rstrip("/") if self.public_url else None

    @property
    def auth_required(self) -> bool:
        return bool(self.access_keys)

    @property
    def oauth_open(self) -> bool:
        """True for a deliberately public deployment with auto-approved OAuth."""
        return bool(
            self.normalised_public_url and self.allow_anonymous and not self.access_keys
        )

    @property
    def oauth_enabled(self) -> bool:
        return bool(
            self.normalised_public_url and (self.access_keys or self.allow_anonymous)
        )

    @property
    def auth_mode(self) -> str:
        if self.oauth_enabled:
            return "oauth"
        if self.auth_required:
            return "key"
        return "anonymous"

    @property
    def base_url(self) -> str:
        return self.normalised_public_url or f"http://{self.host}:{self.port}"

    @property
    def remote_tools(self) -> dict[str, Callable[..., dict]]:
        if self.allow_sync_tools:
            return dict(TOOL_FUNCTIONS)
        return {name: fn for name, fn in TOOL_FUNCTIONS.items() if name not in SYNC_TOOLS}

    def validate(self) -> None:
        if not (0 < self.port < 65536):
            raise ValueError(f"invalid port: {self.port}")
        if self.public_url:
            parsed = urlparse(self.public_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(
                    f"{PUBLIC_URL_ENV} must be an absolute http(s) URL, got {self.public_url!r}"
                )
            if parsed.scheme != "https" and parsed.hostname not in LOOPBACK_HOSTS:
                raise ValueError(
                    f"{PUBLIC_URL_ENV} must use https unless it points at localhost"
                )
            if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                raise ValueError(
                    f"{PUBLIC_URL_ENV} must be an origin such as "
                    "https://hk-law.example.com (no path, query or fragment)"
                )
        if self.public_url and not self.auth_required and not self.allow_anonymous:
            raise ValueError(
                f"{PUBLIC_URL_ENV} is set but {ACCESS_KEY_ENV} is empty. Set an access "
                f"key, or set {ALLOW_ANONYMOUS_ENV}=1 if this is a deliberately public "
                "read-only deployment."
            )
        if self.host not in LOOPBACK_HOSTS and not self.auth_required and not self.allow_anonymous:
            raise ValueError(
                "refusing to bind "
                f"{self.host} without authentication. Set {ACCESS_KEY_ENV}, or set "
                f"{ALLOW_ANONYMOUS_ENV}=1 for a deliberately public, read-only deployment."
            )
        if self.rate_limit < 0 or self.rate_window < 1:
            raise ValueError("rate limit must be >= 0 and the window >= 1 second")


# ---------------------------------------------------------------------------
# Authentication / middleware
# ---------------------------------------------------------------------------


async def _key_or_token(
    token: str,
    settings: HTTPSettings,
    provider: FileOAuthProvider | None,
) -> bool:
    if provider is not None:
        return await provider.load_access_token(token) is not None
    supplied = token.strip().encode("utf-8")
    matched = False
    for key in settings.access_keys:
        if hmac.compare_digest(supplied, key.encode("utf-8")):
            matched = True
    return matched


def _bearer_token(scope: Scope) -> str | None:
    headers = Headers(scope=scope)
    value = headers.get("authorization", "")
    if value.lower().startswith("bearer "):
        candidate = value[7:].strip()
        return candidate or None
    # Some simple harnesses can only add a custom header.
    value = headers.get("x-api-key", "").strip()
    return value or None


class BearerAuthMiddleware:
    """Protect API and (in key-only mode) MCP routes."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: HTTPSettings,
        provider: FileOAuthProvider | None,
    ) -> None:
        self.app = app
        self.settings = settings
        self.provider = provider

    def _is_public(self, path: str, method: str) -> bool:
        if not self.settings.auth_required:
            return True
        if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
            return True
        if self.settings.oauth_enabled and (path in AUTH_PROTOCOL_PATHS or path.startswith("/.well-known/")):
            return True
        if self.settings.oauth_enabled and path == "/mcp":
            # The MCP SDK's bearer middleware handles this route with the
            # OAuth resource-metadata challenge.
            return True
        return False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._is_public(scope["path"], scope.get("method", "GET")):
            await self.app(scope, receive, send)
            return
        token = _bearer_token(scope)
        if token and await _key_or_token(token, self.settings, self.provider):
            await self.app(scope, receive, send)
            return
        payload = {
            "error": "unauthorized",
            "error_description": (
                "A bearer token is required. Send 'Authorization: Bearer <access key>' "
                "or connect with OAuth."
            ),
        }
        response = JSONResponse(
            payload,
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer realm="hk-criminal-law"'},
        )
        await response(scope, receive, send)


class RateLimitMiddleware:
    """Simple per-client fixed-window limit.

    This protects the upstream HKLII/DOJ services and the SQLite corpus from a
    runaway agent. It is intentionally in-process; run one worker or move the
    limit to the reverse proxy if you scale out.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        limit: int,
        window: int,
        trust_proxy: bool,
    ) -> None:
        self.app = app
        self.limit = limit
        self.window = max(1, window)
        self.trust_proxy = trust_proxy
        self._buckets: dict[str, tuple[float, int]] = {}

    def _client(self, scope: Scope) -> str:
        if self.trust_proxy:
            headers = Headers(scope=scope)
            forwarded = headers.get("x-forwarded-for", "")
            if forwarded:
                return forwarded.split(",")[0].strip()
        client = scope.get("client")
        return client[0] if client else "unknown"

    def _allowed(self, key: str) -> bool:
        now = time.monotonic()
        start, count = self._buckets.get(key, (now, 0))
        if now - start >= self.window:
            start, count = now, 0
        count += 1
        self._buckets[key] = (start, count)
        if len(self._buckets) > MAX_RATE_BUCKETS:
            cutoff = now - self.window
            self._buckets = {
                bucket: value for bucket, value in self._buckets.items() if value[0] >= cutoff
            }
        return count <= self.limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.limit <= 0:
            await self.app(scope, receive, send)
            return
        if not self._allowed(self._client(scope)):
            response = JSONResponse(
                {
                    "error": "rate_limited",
                    "error_description": (
                        f"Too many requests. Limit: {self.limit} per {self.window}s. "
                        "Retry shortly."
                    ),
                },
                status_code=429,
                headers={"Retry-After": str(self.window)},
            )
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    _CSP = (
        "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; "
        "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    )

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault("X-Frame-Options", "DENY")
                content_type = headers.get("content-type", "")
                if content_type.startswith("text/html"):
                    headers.setdefault("Content-Security-Policy", self._CSP)
                if scope["path"] in {"/authorize", "/token", "/register", "/oauth/consent"}:
                    headers.setdefault("Cache-Control", "no-store")
                    headers.setdefault("Pragma", "no-cache")
            await send(message)

        await self.app(scope, receive, send_wrapper)


# ---------------------------------------------------------------------------
# Tool invocation and schemas
# ---------------------------------------------------------------------------


class BadRequest(Exception):
    pass


class UnknownTool(Exception):
    pass


_PRIVATE_STATUS_KEYS = {
    "case_import_dir",
    "case_citations_file",
    "case_source_url",
    "database",  # absolute SQLite path from db.stats()
}
_PRIVATE_ROW_KEYS = {"permission_ref", "base_url"}


def _redact_status(payload: dict) -> dict:
    """Remove operator-only details from a status payload.

    ``sync_status`` is designed for the operator's terminal. On a remote
    endpoint, the permission reference, private source URL and filesystem paths
    are not needed by a research client and must not leak.
    """
    cleaned = dict(payload)
    for key in _PRIVATE_STATUS_KEYS:
        cleaned.pop(key, None)
    rows = cleaned.get("case_source_rows")
    if isinstance(rows, list):
        cleaned["case_source_rows"] = [
            {key: value for key, value in row.items() if key not in _PRIVATE_ROW_KEYS}
            if isinstance(row, dict)
            else row
            for row in rows
        ]
    runs = cleaned.get("recent_syncs")
    if isinstance(runs, list):
        cleaned["recent_syncs"] = [
            {key: value for key, value in run.items() if key != "error"}
            if isinstance(run, dict)
            else run
            for run in runs
        ]
    return cleaned


def _remote_safe(name: str, fn: Callable[..., dict]) -> Callable[..., dict]:
    if name not in {"corpus_status", "sync_status"}:
        return fn

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> dict:
        result = fn(*args, **kwargs)
        if name == "corpus_status" and isinstance(result.get("corpus"), dict):
            result["corpus"] = _redact_status(result["corpus"])
        elif name == "sync_status":
            result = _redact_status(result)
        return result

    return wrapper


def _tool_schema(tool: Any) -> dict:
    schema = getattr(tool, "inputSchema", None)
    if schema is None:
        schema = getattr(tool, "input_schema", None)
    if schema is None and hasattr(tool, "model_dump"):
        schema = tool.model_dump(by_alias=True).get("inputSchema")
    return schema or {"type": "object", "properties": {}}


def _tool_description(tool: Any) -> str:
    return (getattr(tool, "description", None) or "").strip()


def _read_only(name: str) -> bool | None:
    annotations = TOOL_ANNOTATIONS.get(name)
    if annotations is None:
        return None
    return getattr(
        annotations, "read_only_hint", getattr(annotations, "readOnlyHint", None)
    )


async def _tool_parameters(request: Request, name: str) -> dict | None:
    for spec in await _list_specs(request):
        if spec["name"] == name:
            return spec["parameters"]
    return None


async def _list_specs(request: Request) -> list[dict]:
    cached = getattr(request.app.state, "tool_specs", None)
    if cached is not None:
        return cached
    http_mcp = request.app.state.http_mcp
    tools = await http_mcp.list_tools()
    allowed = set(request.app.state.remote_tools)
    specs = [
        {
            "name": tool.name,
            "description": _tool_description(tool),
            "parameters": _tool_schema(tool),
            "read_only": _read_only(tool.name),
        }
        for tool in tools
        if tool.name in allowed
    ]
    request.app.state.tool_specs = specs
    return specs


def _sanitize_schema(value: Any) -> Any:
    """Make MCP's JSON Schema acceptable to OpenAPI 3.0 and Gemini.

    FastMCP expresses ``x: str | None`` as ``anyOf: [{type: string}, {type:
    null}]``. OpenAPI 3.0 and Gemini's function schema prefer ``nullable``.
    """
    if isinstance(value, list):
        return [_sanitize_schema(item) for item in value]
    if not isinstance(value, dict):
        return value
    any_of = value.get("anyOf")
    if isinstance(any_of, list) and len(any_of) == 2:
        non_null = [
            item
            for item in any_of
            if not (isinstance(item, dict) and item.get("type") == "null")
        ]
        has_null = any(
            isinstance(item, dict) and item.get("type") == "null" for item in any_of
        )
        if has_null and len(non_null) == 1:
            merged = _sanitize_schema(non_null[0])
            if not isinstance(merged, dict):
                return value
            merged["nullable"] = True
            for key, val in value.items():
                if key != "anyOf":
                    merged.setdefault(key, val)
            merged.pop("title", None)
            return merged
    cleaned = {key: _sanitize_schema(val) for key, val in value.items()}
    cleaned.pop("title", None)
    return cleaned


def _operation_id(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


def _openapi_spec(request: Request, specs: list[dict]) -> dict:
    settings: HTTPSettings = request.app.state.settings
    public_url = settings.normalised_public_url
    paths: dict[str, Any] = {}
    for spec in specs:
        schema = _sanitize_schema(spec["parameters"])
        required = bool(schema.get("required"))
        operation: dict[str, Any] = {
            "operationId": _operation_id(spec["name"]),
            "summary": (spec["description"].splitlines() or [spec["name"]])[0][:120],
            "description": spec["description"] or spec["name"],
            "requestBody": {
                "required": required,
                "content": {"application/json": {"schema": schema}},
            },
            "responses": {
                "200": {
                    "description": "Tool result as JSON, including provenance and the disclaimer.",
                    "content": {"application/json": {"schema": {"type": "object"}}},
                },
                "400": {"description": "Invalid arguments."},
                "429": {"description": "Rate limited."},
                "500": {"description": "Tool failure."},
            },
        }
        if settings.auth_required:
            operation["responses"]["401"] = {"description": "Missing or invalid bearer token."}
            operation["security"] = [{"bearerAuth": []}]
        paths[f"/api/{spec['name']}"] = {"post": operation}

    spec: dict[str, Any] = {
        "openapi": "3.0.3",
        "info": {
            "title": "Hong Kong Criminal Law Research API",
            "version": VERSION,
            "description": (
                "Citation-aware Hong Kong legislation, judgment and DOJ policy retrieval. "
                "Every result carries provenance and a disclaimer. This is a retrieval aid, "
                "not legal advice."
            ),
        },
        "servers": [{"url": public_url or "/"}],
        "paths": paths,
    }
    if settings.auth_required:
        spec["components"] = {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "The deployment access key, or an OAuth access token.",
                }
            }
        }
        spec["security"] = [{"bearerAuth": []}]
    return spec


async def _execute_tool(
    name: str,
    arguments: dict[str, Any],
    remote_tools: dict[str, Callable[..., dict]],
    parameters: dict | None = None,
) -> dict:
    fn = remote_tools.get(name)
    if fn is None:
        raise UnknownTool(name)
    if not isinstance(arguments, dict):
        raise BadRequest("arguments must be a JSON object")
    if parameters:
        try:
            jsonschema.validate(arguments, parameters)
        except jsonschema.ValidationError as exc:
            raise BadRequest(f"invalid arguments for {name}: {exc.message}") from exc
    signature = inspect.signature(fn)
    try:
        bound = signature.bind(**arguments)
    except TypeError as exc:
        raise BadRequest(str(exc)) from exc
    bound.apply_defaults()
    if inspect.iscoroutinefunction(fn):
        result = await fn(*bound.args, **bound.kwargs)
    else:
        result = await run_in_threadpool(fn, *bound.args, **bound.kwargs)
    if not isinstance(result, dict):
        raise RuntimeError(f"tool {name} returned a non-object result")
    result.setdefault("disclaimer", DISCLAIMER)
    return result


def _error_payload(exc: Exception, status: int) -> JSONResponse:
    message = str(exc) or exc.__class__.__name__
    if isinstance(exc, (CaseNotLocalError, HKLIIError)):
        status = 422
    elif isinstance(exc, (ValueError, BadRequest)):
        status = 400
    return JSONResponse(
        {
            "error": exc.__class__.__name__,
            "error_description": message,
            "disclaimer": DISCLAIMER,
        },
        status_code=status,
    )


# ---------------------------------------------------------------------------
# Routes: meta, health, API, OpenAPI, web app
# ---------------------------------------------------------------------------


def _index_html() -> str:
    cached = getattr(_index_html, "_cache", None)
    if cached is not None:
        return cached
    try:
        text = resources.files("hk_criminal_law_mcp").joinpath("web/index.html").read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise RuntimeError("packaged web/index.html is missing; reinstall the package") from exc
    _index_html._cache = text  # type: ignore[attr-defined]
    return text


async def _index(request: Request) -> Response:
    return HTMLResponse(
        _index_html(),
        headers={"Cache-Control": "no-cache"},
    )


async def _healthz(request: Request) -> Response:
    settings: HTTPSettings = request.app.state.settings
    db_ok = False
    try:
        conn = connect()
        try:
            conn.execute("SELECT 1").fetchone()
            db_ok = True
        finally:
            conn.close()
    except Exception as exc:  # a health check must not raise
        logger.warning("database health check failed: %s", exc)
    return JSONResponse(
        {
            "status": "ok" if db_ok else "degraded",
            "version": VERSION,
            "database": db_ok,
            "auth": settings.auth_mode,
            "oauth_open": settings.oauth_open,
            "tools": len(settings.remote_tools),
        }
    )


def _request_base(request: Request) -> str:
    settings: HTTPSettings = request.app.state.settings
    base = settings.normalised_public_url
    if not base:
        host = request.headers.get("host")
        base = f"{request.url.scheme}://{host}" if host else settings.base_url
    return base.rstrip("/")


async def _meta(request: Request) -> Response:
    settings: HTTPSettings = request.app.state.settings
    base = _request_base(request)
    return JSONResponse(
        {
            "name": APP_NAME,
            "version": VERSION,
            "description": (
                "Hong Kong criminal law and defence research: legislation, judgments and "
                "DOJ policy with citation verification."
            ),
            "auth": settings.auth_mode,
            "auth_required": settings.auth_required,
            "oauth": settings.oauth_enabled,
            "oauth_open": settings.oauth_open,
            "open_access_token": OPEN_ACCESS_TOKEN if settings.oauth_open else None,
            "endpoints": {
                "web_app": f"{base}/",
                "connect": f"{base}/connect",
                "mcp": f"{base}/mcp",
                "rest": f"{base}/api/",
                "tools": f"{base}/api/tools",
                "openapi": f"{base}/openapi.json",
                "openapi_core": f"{base}/openapi-core.json",
                "server_json": f"{base}/server.json",
                "health": f"{base}/healthz",
            },
            "tools": len(settings.remote_tools),
            "disclaimer": DISCLAIMER,
        }
    )


async def _api_tools(request: Request) -> Response:
    specs = await _list_specs(request)
    fmt = (request.query_params.get("format") or "").lower()
    settings: HTTPSettings = request.app.state.settings
    if fmt in {"openai", "deepseek"}:
        payload = {
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": spec["name"],
                        "description": spec["description"],
                        "parameters": _sanitize_schema(spec["parameters"]),
                    },
                }
                for spec in specs
            ]
        }
    elif fmt == "gemini":
        payload = {
            "functionDeclarations": [
                {
                    "name": spec["name"],
                    "description": spec["description"],
                    "parameters": _sanitize_schema(spec["parameters"]),
                }
                for spec in specs
            ]
        }
    elif fmt in {"anthropic", "claude"}:
        payload = {
            "tools": [
                {
                    "name": spec["name"],
                    "description": spec["description"],
                    "input_schema": spec["parameters"],
                }
                for spec in specs
            ]
        }
    else:
        payload = {
            "name": APP_NAME,
            "version": VERSION,
            "auth": settings.auth_mode,
            "tools": specs,
            "usage": (
                "POST /api/<tool> with the tool arguments as the JSON body, or "
                "POST /api/call with {\"tool\": \"<name>\", \"arguments\": {...}}. "
                "Add ?format=openai, deepseek, gemini or anthropic for a "
                "function-calling definition list."
            ),
        }
    return JSONResponse(payload)


async def _json_body(request: Request) -> dict:
    raw = await request.body()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise BadRequest("request body must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise BadRequest("request body must be a JSON object")
    return payload


async def _api_call(request: Request) -> Response:
    payload = await _json_body(request)
    name = payload.get("tool")
    arguments = payload.get("arguments") or {}
    if not isinstance(name, str):
        raise BadRequest("'tool' must be a string")
    try:
        result = await _execute_tool(
            name,
            arguments,
            request.app.state.remote_tools,
            await _tool_parameters(request, name),
        )
    except UnknownTool:
        return JSONResponse(
            {"error": "unknown_tool", "error_description": f"unknown tool: {name}"},
            status_code=404,
        )
    except BadRequest as exc:
        return _error_payload(exc, 400)
    except Exception as exc:
        logger.exception("tool %s failed", name)
        return _error_payload(exc, 500)
    return JSONResponse(result)


async def _api_tool(request: Request) -> Response:
    name = request.path_params["tool"]
    if name not in request.app.state.remote_tools:
        return JSONResponse(
            {
                "error": "unknown_tool",
                "error_description": f"unknown tool: {name}",
                "available": sorted(request.app.state.remote_tools),
            },
            status_code=404,
        )
    payload = await _json_body(request)
    try:
        result = await _execute_tool(
            name,
            payload,
            request.app.state.remote_tools,
            await _tool_parameters(request, name),
        )
    except BadRequest as exc:
        return _error_payload(exc, 400)
    except Exception as exc:
        logger.exception("tool %s failed", name)
        return _error_payload(exc, 500)
    return JSONResponse(result)


async def _openapi(request: Request) -> Response:
    specs = await _list_specs(request)
    return JSONResponse(_openapi_spec(request, specs))


async def _openapi_core(request: Request) -> Response:
    specs = [
        spec
        for spec in await _list_specs(request)
        if spec["name"] in CORE_TOOLS
    ]
    return JSONResponse(_openapi_spec(request, specs))


async def _manifest(request: Request) -> Response:
    return JSONResponse(
        {
            "name": "HK Criminal Law",
            "short_name": "HK Law",
            "description": "Hong Kong criminal law and defence research",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "background_color": "#f7f5f0",
            "theme_color": "#7a1f2b",
            "icons": [
                {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}
            ],
        },
        media_type="application/manifest+json",
    )


_ICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#7a1f2b"/>
<path d="M18 16h28v5H18zM20 24h24v3H20z" fill="#f7f5f0"/>
<path d="M32 27v21M25 48h14" stroke="#f7f5f0" stroke-width="3" stroke-linecap="round"/>
<path d="M22 31l-6 10h12l-6-10zM42 31l-6 10h12l-6-10z" fill="none" stroke="#f7f5f0" stroke-width="2.5" stroke-linejoin="round"/>
</svg>"""


async def _icon(request: Request) -> Response:
    return Response(
        _ICON,
        media_type="image/svg+xml",
        headers={"Cache-Control": "public, max-age=86400"},
    )


_CONSENT_STYLE = """
:root{color-scheme:light dark}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
background:#f7f5f0;color:#1d1b18;font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
padding:24px}
main{width:100%;max-width:430px;background:#fff;border:1px solid #e3ddd2;border-radius:16px;
padding:28px;box-shadow:0 10px 40px rgba(0,0,0,.06)}
h1{font:600 22px/1.25 Georgia,"Noto Serif TC",serif;margin:0 0 6px}
p{color:#5c554a;margin:12px 0}
code{background:#f2ede4;border-radius:5px;padding:2px 6px;font-size:14px;overflow-wrap:anywhere}
label{display:block;font-weight:600;margin:20px 0 6px}
input{width:100%;padding:12px 14px;font-size:16px;border:1px solid #cfc6b8;border-radius:10px;background:#fff;color:inherit}
button{width:100%;margin-top:18px;padding:13px;font-size:16px;font-weight:600;color:#fff;
background:#7a1f2b;border:0;border-radius:10px}
.error{background:#fbeaea;color:#7a1f2b;border-radius:8px;padding:10px 12px}
.note{font-size:13px;color:#777064}
@media(prefers-color-scheme:dark){
body{background:#121212;color:#eee}
main{background:#1c1b19;border-color:#33302b}
p{color:#b8b0a3}
code{background:#2a2723}
input{background:#242220;border-color:#49443d}
.note{color:#948b7d}
.error{background:#3a1d1f;color:#f0b8bc}
}
"""


def _consent_page(
    *,
    client_name: str,
    redirect_host: str,
    request_id: str,
    error: str | None = None,
) -> str:
    error_html = f'<p class="error">{html.escape(error)}</p>' if error else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Authorise access · HK Criminal Law</title>
<style>{_CONSENT_STYLE}</style></head>
<body><main>
<h1>Authorise access</h1>
<p><strong>{html.escape(client_name)}</strong> wants to connect to this Hong Kong criminal law research server.</p>
<p>It will be able to read legislation, judgments and DOJ policy through <code>{html.escape(redirect_host)}</code>. It will not receive your access key.</p>
{error_html}
<form method="post" action="/oauth/consent">
<input type="hidden" name="request" value="{html.escape(request_id)}">
<label for="key">Deployment access key</label>
<input id="key" name="key" type="password" autocomplete="current-password" required autofocus>
<button type="submit">Approve connection</button>
</form>
<p class="note">Only approve a connection you started. This server is a retrieval aid, not legal advice.</p>
</main></body></html>"""


async def _consent(request: Request) -> Response:
    provider: FileOAuthProvider | None = request.app.state.oauth_provider
    if provider is None:
        return HTMLResponse(
            "<h1>OAuth is not enabled</h1><p>Set HK_LAW_HTTP_PUBLIC_URL and "
            "HK_LAW_HTTP_ACCESS_KEY to enable hosted-assistant connections.</p>",
            status_code=404,
        )
    if provider.open_access:
        return HTMLResponse(
            "<h1>Open access</h1><p>This deployment does not require approval. "
            "Start the connection again from your assistant.</p>",
            status_code=200,
            headers={"Cache-Control": "no-store"},
        )
    if request.method == "GET":
        request_id = request.query_params.get("request", "")
        pending = provider.pending_request(request_id)
        if pending is None:
            return HTMLResponse(
                _consent_page(
                    client_name="Unknown client",
                    redirect_host="an unknown address",
                    request_id="",
                    error="This authorisation request has expired. Return to your assistant and try again.",
                ),
                status_code=400,
            )
        client = await provider.get_client(pending["client_id"])
        params = pending["params"]
        return HTMLResponse(
            _consent_page(
                client_name=(client.client_name if client and client.client_name else "An application"),
                redirect_host=urlparse(str(params.redirect_uri)).netloc or str(params.redirect_uri),
                request_id=request_id,
            ),
            headers={"Cache-Control": "no-store"},
        )

    form = await request.form()
    request_id = str(form.get("request", ""))
    key = str(form.get("key", ""))
    pending = provider.pending_request(request_id)
    if pending is None:
        return HTMLResponse(
            _consent_page(
                client_name="Unknown client",
                redirect_host="an unknown address",
                request_id="",
                error="This authorisation request has expired. Return to your assistant and try again.",
            ),
            status_code=400,
        )
    client = await provider.get_client(pending["client_id"])
    client_name = client.client_name if client and client.client_name else "An application"
    params = pending["params"]
    if not provider.key_matches(key):
        return HTMLResponse(
            _consent_page(
                client_name=client_name,
                redirect_host=urlparse(str(params.redirect_uri)).netloc or str(params.redirect_uri),
                request_id=request_id,
                error="That access key is not correct.",
            ),
            status_code=401,
            headers={"Cache-Control": "no-store"},
        )
    completed = provider.complete_consent(request_id)
    if completed is None:
        return HTMLResponse("This authorisation request has expired.", status_code=400)
    record, params, _client_id = completed
    target = construct_redirect_uri(
        str(params.redirect_uri),
        code=record.code,
        state=params.state,
    )
    return RedirectResponse(target, status_code=302, headers={"Cache-Control": "no-store"})


def _connect_html() -> str:
    cached = getattr(_connect_html, "_cache", None)
    if cached is not None:
        return cached
    try:
        text = resources.files("hk_criminal_law_mcp").joinpath("web/connect.html").read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError) as exc:
        raise RuntimeError("packaged web/connect.html is missing; reinstall the package") from exc
    _connect_html._cache = text  # type: ignore[attr-defined]
    return text


async def _connect(request: Request) -> Response:
    return HTMLResponse(_connect_html(), headers={"Cache-Control": "no-cache"})


async def _server_json(request: Request) -> Response:
    """MCP Registry manifest for one-click / universal installers."""
    settings: HTTPSettings = request.app.state.settings
    base = _request_base(request)
    remote: dict[str, Any] = {
        "type": "streamable-http",
        "url": f"{base}/mcp",
    }
    if settings.auth_required and not settings.oauth_open:
        remote["headers"] = [
            {
                "name": "Authorization",
                "description": "Bearer access key; OAuth clients can omit this.",
                "isSecret": True,
            }
        ]
    payload = {
        "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
        "name": "io.github.helloworld20484096/hk-criminal-law",
        "title": "HK Criminal Law",
        "description": (
            "Hong Kong legislation, judgments and DOJ policy with citation verification."
        ),
        "version": VERSION,
        "remotes": [remote],
    }
    return JSONResponse(payload)


async def _connect_dsh(request: Request) -> Response:
    """A reviewed one-command installer for DeepSeek Harness."""
    settings: HTTPSettings = request.app.state.settings
    base = _request_base(request)
    mcp_url = f"{base}/mcp"

    headers = ""
    key_note = ""
    if settings.oauth_open:
        headers = (
            "        headers:\n"
            "          Authorization: Bearer open-access\n"
        )
    elif settings.auth_required:
        headers = (
            "        headers:\n"
            "          Authorization: !!js `Bearer ${process.env.HK_LAW_KEY}`\n"
        )
        key_note = (
            'echo "Set HK_LAW_KEY in the environment that starts dsh."\n'
        )

    config_block = (
        "- insert:\n"
        "    - id: mcp-hk-law\n"
        "      name: '@deepseek-ai/dsh-mcp-client'\n"
        "      config:\n"
        "        serverName: hk-law\n"
        "        transport: streamable-http\n"
        f"        url: {mcp_url}\n"
        "        failOnStartupError: true\n"
        f"{headers}"
    )
    script = f"""#!/usr/bin/env bash
# DeepSeek Harness installer for the HK Criminal Law MCP.
# Server: {mcp_url}
set -euo pipefail

CONFIG="${{HOME}}/.dsh/cordis.patch.yml"
PROFILE="${{DSH_PROFILE:-web}}"
VERSION="${{DSH_MCP_CLIENT_VERSION:-0.1.0-rc.7}}"

if ! command -v dsh >/dev/null 2>&1; then
  echo "DeepSeek Harness (dsh) was not found on PATH." >&2
  exit 1
fi

dsh plugin --profile "$PROFILE" add "@deepseek-ai/dsh-mcp-client@${{VERSION}}"
mkdir -p "$(dirname "$CONFIG")"

if grep -q "mcp-hk-law" "$CONFIG" 2>/dev/null; then
  echo "hk-law is already configured in $CONFIG"
  exit 0
fi

if [ -f "$CONFIG" ]; then
  cp "$CONFIG" "${{CONFIG}}.bak.$(date +%s)"
fi

cat >> "$CONFIG" <<'HKLAW_CONFIG'

{config_block}HKLAW_CONFIG

echo "Configured in $CONFIG"
echo "Verify: dsh --profile $PROFILE --dump-config | grep mcp-"
echo "Restart: dsh $PROFILE"
{key_note}"""
    return Response(
        script,
        media_type="text/x-shellscript; charset=utf-8",
        headers={
            "Content-Disposition": "inline; filename=connect-dsh.sh",
            "Cache-Control": "no-cache",
        },
    )


def _legal_page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · HK Criminal Law</title>
<style>{_CONSENT_STYLE}
main{{max-width:720px}}
main p, main li{{color:var(--ink);font-size:15px}}
</style></head>
<body><main>
<p><a href="/connect">← Connect</a></p>
<h1>{html.escape(title)}</h1>
{body}
<p class="note">For privacy or terms questions, contact the operator of this deployment.</p>
</main></body></html>"""


async def _privacy(request: Request) -> Response:
    return HTMLResponse(
        _legal_page(
            "Privacy",
            """
<p>This deployment is a legal-research retrieval service. It does not create
user accounts and does not set tracking cookies.</p>
<ul>
<li>The browser web app stores the optional access key and language choice in
that browser's local storage. They are not sent anywhere except this server.</li>
<li>Server and reverse-proxy logs may record IP address, user agent, timestamps
and the text of research queries. Treat research queries as confidential.</li>
<li>Queries are sent to the configured sources only when live case retrieval is
enabled. The operator of this deployment controls that setting.</li>
<li>No personal data is sold or used for advertising.</li>
</ul>
<p>The underlying legislation, DOJ policy and judgment sources have their own
terms; see the project's data-sources documentation.</p>
""",
        )
    )


async def _terms(request: Request) -> Response:
    return HTMLResponse(
        _legal_page(
            "Terms",
            """
<p>This is a research retrieval aid, not legal advice and not a citator of
record. Every provision, judgment and policy paragraph must be checked against
the official source before it is relied on.</p>
<ul>
<li>Do not use the service to redistribute bulk judgment text you are not
permitted to redistribute.</li>
<li>Respect the source terms and rate limits. Do not attempt to bypass
authentication or the rate limiter.</li>
<li>The operator may change or withdraw the service at any time. There is no
warranty of availability, accuracy or completeness.</li>
<li>By connecting a client, you authorise it to query this corpus on your
behalf.</li>
</ul>
""",
        )
    )


def _routes() -> list[Route]:
    return [
        Route("/", _index, methods=["GET"]),
        Route("/index.html", _index, methods=["GET"]),
        Route("/connect", _connect, methods=["GET"]),
        Route("/connect/", _connect, methods=["GET"]),
        Route("/connect/dsh.sh", _connect_dsh, methods=["GET"]),
        Route("/server.json", _server_json, methods=["GET"]),
        Route("/.well-known/mcp/server.json", _server_json, methods=["GET"]),
        Route("/privacy", _privacy, methods=["GET"]),
        Route("/terms", _terms, methods=["GET"]),
        Route("/healthz", _healthz, methods=["GET"]),
        Route("/api/meta", _meta, methods=["GET"]),
        Route("/api/tools", _api_tools, methods=["GET"]),
        Route("/api/call", _api_call, methods=["POST"]),
        Route("/api/{tool}", _api_tool, methods=["POST"]),
        Route("/openapi.json", _openapi, methods=["GET"]),
        Route("/openapi-core.json", _openapi_core, methods=["GET"]),
        Route("/manifest.webmanifest", _manifest, methods=["GET"]),
        Route("/icon.svg", _icon, methods=["GET"]),
        Route("/favicon.ico", _icon, methods=["GET"]),
        Route("/oauth/consent", _consent, methods=["GET", "POST"]),
    ]


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def _auth_settings(settings: HTTPSettings) -> AuthSettings:
    assert settings.normalised_public_url is not None
    public = settings.normalised_public_url
    kwargs: dict[str, Any] = {
        "issuer_url": public,
        "service_documentation_url": None,
        "resource_server_url": f"{public}/mcp",
        "required_scopes": [],
        "client_registration_options": ClientRegistrationOptions(
            enabled=True,
            # Scopes are informational here (the server enforces one operator
            # key, not per-scope permissions). Accept what a client requests
            # rather than rejecting an otherwise valid MCP client.
            valid_scopes=None,
            default_scopes=[SCOPE],
        ),
        "revocation_options": RevocationOptions(enabled=True),
    }
    if "validate_token_resource" in getattr(AuthSettings, "model_fields", {}):
        kwargs["validate_token_resource"] = False
    return AuthSettings(**kwargs)


def _transport_security(settings: HTTPSettings) -> TransportSecuritySettings | None:
    origins = list(settings.allowed_origins)
    if settings.normalised_public_url:
        parsed = urlparse(settings.normalised_public_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in origins:
            origins.append(origin)
    if settings.allowed_hosts:
        return TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=list(settings.allowed_hosts),
            allowed_origins=origins,
        )
    if settings.normalised_public_url:
        # A reverse proxy presents the public Host header to a loopback
        # listener. The SDK's automatic localhost allow-list would reject it,
        # so rely on authentication and the proxy for this deployment.
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return None


def _build_mcp(
    settings: HTTPSettings,
    provider: FileOAuthProvider | None,
    remote_tools: dict[str, Callable[..., dict]],
) -> Any:
    kwargs: dict[str, Any] = {}
    if provider is not None:
        kwargs["auth"] = _auth_settings(settings)
        kwargs["auth_server_provider"] = provider
    try:
        supported = inspect.signature(_MCPServer.__init__).parameters
    except (TypeError, ValueError):
        supported = {}
    accepts_kwargs = any(
        param.kind is inspect.Parameter.VAR_KEYWORD for param in supported.values()
    )
    unsupported = [key for key in kwargs if key not in supported and not accepts_kwargs]
    if unsupported:
        raise RuntimeError(
            "this MCP SDK build cannot configure OAuth on the HTTP transport. "
            "Upgrade the 'mcp' package (mcp>=1.10) or run in key/anonymous mode."
        )

    # MCP 1.x puts HTTP transport settings on the server, while 2.x puts them
    # on streamable_http_app(). Detect which generation we have.
    try:
        app_params = inspect.signature(_MCPServer.streamable_http_app).parameters
    except (TypeError, ValueError):
        app_params = {}
    app_accepts_kwargs = any(
        param.kind is inspect.Parameter.VAR_KEYWORD for param in app_params.values()
    )
    if not app_accepts_kwargs and "stateless_http" not in app_params:
        if accepts_kwargs:
            kwargs.update(
                stateless_http=settings.stateless,
                json_response=settings.json_response,
                streamable_http_path="/mcp",
                transport_security=_transport_security(settings),
            )
    http_mcp = _MCPServer("hk-criminal-law", instructions=INSTRUCTIONS, **kwargs)
    for name, fn in remote_tools.items():
        http_mcp.tool(annotations=TOOL_ANNOTATIONS[name])(fn)
    return http_mcp


def _streamable_app(http_mcp: Any, settings: HTTPSettings) -> Starlette:
    kwargs: dict[str, Any] = {
        "streamable_http_path": "/mcp",
        "stateless_http": settings.stateless,
        "json_response": settings.json_response,
        "transport_security": _transport_security(settings),
        "host": settings.host,
    }
    try:
        supported = inspect.signature(http_mcp.streamable_http_app).parameters
    except (TypeError, ValueError):
        supported = {}
    accepts_kwargs = any(
        param.kind is inspect.Parameter.VAR_KEYWORD for param in supported.values()
    )
    if not accepts_kwargs:
        kwargs = {key: value for key, value in kwargs.items() if key in supported}
    return http_mcp.streamable_http_app(**kwargs)


def create_app(settings: HTTPSettings | None = None) -> Starlette:
    """Build the remote application.

    The same object is a valid ASGI app for uvicorn, gunicorn or a test client.
    """
    settings = settings or HTTPSettings.from_env()
    settings.validate()

    provider: FileOAuthProvider | None = None
    if settings.oauth_enabled:
        assert settings.normalised_public_url is not None
        provider = FileOAuthProvider(
            access_keys=settings.access_keys,
            public_url=settings.normalised_public_url,
            store_path=settings.oauth_store or home_dir() / "oauth_state.json",
            open_access=settings.oauth_open,
        )

    remote_tools = {
        name: _remote_safe(name, fn) for name, fn in settings.remote_tools.items()
    }
    http_mcp = _build_mcp(settings, provider, remote_tools)
    app = _streamable_app(http_mcp, settings)
    app.router.routes.extend(_routes())
    app.state.settings = settings
    app.state.http_mcp = http_mcp
    app.state.oauth_provider = provider
    app.state.remote_tools = remote_tools
    app.state.tool_specs = None

    async def _bad_request(request: Request, exc: Exception) -> JSONResponse:
        return _error_payload(exc, 400)

    async def _unknown_tool(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            {"error": "unknown_tool", "error_description": str(exc)},
            status_code=404,
        )

    app.add_exception_handler(BadRequest, _bad_request)
    app.add_exception_handler(UnknownTool, _unknown_tool)

    app.add_middleware(
        BearerAuthMiddleware,
        settings=settings,
        provider=provider,
    )
    if settings.rate_limit:
        app.add_middleware(
            RateLimitMiddleware,
            limit=settings.rate_limit,
            window=settings.rate_window,
            trust_proxy=settings.trust_proxy,
        )
    app.add_middleware(SecurityHeadersMiddleware)
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "X-API-Key",
                "Content-Type",
                "Accept",
                "Mcp-Protocol-Version",
                "Mcp-Session-Id",
                "Last-Event-ID",
            ],
            expose_headers=["Mcp-Session-Id"],
            max_age=600,
        )
    return app


# ---------------------------------------------------------------------------
# Command line entry point
# ---------------------------------------------------------------------------


def _banner(settings: HTTPSettings) -> str:
    base = settings.base_url
    if not settings.normalised_public_url and settings.host in {"0.0.0.0", "::", "[::]"}:
        base = f"http://127.0.0.1:{settings.port}"
    lines = [
        "",
        "HK Criminal Law remote server",
        f"  Web app      {base}/",
        f"  MCP          {base}/mcp",
        f"  REST/OpenAPI {base}/api/  ·  {base}/openapi.json",
        f"  Health       {base}/healthz",
        f"  Auth         {settings.auth_mode}",
    ]
    if settings.host in {"0.0.0.0", "::", "[::]"}:
        lines.append("  Bind         all interfaces; use your public URL/domain")
    if settings.auth_mode == "anonymous":
        lines.append("  Warning      Anyone who can reach this URL can query the corpus.")
    if settings.auth_mode == "key":
        lines.append("  Clients      Send 'Authorization: Bearer <access key>'.")
    if settings.auth_mode == "oauth":
        if settings.oauth_open:
            lines.append(
                "  Open OAuth   Anyone can obtain a read-only token; no approval key."
            )
        else:
            lines.append(
                "  Clients      Connect with OAuth, or use the access key as a bearer token."
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="hk-law serve-http",
        description=(
            "Run the Hong Kong criminal law MCP over Streamable HTTP, with a JSON "
            "API, an OpenAPI schema and a mobile web app."
        ),
    )
    parser.add_argument("--host", default=os.environ.get("HK_LAW_HTTP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("HK_LAW_HTTP_PORT", "8765")))
    parser.add_argument("--access-key", default=None, help=f"shared secret (or {ACCESS_KEY_ENV})")
    parser.add_argument(
        "--public-url",
        default=None,
        help=(
            "public https:// base URL (or HK_LAW_HTTP_PUBLIC_URL). Required for "
            "OAuth; use the URL clients will connect to, without /mcp."
        ),
    )
    parser.add_argument(
        "--anonymous",
        action="store_true",
        help="allow unauthenticated access when binding a non-loopback address",
    )
    parser.add_argument(
        "--allowed-host",
        action="append",
        default=None,
        help="allowed Host header (repeatable); supports a ':*' port wildcard",
    )
    parser.add_argument(
        "--allowed-origin",
        action="append",
        default=None,
        help="allowed CORS/transport Origin (repeatable)",
    )
    parser.add_argument(
        "--rate-limit",
        type=int,
        default=int(os.environ.get(RATE_LIMIT_ENV, "120")),
        help="requests per client per window; 0 disables the limiter",
    )
    parser.add_argument("--rate-window", type=int, default=int(os.environ.get(RATE_WINDOW_ENV, "60")))
    parser.add_argument("--trust-proxy", action="store_true", help="read client IP from X-Forwarded-For")
    parser.add_argument(
        "--stateful",
        action="store_true",
        help="keep MCP sessions (default is stateless HTTP, which is easier to scale)",
    )
    parser.add_argument(
        "--json-response",
        action="store_true",
        help="return application/json instead of SSE for MCP responses",
    )
    parser.add_argument(
        "--allow-sync",
        action="store_true",
        help="expose sync_doj remotely (hidden by default)",
    )
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args(argv)

    settings = HTTPSettings(
        host=args.host,
        port=args.port,
        access_keys=(args.access_key.strip(),) if args.access_key else _split_env(ACCESS_KEY_ENV),
        public_url=args.public_url or (os.environ.get(PUBLIC_URL_ENV, "").strip() or None),
        allow_anonymous=args.anonymous or _env_bool(ALLOW_ANONYMOUS_ENV),
        allowed_hosts=tuple(args.allowed_host or _split_env(ALLOWED_HOSTS_ENV)),
        allowed_origins=tuple(args.allowed_origin or _split_env(ALLOWED_ORIGINS_ENV)),
        rate_limit=args.rate_limit,
        rate_window=args.rate_window,
        trust_proxy=args.trust_proxy or _env_bool(TRUST_PROXY_ENV),
        stateless=(not args.stateful) and _env_bool(STATELESS_ENV, True),
        json_response=args.json_response or _env_bool(JSON_RESPONSE_ENV),
        allow_sync_tools=args.allow_sync or _env_bool(ALLOW_SYNC_ENV),
        oauth_store=home_dir() / "oauth_state.json",
    )
    try:
        app = create_app(settings)
    except (ValueError, RuntimeError) as exc:
        parser.exit(2, f"hk-law serve-http: {exc}\n")

    import uvicorn

    print(_banner(settings), flush=True)
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
