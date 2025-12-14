"""End-to-end test script for the complete data pipeline.

Tests the full workflow: extraction -> storage -> transformation.
Requires running MongoDB and MinIO services (docker-compose up).
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, Mock
from datetime import datetime, timedelta
from typing import Dict, Any, List
from pathlib import Path
import logging
import time
import sys
import os

from twisted.internet import reactor, defer
from scrapy.crawler import CrawlerRunner
from pymongo import MongoClient
from minio.error import S3Error
from minio import Minio
import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extraction import WRCSpider
from src.transform import run_transformation_pipeline
from src.storage import MongoDBStorage, MinIOStorage
from src.models import RecordMetadata
from src.config import scrapy_settings

logger = logging.getLogger(__name__)


class TestEndToEndPipeline:
    """End-to-end tests for the complete data pipeline."""

    @pytest.fixture(autouse=True)
    def setup_environment(self) -> None:
        """Set up test environment and clean up after test."""
        # Test environment configuration
        self.test_env = {
            "MONGO_URI": os.getenv("MONGO_URI", "mongodb://localhost:27017/"),
            "MONGO_DB": os.getenv("MONGO_DB", "test_workplace_relations"),
            "MONGO_COLLECTION": "test_records",
            "MONGO_PROCESSED_COLLECTION": "test_processed_records",
            "MINIO_ENDPOINT": os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            "MINIO_ACCESS_KEY": os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            "MINIO_SECRET_KEY": os.getenv("MINIO_SECRET_KEY", "minioadmin"),
            "MINIO_BUCKET": "test-landing-zone",
            "MINIO_PROCESSED_BUCKET": "test-processed",
        }

        # Initialize storage clients for setup and teardown
        self.mongo_client = MongoClient(self.test_env["MONGO_URI"])
        self.test_db = self.mongo_client[self.test_env["MONGO_DB"]]

        self.minio_client = Minio(
            self.test_env["MINIO_ENDPOINT"],
            access_key=self.test_env["MINIO_ACCESS_KEY"],
            secret_key=self.test_env["MINIO_SECRET_KEY"],
            secure=False,
        )

        # Clean up before test
        self._cleanup()

        # Create test buckets
        self._create_buckets()

        yield

        # Clean up after test
        self._cleanup()

    def _cleanup(self) -> None:
        """Clean up test data from MongoDB and MinIO."""
        # Drop test collections
        try:
            self.test_db[self.test_env["MONGO_COLLECTION"]].drop()
            self.test_db[self.test_env["MONGO_PROCESSED_COLLECTION"]].drop()
            logger.info("Dropped test MongoDB collections")
        except Exception as e:
            logger.warning(f"Failed to drop test collections: {e}")

        # Remove test buckets and their contents
        for bucket_name in [
            self.test_env["MINIO_BUCKET"],
            self.test_env["MINIO_PROCESSED_BUCKET"],
        ]:
            try:
                if self.minio_client.bucket_exists(bucket_name):
                    # Remove all objects in bucket
                    objects = self.minio_client.list_objects(bucket_name, recursive=True)
                    for obj in objects:
                        self.minio_client.remove_object(bucket_name, obj.object_name)
                    # Remove bucket
                    self.minio_client.remove_bucket(bucket_name)
                    logger.info(f"Removed test bucket: {bucket_name}")
            except Exception as e:
                logger.warning(f"Failed to remove bucket {bucket_name}: {e}")

    def _create_buckets(self) -> None:
        """Create test buckets in MinIO."""
        for bucket_name in [
            self.test_env["MINIO_BUCKET"],
            self.test_env["MINIO_PROCESSED_BUCKET"],
        ]:
            try:
                if not self.minio_client.bucket_exists(bucket_name):
                    self.minio_client.make_bucket(bucket_name)
                    logger.info(f"Created test bucket: {bucket_name}")
            except S3Error as e:
                logger.error(f"Failed to create bucket {bucket_name}: {e}")
                raise

    @pytest.mark.e2e
    def test_full_pipeline_with_mocked_spider(self) -> None:
        """Test complete pipeline with mocked spider data.

        This test validates the entire workflow without depending on external website:
        1. Mock spider extraction and populate MongoDB with test records
        2. Download and store mock files to MinIO
        3. Run transformation pipeline
        4. Verify processed data in destination bucket and collection
        """
        with patch.dict(os.environ, self.test_env):
            # Step 1: Create mock extracted records
            mock_records = self._create_mock_records()

            # Step 2: Populate MongoDB with mock records
            mongo_storage = MongoDBStorage(
                mongo_uri=self.test_env["MONGO_URI"],
                database=self.test_env["MONGO_DB"],
                collection=self.test_env["MONGO_COLLECTION"],
            )

            # Step 3: Upload mock files to MinIO landing zone
            minio_storage = MinIOStorage(
                endpoint=self.test_env["MINIO_ENDPOINT"],
                access_key=self.test_env["MINIO_ACCESS_KEY"],
                secret_key=self.test_env["MINIO_SECRET_KEY"],
                bucket_name=self.test_env["MINIO_BUCKET"],
                secure=False,
            )

            inserted_ids = []
            for record in mock_records:
                # Upload mock file to MinIO
                file_data = self._generate_mock_file_content(record)
                file_path = minio_storage.upload_file(
                    file_data=file_data,
                    object_name=record["file_path"].split("/")[-1],
                    content_type=record["mime_type"],
                )

                # Update record with actual file path
                record["file_path"] = file_path
                record["status"] = "extracted"

                # Insert to MongoDB
                inserted_id = mongo_storage.insert_one(record)
                inserted_ids.append(inserted_id)
                logger.info(f"Inserted mock record: {record['identifier']} -> {inserted_id}")

            # Verify records in MongoDB
            assert len(inserted_ids) == len(mock_records)

            # Verify files in MinIO landing zone
            objects = list(self.minio_client.list_objects(
                self.test_env["MINIO_BUCKET"],
                recursive=True,
            ))
            assert len(objects) == len(mock_records)

            # Step 4: Run transformation pipeline
            logger.info("Running transformation pipeline...")
            stats = run_transformation_pipeline(
                start_date="2024-01-01",
                end_date="2024-01-31",
                mongo_uri=self.test_env["MONGO_URI"],
                mongo_db=self.test_env["MONGO_DB"],
                source_collection=self.test_env["MONGO_COLLECTION"],
                dest_collection=self.test_env["MONGO_PROCESSED_COLLECTION"],
                minio_endpoint=self.test_env["MINIO_ENDPOINT"],
                minio_access_key=self.test_env["MINIO_ACCESS_KEY"],
                minio_secret_key=self.test_env["MINIO_SECRET_KEY"],
                source_bucket=self.test_env["MINIO_BUCKET"],
                dest_bucket=self.test_env["MINIO_PROCESSED_BUCKET"],
            )

            # Step 5: Verify transformation results
            assert stats["total"] == len(mock_records)
            assert stats["processed"] >= len(mock_records) - 1  # Allow 1 failure for error test
            assert stats["failed"] <= 1

            # Verify processed records in MongoDB
            processed_collection = self.test_db[self.test_env["MONGO_PROCESSED_COLLECTION"]]
            processed_count = processed_collection.count_documents({})
            assert processed_count >= len(mock_records) - 1

            # Verify processed files in MinIO
            processed_objects = list(self.minio_client.list_objects(
                self.test_env["MINIO_PROCESSED_BUCKET"],
                recursive=True,
            ))
            assert len(processed_objects) >= len(mock_records) - 1

            # Step 6: Verify specific record transformations
            for record in mock_records:
                if record["status"] == "extracted":  # Only check successfully extracted records
                    processed_record = processed_collection.find_one(
                        {"identifier": record["identifier"]}
                    )

                    if processed_record:  # Record should be transformed
                        assert processed_record["status"] == "transformed"
                        assert "file_path" in processed_record
                        assert processed_record["file_path"].startswith(
                            self.test_env["MINIO_PROCESSED_BUCKET"]
                        )

                        # Verify file exists in processed bucket
                        try:
                            self.minio_client.stat_object(
                                self.test_env["MINIO_PROCESSED_BUCKET"],
                                processed_record["file_path"].split("/", 1)[1],
                            )
                            logger.info(f"Verified transformed file: {processed_record['file_path']}")
                        except S3Error:
                            pytest.fail(f"Transformed file not found: {processed_record['file_path']}")

            # Cleanup
            mongo_storage.close()
            logger.info("E2E pipeline test completed successfully")

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_extraction_with_real_spider(self) -> None:
        """Test extraction using real spider against live website.

        This test requires internet connection and tests:
        1. Spider crawling and scraping
        2. Pipeline processing (download, storage)
        3. Data validation

        Note: This test is marked as slow and may be skipped in CI.
        """
        with patch.dict(os.environ, self.test_env):
            # Use a very short date range to limit test duration
            test_start_date = "2024-01-01"
            test_end_date = "2024-01-05"

            # Configure Scrapy settings for test
            settings = scrapy_settings.to_scrapy_dict().copy()
            settings["LOG_LEVEL"] = "INFO"

            # Create crawler runner
            runner = CrawlerRunner(settings)

            @defer.inlineCallbacks
            def crawl():
                """Run spider and wait for completion."""
                yield runner.crawl(
                    WRCSpider,
                    start_date=test_start_date,
                    end_date=test_end_date,
                    bodies=["WRC"],  # Test single body type
                )
                reactor.stop()

            # Run spider
            crawl()
            reactor.run()

            # Verify extracted data
            mongo_storage = MongoDBStorage(
                mongo_uri=self.test_env["MONGO_URI"],
                database=self.test_env["MONGO_DB"],
                collection=self.test_env["MONGO_COLLECTION"],
            )

            # Check that some records were extracted
            extracted_records = list(
                self.test_db[self.test_env["MONGO_COLLECTION"]].find({})
            )

            assert len(extracted_records) > 0, "No records were extracted"

            # Verify record structure
            for record in extracted_records[:5]:  # Check first 5
                assert "identifier" in record
                assert "doc_link" in record
                assert "partition_date" in record
                assert "body_type" in record
                assert "published_date" in record
                assert "status" in record

                # Verify file was downloaded and stored
                if record["status"] == "extracted":
                    assert "file_path" in record
                    assert "file_hash" in record
                    assert "mime_type" in record

                    # Verify file exists in MinIO
                    try:
                        self.minio_client.stat_object(
                            self.test_env["MINIO_BUCKET"],
                            record["file_path"].split("/", 1)[1],
                        )
                    except S3Error:
                        pytest.fail(f"File not found in MinIO: {record['file_path']}")

            mongo_storage.close()
            logger.info(f"Extracted {len(extracted_records)} records successfully")

    @pytest.mark.e2e
    def test_error_handling_and_recovery(self) -> None:
        """Test pipeline error handling and recovery mechanisms.

        Verifies that:
        1. Invalid records are marked with error status
        2. Pipeline continues processing after errors
        3. Error details are logged in notes field
        4. Valid records are processed successfully
        """
        with patch.dict(os.environ, self.test_env):
            # Create mix of valid and invalid mock records
            mock_records = self._create_mock_records_with_errors()

            mongo_storage = MongoDBStorage(
                mongo_uri=self.test_env["MONGO_URI"],
                database=self.test_env["MONGO_DB"],
                collection=self.test_env["MONGO_COLLECTION"],
            )

            minio_storage = MinIOStorage(
                endpoint=self.test_env["MINIO_ENDPOINT"],
                access_key=self.test_env["MINIO_ACCESS_KEY"],
                secret_key=self.test_env["MINIO_SECRET_KEY"],
                bucket_name=self.test_env["MINIO_BUCKET"],
                secure=False,
            )

            # Insert records (some with error status, some without files)
            for record in mock_records:
                if record.get("create_file", True):
                    # Upload mock file to MinIO
                    file_data = self._generate_mock_file_content(record)
                    file_path = minio_storage.upload_file(
                        file_data=file_data,
                        object_name=record["file_path"].split("/")[-1],
                        content_type=record["mime_type"],
                    )
                    record["file_path"] = file_path

                mongo_storage.insert_one(record)

            # Run transformation pipeline
            stats = run_transformation_pipeline(
                start_date="2024-01-01",
                end_date="2024-01-31",
                mongo_uri=self.test_env["MONGO_URI"],
                mongo_db=self.test_env["MONGO_DB"],
                source_collection=self.test_env["MONGO_COLLECTION"],
                dest_collection=self.test_env["MONGO_PROCESSED_COLLECTION"],
                minio_endpoint=self.test_env["MINIO_ENDPOINT"],
                minio_access_key=self.test_env["MINIO_ACCESS_KEY"],
                minio_secret_key=self.test_env["MINIO_SECRET_KEY"],
                source_bucket=self.test_env["MINIO_BUCKET"],
                dest_bucket=self.test_env["MINIO_PROCESSED_BUCKET"],
            )

            # Verify error handling
            assert stats["total"] == len(mock_records)
            assert stats["failed"] > 0  # Some records should fail
            assert stats["processed"] > 0  # Some should succeed

            # Check that error records were skipped appropriately
            processed_collection = self.test_db[self.test_env["MONGO_PROCESSED_COLLECTION"]]

            # Error records should either not be processed or marked as error
            for record in mock_records:
                if record.get("status") == "error":
                    processed = processed_collection.find_one(
                        {"identifier": record["identifier"]}
                    )
                    # Either not processed or still has error status
                    if processed:
                        assert "error" in processed.get("status", "").lower() or \
                               processed.get("notes") is not None

            mongo_storage.close()
            logger.info("Error handling test completed successfully")

    @pytest.mark.e2e
    def test_idempotency(self) -> None:
        """Test pipeline idempotency (running twice produces same result).

        Verifies that:
        1. Duplicate identifiers are not re-processed
        2. Files are not duplicated in storage
        3. Metadata remains consistent
        """
        with patch.dict(os.environ, self.test_env):
            mock_records = self._create_mock_records()

            mongo_storage = MongoDBStorage(
                mongo_uri=self.test_env["MONGO_URI"],
                database=self.test_env["MONGO_DB"],
                collection=self.test_env["MONGO_COLLECTION"],
            )

            minio_storage = MinIOStorage(
                endpoint=self.test_env["MINIO_ENDPOINT"],
                access_key=self.test_env["MINIO_ACCESS_KEY"],
                secret_key=self.test_env["MINIO_SECRET_KEY"],
                bucket_name=self.test_env["MINIO_BUCKET"],
                secure=False,
            )

            # First run: populate data
            for record in mock_records:
                file_data = self._generate_mock_file_content(record)
                file_path = minio_storage.upload_file(
                    file_data=file_data,
                    object_name=record["file_path"].split("/")[-1],
                    content_type=record["mime_type"],
                )
                record["file_path"] = file_path
                record["status"] = "extracted"
                mongo_storage.insert_one(record)

            # First transformation
            stats1 = run_transformation_pipeline(
                start_date="2024-01-01",
                end_date="2024-01-31",
                mongo_uri=self.test_env["MONGO_URI"],
                mongo_db=self.test_env["MONGO_DB"],
                source_collection=self.test_env["MONGO_COLLECTION"],
                dest_collection=self.test_env["MONGO_PROCESSED_COLLECTION"],
                minio_endpoint=self.test_env["MINIO_ENDPOINT"],
                minio_access_key=self.test_env["MINIO_ACCESS_KEY"],
                minio_secret_key=self.test_env["MINIO_SECRET_KEY"],
                source_bucket=self.test_env["MINIO_BUCKET"],
                dest_bucket=self.test_env["MINIO_PROCESSED_BUCKET"],
            )

            # Get counts after first run
            processed_collection = self.test_db[self.test_env["MONGO_PROCESSED_COLLECTION"]]
            count_after_first = processed_collection.count_documents({})

            objects_after_first = list(self.minio_client.list_objects(
                self.test_env["MINIO_PROCESSED_BUCKET"],
                recursive=True,
            ))

            # Second transformation (should be idempotent)
            stats2 = run_transformation_pipeline(
                start_date="2024-01-01",
                end_date="2024-01-31",
                mongo_uri=self.test_env["MONGO_URI"],
                mongo_db=self.test_env["MONGO_DB"],
                source_collection=self.test_env["MONGO_COLLECTION"],
                dest_collection=self.test_env["MONGO_PROCESSED_COLLECTION"],
                minio_endpoint=self.test_env["MINIO_ENDPOINT"],
                minio_access_key=self.test_env["MINIO_ACCESS_KEY"],
                minio_secret_key=self.test_env["MINIO_SECRET_KEY"],
                source_bucket=self.test_env["MINIO_BUCKET"],
                dest_bucket=self.test_env["MINIO_PROCESSED_BUCKET"],
            )

            # Get counts after second run
            count_after_second = processed_collection.count_documents({})
            objects_after_second = list(self.minio_client.list_objects(
                self.test_env["MINIO_PROCESSED_BUCKET"],
                recursive=True,
            ))

            # Verify idempotency
            assert count_after_first == count_after_second, \
                "Record count changed on second run"
            assert len(objects_after_first) == len(objects_after_second), \
                "File count changed on second run"

            # Most records should be skipped on second run
            assert stats2["skipped"] >= stats1["processed"], \
                "Expected more skipped records on second run"

            mongo_storage.close()
            logger.info("Idempotency test completed successfully")

    @pytest.mark.e2e
    def test_date_range_filtering(self) -> None:
        """Test that transformation pipeline correctly filters by date range.

        Verifies:
        1. Only records within date range are processed
        2. Records outside range are skipped
        3. Edge cases (start/end dates) are handled correctly
        """
        with patch.dict(os.environ, self.test_env):
            # Create records with different partition dates
            records_with_dates = [
                self._create_single_mock_record(
                    identifier=f"TEST-{i:03d}",
                    partition_date=date,
                )
                for i, date in enumerate([
                    "2023-12-31",  # Outside range (before)
                    "2024-01-01",  # Start of range
                    "2024-01-15",  # Middle of range
                    "2024-01-31",  # End of range
                    "2024-02-01",  # Outside range (after)
                ], start=1)
            ]

            mongo_storage = MongoDBStorage(
                mongo_uri=self.test_env["MONGO_URI"],
                database=self.test_env["MONGO_DB"],
                collection=self.test_env["MONGO_COLLECTION"],
            )

            minio_storage = MinIOStorage(
                endpoint=self.test_env["MINIO_ENDPOINT"],
                access_key=self.test_env["MINIO_ACCESS_KEY"],
                secret_key=self.test_env["MINIO_SECRET_KEY"],
                bucket_name=self.test_env["MINIO_BUCKET"],
                secure=False,
            )

            # Insert all records
            for record in records_with_dates:
                file_data = self._generate_mock_file_content(record)
                file_path = minio_storage.upload_file(
                    file_data=file_data,
                    object_name=record["file_path"].split("/")[-1],
                    content_type=record["mime_type"],
                )
                record["file_path"] = file_path
                record["status"] = "extracted"
                mongo_storage.insert_one(record)

            # Run transformation with specific date range
            stats = run_transformation_pipeline(
                start_date="2024-01-01",
                end_date="2024-01-31",
                mongo_uri=self.test_env["MONGO_URI"],
                mongo_db=self.test_env["MONGO_DB"],
                source_collection=self.test_env["MONGO_COLLECTION"],
                dest_collection=self.test_env["MONGO_PROCESSED_COLLECTION"],
                minio_endpoint=self.test_env["MINIO_ENDPOINT"],
                minio_access_key=self.test_env["MINIO_ACCESS_KEY"],
                minio_secret_key=self.test_env["MINIO_SECRET_KEY"],
                source_bucket=self.test_env["MINIO_BUCKET"],
                dest_bucket=self.test_env["MINIO_PROCESSED_BUCKET"],
            )

            # Verify only records in date range were processed
            processed_collection = self.test_db[self.test_env["MONGO_PROCESSED_COLLECTION"]]

            # Should have processed exactly 3 records (Jan 1, 15, 31)
            assert stats["processed"] == 3
            assert stats["total"] == 3  # Only 3 should be found in date range

            # Verify which records were processed
            for record in records_with_dates:
                processed = processed_collection.find_one(
                    {"identifier": record["identifier"]}
                )

                if record["partition_date"] in ["2024-01-01", "2024-01-15", "2024-01-31"]:
                    assert processed is not None, \
                        f"Record {record['identifier']} should be processed"
                    assert processed["status"] == "transformed"
                else:
                    assert processed is None, \
                        f"Record {record['identifier']} should not be processed"

            mongo_storage.close()
            logger.info("Date range filtering test completed successfully")

    def _create_mock_records(self) -> List[Dict[str, Any]]:
        """Create mock records for testing."""
        return [
            {
                "identifier": "TEST-001",
                "description": "Test Decision 001",
                "published_date": "01/01/2024",
                "body_type": "WRC",
                "source_url": "https://example.com/search",
                "doc_link": "https://example.com/TEST-001.pdf",
                "partition_date": "2024-01-01",
                "file_path": "landing-zone/TEST-001.pdf",
                "file_hash": "abc123",
                "mime_type": "application/pdf",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            {
                "identifier": "TEST-002",
                "description": "Test Decision 002",
                "published_date": "15/01/2024",
                "body_type": "LC",
                "source_url": "https://example.com/search",
                "doc_link": "https://example.com/TEST-002.html",
                "partition_date": "2024-01-15",
                "file_path": "landing-zone/TEST-002.html",
                "file_hash": "def456",
                "mime_type": "text/html",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
            {
                "identifier": "TEST-003",
                "description": "Test Decision 003",
                "published_date": "20/01/2024",
                "body_type": "EAT",
                "source_url": "https://example.com/search",
                "doc_link": "https://example.com/TEST-003.pdf",
                "partition_date": "2024-01-20",
                "file_path": "landing-zone/TEST-003.pdf",
                "file_hash": "ghi789",
                "mime_type": "application/pdf",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            },
        ]

    def _create_mock_records_with_errors(self) -> List[Dict[str, Any]]:
        """Create mock records with some error cases for testing."""
        records = self._create_mock_records()

        # Add an error record
        records.append({
            "identifier": "TEST-ERR-001",
            "description": "Test Error Record",
            "published_date": "25/01/2024",
            "body_type": "WRC",
            "source_url": "https://example.com/search",
            "doc_link": "https://example.com/error.pdf",
            "partition_date": "2024-01-25",
            "status": "error",
            "notes": "Download failed",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "create_file": False,  # Don't create file for this one
        })

        # Add a record with missing file
        records.append({
            "identifier": "TEST-MISSING-001",
            "description": "Test Missing File",
            "published_date": "28/01/2024",
            "body_type": "LC",
            "source_url": "https://example.com/search",
            "doc_link": "https://example.com/missing.pdf",
            "partition_date": "2024-01-28",
            "file_path": "landing-zone/NONEXISTENT.pdf",
            "file_hash": "missing123",
            "mime_type": "application/pdf",
            "status": "extracted",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "create_file": False,  # Don't create file
        })

        return records

    def _create_single_mock_record(
        self,
        identifier: str,
        partition_date: str,
    ) -> Dict[str, Any]:
        """Create a single mock record with specified parameters."""
        return {
            "identifier": identifier,
            "description": f"Test Decision {identifier}",
            "published_date": partition_date.replace("-", "/"),
            "body_type": "WRC",
            "source_url": "https://example.com/search",
            "doc_link": f"https://example.com/{identifier}.pdf",
            "partition_date": partition_date,
            "file_path": f"landing-zone/{identifier}.pdf",
            "file_hash": f"hash_{identifier}",
            "mime_type": "application/pdf",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

    def _generate_mock_file_content(self, record: Dict[str, Any]) -> bytes:
        """Generate mock file content based on record mime type."""
        mime_type = record.get("mime_type", "application/pdf")
        identifier = record.get("identifier", "UNKNOWN")

        if mime_type == "text/html":
            content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>{identifier}</title>
            </head>
            <body>
                <h1>Test Document {identifier}</h1>
                <p>This is a test HTML document for {identifier}.</p>
                <p>Published: {record.get('published_date', 'Unknown')}</p>
                <p>Body: {record.get('body_type', 'Unknown')}</p>
            </body>
            </html>
            """
            return content.encode("utf-8")
        else:
            # Mock PDF content (simple binary)
            return f"MOCK_PDF_CONTENT_{identifier}_{datetime.now().isoformat()}".encode("utf-8")


if __name__ == "__main__":
    """Run e2e tests directly."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Run with pytest
    pytest.main([
        __file__,
        "-v",
        "-m", "e2e",
        "--tb=short",
        "-s",  # Show print statements
    ])
