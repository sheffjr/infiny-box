"""Infiny page reader — extracting page text with a real Chromium.

**Why.** Every extract provider Hermes ships with is paid (Firecrawl, Tavily,
Exa, Parallel), and SearXNG can only search — its `supports_extract()` is False.
Without this provider the Box could find a link but not read it, while the
Phase 1 promise is to work without a single API key.

**Why a provider rather than an MCP server.** The previous version was an MCP
server named `web`, and that name is already taken by Hermes' built-in toolset.
Because of the collision the tools registered (`mcp__web__web_search`) but NEVER
reached the agent: the platform resolver returned the built-in toolset, which
was dead without a provider. The symptom — "the agent lies about search" — held
for two weeks and was misdiagnosed three times. A provider slots exactly where
Hermes expects an extract backend, and creates no duplicates.

**Why async.** The gateway lives in asyncio, and Playwright's sync API fails
inside a running event loop. The provider ABC explicitly allows async.

**Why the full text is returned.** Truncation is `web_extract`'s own job
(truncate-and-store): the complete copy goes into the cache, the model receives
a tail of the right size, and reads the rest through `read_file`. Truncating
here by max_chars would break that.
"""

from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Dict, List

# The browser is baked into the image as root while the gateway runs elsewhere;
# without this variable Playwright would look for Chromium in
# ~/.cache/ms-playwright, which does not exist there. setdefault, so the
# environment can still override it.
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/playwright")

from agent.web_search_provider import WebSearchProvider

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) Infiny/1.0"

# Images, fonts and stylesheets are not needed to extract text — blocked for
# speed and for CPU, of which the Box has little to spare: the model already
# took its share.
_BLOCKED_RESOURCE_TYPES = {"image", "media", "font", "stylesheet"}

_PAGE_TIMEOUT_MS = 20_000
_SETTLE_MS = 1_000

_playwright = None
_browser = None
_browser_lock: "asyncio.Lock | None" = None


def _lock() -> "asyncio.Lock":
    # Lazily: an asyncio.Lock() at module level would bind to whichever event
    # loop existed at import time, and plugins are imported before the gateway's
    # loop starts.
    global _browser_lock
    if _browser_lock is None:
        _browser_lock = asyncio.Lock()
    return _browser_lock


async def _get_browser():
    """One Chromium for the whole gateway process, reused across calls."""
    global _playwright, _browser
    async with _lock():
        if _browser is not None and _browser.is_connected():
            return _browser
        from playwright.async_api import async_playwright

        _playwright = await async_playwright().start()
        _browser = await _playwright.chromium.launch(headless=True)
        return _browser


async def _render(url: str) -> Dict[str, Any]:
    browser = await _get_browser()
    context = await browser.new_context(user_agent=USER_AGENT)
    page = await context.new_page()

    async def _route(route):
        if route.request.resource_type in _BLOCKED_RESOURCE_TYPES:
            await route.abort()
        else:
            await route.continue_()

    await page.route("**/*", _route)
    try:
        await page.goto(url, timeout=_PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
        await page.wait_for_timeout(_SETTLE_MS)
        title = await page.title()
        text = await page.inner_text("body")
    finally:
        await context.close()

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text).strip()
    return {"url": url, "title": title or "", "content": text,
            "raw_content": text, "metadata": {"rendered": True}}


class InfinyRenderProvider(WebSearchProvider):
    """Extract-only provider: renders the page with a local Chromium."""

    @property
    def name(self) -> str:
        return "infiny-render"

    @property
    def display_name(self) -> str:
        return "Infiny page reader"

    def is_available(self) -> bool:
        # The ABC requires this to be cheap and offline: it is called when tools
        # are registered and on every redraw of `hermes tools`.
        try:
            import importlib.util

            if importlib.util.find_spec("playwright") is None:
                return False
        except Exception:
            return False
        return os.path.isdir(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "/opt/playwright"))

    def supports_search(self) -> bool:
        return False

    def supports_extract(self) -> bool:
        return True

    async def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for url in urls:
            try:
                results.append(await _render(url))
            except Exception as e:
                # The MODEL reads this error text and acts on it literally.
                # Without the closing sentence it fills the gap from memory —
                # which is exactly how the agent's "lying" began on 2 August.
                results.append({
                    "url": url,
                    "title": "",
                    "content": "",
                    "raw_content": "",
                    "error": (f"{type(e).__name__}: {e}. Page could not be read. "
                              "Tell the user this page failed; do not answer from memory."),
                })
        return results

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "Infiny page reader",
            "badge": "free · local",
            "tag": "Renders JS pages with the Chromium baked into the Box. No API key.",
            "env_vars": [],
        }
