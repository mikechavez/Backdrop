#!/usr/bin/env python3
"""
Analyze LLM traces from 48-hour burn-in period.
Generates findings doc with cost attribution and Sprint 14 decision.

Usage:
    python scripts/analyze_burn_in.py [start_time_iso] [end_time_iso]

If no times provided, uses last 48 hours.
"""

import sys
import os
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from collections import defaultdict

uri = os.getenv('MONGODB_URI')
if not uri:
    print("ERROR: MONGODB_URI environment variable not set")
    sys.exit(1)

def get_analysis_period(start_str=None, end_str=None):
    """Parse time range or default to last 48 hours"""
    if end_str:
        end_time = datetime.fromisoformat(end_str)
    else:
        end_time = datetime.now(timezone.utc)

    if start_str:
        start_time = datetime.fromisoformat(start_str)
    else:
        start_time = end_time - timedelta(hours=48)

    return start_time, end_time

def analyze_traces(db, start_time, end_time):
    """Query llm_traces for cost analysis"""

    # Cost by operation
    op_pipeline = [
        {"$match": {"timestamp": {"$gte": start_time, "$lte": end_time}}},
        {"$group": {
            "_id": "$operation",
            "total_cost": {"$sum": "$cost"},
            "calls": {"$sum": 1},
            "avg_input_tokens": {"$avg": "$input_tokens"},
            "avg_output_tokens": {"$avg": "$output_tokens"},
            "avg_duration_ms": {"$avg": "$duration_ms"},
            "total_input_tokens": {"$sum": "$input_tokens"},
            "total_output_tokens": {"$sum": "$output_tokens"},
        }},
        {"$sort": {"total_cost": -1}}
    ]

    ops = list(db.llm_traces.aggregate(op_pipeline))

    # Cost by model
    model_pipeline = [
        {"$match": {"timestamp": {"$gte": start_time, "$lte": end_time}}},
        {"$group": {
            "_id": "$model",
            "total_cost": {"$sum": "$cost"},
            "calls": {"$sum": 1},
        }},
        {"$sort": {"total_cost": -1}}
    ]

    models = list(db.llm_traces.aggregate(model_pipeline))

    # Error rate
    error_pipeline = [
        {"$match": {"timestamp": {"$gte": start_time, "$lte": end_time}}},
        {"$group": {
            "_id": "$operation",
            "total": {"$sum": 1},
            "errors": {"$sum": {"$cond": [{"$ne": ["$error", None]}, 1, 0]}},
        }},
        {"$sort": {"errors": -1}}
    ]

    errors = list(db.llm_traces.aggregate(error_pipeline))

    return ops, models, errors

def analyze_refine_loop(db, start_time, end_time):
    """Analyze refine loop behavior from briefing_drafts"""

    pipeline = [
        {"$match": {"timestamp": {"$gte": start_time, "$lte": end_time}}},
        {"$group": {
            "_id": "$briefing_id",
            "stages": {"$push": "$stage"},
            "count": {"$sum": 1},
        }},
    ]

    drafts = list(db.briefing_drafts.aggregate(pipeline))

    # Analyze iteration counts
    iteration_counts = defaultdict(int)
    for draft in drafts:
        stages = draft['stages']
        # Count unique iterations (post_refine_1, post_refine_2, etc.)
        refine_stages = [s for s in stages if s.startswith('post_refine_')]
        iteration_counts[len(refine_stages)] += 1

    return drafts, iteration_counts

def calculate_daily_average(total_cost, start_time, end_time):
    """Calculate average daily spend"""
    duration_hours = (end_time - start_time).total_seconds() / 3600
    daily_rate = (total_cost / duration_hours) * 24 if duration_hours > 0 else 0
    return daily_rate

def main():
    start_str = sys.argv[1] if len(sys.argv) > 1 else None
    end_str = sys.argv[2] if len(sys.argv) > 2 else None

    start_time, end_time = get_analysis_period(start_str, end_str)

    print(f"Analyzing burn-in period: {start_time} to {end_time}")
    print(f"Duration: {(end_time - start_time).total_seconds() / 3600:.1f} hours\n")

    try:
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        db = client.crypto_news
        db.command('ping')

        # Get analysis data
        ops, models, errors = analyze_traces(db, start_time, end_time)
        drafts, iteration_counts = analyze_refine_loop(db, start_time, end_time)

        # Calculate totals
        total_cost = sum(op['total_cost'] for op in ops)
        total_calls = sum(op['calls'] for op in ops)
        daily_avg = calculate_daily_average(total_cost, start_time, end_time)

        print("=" * 60)
        print("BURN-IN ANALYSIS SUMMARY")
        print("=" * 60)
        print(f"Total Cost: ${total_cost:.4f}")
        print(f"Daily Average: ${daily_avg:.4f} (target: $0.33)")
        print(f"Total API Calls: {total_calls}")
        print(f"Briefings Generated: {len(drafts)}")
        print()

        # Cost by operation
        print("Cost by Operation:")
        print("-" * 60)
        print(f"{'Operation':<30} {'Calls':<8} {'Cost':<12} {'Pct':<6}")
        print("-" * 60)
        for op in ops:
            pct = (op['total_cost'] / total_cost * 100) if total_cost > 0 else 0
            print(f"{op['_id']:<30} {op['calls']:<8} ${op['total_cost']:<11.6f} {pct:<5.1f}%")
        print()

        # Cost by model
        print("Cost by Model:")
        print("-" * 60)
        for model in models:
            pct = (model['total_cost'] / total_cost * 100) if total_cost > 0 else 0
            print(f"{model['_id']:<40} {model['calls']:<8} ${model['total_cost']:<11.6f} {pct:<5.1f}%")
        print()

        # Refine loop analysis
        print("Refine Loop Behavior:")
        print("-" * 60)
        print(f"Briefings generated: {len(drafts)}")
        if iteration_counts:
            for iterations in sorted(iteration_counts.keys()):
                count = iteration_counts[iterations]
                pct = (count / len(drafts) * 100) if drafts else 0
                print(f"  {iterations} iterations: {count} briefings ({pct:.1f}%)")
        print()

        # Error analysis
        print("Error Rate:")
        print("-" * 60)
        for err in errors:
            if err['total'] > 0:
                error_rate = (err['errors'] / err['total'] * 100)
                print(f"{err['_id']:<30} {err['errors']}/{err['total']} ({error_rate:.1f}%)")
        print()

        # Decision
        print("=" * 60)
        print("SPRINT 14 DECISION")
        print("=" * 60)
        if daily_avg <= 0.33:
            status = "✅ WITHIN TARGET"
            decision = "Gateway + spend cap is working. Continue monitoring. Consider:"
        else:
            status = f"⚠️  EXCEEDS TARGET (${daily_avg:.4f} vs $0.33)"
            decision = "Need optimization. Prioritize:"

        print(f"Status: {status}")
        print()
        print(f"{decision}")

        # Find top cost driver
        if ops:
            top_op = ops[0]
            top_pct = (top_op['total_cost'] / total_cost * 100)
            print(f"  1. Reduce {top_op['_id']} ({top_pct:.1f}% of cost)")
            if len(ops) > 1:
                second_op = ops[1]
                second_pct = (second_op['total_cost'] / total_cost * 100)
                print(f"  2. Reduce {second_op['_id']} ({second_pct:.1f}% of cost)")

        print()
        print("Data saved. Next: Write findings doc with detailed analysis.")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
