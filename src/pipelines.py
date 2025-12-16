"""Scrapy pipelines for processing scraped items.

MetadataPipeline handles file downloads, storage, and metadata persistence.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from scrapy import Spider
from scrapy.exceptions import DropItem

from src.models import RecordMetadata
from src.storage import MongoDBStorage, MinIOStorage, FileDownloader, HTMLScraper
from src.config import mongodb_settings, minio_settings
from src.ingest import WRCSpider

logger = logging.getLogger(__name__)


class MetadataPipeline:
    """Pipeline for downloading files and storing metadata."""

    def __init__(self) -> None:
        """Initialize pipeline components."""
        self.mongo_storage: MongoDBStorage
        self.minio_storage: MinIOStorage
        self.file_downloader: FileDownloader
        self.html_scraper: HTMLScraper
        self.spider: Spider

    def open_spider(self, spider: Spider) -> None:
        """Initialize storage connections when spider opens.

        Args:
            spider: The spider that was opened
        """
        self.spider = spider

        # Initialize MongoDB storage
        self.mongo_storage = MongoDBStorage(
            mongo_uri=mongodb_settings.uri,
            database=mongodb_settings.database,
            collection=mongodb_settings.collection,
        )
        logger.info("Initialized MongoDB storage for pipeline")

        # Initialize MinIO storage
        self.minio_storage = MinIOStorage(
            endpoint=minio_settings.endpoint,
            access_key=minio_settings.access_key,
            secret_key=minio_settings.secret_key,
            bucket_name=minio_settings.bucket,
            secure=False,
        )
        logger.info("Initialized MinIO storage for pipeline")

        # Initialize file downloader and HTML scraper
        self.file_downloader = FileDownloader(timeout=30, max_retries=3)
        self.html_scraper = HTMLScraper(timeout=30)

        logger.info("MetadataPipeline initialized successfully")

    def close_spider(self, spider: Spider) -> None:
        """Clean up resources when spider closes.

        Args:
            spider: The spider that was closed
        """
        if self.mongo_storage:
            self.mongo_storage.close()

        if self.file_downloader:
            self.file_downloader.close()

        if self.html_scraper:
            self.html_scraper.close()

        logger.info("MetadataPipeline closed successfully")

    def process_item(self, item: RecordMetadata, spider: Spider) -> RecordMetadata:
        """Process scraped item: download files, store in MinIO, save metadata to MongoDB.

        Args:
            item: Scraped metadata record
            spider: Spider that scraped the item

        Returns:
            Processed item

        Raises:
            DropItem: If item processing fails critically
        """
        try:
            identifier = item.get("identifier")
            doc_link = item.get("doc_link")

            if not identifier or not doc_link:
                logger.error("Missing identifier or doc_link in item")
                raise DropItem(f"Missing required fields: identifier={identifier}, doc_link={doc_link}")

            # Check if record already exists in MongoDB
            existing_record = self.mongo_storage.find_by_identifier(identifier)
            if existing_record:
                logger.info(f"Record {identifier} already exists, skipping")
                return item

            logger.info(f"Processing record {identifier} with doc_link {doc_link}")

            # Download and analyze the document
            try:
                file_data, file_hash, mime_type = self.file_downloader.download(doc_link)
                item["mime_type"] = mime_type

                # Check if it's an HTML page
                is_html = self.file_downloader.is_html_page(mime_type, file_data)

                if is_html:
                    # HTML page: scrape and store as .html
                    logger.info(f"Document is HTML page for {identifier}, scraping content")
                    file_path = self._process_html_document(
                        identifier=identifier,
                        url=doc_link,
                        html_content=file_data.decode("utf-8", errors="ignore"),
                    )
                    # Recalculate hash for the cleaned HTML
                    file_hash = hashlib.sha256(file_data).hexdigest()
                else:
                    # PDF/DOC/other: store as-is
                    logger.info(f"Document is {mime_type} for {identifier}, storing directly")
                    file_path = self._process_direct_document(
                        identifier=identifier,
                        file_data=file_data,
                        mime_type=mime_type,
                        url=doc_link,
                    )

                # Update item with file information
                item["file_path"] = file_path
                item["file_hash"] = file_hash
                item["updated_at"] = datetime.now().isoformat()

                logger.info(
                    f"Successfully processed {identifier}: path={file_path}, hash={file_hash[:8]}"
                )

            except Exception as e:
                logger.error(f"Error downloading/processing file for {identifier}: {e}", exc_info=True)
                item["status"] = "error"
                item["notes"] = f"File processing error: {str(e)}"
                item["updated_at"] = datetime.now().isoformat()

            # Store metadata in MongoDB
            try:
                # Convert item to dict for MongoDB
                item_dict = dict(item)
                # Set status to 'extracted' when successfully saving record and its docs
                if "status" not in item_dict or item_dict["status"] != "error":
                    item_dict["status"] = "extracted"
                self.mongo_storage.insert_one(item_dict)
                logger.info(f"Stored metadata for {identifier} in MongoDB with status={item_dict['status']}")
            except Exception as e:
                logger.error(f"Error storing metadata for {identifier}: {e}", exc_info=True)
                raise DropItem(f"Failed to store metadata: {str(e)}")

            return item

        except DropItem:
            raise
        except Exception as e:
            logger.error(f"Unexpected error processing item: {e}", exc_info=True)
            raise DropItem(f"Unexpected error: {str(e)}")

    def _process_direct_document(
        self,
        identifier: str,
        file_data: bytes,
        mime_type: str,
        url: str,
    ) -> str:
        """Process and store PDF/DOC/other documents directly in MinIO.

        Args:
            identifier: Record identifier
            file_data: File content
            mime_type: MIME type
            url: Source URL

        Returns:
            File path in MinIO bucket
        """
        # Get appropriate file extension
        file_ext = self.file_downloader.get_file_extension(url, mime_type)

        # Generate object name: identifier + extension
        object_name = f"{identifier}{file_ext}"

        # Upload to MinIO
        file_path = self.minio_storage.upload_file(
            file_data=file_data,
            object_name=object_name,
            content_type=mime_type,
        )

        logger.info(f"Stored direct document for {identifier} at {file_path}")
        return file_path

    def _process_html_document(
        self,
        identifier: str,
        url: str,
        html_content: str,
    ) -> str:
        """Process and store HTML document in MinIO.

        For HTML pages, scrape the page and store as .html file.

        Args:
            identifier: Record identifier
            url: Source URL
            html_content: Pre-downloaded HTML content

        Returns:
            File path in MinIO bucket
        """
        # Use the already downloaded content or re-scrape for cleaner version
        try:
            # Re-scrape for cleaner HTML and proper hash
            cleaned_html, file_hash = self.html_scraper.scrape_page(url)
            html_bytes = cleaned_html.encode("utf-8")
        except Exception as e:
            logger.warning(f"Failed to re-scrape HTML for {identifier}, using original: {e}")
            html_bytes = html_content.encode("utf-8")

        # Generate object name with .html extension
        object_name = f"{identifier}.html"

        # Upload to MinIO
        file_path = self.minio_storage.upload_file(
            file_data=html_bytes,
            object_name=object_name,
            content_type="text/html",
        )

        logger.info(f"Stored HTML document for {identifier} at {file_path}")
        return file_path
