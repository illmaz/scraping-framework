import os
import json
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)


class OutputManager:
    """
    Single entry point for all output operations.
    Reads the 'format' key from the site config and
    delegates to the correct writer.

    Usage:
        manager = OutputManager(config)
        manager.save(data)   # data is a list of dicts
    """

    def __init__(self, config: dict):
        # Store the full site config so writers can read
        # filename, format, and other settings from it
        self.config = config

        # Instantiate the correct writer based on config
        self.writer = self._get_writer()

    def _get_writer(self):
        # Read the format from the output section of the site YAML
        # e.g. output: {format: "json"} -> "json"
        fmt = self.config.get("output", {}).get("format", "json")

        if fmt == "json":
            return JsonWriter(self.config)
        elif fmt == "csv":
            return CsvWriter(self.config)
        elif fmt == "postgres":
            return PostgresWriter(self.config)
        else:
            # Fail immediately with a clear message rather than
            # silently writing nothing after a full scrape run
            raise ValueError(f"Unsupported output format: '{fmt}'. Use json, csv, or postgres.")

    def save(self, data: list[dict]):
        """
        Save scraped data. Called by every scraper the same way.
        The writer handles the actual format-specific logic.
        """
        if not data:
            logger.warning("No data to save - skipping output")
            return

        logger.info(f"Saving {len(data)} records via {self.writer.__class__.__name__}")
        self.writer.save(data)


class JsonWriter:
    """
    Writes scraped data to a timestamped JSON file.
    Output: output/books_20250503.json
    """

    def __init__(self, config: dict):
        self.config = config

    def save(self, data: list[dict]):
        # Build the output path from config settings
        base_dir = self.config.get("output", {}).get("base_dir", "output")
        filename = self.config.get("output", {}).get("filename", "scrape")
        timestamp = datetime.now().strftime("%Y%m%d")

        # pathlib Path handles cross-platform path separators automatically
        output_dir = Path(base_dir)

        # parents=True: create nested dirs if needed (e.g. output/books/)
        # exist_ok=True: don't crash if the folder already exists
        output_dir.mkdir(parents=True, exist_ok=True)

        filepath = output_dir / f"{filename}_{timestamp}.json"

        with open(filepath, "w", encoding="utf-8") as f:
            # indent=2 makes the JSON human-readable
            # ensure_ascii=False preserves unicode characters (e.g. £ signs)
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"JSON saved to {filepath} ({len(data)} records)")


class CsvWriter:
    """
    Writes scraped data to a timestamped CSV file using pandas.
    Output: output/hockey_stats_20250503.csv
    """

    def __init__(self, config: dict):
        self.config = config

    def save(self, data: list[dict]):
        base_dir = self.config.get("output", {}).get("base_dir", "output")
        filename = self.config.get("output", {}).get("filename", "scrape")
        timestamp = datetime.now().strftime("%Y%m%d")

        output_dir = Path(base_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        filepath = output_dir / f"{filename}_{timestamp}.csv"

        # pd.DataFrame(data) converts list of dicts to a DataFrame
        # Each dict key becomes a column header
        # Each dict becomes a row
        df = pd.DataFrame(data)

        # index=False stops pandas writing a useless 0,1,2,3 index column
        df.to_csv(filepath, index=False, encoding="utf-8")

        logger.info(f"CSV saved to {filepath} ({len(df)} rows, {len(df.columns)} columns)")


class PostgresWriter:
    """
    Writes scraped data to a PostgreSQL table using pandas + SQLAlchemy.
    Reads DATABASE_URL from .env file.
    Creates the table if it doesn't exist.
    Appends rows on subsequent runs - never drops existing data.

    Output: a table in your Supabase PostgreSQL database
    """

    def __init__(self, config: dict):
        self.config = config

    def save(self, data: list[dict]):
        # load_dotenv() reads your .env file and puts DATABASE_URL
        # into os.environ so os.getenv() can access it
        load_dotenv()

        db_url = os.getenv("DATABASE_URL")

        if not db_url:
            raise EnvironmentError(
                "DATABASE_URL not found. "
                "Check your .env file has: DATABASE_URL=postgresql://..."
            )

        # Table name comes from the site config filename field
        # e.g. filename: "quotes" -> table name: "quotes"
        table_name = self.config.get("output", {}).get("filename", "scrape")

        # SQLAlchemy create_engine sets up a connection pool
        # pandas needs this to talk to PostgreSQL
        # The URL format: postgresql://user:password@host:port/dbname
        engine = create_engine(db_url)

        df = pd.DataFrame(data)

        # to_sql writes the DataFrame to a PostgreSQL table
        # if_exists="append": add rows to existing table, never drop data
        # if_exists="replace": drop and recreate table (destructive - don't use in production)
        # if_exists="fail": raise error if table exists
        # index=False: don't write the pandas row index as a column
        df.to_sql(
            name=table_name,
            con=engine,
            if_exists="append",
            index=False
        )

        logger.info(f"PostgreSQL: inserted {len(df)} rows into table '{table_name}'")

        # Always dispose the engine to close connection pool cleanly
        engine.dispose()