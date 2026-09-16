#!/usr/bin/env python3
"""
BUG-110: read-only duplicate-remediation audit CLI for entity_mentions.

Default mode is a report-only, read-only dry run. Nothing in the default
invocation writes to the database.

Usage:

    # Full report: group sizes, excess documents, created_at ranges,
    # size-distribution histogram, bounded samples.
    poetry run python scripts/entity_mentions_duplicate_audit.py report

    # Field-level comparison of documents inside one specific group
    # (identify whether "duplicates" are identical or actually differ).
    poetry run python scripts/entity_mentions_duplicate_audit.py compare \\
        --article-id 69cebfd8aa731a71682e7d33 --entity Bitcoin \\
        --entity-type cryptocurrency --is-primary true

    # Build (but do not apply) a canonical-record cleanup plan for the
    # smallest N duplicate groups; writes the plan as JSON for review.
    poetry run python scripts/entity_mentions_duplicate_audit.py plan \\
        --max-groups 50 --out /tmp/cleanup_plan.json

    # Apply an approved plan. Requires --confirm with the exact phrase and
    # --execute to actually delete (otherwise this only re-previews the
    # plan's effect). Never run this against production without explicit
    # operator sign-off per BUG-110.
    poetry run python scripts/entity_mentions_duplicate_audit.py cleanup \\
        --plan /tmp/cleanup_plan.json \\
        --confirm "DELETE DUPLICATE ENTITY MENTIONS" \\
        --batch-size 25 \\
        [--execute]

This tool never creates the article_entity_type_primary_unique index and
never should be extended to. Index creation is a separate, explicitly
operator-gated step in db/operations/entity_mentions_index_rollout.py and
must only run after this tool's report shows duplicate_groups == 0 (i.e.
approved cleanup, if any, is complete).
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.crypto_news_aggregator.db.mongodb import mongo_manager  # noqa: E402
from src.crypto_news_aggregator.db.operations.entity_mentions_duplicate_audit import (  # noqa: E402
    CLEANUP_CONFIRMATION_PHRASE,
    CleanupPlan,
    CanonicalChoice,
    compare_group_documents,
    execute_cleanup_plan,
    plan_duplicate_cleanup,
    run_duplicate_audit,
)


def _json_default(o):
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


async def cmd_report(args) -> None:
    db = await mongo_manager.get_async_database()
    report = await run_duplicate_audit(
        db.entity_mentions,
        sample_limit=args.sample_limit,
        max_groups_scanned=args.max_groups_scanned,
    )

    print("=" * 80)
    print("ENTITY_MENTIONS DUPLICATE AUDIT (read-only)")
    print("=" * 80)
    print(f"duplicate_groups:                {report.duplicate_groups}")
    print(f"total_documents_in_dup_groups:    {report.total_documents_in_duplicate_groups}")
    print(f"excess_documents:                 {report.excess_documents}")
    print(f"max_group_size:                   {report.max_group_size}")
    print(f"max_group_key:                    {report.max_group_key}")
    print(f"created_at range:                 {report.created_at_min} .. {report.created_at_max}")
    print()
    print("Group size distribution:")
    for bucket in report.size_distribution:
        print(f"  {bucket.label:>10}: groups={bucket.group_count:>6}  documents={bucket.document_count:>8}")
    print()
    print(f"Sample groups (up to {args.sample_limit}):")
    for s in report.sample_groups:
        print(f"  count={s['count']:>6}  key={s['key']}  created_at={s['created_at_min']}..{s['created_at_max']}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(asdict(report), f, default=_json_default, indent=2)
        print(f"\nFull report written to {args.out}")


async def cmd_compare(args) -> None:
    db = await mongo_manager.get_async_database()
    key = {
        "article_id": args.article_id,
        "entity": args.entity,
        "entity_type": args.entity_type,
        "is_primary": args.is_primary,
    }
    comparison = await compare_group_documents(db.entity_mentions, key)

    print("=" * 80)
    print("GROUP COMPARISON (read-only)")
    print("=" * 80)
    print(f"key: {comparison.key}")
    print(f"document_count: {comparison.document_count}")
    print(f"identical: {comparison.identical}")
    print(f"created_at range: {comparison.created_at_min} .. {comparison.created_at_max}")
    if comparison.field_differences:
        print("Field differences:")
        for diff in comparison.field_differences:
            print(f"  {diff.field}: {diff.distinct_values}")
    else:
        print("No field differences found across compared fields.")


async def cmd_plan(args) -> None:
    db = await mongo_manager.get_async_database()
    plan = await plan_duplicate_cleanup(
        db.entity_mentions,
        max_groups=args.max_groups,
        max_group_size_for_auto_plan=args.max_group_size_for_auto_plan,
    )

    print("=" * 80)
    print("CLEANUP PLAN (dry-run, nothing deleted)")
    print("=" * 80)
    print(f"groups_planned: {plan.groups_planned}")
    print(f"documents_to_delete: {len(plan.documents_to_delete)}")
    print(f"skipped_groups (too large for auto-plan): {len(plan.skipped_groups)}")
    for s in plan.skipped_groups:
        print(f"  SKIPPED: {s}")

    if args.out:
        with open(args.out, "w") as f:
            json.dump(asdict(plan), f, default=_json_default, indent=2)
        print(f"\nPlan written to {args.out} -- review before any cleanup run.")


async def cmd_cleanup(args) -> None:
    with open(args.plan) as f:
        raw = json.load(f)

    plan = CleanupPlan(
        groups_planned=raw["groups_planned"],
        documents_to_delete=raw["documents_to_delete"],
        choices=[CanonicalChoice(**c) for c in raw["choices"]],
        skipped_groups=raw.get("skipped_groups", []),
    )

    db = await mongo_manager.get_async_database()
    report = await execute_cleanup_plan(
        db.entity_mentions,
        plan,
        confirm=args.confirm,
        batch_size=args.batch_size,
        dry_run=not args.execute,
    )

    print("=" * 80)
    print(f"CLEANUP {'EXECUTED' if args.execute else 'DRY RUN'}")
    print("=" * 80)
    print(f"batches: {report.batches}")
    print(f"total_deleted: {report.total_deleted}")
    print(f"errors: {len(report.errors)}")
    for e in report.errors:
        print(f"  ERROR: {e}")

    if args.audit_out:
        with open(args.audit_out, "w") as f:
            json.dump(asdict(report), f, default=_json_default, indent=2)
        print(f"\nAudit report written to {args.audit_out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_report = sub.add_parser("report", help="Read-only duplicate audit report")
    p_report.add_argument("--sample-limit", type=int, default=20)
    p_report.add_argument("--max-groups-scanned", type=int, default=None)
    p_report.add_argument("--out", type=str, default=None, help="Write full JSON report to this path")
    p_report.set_defaults(func=cmd_report)

    p_compare = sub.add_parser("compare", help="Compare documents inside one duplicate group")
    p_compare.add_argument("--article-id", required=True)
    p_compare.add_argument("--entity", required=True)
    p_compare.add_argument("--entity-type", required=True)
    p_compare.add_argument("--is-primary", type=lambda s: s.lower() == "true", required=True)
    p_compare.set_defaults(func=cmd_compare)

    p_plan = sub.add_parser("plan", help="Build (do not apply) a canonical-record cleanup plan")
    p_plan.add_argument("--max-groups", type=int, default=100)
    p_plan.add_argument("--max-group-size-for-auto-plan", type=int, default=20000)
    p_plan.add_argument("--out", type=str, default=None, help="Write plan JSON to this path")
    p_plan.set_defaults(func=cmd_plan)

    p_cleanup = sub.add_parser("cleanup", help="Apply an approved cleanup plan (requires --confirm)")
    p_cleanup.add_argument("--plan", required=True, help="Path to a plan JSON produced by `plan --out`")
    p_cleanup.add_argument("--confirm", required=True, help=f"Must be exactly: {CLEANUP_CONFIRMATION_PHRASE!r}")
    p_cleanup.add_argument("--batch-size", type=int, default=25)
    p_cleanup.add_argument("--execute", action="store_true", help="Actually delete. Omit for a dry run.")
    p_cleanup.add_argument("--audit-out", type=str, default=None, help="Write audit report JSON to this path")
    p_cleanup.set_defaults(func=cmd_cleanup)

    args = parser.parse_args()
    asyncio.run(args.func(args))


if __name__ == "__main__":
    main()
