"""CLI interface for the Azure DevOps Lead Finder."""

import logging
from enum import Enum
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .config import Config, SourceConfig, create_default_config, load_config
from .database import (
    add_signal,
    get_companies_with_signal_count,
    get_stats,
    init_db,
    signal_exists,
    upsert_company,
)
from .exporters import CSVExporter
from .scrapers import LinkedInScraper
from .scrapers.base import GracefulInterrupt
from .utils import extract_domain, setup_logging


app = typer.Typer(
    name="ado-finder",
    help="Azure DevOps Lead Finder - Identify companies using Azure DevOps by monitoring job postings.",
    add_completion=False,
)
console = Console()


class SourceType(str, Enum):
    """Available data sources."""
    linkedin = "linkedin"
    indeed = "indeed"


class ExportFormat(str, Enum):
    """Available export formats."""
    csv = "csv"


def version_callback(value: bool):
    """Print version and exit."""
    if value:
        console.print(f"ado-finder version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=version_callback,
        is_eager=True,
    ),
):
    """Azure DevOps Lead Finder CLI."""
    # Initialize database
    init_db()


@app.command()
def search(
    source: SourceType = typer.Option(
        SourceType.linkedin,
        "--source",
        "-s",
        help="Data source to search.",
    ),
    query: str = typer.Option(
        "Azure DevOps",
        "--query",
        "-q",
        help="Search query.",
    ),
    country: Optional[str] = typer.Option(
        None,
        "--country",
        "-c",
        help="Country to filter by (e.g., 'Sweden', 'Norway').",
    ),
    max_results: int = typer.Option(
        100,
        "--max-results",
        "-m",
        help="Maximum number of results to fetch.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Enable verbose logging.",
    ),
):
    """
    Search for companies using Azure DevOps.

    Searches job postings for Azure DevOps related keywords and stores
    the findings in the database.
    """
    # Setup logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logger = setup_logging(log_level)

    config = load_config()

    console.print(f"[bold blue]Searching {source.value} for '{query}'...[/bold blue]")
    if country:
        console.print(f"[dim]Filtering by country: {country}[/dim]")

    # Get source configuration
    source_config = config.sources.get(
        source.value,
        SourceConfig()
    )
    source_config.max_results_per_query = max_results

    # Select scraper based on source
    if source == SourceType.linkedin:
        scraper_class = LinkedInScraper
    else:
        console.print(f"[red]Source '{source.value}' is not yet implemented.[/red]")
        raise typer.Exit(1)

    new_companies = 0
    updated_companies = 0
    new_signals = 0

    try:
        with scraper_class(source_config) as scraper:
            jobs = scraper.search(query=query, country=country, max_results=max_results)

            console.print(f"\n[green]Found {len(jobs)} job postings[/green]")

            with console.status("[bold green]Processing results...") as status:
                for i, job in enumerate(jobs):
                    status.update(f"[bold green]Processing {i + 1}/{len(jobs)}...")

                    # Extract domain from company URL or job URL
                    domain = None
                    if job.company_url:
                        domain = extract_domain(job.company_url)
                    if not domain and job.job_url:
                        # Try to extract from LinkedIn company URL patterns
                        domain = extract_domain(job.company_url) if job.company_url else None

                    if not domain:
                        # Generate a pseudo-domain from company name
                        domain = job.company_name.lower().replace(" ", "-") + ".unknown"
                        logger.debug(
                            f"No domain found for {job.company_name}, using: {domain}"
                        )

                    # Determine country from job location
                    job_country = country
                    if job.location and not job_country:
                        # Simple country detection from location string
                        location_lower = job.location.lower()
                        for c in ["sweden", "norway", "denmark", "finland"]:
                            if c in location_lower:
                                job_country = c.title()
                                break

                    # Upsert company
                    from .database import get_company_by_domain
                    existing = get_company_by_domain(domain)
                    is_new = existing is None

                    company_id = upsert_company(
                        name=job.company_name,
                        domain=domain,
                        website=job.company_url,
                        country=job_country,
                        source=source.value,
                    )

                    if is_new:
                        new_companies += 1
                    else:
                        updated_companies += 1

                    # Add signal if not duplicate
                    if not signal_exists(company_id, job.job_url):
                        add_signal(
                            company_id=company_id,
                            signal_type="job_posting",
                            source_url=job.job_url,
                            title=job.job_title,
                            snippet=job.snippet,
                            raw_data=job.raw_data,
                        )
                        new_signals += 1

            console.print("\n[bold green]Search complete![/bold green]")
            console.print(f"  New companies: {new_companies}")
            console.print(f"  Updated companies: {updated_companies}")
            console.print(f"  New signals: {new_signals}")

    except KeyboardInterrupt:
        console.print("\n[yellow]Search interrupted. Partial results have been saved.[/yellow]")
        console.print(f"  New companies: {new_companies}")
        console.print(f"  Updated companies: {updated_companies}")
        console.print(f"  New signals: {new_signals}")
    except Exception as e:
        logger.exception(f"Search failed: {e}")
        console.print(f"[red]Search failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def export(
    format: ExportFormat = typer.Option(
        ExportFormat.csv,
        "--format",
        "-f",
        help="Export format.",
    ),
    output: Path = typer.Option(
        Path("companies.csv"),
        "--output",
        "-o",
        help="Output file path.",
    ),
    include_signals: bool = typer.Option(
        False,
        "--include-signals",
        help="Export signals instead of companies.",
    ),
    days: Optional[int] = typer.Option(
        None,
        "--days",
        "-d",
        help="Only include records from the last N days.",
    ),
):
    """
    Export data to a file.

    By default exports companies. Use --include-signals to export signals instead.
    """
    try:
        if include_signals:
            count = CSVExporter.export_signals(output, days=days)
            console.print(f"[green]Exported {count} signals to {output}[/green]")
        else:
            count = CSVExporter.export_companies(output, days=days)
            console.print(f"[green]Exported {count} companies to {output}[/green]")
    except Exception as e:
        console.print(f"[red]Export failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def stats():
    """
    Show database statistics.

    Displays counts of companies, signals, and recent activity.
    """
    try:
        data = get_stats()

        console.print("\n[bold blue]Database Statistics[/bold blue]\n")

        # Summary table
        summary_table = Table(title="Summary", show_header=False)
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")

        summary_table.add_row("Total Companies", str(data["total_companies"]))
        summary_table.add_row("Total Signals", str(data["total_signals"]))
        summary_table.add_row("New Companies (7 days)", str(data["new_companies_7d"]))
        summary_table.add_row("New Signals (7 days)", str(data["new_signals_7d"]))

        console.print(summary_table)

        # Companies by source
        if data["companies_by_source"]:
            console.print("\n[bold]Companies by Source[/bold]")
            source_table = Table(show_header=True)
            source_table.add_column("Source", style="cyan")
            source_table.add_column("Count", style="green", justify="right")

            for source, count in data["companies_by_source"].items():
                source_table.add_row(source or "Unknown", str(count))

            console.print(source_table)

        # Companies by country
        if data["companies_by_country"]:
            console.print("\n[bold]Companies by Country[/bold]")
            country_table = Table(show_header=True)
            country_table.add_column("Country", style="cyan")
            country_table.add_column("Count", style="green", justify="right")

            for country, count in data["companies_by_country"].items():
                country_table.add_row(country or "Unknown", str(count))

            console.print(country_table)

        # Signals by type
        if data["signals_by_type"]:
            console.print("\n[bold]Signals by Type[/bold]")
            type_table = Table(show_header=True)
            type_table.add_column("Type", style="cyan")
            type_table.add_column("Count", style="green", justify="right")

            for signal_type, count in data["signals_by_type"].items():
                type_table.add_row(signal_type or "Unknown", str(count))

            console.print(type_table)

    except Exception as e:
        console.print(f"[red]Failed to get stats: {e}[/red]")
        raise typer.Exit(1)


@app.command("list")
def list_companies(
    days: int = typer.Option(
        7,
        "--days",
        "-d",
        help="Show companies seen in the last N days.",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        "-l",
        help="Maximum number of companies to display.",
    ),
):
    """
    List recently found companies.

    Shows companies discovered or updated in the last N days.
    """
    try:
        companies = get_companies_with_signal_count(days=days)[:limit]

        if not companies:
            console.print(f"[yellow]No companies found in the last {days} days.[/yellow]")
            return

        table = Table(title=f"Companies (last {days} days)")
        table.add_column("Company", style="cyan")
        table.add_column("Domain", style="dim")
        table.add_column("Country", style="green")
        table.add_column("Signals", justify="right")
        table.add_column("First Seen")
        table.add_column("Last Seen")

        for company in companies:
            table.add_row(
                company.get("name", "Unknown"),
                company.get("domain", ""),
                company.get("country", ""),
                str(company.get("signal_count", 0)),
                company.get("first_seen", ""),
                company.get("last_seen", ""),
            )

        console.print(table)
        console.print(f"\n[dim]Showing {len(companies)} of {len(get_companies_with_signal_count(days=days))} companies[/dim]")

    except Exception as e:
        console.print(f"[red]Failed to list companies: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def init(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Overwrite existing configuration.",
    ),
):
    """
    Initialize the tool with default configuration.

    Creates the database and configuration file if they don't exist.
    """
    from .config import DEFAULT_CONFIG_PATH

    try:
        # Initialize database
        init_db()
        console.print("[green]Database initialized.[/green]")

        # Create config if needed
        if DEFAULT_CONFIG_PATH.exists() and not force:
            console.print(f"[yellow]Configuration already exists at {DEFAULT_CONFIG_PATH}[/yellow]")
            console.print("[dim]Use --force to overwrite.[/dim]")
        else:
            create_default_config()
            console.print(f"[green]Configuration created at {DEFAULT_CONFIG_PATH}[/green]")

        console.print("\n[bold green]Initialization complete![/bold green]")
        console.print("\nNext steps:")
        console.print("  1. Edit the config file to customize search queries and regions")
        console.print("  2. Run 'ado-finder search' to start finding companies")

    except Exception as e:
        console.print(f"[red]Initialization failed: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
