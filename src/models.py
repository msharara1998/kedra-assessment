"""Item models for Scrapy spider outputs.

Defines `MetadataItem` structure aligned with MongoDB storage.
"""
from typing import Optional
from scrapy import Item, Field


class RecordMetadata(Item):
    """Scraped metadata for a record"""

    identifier: str = Field()
    description: Optional[str] = Field()
    published_date: str = Field()
    body_type: str = Field()
    source_url: str = Field()
    doc_link: str = Field()
    partition_date: str = Field()
    file_path: Optional[str] = Field()
    file_hash: Optional[str] = Field()
    mime_type: Optional[str] = Field() # whether the doc link points to a pdf/html/doc etc
    status: str = Field() # extracted|error - set when saving record and its docs to MongoDB
    created_at: str = Field()
    updated_at: str = Field()
    notes: Optional[str] = Field()
