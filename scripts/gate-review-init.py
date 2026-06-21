#!/usr/bin/env python3
"""
Phase A Exit Gate Review - Database Initialization Script

This script sets up the isolated MongoDB instance for Phase A Exit Gate validation
(TASK-114C historical replay, TASK-114D synthetic injection, TASK-114E scorecard).

Usage:
    1. Start the isolated MongoDB instance:
       docker compose -f docker-compose.gate-review.yml up -d

    2. Run this script:
       poetry run python scripts/gate-review-init.py

    3. The script will:
       - Verify MongoDB connection
       - Create required collections (bug_cases, evidence_packs)
       - Create required indexes
       - Report success or fail with diagnostic output

    4. Run gate review tests (TASK-114C, TASK-114D, TASK-114E)

    5. Tear down after review:
       docker compose -f docker-compose.gate-review.yml down -v
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add src to path so we can import from the project
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from pymongo import MongoClient, IndexModel, ASCENDING, DESCENDING
from pymongo.errors import ServerSelectionTimeoutError, OperationFailure

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)


def verify_gate_review_environment():
    """Verify that we're using the gate-review environment, not production."""
    env_file = project_root / ".env.gate-review"

    if not env_file.exists():
        logger.error(f"❌ {env_file} not found. Run this script after docker-compose up.")
        return False

    # Check that MONGODB_URI points to local instance
    with open(env_file) as f:
        content = f.read()
        if "localhost:27018" not in content:
            logger.error("❌ .env.gate-review does not point to local MongoDB on port 27018")
            return False
        if "bugops_gate_review" not in content:
            logger.error("❌ .env.gate-review database name is not 'bugops_gate_review'")
            return False

    logger.info("✅ Gate review environment verified (local instance, isolated database)")
    return True


def initialize_mongodb():
    """Initialize the isolated MongoDB instance with required collections and indexes."""
    # Load environment from .env.gate-review
    env_file = project_root / ".env.gate-review"
    env_vars = {}
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()

    mongodb_uri = env_vars.get("MONGODB_URI")
    if not mongodb_uri:
        logger.error("❌ MONGODB_URI not found in .env.gate-review")
        return False

    try:
        # Connect to the local MongoDB instance
        logger.info(f"Connecting to MongoDB at {mongodb_uri}...")
        client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)

        # Verify connection
        client.admin.command('ping')
        logger.info("✅ MongoDB connection successful")

        # Get the database name from URI
        db_name = mongodb_uri.rstrip('/').split('/')[-1]
        db = client[db_name]

        logger.info(f"Using database: {db_name}")

        # Create collections and indexes
        _create_bug_cases_collection(db)
        _create_evidence_packs_collection(db)

        logger.info("\n✅ Initialization complete!")
        logger.info("\nDatabase is ready for Phase A Exit Gate validation:")
        logger.info("  - TASK-114C (historical replay)")
        logger.info("  - TASK-114D (synthetic injection)")
        logger.info("  - TASK-114E (scorecard review)")
        logger.info(f"\nDatabase name: {db_name}")
        logger.info(f"MongoDB URI: {mongodb_uri}")
        logger.info("\nTeardown command (after review):")
        logger.info("  docker compose -f docker-compose.gate-review.yml down -v")

        return True

    except ServerSelectionTimeoutError:
        logger.error("❌ Could not connect to MongoDB. Is the container running?")
        logger.error("   Start it with: docker compose -f docker-compose.gate-review.yml up -d")
        return False
    except Exception as e:
        logger.error(f"❌ Initialization failed: {e}")
        return False


def _create_bug_cases_collection(db):
    """Create bug_cases collection with indexes."""
    collection_name = "bug_cases"

    if collection_name in db.list_collection_names():
        logger.info(f"  Collection '{collection_name}' already exists")
        return

    logger.info(f"Creating collection: {collection_name}")
    db.create_collection(collection_name)

    # Define indexes (from mongodb.py BUG_CASES_INDEXES)
    indexes = [
        IndexModel([("dedupe_key", ASCENDING), ("status", ASCENDING)]),
        IndexModel([("status", ASCENDING), ("created_at", DESCENDING)]),
        IndexModel([("root_subsystem", ASCENDING), ("status", ASCENDING)]),
        IndexModel([("first_seen_at", ASCENDING)]),
    ]

    collection = db[collection_name]
    collection.create_indexes(indexes)
    logger.info(f"  ✅ Created {len(indexes)} indexes on '{collection_name}'")


def _create_evidence_packs_collection(db):
    """Create evidence_packs collection with indexes."""
    collection_name = "evidence_packs"

    if collection_name in db.list_collection_names():
        logger.info(f"  Collection '{collection_name}' already exists")
        return

    logger.info(f"Creating collection: {collection_name}")
    db.create_collection(collection_name)

    # Define indexes (from mongodb.py EVIDENCE_PACKS_INDEXES)
    indexes = [
        IndexModel([("pack_id", ASCENDING)], unique=True),
        IndexModel([("bugcase_id", ASCENDING)]),
        IndexModel([("collection_status", ASCENDING)]),
        IndexModel([("created_at", DESCENDING)]),
    ]

    collection = db[collection_name]
    collection.create_indexes(indexes)
    logger.info(f"  ✅ Created {len(indexes)} indexes on '{collection_name}'")


def main():
    """Main entry point."""
    logger.info("=" * 70)
    logger.info("Phase A Exit Gate Review — MongoDB Initialization")
    logger.info("=" * 70)

    # Verify we're in the right environment
    if not verify_gate_review_environment():
        sys.exit(1)

    # Initialize MongoDB
    if not initialize_mongodb():
        sys.exit(1)


if __name__ == "__main__":
    main()
