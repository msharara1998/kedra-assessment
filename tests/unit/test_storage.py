"""Unit tests for storage module."""
from unittest.mock import MagicMock, patch, Mock
import pytest

from src.storage import MongoDBStorage, MinIOStorage, FileDownloader


class TestMongoDBStorage:
    """Test cases for MongoDBStorage class."""

    @patch("src.storage.MongoClient")
    def test_init(self, mock_mongo_client: MagicMock) -> None:
        """Test MongoDB storage initialization."""
        mock_client = MagicMock()
        mock_mongo_client.return_value = mock_client
        
        storage = MongoDBStorage(
            mongo_uri="mongodb://localhost:27017/",
            database="test_db",
            collection="test_collection",
        )
        
        mock_mongo_client.assert_called_once_with("mongodb://localhost:27017/")
        assert storage.db == mock_client["test_db"]
        assert storage.collection == mock_client["test_db"]["test_collection"]

    @patch("src.storage.MongoClient")
    def test_insert_one(self, mock_mongo_client: MagicMock) -> None:
        """Test inserting single document."""
        mock_collection = MagicMock()
        mock_result = MagicMock()
        mock_result.inserted_id = "test_id_123"
        mock_collection.insert_one.return_value = mock_result
        
        mock_client = MagicMock()
        mock_client.__getitem__.return_value.__getitem__.return_value = mock_collection
        mock_mongo_client.return_value = mock_client
        
        storage = MongoDBStorage(
            mongo_uri="mongodb://localhost:27017/",
            database="test_db",
            collection="test_collection",
        )
        
        doc = {"identifier": "TEST-001", "title": "Test"}
        result = storage.insert_one(doc)
        
        mock_collection.insert_one.assert_called_once_with(doc)
        assert result == "test_id_123"

    @patch("src.storage.MongoClient")
    def test_find_by_identifier(self, mock_mongo_client: MagicMock) -> None:
        """Test finding document by identifier."""
        mock_collection = MagicMock()
        expected_doc = {"identifier": "TEST-001", "title": "Test"}
        mock_collection.find_one.return_value = expected_doc
        
        mock_client = MagicMock()
        mock_client.__getitem__.return_value.__getitem__.return_value = mock_collection
        mock_mongo_client.return_value = mock_client
        
        storage = MongoDBStorage(
            mongo_uri="mongodb://localhost:27017/",
            database="test_db",
            collection="test_collection",
        )
        
        result = storage.find_by_identifier("TEST-001")
        
        mock_collection.find_one.assert_called_once_with({"identifier": "TEST-001"})
        assert result == expected_doc

    @patch("src.storage.MongoClient")
    def test_find_by_date_range(self, mock_mongo_client: MagicMock) -> None:
        """Test finding documents by date range."""
        mock_collection = MagicMock()
        expected_docs = [
            {"identifier": "TEST-001", "partition_date": "2024-01-01"},
            {"identifier": "TEST-002", "partition_date": "2024-01-15"},
        ]
        mock_collection.find.return_value = expected_docs
        
        mock_client = MagicMock()
        mock_client.__getitem__.return_value.__getitem__.return_value = mock_collection
        mock_mongo_client.return_value = mock_client
        
        storage = MongoDBStorage(
            mongo_uri="mongodb://localhost:27017/",
            database="test_db",
            collection="test_collection",
        )
        
        result = storage.find_by_date_range("2024-01-01", "2024-01-31")
        
        mock_collection.find.assert_called_once()
        assert result == expected_docs


