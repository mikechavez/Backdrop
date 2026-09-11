---
ticket_id: BUG-107
title: Railway production container cannot start because libexpat.so.1 is missing
priority: critical
status: OPEN
phase: A
date_created: 2026-09-11
branch: fix/bug-107-railway-missing-libexpat-runtime
effort_estimate: medium
---

# BUG-107: Railway production container cannot start because libexpat.so.1 is missing

## Problem Statement

Railway deployment `16127b3f` for `crypto-news-aggregator` crashed before the application started. The runtime repeatedly reported:

```text
/mise/installs/poetry/2.4.1/venv/bin/python: error while loading shared libraries: libexpat.so.1: cannot open shared object file: No such file or directory
```

This is a container/runtime image failure, not a MongoDB failure. Python cannot launch, so FastAPI lifespan startup, MongoDB connection, and application code are never reached.

## Evidence

- Railway service: `crypto-news-aggregator`
- Environment: `production`
- Deployment: `16127b3f`
- Region: US East
- Observed: 2026-09-11 13:44 PDT through 13:52 PDT
- Repeated process restart/crash loop
- Existing BUG-105 MongoDB recovery is a separate incident; BUG-106 covers health-check routing/datetime errors observed after recovery.

## Investigation Requirements

1. Identify the Railway build method and runtime image used by the failed deployment (Nixpacks, Docker, or other configuration).
2. Compare the failed deployment with the last known-good deployment, including commit, build configuration, Python/Poetry versions, and build cache state.
3. Determine which package supplies `libexpat.so.1` for the selected base image and why it is absent.
4. Reproduce the runtime check in the build environment where practical:

```bash
python --version
poetry --version
ldd "$(command -v python)" | rg 'expat|not found'
```

5. Inspect repository deployment files before adding configuration. Current repository discovery found `pyproject.toml`, `poetry.lock`, and `docker-compose.gate-review.yml`; no root Dockerfile or Railway/Nixpacks file was found at ticket creation time. Check Railway service settings as well as the repository.

## Remediation Options

Use the smallest verified fix:

- Clear Railway build cache and redeploy if the failure is cache/image corruption.
- If using Nixpacks, explicitly install the OS package that provides `libexpat.so.1` through the supported Nixpacks configuration.
- If using a Dockerfile, use a supported Python base image or install the required runtime package in the image.
- If the failure is caused by a dependency/runtime mismatch, pin the compatible Python/Poetry/runtime versions and document why.

Do not add arbitrary binary files or vendor system libraries into the repository. Do not change application MongoDB behavior for this ticket.

## Recovery and Verification

1. Preserve the failed deployment logs and identify the exact deployment commit/configuration.
2. Redeploy the last known-good revision only if needed to restore service quickly; record the revision used.
3. Apply the minimal build/runtime fix.
4. Confirm the built container can launch Python and resolve `libexpat.so.1` before application startup.
5. Deploy to Railway and verify:
   - container remains running;
   - no repeated shared-library error;
   - Gunicorn binds to port 8000;
   - all workers pass application startup;
   - health endpoint responds;
   - MongoDB and Redis checks run after the runtime is fixed.
6. Run focused tests locally and record the Railway deployment ID and commit.

## Files to Inspect / Modify

```
pyproject.toml
poetry.lock
docker-compose.gate-review.yml
Dockerfile                    # if present in Railway configuration or added as the approved fix
nixpacks.toml                  # if present or required by the approved Nixpacks fix
railway.toml / railway.json    # if present
docs/sprints/sprint-021/tickets/BUG-107-railway-missing-libexpat-runtime.md
```

Also inspect Railway service build/deploy settings; those settings may not be represented in this repository.

## Acceptance Criteria

- [ ] Root cause of missing `libexpat.so.1` is identified and documented.
- [ ] Failed versus known-good runtime/build configuration is compared.
- [ ] Minimal fix is implemented in the correct Railway build configuration.
- [ ] Local/runtime verification confirms Python can load `libexpat.so.1`.
- [ ] Railway production deployment remains running without the shared-library error.
- [ ] Gunicorn, health, MongoDB, and Redis verification pass.
- [ ] Deployment ID, commit, logs, and rollback/recovery notes are recorded.
- [ ] No secrets or full connection strings are committed or placed in the ticket.
