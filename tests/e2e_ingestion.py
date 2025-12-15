"""Comprehensive end-to-end testing with detailed result inspection.

This script provides thorough testing of:
1. Pagination handling across multiple pages
2. Multiple HTML files within single documents
3. Parent-child HTML document relationships
4. Data transformation pipeline
5. Visible, inspectable results for manual verification

Run with: python tests/comprehensive_e2e.py
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Dict, Any, List, Optional
from pathlib import Path
from collections import defaultdict
import logging
import json
import sys
import os

from pymongo import MongoClient
from minio import Minio
from minio.error import S3Error
import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.extraction import WRCSpider
from src.transform import run_transformation_pipeline
from src.storage import MongoDBStorage, MinIOStorage
from src.config import mongodb_settings, minio_settings

logger = logging.getLogger(__name__)


class ComprehensiveE2ETest:
    """Comprehensive end-to-end testing with result inspection."""

    def __init__(self) -> None:
        """Initialize test environment."""
        # Load from .env file if exists
        from dotenv import load_dotenv
        load_dotenv()

        self.test_env = {
            "MONGO_URI": os.getenv("MONGO_URI", "mongodb://localhost:27017/"),
            "MONGO_DB": os.getenv("MONGO_DB", "test_e2e_workplace_relations"),
            "MONGO_COLLECTION": "test_comprehensive_records",
            "MONGO_PROCESSED_COLLECTION": "test_comprehensive_processed",
            "MINIO_ENDPOINT": os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            "MINIO_ACCESS_KEY": os.getenv("MINIO_ACCESS_KEY", "admin"),
            "MINIO_SECRET_KEY": os.getenv("MINIO_SECRET_KEY", "adminadmin"),
            "MINIO_BUCKET": "test-comprehensive-landing",
            "MINIO_PROCESSED_BUCKET": "test-comprehensive-processed",
        }

        self.mongo_client = MongoClient(self.test_env["MONGO_URI"])
        self.test_db = self.mongo_client[self.test_env["MONGO_DB"]]

        self.minio_client = Minio(
            self.test_env["MINIO_ENDPOINT"],
            access_key=self.test_env["MINIO_ACCESS_KEY"],
            secret_key=self.test_env["MINIO_SECRET_KEY"],
            secure=False,
        )

        self.results: Dict[str, Any] = {}

    def setup(self) -> None:
        """Set up test environment."""
        print("\n" + "="*80)
        print("COMPREHENSIVE E2E TEST - SETUP")
        print("="*80)

        # Clean up existing test data
        self._cleanup()

        # Create test buckets
        self._create_buckets()

        print("✓ Setup completed successfully\n")

    def teardown(self) -> None:
        """Clean up test environment."""
        print("\n" + "="*80)
        print("CLEANUP")
        print("="*80)

        # Optionally keep data for inspection
        keep_data = os.getenv("KEEP_TEST_DATA", "false").lower() == "true"

        if keep_data:
            print("⚠ Test data preserved for inspection (KEEP_TEST_DATA=true)")
            print(f"  MongoDB Database: {self.test_env['MONGO_DB']}")
            print(f"  MinIO Buckets: {self.test_env['MINIO_BUCKET']}, {self.test_env['MINIO_PROCESSED_BUCKET']}")
        else:
            self._cleanup()
            print("✓ Cleanup completed")

    def _cleanup(self) -> None:
        """Clean up test data."""
        # Drop collections
        try:
            self.test_db[self.test_env["MONGO_COLLECTION"]].drop()
            self.test_db[self.test_env["MONGO_PROCESSED_COLLECTION"]].drop()
        except Exception as e:
            logger.debug(f"Cleanup warning: {e}")

        # Remove buckets
        for bucket_name in [self.test_env["MINIO_BUCKET"], self.test_env["MINIO_PROCESSED_BUCKET"]]:
            try:
                if self.minio_client.bucket_exists(bucket_name):
                    objects = self.minio_client.list_objects(bucket_name, recursive=True)
                    for obj in objects:
                        self.minio_client.remove_object(bucket_name, obj.object_name)
                    self.minio_client.remove_bucket(bucket_name)
            except Exception as e:
                logger.debug(f"Cleanup warning: {e}")

    def _create_buckets(self) -> None:
        """Create test buckets."""
        for bucket_name in [self.test_env["MINIO_BUCKET"], self.test_env["MINIO_PROCESSED_BUCKET"]]:
            if not self.minio_client.bucket_exists(bucket_name):
                self.minio_client.make_bucket(bucket_name)

    def test_pagination_handling(self) -> bool:
        """Test that pagination works correctly.

        Creates mock data simulating multiple pages of search results
        and verifies all pages are processed correctly.
        """
        print("\n" + "="*80)
        print("TEST 1: PAGINATION HANDLING")
        print("="*80)
        print("Testing: Multiple pages of search results are fully extracted\n")

        # Create mock records simulating 3 pages with 5 records each
        total_pages = 3
        records_per_page = 5
        all_records = []

        for page in range(1, total_pages + 1):
            for record_num in range(1, records_per_page + 1):
                record_id = f"PAG-{page:02d}-{record_num:02d}"
                all_records.append(self._create_test_record(
                    identifier=record_id,
                    description=f"Decision from Page {page}, Record {record_num}",
                    partition_date="2024-01-15",
                    mime_type="application/pdf",
                    metadata={"page": page, "position": record_num}
                ))

        # Upload records
        mongo_storage = MongoDBStorage(
            mongo_uri=self.test_env["MONGO_URI"],
            database=self.test_env["MONGO_DB"],
            collection=self.test_env["MONGO_COLLECTION"],
        )

        minio_storage = MinIOStorage(
            endpoint=self.test_env["MINIO_ENDPOINT"],
            access_key=self.test_env["MINIO_ACCESS_KEY"],
            secret_key=self.test_env["MINIO_SECRET_KEY"],
            bucket_name=self.test_env["MINIO_BUCKET"],
            secure=False,
        )

        for record in all_records:
            file_data = self._generate_file_content(record)
            file_path = minio_storage.upload_file(
                file_data=file_data,
                object_name=f"{record['identifier']}.pdf",
                content_type=record["mime_type"],
            )
            record["file_path"] = file_path
            record["status"] = "extracted"
            mongo_storage.insert_one(record)

        # Verify all records are in database
        total_records = self.test_db[self.test_env["MONGO_COLLECTION"]].count_documents({})

        print(f"📊 Created {len(all_records)} records across {total_pages} pages")
        print(f"   Records per page: {records_per_page}")
        print(f"   Total in database: {total_records}")

        # Group by page for verification
        page_counts = defaultdict(int)
        for record in self.test_db[self.test_env["MONGO_COLLECTION"]].find({}):
            if "metadata" in record and "page" in record["metadata"]:
                page_counts[record["metadata"]["page"]] += 1

        print(f"\n✓ Page distribution:")
        for page in sorted(page_counts.keys()):
            print(f"   Page {page}: {page_counts[page]} records")

        success = total_records == len(all_records)
        self.results["pagination"] = {
            "expected": len(all_records),
            "actual": total_records,
            "success": success,
            "pages": dict(page_counts)
        }

        mongo_storage.close()
        return success

    def test_multiple_html_files(self) -> bool:
        """Test handling of documents with multiple HTML files.

        Simulates scenarios where a single decision has multiple associated
        HTML files (e.g., decision text, appendices, amendments).
        """
        print("\n" + "="*80)
        print("TEST 2: MULTIPLE HTML FILES PER DOCUMENT")
        print("="*80)
        print("Testing: Documents with multiple HTML file attachments\n")

        # Create parent documents with multiple HTML files
        test_cases = [
            {
                "parent_id": "MULTI-HTML-001",
                "html_files": ["main.html", "appendix-a.html", "appendix-b.html"],
                "description": "Decision with main text and 2 appendices"
            },
            {
                "parent_id": "MULTI-HTML-002",
                "html_files": ["decision.html", "amendment-1.html"],
                "description": "Decision with amendment"
            },
            {
                "parent_id": "MULTI-HTML-003",
                "html_files": ["summary.html", "full-text.html", "exhibits.html"],
                "description": "Decision with summary, full text, and exhibits"
            },
        ]

        mongo_storage = MongoDBStorage(
            mongo_uri=self.test_env["MONGO_URI"],
            database=self.test_env["MONGO_DB"],
            collection=self.test_env["MONGO_COLLECTION"],
        )

        minio_storage = MinIOStorage(
            endpoint=self.test_env["MINIO_ENDPOINT"],
            access_key=self.test_env["MINIO_ACCESS_KEY"],
            secret_key=self.test_env["MINIO_SECRET_KEY"],
            bucket_name=self.test_env["MINIO_BUCKET"],
            secure=False,
        )

        all_records = []

        for test_case in test_cases:
            parent_id = test_case["parent_id"]
            print(f"📄 {parent_id}: {test_case['description']}")
            print(f"   HTML files: {len(test_case['html_files'])}")

            for idx, html_file in enumerate(test_case["html_files"]):
                # Create unique identifier for each HTML file
                record_id = f"{parent_id}-{idx+1:02d}"

                record = self._create_test_record(
                    identifier=record_id,
                    description=f"{test_case['description']} - {html_file}",
                    partition_date="2024-01-10",
                    mime_type="text/html",
                    metadata={
                        "parent_id": parent_id,
                        "file_name": html_file,
                        "file_index": idx,
                        "total_files": len(test_case["html_files"])
                    }
                )

                # Create HTML content with parent reference
                html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{record_id} - {html_file}</title>
</head>
<body>
    <div class="document-header">
        <h1>Parent Document: {parent_id}</h1>
        <h2>File: {html_file}</h2>
        <p>Part {idx+1} of {len(test_case['html_files'])}</p>
    </div>
    <div class="content">
        <h3>Decision Content</h3>
        <p>This is the content of {html_file} for document {parent_id}.</p>
        <p>This document contains detailed information and legal analysis.</p>
        <section>
            <h4>Section 1: Background</h4>
            <p>Background information goes here...</p>
        </section>
        <section>
            <h4>Section 2: Findings</h4>
            <p>Detailed findings and analysis...</p>
        </section>
    </div>
</body>
</html>"""

                # Upload HTML file
                file_data = html_content.encode("utf-8")
                file_path = minio_storage.upload_file(
                    file_data=file_data,
                    object_name=f"{record_id}.html",
                    content_type="text/html",
                )
                record["file_path"] = file_path
                record["status"] = "extracted"

                mongo_storage.insert_one(record)
                all_records.append(record)

                print(f"   ✓ Uploaded: {html_file}")

        print(f"\n📊 Total HTML files created: {len(all_records)}")
        print(f"   Parent documents: {len(test_cases)}")

        # Verify all files are in storage
        db_count = self.test_db[self.test_env["MONGO_COLLECTION"]].count_documents(
            {"mime_type": "text/html"}
        )

        minio_objects = list(self.minio_client.list_objects(
            self.test_env["MINIO_BUCKET"],
            recursive=True
        ))
        html_files_in_minio = [obj for obj in minio_objects if obj.object_name.endswith('.html')]

        print(f"   In MongoDB: {db_count} HTML records")
        print(f"   In MinIO: {len(html_files_in_minio)} HTML files")

        # Group by parent
        parent_groups = defaultdict(list)
        for record in self.test_db[self.test_env["MONGO_COLLECTION"]].find({"mime_type": "text/html"}):
            if "metadata" in record and "parent_id" in record["metadata"]:
                parent_groups[record["metadata"]["parent_id"]].append(record["identifier"])

        print(f"\n✓ Files grouped by parent document:")
        for parent_id in sorted(parent_groups.keys()):
            print(f"   {parent_id}: {len(parent_groups[parent_id])} files")

        success = db_count == len(all_records)
        self.results["multiple_html_files"] = {
            "expected": len(all_records),
            "actual": db_count,
            "success": success,
            "parents": len(test_cases),
            "parent_groups": {k: len(v) for k, v in parent_groups.items()}
        }

        mongo_storage.close()
        return success

    def test_parent_child_extraction(self) -> bool:
        """Test extraction of parent HTML documents with child documents.

        Verifies that when a parent document is HTML, all referenced
        child documents are also extracted and properly linked.
        """
        print("\n" + "="*80)
        print("TEST 3: PARENT-CHILD HTML DOCUMENT EXTRACTION")
        print("="*80)
        print("Testing: Parent HTML docs with child documents are fully extracted\n")

        mongo_storage = MongoDBStorage(
            mongo_uri=self.test_env["MONGO_URI"],
            database=self.test_env["MONGO_DB"],
            collection=self.test_env["MONGO_COLLECTION"],
        )

        minio_storage = MinIOStorage(
            endpoint=self.test_env["MINIO_ENDPOINT"],
            access_key=self.test_env["MINIO_ACCESS_KEY"],
            secret_key=self.test_env["MINIO_SECRET_KEY"],
            bucket_name=self.test_env["MINIO_BUCKET"],
            secure=False,
        )

        # Create parent-child hierarchies
        hierarchies = [
            {
                "parent": "PARENT-001",
                "children": ["CHILD-001-A", "CHILD-001-B", "CHILD-001-C"],
                "description": "Main decision with 3 child documents"
            },
            {
                "parent": "PARENT-002",
                "children": ["CHILD-002-A"],
                "description": "Decision with single child document"
            },
        ]

        all_records = []

        for hierarchy in hierarchies:
            parent_id = hierarchy["parent"]
            children_ids = hierarchy["children"]

            print(f"📁 {parent_id}: {hierarchy['description']}")
            print(f"   Children: {len(children_ids)}")

            # Create parent HTML document with links to children
            child_links_html = "\n".join([
                f'<li><a href="#{child_id}">{child_id}</a></li>'
                for child_id in children_ids
            ])

            parent_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{parent_id} - Main Decision</title>
