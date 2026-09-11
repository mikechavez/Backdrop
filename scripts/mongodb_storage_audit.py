#!/usr/bin/env python
"""
MongoDB storage audit tool for diagnosing and recovering quota exhaustion.

Read-only diagnostic script. No destructive operations without explicit --confirm flags.
Credentials are read from MONGODB_URI environment variable only; never embedded in script.

Usage:
    python scripts/mongodb_storage_audit.py --help
    python scripts/mongodb_storage_audit.py --database crypto_news
    python scripts/mongodb_storage_audit.py --database crypto_news --show-indexes
"""

import os
import sys
import argparse
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from urllib.parse import urlparse

import pymongo
from pymongo import MongoClient
from pymongo.errors import OperationFailure, ConnectionFailure, ConfigurationError


class MongoStorageAudit:
    """Read-only MongoDB storage audit tool."""

    def __init__(self, mongodb_uri: Optional[str] = None, database_name: str = "crypto_news", verbose: bool = False):
        """
        Initialize audit tool.

        Args:
            mongodb_uri: MongoDB connection URI (from env if None)
            database_name: Target database name
            verbose: Enable verbose logging
        """
        self.mongodb_uri = mongodb_uri or os.getenv("MONGODB_URI")
        if not self.mongodb_uri:
            raise ConfigurationError(
                "MONGODB_URI not provided and not set in environment. "
                "Please set MONGODB_URI environment variable or pass --uri."
            )

        self.database_name = database_name
        self.verbose = verbose
        self.client: Optional[MongoClient] = None
        self.db = None
        self._redacted_uri = self._redact_uri(self.mongodb_uri)

    @staticmethod
    def _redact_uri(uri: str) -> str:
        """Redact credentials from URI for safe logging."""
        try:
            parsed = urlparse(uri)
            if parsed.password:
                return uri.replace(parsed.password, "***")
            return uri[:50] + "..." if len(uri) > 50 else uri
        except Exception:
            return "mongodb://***"

    def connect(self) -> None:
        """Establish MongoDB connection."""
        try:
            self.client = MongoClient(
                self.mongodb_uri,
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=10000,
            )
            self.client.admin.command("ping")
            self.db = self.client[self.database_name]
            if self.verbose:
                print(f"✓ Connected to {self.database_name} at {self._redacted_uri}")
        except ConnectionFailure as e:
            raise ConfigurationError(f"Failed to connect to MongoDB: {e}")

    def close(self) -> None:
        """Close MongoDB connection."""
        if self.client:
            self.client.close()

    def get_db_stats(self) -> Dict[str, Any]:
        """Fetch database-level storage statistics."""
        try:
            stats = self.db.command("dbStats")
            return {
                "db_name": stats.get("db"),
                "collections": stats.get("collections"),
                "data_size_bytes": stats.get("dataSize", 0),
                "storage_size_bytes": stats.get("storageSize", 0),
                "indexes_size_bytes": stats.get("indexSize", 0),
                "avg_obj_size_bytes": stats.get("avgObjSize", 0),
            }
        except OperationFailure as e:
            print(f"⚠ dbStats failed: {e}", file=sys.stderr)
            return {}

    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """Fetch collection-level storage and document statistics."""
        try:
            stats = self.db.command("collStats", collection_name)
            return {
                "collection": collection_name,
                "document_count": stats.get("count", 0),
                "avg_doc_size_bytes": stats.get("avgObjSize", 0),
                "data_size_bytes": stats.get("size", 0),
                "storage_size_bytes": stats.get("storageSize", 0),
                "indexes_count": stats.get("nindexes", 0),
                "total_index_size_bytes": stats.get("totalIndexSize", 0),
            }
        except OperationFailure as e:
            if self.verbose:
                print(f"⚠ collStats({collection_name}) failed: {e}", file=sys.stderr)
            return {}

    def get_index_details(self, collection_name: str) -> List[Dict[str, Any]]:
        """Fetch index metadata and sizes for a collection."""
        try:
            collection = self.db[collection_name]
            index_info = collection.index_information()
            index_stats = collection.aggregate([
                {"$indexStats": {}}
            ])

            stats_by_name = {}
            for stat in index_stats:
                idx_name = stat.get("name", "unknown")
                stats_by_name[idx_name] = {
                    "size_bytes": stat.get("size", {}).get("bytes", 0),
                    "accesses_count": stat.get("accesses", {}).get("ops", 0),
                }

            indexes = []
            for idx_name, idx_spec in index_info.items():
                if idx_name == "_id_":
                    continue
                indexes.append({
                    "name": idx_name,
                    "keys": idx_spec.get("key", []),
                    "size_bytes": stats_by_name.get(idx_name, {}).get("size_bytes", 0),
                    "accesses": stats_by_name.get(idx_name, {}).get("accesses_count", 0),
                    "unique": idx_spec.get("unique", False),
                    "ttl": idx_spec.get("expireAfterSeconds"),
                })
            return indexes
        except OperationFailure as e:
            if self.verbose:
                print(f"⚠ Index details for {collection_name} failed: {e}", file=sys.stderr)
            return []

    def get_age_distribution(
        self,
        collection_name: str,
        timestamp_field: str = "created_at",
        buckets: int = 5,
    ) -> Dict[str, Any]:
        """
        Get age distribution of documents (for retention planning).

        Args:
            collection_name: Target collection
            timestamp_field: Field name for timestamp
            buckets: Number of age buckets (5 = <1d, 1-7d, 7-30d, 30-90d, >90d)

        Returns:
            Age distribution summary
        """
        try:
            collection = self.db[collection_name]
            now = datetime.utcnow()

            # Verify field exists
            sample = collection.find_one({timestamp_field: {"$exists": True}})
            if not sample:
                return {"collection": collection_name, "field": timestamp_field, "status": "no_documents"}

            # Get age range
            oldest_doc = collection.find_one(
                {timestamp_field: {"$exists": True}},
                sort=[(timestamp_field, 1)]
            )
            newest_doc = collection.find_one(
                {timestamp_field: {"$exists": True}},
                sort=[(timestamp_field, -1)]
            )

            if not oldest_doc or not newest_doc:
                return {"collection": collection_name, "field": timestamp_field, "status": "no_documents"}

            oldest_ts = oldest_doc.get(timestamp_field)
            newest_ts = newest_doc.get(timestamp_field)

            if not isinstance(oldest_ts, datetime) or not isinstance(newest_ts, datetime):
                return {"collection": collection_name, "field": timestamp_field, "status": "invalid_timestamps"}

            # Calculate age distribution
            total_count = collection.count_documents({timestamp_field: {"$exists": True}})

            age_ranges = [
                (timedelta(days=1), "<1 day"),
                (timedelta(days=7), "1-7 days"),
                (timedelta(days=30), "7-30 days"),
                (timedelta(days=90), "30-90 days"),
                (None, ">90 days"),
            ]

            distribution = {}
            for days_back, label in age_ranges:
                if days_back is None:
                    cutoff = now - timedelta(days=90)
                    count = collection.count_documents({timestamp_field: {"$lt": cutoff}})
                else:
                    cutoff = now - days_back
                    count = collection.count_documents({
                        timestamp_field: {
                            "$gte": now - days_back,
                            "$lt": now if days_back == timedelta(days=1) else now - (days_back - timedelta(days=1))
                        }
                    })
                distribution[label] = count

            return {
                "collection": collection_name,
                "field": timestamp_field,
                "total_documents": total_count,
                "oldest_document_age": (now - oldest_ts).days,
                "newest_document_age": (now - newest_ts).days,
                "age_distribution": distribution,
                "oldest_ts": oldest_ts.isoformat(),
                "newest_ts": newest_ts.isoformat(),
            }
        except Exception as e:
            if self.verbose:
                print(f"⚠ Age distribution for {collection_name}.{timestamp_field} failed: {e}", file=sys.stderr)
            return {"collection": collection_name, "field": timestamp_field, "status": f"error: {e}"}

    def check_ttl_index(self, collection_name: str) -> Dict[str, Any]:
        """Check if a collection has a valid TTL index."""
        try:
            collection = self.db[collection_name]
            indexes = collection.index_information()
            ttl_indexes = []
            for idx_name, idx_spec in indexes.items():
                if "expireAfterSeconds" in idx_spec:
                    ttl_indexes.append({
                        "name": idx_name,
                        "field": idx_spec.get("key", []),
                        "ttl_seconds": idx_spec.get("expireAfterSeconds"),
                    })
            return {
                "collection": collection_name,
                "has_ttl": len(ttl_indexes) > 0,
                "ttl_indexes": ttl_indexes,
            }
        except Exception as e:
            if self.verbose:
                print(f"⚠ TTL check for {collection_name} failed: {e}", file=sys.stderr)
            return {"collection": collection_name, "has_ttl": False, "error": str(e)}

    def get_duplicate_fingerprints(self, collection_name: str = "articles", limit: int = 100) -> Dict[str, Any]:
        """Find articles with duplicate fingerprints (candidates for cleanup)."""
        try:
            collection = self.db[collection_name]
            duplicates = list(collection.aggregate([
                {"$match": {"fingerprint": {"$exists": True, "$ne": None}}},
                {"$group": {
                    "_id": "$fingerprint",
                    "count": {"$sum": 1},
                    "ids": {"$push": "$_id"}
                }},
                {"$match": {"count": {"$gt": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": limit},
            ]))
            return {
                "collection": collection_name,
                "total_duplicate_groups": len(duplicates),
                "total_duplicate_docs": sum(d["count"] - 1 for d in duplicates),
                "duplicates": [
                    {
                        "fingerprint": d["_id"],
                        "count": d["count"],
                        "excess_copies": d["count"] - 1,
                    }
                    for d in duplicates
                ],
            }
        except Exception as e:
            if self.verbose:
                print(f"⚠ Duplicate fingerprints in {collection_name} failed: {e}", file=sys.stderr)
            return {"collection": collection_name, "total_duplicate_groups": 0, "error": str(e)}

    def get_tier_distribution(self, collection_name: str = "articles") -> Dict[str, Any]:
        """Get distribution of articles by relevance tier."""
        try:
            collection = self.db[collection_name]
            pipeline = [
                {"$group": {
                    "_id": "$relevance_tier",
                    "count": {"$sum": 1},
                    "data_size": {"$sum": {"$bsonSize": "$$ROOT"}}
                }},
                {"$sort": {"_id": 1}},
            ]
            tiers = list(collection.aggregate(pipeline))
            return {
                "collection": collection_name,
                "tiers": [
                    {
                        "tier": t["_id"] or "unknown",
                        "count": t["count"],
                        "data_size_bytes": t.get("data_size", 0),
                    }
                    for t in tiers
                ],
            }
        except Exception as e:
            if self.verbose:
                print(f"⚠ Tier distribution in {collection_name} failed: {e}", file=sys.stderr)
            return {"collection": collection_name, "tiers": [], "error": str(e)}

    def print_summary_report(self, show_indexes: bool = False, show_age: bool = False) -> None:
        """Print formatted summary report."""
        print("\n" + "=" * 80)
        print(f"MongoDB Storage Audit Report")
        print(f"Database: {self.database_name}")
        print(f"Generated: {datetime.utcnow().isoformat()}Z")
        print("=" * 80 + "\n")

        # Database-level stats
        db_stats = self.get_db_stats()
        if db_stats:
            print("📊 DATABASE STORAGE SUMMARY")
            print(f"  Collections: {db_stats.get('collections', 'unknown')}")
            print(f"  Data size: {self._format_bytes(db_stats.get('data_size_bytes', 0))}")
            print(f"  Storage size: {self._format_bytes(db_stats.get('storage_size_bytes', 0))}")
            print(f"  Total index size: {self._format_bytes(db_stats.get('indexes_size_bytes', 0))}")
            print()

        # Collection stats
        print("📦 COLLECTION BREAKDOWN")
        collections = sorted(self.db.list_collection_names())
        for coll_name in collections:
            stats = self.get_collection_stats(coll_name)
            if stats:
                print(f"\n  {coll_name}:")
                print(f"    Documents: {stats['document_count']:,}")
                print(f"    Data size: {self._format_bytes(stats['data_size_bytes'])}")
                print(f"    Storage size: {self._format_bytes(stats['storage_size_bytes'])}")
                if stats['total_index_size_bytes'] > 0:
                    print(f"    Index size: {self._format_bytes(stats['total_index_size_bytes'])} ({stats['indexes_count']} indexes)")

        # Index details
        if show_indexes:
            print("\n" + "=" * 80)
            print("📇 INDEX DETAILS")
            for coll_name in collections:
                indexes = self.get_index_details(coll_name)
                if indexes:
                    print(f"\n  {coll_name}:")
                    for idx in indexes:
                        ttl_info = f" (TTL: {idx['ttl']}s)" if idx['ttl'] else ""
                        print(f"    • {idx['name']}{ttl_info}")
                        print(f"      Keys: {idx['keys']}")
                        print(f"      Size: {self._format_bytes(idx['size_bytes'])}, Accesses: {idx['accesses']:,}")

        # Age distribution (for key collections)
        if show_age:
            print("\n" + "=" * 80)
            print("📅 DOCUMENT AGE DISTRIBUTION (Sample Collections)")
            age_collections = ["articles", "llm_traces", "llm_cache", "daily_briefings", "narratives"]
            for coll_name in age_collections:
                if coll_name in self.db.list_collection_names():
                    age_info = self.get_age_distribution(coll_name)
                    if "age_distribution" in age_info:
                        print(f"\n  {coll_name}:")
                        print(f"    Total: {age_info['total_documents']:,} documents")
                        print(f"    Range: {age_info['oldest_document_age']} to {age_info['newest_document_age']} days old")
                        for label, count in age_info["age_distribution"].items():
                            pct = (count / age_info["total_documents"] * 100) if age_info["total_documents"] > 0 else 0
                            print(f"      {label:12} {count:6,} docs ({pct:5.1f}%)")

        # TTL index status
        print("\n" + "=" * 80)
        print("⏰ TTL INDEX STATUS")
        ttl_collections = ["llm_traces", "llm_cache"]
        for coll_name in ttl_collections:
            if coll_name in self.db.list_collection_names():
                ttl_status = self.check_ttl_index(coll_name)
                if ttl_status["has_ttl"]:
                    print(f"  ✓ {coll_name}: TTL configured")
                    for ttl_idx in ttl_status["ttl_indexes"]:
                        print(f"      Index: {ttl_idx['name']} ({ttl_idx['ttl_seconds']}s)")
                else:
                    print(f"  ⚠ {coll_name}: NO TTL INDEX")

        # Duplicates summary
        print("\n" + "=" * 80)
        print("🔄 DUPLICATE DETECTION (Articles)")
        dup_info = self.get_duplicate_fingerprints()
        print(f"  Duplicate fingerprint groups: {dup_info['total_duplicate_groups']}")
        print(f"  Total excess copies: {dup_info['total_duplicate_docs']}")
        if dup_info['total_duplicate_groups'] > 0:
            print(f"  Top duplicates (showing up to 10):")
            for dup in dup_info["duplicates"][:10]:
                print(f"    • {dup['excess_copies']} excess copies for fingerprint {dup['fingerprint'][:16]}...")

        # Tier distribution
        print("\n" + "=" * 80)
        print("📊 ARTICLE TIER DISTRIBUTION")
        tier_info = self.get_tier_distribution()
        for tier in tier_info["tiers"]:
            print(f"  {tier['tier']:15} {tier['count']:6,} articles ({self._format_bytes(tier['data_size_bytes'])})")

        print("\n" + "=" * 80 + "\n")

    @staticmethod
    def _format_bytes(num_bytes: int) -> str:
        """Format bytes as human-readable string."""
        for unit in ["B", "KB", "MB", "GB"]:
            if abs(num_bytes) < 1024:
                return f"{num_bytes:.1f} {unit}"
            num_bytes /= 1024
        return f"{num_bytes:.1f} TB"


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="MongoDB storage audit tool (read-only diagnostic)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic audit
  python scripts/mongodb_storage_audit.py --database crypto_news

  # Full audit with indexes and age distribution
  python scripts/mongodb_storage_audit.py --database crypto_news --show-indexes --show-age

  # Verbose output
  python scripts/mongodb_storage_audit.py --database crypto_news -v
        """
    )

    parser.add_argument(
        "--database",
        default="crypto_news",
        help="Target MongoDB database (default: crypto_news)"
    )
    parser.add_argument(
        "--uri",
        help="MongoDB connection URI (reads from MONGODB_URI env var if not provided)"
    )
    parser.add_argument(
        "--show-indexes",
        action="store_true",
        help="Include detailed index metadata and access statistics"
    )
    parser.add_argument(
        "--show-age",
        action="store_true",
        help="Include document age distribution for key collections"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    try:
        audit = MongoStorageAudit(
            mongodb_uri=args.uri,
            database_name=args.database,
            verbose=args.verbose
        )
        audit.connect()
        try:
            audit.print_summary_report(
                show_indexes=args.show_indexes,
                show_age=args.show_age
            )
        finally:
            audit.close()
    except ConfigurationError as e:
        print(f"❌ Configuration error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
