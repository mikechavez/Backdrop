---
id: BUG-053
type: bug
status: OPEN
priority: high
severity: high
created: 2026-04-02
updated: 2026-04-02
---

# BUG-053: Hardcoded SMTP Password in config.py

## Problem

`src/crypto_news_aggregator/core/config.py` contains a plaintext SMTP password on line ~107.

This credential is committed to the Git repo and visible to anyone with access. Additionally, SMTP is not actively used in the app, but the config still contains full SMTP settings with real credentials, which is unnecessary attack surface.

## Expected Behavior

- No secrets hardcoded in source code
- SMTP password loaded from environment variable with empty default
- SMTP functionality explicitly disabled if not configured

## Actual Behavior

- Password is hardcoded in plain text in a committed file
- SMTP settings contain real credentials
- No guard preventing accidental email sends if SMTP code paths are triggered

## Steps to Reproduce
1. Open `src/crypto_news_aggregator/core/config.py`
2. Observe `SMTP_PASSWORD` on ~line 102

## Environment
- Environment: All (code is in repo)
- User impact: high (credential exposure)

---

## Resolution

**Status:** Open

### Changes Required

#### Step 1: Rotate the credential
Before any code changes, go to Mailtrap (or wherever the SMTP account lives) and change the password. The current one is compromised since it's in Git history.

#### Step 2: Update config.py

Replace all hardcoded SMTP values with safe empty defaults:

```python
# Email Settings
SMTP_SERVER: str = ""          # was: "smtp.mailtrap.io"
SMTP_PORT: int = 2525
SMTP_USERNAME: str = ""        # was: "snotboogy"
SMTP_PASSWORD: str = ""        # was: hardcoded password
SMTP_USE_TLS: bool = True
SMTP_TIMEOUT: int = 10

EMAIL_FROM: str = ""           # was: "snotboogy@cryptochime.com"
EMAIL_FROM_NAME: str = "Backdrop"
SUPPORT_EMAIL: str = ""        # was: "support@example.com"
```

#### Step 3: Verify SMTP is not called anywhere in active code paths

Search the codebase for any active usage of SMTP/email sending:
```bash
grep -r "SMTP\|send_email\|smtp" src/ --include="*.py" -l
```

If email sending code exists, confirm it is either:
- Behind a feature flag / config check (e.g., `if settings.SMTP_SERVER:`)
- Only triggered by explicit admin action (not automatic)
- Disabled by default when SMTP settings are empty

If any code path could trigger email sending without explicit configuration, add a guard:
```python
if not settings.SMTP_SERVER or not settings.SMTP_PASSWORD:
    logger.warning("SMTP not configured, skipping email send")
    return
```

#### Step 4: Clean up Git history (optional, low priority)

The password is in Git history. For a private repo this is lower risk, but consider:
- If the repo ever becomes public, the password is exposed
- `git filter-branch` or BFG Repo-Cleaner can scrub it, but this rewrites history

### Files Changed
- `src/crypto_news_aggregator/core/config.py` — remove hardcoded SMTP credentials
- Any email-sending modules — add guard for unconfigured SMTP

### Testing
- [ ] App starts without SMTP env vars (empty defaults don't crash)
- [ ] Health endpoint still works
- [ ] No email-related errors in logs on startup
- [ ] Grep confirms no other hardcoded credentials in codebase