"""Transformation module for processing landing zone data.

Processes raw data from landing zone bucket and stores cleaned data in processed bucket.
Handles HTML content extraction, file renaming, and metadata updates.
"""
from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from src.storage import MongoDBStorage, MinIOStorage

logger = logging.getLogger(__name__)


def calculate_file_hash(file_data: bytes) -> str:
    """Calculate SHA256 hash of file data.

    Args:
        file_data: File content as bytes

    Returns:
        SHA256 hash as hexadecimal string
    """
    return hashlib.sha256(file_data).hexdigest()


def get_file_extension(mime_type: str) -> str:
    """Get file extension from MIME type.

    Args:
        mime_type: MIME type string

    Returns:
        File extension with dot (e.g., '.pdf', '.html')
    """
    mime_to_ext = {
        "application/pdf": ".pdf",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "text/html": ".html",
        "text/htm": ".html",
        "text/plain": ".txt",
    }
    
    # Normalize mime type (remove charset and other parameters)
    if ";" in mime_type:
        mime_type = mime_type.split(";")[0].strip()
    
    return mime_to_ext.get(mime_type.lower(), ".bin")


def validate_date_range(start_date: str, end_date: str) -> bool:
    """Validate date range format and logic.

    Args:
        start_date: Start date in ISO format (YYYY-MM-DD)
        end_date: End date in ISO format (YYYY-MM-DD)

    Returns:
        True if dates are valid

    Raises:
        ValueError: If dates are invalid or end_date < start_date
    """
    try:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
        
        if end < start:
            raise ValueError(f"End date ({end_date}) must be greater than or equal to start date ({start_date})")
        
        return True
    except ValueError as e:
        if "does not match format" in str(e) or "Invalid isoformat string" in str(e):
            raise ValueError(f"Invalid date format. Expected ISO format (YYYY-MM-DD): {e}")
        raise


class HTMLContentExtractor:
    """Extract relevant content from HTML files using BeautifulSoup.
    
    Removes navigation elements, headers, footers, and extracts main content.
    """

    def __init__(self) -> None:
        """Initialize HTML content extractor."""
        logger.debug("HTMLContentExtractor initialized")

    def extract_content(self, html_content: str) -> str:
        """Remove navigation, headers, footers, and extract main content.

        Args:
            html_content: Raw HTML content as string

        Returns:
            Cleaned HTML content as string
        """
        try:
            soup = BeautifulSoup(html_content, "html.parser")
            
            # Remove unwanted elements
            self._remove_unwanted_elements(soup)
            
            # Extract main content
            cleaned_html = self._extract_main_content(soup)
            
            logger.debug(
                "HTML content extracted: original=%d cleaned=%d",
                len(html_content),
                len(cleaned_html),
            )
            
            return cleaned_html
            
        except Exception as e:
            logger.error("Error extracting HTML content: %s", e)
            raise

    def _remove_unwanted_elements(self, soup: BeautifulSoup) -> None:
        """Remove navigation, headers, footers, scripts, and styles.

        Args:
            soup: BeautifulSoup object (modified in place)
        """
        # Elements to remove
        unwanted_tags = [
            "nav",
            "header",
            "footer",
            "script",
            "style",
            "noscript",
            "iframe",
        ]
        
        for tag in unwanted_tags:
            for element in soup.find_all(tag):
                element.decompose()
        
        # Remove elements with common navigation/sidebar classes
        unwanted_classes = [
            "navigation",
            "nav",
            "sidebar",
            "menu",
            "header",
            "footer",
            "breadcrumb",
            "pagination",
            "advertisement",
            "ads",
            "social-share",
            "related-posts",
            "comments",
        ]
        
        for class_name in unwanted_classes:
            for element in soup.find_all(class_=lambda x: isinstance(x, str) and class_name in x.lower()):
                element.decompose()
        
        # Remove button elements
        for button in soup.find_all("button"):
            button.decompose()
        
        # Remove elements with role="navigation"
        for element in soup.find_all(attrs={"role": "navigation"}):
            element.decompose()

    def _extract_main_content(self, soup: BeautifulSoup) -> str:
        """Extract main content area from cleaned soup.

        Args:
            soup: BeautifulSoup object with unwanted elements removed

        Returns:
            HTML string of main content
        """
        # Try to find main content container in order of preference
        content_selectors = [
            ("main", None),
            ("article", None),
            ("div", "content"),
            ("div", "main"),
            ("div", "main-content"),
            ("div", "article"),
            ("div", "post"),
            ("div", "entry-content"),
            ("section", "content"),
        ]
        
        for tag, class_name in content_selectors:
            if class_name:
                element = soup.find(tag, class_=lambda x: isinstance(x, str) and class_name in x.lower())
            else:
                element = soup.find(tag)
            
            if element:
                logger.debug("Main content found in <%s> tag", tag)
                return str(element)
        
        # If no main content container found, return body or full soup
        body = soup.find("body")
        if body:
            logger.debug("Main content not found, using <body>")
            return str(body)
        
        logger.debug("Main content not found, using full document")
        return str(soup)


