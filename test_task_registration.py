#!/usr/bin/env python3
"""
Verify that all briefing tasks are properly registered with the Celery worker.

Run this locally to check that tasks are discoverable by the Celery worker:
    python test_task_registration.py

This script imports the Celery app and inspects its registered tasks,
verifying that all briefing tasks are available for scheduling and execution.
"""

import sys
from src.crypto_news_aggregator.tasks import app

def check_task_registration():
    """Check if all required tasks are registered."""
    required_tasks = {
        "generate_morning_briefing",
        "generate_evening_briefing",
        "cleanup_old_briefings",
        "consolidate_narratives",
        "warm_cache",
        "send_daily_digest",
        "generate_afternoon_briefing",
        "force_generate_briefing",
    }

    # Get registered tasks from the Celery app
    registered_tasks = set(app.tasks.keys())

    print("=" * 70)
    print("CELERY TASK REGISTRATION CHECK")
    print("=" * 70)
    print()

    # Filter to show only user-defined tasks (exclude celery built-ins)
    user_tasks = {t for t in registered_tasks if not t.startswith("celery.")}

    print(f"Total registered tasks: {len(registered_tasks)}")
    print(f"User-defined tasks: {len(user_tasks)}")
    print()

    print("Required briefing tasks:")
    all_present = True
    for task_name in sorted(required_tasks):
        if task_name in registered_tasks:
            print(f"  ✅ {task_name}")
        else:
            print(f"  ❌ {task_name} - MISSING!")
            all_present = False

    print()
    print("=" * 70)

    if all_present:
        print("SUCCESS: All required briefing tasks are registered!")
        print()
        print("Beat schedule entries that will execute these tasks:")
        for schedule_name, schedule_config in app.conf.beat_schedule.items():
            task_name = schedule_config.get("task")
            if task_name in required_tasks:
                print(f"  • {schedule_name}")
                print(f"    Task: {task_name}")
                print(f"    Schedule: {schedule_config.get('schedule')}")
        return 0
    else:
        print("FAILURE: Some required tasks are not registered!")
        print()
        print("All registered user-defined tasks:")
        for task_name in sorted(user_tasks):
            print(f"  • {task_name}")
        return 1

if __name__ == "__main__":
    sys.exit(check_task_registration())