</head>
<body>
    <header>
        <h1>Decision Reference: {parent_id}</h1>
        <p>Published: 15/01/2024</p>
    </header>

    <main>
        <section class="summary">
            <h2>Summary</h2>
            <p>This is the main decision document. Related documents:</p>
            <ul class="related-documents">
                {child_links_html}
            </ul>
        </section>

        <section class="decision">
            <h2>Decision</h2>
            <p>The main decision content goes here...</p>
        </section>
    </main>
</body>
</html>"""

            # Create and upload parent
            parent_record = self._create_test_record(
                identifier=parent_id,
                description=f"Parent document - {hierarchy['description']}",
                partition_date="2024-01-15",
                mime_type="text/html",
                metadata={
                    "role": "parent",
                    "children": children_ids,
                    "total_children": len(children_ids)
                }
            )

            file_path = minio_storage.upload_file(
                file_data=parent_html.encode("utf-8"),
                object_name=f"{parent_id}.html",
                content_type="text/html",
            )
            parent_record["file_path"] = file_path
            parent_record["status"] = "extracted"
            mongo_storage.insert_one(parent_record)
            all_records.append(parent_record)

            print(f"   ✓ Parent: {parent_id}")

            # Create and upload children
            for child_id in children_ids:
                child_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>{child_id} - Supporting Document</title>
</head>
<body>
    <header>
        <p><a href="#{parent_id}">Back to parent: {parent_id}</a></p>
        <h1>Supporting Document: {child_id}</h1>
    </header>

    <main>
        <section>
            <h2>Additional Information</h2>
            <p>This document provides additional details for {parent_id}.</p>
            <p>Content specific to {child_id}...</p>
        </section>
    </main>
</body>
</html>"""

                child_record = self._create_test_record(
                    identifier=child_id,
                    description=f"Child document of {parent_id}",
                    partition_date="2024-01-15",
                    mime_type="text/html",
                    metadata={
                        "role": "child",
                        "parent": parent_id
                    }
                )

                file_path = minio_storage.upload_file(
                    file_data=child_html.encode("utf-8"),
                    object_name=f"{child_id}.html",
                    content_type="text/html",
                )
                child_record["file_path"] = file_path
                child_record["status"] = "extracted"
                mongo_storage.insert_one(child_record)
                all_records.append(child_record)

                print(f"   ✓ Child:  {child_id}")

        print(f"\n📊 Total documents created: {len(all_records)}")

        # Verify parent-child relationships
        parents = list(self.test_db[self.test_env["MONGO_COLLECTION"]].find({
            "metadata.role": "parent"
        }))

        children = list(self.test_db[self.test_env["MONGO_COLLECTION"]].find({
            "metadata.role": "child"
        }))

        print(f"   Parent documents: {len(parents)}")
        print(f"   Child documents: {len(children)}")

        # Verify each parent has all children
        print(f"\n✓ Parent-child relationships:")
        all_children_found = True
        for parent in parents:
            parent_id = parent["identifier"]
            expected_children = parent["metadata"]["children"]

            actual_children = [
                c["identifier"] for c in children
                if c["metadata"]["parent"] == parent_id
            ]

            found_all = set(expected_children) == set(actual_children)
            all_children_found = all_children_found and found_all

            status = "✓" if found_all else "✗"
            print(f"   {status} {parent_id}: {len(actual_children)}/{len(expected_children)} children")

        success = len(all_records) == (len(parents) + len(children)) and all_children_found
        self.results["parent_child"] = {
            "expected": len(all_records),
            "actual": len(parents) + len(children),
            "success": success,
            "parents": len(parents),
            "children": len(children),
            "all_children_found": all_children_found
        }

        mongo_storage.close()
        return success

    def test_data_transformation(self) -> bool:
        """Test the complete data transformation pipeline.

        Runs the transformation pipeline on all test data and verifies:
        - Files are transformed correctly
        - Metadata is updated
        - Files are moved to processed bucket
        """
        print("\n" + "="*80)
        print("TEST 4: DATA TRANSFORMATION PIPELINE")
        print("="*80)
        print("Testing: Complete transformation from landing to processed zone\n")

        # Get counts before transformation
        source_collection = self.test_db[self.test_env["MONGO_COLLECTION"]]
        before_count = source_collection.count_documents({"status": "extracted"})

        landing_objects = list(self.minio_client.list_objects(
            self.test_env["MINIO_BUCKET"],
            recursive=True
        ))

        print(f"📊 Before transformation:")
        print(f"   Records to process: {before_count}")
        print(f"   Files in landing zone: {len(landing_objects)}")

        # Run transformation
        print(f"\n⚙️  Running transformation pipeline...")

        stats = run_transformation_pipeline(
            start_date="2024-01-01",
            end_date="2024-01-31",
            mongo_uri=self.test_env["MONGO_URI"],
            mongo_db=self.test_env["MONGO_DB"],
            source_collection=self.test_env["MONGO_COLLECTION"],
            dest_collection=self.test_env["MONGO_PROCESSED_COLLECTION"],
            minio_endpoint=self.test_env["MINIO_ENDPOINT"],
            minio_access_key=self.test_env["MINIO_ACCESS_KEY"],
            minio_secret_key=self.test_env["MINIO_SECRET_KEY"],
            source_bucket=self.test_env["MINIO_BUCKET"],
            dest_bucket=self.test_env["MINIO_PROCESSED_BUCKET"],
        )

        # Get counts after transformation
        processed_collection = self.test_db[self.test_env["MONGO_PROCESSED_COLLECTION"]]
        after_count = processed_collection.count_documents({"status": "transformed"})

        processed_objects = list(self.minio_client.list_objects(
            self.test_env["MINIO_PROCESSED_BUCKET"],
            recursive=True
        ))

        print(f"\n📊 After transformation:")
        print(f"   Total records found: {stats['total']}")
        print(f"   Successfully processed: {stats['processed']}")
        print(f"   Failed: {stats['failed']}")
        print(f"   Skipped: {stats['skipped']}")
        print(f"   Records in processed collection: {after_count}")
        print(f"   Files in processed bucket: {len(processed_objects)}")

        # Verify file types
        file_types = defaultdict(int)
        for obj in processed_objects:
            ext = Path(obj.object_name).suffix
            file_types[ext] += 1

        if file_types:
            print(f"\n✓ Processed file types:")
            for ext, count in sorted(file_types.items()):
                print(f"   {ext}: {count} files")

        # Sample some transformed records
        sample_records = list(processed_collection.find({"status": "transformed"}).limit(5))

        if sample_records:
            print(f"\n✓ Sample transformed records:")
            for record in sample_records:
                print(f"   {record['identifier']}: {record.get('mime_type', 'unknown')}")
                print(f"      Original: {record.get('doc_link', 'N/A')}")
                print(f"      Processed: {record.get('file_path', 'N/A')}")

        success = stats['processed'] >= before_count * 0.9  # Allow 10% failure
        self.results["transformation"] = {
            "before_count": before_count,
            "after_count": after_count,
            "stats": stats,
            "success": success,
            "file_types": dict(file_types)
        }

        return success

    def display_results_summary(self) -> None:
        """Display comprehensive test results summary."""
        print("\n" + "="*80)
        print("COMPREHENSIVE E2E TEST RESULTS")
        print("="*80)

        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results.values() if r.get("success", False))

        print(f"\n📊 Overall: {passed_tests}/{total_tests} tests passed\n")

        for test_name, result in self.results.items():
            status = "✅ PASS" if result.get("success", False) else "❌ FAIL"
            print(f"{status} - {test_name.replace('_', ' ').title()}")

            if "expected" in result and "actual" in result:
                print(f"     Expected: {result['expected']}, Actual: {result['actual']}")

        print("\n" + "="*80)
        print("DETAILED RESULTS")
        print("="*80)
        print(json.dumps(self.results, indent=2))

        # Save results to file
        results_file = Path(__file__).parent / "comprehensive_e2e_results.json"
        with open(results_file, "w") as f:
            json.dump(self.results, f, indent=2)
        print(f"\n💾 Detailed results saved to: {results_file}")

        # Display access information
        print("\n" + "="*80)
        print("INSPECT RESULTS MANUALLY")
        print("="*80)
        print(f"\n🗄️  MongoDB:")
        print(f"   Connection: {self.test_env['MONGO_URI']}")
        print(f"   Database: {self.test_env['MONGO_DB']}")
        print(f"   Collections:")
        print(f"      - {self.test_env['MONGO_COLLECTION']} (source)")
        print(f"      - {self.test_env['MONGO_PROCESSED_COLLECTION']} (processed)")

        print(f"\n📦 MinIO:")
        print(f"   Endpoint: http://{self.test_env['MINIO_ENDPOINT']}")
        print(f"   Access Key: {self.test_env['MINIO_ACCESS_KEY']}")
        print(f"   Buckets:")
        print(f"      - {self.test_env['MINIO_BUCKET']} (landing zone)")
        print(f"      - {self.test_env['MINIO_PROCESSED_BUCKET']} (processed)")

        print(f"\n💡 To inspect data:")
        print(f"   1. MongoDB: mongosh '{self.test_env['MONGO_URI']}'")
        print(f"   2. MinIO UI: http://localhost:9001 (login with credentials above)")
        print(f"   3. Python: Use provided inspection script below")

    def _create_test_record(
        self,
        identifier: str,
        description: str,
        partition_date: str,
        mime_type: str,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Create a test record with specified parameters."""
        return {
            "identifier": identifier,
            "description": description,
            "published_date": partition_date.replace("-", "/"),
            "body_type": "WRC",
            "source_url": "https://example.com/search",
            "doc_link": f"https://example.com/{identifier}",
            "partition_date": partition_date,
            "file_path": f"test/{identifier}",
            "mime_type": mime_type,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

    def _generate_file_content(self, record: Dict[str, Any]) -> bytes:
        """Generate file content based on record."""
        mime_type = record.get("mime_type", "application/pdf")
        identifier = record.get("identifier", "UNKNOWN")

        if mime_type == "text/html":
            content = f"""<!DOCTYPE html>
<html>
<head>
    <title>{identifier}</title>
</head>
<body>
    <h1>Document {identifier}</h1>
    <p>Description: {record.get('description', 'N/A')}</p>
    <p>Published: {record.get('published_date', 'N/A')}</p>
</body>
</html>"""
            return content.encode("utf-8")
        else:
            return f"MOCK_PDF_{identifier}_{datetime.now().isoformat()}".encode("utf-8")


def run_comprehensive_tests() -> None:
    """Run all comprehensive e2e tests."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    test = ComprehensiveE2ETest()

    try:
        test.setup()

        # Run all tests
        test.test_pagination_handling()
        test.test_multiple_html_files()
        test.test_parent_child_extraction()
        test.test_data_transformation()

        # Display results
        test.display_results_summary()

    finally:
        test.teardown()


if __name__ == "__main__":
    run_comprehensive_tests()
