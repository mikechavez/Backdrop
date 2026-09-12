#!/usr/bin/env python
"""Preview or explicitly execute one bounded MongoDB retention batch."""

import argparse
import asyncio
import json

from motor.motor_asyncio import AsyncIOMotorClient

from crypto_news_aggregator.core.config import get_settings
from crypto_news_aggregator.services.mongodb_retention import run_retention_cleanup


async def run(database_name: str, execute: bool) -> dict:
    settings = get_settings()
    if database_name != settings.MONGODB_NAME:
        raise ValueError(
            f"Refusing database mismatch: requested {database_name!r}, "
            f"configured MONGODB_NAME is {settings.MONGODB_NAME!r}"
        )
    client = AsyncIOMotorClient(settings.MONGODB_URI, serverSelectionTimeoutMS=10000)
    try:
        await client.admin.command("ping")
        return await run_retention_cleanup(
            client[database_name], settings, dry_run=not execute
        )
    finally:
        client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="crypto_news")
    parser.add_argument("--execute", action="store_true", help="Delete one bounded batch per enabled collection")
    parser.add_argument("--confirm", action="store_true", help="Required with --execute")
    args = parser.parse_args()
    if args.execute and not args.confirm:
        parser.error("--execute requires explicit --confirm")
    result = asyncio.run(run(args.database, execute=args.execute))
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
