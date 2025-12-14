"""Unit tests for transformation module."""
from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, Mock, patch

import pytest

from src.transform import (
    HTMLContentExtractor,
    FileProcessor,
    TransformationPipeline,
    calculate_file_hash,
    get_file_extension,
    validate_date_range,
)


class TestHelperFunctions:
    """Test helper functions."""

    def test_calculate_file_hash(self) -> None:
        """Test file hash calculation."""
        test_data = b"test data content"
        expected_hash = hashlib.sha256(test_data).hexdigest()
        
        result = calculate_file_hash(test_data)
        
        assert result == expected_hash
        assert len(result) == 64  # SHA256 produces 64 hex characters

    def test_calculate_file_hash_empty(self) -> None:
        """Test hash calculation with empty data."""
        test_data = b""
        result = calculate_file_hash(test_data)
        
        assert isinstance(result, str)
        assert len(result) == 64

    def test_get_file_extension_pdf(self) -> None:
        """Test extension extraction for PDF."""
        assert get_file_extension("application/pdf") == ".pdf"

    def test_get_file_extension_html(self) -> None:
        """Test extension extraction for HTML."""
        assert get_file_extension("text/html") == ".html"
        assert get_file_extension("text/htm") == ".html"

    def test_get_file_extension_doc(self) -> None:
        """Test extension extraction for DOC files."""
        assert get_file_extension("application/msword") == ".doc"
        assert get_file_extension("application/vnd.openxmlformats-officedocument.wordprocessingml.document") == ".docx"

    def test_get_file_extension_with_charset(self) -> None:
        """Test extension extraction with charset parameter."""
        assert get_file_extension("text/html; charset=utf-8") == ".html"
        assert get_file_extension("application/pdf; charset=binary") == ".pdf"

    def test_get_file_extension_unknown(self) -> None:
        """Test extension extraction for unknown type."""
        assert get_file_extension("application/unknown") == ".bin"
        assert get_file_extension("image/png") == ".bin"

    def test_validate_date_range_valid(self) -> None:
        """Test valid date range."""
        assert validate_date_range("2024-01-01", "2024-12-31") is True
        assert validate_date_range("2024-06-15", "2024-06-15") is True

    def test_validate_date_range_invalid_order(self) -> None:
        """Test invalid date range (end before start)."""
        with pytest.raises(ValueError, match="End date .* must be greater than or equal to start date"):
            validate_date_range("2024-12-31", "2024-01-01")

    def test_validate_date_range_invalid_format(self) -> None:
        """Test invalid date format."""
        with pytest.raises(ValueError, match="Invalid date format"):
            validate_date_range("2024/01/01", "2024-12-31")
        
        with pytest.raises(ValueError, match="Invalid date format"):
            validate_date_range("2024-01-01", "invalid-date")


class TestHTMLContentExtractor:
    """Test HTMLContentExtractor class."""

    def test_extract_content_basic(self) -> None:
        """Test basic HTML content extraction."""
        extractor = HTMLContentExtractor()
        html = """
        <html>
            <head><title>Test</title></head>
            <body>
                <main>
                    <h1>Main Content</h1>
                    <p>This is the main content.</p>
                </main>
            </body>
        </html>
        """
        
        result = extractor.extract_content(html)
        
        assert "Main Content" in result
        assert "This is the main content" in result
        assert "<main>" in result

    def test_extract_content_removes_navigation(self) -> None:
        """Test that navigation elements are removed."""
        extractor = HTMLContentExtractor()
        html = """
        <html>
            <body>
                <nav>Navigation Menu</nav>
                <main>
                    <p>Main Content</p>
                </main>
            </body>
        </html>
        """
        
        result = extractor.extract_content(html)
        
        assert "Navigation Menu" not in result
        assert "Main Content" in result

    def test_extract_content_removes_header_footer(self) -> None:
        """Test that header and footer are removed."""
        extractor = HTMLContentExtractor()
        html = """
        <html>
            <body>
                <header>Header Content</header>
                <main>Main Content</main>
                <footer>Footer Content</footer>
            </body>
        </html>
        """
        
        result = extractor.extract_content(html)
        
        assert "Header Content" not in result
        assert "Footer Content" not in result
        assert "Main Content" in result

    def test_extract_content_removes_scripts_and_styles(self) -> None:
        """Test that scripts and styles are removed."""
        extractor = HTMLContentExtractor()
        html = """
        <html>
            <head>
                <style>body { color: red; }</style>
                <script>alert('test');</script>
            </head>
            <body>
                <main>Main Content</main>
            </body>
        </html>
        """
        
        result = extractor.extract_content(html)
        
        assert "color: red" not in result
        assert "alert" not in result
        assert "Main Content" in result

    def test_extract_content_removes_buttons(self) -> None:
        """Test that buttons are removed."""
        extractor = HTMLContentExtractor()
        html = """
        <html>
            <body>
                <main>
                    <p>Content</p>
                    <button>Click Me</button>
                </main>
            </body>
        </html>
        """
        
        result = extractor.extract_content(html)
        
        assert "Click Me" not in result
        assert "Content" in result

    def test_extract_content_with_article_tag(self) -> None:
        """Test content extraction with article tag."""
        extractor = HTMLContentExtractor()
        html = """
        <html>
            <body>
                <nav>Nav</nav>
                <article>
                    <h1>Article Title</h1>
                    <p>Article content</p>
                </article>
            </body>
        </html>
        """
        
        result = extractor.extract_content(html)
        
        assert "Article Title" in result
        assert "Article content" in result
        assert "Nav" not in result

    def test_extract_content_fallback_to_body(self) -> None:
        """Test fallback to body when no main container found."""
        extractor = HTMLContentExtractor()
        html = """
        <html>
            <body>
                <div>Some content</div>
            </body>
        </html>
        """
        
        result = extractor.extract_content(html)
        
        assert "Some content" in result
        assert "<body>" in result


