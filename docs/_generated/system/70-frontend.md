# Frontend Routes & React API Integration

## Overview

The frontend is a React SPA that serves the user interface, displays briefings and narratives, integrates with backend APIs, and provides operational visibility into LLM cost usage. This document describes the React routing architecture, component structure, API integrations, Cost Monitor behavior, proposed BugOps dashboard boundaries, and common debugging checks.

**Anchor:** `#frontend-routes-api`

**Status note:** This document supersedes the prior frontend doc section that stated the Cost Monitor had no live API endpoint. The current `CostMonitor.tsx` is wired to admin API methods and refreshes live data on intervals.

---

## Architecture

### Key Components

- **React Router v7** — Client-side navigation without page reloads
- **BrowserRouter** — Browser history and URL management
- **Routes & Route Components** — Page mappings for core product routes
- **API Client** — Async functions for backend communication
- **TanStack React Query** — Data fetching, loading/error states, polling, cache invalidation
- **Layout Navigation** — Sidebar navigation with active route highlighting
- **Cost Monitor UI** — Live LLM cost/caching/processing dashboard
- **Planned BugOps Dashboard** — Separate operational dashboard for bug cases, traces, alerts, approvals, and BugOps budget

---

## Routes Overview

The current application exposes five main product routes served from a single-page entry point.

| Route | Component | Purpose | API Calls |
|---|---|---|---|
| `/` | `Briefing` | Display latest daily briefing | `GET /briefings/latest` |
| `/signals` | `Signals` | Show active market signals and alerts | `GET /signals` |
| `/narratives` | `Narratives` | Browse narrative threads | `GET /narratives` |
| `/articles` | `Articles` | View collected news articles | `GET /articles` |
| `/cost-monitor` | `CostMonitor` | Track production LLM usage, cache, model, operation, and processing metrics | Admin API calls via `adminAPI` |

### Proposed Future BugOps Routes

BugOps should be a separate dashboard, not a tab inside the existing Cost Monitor. The Cost Monitor tracks production LLM spend and optimization; BugOps tracks incidents, investigations, tool calls, approvals, separate BugOps LLM budget, and agent traces.

| Route | Component | Purpose | API Calls |
|---|---|---|---|
| `/bugops` | `BugOpsDashboard` | Overview of open cases, active alerts, service health, and decisions needed | `GET /bugops/summary` |
| `/bugops/cases` | `BugCaseList` | Browse bug cases by status/severity/service | `GET /bugops/cases` |
| `/bugops/cases/:caseId` | `BugCaseDetail` | Full case timeline, evidence, report, Q&A, approvals | `GET /bugops/cases/{caseId}` |
| `/bugops/traces` | `BugTraceExplorer` | Inspect BugOps model calls, tool calls, files read, commands run | `GET /bugops/traces` |
| `/bugops/budget` | `BugOpsBudget` | Separate BugOps LLM budget, spend by case/model/operation | `GET /bugops/budget` |
| `/bugops/settings` | `BugOpsSettings` | Alert thresholds, Slack webhook status, approval rules, budget limits | `GET/PUT /bugops/settings` |

---

## Implementation Details

### Route Configuration

**File:** `context-owl-ui/src/App.tsx`

The root application component uses React Router to define routes:

```tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Briefing />} />
          <Route path="/signals" element={<Signals />} />
          <Route path="/narratives" element={<Narratives />} />
          <Route path="/articles" element={<Articles />} />
          <Route path="/cost-monitor" element={<CostMonitor />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
```

**Key behaviors:**

- `BrowserRouter` manages URL state and browser history
- Routes are wrapped in `Layout` for shared navigation
- Current routes are public unless backend/API auth is added separately
- Route paths match API endpoint patterns where practical

### Proposed BugOps Route Additions

When BugOps UI is implemented, add routes separately from Cost Monitor:

```tsx
<Route path="/bugops" element={<BugOpsDashboard />} />
<Route path="/bugops/cases" element={<BugCaseList />} />
<Route path="/bugops/cases/:caseId" element={<BugCaseDetail />} />
<Route path="/bugops/traces" element={<BugTraceExplorer />} />
<Route path="/bugops/budget" element={<BugOpsBudget />} />
<Route path="/bugops/settings" element={<BugOpsSettings />} />
```

---

