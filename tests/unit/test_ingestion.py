"""Unit tests for ingestion module."""
from datetime import datetime
from unittest.mock import MagicMock, patch
import pytest

from src.ingest import validate_date, validate_bodies


class TestValidateDate:
    """Test cases for validate_date function."""

    def test_valid_date_format(self) -> None:
        """Test that valid date format is accepted."""
        result = validate_date("2024-01-15")
        assert result == "2024-01-15"

    def test_valid_date_leap_year(self) -> None:
        """Test that leap year date is accepted."""
        result = validate_date("2024-02-29")
        assert result == "2024-02-29"

    def test_invalid_date_format(self) -> None:
        """Test that invalid date format raises error."""
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError) as exc_info:
            validate_date("01/15/2024")
        assert "Invalid date format" in str(exc_info.value)

    def test_invalid_date_value(self) -> None:
        """Test that invalid date value raises error."""
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError):
            validate_date("2024-02-30")

    def test_invalid_date_string(self) -> None:
        """Test that non-date string raises error."""
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError):
            validate_date("not-a-date")


class TestValidateBodies:
    """Test cases for validate_bodies function."""

    def test_single_valid_body(self) -> None:
        """Test that single valid body type is accepted."""
        result = validate_bodies("WRC")
        assert result == ["WRC"]

    def test_multiple_valid_bodies(self) -> None:
        """Test that multiple valid body types are accepted."""
        result = validate_bodies("WRC,LC,EAT,ET")
        assert set(result) == {"WRC", "LC", "EAT", "ET"}

    def test_bodies_with_spaces(self) -> None:
        """Test that bodies with spaces are properly trimmed."""
        result = validate_bodies("WRC, LC, EAT")
        assert result == ["WRC", "LC", "EAT"]

    def test_invalid_body_type(self) -> None:
        """Test that invalid body type raises error."""
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError) as exc_info:
            validate_bodies("WRC,INVALID")
        assert "Invalid body types" in str(exc_info.value)
        assert "INVALID" in str(exc_info.value)

    def test_all_invalid_bodies(self) -> None:
        """Test that all invalid body types raises error."""
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError):
            validate_bodies("INVALID1,INVALID2")

    def test_mixed_valid_invalid_bodies(self) -> None:
        """Test that mixed valid and invalid body types raises error."""
        import argparse
        
        with pytest.raises(argparse.ArgumentTypeError) as exc_info:
            validate_bodies("WRC,INVALID,LC")
        assert "INVALID" in str(exc_info.value)


class TestRunIngestion:
    """Test cases for run_ingestion function."""

    @patch("src.ingest.CrawlerProcess")
    def test_run_ingestion_basic(self, mock_crawler_process: MagicMock) -> None:
        """Test basic ingestion run."""
        from src.ingest import run_ingestion
        
        mock_process = MagicMock()
        mock_crawler_process.return_value = mock_process
        
        run_ingestion(
            start_date="2024-01-01",
            end_date="2024-01-31",
            bodies=["WRC"],
        )
        
        mock_crawler_process.assert_called_once()
        mock_process.crawl.assert_called_once()
        mock_process.start.assert_called_once()

    @patch("src.ingest.CrawlerProcess")
    def test_run_ingestion_with_output(self, mock_crawler_process: MagicMock) -> None:
        """Test ingestion with output file."""
        from src.ingest import run_ingestion
        
        mock_process = MagicMock()
        mock_crawler_process.return_value = mock_process
        
        run_ingestion(
            start_date="2024-01-01",
            end_date="2024-01-31",
            bodies=["WRC", "LC"],
            output_file="results.json",
        )
        
        # Check that settings include feeds configuration
        call_args = mock_crawler_process.call_args
        settings = call_args[0][0]
        assert "FEEDS" in settings
        assert "results.json" in settings["FEEDS"]

    @patch("src.ingest.CrawlerProcess")
    def test_run_ingestion_multiple_bodies(self, mock_crawler_process: MagicMock) -> None:
        """Test ingestion with multiple body types."""
        from src.ingest import run_ingestion
        
        mock_process = MagicMock()
        mock_crawler_process.return_value = mock_process
        
        run_ingestion(
            start_date="2024-01-01",
            end_date="2024-12-31",
            bodies=["WRC", "LC", "EAT", "ET"],
        )
        
        mock_process.crawl.assert_called_once()
        crawl_call = mock_process.crawl.call_args
        assert crawl_call[1]["bodies"] == ["WRC", "LC", "EAT", "ET"]
        assert crawl_call[1]["start_date"] == "2024-01-01"
        assert crawl_call[1]["end_date"] == "2024-12-31"
