"""Unit tests for WRCSpider start_requests method."""
from datetime import date
from unittest.mock import patch
import pytest

from extraction import WRCSpider


class TestWRCSpiderStartRequests:
    """Test cases for WRCSpider start_requests method."""

    def test_start_requests_single_body_single_month(self) -> None:
        """Test start_requests generates correct request for single body and month."""
        spider = WRCSpider(
            start_date="2024-01-01",
            end_date="2024-01-31",
            bodies=["WRC"]
        )
        
        requests = list(spider.start_requests())
        
        assert len(requests) == 1
        request = requests[0]
        assert "workplacerelations.ie/en/search/" in request.url
        assert "body=15376" in request.url
        assert "from=01%2F01%2F2024" in request.url
        assert "to=31%2F01%2F2024" in request.url
        assert request.cb_kwargs["body"] == "WRC"
        assert request.cb_kwargs["partition_date"] == "2024-01-01"

    def test_start_requests_multiple_bodies(self) -> None:
        """Test start_requests generates requests for multiple bodies."""
        spider = WRCSpider(
            start_date="2024-01-01",
            end_date="2024-01-31",
            bodies=["WRC", "LC", "EAT", "ET"]
        )
        
        requests = list(spider.start_requests())
        
        assert len(requests) == 4
        body_params = [req.url.split("body=")[1].split("&")[0] for req in requests]
        assert "15376" in body_params  # WRC
        assert "3" in body_params  # LC
        assert "2" in body_params  # EAT
        assert "1" in body_params  # ET

    def test_start_requests_multiple_months(self) -> None:
        """Test start_requests partitions date range by month."""
        spider = WRCSpider(
            start_date="2024-01-01",
            end_date="2024-03-31",
            bodies=["WRC"]
        )
        
        requests = list(spider.start_requests())
        
        assert len(requests) == 3
        assert requests[0].cb_kwargs["partition_date"] == "2024-01-01"
        assert requests[1].cb_kwargs["partition_date"] == "2024-02-01"
        assert requests[2].cb_kwargs["partition_date"] == "2024-03-01"

    def test_start_requests_single_body_string(self) -> None:
        """Test start_requests handles single body as string."""
        spider = WRCSpider(
            start_date="2024-01-01",
            end_date="2024-01-31",
            bodies="LC"
        )
        
        requests = list(spider.start_requests())
        
        assert len(requests) == 1
        assert "body=3" in requests[0].url

    def test_start_requests_cross_year_boundary(self) -> None:
        """Test start_requests handles date range across year boundary."""
        spider = WRCSpider(
            start_date="2023-12-01",
            end_date="2024-01-31",
            bodies=["WRC"]
        )
        
        requests = list(spider.start_requests())
        
        assert len(requests) == 2
        assert requests[0].cb_kwargs["partition_date"] == "2023-12-01"
        assert requests[1].cb_kwargs["partition_date"] == "2024-01-01"

    def test_start_requests_url_structure(self) -> None:
        """Test that generated URLs have correct structure and parameters."""
        spider = WRCSpider(
            start_date="2024-06-15",
            end_date="2024-06-20",
            bodies=["EAT"]
        )
        
        requests = list(spider.start_requests())
        
        assert len(requests) == 1
        url = requests[0].url
        print(url)
        assert url.startswith("https://www.workplacerelations.ie/en/search/")
        assert "decisions=1" in url
        assert "body=2" in url
        assert "from=15%2F06%2F2024" in url
        assert "to=20%2F06%2F2024" in url

    def test_start_requests_callback_kwargs(self) -> None:
        """Test that callback kwargs contain required metadata."""
        spider = WRCSpider(
            start_date="2024-05-01",
            end_date="2024-05-31",
            bodies=["ET"]
        )
        
        requests = list(spider.start_requests())
        
        assert len(requests) == 1
        assert "body" in requests[0].cb_kwargs
        assert "partition_date" in requests[0].cb_kwargs
        assert requests[0].cb_kwargs["body"] == "ET"
        assert isinstance(requests[0].cb_kwargs["partition_date"], str)

    def test_start_requests_all_body_types(self) -> None:
        """Test start_requests handles all supported body types."""
        body_types = ["WRC", "LC", "EAT", "ET"]
        expected_codes = {"WRC": "15376", "LC": "3", "EAT": "2", "ET": "1"}
        
        for body in body_types:
            spider = WRCSpider(
                start_date="2024-01-01",
                end_date="2024-01-31",
                bodies=[body]
            )
            
            requests = list(spider.start_requests())
            
            assert len(requests) == 1
            assert f"body={expected_codes[body]}" in requests[0].url

    def test_start_requests_end_date_mid_month(self) -> None:
        """Test start_requests respects end_date when it falls mid-month."""
        spider = WRCSpider(
            start_date="2024-01-01",
            end_date="2024-01-15",
            bodies=["WRC"]
        )
        
        requests = list(spider.start_requests())
        
        assert len(requests) == 1
        assert "to=15%2F01%2F2024" in requests[0].url
