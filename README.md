# Azure DevOps Lead Finder

A Python CLI tool that identifies companies using Azure DevOps by monitoring job postings. Stores findings in SQLite with deduplication and export capabilities.

## Features

- **Job Scraping**: Search LinkedIn for Azure DevOps related job postings
- **Company Tracking**: Automatically deduplicate companies by domain
- **Signal Collection**: Track job postings, press releases, and other signals
- **Export**: Export findings to CSV format
- **Statistics**: View database statistics and recent activity

## Installation

### Prerequisites

- Python 3.11 or higher
- pip or pipx for installation

### Install from source

```bash
# Clone the repository
git clone <repository-url>
cd ado-finder

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install the package
pip install -e .

# Install Playwright browsers
playwright install chromium
```

### Quick install with pipx

```bash
pipx install .
playwright install chromium
```

## Usage

### Initialize the tool

```bash
ado-finder init
```

This creates the database and configuration file at `~/.ado-finder/`.

### Search for companies

```bash
# Basic search
ado-finder search --source linkedin --query "Azure DevOps"

# Search in a specific country
ado-finder search --source linkedin --query "Azure DevOps" --country Sweden

# Limit results
ado-finder search --source linkedin --query "Azure Pipelines" --max-results 50 --country Norway

# Enable verbose logging
ado-finder search --query "Azure DevOps Engineer" --verbose
```

### Export results

```bash
# Export companies to CSV
ado-finder export --output companies.csv

# Export with signals included
ado-finder export --output signals.csv --include-signals

# Export only recent data
ado-finder export --output recent.csv --days 7
```

### View statistics

```bash
ado-finder stats
```

### List recent findings

```bash
# Show companies from the last 7 days
ado-finder list

# Show companies from the last 30 days
ado-finder list --days 30

# Limit output
ado-finder list --days 14 --limit 10
```

### Show version

```bash
ado-finder --version
```

## Configuration

The configuration file is located at `~/.ado-finder/config.yaml`:

```yaml
sources:
  linkedin:
    enabled: true
    max_results_per_query: 100
    delay_seconds: [2, 5]  # Random delay range between requests
  indeed:
    enabled: false
    max_results_per_query: 100
    delay_seconds: [2, 5]

search_queries:
  - "Azure DevOps"
  - "Azure DevOps Engineer"
  - "Azure Pipelines"
  - "Azure Boards"

regions:
  - Sweden
  - Norway
  - Denmark
  - Finland
```

## Data Model

### Companies Table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| name | TEXT | Company name |
| domain | TEXT | Domain (unique, used for deduplication) |
| website | TEXT | Company website URL |
| first_seen | DATE | Date first discovered |
| last_seen | DATE | Date last seen/updated |
| country | TEXT | Country |
| source | TEXT | Data source (e.g., "linkedin") |
| created_at | TIMESTAMP | Record creation time |

### Signals Table

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER | Primary key |
| company_id | INTEGER | Foreign key to companies |
| signal_type | TEXT | Type (e.g., "job_posting") |
| source_url | TEXT | Original URL |
| title | TEXT | Job/article title |
| snippet | TEXT | Relevant excerpt |
| found_date | DATE | Date found |
| raw_data | JSON | Full scraped data |
| created_at | TIMESTAMP | Record creation time |

## Data Storage

All data is stored in:
- Database: `~/.ado-finder/data.db`
- Configuration: `~/.ado-finder/config.yaml`
- Logs: `~/.ado-finder/ado-finder.log`

## Deduplication Logic

1. Extract domain from company website or LinkedIn URL
2. Strip common prefixes (www, careers, jobs, etc.)
3. If domain exists in database → update `last_seen`, add new signal
4. If domain is new → create company record and signal

## Error Handling

- Failed requests are retried 3x with exponential backoff
- All errors are logged to `~/.ado-finder/ado-finder.log`
- Processing continues if a single page fails
- Partial results are saved on interrupt (Ctrl+C)

## Development

### Run tests

```bash
pip install -e ".[dev]"
pytest
```

### Code structure

```
ado_finder/
├── __init__.py         # Package initialization
├── cli.py              # CLI interface (typer)
├── config.py           # Configuration handling
├── database.py         # SQLite operations
├── utils.py            # Utility functions
├── scrapers/
│   ├── __init__.py
│   ├── base.py         # Base scraper class
│   └── linkedin.py     # LinkedIn scraper
└── exporters/
    ├── __init__.py
    └── csv_exporter.py # CSV export
```

## Roadmap

### Phase 2 Extensions
- [ ] Indeed job search
- [ ] Arbetsförmedlingen API (Swedish job board)
- [ ] Google News search for press releases

### Nice-to-haves
- [ ] Company size enrichment
- [ ] Slack/email notifications
- [ ] Scheduled runs via cron
- [ ] Web dashboard with Streamlit

## License

MIT License
