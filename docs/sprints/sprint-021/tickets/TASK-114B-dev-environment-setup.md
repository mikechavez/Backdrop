---
id: TASK-114B
type: task
status: open
priority: high
parent_sprint: Sprint 021 — Evidence & Investigation
phase: Phase A Exit Gate
depends_on: []
blocks: [TASK-114C, TASK-114D]
---

# Provision isolated local Mongo for Phase A Exit Gate review

## Goal

Stand up a throwaway, fully isolated MongoDB instance via Docker that the Phase A
Exit Gate review scripts (TASK-114C, TASK-114D) will read from and write to. This
instance must never connect to or resemble production `crypto_news` data. No
production credentials, no production database name, no shared network path.

This ticket produces infrastructure only — no review logic, no synthetic BugCases,
no EvidenceCollector invocations. Those belong to TASK-114C and TASK-114D.

## Context

Per CLAUDE.md, production database write access is forbidden for this kind of
exploratory/validation work. The Phase A Exit Gate requires Evidence Packs to be
persisted (not just constructed in memory) to genuinely test TASK-115 persistence
and the full collector path. The only way to test writes without touching
production is a local, disposable database.

## Scope

### In Scope
- [ ] `docker-compose.gate-review.yml` (or equivalent) defining a single MongoDB
      service, no auth required (local-only, throwaway), exposed on a non-default
      port to avoid collision with any other local Mongo instance (e.g. `27018`)
- [ ] A `.env.gate-review` file (gitignored) with `MONGODB_URI` pointing at the
      Dockerized instance and `MONGODB_NAME` set to something unambiguous like
      `bugops_gate_review` — never `crypto_news`
- [ ] A teardown command/script (`docker compose -f docker-compose.gate-review.yml down -v`)
      documented in the ticket completion summary, so the instance and its volume
      can be fully destroyed after the gate review concludes
- [ ] Verify the app's existing `MongoManager` singleton (per the context report,
      `src/crypto_news_aggregator/db/mongodb.py`) connects successfully against
      this instance using the new `.env.gate-review` values, and that the database
      name validation at startup (line 233, expects `crypto_news`) either passes
      against the new name or is documented as a deliberate override for this
      script only — do not modify that validation logic in the main codebase
- [ ] Confirm `bug_cases` and `evidence_packs` collections and their indexes
      (per `db/mongodb.py` lines 189-194, 267) get created correctly against the
      fresh instance — either via existing app init/migration logic if one exists,
      or document that they need manual index creation in the review script

### Out of Scope
- Writing any review/replay logic (TASK-114C, TASK-114D)
- Constructing synthetic BugCases
- Touching production MongoDB in any way
- CI/CD integration — this is a one-off manual review aid, not a permanent test fixture

## Safety Constraints

- This instance must run on localhost only, no external network exposure
- No production connection string, credentials, or database name may appear in
  any file this ticket produces
- If the existing `MongoManager.initialize()` has hardcoded expectations beyond
  the database name (e.g. specific replica set config, specific auth mechanism)
  that don't work against a bare local Mongo container, stop and document the
  blocker rather than modifying production connection code to work around it

## Acceptance Criteria

- [ ] `docker compose -f docker-compose.gate-review.yml up -d` brings up a healthy
      Mongo instance with zero manual steps beyond having Docker installed
- [ ] App's `MongoManager` connects successfully using `.env.gate-review`
- [ ] `bug_cases` and `evidence_packs` collections exist with expected indexes
- [ ] Teardown command documented and verified to fully remove the container and volume
- [ ] Completion summary states explicitly: "This instance has no path to
      production data" and how that was verified

## Files Likely Touched

- New: `docker-compose.gate-review.yml`
- New: `.env.gate-review` (gitignored)
- Possibly new: a small init script if collections/indexes aren't created by
  existing app startup logic

## Notes for Implementing Agent

- Don't reuse or modify the production `.env` file
- If you're unsure whether something is safe to do against this local instance,
  it's safe — that's the entire point of this ticket. Constraints above are
  about preventing accidental production access, not about being conservative
  with the local instance itself.
- Keep this minimal. The goal is "Mike can run one command, get a clean Mongo,
  run the gate review, then nuke it" — not a polished dev environment.
