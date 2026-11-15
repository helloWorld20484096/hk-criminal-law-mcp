#!/usr/bin/env python3
"""Probe the public protocol metadata of the optional HKLawLLM MCP service.

This script intentionally does NOT authenticate, register a client, or call any
tool. It only checks:

- the unauthenticated 401 response from the MCP endpoint;
- the public protected-resource metadata;
- the public authorization-server metadata.

Usage:
    python scripts/check_hklawllm.py
    python scripts/check_hklawllm.py --json
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx

ENDPOINT = "https://hklawllm.com/api/mcp"
PUBLIC_PAGE = "https://hklawllm.com/mcp"
RESOURCE_METADATA = "https://hklawllm.com/.well-known/oauth-protected-resource"
USER_AGENT = "hk-criminal-law-mcp/0.1 (public metadata probe)"

TOOLS = [
    "search_cases",
    "get_case",
    "search_legislation",
    "get_section",
    "statute_history",
    "sentencing_tariff",
    "civil_quantum",
    "family_orders",
    "doctrine",
    "authority_top",
    "verify_citations",
    "db_stats",
    "report_issue",
]


def probe() -> dict:
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "metadata-probe", "version": "0.0.0"},
        },
    }
    with httpx.Client(
        timeout=30.0,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        response = client.post(
            ENDPOINT,
            json=initialize,
            headers={"Accept": "application/json, text/event-stream"},
        )
        resource = client.get(RESOURCE_METADATA)
        resource.raise_for_status()
        resource_data = resource.json()
        auth_servers = resource_data.get("authorization_servers") or []
        auth_metadata = None
        auth_error = None
        if auth_servers:
            auth_url = auth_servers[0].rstrip("/") + "/.well-known/oauth-authorization-server"
            try:
                auth_response = client.get(auth_url)
                auth_response.raise_for_status()
                auth_metadata = auth_response.json()
            except Exception as exc:  # network or JSON failure
                auth_error = str(exc)

    return {
        "public_page": PUBLIC_PAGE,
        "endpoint": ENDPOINT,
        "initialize_status": response.status_code,
        "www_authenticate": response.headers.get("www-authenticate"),
        "endpoint_body": response.text[:300],
        "resource_metadata_url": RESOURCE_METADATA,
        "resource_metadata": resource_data,
        "authorization_server_metadata_url": (
            auth_servers[0].rstrip("/") + "/.well-known/oauth-authorization-server"
            if auth_servers
            else None
        ),
        "authorization_server_metadata": auth_metadata,
        "authorization_server_error": auth_error,
        "published_tools": TOOLS,
        "note": (
            "No authentication, client registration, or tool call was attempted. "
            "Tool schemas and results require OAuth."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args(argv)

    try:
        result = probe()
    except Exception as exc:
        print(f"probe failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"public page:   {result['public_page']}")
        print(f"endpoint:      {result['endpoint']}")
        print(f"initialize:    HTTP {result['initialize_status']} (401 expected without OAuth)")
        if result["www_authenticate"]:
            print(f"auth header:   {result['www_authenticate']}")
        print(f"resource:      {result['resource_metadata']}")
        if result["authorization_server_metadata"]:
            auth = result["authorization_server_metadata"]
            print(f"auth issuer:   {auth.get('issuer')}")
            print(f"authorize:     {auth.get('authorization_endpoint')}")
            print(f"token:         {auth.get('token_endpoint')}")
            print(f"register:      {auth.get('registration_endpoint')}")
            print(f"grants:        {', '.join(auth.get('grant_types_supported', []))}")
            print(
                "PKCE:          "
                + ", ".join(auth.get("code_challenge_methods_supported", []))
            )
        elif result["authorization_server_error"]:
            print(f"auth metadata: unavailable ({result['authorization_server_error']})")
        print(f"published tools ({len(result['published_tools'])}):")
        for name in result["published_tools"]:
            print(f"  - {name}")
        print(result["note"])

    expected = result["initialize_status"] == 401
    return 0 if expected else 2


if __name__ == "__main__":
    raise SystemExit(main())
