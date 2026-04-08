# TASK-028: Burn-in Validation (72hr) -- Implementation Plan

**Branch:** `feature/task-028-burn-in`
**Estimated:** 1 hour setup, then 72 hours passive monitoring
**Dependencies:** TASK-027 (health endpoint must be deployed first)

---

## Overview

Validate that Backdrop runs 72 hours without intervention after TASK-025 (cost controls), TASK-026 (error handling), and TASK-027 (health check) are deployed. This is not a code-heavy task -- it is a monitoring setup + pass/fail criteria definition + post-burn-in evidence collection.

---

## File Changes Summary

| Action | File | Description |
|--------|------|-------------|
| CREATE | `scripts/burn_in_check.py` | Script to poll /health and log results |
| CREATE | `docs/_generated/evidence/14-burn-in-validation.md` | Evidence doc (created post-burn-in) |

---

## Step 1: Create the Burn-in Monitoring Script

**File:** `scripts/burn_in_check.py`

This script polls the health endpoint every 15 minutes, logs results to a CSV, and flags any non-healthy states. Mike runs it locally or on any machine with network access to the deployed app.

```python
#!/usr/bin/env python3
"""
Burn-in validation script for TASK-028.

Polls the /health endpoint every 15 minutes and logs results to CSV.
Run with: python scripts/burn_in_check.py --url https://your-app.railway.app/api/v1/health
"""

import argparse
import csv
import os
import sys
import time
from datetime import datetime, timezone

import requests


DEFAULT_INTERVAL = 900  # 15 minutes
DEFAULT_DURATION = 72 * 3600  # 72 hours
LOG_FILE = "burn_in_results.csv"


def check_health(url: str) -> dict:
    """Poll the health endpoint and return structured result."""
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "http_status": response.status_code,
            "overall_status": data.get("status", "unknown"),
            "database": data.get("checks", {}).get("database", {}).get("status", "unknown"),
            "redis": data.get("checks", {}).get("redis", {}).get("status", "unknown"),
            "llm": data.get("checks", {}).get("llm", {}).get("status", "unknown"),
            "data_freshness": data.get("checks", {}).get("data_freshness", {}).get("status", "unknown"),
            "error": "",
        }
    except requests.RequestException as e:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "http_status": 0,
            "overall_status": "unreachable",
            "database": "unknown",
            "redis": "unknown",
            "llm": "unknown",
            "data_freshness": "unknown",
            "error": str(e)[:200],
        }


def run_burn_in(url: str, interval: int, duration: int, log_file: str):
    """Run the burn-in monitoring loop."""
    print(f"Starting burn-in validation")
    print(f"  URL:      {url}")
    print(f"  Interval: {interval}s ({interval // 60}min)")
    print(f"  Duration: {duration}s ({duration // 3600}hr)")
    print(f"  Log file: {log_file}")
    print()

    fieldnames = [
        "timestamp", "http_status", "overall_status",
        "database", "redis", "llm", "data_freshness", "error",
    ]

    file_exists = os.path.exists(log_file)
    start_time = time.monotonic()
    check_count = 0
    fail_count = 0

    with open(log_file, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        while (time.monotonic() - start_time) < duration:
            result = check_health(url)
            writer.writerow(result)
            f.flush()  # Write immediately so we don't lose data on crash
            check_count += 1

            status = result["overall_status"]
            marker = "OK" if status == "healthy" else "WARN" if status == "degraded" else "FAIL"
            if status != "healthy":
                fail_count += 1

            elapsed_hr = (time.monotonic() - start_time) / 3600
            print(
                f"[{result['timestamp']}] {marker} | "
                f"status={status} | "
                f"db={result['database']} redis={result['redis']} "
                f"llm={result['llm']} fresh={result['data_freshness']} | "
                f"check #{check_count} | {elapsed_hr:.1f}hr elapsed"
            )

            time.sleep(interval)

    print()
    print(f"Burn-in complete: {check_count} checks, {fail_count} failures")
    print(f"Results saved to: {log_file}")

    if fail_count == 0:
        print("RESULT: PASS")
        return 0
    else:
        print(f"RESULT: FAIL ({fail_count} non-healthy checks)")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Burn-in validation for Backdrop")
    parser.add_argument(
        "--url",
        required=True,
        help="Full URL to health endpoint (e.g., https://your-app.railway.app/api/v1/health)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL,
        help=f"Seconds between checks (default: {DEFAULT_INTERVAL})",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION,
        help=f"Total seconds to run (default: {DEFAULT_DURATION} = 72hr)",
    )
    parser.add_argument(
        "--log-file",
        default=LOG_FILE,
        help=f"CSV output file (default: {LOG_FILE})",
    )
    args = parser.parse_args()

    sys.exit(run_burn_in(args.url, args.interval, args.duration, args.log_file))


if __name__ == "__main__":
    main()
```

