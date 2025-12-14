"""Extract metadata from Workplace Relations decisions website.

Provides interface for running Scrapy spider with specified date range and body filters.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Iterable
from datetime import datetime, date
from urllib.parse import urlencode
import logging

from bs4 import BeautifulSoup
import scrapy

from src.utils import partition
from src.config import wrc_settings
from src.models import RecordMetadata



logger = logging.getLogger(__name__)



class WRCSpider(scrapy.Spider):
    """Scrapy spider for Workplace Relations Commission."""

    name = "wrc_spider"
    allowed_domains = ["workplacerelations.ie"]

    def __init__(
        self,
        start_date: str,
        end_date: str,
        bodies: list[str] | str | None = None,
        *args, **kwargs
    ) -> None:
        """Initialize spider with date range and body types.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            bodies: List of body types or single body type string. Bodies can be:
                - "WRC" (Workplace Relations Commission)
                - "LC" (Labour Court)
                - "EAT" (Employment Appeals Tribunal)
                - "ET" (Equality Tribunal)

        """
        super().__init__(*args, **kwargs)
        self.start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
        self.end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        # Use provided bodies or default from config
        if bodies is None:
            self.bodies = wrc_settings.get_bodies()
        else:
            self.bodies = bodies if isinstance(bodies, list) else [bodies]

    def start_requests(self) -> Iterable[scrapy.Request]:
        """Generate search requests for each body and month partition."""
        body_mapping = wrc_settings.get_body_mapping()

        for body in self.bodies:
            body_name = body_mapping.get(body, body)
            for part_date in partition(self.start_date, self.end_date, "monthly"):
                # Use actual start_date for the first partition, otherwise use partition start
                period_start = max(part_date, self.start_date)

                # Calculate end of month
                if part_date.month == 12:
                    month_end = date(part_date.year + 1, 1, 1)
                else:
                    month_end = date(part_date.year, part_date.month + 1, 1)

                # Don't go beyond the specified end_date
                month_end = min(month_end, self.end_date)


                # Construct search URL with date filters and body type
                base_url = "https://www.workplacerelations.ie/en/search/"
                params = {
                    "decisions": "1",
                    "body": body_name,
                    "from": period_start.strftime("%d/%m/%Y"),
                    "to": month_end.strftime("%d/%m/%Y"),
                }
                search_url = f"{base_url}?{urlencode(params)}"

                logger.info("Queue search: body=%s partition=%s", body, part_date)
                yield scrapy.Request(
                    url=search_url,
                    callback=self.parse,
                    cb_kwargs={"body": body, "partition_date": part_date.isoformat()},
                )

    def parse(self, response: scrapy.http.Response, body: str, partition_date: str) -> Iterable[RecordMetadata]:
        """Parse search results page and extract metadata for each decision record.

        Args:
            response: HTTP response from search page
            body: Body type being searched
            partition_date: Partition date in ISO format

        Yields:
            RecordMetadata items with extracted metadata
        """
        soup = BeautifulSoup(response.body, "html.parser")

        # Find all bottom-ref rows which mark the end of each result
        results = soup.find_all("div", class_="bottom-ref")

        logger.info(f"Found {len(results)} results for body={body}, partition={partition_date}")

        for result in results:
            try:
                # Extract identifier from refNO span
                identifier_elem = result.find("span", class_="refNO")
                identifier = identifier_elem.get_text(strip=True) if identifier_elem else None

                if not identifier:
                    logger.warning("No identifier found, skipping result")
                    continue

                # Go backwards to find the title row
                title_row = result.find_previous_sibling("div", class_="row")

                if not title_row:
                    logger.warning(f"No title row found for {identifier}, skipping")
                    continue

                # Extract published date from title row
                date_elem = title_row.find("span", class_="date")
                published_date = date_elem.get_text(strip=True) if date_elem else None

                # Extract document link from title h2
                title_elem = title_row.find("h2", class_="title")
                doc_link = None
                if title_elem:
                    link_elem = title_elem.find("a")
                    if link_elem and link_elem.get("href"):
                        doc_link = response.urljoin(link_elem["href"])

                # Extract description from p.description between title row and bottom-ref
                description_elem = title_row.find_next_sibling("p", class_="description")
                description = description_elem.get_text(strip=True) if description_elem else None

                # Build and yield metadata item
                item = RecordMetadata()
                item["identifier"] = identifier
                item["description"] = description
                item["published_date"] = published_date
                item["body_type"] = body
                item["source_url"] = response.url
                item["doc_link"] = doc_link or response.url
                item["partition_date"] = partition_date
                item["created_at"] = datetime.now().isoformat()
                item["updated_at"] = datetime.now().isoformat()

                yield item

            except Exception as e:
                logger.error(f"Error parsing result: {e}", exc_info=True)
                continue

        # Handle pagination - look for next page link
        pagination = soup.find("a", text="»")
        if not pagination:
            # Try finding by URL pattern
            pagination = soup.find("a", href=lambda h: h and "pageNumber=" in h and int(h.split("pageNumber=")[1].split("&")[0]) > 1)

        if pagination and pagination.get("href"):
            next_url = response.urljoin(pagination["href"])
            logger.info(f"Following pagination: {next_url}")
            yield scrapy.Request(
                url=next_url,
                callback=self.parse,
                cb_kwargs={"body": body, "partition_date": partition_date},
            )
