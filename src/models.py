"""Item models for Scrapy spider outputs.

Defines `MetadataItem` structure aligned with MongoDB storage.
"""
from typing import Optional
from scrapy import Item, Field


class RecordMetadata(Item):
    """Scraped metadata for a record"""

    identifier = Field()
    description = Field()
    published_date = Field()
    body_type = Field()
    source_url = Field()
    doc_link = Field()
    partition_date = Field()
    file_path = Field()
    file_hash = Field()
    mime_type = Field() # whether the doc link points to a pdf/html/doc etc
    status = Field() # extracted|transformed|error
    created_at = Field()
    updated_at = Field()
    notes = Field()