## Layout & Navigation

**File:** `context-owl-ui/src/components/Layout.tsx`

The Layout component provides navigation sidebar entries. Existing navigation includes:

```tsx
const navigationItems = [
  { path: '/', label: 'Briefing', icon: BookOpen },
  { path: '/signals', label: 'Signals', icon: TrendingUp },
  { path: '/narratives', label: 'Narratives', icon: Newspaper },
  { path: '/articles', label: 'Articles', icon: FileText },
  { path: '/cost-monitor', label: 'Cost Monitor', icon: DollarSign },
];
```

Planned BugOps navigation should be a distinct primary item:

```tsx
{ path: '/bugops', label: 'BugOps', icon: Bug }
```

Do not merge BugOps into Cost Monitor navigation. BugOps has a separate product purpose and separate budget.

---

## API Client Integration

**File:** `context-owl-ui/src/api/client.ts` or `context-owl-ui/src/api/index.ts`

API calls are abstracted into service modules.

### Briefing API

```typescript
// GET /briefings/latest
async function getLatestBriefing() {
  const response = await fetch(`${API_BASE}/briefings/latest`);
  return response.json();
}
```

Returns latest production briefing fields such as `_id`, `type`, `generated_at`, `content`, `metadata`, `is_smoke`, and `task_id`.

### Signals API

```typescript
// GET /signals?limit=50
async function getSignals(limit: number = 50) {
  const response = await fetch(`${API_BASE}/signals?limit=${limit}`);
  return response.json();
}
```

### Narratives API

```typescript
// GET /narratives?limit=30
async function getNarratives(limit: number = 30) {
  const response = await fetch(`${API_BASE}/narratives?limit=${limit}`);
  return response.json();
}
```

### Articles API

```typescript
// GET /articles?limit=50
async function getArticles(limit: number = 50) {
  const response = await fetch(`${API_BASE}/articles?limit=${limit}`);
  return response.json();
}
```

---

## Cost Monitor

**File:** `context-owl-ui/src/pages/CostMonitor.tsx`

### Current Status

The Cost Monitor page is operational and wired to live admin API methods through `adminAPI`. It is not just a placeholder.

The component fetches:

```typescript
adminAPI.getCostSummary()
adminAPI.getDailyCosts(dailyDays)
adminAPI.getCostsByModel(30)
adminAPI.getCacheStats()
adminAPI.getProcessingStats(7)
adminAPI.clearExpiredCache()
```

### Polling / Refresh Behavior

The Cost Monitor uses TanStack React Query polling:

| Data | Query Key | Method | Refresh Interval |
|---|---|---|---|
| Cost summary | `['costSummary']` | `adminAPI.getCostSummary()` | 60 seconds |
| Daily costs | `['dailyCosts', dailyDays]` | `adminAPI.getDailyCosts(dailyDays)` | 5 minutes |
| Model costs | `['modelCosts']` | `adminAPI.getCostsByModel(30)` | 5 minutes |
| Cache stats | `['cacheStats']` | `adminAPI.getCacheStats()` | 60 seconds |
| Processing stats | `['processingStats']` | `adminAPI.getProcessingStats(7)` | 5 minutes |

The page also exposes a manual refresh button that invalidates all cost-related queries.

### Displayed Metrics

The Cost Monitor shows:

- Month-to-date production LLM spend
- Projected monthly production LLM spend
- Monthly savings compared with the historical `$92/mo` baseline
- Cache hit rate
- Daily cost trend over 7/14/30 days
- Cost by model
- Cache performance
- Processing distribution: LLM extraction vs regex extraction
- Cost by operation
- Clear-expired-cache action

### Data Source Expectations

Production LLM budget and spend metrics should be backed by `llm_traces` as the source of truth for budget enforcement and cost aggregation. Cost aggregation should use:

```javascript
{ timestamp: { $gte: cutoff } }
{ $sum: '$cost' }
```

Important field names:

- Use `timestamp`, not `created_at`
- Use `cost`, not `cost_usd`
- Use `operation` for operation breakdown
- Use `model` for model breakdown
- Use `cached` for cache hit/miss metrics

### Cost Monitor Is Not BugOps

Cost Monitor should continue to represent **production LLM usage**. BugOps should not be added here except perhaps as a link or high-level nav item.

