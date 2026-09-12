---
ticket_id: BUG-107
title: Railway production container cannot start because libexpat.so.1 is missing
priority: critical
status: MITIGATED
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

### Production mitigation and verification (2026-09-12)

- Railway uses Railpack `v0.39.0`, build environment V3, runtime V2, Python `3.13.1` from `runtime.txt`, and Poetry `2.4.1` installed by Railpack. The configured start command originally invoked `poetry install && poetry run gunicorn ...`.
- The deploy failure consistently named `/mise/installs/poetry/2.4.1/venv/bin/python` and reported that it could not load `libexpat.so.1`.
- A fresh build with `NO_CACHE=1` did not resolve the failure. The generated build installed project requirements into `/app/.venv`.
- Production was made to start by bypassing Poetry at runtime and launching `/app/.venv/bin/gunicorn` directly, with `PYTHONPATH=/app/src` so both the `src.crypto_news_aggregator` entry point and absolute `crypto_news_aggregator` imports resolve.
- The deployment then reached Gunicorn startup, bound to `0.0.0.0:8000`, completed FastAPI lifespan startup, connected to MongoDB and Redis, initialized background workers, and began RSS ingestion. No `libexpat.so.1` error appeared in the supplied successful startup logs.
- After removing `NO_CACHE=1`, the user initiated another redeploy; the production health endpoint was subsequently checked and returned HTTP 200. MongoDB, Redis, and data freshness checks were `ok`.
- The health payload was overall `unhealthy` for separate issues: no LLM routing strategy for `health_check`, and naive/aware datetime subtraction in the pipeline heartbeat check (tracked separately under BUG-106).
- Successful-workaround deployment ID/commit were not provided; do not infer them from the original failed deployment ID.

### Current conclusion

The production outage is mitigated by avoiding Railpack's Poetry runtime interpreter at container startup. The direct trigger is established: the configured startup path invoked a Poetry-managed Python executable that could not load `libexpat.so.1`. The deeper reason that this Poetry interpreter lacked the shared library remains unknown; the last known-good deployment's logs/configuration were outside Railway's log-retention window, and no runtime-level comparison was available. Disabling build cache was tested and did not fix the issue, so cache corruption alone is not supported by the evidence.

## Investigation Requirements

1. (Done) Identify the Railway builder and deployment configuration.
2. Compare the failed deployment with the last known-good deployment, including commit and runtime details. Historical logs were no longer available, so this remains incomplete.
3. Determine why the Poetry-managed runtime interpreter lacks `libexpat.so.1`. This remains unresolved; the deployed workaround avoids that interpreter.
4. Reproduce the runtime check in the build environment where practical:

```bash
python --version
poetry --version
ldd "$(command -v python)" | rg 'expat|not found'
```

5. (Done) Inspect repository deployment files and Railway settings. No root Dockerfile, Nixpacks file, or Railway config was found; Railway service settings showed Railpack.

## Remediation

The production workaround is in Railway's service Start Command (not a repository build-file change):

```sh
PYTHONPATH=/app/src /app/.venv/bin/gunicorn -w 4 -k uvicorn.workers.UvicornWorker src.crypto_news_aggregator.main:app --bind 0.0.0.0:$PORT
```

This uses the project environment populated during the Railpack build and avoids invoking `poetry install` in the runtime container. `NO_CACHE=1` was used during diagnosis, did not fix the Poetry interpreter failure, and was removed before a subsequent redeploy.

If Poetry must be retained as the runtime command, investigate/fix the missing shared library in the Railpack Poetry runtime separately. Do not claim the deeper image/package cause is known.

Original remediation options (not used):

Use the smallest verified fix:

- Clear Railway build cache and redeploy if the failure is cache/image corruption.
- If using Nixpacks, explicitly install the OS package that provides `libexpat.so.1` through the supported Nixpacks configuration.
- If using a Dockerfile, use a supported Python base image or install the required runtime package in the image.
- If the failure is caused by a dependency/runtime mismatch, pin the compatible Python/Poetry/runtime versions and document why.

Do not add arbitrary binary files or vendor system libraries into the repository. Do not change application MongoDB behavior for this ticket.

## Recovery and Verification

1. Preserve the failed deployment logs and identify the exact deployment commit/configuration. Partial: failed deployment ID/configuration are known; historical logs and successful-workaround deployment ID/commit were not recorded.
2. Redeploy the last known-good revision only if needed to restore service quickly; record the revision used.
3. (Done as mitigation) Change Railway's start command to launch Gunicorn from `/app/.venv` with `PYTHONPATH=/app/src`.
4. The container starts with that command, but Poetry's missing-library cause was not repaired or directly re-tested. Verification proves the workaround avoids the failing Poetry interpreter.
5. (Done, with caveats) Deploy to Railway and verify:
   - container remains running;
   - no repeated shared-library error;
   - Gunicorn binds to port 8000;
   - workers pass application startup and Gunicorn binds to port 8000;
   - health endpoint responds with HTTP 200 (overall health still reports unrelated LLM and pipeline-check errors);
   - MongoDB and Redis checks pass.
6. Successful workaround deployment ID/commit and focused local tests were not recorded; capture them if available.

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

- [ ] Deeper root cause of why the Poetry-managed interpreter lacks `libexpat.so.1` is identified and documented (production workaround is known).
- [ ] Failed versus known-good runtime/build configuration is compared; historical logs unavailable.
- [x] Production workaround is configured in Railway's Start Command; no repository build configuration change was required.
- [ ] The Poetry-managed runtime interpreter itself is verified to load `libexpat.so.1` (not necessary for the active workaround).
- [x] Railway production starts and remains reachable without the shared-library error, including after removing `NO_CACHE=1`.
- [x] Gunicorn starts and binds to port 8000; MongoDB and Redis checks pass. Health endpoint returns HTTP 200, though overall health remains unhealthy for separately tracked checks.
- [ ] Successful deployment ID, commit, and exact log artifact are recorded; only the original failed deployment ID is currently known.
- [ ] No secrets or full connection strings are committed or placed in the ticket.
