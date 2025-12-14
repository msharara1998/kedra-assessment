**Overview**
- Scrapy-based pipeline to ingest Workplace Relations decisions by body and monthly partitions, store metadata in MongoDB and raw files in MinIO (Landing Zone), then transform HTML to extract relevant content, rename files to identifier-based names, rehash, and persist to a Transformed Zone.

**Quick Start**
- Prerequisites: Docker, Docker Compose, Python 3.11+, Linux.
- Bring up infra:

```
docker compose up -d
```

- Install Python deps:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- Run ingestion process:

```bash
# Ingest WRC decisions for a specific period
python -m src.ingest --start-date 2024-01-01 --end-date 2024-03-31 --bodies WRC --output results.json

# Ingest multiple bodies
python -m src.ingest --start-date 2024-01-01 --end-date 2024-12-31 --bodies WRC,LC,EAT,ET
```

- Run transformation over the same range:

```bash
# Run transformation to process landing zone data
python examples/run_transformation.py
```

**Architecture**
- Buckets: `landing-zone`, `processed` in MinIO.
- MongoDB DB: `workplace_relations`. Collections: `records`, `processed_records`.
- Partitioning: Monthly windows; records carry `partition_date` = first day of month.

**Configuration**
- Env file: `.env` (auto-loaded by scripts). Edit credentials as needed.
- Key variables:
  - `MONGO_URI`
  - `MONGO_DB`
  - `MINIO_ENDPOINT`
  - `MINIO_ACCESS_KEY`
  - `MINIO_SECRET_KEY`
  - `MINIO_BUCKET` (landing-zone)
  - `MINIO_PROCESSED_BUCKET` (processed)
  - `MONGO_PROCESSED_COLLECTION` (processed_records)

**Testing**
- Run unit tests:

```bash
pytest -q
```

**Ingestion Pipeline**

The ingestion pipeline consists of:

1. **WRCSpider** ([src/extract.py](src/extract.py)): Scrapy spider that:
   - Scrapes workplace relations decisions from workplacerelations.ie
   - Partitions date ranges into monthly intervals
   - Handles pagination automatically
   - Extracts metadata from search results

2. **MetadataPipeline** ([src/pipelines.py](src/pipelines.py)): Scrapy pipeline that:
   - Downloads document files (PDF, HTML, DOC, etc.)
   - Detects HTML pages vs binary documents automatically
   - For PDF/DOC files: Downloads and stores as-is
   - For HTML pages: Scrapes web page content and stores as .html files
   - Calculates SHA256 file hash for all files
   - Stores files in MinIO (landing-zone bucket)
   - Persists metadata to MongoDB (landing_metadata collection)
   - Handles errors and duplicates gracefully

3. **Storage Modules** ([src/storage.py](src/storage.py)):
   - **MongoDBStorage**: MongoDB operations (insert, find, update)
   - **MinIOStorage**: Object storage operations (upload, download, exists)
   - **FileDownloader**: HTTP file downloads with retry logic and HTML detection
   - **HTMLScraper**: Web page scraping for HTML content extraction

**Running Ingestion**

```bash
# Basic usage
python -m src.ingest \
  --start-date 2024-01-01 \
  --end-date 2024-03-31 \
  --bodies WRC

# Multiple bodies with JSON output
python -m src.ingest \
  --start-date 2024-01-01 \
  --end-date 2024-12-31 \
  --bodies WRC,LC,EAT,ET \
  --output results.json

# With debug logging
python -m src.ingest \
  --start-date 2024-06-01 \
  --end-date 2024-06-30 \
  --bodies WRC \
  --log-level DEBUG
```

**How It Works**

1. Spider divides date range into monthly partitions
2. For each partition and body type, sends search request with date filters
3. Parses search results to extract metadata (identifier, title, date, link)
4. Pipeline downloads each document file via doc_link
5. Detects content type (HTML vs binary document):
   - **For HTML pages**: Scrapes the web page content using BeautifulSoup and stores as .html
   - **For PDF/DOC files**: Downloads binary content and stores as-is
6. Calculates SHA256 hash of file content
7. Determines file extension from URL or MIME type
8. Uploads file to MinIO: `{bucket}/{partition_date}/{identifier}.ext`
9. Stores metadata in MongoDB with file_path and file_hash
10. Handles pagination to process all results
11. Logs all operations for monitoring and debugging

**Anti-Blocking Features**

- Randomized download delays (configured via `SCRAPY_DOWNLOAD_DELAY`)
- Auto-throttling based on response times
- Configurable concurrent requests
- Retry logic with exponential backoff
- Realistic User-Agent headers
- Request rate limiting per domain

