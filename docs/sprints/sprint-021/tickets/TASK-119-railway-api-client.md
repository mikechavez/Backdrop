---
ticket_id: TASK-119
title: Build Railway API client
priority: high
status: ✅ COMPLETE
phase: A
date_created: 2026-06-16
branch: task/bugops-119-railway-api-client
effort_estimate: medium
date_completed: 2026-06-20
---

# TASK-119: Build Railway API client

## Problem Statement

Both deploy context collection (TASK-120) and log collection (TASK-122) require a Railway GraphQL API client. The stub at `bugops/signal_sources/railway_logs.py` makes no real API calls. This ticket implements the real client as a shared module.

---

## Context

Railway exposes logs and deployment data via GraphQL API at `https://backboard.railway.app/graphql/v2`. Authentication uses a bearer token. The CLI cannot be used — it requires local auth and cannot run inside a Railway container.

**Log query flow:**
```
Project → Services → Active Deployment → Logs (by deployment ID + time range)
```

Logs are queried by deployment ID, not by service name directly. Service name must be resolved to a deployment ID first.

**Service name mapping** — the Railway API uses internal IDs, not human-readable names. The implementation must resolve:

```
service_name ("fastapi", "celery_worker", "celery_scheduler")
    ↓
Railway service ID (UUID)
    ↓
Active deployment ID (UUID)
    ↓
Log lines
```

This mapping requires `RAILWAY_PROJECT_ID` (the Railway project UUID) to scope service lookups. Add this to config. Service name → Railway service ID mapping must also be configurable (Railway service names in the dashboard may differ from what Backdrop calls them internally).

**Truncation detection** — fetch `line_cap + 1` lines from Railway. If `len(result) > line_cap`, truncation occurred. Store only `line_cap` lines (drop the extra). This is the only reliable way to detect truncation when Railway returns exactly `line_cap` lines.

**Implementation note** — Railway's GraphQL schema must be verified against their live API during implementation. The query shapes below are the expected structure based on Railway's documented API. The implementation agent must run a schema introspection query first and adjust field names as needed. Document the actual queries used in the Completion Summary.

---

## Task

1. Create `RailwayClient` at `bugops/clients/railway.py`
2. Create `bugops/clients/__init__.py`
3. Add config keys to `core/config.py`
4. Write unit tests with mocked HTTP responses

---

## Files to Create

```
src/crypto_news_aggregator/bugops/clients/__init__.py
src/crypto_news_aggregator/bugops/clients/railway.py
tests/bugops/test_railway_client.py
```

---

## Files to Modify

```
src/crypto_news_aggregator/core/config.py  (add Railway config keys)
```

---

## Do Not Modify

```
src/crypto_news_aggregator/bugops/signal_sources/railway_logs.py  (stub stays; client is now in bugops/clients/)
src/crypto_news_aggregator/bugops/monitor.py
src/crypto_news_aggregator/bugops/models.py
```

---

## Implementation Requirements

### Config keys to add

```python
# In core/config.py BugOps section:
RAILWAY_API_TOKEN: str = ""
RAILWAY_PROJECT_ID: str = ""

# Service name → Railway service display name mapping
# Allows decoupling internal names from Railway dashboard names
RAILWAY_SERVICE_NAME_FASTAPI: str = "fastapi"
RAILWAY_SERVICE_NAME_CELERY_WORKER: str = "celery-worker"
RAILWAY_SERVICE_NAME_CELERY_SCHEDULER: str = "celery-scheduler"
```

### RailwayClient interface

