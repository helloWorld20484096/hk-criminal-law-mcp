# Use it from ChatGPT, Claude, Gemini, DeepSeek and a phone

This document answers: **how do I put one Hong Kong law research service in
front of the AI tools I already use, including on my phone?**

The stdio MCP server is still the simplest option for Claude Code and other
local agents. This page is about the remote surface: one HTTPS process that
speaks MCP, plain JSON and a mobile web app over the same corpus.

## What one deployment gives you

| Surface | URL | Used by |
|---|---|---|
| Mobile web app | `https://your-host/` | Any phone or desktop browser; no install, no account |
| MCP (Streamable HTTP) | `https://your-host/mcp` | Claude, ChatGPT, Gemini, DeepSeek Harness, MCP Inspector, any MCP client |
| JSON API | `POST https://your-host/api/<tool>` | Scripts, function calling, custom GPT Actions |
| Generic call | `POST https://your-host/api/call` | Harnesses that prefer one endpoint |
| OpenAPI schema | `https://your-host/openapi.json` | Custom GPT Actions and OpenAPI clients |
| Tool schemas | `https://your-host/api/tools?format=openai` (or `gemini`, `anthropic`, `deepseek`) | Provider function-calling APIs |
| Health | `https://your-host/healthz` | Your uptime monitor |

All surfaces call the same 29 read-oriented tools and return the same
provenance, warnings and disclaimer. `sync_doj` is hidden from the remote
surface by default because syncing is an operator task; set
`HK_LAW_HTTP_ALLOW_SYNC=1` if you want chat clients to trigger it.

## One-click connect: `/connect`

Every deployment serves a public setup page at:

```text
https://your-host/connect
```

It detects the deployment mode and gives one button per client:

| Button | What actually happens |
|---|---|
| **Add to Claude** | Opens Claude's custom-connector dialog with this server's name and URL prefilled. (The prefill URL is community-adopted, not a published Anthropic standard; manual steps are on the page.) |
| **Add to ChatGPT** | Opens ChatGPT's developer-mode create-connector screen and copies the MCP URL. Paste it into the form. For a true one-click link for other people, publish a custom GPT or ChatGPT app once and share that link. |
| **Open Gemini connectors** | Opens Gemini's Connected Apps screen and copies the URL. Gemini has no public prefill link yet, so paste it into **+ Custom**. For a true one-click install, register the server in Google's Connected Apps console. |
| **DeepSeek Harness** | Copies a one-command installer that installs `@deepseek-ai/dsh-mcp-client` and adds this server to `~/.dsh/cordis.patch.yml`. |
| **Open the web app** | Opens the phone-friendly research UI. Add to Home Screen for an app shortcut. |
| **Copy JSON / server.json** | Works with any MCP client, the MCP Registry manifest and universal installers. |

The page also publishes:

- `GET /server.json` and `GET /.well-known/mcp/server.json` — an MCP Registry
  manifest (`streamable-http` remote).
- `GET /connect/dsh.sh` — the reviewed DeepSeek Harness installer.
- `GET /privacy` and `GET /terms` — short pages for directory/app review.

### For a true one-click listing

No vendor offers a fully one-click install for an **unlisted** remote MCP
server yet. The `/connect` page gets as close as each platform allows. For a
genuine one-click install for other people, publish once:

- **Claude:** submit the connector to Anthropic's Connectors Directory. Until
  then, the prefilled custom-connector link is the closest path.
- **ChatGPT:** publish a ChatGPT app, or a custom GPT with the
  `/openapi-core.json` Action. Share the app/GPT link; users click once.
- **Gemini:** register the server in Google's Connected Apps console (HTTPS,
  OAuth 2.1 + PKCE + dynamic registration, tool annotations). Consumer custom
  connectors are still rolling out.
- **MCP Registry:** `/server.json` is already a valid registry manifest with a
  `streamable-http` remote. Publish it with the MCP publisher after verifying
  the namespace; universal installers can then resolve it.

The `/connect` page links to the privacy and terms pages that directory reviews
usually ask for.

### Open mode: no key, true one-click

For a deliberately public, read-only deployment, set a public URL and allow
anonymous access **without** an access key:

```bash
HK_LAW_HTTP_PUBLIC_URL=https://your-host \
HK_LAW_HTTP_ALLOW_ANONYMOUS=1 \
.venv/bin/hk-law serve-http
```

In this mode OAuth is **auto-approved** (no consent screen and no key), so the
Claude/ChatGPT/Gemini connect flow completes immediately. MCP clients that
cannot do OAuth can send:

```http
Authorization: Bearer open-access
```

This is only suitable for public legal data. Anyone with the URL can query the
corpus; the server still hides `sync_doj`, redacts operator details, rate-limits
and disclaims. Use key mode for anything private.

## Quick start: localhost

```bash
# 1. Install and build the corpus (see README if you have not done this)
make setup
make ingest            # or restore the published database

# 2. Run the remote surface on loopback
make serve-http
# equivalent: .venv/bin/hk-law serve-http
```

Open <http://127.0.0.1:8765/>. The MCP endpoint is
`http://127.0.0.1:8765/mcp`. Loopback-only use requires no key.

Hosted assistants such as Claude, ChatGPT and Gemini connect from the
provider's cloud, not from your laptop. For those, continue to the public
deployment.

## Quick start: public HTTPS

You need a machine with the corpus, a domain name and ports 80/443.

```bash
# On the server, from the repository root:
mkdir -p data
# Build or restore data/hk_law.db first. The image does not contain the corpus.
# The container runs as uid 10001 and needs to write SQLite WAL files:
sudo chown -R 10001:10001 data

cp .env.example .env
# Set HK_LAW_HTTP_ACCESS_KEY, HK_LAW_HTTP_PUBLIC_URL, and review LOCAL_ONLY.
# Generate a key with: openssl rand -base64 32

docker compose up -d --build
docker compose logs -f
```

Point `deploy/Caddyfile` at your domain and run Caddy on the host:

```bash
sudo caddy run --config deploy/Caddyfile
```

Then check:

```bash
curl -s https://your-host/healthz
curl -s https://your-host/api/meta | jq .auth        # "oauth"
curl -s -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' \
  -d '{"query":"bail conditions"}' \
  https://your-host/api/search_legislation | jq .count
```

The container binds only to `127.0.0.1:8765`; Caddy is the public entry point.
Do not publish port 8765 directly.

### Without Docker

```bash
.venv/bin/hk-law serve-http \
  --host 0.0.0.0 \
  --port 8765 \
  --access-key "$(openssl rand -base64 32)" \
  --public-url https://your-host
```

Run it under systemd, a process supervisor, or a PaaS that provides HTTPS. The
server refuses a non-loopback bind without an access key unless you pass
`--anonymous` (or set `HK_LAW_HTTP_ALLOW_ANONYMOUS=1`). From a checkout,
`bash scripts/serve_http.sh` is a shortcut that points `HK_LAW_DB` at
`data/hk_law.db` unless you set it.

### No public server? Use a tunnel

For a quick test from ChatGPT/Claude without a VPS, expose localhost with a
tunnel. With Cloudflare Tunnel, start the tunnel first, copy the HTTPS URL it
prints, then start the server with that URL:

```bash
cloudflared tunnel --url http://127.0.0.1:8765
# in another terminal, with the printed https://...trycloudflare.com URL:
.venv/bin/hk-law serve-http \
  --access-key "$(openssl rand -base64 32)" \
  --public-url https://your-tunnel-url
```

The OAuth issuer is fixed at startup, so the tunnel URL must be known first.
Quick tunnels are ephemeral and intended for testing; use a named tunnel or a
real reverse proxy for anything durable. ngrok works the same way.

## Authentication modes