class TestFileProcessor:
    """Test FileProcessor class."""

    def test_process_html_file(self) -> None:
        """Test processing HTML file."""
        processor = FileProcessor()
        html_data = b"<html><body><main><p>Test content</p></main></body></html>"
        
        processed_data, new_hash, new_filename = processor.process_file(
            file_data=html_data,
            mime_type="text/html",
            identifier="TEST-001",
        )
        
        assert isinstance(processed_data, bytes)
        assert len(new_hash) == 64  # SHA256
        assert new_filename == "TEST-001.html"
        assert b"Test content" in processed_data

    def test_process_pdf_file(self) -> None:
        """Test processing PDF file (no transformation)."""
        processor = FileProcessor()
        pdf_data = b"%PDF-1.4 fake pdf content"
        original_hash = calculate_file_hash(pdf_data)
        
        processed_data, new_hash, new_filename = processor.process_file(
            file_data=pdf_data,
            mime_type="application/pdf",
            identifier="TEST-002",
        )
        
        assert processed_data == pdf_data  # Unchanged
        assert new_hash == original_hash
        assert new_filename == "TEST-002.pdf"

    def test_process_doc_file(self) -> None:
        """Test processing DOC file (no transformation)."""
        processor = FileProcessor()
        doc_data = b"fake word document content"
        
        processed_data, new_hash, new_filename = processor.process_file(
            file_data=doc_data,
            mime_type="application/msword",
            identifier="TEST-003",
        )
        
        assert processed_data == doc_data
        assert new_filename == "TEST-003.doc"

    def test_process_docx_file(self) -> None:
        """Test processing DOCX file (no transformation)."""
        processor = FileProcessor()
        docx_data = b"fake docx content"
        
        processed_data, new_hash, new_filename = processor.process_file(
            file_data=docx_data,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            identifier="TEST-004",
        )
        
        assert processed_data == docx_data
        assert new_filename == "TEST-004.docx"

    def test_process_file_with_charset(self) -> None:
        """Test processing file with charset in MIME type."""
        processor = FileProcessor()
        html_data = b"<html><body><main><p>Test</p></main></body></html>"
        
        processed_data, new_hash, new_filename = processor.process_file(
            file_data=html_data,
            mime_type="text/html; charset=utf-8",
            identifier="TEST-005",
        )
        
        assert new_filename == "TEST-005.html"
        assert isinstance(processed_data, bytes)

    def test_process_unknown_mime_type(self) -> None:
        """Test processing unknown MIME type (treated as document)."""
        processor = FileProcessor()
        data = b"unknown content"
        
        processed_data, new_hash, new_filename = processor.process_file(
            file_data=data,
            mime_type="application/unknown",
            identifier="TEST-006",
        )
        
        assert processed_data == data  # Unchanged
        assert new_filename == "TEST-006.bin"


