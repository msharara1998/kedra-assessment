"""Manual test script for extraction functionality.

Run this script directly without pytest to test the extraction process.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime
import argparse
import logging

# Add parent directory to path to enable imports
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scrapy.crawler import CrawlerProcess
from extraction import WRCSpider
from src.config import scrapy_settings

logger = logging.getLogger(__name__)


def extract_workplace_relations_data(
    start_date: str,
    end_date: str,
    body_type: str,
    output_format: str = "json",
    output_file: Optional[str] = None,
) -> Dict[str, Any]:
    """Extract workplace relations decisions metadata using Scrapy.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        body_type: Comma-separated body types (e.g., "WRC", "Labour Court", "EAT", "Equality Tribunal")
        output_format: Output format (json, csv, xml) - default: json
        output_file: Optional output file path

    Returns:
        Dictionary containing extraction statistics

    Raises:
        ValueError: If date format is invalid or end_date is before start_date
    """
    # Validate date formats
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"Invalid date format. Use YYYY-MM-DD: {e}") from e

    if end < start:
        raise ValueError("end_date must be on or after start_date")

    # Validate body types
    valid_bodies = {
        "WRC": "Workplace Relations Commission",
        "Labour Court": "Labour Court",
        "EAT": "Employment Appeals Tribunal",
        "Equality Tribunal": "Equality Tribunal",
    }

    bodies_list = [b.strip() for b in body_type.split(",") if b.strip()]
    for body in bodies_list:
        if body not in valid_bodies:
            logger.warning(f"Body type '{body}' may not be recognized. Valid: {list(valid_bodies.keys())}")

    logger.info(
        f"Starting extraction: {start_date} to {end_date}, bodies={body_type}"
    )

    # Get Scrapy settings
    settings = scrapy_settings.to_scrapy_dict().copy()

    if output_file:
        settings["FEEDS"] = {output_file: {"format": output_format}}

    # Create and run crawler
    process = CrawlerProcess(settings)

    process.crawl(
        WRCSpider,
        start_date=start_date,
        end_date=end_date,
        bodies=bodies_list,
    )

    try:
        process.start()
        logger.info("Extraction completed successfully")
        return {
            "status": "success",
            "start_date": start_date,
            "end_date": end_date,
            "bodies": bodies_list,
            "output_file": output_file,
        }
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "start_date": start_date,
            "end_date": end_date,
        }


def run_extraction_cli() -> None:
    """Run extraction from command line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract Workplace Relations decisions metadata"
    )
    parser.add_argument(
        "--start-date",
        required=True,
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        required=True,
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--body-type",
        required=True,
        help='Body type(s), comma-separated (e.g., "WRC,Labour Court")',
    )
    parser.add_argument(
        "--output",
        help="Output file path",
    )
    parser.add_argument(
        "--format",
        default="json",
        choices=["json", "csv", "xml"],
        help="Output format (default: json)",
    )

    args = parser.parse_args()

    result = extract_workplace_relations_data(
        start_date=args.start_date,
        end_date=args.end_date,
        body_type=args.body_type,
        output_format=args.format,
        output_file=args.output,
    )

    if result["status"] == "success":
        print(f"✓ Extraction completed: {result}")
    else:
        print(f"✗ Extraction failed: {result['error']}")
        exit(1)


if __name__ == "__main__":
    run_extraction_cli()
