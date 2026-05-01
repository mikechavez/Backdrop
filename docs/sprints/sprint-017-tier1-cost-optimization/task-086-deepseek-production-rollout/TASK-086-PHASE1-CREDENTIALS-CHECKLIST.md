---
id: TASK-086-CREDENTIALS
type: checklist
status: ready-for-testing
---

# TASK-086 Phase 1: Live Smoke Test Credentials Checklist

## Status
- ✅ Mocked validation: **PASS** (8/8 tests)
- ✅ Routing mechanism: **VERIFIED**
- ✅ Cost savings: **88.2%** (DeepSeek is 0.12x the cost of Haiku)
- ⏳ Live smoke test: **PENDING CREDENTIALS**

---

## Required Credentials

### 1. ANTHROPIC_API_KEY ✓ REQUIRED
**Purpose:** Baseline enrichment batch call for comparison

| Item | Details |
|------|---------|
| **Type** | API Key (secret) |
| **Where to get** | https://console.anthropic.com/settings/keys |
| **What it's for** | Calling `article_enrichment_batch` through Anthropic |
| **Required for** | Live smoke test baseline call + FEATURE-054 eval baseline |
| **Account state** | Must have available credits (not $0 balance) |
| **How to verify** | Can successfully call `POST /v1/messages` and get response |

**Where to add:**
```bash
# In .env or via environment variable
ANTHROPIC_API_KEY=sk-ant-...
```

---

### 2. DEEPSEEK_API_KEY ✓ REQUIRED
**Purpose:** DeepSeek enrichment batch call for Phase 1 validation

| Item | Details |
|------|---------|
| **Type** | API Key (secret) |
| **Where to get** | https://platform.deepseek.com/api_keys |
| **What it's for** | Calling `article_enrichment_batch` through DeepSeek |
| **Required for** | Live smoke test DeepSeek call |
| **Account state** | Must have available credits (not $0 balance) |
| **How to verify** | Can successfully call `POST /chat/completions` and get response |

**Where to add:**
```bash
# In .env or via environment variable
DEEPSEEK_API_KEY=sk-...
```

---

### 3. MONGODB_URI ✓ REQUIRED
**Purpose:** Verify llm_traces records are written correctly

