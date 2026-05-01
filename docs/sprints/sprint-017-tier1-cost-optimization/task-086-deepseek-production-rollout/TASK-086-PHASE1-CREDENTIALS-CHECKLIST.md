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

## Setup Steps

### Step 1: Populate .env file
```bash
# Edit .env and add the three credentials:
vi .env
```

Required additions:
```bash
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...
MONGODB_URI=mongodb+srv://...
```

### Step 2: Load environment
```bash
# Option A: Source .env directly
source .env

# Option B: Use load_keys.sh (macOS Keychain)
# First, add keys to keychain:
security add-generic-password -s "ANTHROPIC_API_KEY" -w "sk-ant-..."
security add-generic-password -s "DEEPSEEK_API_KEY" -w "sk-..."

# Then source load_keys.sh (edit to uncomment ANTHROPIC_API_KEY and DEEPSEEK_API_KEY)
source scripts/load_keys.sh
```

### Step 3: Verify environment
```bash
# Check that credentials are loaded (without printing them)
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

### Step 4: Run live smoke test
```bash
poetry run python scripts/task_086_phase1_smoke_test.py
```

Expected output:
- ✅ Anthropic enrichment call succeeds
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

## Troubleshooting

### "ANTHROPIC_API_KEY not configured"
- **Cause:** Environment variable not set
- **Fix:** Run `source .env` and verify `echo $ANTHROPIC_API_KEY` outputs something

### "Your credit balance is too low"
- **Cause:** Anthropic account has $0 credits
- **Fix:** Add credits to your Anthropic account

### "DEEPSEEK_API_KEY not configured"
- **Cause:** Environment variable not set
- **Fix:** Run `source .env` and verify `echo $DEEPSEEK_API_KEY` outputs something

### "MONGODB_URI not set, cannot write sync trace"
- **Cause:** MongoDB connection string not set
- **Fix:** Run `source .env` and verify `echo $MONGODB_URI` outputs something
- **Note:** Traces will still be recorded to MongoDB if DB is accessible

### Tests pass but can't verify traces in MongoDB
- **Cause:** Don't have read access to crypto_news database
- **Fix:** Use same MongoDB URI as production/staging where data lives

---

**Ready to proceed:** Once all three credentials are in place and verified, run the live smoke test.
