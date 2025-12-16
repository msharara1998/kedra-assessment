# Workplace Relations Data Pipeline

A data pipeline for scraping, storing, and transforming workplace relations decisions from the Workplace Relations Commission (WRC) website.

## Features

- **Web Scraping**: Automated extraction of decision records from multiple bodies (WRC, LC, EAT, ET)
- **Monthly Partitioning**: Intelligent date-based partitioning for efficient data processing
- **Document Storage**: Handles PDF, DOC, and HTML documents with automatic type detection
- **Data Transformation**: Cleans and processes raw data for downstream analysis
- **Distributed Storage**: MongoDB for metadata, MinIO for document files
- **Hash Verification**: SHA256 checksums for data integrity

## Prerequisites

- Python 3.10+
- Docker & Docker Compose
- 4GB+ RAM recommended

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository-url>
cd kedra-assessment
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Start Infrastructure

```bash
docker-compose up -d
```

This starts:
- MongoDB on `localhost:27017`
- MinIO on `localhost:9000` (console: `localhost:9001`)

### 4. Configure MinIO

Access MinIO console at http://localhost:9001:
- **Username**: `minioadmin`
- **Password**: `minioadmin`

Create two buckets:
- `landing-zone` (for raw data)
- `processed` (for transformed data)

### 5. Configure Environment

The `.env` file is pre-configured with defaults. Adjust if needed:

```env
# MongoDB
MONGO_URI=mongodb://localhost:27017/
MONGO_DB=workplace_relations
MONGO_COLLECTION=records
MONGO_PROCESSED_COLLECTION=processed_records

# MinIO
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=admin
MINIO_SECRET_KEY=adminadmin
MINIO_BUCKET=landing-zone
MINIO_PROCESSED_BUCKET=processed

# Scrapy (optional tuning)
SCRAPY_CONCURRENT_REQUESTS=10
SCRAPY_DOWNLOAD_DELAY=0.5
```

## Usage

### Run Ingestion Pipeline

Scrape data from the WRC website:

```bash
python -m src.main ingest --start-date 2024-01-01 --end-date 2024-01-31
```

**Options:**
- `--start-date` (required): Start date in YYYY-MM-DD format
- `--end-date` (required): End date in YYYY-MM-DD format
- `--bodies`: Comma-separated list of bodies (e.g., `WRC,LC,EAT,ET`). Defaults to all.
- `--output`: Optional JSON file to export scraped data

**Example - Scrape specific bodies:**
```bash
python -m src.main ingest --start-date 2024-01-01 --end-date 2024-03-31 --bodies WRC,LC
```

**Example - Export to JSON:**
```bash
python -m src.main ingest --start-date 2024-01-01 --end-date 2024-01-31 --output results.json
```

### Run Transformation Pipeline

Transform raw data from landing zone to processed zone:

```bash
python -m src.main transform --start-date 2024-01-01 --end-date 2024-01-31
```

**What it does:**
- Extracts main content from HTML documents
- Renames files to standardized format
- Updates file hashes
- Stores cleaned data in `processed` bucket and collection

## Architecture

```
┌─────────────────┐
│   WRC Website   │
└────────┬────────┘
         │ Scrapy Spider
         ▼
┌─────────────────────────────────────┐
│      Ingestion Pipeline             │
│  • Scrape metadata                  │
│  • Download documents (PDF/HTML)    │
│  • Calculate file hashes            │
└──────┬──────────────────────────────┘
       │
       ├──────────────┬─────────────────┐
       ▼              ▼                 ▼
┌───────────┐  ┌────────────┐   ┌──────────────┐
│  MongoDB  │  │   MinIO    │   │ Metadata     │
│  records  │  │ landing-   │   │ • identifier │
│           │  │  zone      │   │ • file_path  │
│           │  │            │   │ • file_hash  │
└─────┬─────┘  └─────┬──────┘   │ • dates      │
      │              │           └──────────────┘
      │              │
      ▼              ▼
┌─────────────────────────────────────┐
│   Transformation Pipeline           │
│  • Clean HTML content               │
│  • Rename files                     │
│  • Update metadata                  │
└──────┬──────────────────────────────┘
       │
       ├──────────────┬─────────────────┐
       ▼              ▼                 ▼
┌───────────┐  ┌────────────┐   ┌──────────────┐
│  MongoDB  │  │   MinIO    │   │   Cleaned    │
│ processed_│  │ processed  │   │   Documents  │
│  records  │  │            │   │              │
└───────────┘  └────────────┘   └──────────────┘
```

