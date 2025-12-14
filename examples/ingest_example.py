"""Example script demonstrating ingestion pipeline usage.

This script shows how to programmatically run the ingestion process
without using command-line arguments.
"""
from datetime import date
import logging
import os

from dotenv import load_dotenv
from scrapy.crawler import CrawlerProcess

from src.config import scrapy_settings
from extraction import WRCSpider

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Run ingestion example."""
    # Define parameters
    start_date = "2024-01-01"
    end_date = "2024-01-31"
    bodies = ["WRC"]  # Can include: WRC, LC, EAT, ET
    output_file = "example_results.json"

    logger.info("Starting ingestion example")
    logger.info("Date range: %s to %s", start_date, end_date)
    logger.info("Bodies: %s", ", ".join(bodies))

    # Configure Scrapy settings
    settings = scrapy_settings.to_scrapy_dict().copy()
    settings["FEEDS"] = {
        output_file: {
            "format": "json",
            "encoding": "utf8",
            "store_empty": False,
            "indent": 2,
        }
    }

    # Create crawler process
    process = CrawlerProcess(settings=settings)

    # Add spider to crawler
    process.crawl(
        WRCSpider,
        start_date=start_date,
        end_date=end_date,
        bodies=bodies,
    )

    # Start crawling (blocking call)
    logger.info("Starting crawler...")
    process.start()

    logger.info("Ingestion completed successfully")
    logger.info("Results saved to: %s", output_file)


if __name__ == "__main__":
    main()
