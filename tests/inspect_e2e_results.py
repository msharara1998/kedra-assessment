"""Interactive script to inspect E2E test results.

This script helps you manually verify and inspect the results of E2E tests
by providing easy access to MongoDB and MinIO data with formatted output.

Run with: python tests/inspect_e2e_results.py
"""
from __future__ import annotations

from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import argparse
import json
import sys
import os

from pymongo import MongoClient
from minio import Minio
from minio.error import S3Error
from tabulate import tabulate

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class E2EResultsInspector:
    """Interactive inspector for E2E test results."""

    def __init__(
        self,
        mongo_uri: str = "mongodb://localhost:27017/",
        mongo_db: str = "test_e2e_workplace_relations",
        minio_endpoint: str = "localhost:9000",
        minio_access_key: str = "admin",
        minio_secret_key: str = "adminadmin",
    ) -> None:
        """Initialize inspector."""
        # Load from .env if available
        from dotenv import load_dotenv
        load_dotenv()

        # Override with env vars if present
        minio_access_key = os.getenv("MINIO_ACCESS_KEY", minio_access_key)
        minio_secret_key = os.getenv("MINIO_SECRET_KEY", minio_secret_key)

        self.mongo_client = MongoClient(mongo_uri)
        self.db = self.mongo_client[mongo_db]

        self.minio_client = Minio(
            minio_endpoint,
            access_key=minio_access_key,
            secret_key=minio_secret_key,
            secure=False,
        )

        self.mongo_db_name = mongo_db

    def show_collections_summary(self) -> None:
        """Display summary of all collections."""
        print("\n" + "="*80)
        print("MONGODB COLLECTIONS SUMMARY")
        print("="*80 + "\n")

        collections = self.db.list_collection_names()

        if not collections:
            print("⚠️  No collections found in database")
            return

        summary_data = []
        for coll_name in collections:
            collection = self.db[coll_name]
            count = collection.count_documents({})

            # Get status distribution
            statuses = defaultdict(int)
            for doc in collection.find({}, {"status": 1}):
                status = doc.get("status", "unknown")
                statuses[status] += 1

            status_str = ", ".join([f"{k}: {v}" for k, v in statuses.items()])

            summary_data.append([
                coll_name,
                count,
                status_str
            ])

        print(tabulate(
            summary_data,
            headers=["Collection", "Total Records", "Status Distribution"],
            tablefmt="grid"
        ))

    def show_buckets_summary(self) -> None:
        """Display summary of all MinIO buckets."""
        print("\n" + "="*80)
        print("MINIO BUCKETS SUMMARY")
        print("="*80 + "\n")

        buckets = self.minio_client.list_buckets()

        if not buckets:
            print("⚠️  No buckets found")
            return

        summary_data = []
        for bucket in buckets:
            objects = list(self.minio_client.list_objects(bucket.name, recursive=True))

            # Count by file type
            file_types = defaultdict(int)
            total_size = 0
            for obj in objects:
                ext = Path(obj.object_name).suffix or ".no_ext"
                file_types[ext] += 1
                total_size += obj.size

            file_types_str = ", ".join([f"{k}: {v}" for k, v in sorted(file_types.items())])
            size_mb = total_size / (1024 * 1024)

            summary_data.append([
                bucket.name,
                len(objects),
                f"{size_mb:.2f} MB",
                file_types_str
            ])

        print(tabulate(
            summary_data,
            headers=["Bucket", "Files", "Total Size", "File Types"],
            tablefmt="grid"
        ))

    def show_pagination_results(self, collection_name: str) -> None:
        """Display pagination test results."""
        print("\n" + "="*80)
        print("PAGINATION TEST RESULTS")
        print("="*80 + "\n")

        collection = self.db[collection_name]

        # Find records with page metadata
        records_with_pages = list(collection.find(
            {"metadata.page": {"$exists": True}},
            {"identifier": 1, "metadata": 1, "status": 1}
        ))

        if not records_with_pages:
            print("⚠️  No pagination test data found")
            return

        # Group by page
        page_groups = defaultdict(list)
        for record in records_with_pages:
            page = record["metadata"]["page"]
            page_groups[page].append(record["identifier"])

        print(f"📊 Total records: {len(records_with_pages)}")
        print(f"   Pages: {len(page_groups)}\n")

        page_data = []
        for page in sorted(page_groups.keys()):
            identifiers = page_groups[page]
            page_data.append([
                f"Page {page}",
                len(identifiers),
                ", ".join(identifiers[:3]) + ("..." if len(identifiers) > 3 else "")
            ])

        print(tabulate(
            page_data,
            headers=["Page", "Records", "Sample Identifiers"],
            tablefmt="grid"
        ))

    def show_multiple_html_results(self, collection_name: str) -> None:
        """Display multiple HTML files test results."""
        print("\n" + "="*80)
        print("MULTIPLE HTML FILES TEST RESULTS")
        print("="*80 + "\n")

        collection = self.db[collection_name]

        # Find records with parent_id metadata
        records = list(collection.find(
            {"metadata.parent_id": {"$exists": True}},
            {"identifier": 1, "metadata": 1, "mime_type": 1, "status": 1}
        ))

        if not records:
            print("⚠️  No multiple HTML files test data found")
            return

        # Group by parent
        parent_groups = defaultdict(list)
        for record in records:
            parent_id = record["metadata"]["parent_id"]
            parent_groups[parent_id].append({
                "identifier": record["identifier"],
                "file_name": record["metadata"].get("file_name", "unknown"),
                "mime_type": record.get("mime_type", "unknown")
            })

        print(f"📊 Total HTML files: {len(records)}")
        print(f"   Parent documents: {len(parent_groups)}\n")

        for parent_id in sorted(parent_groups.keys()):
            files = parent_groups[parent_id]
            print(f"📄 {parent_id} ({len(files)} files):")

            file_data = []
            for file_info in files:
                file_data.append([
                    "  " + file_info["identifier"],
                    file_info["file_name"],
                    file_info["mime_type"]
                ])

            print(tabulate(
                file_data,
                headers=["Identifier", "File Name", "MIME Type"],
                tablefmt="simple"
            ))
            print()

    def show_parent_child_results(self, collection_name: str) -> None:
        """Display parent-child extraction results."""
        print("\n" + "="*80)
        print("PARENT-CHILD EXTRACTION RESULTS")
        print("="*80 + "\n")

        collection = self.db[collection_name]

        # Find parent and child records
        parents = list(collection.find(
            {"metadata.role": "parent"},
            {"identifier": 1, "metadata": 1, "status": 1}
        ))

        children = list(collection.find(
            {"metadata.role": "child"},
            {"identifier": 1, "metadata": 1, "status": 1}
        ))

        if not parents and not children:
            print("⚠️  No parent-child test data found")
            return

        print(f"📊 Parent documents: {len(parents)}")
        print(f"   Child documents: {len(children)}\n")

        # Group children by parent
        children_by_parent = defaultdict(list)
        for child in children:
            parent_id = child["metadata"]["parent"]
            children_by_parent[parent_id].append(child["identifier"])

        # Display each hierarchy
        for parent in parents:
            parent_id = parent["identifier"]
            expected_children = parent["metadata"].get("children", [])
            actual_children = children_by_parent.get(parent_id, [])

            status = "✅" if set(expected_children) == set(actual_children) else "❌"
            print(f"{status} Parent: {parent_id}")
            print(f"   Expected children: {len(expected_children)}")
            print(f"   Actual children: {len(actual_children)}")

            if expected_children:
                comparison_data = []
                for expected in expected_children:
                    found = expected in actual_children
                    comparison_data.append([
                        "  " + expected,
                        "✓" if found else "✗"
                    ])

                print(tabulate(
                    comparison_data,
                    headers=["Child ID", "Found"],
                    tablefmt="simple"
                ))
            print()

    def show_transformation_results(
        self,
        source_collection: str,
        dest_collection: str
    ) -> None:
        """Display transformation pipeline results."""
        print("\n" + "="*80)
        print("TRANSFORMATION PIPELINE RESULTS")
        print("="*80 + "\n")

        source_coll = self.db[source_collection]
        dest_coll = self.db[dest_collection]

        source_count = source_coll.count_documents({"status": "extracted"})
        dest_count = dest_coll.count_documents({"status": "transformed"})

        print(f"📊 Source records (extracted): {source_count}")
        print(f"   Destination records (transformed): {dest_count}")
        print(f"   Success rate: {(dest_count/source_count*100):.1f}%\n" if source_count > 0 else "\n")

        # Show transformation by file type
        print("File type distribution:")

        # Source
        source_types = defaultdict(int)
        for doc in source_coll.find({"status": "extracted"}, {"mime_type": 1}):
            mime_type = doc.get("mime_type", "unknown")
            source_types[mime_type] += 1

        # Destination
        dest_types = defaultdict(int)
        for doc in dest_coll.find({"status": "transformed"}, {"mime_type": 1}):
            mime_type = doc.get("mime_type", "unknown")
            dest_types[mime_type] += 1

        type_data = []
        all_types = set(source_types.keys()) | set(dest_types.keys())
        for mime_type in sorted(all_types):
            type_data.append([
                mime_type,
                source_types.get(mime_type, 0),
                dest_types.get(mime_type, 0)
            ])

        print(tabulate(
            type_data,
            headers=["MIME Type", "Source", "Transformed"],
            tablefmt="grid"
        ))

        # Sample transformed records
        print("\n📄 Sample transformed records:")
        samples = list(dest_coll.find({"status": "transformed"}).limit(10))

        if samples:
            sample_data = []
            for sample in samples:
                sample_data.append([
                    sample["identifier"],
                    sample.get("mime_type", "unknown"),
                    Path(sample.get("file_path", "")).name
                ])

            print(tabulate(
                sample_data,
                headers=["Identifier", "Type", "File Name"],
                tablefmt="simple"
            ))
        else:
            print("   No transformed records found")

    def download_sample_file(
        self,
        bucket_name: str,
        identifier: str,
        output_dir: str = "./samples"
    ) -> None:
        """Download a sample file from MinIO for inspection."""
        print(f"\n📥 Downloading sample file: {identifier}")

        # Find object in bucket
        objects = list(self.minio_client.list_objects(bucket_name, recursive=True))

        matching_obj = None
        for obj in objects:
            if identifier in obj.object_name:
                matching_obj = obj
                break

        if not matching_obj:
            print(f"❌ File not found for identifier: {identifier}")
            return

        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Download file
        file_path = output_path / Path(matching_obj.object_name).name

        try:
            self.minio_client.fget_object(
                bucket_name,
                matching_obj.object_name,
                str(file_path)
            )
            print(f"✅ Downloaded to: {file_path}")
            print(f"   Size: {matching_obj.size} bytes")

            # If HTML, show preview
            if file_path.suffix == ".html":
                print(f"\n📄 Content preview (first 500 chars):")
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read(500)
                    print(content)
                    if len(content) == 500:
                        print("...")

        except Exception as e:
            print(f"❌ Error downloading file: {e}")

    def export_collection_to_json(
        self,
        collection_name: str,
        output_file: str,
        limit: Optional[int] = None
    ) -> None:
        """Export collection data to JSON file."""
        print(f"\n💾 Exporting {collection_name} to {output_file}")

        collection = self.db[collection_name]

        query = collection.find()
        if limit:
            query = query.limit(limit)

        records = list(query)

        # Convert ObjectId to string
        for record in records:
            if "_id" in record:
                record["_id"] = str(record["_id"])

        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(records, f, indent=2, default=str)

        print(f"✅ Exported {len(records)} records to {output_path}")