**Notes for CC:**
- Pure stdlib + requests (no project imports, runs standalone)
- Appends to CSV so you can restart without losing data
- Returns exit code 0 (pass) or 1 (fail) for CI integration
- Default: 72 hours, poll every 15 minutes = ~288 checks

---

## Step 2: Define Pass/Fail Criteria

These go in the ticket as acceptance criteria. CC does not implement these -- Mike evaluates after 72 hours.

**PASS if all of the following are true after 72 hours:**
1. Zero `unreachable` results in the CSV (app never went completely down)
2. Zero `unhealthy` results (no critical system failures)
3. `degraded` count is < 5% of total checks (occasional non-critical blips are OK)
4. No manual intervention was required during the 72 hours
5. LLM daily spend stayed within budget (check cost tracker)

**FAIL if any of the following:**
1. App became unreachable for > 30 minutes
2. Any `unhealthy` result (database or LLM down)
3. `degraded` count > 5% of checks
4. Manual restart or fix was required

---

## Step 3: Evidence Document Template

**File:** `docs/_generated/evidence/14-burn-in-validation.md`

CC creates this file with the template below. Mike fills in results after the 72-hour period.

```markdown
# Evidence: Burn-in Validation (TASK-028)

**Date started:**
**Date completed:**
**Duration:** 72 hours
**Environment:** Railway (production)

---

## Health Check Summary

| Metric | Value |
|--------|-------|
| Total checks | |
| Healthy | |
| Degraded | |
| Unhealthy | |
| Unreachable | |
| Pass rate | |

## Cost During Burn-in

| Metric | Value |
|--------|-------|
| Total LLM spend (72hr) | |
| Average daily spend | |
| Health check LLM cost | |
| Within budget? | |

## Incidents

_List any non-healthy checks and what caused them. If none, write "None."_

## Result

**PASS / FAIL**

_Rationale:_

---

## Raw Data

CSV attached: `burn_in_results.csv`
```

---

## Step 4: How to Run

After TASK-027 is deployed to Railway:

```bash
# Start the 72-hour burn-in
python scripts/burn_in_check.py \
  --url https://your-app.railway.app/api/v1/health \
  --log-file burn_in_results.csv

# For a quick 1-hour test first:
python scripts/burn_in_check.py \
  --url https://your-app.railway.app/api/v1/health \
  --interval 60 \
  --duration 3600 \
  --log-file burn_in_test.csv
```

---

## Verification Checklist (for CC)

```bash
# Verify script runs (quick 2-check test against any URL)
python scripts/burn_in_check.py \
  --url https://httpbin.org/json \
  --interval 5 \
  --duration 12 \
  --log-file /tmp/test_burn_in.csv

# Verify CSV was created with expected columns
head -1 /tmp/test_burn_in.csv
# Expected: timestamp,http_status,overall_status,database,redis,llm,data_freshness,error

# Verify evidence template exists
cat docs/_generated/evidence/14-burn-in-validation.md
```

---

## Commit Message

```
feat(ops): Add burn-in validation script and evidence template (TASK-028)

- Polling script: checks /health every 15min for 72hr, logs to CSV
- Pass/fail criteria defined in evidence template
- Standalone script (no project imports) -- runs anywhere with requests
```