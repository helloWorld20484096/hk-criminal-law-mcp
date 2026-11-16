"""A small OAuth 2.1 authorization server for the remote MCP endpoint.

The remote deployment needs OAuth (rather than a bare bearer token) to work
with hosted assistants that register clients dynamically: Claude, ChatGPT and
Gemini all support that pattern. This module implements the provider interface
expected by the MCP SDK and keeps its state in a JSON file under the
application home directory.

Security model
--------------
One operator secret (``HK_LAW_HTTP_ACCESS_KEY``) authorises the service. It is
accepted directly as a bearer token, and it is also the password on the
authorization-consent page. Anyone with the secret can approve a client; a
client registration alone grants nothing. Access and refresh tokens are stored
as SHA-256 hashes, so the state file does not contain usable bearer tokens.

This is deliberately a single-operator server, not a multi-tenant identity
provider. Do not use it to protect data belonging to different users.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    RegistrationError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

logger = logging.getLogger(__name__)

# A non-secret bearer value for MCP clients that cannot run OAuth. It is only
# accepted on a deliberately open deployment (HK_LAW_HTTP_ALLOW_ANONYMOUS=1).
OPEN_ACCESS_TOKEN = "open-access"

ACCESS_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
REFRESH_TOKEN_TTL_SECONDS = 90 * 24 * 60 * 60
AUTHORIZATION_CODE_TTL_SECONDS = 5 * 60
PENDING_TTL_SECONDS = 10 * 60
MAX_PENDING = 256
SCOPE = "hk-law"

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now() -> int:
    return int(time.time())


def _construct(model: type, **values):
    """Build an SDK auth model with only the fields this SDK version defines.

    MCP 2.x added ``subject`` to tokens and ``resource`` to refresh tokens;
    1.10 has neither on ``RefreshToken``. Keep one provider working on both.
    """
    allowed = set(getattr(model, "model_fields", {}))
    return model(**{key: value for key, value in values.items() if key in allowed})


class FileOAuthProvider(
    OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]
):
    """Single-operator OAuth provider with on-disk client/token state."""

    def __init__(
        self,
        *,
        access_keys: tuple[str, ...],
        public_url: str,
        store_path: Path,
        open_access: bool = False,
    ) -> None:
        if not access_keys and not open_access:
            raise ValueError("an access key or open access is required")
        self._access_keys = access_keys
        self.open_access = open_access
        self.public_url = public_url.rstrip("/")
        self.store_path = Path(store_path)
        self._clients: dict[str, dict] = {}
        self._access: dict[str, dict] = {}
        self._refresh: dict[str, dict] = {}
        self._codes: dict[str, AuthorizationCode] = {}
        self._pending: dict[str, dict] = {}
        self._lock = asyncio.Lock()
        self._load()
        # Fail at startup, not on the first token exchange, if the state file
        # cannot be written (for example a read-only Docker mount).
        try:
            self._save()
        except OSError as exc:
            raise RuntimeError(
                f"cannot write OAuth state to {self.store_path}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Operator access key
    # ------------------------------------------------------------------

    def key_matches(self, candidate: str | None) -> bool:
        """Constant-time check of the operator secret."""
        if not candidate:
            return False
        supplied = candidate.strip().encode("utf-8")
        matched = False
        for key in self._access_keys:
            # Compare every key so timing does not reveal which one matched.
            if hmac.compare_digest(supplied, key.encode("utf-8")):
                matched = True
        return matched

    def _looks_like_key(self, token: str) -> bool:
        return self.key_matches(token)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self.store_path.exists():
            return
        try:
            raw = json.loads(self.store_path.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("OAuth state at %s is unreadable (%s); starting empty", self.store_path, exc)
            try:
                self.store_path.replace(self.store_path.with_suffix(".corrupt"))
            except OSError:
                pass
            return
        if not isinstance(raw, dict):
            logger.warning("OAuth state at %s is not an object; ignoring", self.store_path)
            return

        clients = raw.get("clients") or {}
        self._clients = (
            {key: value for key, value in clients.items() if isinstance(value, dict)}
            if isinstance(clients, dict)
            else {}
        )
        now = _now()
        self._access = self._live_tokens(raw.get("access"), now)
        self._refresh = self._live_tokens(raw.get("refresh"), now)

    @staticmethod
    def _live_tokens(raw: object, now: int) -> dict[str, dict]:
        if not isinstance(raw, dict):
            return {}
        out: dict[str, dict] = {}
        for key, value in raw.items():
            if not isinstance(value, dict):
                continue
            try:
                expires = int(value.get("expires_at") or 0)
            except (TypeError, ValueError):
                continue
            if expires > now:
                out[key] = value
        return out

    def _save(self) -> None:
        now = _now()
        self._access = {
            key: value
            for key, value in self._access.items()
            if int(value.get("expires_at") or 0) > now
        }
        self._refresh = {
            key: value
            for key, value in self._refresh.items()
            if int(value.get("expires_at") or 0) > now
        }
        payload = {
            "version": 1,
            "clients": self._clients,
            "access": self._access,
            "refresh": self._refresh,
        }
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(
            prefix=".oauth-", suffix=".json", dir=self.store_path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, self.store_path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    # ------------------------------------------------------------------
    # Client registration
    # ------------------------------------------------------------------

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        data = self._clients.get(client_id)
        if data is None:
            return None
        try:
            return OAuthClientInformationFull(**data)
        except ValueError:
            logger.warning("Stored OAuth client %s is no longer valid; ignoring", client_id)
            return None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        # Refuse redirect URIs that could turn the consent page into an open
        # redirect. HTTPS everywhere, plus HTTP loopback for native clients.
        uris = client_info.redirect_uris or []
        if not uris:
            raise RegistrationError("invalid_redirect_uri", "at least one redirect_uri is required")
        for uri in uris:
            parsed = urlparse(str(uri))
            if parsed.scheme == "https":
                continue
            if parsed.scheme == "http" and parsed.hostname in _LOOPBACK_HOSTS:
                continue
            raise RegistrationError(
                "invalid_redirect_uri",
                "redirect_uri must use https (http is allowed only for loopback)",
            )

        async with self._lock:
            self._clients[client_info.client_id] = client_info.model_dump(
                mode="json", by_alias=True, exclude_none=True
            )
            self._save()

    # ------------------------------------------------------------------
    # Authorization endpoint / consent
    # ------------------------------------------------------------------

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        if not params.code_challenge:
            raise AuthorizeError("invalid_request", "PKCE code_challenge is required")
        if self.open_access:
            # Deliberately public deployment: no operator approval is needed,
            # because anonymous callers can already query the corpus. Return
            # the code directly so hosted assistants connect in one click.
            code = self._mint_code(client.client_id, params)
            return construct_redirect_uri(
                str(params.redirect_uri), code=code, state=params.state
            )
        now = _now()
        for request_id, entry in list(self._pending.items()):
            if entry["expires_at"] <= now:
                self._pending.pop(request_id, None)
        if len(self._pending) >= MAX_PENDING:
            raise AuthorizeError("temporarily_unavailable", "too many pending authorizations")

        request_id = secrets.token_urlsafe(24)
        self._pending[request_id] = {
            "client_id": client.client_id,
            "params": params,
            "expires_at": now + PENDING_TTL_SECONDS,
        }
        return f"{self.public_url}/oauth/consent?request={request_id}"

    def pending_request(self, request_id: str) -> dict | None:
        entry = self._pending.get(request_id)
        if entry is None or entry["expires_at"] <= _now():
            self._pending.pop(request_id, None)
            return None
        return entry

    def _mint_code(self, client_id: str, params: AuthorizationParams) -> str:
        now = _now()
        for code_key, record in list(self._codes.items()):
            if record.expires_at <= now:
                self._codes.pop(code_key, None)
        code = secrets.token_urlsafe(32)
        record = _construct(
            AuthorizationCode,
            code=code,
            scopes=params.scopes or [SCOPE],
            expires_at=now + AUTHORIZATION_CODE_TTL_SECONDS,
            client_id=client_id,
            code_challenge=params.code_challenge,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            resource=params.resource,
            subject="operator" if not self.open_access else "public",
        )
        self._codes[code] = record
        return code

    def complete_consent(
        self, request_id: str
    ) -> tuple[AuthorizationCode, AuthorizationParams, str] | None:
        """Mint an authorization code after the operator approves the request."""
        entry = self._pending.pop(request_id, None)
        if entry is None or entry["expires_at"] <= _now():
            return None
        params: AuthorizationParams = entry["params"]
        code = self._mint_code(entry["client_id"], params)
        return self._codes[code], params, entry["client_id"]

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        return self._codes.get(authorization_code)

    async def exchange_authorization_code(
        self,
        client: OAuthClientInformationFull,
        authorization_code: AuthorizationCode,
    ) -> OAuthToken:
        self._codes.pop(authorization_code.code, None)
        return await self._issue_tokens(
            client_id=client.client_id,
            scopes=authorization_code.scopes,
            resource=getattr(authorization_code, "resource", None),
            subject=getattr(authorization_code, "subject", None),
        )

    # ------------------------------------------------------------------
    # Token issue / refresh / revoke
    # ------------------------------------------------------------------

    async def _issue_tokens(
        self,
        *,
        client_id: str,
        scopes: list[str],
        resource: str | None,
        subject: str | None,
    ) -> OAuthToken:
        access = secrets.token_urlsafe(32)
        refresh = secrets.token_urlsafe(48)
        access_hash = _hash_token(access)
        refresh_hash = _hash_token(refresh)
        now = _now()
        access_record = {
            "client_id": client_id,
            "scopes": list(scopes),
            "expires_at": now + ACCESS_TOKEN_TTL_SECONDS,
            "resource": resource,
            "subject": subject,
            "refresh_hash": refresh_hash,
        }
        refresh_record = {
            "client_id": client_id,
            "scopes": list(scopes),
            "expires_at": now + REFRESH_TOKEN_TTL_SECONDS,
            "resource": resource,
            "subject": subject,
            "access_hash": access_hash,
        }
        async with self._lock:
            self._access[access_hash] = access_record
            self._refresh[refresh_hash] = refresh_record
            self._save()
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_TOKEN_TTL_SECONDS,
            scope=" ".join(scopes),
            refresh_token=refresh,
        )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        record = self._refresh.get(_hash_token(refresh_token))
        if record is None or int(record.get("expires_at") or 0) <= _now():
            return None
        if record["client_id"] != client.client_id:
            return None
        return _construct(
            RefreshToken,
            token=refresh_token,
            client_id=record["client_id"],
            scopes=list(record.get("scopes") or []),
            expires_at=int(record.get("expires_at") or 0),
            resource=record.get("resource"),
            subject=record.get("subject"),
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        old_hash = _hash_token(refresh_token.token)
        async with self._lock:
            old = self._refresh.pop(old_hash, None)
            if old and old.get("access_hash"):
                self._access.pop(old["access_hash"], None)
            self._save()
        granted = scopes or refresh_token.scopes
        return await self._issue_tokens(
            client_id=client.client_id,
            scopes=granted,
            resource=getattr(refresh_token, "resource", None),
            subject=getattr(refresh_token, "subject", None),
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        if self.open_access and token == OPEN_ACCESS_TOKEN:
            return _construct(
                AccessToken,
                token=token,
                client_id="open-access",
                scopes=[SCOPE],
                expires_at=None,
                subject="public",
            )
        # The operator secret works as a plain bearer token too, so clients
        # that only support custom headers (and CLI scripts) can skip OAuth.
        if self._looks_like_key(token):
            return _construct(
                AccessToken,
                token=token,
                client_id="operator-access-key",
                scopes=[SCOPE],
                expires_at=None,
                subject="operator",
            )
        record = self._access.get(_hash_token(token))
        if record is None or int(record.get("expires_at") or 0) <= _now():
            return None
        return _construct(
            AccessToken,
            token=token,
            client_id=record["client_id"],
            scopes=list(record.get("scopes") or []),
            expires_at=int(record.get("expires_at") or 0),
            resource=record.get("resource"),
            subject=record.get("subject"),
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        token_hash = _hash_token(token.token)
        async with self._lock:
            access = self._access.pop(token_hash, None)
            if access and access.get("refresh_hash"):
                self._refresh.pop(access["refresh_hash"], None)
            refresh = self._refresh.pop(token_hash, None)
            if refresh and refresh.get("access_hash"):
                self._access.pop(refresh["access_hash"], None)
            self._save()
