"""CSV exporter for companies and signals."""

import csv
from pathlib import Path
from typing import Optional

from ..database import get_all_signals, get_companies_with_signal_count


class CSVExporter:
    """Export data to CSV format."""

    @staticmethod
    def export_companies(
        output_path: Path,
        days: Optional[int] = None,
        db_path: Optional[Path] = None,
    ) -> int:
        """
        Export companies to CSV.

        Args:
            output_path: Path to write the CSV file
            days: Only include companies seen in the last N days
            db_path: Optional database path

        Returns:
            Number of companies exported
        """
        companies = get_companies_with_signal_count(days=days, db_path=db_path)

        headers = [
            "name",
            "domain",
            "website",
            "country",
            "first_seen",
            "last_seen",
            "signal_count",
            "latest_signal_type",
            "latest_source_url",
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()

            for company in companies:
                writer.writerow({
                    "name": company.get("name", ""),
                    "domain": company.get("domain", ""),
                    "website": company.get("website", ""),
                    "country": company.get("country", ""),
                    "first_seen": company.get("first_seen", ""),
                    "last_seen": company.get("last_seen", ""),
                    "signal_count": company.get("signal_count", 0),
                    "latest_signal_type": company.get("latest_signal_type", ""),
                    "latest_source_url": company.get("latest_source_url", ""),
                })

        return len(companies)

    @staticmethod
    def export_signals(
        output_path: Path,
        days: Optional[int] = None,
        signal_type: Optional[str] = None,
        db_path: Optional[Path] = None,
    ) -> int:
        """
        Export signals to CSV.

        Args:
            output_path: Path to write the CSV file
            days: Only include signals from the last N days
            signal_type: Filter by signal type
            db_path: Optional database path

        Returns:
            Number of signals exported
        """
        signals = get_all_signals(days=days, signal_type=signal_type, db_path=db_path)

        headers = [
            "company_name",
            "company_domain",
            "signal_type",
            "title",
            "snippet",
            "source_url",
            "found_date",
        ]

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()

            for signal in signals:
                writer.writerow({
                    "company_name": signal.get("company_name", ""),
                    "company_domain": signal.get("company_domain", ""),
                    "signal_type": signal.get("signal_type", ""),
                    "title": signal.get("title", ""),
                    "snippet": signal.get("snippet", ""),
                    "source_url": signal.get("source_url", ""),
                    "found_date": signal.get("found_date", ""),
                })

        return len(signals)
