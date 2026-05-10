---
ticket_id: TASK-097
title: Create Lightweight MongoDB Query Skill for Future Verification
priority: low
severity: low
status: COMPLETE
date_created: 2026-05-10
branch: N/A
effort_estimate: 1 hour
---

# TASK-097: Create Lightweight MongoDB Query Skill for Future Verification

## Problem Statement

During BUG-101 post-deploy verification, discovering how to connect to MongoDB and run read-only queries took several attempts. The connection boilerplate (loading .env, importing pymongo, handling credentials) is identical across all verification scenarios.

**Goal:** Create a reusable skill so future MongoDB verification queries don't require connection setup discovery.

---

## Context

- BUG-101 required read-only verification queries (count, find, aggregate)
- Project uses `.env` for MONGODB_URI credentials
- Poetry environment with pymongo already installed
- Queries return JSON for easy parsing/piping
- CLAUDE.md forbids printing secrets, so credentials must load from environment

---

## Task

1. [x] Create `db-query` skill with three commands: count, find, aggregate
2. [x] Implement Python script that auto-loads MONGODB_URI from .env
3. [x] Create reference guide with common query patterns
4. [x] Test with real production queries (count, find, aggregate)
5. [x] Package skill as .skill file
6. [x] Install to `~/.claude/skills/db-query.skill`
7. [x] Document in project memory

---

## Files Created

```text
~/.claude/skills/db-query.skill (packaged skill)
  - SKILL.md
  - scripts/db_query.py
  - references/query_patterns.md
```

---

## Files Modified

```text
~/.claude/projects/.../memory/MEMORY.md
~/.claude/projects/.../memory/db_query_skill.md
```

---

## Do Not Modify

```text
CLAUDE.md (no changes to credential handling policy)
```

---

## Implementation Requirements

- [x] Support three query types: count, find, aggregate
- [x] Auto-load MONGODB_URI from .env (using python-dotenv)
- [x] Return JSON output (compatible with jq, Python json.loads)
- [x] Send errors to stderr (structured JSON)
- [x] Read-only only (no write operations)
- [x] Handle optional parameters: projection, limit, sort
- [x] Exit code 0 on success, 1 on failure

### Commands

```bash
# Count documents
poetry run python3 scripts/db_query.py count <collection> <query>

# Find with optional projection, limit, sort
poetry run python3 scripts/db_query.py find <collection> <query> [projection] [limit] [sort]

# Aggregation pipeline
poetry run python3 scripts/db_query.py aggregate <collection> <pipeline>
```

---

## Verification

### Automated Verification

- [x] Test count: `count narratives '{"lifecycle_state": "hot"}'` → `{"count": 9}` ✅
- [x] Test find: `find articles '{"published": true}' '{"_id": 1}' 10` → Array of 10 articles ✅
- [x] Test aggregate: `aggregate narratives '[{"$group": {"_id": "$lifecycle_state", "count": {"$sum": 1}}}]'` → Grouped results ✅
- [x] Skill packaging: `package_skill.py` validates and creates .skill file ✅
- [x] Skill installation: File present at `~/.claude/skills/db-query.skill` ✅

### Manual Verification

- [x] Run count against production narratives (verified 9 hot narratives)
- [x] Run aggregate against production llm_traces (verified grouped results)
- [x] Verify error handling (tested with invalid query syntax)

---

## Acceptance Criteria

- [x] Three commands work correctly: count, find, aggregate
- [x] Credentials loaded from .env (no hardcoded URIs)
- [x] JSON output compatible with standard tools
- [x] Errors return to stderr with JSON structure
- [x] Exit codes correct (0 success, 1 failure)
- [x] Packaged as reusable .skill file
- [x] Documented in project memory

---

## Impact

**What this solves:**
- No more "how do I connect to MongoDB?" friction in verification tasks
- Reduces boilerplate code in verification scripts
- Read-only guard prevents accidental production mutations
- JSON output enables piping to jq, Python, etc.

**When to use:**
- Post-deployment verification queries
- Production data inspection
- Statistics/metrics gathering
- Ad-hoc queries for investigation

**Future integration:**
- Can be invoked via /db-query skill in future conversations
- Skill file distributable to team (currently at ~/.claude/skills/)

---

## Related Tickets

- BUG-101: Zero Trusted Narratives at Sprint 019 Deployment

---

## Completion Summary

**Status:** ✅ COMPLETE

- **Branch:** N/A (skill creation, not code changes)
- **Commits:** N/A
- **Created:** 
  - Skill: `db-query.skill` (3.8 KB)
  - Script: `scripts/db_query.py` (3.9 KB, 100+ lines)
  - Reference: `references/query_patterns.md` (2.6 KB, 10+ patterns)
  - Memory: `db_query_skill.md` (MEMORY.md updated)

- **Testing Done:**
  - Count query: 9 hot narratives ✅
  - Aggregate query: Grouped by lifecycle_state ✅
  - Projection/limit/sort: Tested with real data ✅

- **Manual Verification:**
  - Skill package created and validated ✅
  - Installed to ~/.claude/skills/ ✅
  - All three commands execute successfully ✅

- **Deviations:** None. Completed as planned.

---

## Usage Reference

Quick commands for future use:

```bash
# Count trusted narratives (Sprint 019 verification)
poetry run python3 scripts/db_query.py count narratives \
  '{"lifecycle_state": {"$in": ["hot", "emerging", "rising", "reactivated"]}, "$or": [{"first_seen": {"$gte": "2026-05-10T00:00:00Z"}}, {"last_summary_generated_at": {"$gte": "2026-05-10T00:00:00Z"}}]}'

# Count backlog
poetry run python3 scripts/db_query.py count narratives '{"needs_summary_update": true}'

# Find recent articles
poetry run python3 scripts/db_query.py find articles \
  '{"created_at": {"$gte": "2026-05-03T00:00:00Z"}}' \
  '{"_id": 1, "title": 1, "created_at": 1}' 10 '{"created_at": -1}'
```

Full reference: See `references/query_patterns.md` in the skill.
