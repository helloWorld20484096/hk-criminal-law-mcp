"""Browser smoke test for the generated Hong Kong Law Atlas.

Run after `make map-site`. Requires Playwright and a Chromium/Chrome binary.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import socketserver
import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


def serve(directory: Path):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    server = socketserver.TCPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist", default="semantic_map/dist")
    parser.add_argument("--chrome", default="/usr/bin/google-chrome")
    args = parser.parse_args()
    dist = Path(args.dist).resolve()
    if not (dist / "index.html").exists():
        raise SystemExit(f"missing built site: {dist / 'index.html'}")
    server, port = serve(dist)
    url = f"http://127.0.0.1:{port}/index.html"
    failures: list[str] = []

    def check(label: str, condition: bool, detail: str = ""):
        if condition:
            print(f"PASS {label}")
        else:
            print(f"FAIL {label} {detail}")
            failures.append(label)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=args.chrome, args=["--no-sandbox"])

            # Desktop
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(url)
            page.wait_for_function("document.getElementById('loading').hidden === true", timeout=60000)
            check("desktop loaded", True)
            check("desktop points", "points" in page.inner_text("#status-visible"))
            check("desktop clusters", page.locator(".cluster-item").count() > 0)
            page.fill("#search", "application")
            page.wait_for_function("document.querySelectorAll('.result-item').length > 0", timeout=20000)
            check("desktop search results", page.locator(".result-item").count() > 0)
            page.locator(".result-item").first.click()
            page.wait_for_function("document.getElementById('detail-text').textContent.length > 20", timeout=20000)
            check("desktop detail", True)
            check("desktop source", page.get_attribute("#detail-source", "href").startswith("http"))
            check("desktop no page errors", not errors, str(errors[:3]))
            page.close()

            # Mobile
            context = browser.new_context(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                has_touch=True,
                device_scale_factor=2,
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.goto(url)
            page.wait_for_function("document.getElementById('loading').hidden === true", timeout=60000)
            check("mobile loaded", True)
            page.fill("#search", "application")
            page.wait_for_function("document.querySelectorAll('.result-item').length > 0", timeout=20000)
            check("mobile search opens drawer", page.evaluate("document.getElementById('sidebar').classList.contains('is-open')"))
            page.locator(".result-item").first.click()
            page.wait_for_function("document.getElementById('detail').classList.contains('open')", timeout=20000)
            page.wait_for_function("document.getElementById('detail-text').textContent.length > 20", timeout=20000)
            check("mobile detail sheet", True)
            check("mobile detail text", True)
            page.click("#btn-list")
            page.wait_for_timeout(400)
            check("mobile list", page.evaluate("!document.getElementById('list-view').hidden"))
            check("mobile no page errors", not errors, str(errors[:3]))
            page.close()
            browser.close()
    finally:
        server.shutdown()

    if failures:
        print(f"\n{len(failures)} failure(s)")
        return 1
    print("\nAll smoke checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