```python
# bugops/clients/railway.py

class RailwayClient:
    """
    Railway GraphQL API client.
    Authenticates via RAILWAY_API_TOKEN.
    Service names resolved to deployment IDs for log and deployment queries.
    """
    
    GRAPHQL_URL = "https://backboard.railway.app/graphql/v2"
    
    def __init__(self, settings):
        self.api_token = settings.RAILWAY_API_TOKEN
        self.project_id = settings.RAILWAY_PROJECT_ID
        self.service_name_map = {
            "fastapi": settings.RAILWAY_SERVICE_NAME_FASTAPI,
            "celery_worker": settings.RAILWAY_SERVICE_NAME_CELERY_WORKER,
            "celery_scheduler": settings.RAILWAY_SERVICE_NAME_CELERY_SCHEDULER,
        }
        self._deployment_id_cache: dict[str, str] = {}
    
    async def get_active_deployment_id(self, service_name: str) -> Optional[str]:
        """
        Resolve internal service name to active Railway deployment ID.
        Cached per client instance.
        Returns None if service not found or API unavailable.
        """
        if service_name in self._deployment_id_cache:
            return self._deployment_id_cache[service_name]
        # Resolve via GraphQL, cache result, return
        ...
    
    async def get_recent_deployments(
        self,
        service_name: str,
        since: datetime,
    ) -> list[dict]:
        """
        Fetch deployments for a service created at or after `since`.
        Returns list of dicts:
          {"deployment_id": str, "status": str, "created_at": str, "updated_at": str, "service": service_name}
        Returns empty list on API error — caller records as unavailable.
        """
        ...
    
    async def get_logs(
        self,
        service_name: str,
        start_time: datetime,
        end_time: datetime,
        line_cap: int,
    ) -> tuple[list[str], bool]:
        """
        Fetch log lines for a service within time window.
        
        Fetches line_cap + 1 lines from Railway.
        If len(result) > line_cap: truncated=True, store only line_cap lines.
        If len(result) <= line_cap: truncated=False, store all lines.
        
        Returns (log_lines, was_truncated).
        Returns ([], False) on API error — caller records as unavailable.
        """
        ...
    
    async def _graphql(self, query: str, variables: dict) -> Optional[dict]:
        """
        Execute a GraphQL query against Railway API.
        Returns parsed response["data"] or None on any error.
        Handles: auth, timeout (10s default), HTTP errors, JSON parse errors.
        Logs errors at error level. Never raises.
        """
        ...
```

### Expected GraphQL query shapes (verify during implementation)

```graphql
# Introspection — run this first to verify schema
{ __schema { queryType { fields { name } } } }

# Get services for project
query GetServices($projectId: String!) {
  project(id: $projectId) {
    services {
      edges {
        node {
          id
          name
        }
      }
    }
  }
}

# Get active deployment for a service
query GetActiveDeployment($serviceId: String!) {
  deployments(
    first: 1
    input: { serviceId: $serviceId }
    orderBy: { field: CREATED_AT, direction: DESC }
  ) {
    edges {
      node {
        id
        status
        createdAt
        updatedAt
      }
    }
  }
}

# Get logs for a deployment
query GetDeploymentLogs(
  $deploymentId: String!
  $startDate: DateTime
  $endDate: DateTime
  $limit: Int
) {
  deploymentLogs(
    deploymentId: $deploymentId
    startDate: $startDate
    endDate: $endDate
    limit: $limit
    filter: ""
  ) {
    timestamp
    message
    severity
  }
}
```

**Important:** Railway's GraphQL schema evolves. The implementation agent must run the introspection query first and verify field names before implementing the above queries. Document the actual working queries in the Completion Summary.

### HTTP client pattern (follow existing `slack.py` httpx pattern)

```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.post(
        self.GRAPHQL_URL,
        json={"query": query, "variables": variables},
        headers={
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        },
        timeout=10.0,
    )
    response.raise_for_status()
    data = response.json()
    return data.get("data")
```

---

## Verification

### Automated Verification

```bash
pytest tests/bugops/test_railway_client.py -v
pytest tests/bugops/ -v
```

All tests use mocked `httpx.AsyncClient` — no real Railway API calls in tests.

### Required Test Coverage

- [ ] `_graphql` sends correct `Authorization: Bearer <token>` header
- [ ] `_graphql` returns `None` on HTTP 401 (does not raise)
- [ ] `_graphql` returns `None` on timeout (does not raise)
- [ ] `_graphql` returns `None` on JSON parse error (does not raise)
- [ ] `get_active_deployment_id` returns cached value on second call (no second HTTP request)
- [ ] `get_active_deployment_id` returns `None` when service not found in Railway
- [ ] `get_active_deployment_id` uses `service_name_map` to resolve internal name to Railway display name
- [ ] `get_logs` fetches `line_cap + 1` lines from Railway
- [ ] `get_logs` returns `(lines[:line_cap], True)` when Railway returns `line_cap + 1` lines
- [ ] `get_logs` returns `(lines, False)` when Railway returns `<= line_cap` lines
- [ ] `get_logs` returns `([], False)` on API error
- [ ] `get_recent_deployments` returns empty list on API error
- [ ] `get_recent_deployments` filters by `since` datetime correctly

