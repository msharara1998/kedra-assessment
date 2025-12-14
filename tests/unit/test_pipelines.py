"""Unit tests for Scrapy pipelines."""
from unittest.mock import MagicMock, patch, Mock
import pytest
from scrapy.exceptions import DropItem

from src.pipelines import MetadataPipeline
from src.models import RecordMetadata


class TestMetadataPipeline:
    """Test cases for MetadataPipeline class."""

    @patch("src.pipelines.HTMLScraper")
    @patch("src.pipelines.FileDownloader")
    @patch("src.pipelines.MinIOStorage")
    @patch("src.pipelines.MongoDBStorage")
    def test_open_spider(
        self,
        mock_mongo_storage: MagicMock,
        mock_minio_storage: MagicMock,
        mock_file_downloader: MagicMock,
        mock_html_scraper: MagicMock,
    ) -> None:
        """Test pipeline initialization on spider open."""
        pipeline = MetadataPipeline()
        spider = MagicMock()
        spider.name = "test_spider"
        
        with patch.dict("os.environ", {
            "MONGO_URI": "mongodb://test:27017/",
            "MONGO_DB": "test_db",
            "MONGO_COLLECTION": "test_collection",
            "MINIO_ENDPOINT": "test-minio:9000",
            "MINIO_ACCESS_KEY": "test-key",
            "MINIO_SECRET_KEY": "test-secret",
            "MINIO_BUCKET": "test-bucket",
        }):
            pipeline.open_spider(spider)
        
        mock_mongo_storage.assert_called_once()
        mock_minio_storage.assert_called_once()
        mock_file_downloader.assert_called_once()
        mock_html_scraper.assert_called_once()

    @patch("src.pipelines.HTMLScraper")
    @patch("src.pipelines.FileDownloader")
    @patch("src.pipelines.MinIOStorage")
    @patch("src.pipelines.MongoDBStorage")
    def test_process_item_pdf_success(
        self,
        mock_mongo_storage: MagicMock,
        mock_minio_storage: MagicMock,
        mock_file_downloader: MagicMock,
        mock_html_scraper: MagicMock,
    ) -> None:
        """Test successful item processing with PDF document."""
        # Setup mocks
        mock_mongo_instance = MagicMock()
        mock_mongo_instance.find_by_identifier.return_value = None
        mock_mongo_instance.insert_one.return_value = "doc_id_123"
        mock_mongo_storage.return_value = mock_mongo_instance
        
        mock_minio_instance = MagicMock()
        mock_minio_instance.upload_file.return_value = "landing-zone/TEST-001.pdf"
        mock_minio_storage.return_value = mock_minio_instance
        
        mock_downloader_instance = MagicMock()
        mock_downloader_instance.download.return_value = (
            b"file content",
            "abc123hash",
            "application/pdf",
        )
        mock_downloader_instance.is_html_page.return_value = False
        mock_downloader_instance.get_file_extension.return_value = ".pdf"
        mock_file_downloader.return_value = mock_downloader_instance
        
        mock_html_scraper.return_value = MagicMock()
        
        # Create pipeline and item
        pipeline = MetadataPipeline()
        spider = MagicMock()
        
        with patch.dict("os.environ", {
            "MONGO_URI": "mongodb://test:27017/",
            "MONGO_DB": "test_db",
            "MONGO_COLLECTION": "test_collection",
            "MINIO_ENDPOINT": "test-minio:9000",
            "MINIO_ACCESS_KEY": "test-key",
            "MINIO_SECRET_KEY": "test-secret",
            "MINIO_BUCKET": "test-bucket",
        }):
            pipeline.open_spider(spider)
        
        item = RecordMetadata()
        item["identifier"] = "TEST-001"
        item["doc_link"] = "https://example.com/doc.pdf"
        item["partition_date"] = "2024-01-01"
        
        # Process item
        result = pipeline.process_item(item, spider)
        
        # Assertions
        assert result["identifier"] == "TEST-001"
        assert result["file_path"] == "landing-zone/TEST-001.pdf"
        assert result["file_hash"] == "abc123hash"
        assert result["mime_type"] == "application/pdf"
        assert result["status"] == "transformed"
        
        mock_downloader_instance.download.assert_called_once_with("https://example.com/doc.pdf")
        mock_minio_instance.upload_file.assert_called_once()
        mock_mongo_instance.insert_one.assert_called_once()

    @patch("src.pipelines.HTMLScraper")
    @patch("src.pipelines.FileDownloader")
    @patch("src.pipelines.MinIOStorage")
    @patch("src.pipelines.MongoDBStorage")
    def test_process_item_html_success(
        self,
        mock_mongo_storage: MagicMock,
        mock_minio_storage: MagicMock,
        mock_file_downloader: MagicMock,
        mock_html_scraper: MagicMock,
    ) -> None:
        """Test successful item processing with HTML page."""
        # Setup mocks
        mock_mongo_instance = MagicMock()
        mock_mongo_instance.find_by_identifier.return_value = None
        mock_mongo_instance.insert_one.return_value = "doc_id_123"
        mock_mongo_storage.return_value = mock_mongo_instance
        
        mock_minio_instance = MagicMock()
        mock_minio_instance.upload_file.return_value = "landing-zone/TEST-001.html"
        mock_minio_storage.return_value = mock_minio_instance
        
        mock_downloader_instance = MagicMock()
        mock_downloader_instance.download.return_value = (
            b"<html><body>Content</body></html>",
            "def456hash",
            "text/html",
        )
        mock_downloader_instance.is_html_page.return_value = True
        mock_file_downloader.return_value = mock_downloader_instance
        
        mock_scraper_instance = MagicMock()
        mock_scraper_instance.scrape_page.return_value = (
            "<html><body>Cleaned Content</body></html>",
            "cleaned789hash",
        )
        mock_html_scraper.return_value = mock_scraper_instance
        
        # Create pipeline and item
        pipeline = MetadataPipeline()
        spider = MagicMock()
        
        with patch.dict("os.environ", {
            "MONGO_URI": "mongodb://test:27017/",
            "MONGO_DB": "test_db",
            "MONGO_COLLECTION": "test_collection",
            "MINIO_ENDPOINT": "test-minio:9000",
            "MINIO_ACCESS_KEY": "test-key",
            "MINIO_SECRET_KEY": "test-secret",
            "MINIO_BUCKET": "test-bucket",
        }):
            pipeline.open_spider(spider)
        
        item = RecordMetadata()
        item["identifier"] = "TEST-001"
        item["doc_link"] = "https://example.com/page.html"
        item["partition_date"] = "2024-01-01"
        
        # Process item
        result = pipeline.process_item(item, spider)
        
        # Assertions
        assert result["identifier"] == "TEST-001"
        assert result["file_path"] == "landing-zone/TEST-001.html"
        assert result["mime_type"] == "text/html"
        assert result["status"] == "transformed"
        
        mock_downloader_instance.download.assert_called_once_with("https://example.com/page.html")
        mock_scraper_instance.scrape_page.assert_called_once_with("https://example.com/page.html")
        mock_minio_instance.upload_file.assert_called_once()
        mock_mongo_instance.insert_one.assert_called_once()

    @patch("src.pipelines.HTMLScraper")
    @patch("src.pipelines.FileDownloader")
    @patch("src.pipelines.MinIOStorage")
    @patch("src.pipelines.MongoDBStorage")
    def test_process_item_missing_identifier(
        self,
        mock_mongo_storage: MagicMock,
        mock_minio_storage: MagicMock,
        mock_file_downloader: MagicMock,
        mock_html_scraper: MagicMock,
    ) -> None:
        """Test item processing with missing identifier."""
        pipeline = MetadataPipeline()
        spider = MagicMock()
        
        mock_mongo_instance = MagicMock()
        mock_mongo_storage.return_value = mock_mongo_instance
        mock_minio_storage.return_value = MagicMock()
        mock_file_downloader.return_value = MagicMock()
        mock_html_scraper.return_value = MagicMock()
        
        with patch.dict("os.environ", {
            "MONGO_URI": "mongodb://test:27017/",
            "MONGO_DB": "test_db",
            "MONGO_COLLECTION": "test_collection",
            "MINIO_ENDPOINT": "test-minio:9000",
            "MINIO_ACCESS_KEY": "test-key",
            "MINIO_SECRET_KEY": "test-secret",
            "MINIO_BUCKET": "test-bucket",
        }):
            pipeline.open_spider(spider)
        
        item = RecordMetadata()
        item["doc_link"] = "https://example.com/doc.pdf"
        
        with pytest.raises(DropItem, match="Missing required fields"):
            pipeline.process_item(item, spider)

    @patch("src.pipelines.HTMLScraper")
    @patch("src.pipelines.FileDownloader")
    @patch("src.pipelines.MinIOStorage")
    @patch("src.pipelines.MongoDBStorage")
    def test_process_item_duplicate(
        self,
        mock_mongo_storage: MagicMock,
        mock_minio_storage: MagicMock,
        mock_file_downloader: MagicMock,
        mock_html_scraper: MagicMock,
    ) -> None:
        """Test item processing with duplicate identifier."""
        mock_mongo_instance = MagicMock()
        mock_mongo_instance.find_by_identifier.return_value = {"identifier": "TEST-001"}
        mock_mongo_storage.return_value = mock_mongo_instance
        mock_minio_storage.return_value = MagicMock()
        mock_file_downloader.return_value = MagicMock()
        mock_html_scraper.return_value = MagicMock()
        
        pipeline = MetadataPipeline()
        spider = MagicMock()
        
        with patch.dict("os.environ", {
            "MONGO_URI": "mongodb://test:27017/",
            "MONGO_DB": "test_db",
            "MONGO_COLLECTION": "test_collection",
            "MINIO_ENDPOINT": "test-minio:9000",
            "MINIO_ACCESS_KEY": "test-key",
            "MINIO_SECRET_KEY": "test-secret",
            "MINIO_BUCKET": "test-bucket",
        }):
            pipeline.open_spider(spider)
        
        item = RecordMetadata()
        item["identifier"] = "TEST-001"
        item["doc_link"] = "https://example.com/doc.pdf"
        
        # Should skip duplicate without raising
        result = pipeline.process_item(item, spider)
        assert result["identifier"] == "TEST-001"

    @patch("src.pipelines.HTMLScraper")
    @patch("src.pipelines.FileDownloader")
    @patch("src.pipelines.MinIOStorage")
    @patch("src.pipelines.MongoDBStorage")
    def test_process_item_missing_doc_link(
        self,
        mock_mongo_storage: MagicMock,
        mock_minio_storage: MagicMock,
        mock_file_downloader: MagicMock,
        mock_html_scraper: MagicMock,
    ) -> None:
        """Test item processing with missing doc_link."""
        mock_mongo_instance = MagicMock()
        mock_mongo_instance.find_by_identifier.return_value = None
        mock_mongo_instance.insert_one.return_value = "doc_id_123"
        mock_mongo_storage.return_value = mock_mongo_instance
        mock_minio_storage.return_value = MagicMock()
        mock_file_downloader.return_value = MagicMock()
        mock_html_scraper.return_value = MagicMock()
        
        pipeline = MetadataPipeline()
        spider = MagicMock()
        
        with patch.dict("os.environ", {
            "MONGO_URI": "mongodb://test:27017/",
            "MONGO_DB": "test_db",
            "MONGO_COLLECTION": "test_collection",
            "MINIO_ENDPOINT": "test-minio:9000",
            "MINIO_ACCESS_KEY": "test-key",
            "MINIO_SECRET_KEY": "test-secret",
            "MINIO_BUCKET": "test-bucket",
        }):
            pipeline.open_spider(spider)
        
        item = RecordMetadata()
        item["identifier"] = "TEST-001"
        
        with pytest.raises(DropItem, match="Missing required fields"):
            pipeline.process_item(item, spider)

    @patch("src.pipelines.HTMLScraper")
    @patch("src.pipelines.FileDownloader")
    @patch("src.pipelines.MinIOStorage")
    @patch("src.pipelines.MongoDBStorage")
    def test_process_item_download_error(
        self,
        mock_mongo_storage: MagicMock,
        mock_minio_storage: MagicMock,
        mock_file_downloader: MagicMock,
        mock_html_scraper: MagicMock,
    ) -> None:
        """Test item processing with download error."""
        import requests
        
        mock_mongo_instance = MagicMock()
        mock_mongo_instance.find_by_identifier.return_value = None
        mock_mongo_instance.insert_one.return_value = "doc_id_123"
        mock_mongo_storage.return_value = mock_mongo_instance
        
        mock_minio_storage.return_value = MagicMock()
        
        mock_downloader_instance = MagicMock()
        mock_downloader_instance.download.side_effect = requests.RequestException("Download failed")
        mock_file_downloader.return_value = mock_downloader_instance
        
        mock_html_scraper.return_value = MagicMock()
        
        pipeline = MetadataPipeline()
        spider = MagicMock()
        
        with patch.dict("os.environ", {
            "MONGO_URI": "mongodb://test:27017/",
            "MONGO_DB": "test_db",
            "MONGO_COLLECTION": "test_collection",
            "MINIO_ENDPOINT": "test-minio:9000",
            "MINIO_ACCESS_KEY": "test-key",
            "MINIO_SECRET_KEY": "test-secret",
            "MINIO_BUCKET": "test-bucket",
        }):
            pipeline.open_spider(spider)
        
        item = RecordMetadata()
        item["identifier"] = "TEST-001"
        item["doc_link"] = "https://example.com/doc.pdf"
        item["partition_date"] = "2024-01-01"
        
        # Process item - should not raise, but set error status
        result = pipeline.process_item(item, spider)
        
        # Should insert error record
        mock_mongo_instance.insert_one.assert_called_once()
        inserted_item = mock_mongo_instance.insert_one.call_args[0][0]
        assert inserted_item["status"] == "error"
        assert "Download failed" in inserted_item["notes"]

    @patch("src.pipelines.HTMLScraper")
    @patch("src.pipelines.FileDownloader")
    @patch("src.pipelines.MinIOStorage")
    @patch("src.pipelines.MongoDBStorage")
    def test_process_item_html_scraping_fallback(
        self,
        mock_mongo_storage: MagicMock,
        mock_minio_storage: MagicMock,
        mock_file_downloader: MagicMock,
        mock_html_scraper: MagicMock,
    ) -> None:
        """Test HTML processing with scraping error fallback."""
        mock_mongo_instance = MagicMock()
        mock_mongo_instance.find_by_identifier.return_value = None
        mock_mongo_instance.insert_one.return_value = "doc_id_123"
        mock_mongo_storage.return_value = mock_mongo_instance
        
        mock_minio_instance = MagicMock()
        mock_minio_instance.upload_file.return_value = "landing-zone/TEST-001.html"
        mock_minio_storage.return_value = mock_minio_instance
        
        original_html = b"<html><body>Original Content</body></html>"
        mock_downloader_instance = MagicMock()
        mock_downloader_instance.download.return_value = (
            original_html,
            "original123hash",
            "text/html",
        )
        mock_downloader_instance.is_html_page.return_value = True
        mock_file_downloader.return_value = mock_downloader_instance
        
        # Scraper fails, should fallback to original content
        mock_scraper_instance = MagicMock()
        mock_scraper_instance.scrape_page.side_effect = Exception("Scraping failed")
        mock_html_scraper.return_value = mock_scraper_instance
        
        pipeline = MetadataPipeline()
        spider = MagicMock()
        
        with patch.dict("os.environ", {
            "MONGO_URI": "mongodb://test:27017/",
            "MONGO_DB": "test_db",
            "MONGO_COLLECTION": "test_collection",
            "MINIO_ENDPOINT": "test-minio:9000",
            "MINIO_ACCESS_KEY": "test-key",
            "MINIO_SECRET_KEY": "test-secret",
            "MINIO_BUCKET": "test-bucket",
        }):
            pipeline.open_spider(spider)
        
        item = RecordMetadata()
        item["identifier"] = "TEST-001"
        item["doc_link"] = "https://example.com/page.html"
        item["partition_date"] = "2024-01-01"
        
        result = pipeline.process_item(item, spider)
        
        # Should use original content when scraping fails
        assert result["file_path"] == "landing-zone/TEST-001.html"
        assert result["status"] == "transformed"
        mock_minio_instance.upload_file.assert_called_once()

    @patch("src.pipelines.HTMLScraper")
    @patch("src.pipelines.FileDownloader")
    @patch("src.pipelines.MinIOStorage")
    @patch("src.pipelines.MongoDBStorage")
    def test_close_spider(
        self,
        mock_mongo_storage: MagicMock,
        mock_minio_storage: MagicMock,
        mock_file_downloader: MagicMock,
        mock_html_scraper: MagicMock,
    ) -> None:
        """Test pipeline cleanup on spider close."""
        mock_mongo_instance = MagicMock()
        mock_mongo_storage.return_value = mock_mongo_instance
        
        mock_downloader_instance = MagicMock()
        mock_file_downloader.return_value = mock_downloader_instance
        
        mock_scraper_instance = MagicMock()
        mock_html_scraper.return_value = mock_scraper_instance
        
        mock_minio_storage.return_value = MagicMock()
        
        pipeline = MetadataPipeline()
        spider = MagicMock()
        
        with patch.dict("os.environ", {
            "MONGO_URI": "mongodb://test:27017/",
            "MONGO_DB": "test_db",
            "MONGO_COLLECTION": "test_collection",
            "MINIO_ENDPOINT": "test-minio:9000",
            "MINIO_ACCESS_KEY": "test-key",
            "MINIO_SECRET_KEY": "test-secret",
            "MINIO_BUCKET": "test-bucket",
        }):
            pipeline.open_spider(spider)
        
        pipeline.close_spider(spider)
        
        # Verify all connections are closed
        mock_mongo_instance.close.assert_called_once()
        mock_downloader_instance.close.assert_called_once()
        mock_scraper_instance.close.assert_called_once()