BugOps needs a completely separate budget and trace store because incident investigation must still work when the production LLM circuit breaker is active.

---

## Planned BugOps Dashboard

### Purpose

BugOps is a separate operational dashboard for incident detection, investigation, audit trails, approvals, and agent observability.

It should answer:

- What is broken?
- What evidence has been collected?
- What did the agent inspect?
- What files were read?
- What commands/tools were run?
- What database queries were executed?
- What logs/traces were inspected?
- What model calls did the BugOps agent make?
- What did those calls cost?
- What action needs human approval?

### Core UI Pages

#### `/bugops`

Dashboard overview:

- Open cases
- Active alerts
- Service health
- Scheduled task freshness
- Production LLM circuit-breaker status
- BugOps LLM budget status
- Pending approvals

#### `/bugops/cases`

Case list:

- Case ID
- Title
- Severity
- Status
- Affected service
- First seen
- Last seen
- Alert count
- Current recommendation

#### `/bugops/cases/:caseId`

Case detail:

- Header: severity, status, affected service, current recommendation
- Timeline: case created, alerts grouped, tools run, files read, model calls, approvals
- Evidence: log samples, fingerprints, files read, commands run, DB queries, traces queried
- Agent report: facts, assumptions, hypotheses, confidence, recommended next checks
- Q&A: ask questions against the durable case state
- Approval panel: approve/reject/defer actions

#### `/bugops/traces`

Trace explorer:

- `case_id`
- `run_id`
- mode / operation
- model / provider
- prompt version
- tools allowed
- tools used
- files read count
- cost
- latency
- status

#### `/bugops/budget`

Separate BugOps budget:

- Today’s BugOps spend
- Spend by case
- Spend by operation
- Spend by model/provider
- Budget remaining
- Blocked BugOps calls
- Per-case cap usage

#### `/bugops/settings`

Operational settings:

- Slack webhook status
- Alert thresholds
- Deduplication window
- Read-only auto-investigation settings
- Approval rules by risk level
- BugOps LLM provider/model configuration
- BugOps budget limits

---

## BugOps Slack Integration

Slack should be the notification and quick-command layer, not the full UI.

### Slack Responsibilities

- Send alerts for new/high-severity cases
- Let the user ask quick questions
- Let the user trigger deeper read-only investigation
- Let the user approve/reject a proposed action
- Link to the full BugOps case UI

### Example Alert

```text
🚨 BugOps: Production LLM circuit-breaker active.
Case BUG-123 created. Initial read-only investigation started.

Likely impact:
All production LLM operations may be blocked.

Actions:
[Open Case] [Ask Why] [Run Deeper Investigation] [Silence 1h]
```

### Example Commands

```text
/bug list
/bug show BUG-123
/bug ask BUG-123 why is the circuit-breaker on?
/bug investigate BUG-123
/bug options BUG-123
/bug approve BUG-123 option-a
/bug reject BUG-123
/bug silence BUG-123 1h
```

---

## BugOps Runtime Model

BugOps should not be a continuously reasoning LLM loop.

The correct split is:

```text
Always-running monitor
→ detects anomalies and creates/updates cases
→ enqueues bounded investigation jobs
→ sends Slack notification

Event-triggered agent worker
→ wakes up for a specific case/job
→ performs read-only investigation within limits
→ records every tool call and model call
→ writes report
→ stops

Human approval layer
→ required for code/config/deploy/database changes
```

So BugOps can feel responsive without leaving an LLM agent running all day.

### Circuit-Breaker Example

If the production LLM circuit breaker is active:

1. The always-running monitor detects the condition through deterministic checks.
2. The monitor creates or updates a bug case.
3. The monitor enqueues an investigation job.
4. The monitor sends Slack alert.
5. The BugOps worker wakes up for that job.
6. The worker uses read-only tools to query production state.
7. If needed, the worker uses the separate BugOps LLM gateway and separate BugOps budget.
8. The worker writes a case report and stops.

The agent does not need to be always on. The monitor/queue is always available; the investigation worker runs only when triggered.

---

## Trace-First Investigation Reporting

Investigation reports should be generated from recorded traces and tool calls, not from the agent’s unsupported self-report.

### Required Trace Events

Every investigation should record:

- Files read
- Commands run
- Database queries executed
- Logs inspected
- Traces queried
- Services checked
- Model calls made
- Budget checks
- Slack commands/actions
- Approval decisions

