Crypto News Aggregator - Project Instructions
Git Workflow Standards
Branch Strategy
ALL changes require feature branches - NO direct commits to main
Branch format: {type}/{description}
Types: feature/, fix/, docs/, chore/
Commit Message Format

type(scope): short description

Bullet point details if needed

Commit types: feat, fix, refactor, docs, test, chore, perf

Rules:

No emojis
No AI attribution or co-author tags
Extract scope from ticket (e.g., sentiment, api, ui, narratives, timeline)
Map tickets to types: BUG→fix(), FEAT→feat(), DOCS→docs(), CHORE→chore()
Pull Request Workflow
Create PR: Push feature branch and open PR against main
PR naming: Use same format as commits: type(scope): description
Merge strategy: Squash merge to main (one commit per PR)
Requirements: All tests must pass before merge
Review: Ensure changes match ticket requirements
Secrets Safety

Coding agents must never print, echo, cat, grep, or log secret values.

Forbidden:

Printing environment variables that may contain secrets
Running env | grep API_KEY
Running env | grep TOKEN
Running env | grep SECRET
Reading .env files unless explicitly instructed by the human
Running security find-generic-password ... -w directly unless explicitly instructed by the human
Committing .env files, API keys, tokens, database URIs, or other secrets
Pasting secret values into tickets, docs, commits, PR descriptions, logs, or chat output

Allowed:

Checking whether a required environment variable is set using set / missing output only
Running source scripts/load_keys.sh if instructed
Using secrets already available in the process environment without printing them
Asking the human to configure missing secrets manually

Safe check example:

python - <<'PY'
import os

for key in ["DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "MONGODB_URI"]:
    print(f"{key}: {'set' if os.getenv(key) else 'missing'}")
PY
Production Database Safety

Coding agents must never use unrestricted production database credentials.

Default agent database access:

Production: read-only user only
Staging/dev: read-write allowed
Destructive operations require explicit human approval and must run only with human-owned credentials

Forbidden for coding agents on production:

deleteMany
drop
updateMany without explicit approval
bulkWrite with destructive changes
Collection drops
Database drops
Index drops
Cleanup scripts that mutate production data
Smoke tests that delete or overwrite production data
Validation scripts that delete or overwrite production data

Agents may inspect production data using read-only credentials only.

Smoke tests, validation scripts, and cleanup scripts must never delete, drop, overwrite, or bulk-update production collections.

Production Runtime Credentials

Production app runtime credentials are separate from coding-agent credentials.

Railway production runtime may use a write-capable MongoDB URI so the app can write:

Articles
Enrichment results
llm_traces
Operational metadata

Coding agents must not use Railway production write credentials.

LLM Gateway Rules

All production LLM calls must go through LLMGateway.

Do not bypass LLMGateway for:

Anthropic calls
DeepSeek calls
OpenRouter calls
Model validation calls that are intended to represent production behavior

Provider selection must remain centralized in gateway routing.

Rollback between providers should require routing/config changes only, not call-site rewrites.

Forbidden:

Adding direct provider calls inside enrichment call sites
Adding DeepSeek-specific logic inside RSS services or article enrichment code
Changing global provider config in a way that bypasses operation-level routing
Creating validation paths that do not match the production gateway path
Testing and Validation

Before marking a ticket complete:

Run relevant unit tests
Run relevant integration or smoke tests when available
Confirm tests match the production path being changed
Document any skipped tests and why

For live validation:

Prefer mocked validation first
Use live credentials only after mocked validation passes
Never print credential values
Never mutate production data except through normal app behavior
Record rollback steps before deployment
Incident / Safety Rule

If a coding agent encounters production data, credentials, billing, or destructive operations, pause and ask the human before proceeding.

When uncertain, choose the safer option:

Read-only over write access
Mocked validation over live mutation
Presence checks over printing values
Human approval over autonomous destructive action