## Project Structure

```
kedra-assessment/
├── src/
│   ├── __init__.py
│   ├── config.py           # Configuration with Pydantic
│   ├── extraction.py       # Spider + ingestion pipeline
│   ├── main.py            # CLI entry point
│   ├── models.py          # Data models
│   ├── pipelines.py       # Scrapy pipeline for file handling
│   ├── storage.py         # MongoDB & MinIO interfaces
│   ├── transform.py       # Transformation pipeline
│   └── utils.py           # Utility functions
├── examples/
│   ├── ingest_example.py
│   └── run_transformation.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── docker-compose.yml     # Infrastructure services
├── requirements.txt       # Python dependencies
├── .env                   # Environment configuration
└── README.md
```

## How It Works

### Ingestion Process

1. **Date Partitioning**: Splits date range into monthly partitions
2. **Web Scraping**: Scrapes each body's decisions with date filters
3. **Pagination**: Automatically follows all result pages
4. **File Download**: Downloads PDF/DOC files or scrapes HTML pages
5. **Storage**: 
   - Saves files to MinIO `landing-zone` bucket
   - Stores metadata in MongoDB `records` collection
6. **Integrity**: Calculates SHA256 hash for each file

### Transformation Process

1. **Fetch Records**: Queries MongoDB for records in date range with status `extracted`
2. **File Processing**:
   - **HTML**: Extracts main content, removes navigation/headers
   - **PDF/DOC**: Passes through unchanged
3. **Storage**:
   - Saves processed files to MinIO `processed` bucket
   - Updates metadata in MongoDB `processed_records` collection
4. **Status Update**: Marks records with status `transformed`

## Data Models

### MongoDB Record Schema

```json
{
  "identifier": "ADJ-00012345",
  "description": "Case description...",
  "published_date": "01 January 2024",
  "body_type": "WRC",
  "source_url": "https://...",
  "doc_link": "https://...",
  "partition_date": "2024-01-01",
  "file_path": "landing-zone/ADJ-00012345.pdf",
  "file_hash": "abc123...",
  "mime_type": "application/pdf",
  "status": "extracted",
  "created_at": "2024-01-15T10:30:00",
  "updated_at": "2024-01-15T10:30:00"
}
```

## Testing

Run unit tests:
```bash
pytest tests/unit/
```

Run integration tests:
```bash
pytest tests/integration/
```

Run end-to-end tests:
```bash
python tests/e2e_ingestion.py
python tests/e2e_transformation.py
```

## Configuration Tuning

### Scraping Performance

Adjust in `.env` to balance speed vs. politeness:

```env
SCRAPY_CONCURRENT_REQUESTS=12    # More = faster (default: 10)
SCRAPY_DOWNLOAD_DELAY=0.25       # Less = faster (default: 0.5)
SCRAPY_AUTOTHROTTLE_TARGET=1.0   # Response time target
```

### Body Types

Available bodies:
- `WRC` - Workplace Relations Commission
- `LC` - Labour Court
- `EAT` - Employment Appeals Tribunal
- `ET` - Equality Tribunal

## Troubleshooting

### MongoDB Connection Error
```bash
# Verify MongoDB is running
docker ps | grep mongo

# Check logs
docker logs wr-mongo
```

### MinIO Connection Error
```bash
# Verify MinIO is running
docker ps | grep minio

# Check logs
docker logs wr-minio

# Ensure buckets exist via console: http://localhost:9001
```

### Scraping Blocked/Slow
- Increase `SCRAPY_DOWNLOAD_DELAY` in `.env`
- Decrease `SCRAPY_CONCURRENT_REQUESTS`
- Check `SCRAPY_USER_AGENT` is set

### No Data Scraped
- Verify date range has data on website
- Check body names are correct (WRC, LC, EAT, ET)
- Review logs for error messages

## Development

### Add New Pipeline Stage

1. Create transformer in `transform.py`
2. Update `TransformationPipeline` class
3. Add tests in `tests/unit/`

### Extend Spider

1. Modify `WRCSpider` in `extraction.py`
2. Update `parse()` method for new fields
3. Update `RecordMetadata` model in `models.py`

## License

[Add your license here]

## Support

For issues and questions, please open a GitHub issue.
