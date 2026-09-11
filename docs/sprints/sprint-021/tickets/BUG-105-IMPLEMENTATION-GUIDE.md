# BUG-105 Implementation Guide: MongoDB Storage Quota Recovery

**Status:** In Progress  
**Script Created:** 2026-09-10  
**Next Phase:** Local testing and validation

---

## Quick Reference

**Audit Script Location:**  
`scripts/mongodb_storage_audit.py`

**Basic Usage:**
```bash
# Test locally
poetry run python scripts/mongodb_storage_audit.py --database crypto_news

# Full diagnostic (indexes + age distribution)
poetry run python scripts/mongodb_storage_audit.py --database crypto_news --show-indexes --show-age

# Against production (requires MONGODB_URI environment variable set)
poetry run python scripts/mongodb_storage_audit.py --database crypto_news --show-age -v
```

---

## Audit Script Features

The script provides **read-only diagnostic capability** with no destructive commands. It produces a comprehensive inventory of:

### Database-Level Statistics
- Total collections
- Data size
- Storage size
- Total index size

### Per-Collection Breakdown
- Document count
- Data size
- Storage size
- Index count and sizes
- Index access statistics

### Index Metadata
- Index name, key pattern, and size
- TTL status (critical for `llm_traces`)
- Access frequency (helps identify unused indexes)

### Document Age Distribution
- Age buckets: <1d, 1-7d, 7-30d, 30-90d, >90d
- Oldest/newest timestamps
- Identifies retention candidates

### Data Quality Checks
- Duplicate fingerprints in `articles` (candidates for cleanup)
- Article distribution by relevance tier (Tier 1/2/3)
- TTL index validation for `llm_traces` and `llm_cache`

---

## Production Recovery Workflow

### Phase 1: Read-Only Inventory (LOCAL FIRST)

**1. Test the script locally** (if local MongoDB is available):
```bash
# This should succeed without errors, even against empty DB
poetry run python scripts/mongodb_storage_audit.py --database crypto_news
```

**2. Against production** (with credentials):
```bash
# Requires MONGODB_URI set in shell environment
source scripts/load_keys.sh  # or equivalent
poetry run python scripts/mongodb_storage_audit.py --database crypto_news --show-indexes --show-age -v > /tmp/audit_baseline.txt
```

**3. Review the baseline**:
- Note total storage size and percent of 512 MB quota used
- Identify largest collections (by data and index size)
- Identify collections with old documents (>90 days)
- Check TTL index status on `llm_traces` and `llm_cache`
- Record the count of duplicate fingerprints

---

### Phase 2: Cleanup Planning (REQUIRES APPROVAL)

**Decision Points** (must be explicitly recorded before any deletions):

1. **llm_cache retention**
   - All `llm_cache` is disposable; older entries safely deleted
   - Typical threshold: delete all entries >7 days old
   - Expected recovery: 5-50 MB (depends on workload)

2. **llm_traces retention**
   - Operational/audit data; retention cutoff must be documented
   - TTL should expire entries, but may need manual cleanup for expired docs
   - Recommended cutoff: 30 days (preserve incident history)
   - Expected recovery: 10-100 MB

3. **Duplicate articles**
   - By fingerprint; keep most recent, delete duplicates
   - Review count and which articles are duplicated
   - Expected recovery: 1-10 MB (varies by duplicate rate)

4. **Old Tier 3 articles**
   - Only delete with explicit approval
   - Recommend cutoff: >60 days old
   - Expected recovery: 50-200 MB (varies by growth rate)

5. **Recent Tier 1/2 articles**
   - **DO NOT delete** without explicit approval
   - These represent valuable freshly ingested content

---

### Phase 3: Staged Cleanup (TO BE IMPLEMENTED)

**Next ticket** (`TASK-128`) implements the cleanup operations. Here's the sequence:

```python
# Pseudocode for cleanup logic (implementation in TASK-128):

# 1. Export/record deletion candidates
deletion_plan = {
    "llm_cache": {"older_than_days": 7, "estimated_docs": count, "estimated_bytes": size},
    "llm_traces": {"older_than_days": 30, "estimated_docs": count, "estimated_bytes": size},
    "duplicate_articles": {"fingerprints": [...], "estimated_docs": count},
}

# 2. Execute deletions in batches
for batch in batches_of_1000_docs:
    # Delete with confirmation and logging
    result = collection.delete_many(filter, delete_confirmed=True)
    # Record: count, bytes affected, new storage size
    # Stop if any unexpected behavior

# 3. Verify headroom exists
new_size = audit_storage()
headroom_mb = (512 - new_size) / 1024
assert headroom_mb > 50, f"Insufficient headroom: {headroom_mb} MB remaining"
```

---

## Local Testing Checklist

- [ ] Script creates successfully at `scripts/mongodb_storage_audit.py`
- [ ] `poetry run python scripts/mongodb_storage_audit.py --help` works
- [ ] Script runs against local MongoDB (if available) without errors
- [ ] Output includes all sections: database summary, collections, TTL status, duplicates
- [ ] Script correctly redacts credentials from output
- [ ] No credentials appear in logs or output (only redacted URI)
- [ ] Script handles missing MONGODB_URI gracefully (clear error message)

---

## Safety Rails

**Embedded in the script:**

1. **Read-only by default** — no delete/drop operations
2. **Credential redaction** — all output is safe to paste into tickets
3. **Connection validation** — fails fast with clear error if DB unreachable
4. **Error handling** — continues reporting even if one collection has issues
5. **No embedded secrets** — reads from environment only

**Before production cleanup (TASK-128):**

1. Explicit approval for each retention cutoff
2. Export/record deletion candidates with document counts
3. Confirmation flags on all delete operations
4. Per-batch logging: count, bytes, new storage size
5. Rollback plan documented before execution
6. Production restart and verification steps

---

## Expected Production Sequence

1. **Now (BUG-105 current phase):** Audit script ready for production use
2. **Immediate next step:** Run read-only audit against production
3. **After baseline reviewed:** Approve retention cutoffs via comment
4. **TASK-128:** Implement cleanup operations and production restart
5. **Post-TASK-128:** Monitor quota and implement TTL maintenance

---

## Files Modified / Created

- ✅ `scripts/mongodb_storage_audit.py` — read-only diagnostic tool
- 📝 `docs/sprints/sprint-021/tickets/BUG-105-IMPLEMENTATION-GUIDE.md` — this file
- 📋 `docs/sprints/sprint-021/tickets/BUG-105-mongodb-storage-quota-recovery.md` — original ticket (needs evidence update)

---

## Next Actions

1. **Validate script locally** (if test MongoDB available)
2. **Run against production** with `--show-indexes --show-age` flags
3. **Document baseline** in BUG-105 ticket evidence section
4. **Approve retention cutoffs** based on age distribution and business requirements
5. **Hand off to TASK-128** for cleanup implementation and production recovery

---

## Troubleshooting

**Script fails to connect:**
```
❌ Configuration error: MONGODB_URI not provided and not set in environment
```
→ Run `source scripts/load_keys.sh` before executing script

**Permission denied on a collection:**
```
⚠ collStats(collection_name) failed: not authorized
```
→ Connection string uses read-only credentials; this is expected for audit phase

**No output from TTL index check:**
```
⚠ TTL INDEX STATUS
  ⚠ llm_traces: NO TTL INDEX
```
→ Critical: TTL must be added as part of TASK-128 prevention

**Memory or timeout errors:**
→ Script uses aggregation pipeline (`$indexStats`, age distribution) which can be resource-intensive on large collections. Consider running against production during low-traffic hours.

---

## Related Tickets

- **BUG-105** (this ticket) — Storage quota recovery and incident documentation
- **TASK-128** — Prevention: MongoDB retention monitoring, startup hardening, TTL index enforcement
- **TASK-114B** — Provisioned isolated local MongoDB for BugOps testing