| Mode | When | Behaviour |
|---|---|---|
| `anonymous` | Localhost, or a deliberately public read-only service | No credentials. Rate limited. Anyone with the URL can query. |
| `key` | Private deployment without OAuth | Clients send `Authorization: Bearer <key>`. The browser web app asks for the key once and stores it locally. |
| `oauth` | Private hosted deployment | Enabled by setting both `HK_LAW_HTTP_ACCESS_KEY` and `HK_LAW_HTTP_PUBLIC_URL`. Supports dynamic client registration, PKCE and a consent page protected by the access key. The key also still works as a bearer token. |
| `open OAuth` | Deliberately public, read-only service | `HK_LAW_HTTP_PUBLIC_URL` + `HK_LAW_HTTP_ALLOW_ANONYMOUS=1`, no key. OAuth is auto-approved, so hosted assistants connect in one click. Header-only clients use `Authorization: Bearer open-access`. Anyone with the URL can query. |

Setting `HK_LAW_HTTP_PUBLIC_URL` without a key is refused unless you also set
`HK_LAW_HTTP_ALLOW_ANONYMOUS=1`; this prevents a forgotten key from silently
creating a public endpoint.

Only one operator secret is involved. This is a single-operator service, not a
multi-tenant identity provider; do not use it to separate data belonging to
different people.

## Connect Claude (web, desktop and mobile)

Claude connects to remote MCP servers from Anthropic's cloud, so the URL must be
publicly reachable over HTTPS.

1. Settings → Connectors → **Add custom connector**.
2. Name: `HK Criminal Law`.
3. Remote MCP server URL: `https://your-host/mcp`.
4. Authentication:
   - **OAuth**: choose Claude's automatic/dynamic client registration (not a
     pre-registered client ID). The consent page asks for
     `HK_LAW_HTTP_ACCESS_KEY`; approve it.
   - Or use **request headers** with
     `Authorization: Bearer <your access key>` if your plan exposes that option.
5. Enable the connector in a conversation from the **+** → Connectors menu.

The connector is attached to your account, so the Claude mobile app sees it too.
Official help: <https://support.claude.com/en/articles/11175166>.

## Connect ChatGPT (web and mobile)

Custom MCP connectors use ChatGPT developer mode.

1. Settings → **Apps & Connectors** → Advanced settings → enable **Developer
   mode** (a workspace admin may need to enable it for Business/Enterprise).
2. Apps & Connectors → **Create**.
3. Name and description: use something explicit, such as
   "Hong Kong criminal law — legislation, judgments and DOJ policy".
4. MCP server URL: `https://your-host/mcp`.
5. Authentication: **OAuth** (recommended), or **No authentication** if you
   deliberately run an anonymous public deployment. ChatGPT's connector UI does
   not offer a static bearer-token field, so OAuth mode (both
   `HK_LAW_HTTP_ACCESS_KEY` and `HK_LAW_HTTP_PUBLIC_URL` set) is the supported
   private path.
6. Start a new chat and enable the connector from the **+** menu. It must be
   enabled per conversation.

ChatGPT may restrict custom connectors on some plans to read/fetch operations.
The remote surface is read-only apart from the hidden `sync_doj`, and the
research tools carry MCP `readOnlyHint` annotations, so ChatGPT should not ask
for a write confirmation on ordinary searches. Mobile apps use the connector
after it is created on the account.

Alternative for custom GPTs: import `https://your-host/openapi-core.json` as a
GPT Action and configure API-key auth with the access key. The core schema has
14 operations to stay within Action limits; `/openapi.json` has all 29.

Official help: <https://help.openai.com/en/articles/12584461>.

## Connect Gemini (web and mobile)

Google is rolling custom MCP connectors and its Connected Apps platform out in
stages. Where the UI is available:

1. Open <https://gemini.google.com/customize/connectors> (or Settings →
   Connectors).
2. **+ Custom** → paste `https://your-host/mcp`.
3. Complete the OAuth flow. The consent page asks for
   `HK_LAW_HTTP_ACCESS_KEY`.

Gemini's connected-app requirements include HTTPS, OAuth 2.1 with PKCE and
dynamic client registration; this server supports that flow. Public listing in
the Gemini app/Search may require Google's review, but a personal connector does
not.

If the consumer Gemini app does not yet offer custom connectors for your
account, use one of:

- **Gemini API function calling**: fetch `https://your-host/api/tools?format=gemini`
  and pass the declarations to the model; execute returned calls against
  `POST /api/call`.
- **Gemini CLI / an MCP-capable Gemini surface**: add
  `https://your-host/mcp` as an HTTP MCP server.