### Manual Verification (after deploy)

- [ ] `RailwayClient` successfully resolves at least one service name to a deployment ID against live Railway API
- [ ] `get_logs` returns non-empty log lines for `celery_worker` service

---

## Acceptance Criteria

- [ ] `RailwayClient` implemented at `bugops/clients/railway.py`
- [ ] Auth via `RAILWAY_API_TOKEN` environment variable
- [ ] `RAILWAY_PROJECT_ID` and service name mapping config keys added
- [ ] Deployment ID caching implemented — no redundant API calls per collection cycle
- [ ] Truncation detection uses `line_cap + 1` fetch strategy
- [ ] All methods return safe defaults on error — never raise to caller
- [ ] All tests pass with mocked HTTP
- [ ] All existing BugOps tests continue to pass
- [ ] Actual working GraphQL queries documented in Completion Summary

---

## Related Tickets

- TASK-116: Framework (must be complete first)
- TASK-120: Deploy context collector (depends on this)
- TASK-122: Log collector (depends on this)

---

## Implementation Summary

### What Was Built

**RailwayClient** (`src/crypto_news_aggregator/bugops/clients/railway.py`):
- Async GraphQL client with three public methods:
  - `get_active_deployment_id(service_name)` — Resolves service name to deployment ID with caching
  - `get_recent_deployments(service_name, since)` — Fetches deployments created after a timestamp
  - `get_logs(service_name, start_time, end_time, line_cap)` — Fetches logs with truncation detection
- Private `_graphql()` method handles all error cases gracefully (never raises)
- Supports both Account/Workspace tokens (Bearer auth) and Project tokens (Project-Access-Token header)
- Deployment ID caching prevents redundant API calls within collection cycle

**Config Keys** (`src/crypto_news_aggregator/core/config.py`):
- `RAILWAY_API_TOKEN` — API token for authentication
- `RAILWAY_PROJECT_ID` — Project UUID for service lookups
- `RAILWAY_SERVICE_NAME_FASTAPI`, `RAILWAY_SERVICE_NAME_CELERY_WORKER`, `RAILWAY_SERVICE_NAME_CELERY_SCHEDULER` — Service name mapping

**Tests** (`tests/bugops/test_railway_client.py`):
- 21 comprehensive tests covering:
  - GraphQL execution, auth headers, error handling (401, timeout, JSON parse, GraphQL errors)
  - Deployment ID caching and service resolution
  - Recent deployments filtering and response format
  - Log fetching, truncation detection, message extraction
- All tests use mocked HTTP responses (no live API calls during testing)

**Verification Script** (`scripts/verify_railway_schema.py`):
- Runs against live Railway API to verify:
  - Schema introspection (124 query fields)
  - Service resolution (GetServices → service ID)
  - Deployment lookup (GetActiveDeployment → deployment ID)
  - Log fetching (GetDeploymentLogs → log lines)

### Live Testing Results (2026-06-20)

✅ **Schema Introspection**
- Endpoint: `https://backboard.railway.com/graphql/v2`
- Found 124 query fields available
- Confirmed schema structure is correct

✅ **Service Resolution**
- Resolved "celery-worker" internal name to service ID: `2c8a41b9-6ff6-4344-a893-e2e0e6c32617`
- Query: GetServices with project ID returns all services

✅ **Deployment Lookup**
- Retrieved active deployment: `1f60248e-364a-4c0d-8dd2-4e3e41ca9b14`
- Status: SUCCESS
- Created: 2026-06-20T04:17:21.213Z

✅ **Log Fetching**
- Retrieved 10 real production log lines from celery-worker service
- Log format verified: timestamp, severity, message all present
- Truncation detection: fetching line_cap + 1 correctly identifies overflow

### Key Implementation Details