class TestTransformationPipeline:
    """Test TransformationPipeline class."""

    @patch("src.transform.MongoDBStorage")
    @patch("src.transform.MinIOStorage")
    def test_pipeline_initialization(
        self,
        mock_minio: Mock,
        mock_mongo: Mock,
    ) -> None:
        """Test pipeline initialization."""
        pipeline = TransformationPipeline(
            mongo_uri="mongodb://localhost:27017/",
            mongo_db="test_db",
            source_collection="source",
            dest_collection="dest",
            minio_endpoint="localhost:9000",
            minio_access_key="admin",
            minio_secret_key="secret",
            source_bucket="landing-zone",
            dest_bucket="processed",
        )
        
        assert pipeline.source_db is not None
        assert pipeline.dest_db is not None
        assert pipeline.source_storage is not None
        assert pipeline.dest_storage is not None
        assert pipeline.file_processor is not None

    @patch("src.transform.MongoDBStorage")
    @patch("src.transform.MinIOStorage")
    def test_transform_with_empty_records(
        self,
        mock_minio: Mock,
        mock_mongo: Mock,
    ) -> None:
        """Test transformation with no records."""
        # Setup mocks
        mock_source_db = MagicMock()
        mock_source_db.find_by_date_range.return_value = []
        mock_mongo.return_value = mock_source_db
        
        pipeline = TransformationPipeline(
            mongo_uri="mongodb://localhost:27017/",
            mongo_db="test_db",
            source_collection="source",
            dest_collection="dest",
            minio_endpoint="localhost:9000",
            minio_access_key="admin",
            minio_secret_key="secret",
            source_bucket="landing-zone",
            dest_bucket="processed",
        )
        
        pipeline.source_db = mock_source_db
        
        stats = pipeline.transform("2024-01-01", "2024-12-31")
        
        assert stats["total"] == 0
        assert stats["processed"] == 0
        assert stats["failed"] == 0

    @patch("src.transform.MongoDBStorage")
    @patch("src.transform.MinIOStorage")
    def test_process_record_success(
        self,
        mock_minio: Mock,
        mock_mongo: Mock,
    ) -> None:
        """Test successful record processing."""
        # Create pipeline
        pipeline = TransformationPipeline(
            mongo_uri="mongodb://localhost:27017/",
            mongo_db="test_db",
            source_collection="source",
            dest_collection="dest",
            minio_endpoint="localhost:9000",
            minio_access_key="admin",
            minio_secret_key="secret",
            source_bucket="landing-zone",
            dest_bucket="processed",
        )
        
        # Mock storage operations
        test_file_data = b"<html><body><main>Test</main></body></html>"
        pipeline.source_storage = MagicMock()
        pipeline.source_storage.download_file.return_value = test_file_data
        pipeline.dest_storage = MagicMock()
        pipeline.dest_storage.upload_file.return_value = "processed/TEST-001.html"
        pipeline.dest_db = MagicMock()
        
        # Test record
        record = {
            "identifier": "TEST-001",
            "file_path": "landing-zone/test.html",
            "mime_type": "text/html",
            "status": "transformed",
        }
        
        result = pipeline._process_record(record)
        
        assert result is not None
        assert result["identifier"] == "TEST-001"
        assert result["file_path"] == "TEST-001.html"
        assert result["status"] == "processed"
        assert "file_hash" in result
        assert "transformation_date" in result

    @patch("src.transform.MongoDBStorage")
    @patch("src.transform.MinIOStorage")
    def test_process_record_missing_fields(
        self,
        mock_minio: Mock,
        mock_mongo: Mock,
    ) -> None:
        """Test record processing with missing fields."""
        pipeline = TransformationPipeline(
            mongo_uri="mongodb://localhost:27017/",
            mongo_db="test_db",
            source_collection="source",
            dest_collection="dest",
            minio_endpoint="localhost:9000",
            minio_access_key="admin",
            minio_secret_key="secret",
            source_bucket="landing-zone",
            dest_bucket="processed",
        )
        
        # Record missing required fields
        record = {
            "identifier": "TEST-001",
            # Missing file_path and mime_type
        }
        
        result = pipeline._process_record(record)
        
        assert result is None

    @patch("src.transform.MongoDBStorage")
    @patch("src.transform.MinIOStorage")
    def test_transform_validates_date_range(
        self,
        mock_minio: Mock,
        mock_mongo: Mock,
    ) -> None:
        """Test that transform validates date range."""
        pipeline = TransformationPipeline(
            mongo_uri="mongodb://localhost:27017/",
            mongo_db="test_db",
            source_collection="source",
            dest_collection="dest",
            minio_endpoint="localhost:9000",
            minio_access_key="admin",
            minio_secret_key="secret",
            source_bucket="landing-zone",
            dest_bucket="processed",
        )
        
        with pytest.raises(ValueError, match="End date .* must be greater than or equal to start date"):
            pipeline.transform("2024-12-31", "2024-01-01")
