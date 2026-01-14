"""Scrapers for various job posting sources."""

from .linkedin import LinkedInScraper
from .base import BaseScraper

__all__ = ["LinkedInScraper", "BaseScraper"]
