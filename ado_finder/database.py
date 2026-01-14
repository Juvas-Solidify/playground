"""Database module for SQLite operations."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Generator, Optional


DEFAULT_DB_PATH = Path.home() / ".ado-finder" / "data.db"


def get_db_path() -> Path:
    """Get the database path, creating directory if needed."""
    db_path = DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


@contextmanager
def get_connection(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection as a context manager."""
    path = db_path or get_db_path()
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize the database with required tables."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Create companies table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                domain TEXT UNIQUE,
                website TEXT,
                first_seen DATE,
                last_seen DATE,
                country TEXT,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create signals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY,
                company_id INTEGER REFERENCES companies(id),
                signal_type TEXT,
                source_url TEXT,
                title TEXT,
                snippet TEXT,
                found_date DATE,
                raw_data JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_companies_domain ON companies(domain)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_companies_last_seen ON companies(last_seen)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_company_id ON signals(company_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_signals_found_date ON signals(found_date)
        """)

        conn.commit()


def get_company_by_domain(domain: str, db_path: Optional[Path] = None) -> Optional[dict]:
    """Get a company by its domain."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM companies WHERE domain = ?", (domain,))
        row = cursor.fetchone()
        return dict(row) if row else None


def upsert_company(
    name: str,
    domain: str,
    website: Optional[str] = None,
    country: Optional[str] = None,
    source: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> int:
    """
    Insert or update a company record.

    If domain exists, update last_seen.
    If domain is new, create new record.

    Returns the company ID.
    """
    today = date.today().isoformat()

    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Check if company exists
        existing = get_company_by_domain(domain, db_path)

        if existing:
            # Update last_seen
            cursor.execute(
                "UPDATE companies SET last_seen = ? WHERE id = ?",
                (today, existing["id"])
            )
            conn.commit()
            return existing["id"]
        else:
            # Insert new company
            cursor.execute(
                """
                INSERT INTO companies (name, domain, website, first_seen, last_seen, country, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (name, domain, website, today, today, country, source)
            )
            conn.commit()
            return cursor.lastrowid


def add_signal(
    company_id: int,
    signal_type: str,
    source_url: str,
    title: Optional[str] = None,
    snippet: Optional[str] = None,
    raw_data: Optional[dict] = None,
    db_path: Optional[Path] = None,
) -> int:
    """Add a signal for a company."""
    today = date.today().isoformat()
    raw_json = json.dumps(raw_data) if raw_data else None

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO signals (company_id, signal_type, source_url, title, snippet, found_date, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (company_id, signal_type, source_url, title, snippet, today, raw_json)
        )
        conn.commit()
        return cursor.lastrowid


def get_companies(
    days: Optional[int] = None,
    country: Optional[str] = None,
    source: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Get companies with optional filters."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        query = "SELECT * FROM companies WHERE 1=1"
        params: list[Any] = []

        if days is not None:
            query += " AND last_seen >= date('now', ?)"
            params.append(f"-{days} days")

        if country:
            query += " AND country = ?"
            params.append(country)

        if source:
            query += " AND source = ?"
            params.append(source)

        query += " ORDER BY last_seen DESC"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_signals_for_company(company_id: int, db_path: Optional[Path] = None) -> list[dict]:
    """Get all signals for a company."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM signals WHERE company_id = ? ORDER BY found_date DESC",
            (company_id,)
        )
        return [dict(row) for row in cursor.fetchall()]


def get_all_signals(
    days: Optional[int] = None,
    signal_type: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Get all signals with optional filters."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        query = """
            SELECT s.*, c.name as company_name, c.domain as company_domain
            FROM signals s
            JOIN companies c ON s.company_id = c.id
            WHERE 1=1
        """
        params: list[Any] = []

        if days is not None:
            query += " AND s.found_date >= date('now', ?)"
            params.append(f"-{days} days")

        if signal_type:
            query += " AND s.signal_type = ?"
            params.append(signal_type)

        query += " ORDER BY s.found_date DESC"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_stats(db_path: Optional[Path] = None) -> dict:
    """Get database statistics."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Total companies
        cursor.execute("SELECT COUNT(*) FROM companies")
        total_companies = cursor.fetchone()[0]

        # Total signals
        cursor.execute("SELECT COUNT(*) FROM signals")
        total_signals = cursor.fetchone()[0]

        # Companies by source
        cursor.execute("""
            SELECT source, COUNT(*) as count
            FROM companies
            GROUP BY source
            ORDER BY count DESC
        """)
        companies_by_source = {row[0]: row[1] for row in cursor.fetchall()}

        # Companies by country
        cursor.execute("""
            SELECT country, COUNT(*) as count
            FROM companies
            WHERE country IS NOT NULL
            GROUP BY country
            ORDER BY count DESC
        """)
        companies_by_country = {row[0]: row[1] for row in cursor.fetchall()}

        # Signals by type
        cursor.execute("""
            SELECT signal_type, COUNT(*) as count
            FROM signals
            GROUP BY signal_type
            ORDER BY count DESC
        """)
        signals_by_type = {row[0]: row[1] for row in cursor.fetchall()}

        # Recent activity (last 7 days)
        cursor.execute("""
            SELECT COUNT(*) FROM companies
            WHERE first_seen >= date('now', '-7 days')
        """)
        new_companies_7d = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM signals
            WHERE found_date >= date('now', '-7 days')
        """)
        new_signals_7d = cursor.fetchone()[0]

        return {
            "total_companies": total_companies,
            "total_signals": total_signals,
            "companies_by_source": companies_by_source,
            "companies_by_country": companies_by_country,
            "signals_by_type": signals_by_type,
            "new_companies_7d": new_companies_7d,
            "new_signals_7d": new_signals_7d,
        }


def get_companies_with_signal_count(
    days: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Get companies with their signal counts and latest signal info."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        query = """
            SELECT
                c.*,
                COUNT(s.id) as signal_count,
                (SELECT signal_type FROM signals WHERE company_id = c.id ORDER BY found_date DESC LIMIT 1) as latest_signal_type,
                (SELECT source_url FROM signals WHERE company_id = c.id ORDER BY found_date DESC LIMIT 1) as latest_source_url
            FROM companies c
            LEFT JOIN signals s ON c.id = s.company_id
        """
        params: list[Any] = []

        if days is not None:
            query += " WHERE c.last_seen >= date('now', ?)"
            params.append(f"-{days} days")

        query += " GROUP BY c.id ORDER BY c.last_seen DESC"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def signal_exists(company_id: int, source_url: str, db_path: Optional[Path] = None) -> bool:
    """Check if a signal with the same source URL already exists for a company."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM signals WHERE company_id = ? AND source_url = ?",
            (company_id, source_url)
        )
        return cursor.fetchone() is not None
