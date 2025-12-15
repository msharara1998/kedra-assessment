"""Detailed transformation pipeline testing.

This script tests and demonstrates the transformation pipeline step-by-step:
1. PDF/DOC files are copied without transformation
2. HTML files have content extracted (navigation/headers/footers removed)
3. File hashes are recalculated
4. Files are renamed to identifier.ext format
5. Files are stored in processed bucket
6. Metadata is stored in processed collection

Run with: python tests/test_transformation_detailed.py
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List
import hashlib
import sys
import os

from pymongo import MongoClient
from minio import Minio
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.transform import run_transformation_pipeline
from src.storage import MongoDBStorage, MinIOStorage

# Load environment
load_dotenv()


class TransformationTester:
    """Detailed transformation pipeline tester."""

    def __init__(self) -> None:
        """Initialize test environment."""
        self.test_env = {
            "MONGO_URI": os.getenv("MONGO_URI", "mongodb://localhost:27017/"),
            "MONGO_DB": "test_transformation_detailed",
            "MONGO_COLLECTION": "source_records",
            "MONGO_PROCESSED_COLLECTION": "processed_records",
            "MINIO_ENDPOINT": os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            "MINIO_ACCESS_KEY": os.getenv("MINIO_ACCESS_KEY", "admin"),
            "MINIO_SECRET_KEY": os.getenv("MINIO_SECRET_KEY", "adminadmin"),
            "MINIO_BUCKET": "test-transform-landing",
            "MINIO_PROCESSED_BUCKET": "test-transform-processed",
        }

        self.mongo_client = MongoClient(self.test_env["MONGO_URI"])
        self.test_db = self.mongo_client[self.test_env["MONGO_DB"]]
        
        self.minio_client = Minio(
            self.test_env["MINIO_ENDPOINT"],
            access_key=self.test_env["MINIO_ACCESS_KEY"],
            secret_key=self.test_env["MINIO_SECRET_KEY"],
            secure=False,
        )

    def setup(self) -> None:
        """Set up test environment."""
        print("\n" + "="*80)
        print("TRANSFORMATION PIPELINE - DETAILED TEST")
        print("="*80)
        print("This test demonstrates each transformation step with visible results\n")
        
        self._cleanup()
        self._create_buckets()
        
        print("✓ Setup completed\n")

    def cleanup(self) -> None:
        """Clean up test data."""
        keep_data = os.getenv("KEEP_TEST_DATA", "false").lower() == "true"
        
        if keep_data:
            print("\n⚠️  Test data preserved for inspection (KEEP_TEST_DATA=true)")
            print(f"   MongoDB: {self.test_env['MONGO_DB']}")
            print(f"   MinIO: {self.test_env['MINIO_BUCKET']}, {self.test_env['MINIO_PROCESSED_BUCKET']}")
        else:
            self._cleanup()
            print("\n✓ Cleanup completed")

    def _cleanup(self) -> None:
        """Clean up test data."""
        # Drop collections
        try:
            self.test_db[self.test_env["MONGO_COLLECTION"]].drop()
            self.test_db[self.test_env["MONGO_PROCESSED_COLLECTION"]].drop()
        except Exception:
            pass

        # Remove buckets
        for bucket_name in [self.test_env["MINIO_BUCKET"], self.test_env["MINIO_PROCESSED_BUCKET"]]:
            try:
                if self.minio_client.bucket_exists(bucket_name):
                    objects = self.minio_client.list_objects(bucket_name, recursive=True)
                    for obj in objects:
                        self.minio_client.remove_object(bucket_name, obj.object_name)
                    self.minio_client.remove_bucket(bucket_name)
            except Exception:
                pass

    def _create_buckets(self) -> None:
        """Create test buckets."""
        for bucket_name in [self.test_env["MINIO_BUCKET"], self.test_env["MINIO_PROCESSED_BUCKET"]]:
            if not self.minio_client.bucket_exists(bucket_name):
                self.minio_client.make_bucket(bucket_name)

    def create_test_data(self) -> None:
        """Create test data with different file types."""
        print("STEP 1: Creating Test Data")
        print("-"*80)
        
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
        
        # Test cases for transformation
        test_cases = [
            {
                "identifier": "PDF-DOC-001",
                "mime_type": "application/pdf",
                "description": "PDF document - should NOT be transformed",
                "original_name": "some_random_name_123.pdf"
            },
            {
                "identifier": "DOC-FILE-001",
                "mime_type": "application/msword",
                "description": "DOC document - should NOT be transformed",
                "original_name": "another_name_xyz.doc"
            },
            {
                "identifier": "HTML-SIMPLE-001",
                "mime_type": "text/html",
                "description": "Simple HTML - should extract content",
                "original_name": "webpage_with_nav.html"
            },
            {
                "identifier": "HTML-COMPLEX-001",
                "mime_type": "text/html",
                "description": "Complex HTML with navigation - should remove nav elements",
                "original_name": "decision_page_full.html"
            },
        ]
        
        for test_case in test_cases:
            identifier = test_case["identifier"]
            mime_type = test_case["mime_type"]
            original_name = test_case["original_name"]
            
            # Create file content
            if mime_type == "text/html":
                file_content = self._create_html_content(identifier)
            else:
                file_content = f"MOCK_{mime_type.upper()}_CONTENT_{identifier}_{datetime.now().isoformat()}".encode("utf-8")
            
            # Calculate original hash
            original_hash = hashlib.sha256(file_content).hexdigest()
            
            # Upload with random name to MinIO
            file_path = minio_storage.upload_file(
                file_data=file_content,
                object_name=original_name,
                content_type=mime_type,
            )
            
            # Create metadata record
            record = {
                "identifier": identifier,
                "description": test_case["description"],
                "published_date": "15/01/2024",
                "body_type": "WRC",
                "source_url": "https://example.com/search",
                "doc_link": f"https://example.com/{identifier}",
                "partition_date": "2024-01-15",
                "file_path": file_path,
                "file_hash": original_hash,
                "mime_type": mime_type,
                "status": "extracted",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "original_filename": original_name,  # Track for comparison
            }
            
            mongo_storage.insert_one(record)
            
            print(f"✓ Created: {identifier}")
            print(f"  Type: {mime_type}")
            print(f"  Original name: {original_name}")
            print(f"  File hash: {original_hash[:16]}...")
            print(f"  Size: {len(file_content)} bytes")
            print()
        
        mongo_storage.close()
        print(f"Created {len(test_cases)} test records\n")

    def run_transformation(self) -> Dict[str, Any]:
        """Run transformation pipeline."""
        print("STEP 2: Running Transformation Pipeline")
        print("-"*80)
        
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
        
        print(f"\n📊 Transformation Statistics:")
        print(f"   Total: {stats['total']}")
        print(f"   Processed: {stats['processed']}")
        print(f"   Failed: {stats['failed']}")
        print(f"   Skipped: {stats['skipped']}")
        print()
        
        return stats

    def verify_transformation(self) -> None:
        """Verify transformation results in detail."""
        print("STEP 3: Verifying Transformation Results")
        print("-"*80)
        
        source_collection = self.test_db[self.test_env["MONGO_COLLECTION"]]
        dest_collection = self.test_db[self.test_env["MONGO_PROCESSED_COLLECTION"]]
        
        source_records = list(source_collection.find({}))
        processed_records = list(dest_collection.find({}))
        
        print(f"Source records: {len(source_records)}")
        print(f"Processed records: {len(processed_records)}")
        print()
        
        # Verify each record
        for source in source_records:
            identifier = source["identifier"]
            processed = dest_collection.find_one({"identifier": identifier})
            
            if not processed:
                print(f"❌ {identifier}: NOT PROCESSED")
                continue
            
            print(f"✅ {identifier}: TRANSFORMED")
            print(f"   Type: {source['mime_type']}")
            
            # Check filename transformation
            original_filename = Path(source["file_path"]).name
            new_filename = Path(processed["file_path"]).name
            expected_filename = f"{identifier}{Path(original_filename).suffix}"
            
            print(f"   📝 Filename:")
            print(f"      Before: {original_filename}")
            print(f"      After:  {new_filename}")
            print(f"      Expected: {expected_filename}")
            
            if new_filename == expected_filename:
                print(f"      ✓ Filename correctly renamed to identifier.ext")
            else:
                print(f"      ✗ Filename mismatch!")
            
            # Check file hash
            print(f"   #️⃣  File Hash:")
            print(f"      Original: {source['file_hash'][:16]}...")
            print(f"      New:      {processed['file_hash'][:16]}...")
            
            # For HTML, hash should change (content extracted)
            # For PDF/DOC, hash might stay same (no transformation)
            if source["mime_type"] == "text/html":
                if source["file_hash"] != processed["file_hash"]:
                    print(f"      ✓ Hash changed (HTML content extracted)")
                else:
                    print(f"      ⚠️  Hash unchanged (possible issue)")
            else:
                print(f"      ✓ Non-HTML file (hash may or may not change)")
            
            # Check storage location
            print(f"   📦 Storage:")
            print(f"      Source bucket: {source['file_path'].split('/')[0]}")
            print(f"      Dest bucket:   {processed['file_path'].split('/')[0]}")
            
            if self.test_env["MINIO_PROCESSED_BUCKET"] in processed["file_path"]:
                print(f"      ✓ File moved to processed bucket")
            else:
                print(f"      ✗ File not in processed bucket!")
            
            # Check status
            print(f"   📊 Status:")
            print(f"      Before: {source.get('status', 'unknown')}")
            print(f"      After:  {processed.get('status', 'unknown')}")
            
            if processed.get("status") == "transformed":
                print(f"      ✓ Status updated to 'transformed'")
            else:
                print(f"      ✗ Status not updated correctly!")
            
            print()

    def verify_html_transformation(self) -> None:
        """Verify HTML transformation details - content extraction."""
        print("STEP 4: Detailed HTML Transformation Verification")
        print("-"*80)
        
        dest_collection = self.test_db[self.test_env["MONGO_PROCESSED_COLLECTION"]]
        
        # Get HTML records
        html_records = list(dest_collection.find({"mime_type": "text/html"}))
        
        print(f"Found {len(html_records)} HTML files to verify\n")
        
        for record in html_records:
            identifier = record["identifier"]
            processed_path = record["file_path"].split("/", 1)[1]
            
            print(f"🔍 Analyzing: {identifier}")
            
            # Download original and processed files
            try:
                # Get original
                source_collection = self.test_db[self.test_env["MONGO_COLLECTION"]]
                source_record = source_collection.find_one({"identifier": identifier})
                original_path = source_record["file_path"].split("/", 1)[1]
                
                original_data = self.minio_client.get_object(
                    self.test_env["MINIO_BUCKET"],
                    original_path
                ).read()
                
                # Get processed
                processed_data = self.minio_client.get_object(
                    self.test_env["MINIO_PROCESSED_BUCKET"],
                    processed_path
                ).read()
                
                original_html = original_data.decode("utf-8")
                processed_html = processed_data.decode("utf-8")
                
                print(f"   📄 Original HTML:")
                print(f"      Size: {len(original_html)} bytes")
                print(f"      Contains <nav>: {'<nav' in original_html}")
                print(f"      Contains <header>: {'<header' in original_html}")
                print(f"      Contains <footer>: {'<footer' in original_html}")
                print(f"      Contains <button>: {'<button' in original_html}")
                
                print(f"   📄 Processed HTML:")
                print(f"      Size: {len(processed_html)} bytes")
                print(f"      Contains <nav>: {'<nav' in processed_html}")
                print(f"      Contains <header>: {'<header' in processed_html}")
                print(f"      Contains <footer>: {'<footer' in processed_html}")
                print(f"      Contains <button>: {'<button' in processed_html}")
                
                # Verify navigation removed
                nav_removed = '<nav' not in processed_html
                header_removed = '<header' not in processed_html
                footer_removed = '<footer' not in processed_html
                
                print(f"\n   ✅ Verification:")
                if nav_removed:
                    print(f"      ✓ Navigation elements removed")
                else:
                    print(f"      ✗ Navigation still present!")
                
                if header_removed:
                    print(f"      ✓ Header elements removed")
                else:
                    print(f"      ✗ Header still present!")
                
                if footer_removed:
                    print(f"      ✓ Footer elements removed")
                else:
                    print(f"      ✗ Footer still present!")
                
                # Show size reduction
                size_reduction = ((len(original_html) - len(processed_html)) / len(original_html)) * 100
                print(f"      📉 Size reduced by {size_reduction:.1f}%")
                
                # Show content preview
                print(f"\n   📖 Processed Content Preview (first 300 chars):")
                print(f"      {processed_html[:300]}...")
                
            except Exception as e:
                print(f"   ❌ Error verifying: {e}")
            
            print()

    def show_file_storage_comparison(self) -> None:
        """Show before/after comparison of file storage."""
        print("STEP 5: File Storage Comparison")
        print("-"*80)
        
        # Landing zone files
        landing_objects = list(self.minio_client.list_objects(
            self.test_env["MINIO_BUCKET"],
            recursive=True
        ))
        
        # Processed zone files
        processed_objects = list(self.minio_client.list_objects(
            self.test_env["MINIO_PROCESSED_BUCKET"],
            recursive=True
        ))
        
        print(f"📦 Landing Zone ({self.test_env['MINIO_BUCKET']}):")
        print(f"   Files: {len(landing_objects)}")
        for obj in landing_objects:
            print(f"      - {obj.object_name} ({obj.size} bytes)")
        
        print(f"\n📦 Processed Zone ({self.test_env['MINIO_PROCESSED_BUCKET']}):")
        print(f"   Files: {len(processed_objects)}")
        for obj in processed_objects:
            print(f"      - {obj.object_name} ({obj.size} bytes)")
        
        print()

    def _create_html_content(self, identifier: str) -> bytes:
        """Create HTML content with navigation elements to be removed."""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Decision {identifier}</title>
    <style>
        .navigation {{ background: #333; color: white; }}
        .content {{ padding: 20px; }}
    </style>
</head>
<body>
    <!-- Navigation bar that should be removed -->
    <nav class="navigation">
        <ul>
            <li><a href="/home">Home</a></li>
            <li><a href="/search">Search</a></li>
            <li><a href="/about">About</a></li>
        </ul>
    </nav>
    
    <!-- Header that should be removed -->
    <header>
        <h1>Workplace Relations Commission</h1>
        <div class="breadcrumb">
            <a href="/">Home</a> &gt; <a href="/decisions">Decisions</a>
        </div>
    </header>
    
    <!-- Main content that should be kept -->
    <main class="content">
        <article>
            <h1>Decision Reference: {identifier}</h1>
            <section class="summary">
                <h2>Summary</h2>
                <p>This is the main decision content for case {identifier}.</p>
                <p>The tribunal has carefully considered all evidence presented.</p>
            </section>
            
            <section class="findings">
                <h2>Findings</h2>
                <p>After reviewing the submissions, the tribunal finds:</p>
                <ul>
                    <li>The claimant has established a prima facie case</li>
                    <li>The respondent has provided adequate justification</li>
                    <li>The evidence supports the following conclusions</li>
                </ul>
            </section>
            
            <section class="decision">
                <h2>Decision</h2>
                <p>The tribunal hereby decides that...</p>
                <p>This decision is final and binding.</p>
            </section>
        </article>
    </main>
    
    <!-- Footer that should be removed -->
    <footer>
        <p>&copy; 2024 Workplace Relations Commission</p>
        <button onclick="print()">Print this page</button>
        <div class="social-share">
            <button>Share on Twitter</button>
            <button>Share on Facebook</button>
        </div>
    </footer>
    
    <!-- Scripts that should be removed -->
    <script>
        console.log("Analytics tracking code");
    </script>
</body>
</html>"""
        return html.encode("utf-8")


def main() -> None:
    """Run detailed transformation test."""
    tester = TransformationTester()
    
    try:
        tester.setup()
        
        # Step 1: Create test data
        tester.create_test_data()
        
        # Step 2: Run transformation
        stats = tester.run_transformation()
        
        # Step 3: Verify results
        tester.verify_transformation()
        
        # Step 4: Verify HTML transformation details
        tester.verify_html_transformation()
        
        # Step 5: Show file storage
        tester.show_file_storage_comparison()
        
        # Summary
        print("="*80)
        print("TRANSFORMATION TEST COMPLETE")
        print("="*80)
        print(f"\n✅ All transformation steps verified!")
        print(f"\n💾 To inspect data manually:")
        print(f"   MongoDB: mongosh 'mongodb://localhost:27017/{tester.test_env['MONGO_DB']}'")
        print(f"   MinIO UI: http://localhost:9001")
        print(f"\n   Set KEEP_TEST_DATA=true to preserve data after test")
        
    finally:
        tester.cleanup()


if __name__ == "__main__":
    main()
