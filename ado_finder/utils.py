"""Utility functions for the Azure DevOps Lead Finder."""

import logging
import random
import re
import time
from functools import wraps
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse


# Setup logging
LOG_PATH = Path.home() / ".ado-finder" / "ado-finder.log"


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Set up logging configuration."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("ado-finder")
    logger.setLevel(level)

    # File handler
    file_handler = logging.FileHandler(LOG_PATH)
    file_handler.setLevel(level)
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(file_format)

    # Console handler for errors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    console_format = logging.Formatter("%(levelname)s: %(message)s")
    console_handler.setFormatter(console_format)

    # Add handlers if not already added
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger


def extract_domain(url: str) -> Optional[str]:
    """
    Extract the main domain from a URL.

    Strips www and common subdomains, returns just the registrable domain.

    Examples:
        https://www.example.com/path -> example.com
        https://careers.example.com -> example.com
        https://jobs.example.co.uk -> example.co.uk
    """
    if not url:
        return None

    try:
        # Add scheme if missing
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        parsed = urlparse(url)
        hostname = parsed.hostname

        if not hostname:
            return None

        hostname = hostname.lower()

        # Remove common subdomains
        subdomains_to_strip = [
            "www.",
            "careers.",
            "jobs.",
            "www2.",
            "m.",
            "mobile.",
            "secure.",
            "portal.",
        ]

        for subdomain in subdomains_to_strip:
            if hostname.startswith(subdomain):
                hostname = hostname[len(subdomain):]
                break

        # Handle multi-part TLDs (e.g., co.uk, com.au)
        # This is a simplified version - for production, consider using tldextract
        multi_part_tlds = [
            ".co.uk", ".co.nz", ".co.za", ".com.au", ".com.br",
            ".co.jp", ".co.kr", ".org.uk", ".net.au", ".gov.uk",
        ]

        for tld in multi_part_tlds:
            if hostname.endswith(tld):
                # Extract domain + multi-part TLD
                parts = hostname[:-len(tld)].split(".")
                if parts:
                    return parts[-1] + tld
                return hostname

        # Standard TLD - take last two parts
        parts = hostname.split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])

        return hostname

    except Exception:
        return None


def normalize_company_name(name: str) -> str:
    """
    Normalize a company name for consistency.

    Removes common suffixes like Inc., Ltd., AB, etc.
    """
    if not name:
        return ""

    name = name.strip()

    # Common company suffixes to remove
    suffixes = [
        r"\s+(Inc\.?|LLC\.?|Ltd\.?|Limited|Corp\.?|Corporation)$",
        r"\s+(AB|AS|A/S|GmbH|BV|NV|SA|SAS|Oy|ApS)$",
        r"\s+(PLC|Plc|plc|Co\.?)$",
    ]

    for suffix_pattern in suffixes:
        name = re.sub(suffix_pattern, "", name, flags=re.IGNORECASE)

    return name.strip()


def random_delay(min_seconds: float = 2.0, max_seconds: float = 5.0) -> None:
    """Sleep for a random duration between min and max seconds."""
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exceptions: tuple = (Exception,),
) -> Callable:
    """
    Decorator for retrying a function with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            logger = logging.getLogger("ado-finder")
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        # Add jitter
                        delay = delay * (0.5 + random.random())
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries + 1} failed for {func.__name__}: {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                    else:
                        logger.error(
                            f"All {max_retries + 1} attempts failed for {func.__name__}: {e}"
                        )

            raise last_exception

        return wrapper
    return decorator


# Common user agents for rotation
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]


def get_random_user_agent() -> str:
    """Get a random user agent string."""
    return random.choice(USER_AGENTS)


def truncate_text(text: str, max_length: int = 500) -> str:
    """Truncate text to a maximum length, adding ellipsis if needed."""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def clean_text(text: str) -> str:
    """Clean text by removing extra whitespace and normalizing."""
    if not text:
        return ""
    # Replace multiple whitespace with single space
    text = re.sub(r"\s+", " ", text)
    return text.strip()
