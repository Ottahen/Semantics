"""Browser automation (Pro tool).

Gives the agent a `browser_navigate` / `browser_click` / `browser_fill` /
`browser_screenshot` toolset for tasks that need to interact with a real
web page (checking a deployed preview, filling a form, scraping a page
that requires JS). Backed by Playwright, headless by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .license import require_license

try:
    from playwright.async_api import Browser, Page, async_playwright

    _HAS_PLAYWRIGHT = True
except ImportError:  # pragma: no cover - playwright is an optional/pro dependency
    _HAS_PLAYWRIGHT = False


class BrowserError(RuntimeError):
    pass


@dataclass
class PageSnapshot:
    url: str
    title: str
    text_content: str


class BrowserController:
    """Async context manager wrapping a single headless Chromium page.

        async with BrowserController() as browser:
            snap = await browser.navigate("https://example.com")
            await browser.click("text=Sign in")
            await browser.fill("#email", "alice@example.com")
            path = await browser.screenshot("out.png")
    """

    def __init__(self, headless: bool = True) -> None:
        if not _HAS_PLAYWRIGHT:
            raise BrowserError(
                "playwright is not installed. `pip install -r requirements.pro.txt && playwright install chromium`."
            )
        self.headless = headless
        self._playwright = None
        self._browser: Optional["Browser"] = None
        self._page: Optional["Page"] = None

    async def __aenter__(self) -> "BrowserController":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        self._page = await self._browser.new_page()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    @property
    def page(self) -> "Page":
        if self._page is None:
            raise BrowserError("BrowserController used outside an `async with` block.")
        return self._page

    @require_license("browser_navigate")
    async def navigate(self, url: str, wait_until: str = "load") -> PageSnapshot:
        await self.page.goto(url, wait_until=wait_until)
        return await self._snapshot()

    @require_license("browser_click")
    async def click(self, selector: str) -> PageSnapshot:
        await self.page.click(selector)
        return await self._snapshot()

    @require_license("browser_fill")
    async def fill(self, selector: str, value: str) -> PageSnapshot:
        await self.page.fill(selector, value)
        return await self._snapshot()

    @require_license("browser_screenshot")
    async def screenshot(self, output_path: str) -> Path:
        path = Path(output_path)
        await self.page.screenshot(path=str(path), full_page=True)
        return path

    async def _snapshot(self) -> PageSnapshot:
        return PageSnapshot(
            url=self.page.url,
            title=await self.page.title(),
            text_content=(await self.page.inner_text("body"))[:5000],
        )