- The **mobile web app** at `https://your-host/` works in any phone browser.

## Connect DeepSeek Harness

DeepSeek Harness (DSH) has an MCP client plugin
(`@deepseek-ai/dsh-mcp-client`) that accepts stdio and HTTP transports. Add a
remote server with these values:

- URL: `https://your-host/mcp`
- Transport: Streamable HTTP
- Header: `Authorization: Bearer <your access key>` (or complete OAuth if the
  plugin supports it)

The plugin's configuration file differs by release; use the fields above in its
MCP-server section. Do not point it at a stdio command.

The `/connect` page also offers a one-command installer:

```bash
curl -fsSL https://your-host/connect/dsh.sh | bash
```

It installs `@deepseek-ai/dsh-mcp-client` (pinned to a known-good version;
override with `DSH_MCP_CLIENT_VERSION`) and appends an `mcp-hk-law` entry to
`~/.dsh/cordis.patch.yml`. For a key-protected deployment, export
`HK_LAW_KEY` in the environment that starts DSH. On an open deployment the
script uses the non-secret `open-access` bearer value.

For `chat.deepseek.com` or any DeepSeek API harness without an MCP client, use
the function-calling route:

1. `GET https://your-host/api/tools?format=openai`
2. Pass the resulting `tools` array to the model.
3. Execute each returned call with
   `POST https://your-host/api/call` and body
   `{"tool": "<name>", "arguments": {...}}`.
4. Return the JSON result to the model.

## Any other MCP client

Most clients accept a URL and headers:

```json
{
  "mcpServers": {
    "hk-criminal-law": {
      "type": "http",
      "url": "https://your-host/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_ACCESS_KEY"
      }
    }
  }
}
```

Some use `"transport": "streamable-http"` instead of `"type": "http"`; some
accept `"url"` directly. The endpoint is stateless by default, so no session
affinity is needed. For a stateful deployment, start with `--stateful` and
enable sticky sessions at the proxy. If a harness cannot consume SSE
responses, start with `--json-response` (or `HK_LAW_HTTP_JSON_RESPONSE=1`);
the REST API is unaffected.

## Phone use

Three options, in order of convenience:

1. **Claude or ChatGPT mobile app** — add the connector once on the web/desktop
   account (the mobile apps use the account's connectors). Then invoke the
   connector in a chat.
2. **The built-in web app** — open `https://your-host/` in Safari or Chrome.
   It is a single mobile-first page: search legislation, judgments and DOJ
   policy; read the full text; verify citations; switch English/繁體中文. Add it
   to the home screen for an app-like shortcut. The access key, if required, is
   stored in that browser only; use **Forget** on a shared device.
3. **A shortcut / automation app** — call `POST /api/search_legislation` (or
   `/api/call`) with the bearer header and render the JSON yourself.

The web app deliberately has no build step and no third-party scripts. It is
served by the same process as the MCP endpoint.

## Operating the service

```bash
# Corpus refresh on the host (while the container is stopped or between reads)
.venv/bin/hk-law sync

# Logs and health
docker compose logs -f
curl -s https://your-host/healthz

# Back up the corpus safely
sqlite3 data/hk_law.db ".backup 'backup-$(date +%F).db'"

# Revoke every OAuth token and force clients to re-authorise
rm data/oauth_state.json && docker compose restart
```

- **One process.** The rate limiter and OAuth state are in-process, and SQLite
  writes are serialised. Scale with a read replica, not multiple uvicorn workers.
- **OAuth state** is stored at `$HK_LAW_HOME/oauth_state.json` (mode 0600).
  Access and refresh tokens are stored as SHA-256 hashes. Back it up with the
  database if you do not want clients to re-authorise after a rebuild.
- **Corpus**: the container reads `/data/hk_law.db`. Build it on the host with
  the CLI. The image intentionally does not bundle judgments.
- **Semantic atlas** is optional. Build it with `make map-all`, mount
  `semantic_map/dist/data`, and set `HK_LAW_SEMANTIC_MAP`; otherwise the
  semantic tools return a build hint.

## Security and source terms

- Keep `HK_LAW_HTTP_ACCESS_KEY` secret. It is both the OAuth consent password
  and a bearer token. Rotate it by changing the env var; existing OAuth access
  tokens remain valid until they expire (30 days), so delete
  `oauth_state.json` to revoke them immediately.
- Run one process per SQLite database. Do not expose the database file or the
  raw volume over the network.
- The default rate limit is 120 requests per client per 60 seconds. Tune with
  `HK_LAW_HTTP_RATE_LIMIT` / `HK_LAW_HTTP_RATE_WINDOW`, or move the limit to the
  proxy. Keep the HKLII rate limiter intact.
- In production, set `HK_LAW_HTTP_ALLOWED_HOSTS=your-host` so the MCP transport
  validates the Host header; add `your-host:*` if your proxy forwards an
  explicit port. The public origin is added to allowed origins automatically.
  Browser-based MCP clients also send an `Origin` header; add their origin to
  `HK_LAW_HTTP_ALLOWED_ORIGINS` if you enable host checking.
- **Open mode is for public data only.** `HK_LAW_HTTP_ALLOW_ANONYMOUS=1` with no
  key lets anyone obtain an OAuth token and query the corpus. Do not use it on a
  corpus containing judgment text you may not redistribute, and do not enable
  `sync_doj` on an open endpoint.
- **Do not turn a personal deployment into a public judgment redistribution
  service.** Live HKLII access is query-time coverage, remains subject to
  HKLII's terms, and bulk automated access requires
  `HK_LAW_CASE_PERMISSION_REF`. For an open, public deployment, default to
  `HK_LAW_LOCAL_ONLY=1` unless you have reviewed the source terms for that
  scale. See [Data sources and licensing](data-sources-and-licensing.md).
- Every response carries the disclaimer. Keep it in your own UI if you build
  one. This is a retrieval aid, not a citator of record and not legal advice.
- `sync_doj` is hidden remotely by default. Enabling it lets any authenticated
  caller cause outbound DOJ fetches (rate-limited and polite, but still an
  operator action). Prefer a scheduled `hk-law sync` instead.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `421 Misdirected Request` / `Invalid Host header` | The Host header does not match the allowed list. Set `HK_LAW_HTTP_ALLOWED_HOSTS=your-host`, or set `HK_LAW_HTTP_PUBLIC_URL` correctly. |
| `401 unauthorized` from REST or MCP | Missing/incorrect bearer token. Send `Authorization: Bearer <key>`; in the web app, use the **Key** button. |
| OAuth discovery returns 404 | `HK_LAW_HTTP_PUBLIC_URL` is unset, so OAuth is disabled. Set it to the exact HTTPS URL and restart. |
| OAuth consent page says the request expired | The pending request lasts 10 minutes. Reconnect from the assistant. |
| ChatGPT does not list the tools | Enable developer mode; recreate or refresh the connector; the connector must be enabled in each conversation. |
| Gemini has no custom connector option | The rollout has not reached the account. Use the function-calling route or the mobile web app. |
| Claude cannot reach the server | Claude calls from Anthropic's cloud. The URL must be public HTTPS, not localhost or a private LAN address. |
| Empty results on a fresh install | The corpus is empty. Download and ingest legislation, or restore the published database (README). |
| Cases missing | Local corpus has no judgment. Use the official source link, or enable a permitted live source; in local-only mode a missing case is a coverage gap, not a negative finding. |
| `429 rate_limited` | Increase `HK_LAW_HTTP_RATE_LIMIT` or wait for the window. |
| MCP calls hang behind a proxy | Disable response buffering for `/mcp` (the Caddyfile does this with `flush_interval -1`), or start the server with `--json-response`. |
| `sync_doj` is 404 | Hidden by default; set `HK_LAW_HTTP_ALLOW_SYNC=1` if you really want it remote. |
| Web app asks for a key repeatedly | The browser is blocking local storage, or you are in a private window. Use the key each session. |

## Related

[Agentic use](agentic-use.md) · [Architecture](architecture.md) ·
[Fully local pipeline](full-local-pipeline.md) ·
[Data sources and licensing](data-sources-and-licensing.md) ·
[README](../README.md)
