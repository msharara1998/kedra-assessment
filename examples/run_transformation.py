"""Example script demonstrating the transformation pipeline.

This script shows how to run the transformation pipeline to process
documents from the landing zone to the processed bucket.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.transform import run_transformation_pipeline
from src.config import mongodb_settings, minio_settings

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the transformation pipeline."""
    # Get configuration from settings
    mongo_uri = mongodb_settings.uri
    mongo_db = mongodb_settings.database
    source_collection = mongodb_settings.collection
    dest_collection = mongodb_settings.processed_collection
    
    minio_endpoint = minio_settings.endpoint
    minio_access_key = minio_settings.access_key
    minio_secret_key = minio_settings.secret_key
    source_bucket = minio_settings.bucket
    dest_bucket = minio_settings.processed_bucket
    
    # Define date range (modify as needed)
    # Example: Process all records from December 2024
    start_date = "2024-12-01"
    end_date = "2024-12-31"
    
    logger.info("=" * 80)
    logger.info("Transformation Pipeline")
    logger.info("=" * 80)
    logger.info("Configuration:")
    logger.info("  MongoDB: %s/%s", mongo_db, source_collection)
    logger.info("  Source Bucket: %s", source_bucket)
    logger.info("  Destination Bucket: %s", dest_bucket)
    logger.info("  Destination Collection: %s", dest_collection)
    logger.info("  Date Range: %s to %s", start_date, end_date)
    logger.info("=" * 80)
    
    try:
        # Run transformation pipeline
        stats = run_transformation_pipeline(
            start_date=start_date,
            end_date=end_date,
            mongo_uri=mongo_uri,
            mongo_db=mongo_db,
            source_collection=source_collection,
            dest_collection=dest_collection,
            minio_endpoint=minio_endpoint,
            minio_access_key=minio_access_key,
            minio_secret_key=minio_secret_key,
            source_bucket=source_bucket,
            dest_bucket=dest_bucket,
        )
        
        # Display results
        logger.info("=" * 80)
        logger.info("Transformation Complete!")
        logger.info("=" * 80)
        logger.info("Statistics:")
        logger.info("  Total Records: %d", stats["total"])
        logger.info("  Processed: %d", stats["processed"])
        logger.info("  Failed: %d", stats["failed"])
        logger.info("  Skipped: %d", stats["skipped"])
        logger.info("=" * 80)
        
        if stats["failed"] > 0:
            logger.warning("Some records failed to process. Check logs for details.")
            sys.exit(1)
        
        logger.info("All records processed successfully!")
        
    except Exception as e:
        logger.error("Transformation pipeline failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