**Valid Body Types:**
- `WRC` - Workplace Relations Commission
- `LC` - Labour Court
- `EAT` - Employment Appeals Tribunal
- `ET` - Equality Tribunal

**Extracted Metadata Fields:**
- `identifier` - Decision reference number (e.g., ADJ-00054658)
- `description` - Case title/description
- `published_date` - Publication date
- `body_type` - The tribunal/commission body
- `source_url` - Search results page URL
- `doc_link` - Direct link to decision document
- `partition_date` - Monthly partition (first day of month)
- `file_path` - MinIO storage path
- `file_hash` - SHA256 hash of file content
- `mime_type` - Document MIME type (PDF, HTML, etc.)
- `status` - Processing status (extracted|transformed|error)
- `created_at` - Record creation timestamp
- `updated_at` - Last update timestamp

**Storage Structure**

Landing Zone (Raw Data):
- **MongoDB**: `{MONGO_DB}/{MONGO_COLLECTION}` (e.g., workplace_relations/records)
  - Each document contains full metadata
  - Indexed by identifier and partition_date
  - Includes file_path and file_hash for each document
  - Status: "transformed" (ready for processing)
- **MinIO**: `{MINIO_BUCKET}/{file_path}` (e.g., landing-zone/workplace-docs/ADJ-00012345.html)
  - Files organized by source structure
  - Original filenames preserved
  - HTML pages stored as .html files
  - Binary documents (PDF, DOC) stored with original extension

Processed Zone (Cleaned Data):
- **MongoDB**: `{MONGO_DB}/{MONGO_PROCESSED_COLLECTION}` (e.g., workplace_relations/processed_records)
  - Transformed metadata with updated file_path and file_hash
  - Status: "processed"
  - Includes transformation_date timestamp
- **MinIO**: `{MINIO_PROCESSED_BUCKET}/{identifier}.ext` (e.g., processed/ADJ-00012345.html)
  - Files renamed to identifier-based naming
  - HTML files have navigation/headers/footers removed
  - PDF/DOC files unchanged (pass-through)
  - New SHA256 hash calculated for transformed content

**Document Processing**

The pipeline intelligently handles different document types:

1. **PDF/DOC Files**:
   - Downloaded as binary content
   - Stored in MinIO with original extension
   - SHA256 hash calculated on raw file content

2. **HTML Pages**:
   - Full page content scraped using BeautifulSoup
   - Stored as .html files in MinIO
   - SHA256 hash calculated on HTML content
   - Preserves document structure for later transformation

**Transformation Pipeline**

The transformation pipeline ([src/transform.py](src/transform.py)) processes landing zone data and creates cleaned, production-ready documents:

1. **TransformationPipeline**: Main orchestrator that:
   - Fetches records from MongoDB by date range
   - Downloads files from landing-zone bucket
   - Processes each file based on type
   - Stores cleaned files in processed bucket
   - Updates metadata in processed_records collection

2. **HTMLContentExtractor**: Cleans HTML documents by:
   - Removing navigation bars, headers, and footers
   - Removing scripts, styles, and buttons
   - Extracting main content area (main, article, or body)
   - Preserving document structure and text
   - Using BeautifulSoup for robust HTML parsing

3. **FileProcessor**: Routes files to appropriate handlers:
   - **HTML files**: Clean with HTMLContentExtractor, recalculate hash
   - **PDF/DOC files**: Pass through unchanged, only rename
   - Generates identifier-based filenames (e.g., ADJ-00012345.pdf)
   - Calculates new SHA256 hash for transformed content

**Running Transformation**

```bash
# Using the example script (edit dates in file)
python examples/run_transformation.py

# Or programmatically
from src.transform import run_transformation_pipeline

stats = run_transformation_pipeline(
    start_date="2024-12-01",
    end_date="2024-12-31",
)

print(f"Processed: {stats['processed']}/{stats['total']}")
```

**Transformation Features**

- **Immutable Landing Zone**: Original data never modified
- **Idempotent Processing**: Safe to rerun transformations
- **Graceful Error Handling**: Failures don't stop pipeline
- **Progress Logging**: Track processing status in real-time
- **Type-Safe**: Full type annotations and validation
- **Tested**: 28 unit tests covering all components

**Notes**
- The spider automatically handles pagination and monthly partitioning
- Documents are downloaded and stored in MinIO with metadata in MongoDB
- HTML pages are scraped and stored with full content
- Binary files (PDF/DOC) are stored as-is
- All file hashes are SHA256 for integrity verification
- All dates use YYYY-MM-DD format
- Transformation creates cleaned, production-ready documents
- Landing zone remains immutable (read-only)
- Vibe coding is avoided by defining explicit schemas, storage layout, and parameters