class FileProcessor:
    """Process files based on their type (PDF/DOC vs HTML)."""

    def __init__(self) -> None:
        """Initialize file processor."""
        self.html_extractor = HTMLContentExtractor()
        logger.debug("FileProcessor initialized")

    def process_file(
        self,
        file_data: bytes,
        mime_type: str,
        identifier: str,
    ) -> Tuple[bytes, str, str]:
        """Process file based on MIME type and return processed data.

        Args:
            file_data: Raw file content as bytes
            mime_type: MIME type of the file
            identifier: Unique identifier for the file

        Returns:
            Tuple of (processed_data, new_hash, new_filename)
        """
        # Normalize mime type
        if ";" in mime_type:
            mime_type = mime_type.split(";")[0].strip()
        
        mime_type = mime_type.lower()
        
        # Route to appropriate handler
        if mime_type in ["text/html", "text/htm"]:
            return self._process_html(file_data, identifier, mime_type)
        elif mime_type in [
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]:
            return self._process_document(file_data, mime_type, identifier)
        else:
            logger.warning("Unknown MIME type %s, treating as document", mime_type)
            return self._process_document(file_data, mime_type, identifier)

    def _process_html(
        self,
        html_data: bytes,
        identifier: str,
        mime_type: str,
    ) -> Tuple[bytes, str, str]:
        """Clean HTML content and return processed data.

        Args:
            html_data: Raw HTML content as bytes
            identifier: Unique identifier for the file
            mime_type: MIME type

        Returns:
            Tuple of (processed_data, new_hash, new_filename)
        """
        try:
            # Decode HTML
            html_string = html_data.decode("utf-8", errors="ignore")
            
            # Extract main content
            cleaned_html = self.html_extractor.extract_content(html_string)
            
            # Convert back to bytes
            processed_data = cleaned_html.encode("utf-8")
            
            # Calculate new hash
            new_hash = calculate_file_hash(processed_data)
            
            # Generate new filename
            extension = get_file_extension(mime_type)
            new_filename = f"{identifier}{extension}"
            
            logger.info(
                "HTML processed: identifier=%s original_size=%d processed_size=%d",
                identifier,
                len(html_data),
                len(processed_data),
            )
            
            return processed_data, new_hash, new_filename
            
        except Exception as e:
            logger.error("Error processing HTML for %s: %s", identifier, e)
            raise

    def _process_document(
        self,
        doc_data: bytes,
        mime_type: str,
        identifier: str,
    ) -> Tuple[bytes, str, str]:
        """Pass through PDF/DOC unchanged with new filename.

        Args:
            doc_data: Document content as bytes
            mime_type: MIME type of the document
            identifier: Unique identifier for the file

        Returns:
            Tuple of (processed_data, new_hash, new_filename)
        """
        # No transformation for documents
        processed_data = doc_data
        
        # Calculate hash (unchanged)
        new_hash = calculate_file_hash(processed_data)
        
        # Generate new filename
        extension = get_file_extension(mime_type)
        new_filename = f"{identifier}{extension}"
        
        logger.info(
            "Document processed (no transformation): identifier=%s size=%d type=%s",
            identifier,
            len(doc_data),
            mime_type,
        )
        
        return processed_data, new_hash, new_filename