| Item | Details |
|------|---------|
| **Type** | Connection string |
| **Where to get** | MongoDB Atlas cluster settings or local MongoDB |
| **What it's for** | Writing and reading `llm_traces` collection |
| **Required for** | Verifying traces, cost, and model refs recorded correctly |
| **Database** | `crypto_news` (or the database you're testing against) |
| **How to verify** | Can connect and read `db.llm_traces.find()` |

**Where to add:**
```bash
# In .env or via environment variable
MONGODB_URI=<your-connection-string>
```

See MongoDB Atlas docs for connection string format.

---

## Environment Setup

### Required: Environment Variables Must Be Present

The live smoke test requires these environment variables to be set before execution:
- `ANTHROPIC_API_KEY`
- `DEEPSEEK_API_KEY`
- `MONGODB_URI`

**Critical:** Do not print secret values. Do not inspect `.env` files. Do not commit `.env` files.

### Local Development Setup (macOS)

Use macOS Keychain via `scripts/load_keys.sh`:

```bash
# Add credentials to Keychain (one-time setup)
security add-generic-password -s "ANTHROPIC_API_KEY" -w "sk-ant-..."
security add-generic-password -s "DEEPSEEK_API_KEY" -w "sk-..."
security add-generic-password -s "MONGODB_URI" -w "your-connection-string"

# Load from Keychain (before running smoke tests)
source scripts/load_keys.sh
```

Alternatively, source `.env` if credentials are stored there:
```bash
source .env
```

### Production Setup (Railway)

Do not use local Keychain or `.env` in Railway. Set environment variables in Railway dashboard:
- `ANTHROPIC_API_KEY` — Anthropic API key (if keeping for rollback/fallback)
- `DEEPSEEK_API_KEY` — DeepSeek API key (required for Phase 1)
- `MONGODB_URI` — MongoDB connection string
- `REDIS_URL` — Redis connection URL
- `DEEPSEEK_DEFAULT_MODEL=deepseek-v4-flash` — Explicit model reference

### Verification (Print Status Only, Never Secrets)

Check that credentials are present without printing values:

```bash
# Check presence (shows SET/MISSING only, no values)
echo "ANTHROPIC_API_KEY: $([ -z "$ANTHROPIC_API_KEY" ] && echo 'MISSING' || echo 'SET')"
echo "DEEPSEEK_API_KEY: $([ -z "$DEEPSEEK_API_KEY" ] && echo 'MISSING' || echo 'SET')"
echo "MONGODB_URI: $([ -z "$MONGODB_URI" ] && echo 'MISSING' || echo 'SET')"
```

Expected output:
```
ANTHROPIC_API_KEY: SET
DEEPSEEK_API_KEY: SET
MONGODB_URI: SET
```

### Run Live Smoke Test

After credentials are loaded and verified as present:

```bash
poetry run python scripts/task_086_phase1_smoke_test.py
```

Expected output:
- ✅ Anthropic enrichment call succeeds (if account has credits)
- ✅ DeepSeek enrichment call succeeds
- ✅ Both write traces to llm_traces
- ✅ Cost is lower for DeepSeek
- ✅ Rollback routing verified

---

## Credential Status Checklist

- [ ] ANTHROPIC_API_KEY obtained and added to .env
- [ ] ANTHROPIC_API_KEY verified (account has credits)
- [ ] DEEPSEEK_API_KEY obtained and added to .env
- [ ] DEEPSEEK_API_KEY verified (account has credits)
- [ ] MONGODB_URI added to .env
- [ ] MONGODB_URI verified (can connect and read crypto_news.llm_traces)
- [ ] Environment loaded: `source .env`
- [ ] Credentials verified with presence check
- [ ] Ready to run live smoke test

---

## Once Live Tests Pass

After live smoke tests pass:

1. ✅ Mocked validation: PASS
2. ✅ Live smoke test: PASS
3. → **Proceed to TASK-086 Phase 1 production deployment**

Production deployment will:
- Update `_OPERATION_ROUTING["article_enrichment_batch"]` to `deepseek:deepseek-v4-flash`
- Deploy to production
- Monitor for 5-7 days
- Record decision (keep/rollback/extend)

---

## Fallback If Anthropic Account Has No Credits

If Anthropic account is at $0 balance and cannot be recharged immediately:

1. **Proceed with DeepSeek-only live smoke test**
   - Run live smoke test with DeepSeek routing only
   - Verify DeepSeek enrichment works through `LLMGateway`
   - Verify traces are recorded to llm_traces
   - Document that Anthropic baseline comparison is pending credits

2. **Use mocked Anthropic baseline**
   - Run mocked smoke test suite (no API calls)
   - Verify routing and cost calculations work for both providers
   - Acceptable for operational validation

3. **Do not advance to Phase 1 production validation without baseline**
   - Live smoke test success ≠ Phase 1 complete
   - Phase 1 validation requires comparing sentiment agreement against Haiku baseline
   - If Anthropic baseline unavailable, document pending baseline and timeline to restore
   - Add to TASK-086 decision record: "Baseline comparison pending Anthropic credits, defer Phase 1 decision until available"

---

## Troubleshooting

### "Your credit balance is too low" (Anthropic)
- **Status:** Non-blocking for live DeepSeek smoke test
- **Action:** Run DeepSeek-only test and use mocked Anthropic baseline
- **Remediation:** Add credits to Anthropic account; re-run with both providers
- **Do not mark Phase 1 complete without Haiku baseline** (mocked or live)

### "DEEPSEEK_API_KEY not configured"
- **Cause:** Environment variable not set
- **Fix:** Verify `scripts/load_keys.sh` exports it, or `source .env` is run
- **Check:** `echo $DEEPSEEK_API_KEY | wc -c` should output > 1 (not empty)
- **Note:** Never print the actual key value

### "MONGODB_URI not set"
- **Cause:** MongoDB connection string not set
- **Fix:** Verify environment is sourced; check presence only: `[ -z "$MONGODB_URI" ] && echo MISSING || echo SET`
- **Note:** Traces will still be written if DB is accessible

### "llm_traces collection not found in MongoDB"
- **Cause:** Connected to wrong database or traces not yet written
- **Fix:** Verify MONGODB_URI points to `crypto_news` database; wait 2s after API call for async write
- **Check:** `mongosh "$MONGODB_URI" --eval "db.llm_traces.countDocuments()"`

---

**Ready to proceed:** Once all three credentials are in place and verified, run the live smoke test.
