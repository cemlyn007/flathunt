import logging

from playwright.async_api import (
    Browser,
    BrowserContext,
    async_playwright,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

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

# Resolves once the RSC chunk that the parser scans for (uprn + coordinates)
# is in the DOM. Both keywords appear in the same script regardless of JSON
# escaping, since textContent returns the raw script source.
_DATA_READY_PREDICATE = """
() => Array.from(document.scripts).some(s => {
    const t = s.textContent || '';
    return t.includes('coordinates') && t.includes('uprn');
})
"""

# Substrings (case-insensitive) seen in the <title> of Cloudflare / bot-wall
# interstitials. When matched we skip the data-ready wait — the listing payload
# will never arrive, so burning the full timeout helps no-one.
_BOT_WALL_TITLE_MARKERS = (
    "just a moment",
    "attention required",
    "sorry, you have been blocked",
)


class ZooplaClient:
    """Async client for fetching Zoopla listing detail pages.

    Usage::

        async with ZooplaClient() as client:
            detail = await client.get_listing_detail(url)
    """

    def __init__(
        self, page_load_timeout: int = 30_000, data_ready_timeout_ms: int = 25_000
    ) -> None:
        self._page_load_timeout = page_load_timeout
        self._data_ready_timeout_ms = data_ready_timeout_ms
        self._playwright = None
        self._browser: Browser | None = None

    async def __aenter__(self) -> "ZooplaClient":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=True)
        return self

    async def __aexit__(self, *args: object) -> None:
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

    async def _new_context(self) -> BrowserContext:
        if self._browser is None:
            raise RuntimeError(
                "Browser not started; use ZooplaClient as an async context manager."
            )
        context = await self._browser.new_context(
            user_agent=_USER_AGENT,
            locale="en-GB",
            viewport={"width": 1280, "height": 800},
        )
        await context.add_init_script(_STEALTH_JS)
        return context

    async def get_listing_detail(self, url: str) -> ZooplaListingDetail:
        """Fetch and parse a Zoopla property listing page.

        Each call uses a fresh ``BrowserContext`` (cookies, storage, and
        fingerprint state). Reusing one context across multiple fetches
        causes Zoopla/Cloudflare to flag the session after the first request
        and stall the RSC payload on every subsequent navigation.

        Args:
            url: Any Zoopla listing URL (query parameters are stripped).

        Returns:
            A ``ZooplaListingDetail`` parsed from the page.
        """
        if self._browser is None:
            raise RuntimeError("Client not started; use as an async context manager")

        clean_url = url.split("?")[0].rstrip("/") + "/"
        logger.debug("Fetching %s", clean_url)

        context = await self._new_context()
        try:
            page = await context.new_page()
            try:
                await page.goto(
                    clean_url,
                    wait_until="domcontentloaded",
                    timeout=self._page_load_timeout,
                )
                title = (await page.title()) or ""
                if any(m in title.lower() for m in _BOT_WALL_TITLE_MARKERS):
                    logger.warning(
                        "Bot wall detected for %s (title=%r); skipping data-ready wait.",
                        clean_url,
                        title,
                    )
                else:
                    try:
                        await page.wait_for_function(
                            _DATA_READY_PREDICATE,
                            timeout=self._data_ready_timeout_ms,
                        )
                    except PlaywrightTimeoutError:
                        logger.warning(
                            "Zoopla page %s did not surface listing payload within %dms; "
                            "parsing whatever is present.",
                            clean_url,
                            self._data_ready_timeout_ms,
                        )
                html = await page.content()
            finally:
                await page.close()
        finally:
            try:
                await context.close()
            except Exception:
                logger.exception("Error closing Playwright context")

        logger.debug("Fetched %d bytes from %s", len(html), clean_url)
        return parse_zoopla_listing_html(html, clean_url)
