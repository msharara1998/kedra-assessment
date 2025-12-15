"""Project configuration using Pydantic settings.

Centralizes all application configuration with type validation and environment
variable support. All settings are loaded from environment variables with
sensible defaults.
"""
from __future__ import annotations

from typing import Dict, List
import json

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScrapySettings(BaseSettings):
    """Scrapy web scraping framework configuration."""

    # ─── Bot Configuration ──────────────────
    bot_name: str = Field(
        default="wr_relations",
        validation_alias="SCRAPY_BOT_NAME",
    )
    robotstxt_obey: bool = Field(
        default=False,
        validation_alias="SCRAPY_ROBOTSTXT_OBEY",
    )
    user_agent: str = Field(
        default="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        validation_alias="SCRAPY_USER_AGENT",
    )

    # ─── Request Settings ───────────────────
    concurrent_requests: int = Field(
        default=12,
        validation_alias="SCRAPY_CONCURRENT_REQUESTS",
    )
    download_delay: float = Field(
        default=0.25,
        validation_alias="SCRAPY_DOWNLOAD_DELAY",
    )
    randomize_download_delay: bool = Field(
        default=True,
        validation_alias="SCRAPY_RANDOMIZE_DOWNLOAD_DELAY",
    )

    # ─── Retry Configuration ────────────────
    retry_enabled: bool = Field(
        default=True,
        validation_alias="SCRAPY_RETRY_ENABLED",
    )
    retry_times: int = Field(
        default=3,
        validation_alias="SCRAPY_RETRY_TIMES",
    )

    # ─── AutoThrottle Settings ──────────────
    autothrottle_enabled: bool = Field(
        default=True,
        validation_alias="SCRAPY_AUTOTHROTTLE_ENABLED",
    )
    autothrottle_target_concurrency: float = Field(
        default=1.0,
        validation_alias="SCRAPY_AUTOTHROTTLE_TARGET",
    )

    # ─── Logging ────────────────────────────
    log_level: str = Field(
        default="INFO",
        validation_alias="SCRAPY_LOG_LEVEL",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def to_scrapy_dict(self) -> Dict[str, object]:
        """Convert to Scrapy settings dictionary format."""
        return {
            "BOT_NAME": self.bot_name,
            "ROBOTSTXT_OBEY": self.robotstxt_obey,
            "CONCURRENT_REQUESTS": self.concurrent_requests,
            "DOWNLOAD_DELAY": self.download_delay,
            "RANDOMIZE_DOWNLOAD_DELAY": self.randomize_download_delay,
            "RETRY_ENABLED": self.retry_enabled,
            "RETRY_TIMES": self.retry_times,
            "AUTOTHROTTLE_ENABLED": self.autothrottle_enabled,
            "AUTOTHROTTLE_TARGET_CONCURRENCY": self.autothrottle_target_concurrency,
            "DEFAULT_REQUEST_HEADERS": {
                "User-Agent": self.user_agent,
            },
            "ITEM_PIPELINES": {"src.pipelines.MetadataPipeline": 300},
            "LOG_LEVEL": self.log_level,
        }


class WRCSettings(BaseSettings):
    """WRC (Workplace Relations Commission) specific configuration."""

    # ─── WRC Bodies ─────────────────────────
    bodies_json: str = Field(
        default="",
        validation_alias="WRC_BODIES_JSON",
    )
    body_mapping_json: str = Field(
        default="",
        validation_alias="WRC_BODY_MAPPING_JSON",
    )
    allowed_domains: str = Field(
        default="",
        validation_alias="ALLOWED_DOMAINS"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def get_allowed_domains(self) -> List[str]:
        """Return the list of allowed domains for scraping."""
        default_domains = ["workplacerelations.ie"]
        if self.allowed_domains:
            try:
                parsed = json.loads(self.allowed_domains)
                if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                    return parsed
            except Exception:
                pass
        return default_domains

    def get_bodies(self) -> List[str]:
        """Return the list of WRC bodies to scrape."""
        default_bodies = ["WRC", "LC", "EAT", "ET"]
        if self.bodies_json:
            try:
                parsed = json.loads(self.bodies_json)
                if isinstance(parsed, list) and all(isinstance(x, str) for x in parsed):
                    return parsed
            except Exception:
                pass
        return default_bodies

    def get_body_mapping(self) -> Dict[str, str]:
        """Return mapping from body codes to query identifiers."""
        default_mapping = {
            "ET": "1",
            "EAT": "2",
            "LC": "3",
            "WRC": "15376",
        }
        if self.body_mapping_json:
            try:
                parsed = json.loads(self.body_mapping_json)
                if isinstance(parsed, dict) and all(
                    isinstance(k, str) and isinstance(v, str) for k, v in parsed.items()
                ):
                    return parsed
            except Exception:
                pass
        return default_mapping


class MongoDBSettings(BaseSettings):
    """MongoDB database configuration."""

    # ─── Connection Settings ────────────────
    uri: str = Field(
        default="mongodb://localhost:27017",
        validation_alias="MONGO_URI",
    )
    database: str = Field(
        default="workplace_relations",
        validation_alias="MONGO_DB",
    )

    # ─── Collections ────────────────────────
    collection: str = Field(
        default="records",
        validation_alias="MONGO_COLLECTION",
    )
    processed_collection: str = Field(
        default="processed_records",
        validation_alias="MONGO_PROCESSED_COLLECTION",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


class MinIOSettings(BaseSettings):
    """MinIO object storage configuration."""

    # ─── Connection Settings ────────────────
    endpoint: str = Field(
        default="localhost:9000",
        validation_alias="MINIO_ENDPOINT",
    )
    access_key: str = Field(
        default="minioadmin",
        validation_alias="MINIO_ACCESS_KEY",
    )
    secret_key: str = Field(
        default="minioadmin",
        validation_alias="MINIO_SECRET_KEY",
    )

    # ─── Buckets ────────────────────────────
    bucket: str = Field(
        default="landing-zone",
        validation_alias="MINIO_BUCKET",
    )
    processed_bucket: str = Field(
        default="processed",
        validation_alias="MINIO_PROCESSED_BUCKET",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# ─── Global Settings Instances ──────────────
scrapy_settings = ScrapySettings()
wrc_settings = WRCSettings()
mongodb_settings = MongoDBSettings()
minio_settings = MinIOSettings()
