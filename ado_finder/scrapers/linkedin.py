"""LinkedIn job scraper using Playwright."""

import logging
import re
from typing import Optional
from urllib.parse import quote_plus, urljoin

from playwright.sync_api import Browser, Page, Playwright, sync_playwright

from ..config import SourceConfig
from ..utils import (
    clean_text,
    extract_domain,
    get_random_user_agent,
    random_delay,
    retry_with_backoff,
    truncate_text,
)
from .base import BaseScraper, GracefulInterrupt, ScrapedJob


logger = logging.getLogger("ado-finder")


# LinkedIn geo IDs for countries (used in job search URL)
LINKEDIN_GEO_IDS = {
    "sweden": "105117694",
    "norway": "103819153",
    "denmark": "104514075",
    "finland": "100456013",
    "united states": "103644278",
    "united kingdom": "101165590",
    "germany": "101282230",
    "netherlands": "102890719",
    "france": "105015875",
}


class LinkedInScraper(BaseScraper):
    """Scraper for LinkedIn job postings."""

    def __init__(self, config: SourceConfig):
        super().__init__(config)
        self.source_name = "linkedin"
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    def _init_browser(self) -> None:
        """Initialize the browser if not already done."""
        if self._browser is not None:
            return

        self._playwright = sync_playwright().start()

        # Try to find an existing chromium installation
        import os
        from pathlib import Path

        executable_path = None
        pw_cache = Path.home() / ".cache" / "ms-playwright"
        if pw_cache.exists():
            # Look for any chromium version
            for chromium_dir in sorted(pw_cache.glob("chromium-*"), reverse=True):
                chrome_path = chromium_dir / "chrome-linux" / "chrome"
                if chrome_path.exists():
                    executable_path = str(chrome_path)
                    logger.info(f"Using existing chromium at: {executable_path}")
                    break

        launch_args = {
            "headless": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ]
        }

        if executable_path:
            launch_args["executable_path"] = executable_path

        self._browser = self._playwright.chromium.launch(**launch_args)

        context = self._browser.new_context(
            user_agent=get_random_user_agent(),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
        )

        self._page = context.new_page()

        # Block unnecessary resources to speed up loading
        self._page.route(
            "**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf}",
            lambda route: route.abort()
        )

    def _build_search_url(
        self,
        query: str,
        country: Optional[str] = None,
        start: int = 0,
    ) -> str:
        """Build a LinkedIn job search URL."""
        base_url = "https://www.linkedin.com/jobs/search/"

        params = [
            f"keywords={quote_plus(query)}",
            f"start={start}",
        ]

        if country:
            geo_id = LINKEDIN_GEO_IDS.get(country.lower())
            if geo_id:
                params.append(f"geoId={geo_id}")
            else:
                # Use location parameter as fallback
                params.append(f"location={quote_plus(country)}")

        return f"{base_url}?{'&'.join(params)}"

    @retry_with_backoff(max_retries=3)
    def _load_page(self, url: str) -> None:
        """Load a page with retry logic."""
        self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Wait for job cards to appear
        try:
            self._page.wait_for_selector(
                ".jobs-search__results-list, .base-search-card",
                timeout=10000
            )
        except Exception:
            logger.warning("Timeout waiting for job results selector")

    def _scroll_to_load_more(self, max_scrolls: int = 5) -> None:
        """Scroll down to load more job postings."""
        for _ in range(max_scrolls):
            self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            random_delay(0.5, 1.0)

            # Check if "Show more" button exists and click it
            try:
                show_more_btn = self._page.query_selector(
                    "button.infinite-scroller__show-more-button"
                )
                if show_more_btn and show_more_btn.is_visible():
                    show_more_btn.click()
                    random_delay(1.0, 2.0)
            except Exception:
                pass

    def _parse_job_card(self, card) -> Optional[ScrapedJob]:
        """Parse a single job card element into a ScrapedJob."""
        try:
            # Get job title
            title_elem = card.query_selector(
                ".base-search-card__title, .job-search-card__title"
            )
            job_title = clean_text(title_elem.inner_text()) if title_elem else ""

            if not job_title:
                return None

            # Get job URL
            link_elem = card.query_selector("a.base-card__full-link, a.base-search-card__full-link")
            job_url = link_elem.get_attribute("href") if link_elem else ""

            if not job_url:
                # Try alternative selector
                link_elem = card.query_selector("a[href*='/jobs/view/']")
                job_url = link_elem.get_attribute("href") if link_elem else ""

            # Get company name
            company_elem = card.query_selector(
                ".base-search-card__subtitle, .job-search-card__company-name, "
                "h4.base-search-card__subtitle a"
            )
            company_name = clean_text(company_elem.inner_text()) if company_elem else ""

            if not company_name:
                return None

            # Get company URL
            company_link = card.query_selector(
                "h4.base-search-card__subtitle a, a[data-tracking-control-name*='company']"
            )
            company_url = company_link.get_attribute("href") if company_link else None

            # Get location
            location_elem = card.query_selector(
                ".job-search-card__location, .base-search-card__metadata"
            )
            location = clean_text(location_elem.inner_text()) if location_elem else None

            # Get snippet (job description preview)
            snippet_elem = card.query_selector(".job-search-card__snippet")
            snippet = truncate_text(
                clean_text(snippet_elem.inner_text()), 500
            ) if snippet_elem else None

            raw_data = {
                "html": card.inner_html() if hasattr(card, 'inner_html') else None,
                "company_name": company_name,
                "job_title": job_title,
                "job_url": job_url,
                "company_url": company_url,
                "location": location,
            }

            return ScrapedJob(
                company_name=company_name,
                company_url=company_url,
                job_title=job_title,
                job_url=job_url,
                location=location,
                snippet=snippet,
                raw_data=raw_data,
            )

        except Exception as e:
            logger.debug(f"Error parsing job card: {e}")
            return None

    def search(
        self,
        query: str,
        country: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> list[ScrapedJob]:
        """
        Search LinkedIn for job postings.

        Args:
            query: Search query (e.g., "Azure DevOps")
            country: Country to filter by (optional)
            max_results: Maximum number of results to return

        Returns:
            List of scraped job postings
        """
        self._init_browser()

        max_results = max_results or self.config.max_results_per_query
        results: list[ScrapedJob] = []
        seen_urls: set[str] = set()

        logger.info(f"Starting LinkedIn search: query='{query}', country='{country}'")

        with GracefulInterrupt() as interrupt:
            start = 0
            page_size = 25  # LinkedIn shows ~25 results per page

            while len(results) < max_results and not interrupt.interrupted:
                url = self._build_search_url(query, country, start)
                logger.debug(f"Loading page: {url}")

                try:
                    self._load_page(url)
                except Exception as e:
                    logger.error(f"Failed to load page: {e}")
                    break

                # Scroll to load more results
                self._scroll_to_load_more(max_scrolls=3)

                # Find job cards
                cards = self._page.query_selector_all(
                    ".base-search-card, .job-search-card, li.jobs-search-results__list-item"
                )

                if not cards:
                    logger.info("No more job cards found")
                    break

                page_results = 0
                for card in cards:
                    if len(results) >= max_results or interrupt.interrupted:
                        break

                    job = self._parse_job_card(card)
                    if job and job.job_url not in seen_urls:
                        results.append(job)
                        seen_urls.add(job.job_url)
                        page_results += 1
                        logger.debug(
                            f"Found job: {job.company_name} - {job.job_title}"
                        )

                if page_results == 0:
                    logger.info("No new results on this page, stopping")
                    break

                logger.info(
                    f"Found {page_results} jobs on page, total: {len(results)}"
                )

                start += page_size

                # Respect rate limits
                if len(results) < max_results and not interrupt.interrupted:
                    delay_min, delay_max = self.config.delay_seconds
                    random_delay(delay_min, delay_max)

        if interrupt.interrupted:
            logger.info(
                f"Search interrupted, returning {len(results)} partial results"
            )

        logger.info(f"LinkedIn search complete: found {len(results)} jobs")
        return results

    def close(self) -> None:
        """Close the browser and clean up resources."""
        if self._page:
            try:
                self._page.close()
            except Exception:
                pass
            self._page = None

        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
