"""Thin Playwright client for Etsy search pages."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlencode

from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from niche_scout.config import DefaultsConfig


class EtsyClient:
    def __init__(self, defaults: DefaultsConfig) -> None:
        self.defaults = defaults
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    def __enter__(self) -> "EtsyClient":
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.defaults.runtime.headless,
            channel=self.defaults.runtime.browser_channel,
        )
        self._context = self._browser.new_context(
            locale=self.defaults.runtime.locale,
            timezone_id=self.defaults.runtime.timezone,
            viewport={"width": 1440, "height": 1280},
        )
        return self

    def __exit__(self, *_args: object) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def new_page(self) -> Page:
        if self._context is None:
            raise RuntimeError("Browser context is not initialized.")
        page = self._context.new_page()
        page.set_default_timeout(self.defaults.runtime.timeout_ms)
        return page

    def build_search_url(self, query: str) -> str:
        params = urlencode({"q": query})
        return f"{self.defaults.etsy.base_url}?{params}"

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def search(self, page: Page, query: str) -> str:
        url = self.build_search_url(query)
        page.goto(url, wait_until="domcontentloaded")
        page.wait_for_timeout(self.defaults.runtime.delay_ms)
        return page.url

    def save_artifacts(self, page: Page, html_path: Path | None = None, screenshot_path: Path | None = None) -> None:
        if html_path is not None:
            html_path.parent.mkdir(parents=True, exist_ok=True)
            html_path.write_text(page.content(), encoding="utf-8")
        if screenshot_path is not None:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)

    def load_cached_html(self, page: Page, html_path: Path) -> None:
        page.set_content(html_path.read_text(encoding="utf-8"), wait_until="domcontentloaded")
