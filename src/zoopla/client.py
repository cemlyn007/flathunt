import logging

from playwright.async_api import Browser, BrowserContext, async_playwright

from zoopla.models import ZooplaListingDetail
from zoopla.parser import parse_zoopla_listing_html

logger = logging.getLogger(__name__)

__all__ = ["ZooplaClient"]

_STEALTH_JS = """
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
Object.defineProperty(navigator, 'languages', {get: () => ['en-GB', 'en']});
window.chrome = {runtime: {}};
"""

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class ZooplaClient:
    """Async client for fetching Zoopla listing detail pages.

    Usage::

        async with ZooplaClient() as client:
            detail = await client.get_listing_detail(url)
    """

    def __init__(self, page_load_timeout: int = 30_000, settle_ms: int = 8_000) -> None:
        self._page_load_timeout = page_load_timeout
        self._settle_ms = settle_ms
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def __aenter__(self) -> "ZooplaClient":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        self._context = await self._browser.new_context(
            user_agent=_USER_AGENT,
            locale="en-GB",
            viewport={"width": 1280, "height": 800},
        )
        await self._context.add_init_script(_STEALTH_JS)
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:
                logger.exception("Error closing Playwright context")
            finally:
                self._context = None
        if self._browser is not None:
            try:
                await self._browser.close()
            except Exception:
                logger.exception("Error closing Playwright browser")
            finally:
                self._browser = None
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception:
                logger.exception("Error stopping Playwright")
            finally:
                self._playwright = None

    async def get_listing_detail(self, url: str) -> ZooplaListingDetail:
        """Fetch and parse a Zoopla property listing page.

        Args:
            url: Any Zoopla listing URL (query parameters are stripped).

        Returns:
            A ``ZooplaListingDetail`` parsed from the page.
        """
        if self._context is None:
            raise RuntimeError("Client not started; use as an async context manager")

        clean_url = url.split("?")[0].rstrip("/") + "/"
        logger.debug("Fetching %s", clean_url)

        page = await self._context.new_page()
        try:
            await page.goto(
                clean_url,
                wait_until="domcontentloaded",
                timeout=self._page_load_timeout,
            )
            await page.wait_for_timeout(self._settle_ms)
            html = await page.content()
        finally:
            await page.close()

        logger.debug("Fetched %d bytes from %s", len(html), clean_url)
        return parse_zoopla_listing_html(html, clean_url)
