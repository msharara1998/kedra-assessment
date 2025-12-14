"""Storage module for MongoDB and MinIO operations.

Provides high-level interfaces for storing metadata and files.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from io import BytesIO
from typing import Dict, Optional, List
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from minio import Minio
from minio.error import S3Error
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

logger = logging.getLogger(__name__)


class MongoDBStorage:
    """MongoDB storage for metadata management."""

    def __init__(
        self,
        mongo_uri: str,
        database: str,
        collection: str,
    ) -> None:
        """Initialize MongoDB storage.

        Args:
            mongo_uri: MongoDB connection URI
            database: Database name
            collection: Collection name
        """
        self.client: MongoClient = MongoClient(mongo_uri)
        self.db: Database = self.client[database]
        self.collection: Collection = self.db[collection]
        logger.info(
            "MongoDB storage initialized: db=%s collection=%s",
            database,
            collection,
        )

    def insert_one(self, document: Dict) -> str:
        """Insert a single document.

        Args:
            document: Document to insert

        Returns:
            Inserted document ID as string
        """
        result = self.collection.insert_one(document)
        return str(result.inserted_id)

    def insert_many(self, documents: List[Dict]) -> List[str]:
        """Insert multiple documents.

        Args:
            documents: List of documents to insert

        Returns:
            List of inserted document IDs as strings
        """
        if not documents:
            return []
        result = self.collection.insert_many(documents)
        return [str(id) for id in result.inserted_ids]

    def find_by_identifier(self, identifier: str) -> Optional[Dict]:
        """Find document by identifier.

        Args:
            identifier: Unique identifier

        Returns:
            Document if found, None otherwise
        """
        return self.collection.find_one({"identifier": identifier})

    def find_by_date_range(
        self,
        start_date: str,
        end_date: str,
        status: Optional[str] = None,
    ) -> List[Dict]:
        """Find documents by partition date range.

        Args:
            start_date: Start date in ISO format
            end_date: End date in ISO format
            status: Optional status filter

        Returns:
            List of matching documents
        """
        query: Dict = {
            "partition_date": {"$gte": start_date, "$lte": end_date}
        }
        if status:
            query["status"] = status

        return list(self.collection.find(query))

    def update_by_identifier(
        self,
        identifier: str,
        updates: Dict,
    ) -> bool:
        """Update document by identifier.

        Args:
            identifier: Document identifier
            updates: Fields to update

        Returns:
            True if document was updated, False otherwise
        """
        updates["updated_at"] = datetime.now().isoformat()
        result = self.collection.update_one(
            {"identifier": identifier},
            {"$set": updates},
        )
        return result.modified_count > 0

    def close(self) -> None:
        """Close MongoDB connection."""
        self.client.close()
        logger.info("MongoDB connection closed")


class MinIOStorage:
    """MinIO object storage for file management."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        secure: bool = False,
    ) -> None:
        """Initialize MinIO storage.

        Args:
            endpoint: MinIO endpoint (host:port)
            access_key: Access key
            secret_key: Secret key
            bucket_name: Bucket name
            secure: Use HTTPS if True
        """
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self.bucket_name = bucket_name
        self._ensure_bucket_exists()
        logger.info("MinIO storage initialized: bucket=%s", bucket_name)

    def _ensure_bucket_exists(self) -> None:
        """Create bucket if it doesn't exist."""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info("Created bucket: %s", self.bucket_name)
        except S3Error as e:
            logger.error("Error ensuring bucket exists: %s", e)
            raise

    def upload_file(
        self,
        file_data: bytes,
        object_name: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload file to MinIO.

        Args:
            file_data: File content as bytes
            object_name: Object name/path in bucket
            content_type: MIME type

        Returns:
            Object path in bucket
        """
        try:
            file_stream = BytesIO(file_data)
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=file_stream,
                length=len(file_data),
                content_type=content_type,
            )
            logger.info(
                "Uploaded file: bucket=%s object=%s size=%d",
                self.bucket_name,
                object_name,
                len(file_data),
            )
            return f"{self.bucket_name}/{object_name}"
        except S3Error as e:
            logger.error("Error uploading file %s: %s", object_name, e)
            raise

    def download_file(self, object_name: str) -> bytes:
        """Download file from MinIO.

        Args:
            object_name: Object name/path in bucket

        Returns:
            File content as bytes
        """
        try:
            response = self.client.get_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
            )
            data = response.read()
            response.close()
            response.release_conn()
            logger.info(
                "Downloaded file: bucket=%s object=%s size=%d",
                self.bucket_name,
                object_name,
                len(data),
            )
            return data
        except S3Error as e:
            logger.error("Error downloading file %s: %s", object_name, e)
            raise

    def file_exists(self, object_name: str) -> bool:
        """Check if file exists in bucket.

        Args:
            object_name: Object name/path in bucket

        Returns:
            True if file exists, False otherwise
        """
        try:
            self.client.stat_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
            )
            return True
        except S3Error:
            return False


class FileDownloader:
    """HTTP file downloader with hash calculation."""

    def __init__(
        self,
        timeout: int = 30,
        max_retries: int = 3,
        user_agent: Optional[str] = None,
    ) -> None:
        """Initialize file downloader.

        Args:
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            user_agent: Custom user agent string
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            )
        })
        logger.info("FileDownloader initialized with timeout=%d", timeout)

    def download(self, url: str) -> tuple[bytes, str, str]:
        """Download file from URL with hash calculation.

        Args:
            url: URL to download from

        Returns:
            Tuple of (file_data, file_hash, mime_type)

        Raises:
            requests.RequestException: If download fails after retries
        """
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                response = self.session.get(
                    url,
                    timeout=self.timeout,
                    stream=True,
                )
                response.raise_for_status()

                # Read content and calculate hash
                content = response.content
                file_hash = hashlib.sha256(content).hexdigest()
                mime_type = response.headers.get(
                    "Content-Type",
                    "application/octet-stream",
                )

                # Extract base MIME type
                if ";" in mime_type:
                    mime_type = mime_type.split(";")[0].strip()

                logger.info(
                    "Downloaded %s: size=%d hash=%s mime=%s",
                    url,
                    len(content),
                    file_hash[:8],
                    mime_type,
                )

                return content, file_hash, mime_type

            except requests.RequestException as e:
                last_exception = e
                logger.warning(
                    "Download attempt %d/%d failed for %s: %s",
                    attempt + 1,
                    self.max_retries,
                    url,
                    str(e),
                )

        logger.error("Failed to download %s after %d attempts", url, self.max_retries)
        raise last_exception or requests.RequestException(f"Failed to download {url}")

    def is_html_page(self, mime_type: str, content: bytes) -> bool:
        """Check if content is an HTML page.

        Args:
            mime_type: MIME type from response
            content: Content bytes

        Returns:
            True if content is HTML, False otherwise
        """
        # Check MIME type
        if mime_type.startswith("text/html"):
            return True
        
        # Check content for HTML indicators
        try:
            text_content = content[:1024].decode("utf-8", errors="ignore").lower()
            return "<!doctype html" in text_content or "<html" in text_content
        except Exception:
            return False

    def get_file_extension(self, url: str, mime_type: str) -> str:
        """Determine file extension from URL or MIME type.

        Args:
            url: File URL
            mime_type: MIME type

        Returns:
            File extension with dot (e.g., '.pdf', '.html')
        """
        # Try to extract extension from URL
        parsed_url = urlparse(url)
        path = parsed_url.path
        if "." in path:
            ext = os.path.splitext(path)[1].lower()
            if ext in {".pdf", ".doc", ".docx", ".html", ".htm", ".txt"}:
                return ext

        # Fall back to MIME type mapping
        mime_to_ext = {
            "application/pdf": ".pdf",
            "application/msword": ".doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
            "text/html": ".html",
            "text/plain": ".txt",
        }

        return mime_to_ext.get(mime_type, ".bin")

    def close(self) -> None:
        """Close HTTP session."""
        self.session.close()
        logger.info("FileDownloader session closed")


