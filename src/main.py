"""Main entry point for the data pipeline.

Provides a command-line interface to run ingestion and transformation processes.
"""
import argparse
import logging
import sys
import os
from datetime import date

# Add project root to python path to allow imports from src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from scrapy.crawler import CrawlerProcess

from src.config import scrapy_settings, mongodb_settings, minio_settings
from src.ingest import WRCSpider, run_ingestion_pipeline
from src.transform import run_transformation_pipeline

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


def run_ingestion(args):
    """Run the complete ingestion pipeline."""
    logger.info("Starting ingestion process")
    logger.info("Date range: %s to %s", args.start_date, args.end_date)

    bodies = args.bodies.split(",") if args.bodies else None
    if bodies:
        logger.info("Bodies: %s", ", ".join(bodies))
    else:
        logger.info("Bodies: All (default)")

    try:
        # Configure Scrapy settings
        settings = scrapy_settings.to_scrapy_dict()

        # If output file is specified, add JSON export feed
        if args.output:
            settings["FEEDS"] = {
                args.output: {
                    "format": "json",
                    "encoding": "utf8",
                    "store_empty": False,
                    "indent": 2,
                }
            }

        # Run ingestion pipeline (scraping + file downloads + MongoDB/MinIO storage)
        stats = run_ingestion_pipeline(
            start_date=args.start_date,
            end_date=args.end_date,
            bodies=bodies,
            mongo_uri=mongodb_settings.uri,
            mongo_db=mongodb_settings.database,
            mongo_collection=mongodb_settings.collection,
            minio_endpoint=minio_settings.endpoint,
            minio_access_key=minio_settings.access_key,
            minio_secret_key=minio_settings.secret_key,
            minio_bucket=minio_settings.bucket,
            scrapy_settings=settings,
        )

        logger.info("Ingestion statistics: %s", stats)

    except Exception as e:
        logger.error("Ingestion failed: %s", e, exc_info=True)
        sys.exit(1)


def run_transformation(args):
    """Run the transformation process."""
    logger.info("Starting transformation process")
    logger.info("Date range: %s to %s", args.start_date, args.end_date)

    try:
        stats = run_transformation_pipeline(
            start_date=args.start_date,
            end_date=args.end_date,
            mongo_uri=mongodb_settings.uri,
            mongo_db=mongodb_settings.database,
            source_collection=mongodb_settings.collection,
            dest_collection=mongodb_settings.processed_collection,
            minio_endpoint=minio_settings.endpoint,
            minio_access_key=minio_settings.access_key,
            minio_secret_key=minio_settings.secret_key,
            source_bucket=minio_settings.bucket,
            dest_bucket=minio_settings.processed_bucket,
        )

        logger.info("Transformation statistics: %s", stats)

        if stats["failed"] > 0:
            logger.warning("Some records failed to process.")
            sys.exit(1)

    except Exception as e:
        logger.error("Transformation failed: %s", e, exc_info=True)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Workplace Relations Data Pipeline")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    subparsers.required = True

    # Ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Run data ingestion (scraping)")
    ingest_parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    ingest_parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    ingest_parser.add_argument("--bodies", help="Comma-separated list of bodies (e.g., WRC,LC)")
    ingest_parser.add_argument("--output", help="Output JSON file for scraped items (optional)")
    ingest_parser.set_defaults(func=run_ingestion)

    # Transform command
    transform_parser = subparsers.add_parser("transform", help="Run data transformation")
    transform_parser.add_argument("--start-date", required=True, help="Start date (YYYY-MM-DD)")
    transform_parser.add_argument("--end-date", required=True, help="End date (YYYY-MM-DD)")
    transform_parser.set_defaults(func=run_transformation)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