class TestMinIOStorage:
    """Test cases for MinIOStorage class."""

    @patch("src.storage.Minio")
    def test_init(self, mock_minio: MagicMock) -> None:
        """Test MinIO storage initialization."""
        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_minio.return_value = mock_client
        
        storage = MinIOStorage(
            endpoint="localhost:9000",
            access_key="admin",
            secret_key="adminadmin",
            bucket_name="test-bucket",
            secure=False,
        )
        
        mock_minio.assert_called_once_with(
            endpoint="localhost:9000",
            access_key="admin",
            secret_key="adminadmin",
            secure=False,
        )
        mock_client.bucket_exists.assert_called_once_with("test-bucket")

    @patch("src.storage.Minio")
    def test_upload_file(self, mock_minio: MagicMock) -> None:
        """Test uploading file to MinIO."""
        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_minio.return_value = mock_client
        
        storage = MinIOStorage(
            endpoint="localhost:9000",
            access_key="admin",
            secret_key="adminadmin",
            bucket_name="test-bucket",
        )
        
        file_data = b"test content"
        object_name = "test/file.txt"
        
        result = storage.upload_file(
            file_data=file_data,
            object_name=object_name,
            content_type="text/plain",
        )
        
        mock_client.put_object.assert_called_once()
        assert result == "test-bucket/test/file.txt"

    @patch("src.storage.Minio")
    def test_file_exists_true(self, mock_minio: MagicMock) -> None:
        """Test checking if file exists (exists)."""
        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_client.stat_object.return_value = MagicMock()
        mock_minio.return_value = mock_client
        
        storage = MinIOStorage(
            endpoint="localhost:9000",
            access_key="admin",
            secret_key="adminadmin",
            bucket_name="test-bucket",
        )
        
        result = storage.file_exists("test/file.txt")
        
        assert result is True
        mock_client.stat_object.assert_called_once_with(
            bucket_name="test-bucket",
            object_name="test/file.txt",
        )

    @patch("src.storage.Minio")
    def test_file_exists_false(self, mock_minio: MagicMock) -> None:
        """Test checking if file exists (doesn't exist)."""
        from minio.error import S3Error
        
        mock_client = MagicMock()
        mock_client.bucket_exists.return_value = True
        mock_client.stat_object.side_effect = S3Error(
            "NoSuchKey",
            "The specified key does not exist",
            "resource",
            "request_id",
            "host_id",
            Mock(status=404),
        )
        mock_minio.return_value = mock_client
        
        storage = MinIOStorage(
            endpoint="localhost:9000",
            access_key="admin",
            secret_key="adminadmin",
            bucket_name="test-bucket",
        )
        
        result = storage.file_exists("test/nonexistent.txt")
        
        assert result is False


class TestFileDownloader:
    """Test cases for FileDownloader class."""

    def test_init(self) -> None:
        """Test FileDownloader initialization."""
        downloader = FileDownloader(
            timeout=30,
            max_retries=3,
            user_agent="TestAgent/1.0",
        )
        
        assert downloader.timeout == 30
        assert downloader.max_retries == 3
        assert "TestAgent/1.0" in downloader.session.headers["User-Agent"]

    @patch("src.storage.requests.Session")
    def test_download_success(self, mock_session_class: MagicMock) -> None:
        """Test successful file download."""
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.content = b"test file content"
        mock_response.headers = {"Content-Type": "application/pdf"}
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session
        
        downloader = FileDownloader(timeout=30, max_retries=3)
        downloader.session = mock_session
        
        content, file_hash, mime_type = downloader.download("https://example.com/file.pdf")
        
        assert content == b"test file content"
        assert len(file_hash) == 64  # SHA256 hex digest length
        assert mime_type == "application/pdf"

    @patch("src.storage.requests.Session")
    def test_download_retry_then_success(self, mock_session_class: MagicMock) -> None:
        """Test download with retry then success."""
        import requests
        
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.content = b"test content"
        mock_response.headers = {"Content-Type": "text/html"}
        
        # First attempt fails, second succeeds
        mock_session.get.side_effect = [
            requests.RequestException("Network error"),
            mock_response,
        ]
        mock_session_class.return_value = mock_session
        
        downloader = FileDownloader(timeout=30, max_retries=3)
        downloader.session = mock_session
        
        content, file_hash, mime_type = downloader.download("https://example.com/page.html")
        
        assert content == b"test content"
        assert mime_type == "text/html"
        assert mock_session.get.call_count == 2

    def test_get_file_extension_from_url(self) -> None:
        """Test getting file extension from URL."""
        downloader = FileDownloader()
        
        ext = downloader.get_file_extension(
            "https://example.com/document.pdf",
            "application/pdf",
        )
        assert ext == ".pdf"

    def test_get_file_extension_from_mime(self) -> None:
        """Test getting file extension from MIME type."""
        downloader = FileDownloader()
        
        ext = downloader.get_file_extension(
            "https://example.com/file",
            "application/pdf",
        )
        assert ext == ".pdf"

    def test_get_file_extension_html(self) -> None:
        """Test getting extension for HTML files."""
        downloader = FileDownloader()
        
        ext = downloader.get_file_extension(
            "https://example.com/page.html",
            "text/html",
        )
        assert ext == ".html"

    def test_get_file_extension_unknown(self) -> None:
        """Test getting extension for unknown type."""
        downloader = FileDownloader()
        
        ext = downloader.get_file_extension(
            "https://example.com/file",
            "application/unknown",
        )
        assert ext == ".bin"