class HTMLScraper:
    """HTML web page scraper for extracting and storing web content."""

    def __init__(
        self,
        timeout: int = 30,
        user_agent: Optional[str] = None,
    ) -> None:
        """Initialize HTML scraper.

        Args:
            timeout: Request timeout in seconds
            user_agent: Custom user agent string
        """
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": user_agent or (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
            )
        })
        logger.info("HTMLScraper initialized with timeout=%d", timeout)

    def scrape_page(self, url: str) -> tuple[str, str]:
        """Scrape HTML page content.

        Args:
            url: URL of the page to scrape

        Returns:
            Tuple of (html_content, file_hash)

        Raises:
            requests.RequestException: If scraping fails
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()

            # Parse and clean HTML
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Get the full HTML content
            html_content = str(soup)
            
            # Calculate hash of the HTML content
            content_bytes = html_content.encode("utf-8")
            file_hash = hashlib.sha256(content_bytes).hexdigest()

            logger.info(
                "Scraped HTML page %s: size=%d hash=%s",
                url,
                len(content_bytes),
                file_hash[:8],
            )

            return html_content, file_hash

        except requests.RequestException as e:
            logger.error("Failed to scrape HTML page %s: %s", url, str(e))
            raise

    def close(self) -> None:
        """Close HTTP session."""
        self.session.close()
        logger.info("HTMLScraper session closed")
