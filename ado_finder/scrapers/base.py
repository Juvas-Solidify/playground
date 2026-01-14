"""Base scraper class defining the interface for all scrapers."""

import signal
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..config import SourceConfig


@dataclass
class ScrapedJob:
    """Represents a scraped job posting."""
    company_name: str
    company_url: Optional[str]
    job_title: str
    job_url: str
    location: Optional[str]
    snippet: Optional[str]
    raw_data: dict


class GracefulInterrupt:
    """Context manager to handle graceful interrupts (Ctrl+C)."""

    def __init__(self):
        self.interrupted = False
        self._original_handler = None

    def __enter__(self):
        self._original_handler = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, self._handler)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        signal.signal(signal.SIGINT, self._original_handler)
        return False

    def _handler(self, signum, frame):
        self.interrupted = True


class BaseScraper(ABC):
    """Base class for all job posting scrapers."""

    def __init__(self, config: SourceConfig):
        """Initialize the scraper with configuration."""
        self.config = config
        self.source_name: str = "unknown"

    @abstractmethod
    def search(
        self,
        query: str,
        country: Optional[str] = None,
        max_results: Optional[int] = None,
    ) -> list[ScrapedJob]:
        """
        Search for job postings matching the query.

        Args:
            query: Search query (e.g., "Azure DevOps")
            country: Country to filter by (optional)
            max_results: Maximum number of results to return

        Returns:
            List of scraped job postings
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Clean up resources (close browser, etc.)."""
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