### Example `bug_tool_calls` Document

```json
{
  "case_id": "BUG-123",
  "run_id": "RUN-456",
  "tool_name": "read_file",
  "target": "src/crypto_news_aggregator/services/cost_tracker.py",
  "reason": "Inspect budget cache and circuit-breaker logic",
  "risk_level": 1,
  "status": "success",
  "result_summary": "Found stale-cache degraded behavior and hard-limit checks",
  "started_at": "2026-05-03T18:00:00Z",
  "ended_at": "2026-05-03T18:00:01Z"
}
```

### Example `bug_agent_traces` Document

```json
{
  "case_id": "BUG-123",
  "run_id": "RUN-456",
  "mode": "root_cause_analysis",
  "operation": "bug_root_cause_analysis",
  "model": "deepseek/deepseek-chat",
  "provider": "openrouter",
  "prompt_version": "bug_rca_v1",
  "input_tokens": 2000,
  "output_tokens": 700,
  "cost": 0.002,
  "timestamp": "2026-05-03T18:00:05Z",
  "status": "success"
}
```

### Report Assembly Rule

The report should be assembled from:

```text
bug_case
+ bug_case_events
+ bug_tool_calls
+ bug_agent_traces
+ bug_alert_events
+ bug_approvals
+ log samples
→ investigation report
```

The UI should show the trace-derived audit trail directly.

---

## Component State Management

React components use hooks and React Query for state and side effects.

Existing simple pages may use `useState` and `useEffect` for fetch-on-mount behavior.

Cost Monitor uses React Query for:

- loading state
- error state
- background polling
- query invalidation
- mutation handling for clearing expired cache

BugOps pages should use React Query as well because operational data needs polling and reliable error/loading states.

Recommended BugOps polling:

| Page | Refresh Interval |
|---|---|
| `/bugops` | 30-60 seconds |
| `/bugops/cases` | 30-60 seconds |
| `/bugops/cases/:caseId` | 10-30 seconds while open/active, slower when resolved |
| `/bugops/traces` | 30-60 seconds |
| `/bugops/budget` | 60 seconds |

---

## API Configuration

**File:** `context-owl-ui/.env` or `context-owl-ui/src/config.ts`

```text
VITE_API_BASE=http://localhost:8000/api/v1
```

In code:

```typescript
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1';
```

BugOps endpoints should live under the same API base unless a separate admin/control-plane service is created:

```text
/api/v1/bugops/summary
/api/v1/bugops/cases
/api/v1/bugops/cases/{case_id}
/api/v1/bugops/traces
/api/v1/bugops/budget
/api/v1/bugops/settings
```

---

## Operational Checks

### Frontend Health

```bash
curl http://localhost:5173
```

Should return frontend HTML.

### Core API Connectivity

```bash
curl http://localhost:8000/api/v1/briefings/latest
curl http://localhost:8000/api/v1/signals
curl http://localhost:8000/api/v1/narratives
curl http://localhost:8000/api/v1/articles
```

### Cost Monitor API Connectivity

Check browser Network tab while opening `/cost-monitor`. Expected admin API calls include:

```text
getCostSummary
getDailyCosts
getCostsByModel
getCacheStats
getProcessingStats
```

If the page shows an error, verify the matching admin API routes are available and returning the shape expected by `CostMonitor.tsx`.

### Future BugOps API Connectivity

When BugOps is implemented:

```bash
curl http://localhost:8000/api/v1/bugops/summary
curl http://localhost:8000/api/v1/bugops/cases
curl http://localhost:8000/api/v1/bugops/budget
```

---

## Debugging

### Issue: Cost Monitor page fails to load

Possible causes:

- One of the admin API methods is missing or returning an unexpected shape
- Admin API route is not reachable from frontend
- CORS misconfiguration
- React Query receives an error from summary/daily/model/cache/processing endpoint

Verification:

- Open DevTools → Network
- Confirm which Cost Monitor request failed
- Check backend logs for the matching admin route
- Confirm API response keys match what `CostMonitor.tsx` expects

### Issue: Cost Monitor shows stale values

Possible causes:

- React Query cache not invalidated
- Backend aggregation stale
- `llm_traces` not receiving current writes
- Budget cache stale