class TransformationPipeline:
    """Main transformation pipeline orchestrator.
    
    Fetches records from MongoDB, processes files from landing zone,
    and stores results in processed bucket and collection.
    """

    def __init__(
        self,
        mongo_uri: str,
        mongo_db: str,
        source_collection: str,
        dest_collection: str,
        minio_endpoint: str,
        minio_access_key: str,
        minio_secret_key: str,
        source_bucket: str,
        dest_bucket: str,
        secure: bool = False,
    ) -> None:
        """Initialize transformation pipeline with storage connections.

        Args:
            mongo_uri: MongoDB connection URI
            mongo_db: MongoDB database name
            source_collection: Source collection name (landing zone)
            dest_collection: Destination collection name (processed)
            minio_endpoint: MinIO endpoint (host:port)
            minio_access_key: MinIO access key
            minio_secret_key: MinIO secret key
            source_bucket: Source bucket name (landing-zone)
            dest_bucket: Destination bucket name (processed)
            secure: Use HTTPS for MinIO if True
        """
        # Initialize MongoDB connections
        self.source_db = MongoDBStorage(
            mongo_uri=mongo_uri,
            database=mongo_db,
            collection=source_collection,
        )
        self.dest_db = MongoDBStorage(
            mongo_uri=mongo_uri,
            database=mongo_db,
            collection=dest_collection,
        )
        
        # Initialize MinIO connections
        self.source_storage = MinIOStorage(
            endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            bucket_name=source_bucket,
            secure=secure,
        )
        self.dest_storage = MinIOStorage(
            endpoint=minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            bucket_name=dest_bucket,
            secure=secure,
        )
        
        # Initialize file processor
        self.file_processor = FileProcessor()
        
        logger.info(
            "TransformationPipeline initialized: source=%s/%s dest=%s/%s",
            source_bucket,
            source_collection,
            dest_bucket,
            dest_collection,
        )

    def transform(
        self,
        start_date: str,
        end_date: str,
    ) -> Dict[str, int]:
        """Execute transformation pipeline for given date range.

        Args:
            start_date: Start date in ISO format (YYYY-MM-DD)
            end_date: End date in ISO format (YYYY-MM-DD)

        Returns:
            Dictionary with statistics:
                - total: Total records fetched
                - processed: Successfully processed records
                - failed: Failed records
                - skipped: Skipped records
        """
        # Validate date range
        validate_date_range(start_date, end_date)
        
        logger.info(
            "Starting transformation pipeline: start_date=%s end_date=%s",
            start_date,
            end_date,
        )
        
        # Initialize statistics
        stats = {
            "total": 0,
            "processed": 0,
            "failed": 0,
            "skipped": 0,
        }
        
        # Fetch records from source collection
        records = self.source_db.find_by_date_range(
            start_date=start_date,
            end_date=end_date,
            status="extracted",
        )
        
        stats["total"] = len(records)
        logger.info("Fetched %d records from source collection", stats["total"])
        
        # Process each record
        for idx, record in enumerate(records, 1):
            identifier = record.get("identifier", "unknown")
            
            try:
                # Process record
                processed_record = self._process_record(record)
                
                if processed_record:
                    stats["processed"] += 1
                    logger.debug(
                        "Processed record %d/%d: %s",
                        idx,
                        stats["total"],
                        identifier,
                    )
                else:
                    stats["skipped"] += 1
                    logger.warning("Skipped record %d/%d: %s", idx, stats["total"], identifier)
                
                # Log progress every 10 records
                if idx % 10 == 0:
                    logger.info(
                        "Progress: %d/%d processed (%.1f%%)",
                        idx,
                        stats["total"],
                        (idx / stats["total"]) * 100,
                    )
                    
            except Exception as e:
                stats["failed"] += 1
                logger.error(
                    "Failed to process record %d/%d (%s): %s",
                    idx,
                    stats["total"],
                    identifier,
                    e,
                )
        
        logger.info(
            "Transformation pipeline completed: %s",
            stats,
        )
        
        return stats

    def _process_record(self, record: Dict) -> Optional[Dict]:
        """Process single record through transformation pipeline.

        Args:
            record: Source record from MongoDB

        Returns:
            Processed record dictionary or None if processing failed
        """
        identifier = record.get("identifier")
        file_path = record.get("file_path")
        mime_type = record.get("mime_type")
        
        # Validate required fields
        if not all([identifier, file_path, mime_type]):
            logger.warning(
                "Missing required fields in record: identifier=%s file_path=%s mime_type=%s",
                identifier,
                file_path,
                mime_type,
            )
            return None
        
        # Type assertions after validation
        assert isinstance(identifier, str)
        assert isinstance(file_path, str)
        assert isinstance(mime_type, str)
        
        try:
            # Extract object name from file_path (format: bucket/object_name)
            object_name = file_path.split("/", 1)[1] if "/" in file_path else file_path
            
            # Download file from source bucket
            file_data = self.source_storage.download_file(object_name)
            
            # Process file based on type
            processed_data, new_hash, new_filename = self.file_processor.process_file(
                file_data=file_data,
                mime_type=mime_type,
                identifier=identifier,
            )
            
            # Upload to destination bucket
            new_file_path = self.dest_storage.upload_file(
                file_data=processed_data,
                object_name=new_filename,
                content_type=mime_type,
            )
            
            # Create new metadata record
            processed_record = {
                **record,  # Copy all original fields
                "file_path": new_file_path,
                "file_hash": new_hash,
                "updated_at": datetime.now().isoformat(),
                "transformation_date": datetime.now().isoformat(),
                "status": "transformed",
            }
            
            # Remove MongoDB _id field if present
            processed_record.pop("_id", None)
            
            # Insert into destination collection
            self.dest_db.insert_one(processed_record)
            
            logger.info(
                "Record processed successfully: identifier=%s new_path=%s",
                identifier,
                new_filename,
            )
            
            return processed_record
            
        except Exception as e:
            logger.error("Error processing record %s: %s", identifier, e)
            raise

    def close(self) -> None:
        """Close all storage connections."""
        self.source_db.close()
        self.dest_db.close()
        logger.info("TransformationPipeline closed")


def run_transformation_pipeline(
    start_date: str,
    end_date: str,
    mongo_uri: str = "mongodb://localhost:27017/",
    mongo_db: str = "workplace_relations",
    source_collection: str = "records",
    dest_collection: str = "processed_records",
    minio_endpoint: str = "localhost:9000",
    minio_access_key: str = "admin",
    minio_secret_key: str = "adminadmin",
    source_bucket: str = "landing-zone",
    dest_bucket: str = "processed",
) -> Dict[str, int]:
    """Run transformation pipeline with configuration.

    Args:
        start_date: Start date in ISO format (YYYY-MM-DD)
        end_date: End date in ISO format (YYYY-MM-DD)
        mongo_uri: MongoDB connection URI
        mongo_db: MongoDB database name
        source_collection: Source collection name
        dest_collection: Destination collection name
        minio_endpoint: MinIO endpoint
        minio_access_key: MinIO access key
        minio_secret_key: MinIO secret key
        source_bucket: Source bucket name
        dest_bucket: Destination bucket name

    Returns:
        Dictionary with transformation statistics
    """
    pipeline = TransformationPipeline(
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
    
    try:
        stats = pipeline.transform(start_date=start_date, end_date=end_date)
        return stats
    finally:
        pipeline.close()