def main() -> None:
    """Main interactive inspection function."""
    parser = argparse.ArgumentParser(
        description="Inspect E2E test results from MongoDB and MinIO"
    )
    parser.add_argument(
        "--mongo-uri",
        default="mongodb://localhost:27017/",
        help="MongoDB connection URI"
    )
    parser.add_argument(
        "--mongo-db",
        default="test_e2e_workplace_relations",
        help="MongoDB database name"
    )
    parser.add_argument(
        "--action",
        choices=[
            "summary",
            "pagination",
            "multiple-html",
            "parent-child",
            "transformation",
            "download",
            "export",
            "all"
        ],
        default="all",
        help="Action to perform"
    )
    parser.add_argument(
        "--collection",
        default="test_comprehensive_records",
        help="Collection name for specific actions"
    )
    parser.add_argument(
        "--dest-collection",
        default="test_comprehensive_processed",
        help="Destination collection for transformation results"
    )
    parser.add_argument(
        "--identifier",
        help="Identifier for download action"
    )
    parser.add_argument(
        "--bucket",
        help="Bucket name for download action"
    )
    parser.add_argument(
        "--output",
        help="Output file path for export action"
    )

    args = parser.parse_args()

    inspector = E2EResultsInspector(
        mongo_uri=args.mongo_uri,
        mongo_db=args.mongo_db
    )

    print("\n" + "="*80)
    print("E2E TEST RESULTS INSPECTOR")
    print("="*80)
    print(f"Database: {args.mongo_db}")
    print("="*80)

    if args.action in ["summary", "all"]:
        inspector.show_collections_summary()
        inspector.show_buckets_summary()

    if args.action in ["pagination", "all"]:
        inspector.show_pagination_results(args.collection)

    if args.action in ["multiple-html", "all"]:
        inspector.show_multiple_html_results(args.collection)

    if args.action in ["parent-child", "all"]:
        inspector.show_parent_child_results(args.collection)

    if args.action in ["transformation", "all"]:
        inspector.show_transformation_results(
            args.collection,
            args.dest_collection
        )

    if args.action == "download":
        if not args.identifier or not args.bucket:
            print("\n❌ Error: --identifier and --bucket required for download action")
            return
        inspector.download_sample_file(args.bucket, args.identifier)

    if args.action == "export":
        if not args.output:
            print("\n❌ Error: --output required for export action")
            return
        inspector.export_collection_to_json(args.collection, args.output)

    print("\n" + "="*80)
    print("INSPECTION COMPLETE")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