Verification:

- Click refresh button in UI
- Query `llm_traces` directly for recent `timestamp`
- Confirm cost aggregation uses `timestamp` and `cost`

### Issue: BugOps alert appears, but UI has no case

Possible causes:

- Slack alert succeeded but case creation failed
- Case created in wrong database/collection
- UI API reads a different BugOps database than monitor writes
- Case is filtered out by status/severity filter

Verification:

- Search `bug_agent_cases` by case ID
- Check `bug_alert_events`
- Check BugOps API response
- Check Slack alert payload for `case_id`

### Issue: BugOps report claims a file was read, but trace does not show it

Expected behavior:

- Treat this as a bug.
- Reports must be generated from `bug_tool_calls`, not agent self-report.
- The UI should show trace-derived files read and commands run.

---

## Relevant Files

### Frontend Application

- `context-owl-ui/src/App.tsx` — Root app with route definitions
- `context-owl-ui/src/components/Layout.tsx` — Navigation sidebar and layout
- `context-owl-ui/src/pages/Briefing.tsx` — Briefing page component
- `context-owl-ui/src/pages/Signals.tsx` — Signals page component
- `context-owl-ui/src/pages/Narratives.tsx` — Narratives page component
- `context-owl-ui/src/pages/Articles.tsx` — Articles page component
- `context-owl-ui/src/pages/CostMonitor.tsx` — Operational production LLM cost dashboard

### Planned BugOps Frontend

- `context-owl-ui/src/pages/BugOpsDashboard.tsx`
- `context-owl-ui/src/pages/BugCaseList.tsx`
- `context-owl-ui/src/pages/BugCaseDetail.tsx`
- `context-owl-ui/src/pages/BugTraceExplorer.tsx`
- `context-owl-ui/src/pages/BugOpsBudget.tsx`
- `context-owl-ui/src/pages/BugOpsSettings.tsx`

### API Integration

- `context-owl-ui/src/api/client.ts` — API client initialization
- `context-owl-ui/src/api/briefing.ts` — Briefing API calls
- `context-owl-ui/src/api/signals.ts` — Signals API calls
- `context-owl-ui/src/api/narratives.ts` — Narratives API calls
- `context-owl-ui/src/api/articles.ts` — Articles API calls
- `context-owl-ui/src/api/admin.ts` or `context-owl-ui/src/api/index.ts` — Admin API calls used by Cost Monitor
- Planned: `context-owl-ui/src/api/bugops.ts` — BugOps API calls

### Backend API Endpoints

- `src/crypto_news_aggregator/api/v1/endpoints/briefing.py`
- `src/crypto_news_aggregator/api/v1/endpoints/signals.py`
- `src/crypto_news_aggregator/api/v1/endpoints/narratives.py`
- `src/crypto_news_aggregator/api/v1/endpoints/articles.py`
- Admin cost endpoints backing `CostMonitor.tsx`
- Planned: `src/crypto_news_aggregator/api/v1/endpoints/bugops.py`

### Cost / Budget Backend

- `src/crypto_news_aggregator/services/cost_tracker.py` — Production LLM budget/cache/cost tracking
- `src/crypto_news_aggregator/llm/gateway.py` — Production LLM gateway and trace writing
- Planned: BugOps budget manager/gateway/traces separate from production budget

### Configuration

- `context-owl-ui/.env` or `.env.local` — API endpoint URL
- `context-owl-ui/vite.config.ts` — Vite build configuration
- `context-owl-ui/tsconfig.json` — TypeScript configuration
- Backend CORS settings in `src/crypto_news_aggregator/main.py`

## Related Documentation

- **Architecture Overview (`00-overview.md`)** — System-wide perspective including frontend
- **Entrypoints (`10-entrypoints.md`)** — How frontend/server processes start
- **Scheduling (`20-scheduling.md`)** — Scheduled briefing behavior that BugOps should monitor
- **Data Model (`50-data-model.md`)** — Mongo collections frontend queries and BugOps may inspect
- **LLM (`60-llm.md`)** — Production LLM gateway, traces, budget, and circuit-breaker behavior

---

*Last updated: 2026-05-03*  
*Updated from: `70-frontend(3).md`, `CostMonitor.tsx`, and current BugOps architecture discussion*  
*Anchor: frontend-routes-api*