1. **Endpoint Correction**: Documentation showed `.app` but actual API is `.com`
2. **Auth Flexibility**: Added support for Project tokens (uses `Project-Access-Token` header instead of Bearer)
3. **Query Syntax**: Removed unsupported `orderBy` argument; Railway API returns results pre-sorted in reverse chronological order
4. **Error Handling**: All methods return safe defaults (None, [], False) on error; caller decides how to handle
5. **Caching Strategy**: Deployment IDs cached per client instance; cache is fresh per collection cycle

## Completion Summary

- Branch: task/bugops-119-railway-api-client
- Commits: 213bf49 (code), 14edcc8 (docs), f021b54 (status), 2343ae4 (live verification fixes), 540b2d7 (final docs)

### ✅ Code Implementation Complete

- RailwayClient fully implemented at `bugops/clients/railway.py`
- All three public methods implemented: `get_active_deployment_id()`, `get_recent_deployments()`, `get_logs()`
- Private `_graphql()` method handles all HTTP/GraphQL error cases gracefully
- Config keys added: `RAILWAY_PROJECT_ID`, `RAILWAY_SERVICE_NAME_*`
- Test suite: 21 comprehensive tests, all passing with mocked responses
- No regressions: 57 existing evidence collector tests continue to pass

### ✅ Live Railway API Verification Complete

**Verified Against Live Railway API (June 20, 2026):**

1. ✅ Schema introspection: 124 query fields confirmed available
   - Endpoint: `https://backboard.railway.com/graphql/v2` (not .app)
   - Auth: Project tokens use `Project-Access-Token` header (not `Authorization: Bearer`)

2. ✅ GetServices query: Successfully resolved "celery-worker" service
   - Project ID: 0651e5bb-0e47-4183-8198-c321cf2242c9
   - Service ID: 2c8a41b9-6ff6-4344-a893-e2e0e6c32617
   - Found 5 services total in project

3. ✅ GetActiveDeployment query: Retrieved active deployment
   - Deployment ID: 1f60248e-364a-4c0d-8dd2-4e3e41ca9b14
   - Status: SUCCESS
   - Created: 2026-06-20T04:17:21.213Z
   - **Note:** Railway API returns results in reverse chronological order by default (no orderBy support)

4. ✅ GetDeploymentLogs query: Retrieved real production log lines
   - Retrieved 10 log lines from celery-worker service
   - Log format verified: message, severity, timestamp present
   - **Truncation detection works:** Can fetch line_cap + 1 to detect when results exceed cap

**Actual GraphQL Query Shapes (as corrected during live testing):**
```graphql
query GetServices($projectId: String!) {
  project(id: $projectId) {
    services {
      edges {
        node { id name }
      }
    }
  }
}

query GetActiveDeployment($serviceId: String!) {
  deployments(
    first: 1
    input: { serviceId: $serviceId }
  ) {
    edges {
      node { id status createdAt updatedAt }
    }
  }
}

query GetDeploymentLogs(
  $deploymentId: String!
  $startDate: DateTime
  $endDate: DateTime
  $limit: Int
) {
  deploymentLogs(
    deploymentId: $deploymentId
    startDate: $startDate
    endDate: $endDate
    limit: $limit
    filter: ""
  ) {
    timestamp message severity
  }
}
```

### Service Name Resolution Approach

- Internal names (fastapi, celery_worker, celery_scheduler) mapped to Railway display names via config
- Two-step resolution: internal name → service ID lookup → active deployment ID
- Caching per client instance prevents redundant API calls within single collection cycle
- Tested against celery-worker service; resolved successfully

### Key Implementation Discoveries

1. **Endpoint is .com, not .app** — Documentation URLs use `.app` but the actual API endpoint is `.com`
2. **Project token auth** — Tokens created in project settings require `Project-Access-Token` header, not `Authorization: Bearer`
3. **No orderBy in deployments** — Railway API does not support `orderBy` argument; results come pre-sorted in reverse chronological order
4. **Truncation detection confirmed** — Fetching `line_cap + 1` lines works; comparison against cap size determines if truncation occurred

### Deviations from Original Plan

- Original ticket showed `orderBy: { field: CREATED_AT, direction: DESC }` syntax — Railway API does not support this argument. Removed during live testing.
- Original endpoint listed `.app`; corrected to `.com` based on actual Railway API docs and live testing.
- Original auth examples showed Bearer token; added support for Project token auth with `Project-Access-Token` header.
