# Frontend Routes & React API Integration

## Overview

The frontend is a React SPA that serves the user interface, displays briefings and narratives, and integrates with the backend API. This document describes the React routing architecture, component structure, API endpoint integration, and debugging common frontend issues.

**Anchor:** `#frontend-routes-api`

## Architecture

### Key Components

- **React Router v7** - Client-side navigation without page reloads
- **BrowserRouter** - Enables browser history and URL management
- **Routes & Route Components** - Define page mappings
- **API Client** - Async functions for backend communication
- **State Management** - React hooks for component state and caching
- **Layout Navigation** - Sidebar navigation with active route highlighting

### Routes Overview

The application exposes five main routes served from a single-page entry point:

| Route | Component | Purpose | API Calls |
|-------|-----------|---------|-----------|
| `/` | Briefing | Display latest daily briefing | GET /briefings/latest |
| `/signals` | Signals | Show active market signals and alerts | GET /signals |
| `/narratives` | Narratives | Browse narrative threads | GET /narratives |
| `/articles` | Articles | View collected news articles | GET /articles |
| `/cost-monitor` | CostMonitor | Track LLM usage and costs | ⚠️ No live API endpoint — `get_usage_stats()` exists in `llm/tracking.py` as a Python function but is not exposed as an HTTP route. Cost Monitor UI is not yet backed by a real endpoint. TASK-069 will wire this up reading from `llm_traces`. |

## Implementation Details

### Route Configuration

**File:** `context-owl-ui/src/App.tsx:24-56`

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
- Routes are wrapped in `Layout` component for shared navigation
- No route guards currently; all routes publicly accessible
- Route paths match API endpoint patterns (kebab-case)

### Layout & Navigation

**File:** `context-owl-ui/src/components/Layout.tsx:16-69`

The Layout component provides navigation sidebar with route definitions:

```tsx
const navigationItems = [
  { path: '/', label: 'Briefing', icon: BookOpen },
  { path: '/signals', label: 'Signals', icon: TrendingUp },
  { path: '/narratives', label: 'Narratives', icon: Newspaper },
  { path: '/articles', label: 'Articles', icon: FileText },
  { path: '/cost-monitor', label: 'Cost Monitor', icon: DollarSign },
];

// Navigation rendering
navigationItems.map((item) => (
  <Link
    key={item.path}
    to={item.path}
    className={location.pathname === item.path ? 'active' : ''}
  >
    {/* icon and label */}
  </Link>
))
```

**Features:**
- Active route highlighting: Compares `location.pathname` to item.path
- Lucide React icons for visual navigation
- Click handler uses React Router's `Link` for client-side navigation
- No page reload on route change

### API Client Integration

**File:** `context-owl-ui/src/api/client.ts` (inferred pattern)

API calls are abstracted into service modules. Example endpoints:

**Briefing API:**
```typescript
// GET /briefings/latest
async function getLatestBriefing() {
  const response = await fetch(`${API_BASE}/briefings/latest`);
  return response.json();
}

// Returns: { _id, type, generated_at, content, metadata, is_smoke, task_id }
```

**Signals API:**
```typescript
// GET /signals?limit=50
async function getSignals(limit: number = 50) {
  const response = await fetch(`${API_BASE}/signals?limit=${limit}`);
  return response.json();
}

// Returns: [{ _id, title, score, entities, category, detected_at }, ...]
```

**Narratives API:**
```typescript
// GET /narratives?limit=30
async function getNarratives(limit: number = 30) {
  const response = await fetch(`${API_BASE}/narratives?limit=${limit}`);
  return response.json();
}

// Returns: [{ _id, title, description, entities, status, first_seen }, ...]
```

**Articles API:**
```typescript
// GET /articles?limit=50
async function getArticles(limit: number = 50) {
  const response = await fetch(`${API_BASE}/articles?limit=${limit}`);
  return response.json();
}

// Returns: [{ _id, title, content, source, published_at, sentiment }, ...]
```

**Cost Monitor API:**
```typescript
// ⚠️ GET /usage/stats does not exist as an HTTP route.
// get_usage_stats() is defined in llm/tracking.py but not wired to an API endpoint.
// Cost Monitor page has no live data source. TASK-069 will implement the endpoint
// reading from llm_traces collection (aggregate on "cost" field, query by "timestamp").
```

### Component State Management

**File:** `context-owl-ui/src/pages/Briefing.tsx` (example pattern)

React components use hooks for state and side effects:

```tsx
import { useState, useEffect } from 'react';

function Briefing() {
  const [briefing, setBriefing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function fetchBriefing() {
      try {
        setLoading(true);
        const data = await getLatestBriefing();
        setBriefing(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    fetchBriefing();
  }, []); // Fetch once on mount

  if (loading) return <div>Loading...</div>;
  if (error) return <div>Error: {error}</div>;
  if (!briefing) return <div>No briefing available</div>;

  return (
    <div>
      <h1>{briefing.type} Briefing</h1>
      <p>{briefing.content.narrative}</p>
      {/* Render insights, recommendations, etc */}
    </div>
  );
}
```

**Patterns:**
- `useState` for data, loading, error states
- `useEffect` for data fetching (empty dependency array = fetch once)
- Error handling with try/catch
- Loading UI while data fetches
- Conditional rendering based on state

### API Configuration

**File:** `context-owl-ui/.env` or `context-owl-ui/src/config.ts`

API endpoint is configured via environment variable:

```
VITE_API_BASE=http://localhost:8000/api/v1
```

In code:
```typescript
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000/api/v1';
```

**Note:** Must match backend API prefix configured in `src/crypto_news_aggregator/core/config.py:API_V1_STR`

## Operational Checks

### Health Verification

**Check 1: Frontend server is running**
```bash
# Navigate to frontend URL
curl http://localhost:5173
# Should return 200 with HTML content
```
*File reference:* `context-owl-ui/src/App.tsx:1-50`

**Check 2: React Router is initialized**
```bash
# In browser console, verify routes are defined
# Try navigating to each route
curl http://localhost:5173/ # Should load
curl http://localhost:5173/signals # Should load (same HTML, client-side routing)
curl http://localhost:5173/narratives # Should load
```

**Check 3: API connectivity from frontend**
```bash
# In browser console, test API call
fetch('http://localhost:8000/api/v1/briefings/latest')
  .then(r => r.json())
  .then(d => console.log(d))
# Should return briefing JSON without CORS errors
```

**Check 4: Navigation links work**
- Click "Briefing" link → URL becomes `/`, page updates without reload
- Click "Signals" link → URL becomes `/signals`, Signals component renders
- Active link is highlighted (usually bold or different color)

### API Endpoint Verification

**Briefing endpoint working:**
```bash
curl http://localhost:8000/api/v1/briefings/latest
# Returns: { _id, type, generated_at, content.narrative, metadata, ... }
```
*File reference:* `src/crypto_news_aggregator/api/v1/endpoints/briefing.py:27` (router definition)

**Signals endpoint working:**
```bash
curl http://localhost:8000/api/v1/signals
# Returns: [{ _id, title, score, ... }, ...]
```
*File reference:* `src/crypto_news_aggregator/api/v1/endpoints/signals.py:18` (router definition)

**Narratives endpoint working:**
```bash
curl http://localhost:8000/api/v1/narratives
# Returns: [{ _id, title, entities, ... }, ...]
```
*File reference:* `src/crypto_news_aggregator/api/v1/endpoints/narratives.py:21` (router definition)

**Articles endpoint working:**
```bash
curl http://localhost:8000/api/v1/articles
# Returns: [{ _id, title, source, ... }, ...]
```
*File reference:* `src/crypto_news_aggregator/api/v1/endpoints/articles.py:15` (router definition)

## Debugging

**Issue:** Page loads but shows "Loading..." forever
- **Root cause:** API call fails silently, or response is wrong format
- **Verification:** Open browser DevTools → Network tab, reload page
  - Check if requests are sent to correct URL
  - Check response status (404 = endpoint missing, 500 = server error, CORS error = config issue)
- **Fix:** Verify API_BASE environment variable matches backend URL
  - Frontend: `VITE_API_BASE=http://localhost:8000/api/v1`
  - Backend: `API_V1_STR=/api/v1` in config.py
  *Reference:* `context-owl-ui/src/api/client.ts` (API client initialization)

**Issue:** Navigation links don't work (page doesn't update)
- **Root cause:** React Router not initialized or BrowserRouter missing
- **Verification:** Check browser console for errors; verify URL changes
- **Fix:** Ensure App.tsx wraps Routes in BrowserRouter (line 24)
  *Reference:* `context-owl-ui/src/App.tsx:24-56` (BrowserRouter setup)

**Issue:** Signals page loads but shows no data
- **Root cause:** API returns empty array, or component doesn't render empty state
- **Verification:** Check API response: `curl http://localhost:8000/api/v1/signals`
  - If returns `[]`, check if signals exist in database
  - If returns 500 error, check backend logs
- **Fix:** Verify signals were generated:
  - Check MongoDB: `db.signals.count()` should be > 0
  - Check API endpoint is working: `curl http://localhost:8000/api/v1/signals`
  *Reference:* `src/crypto_news_aggregator/api/v1/endpoints/signals.py:18-100` (endpoint implementation)

**Issue:** CORS error when frontend tries to call API
- **Root cause:** Backend CORS policy doesn't allow frontend origin
- **Verification:** Check browser console for "Access-Control-Allow-Origin" errors
- **Fix:** Verify CORS configuration in backend:
  - Check `src/crypto_news_aggregator/main.py` has CORSMiddleware configured
  - Verify `CORS_ORIGINS` includes frontend URL (e.g., `http://localhost:5173`)
  *Reference:* `src/crypto_news_aggregator/main.py:100-130` (CORS setup)

**Issue:** Briefing page shows stale data (old briefing)
- **Root cause:** Component doesn't refresh on API data change, or cache is stale
- **Verification:** Check database: `db.daily_briefings.findOne({}, {generated_at:1}).sort({generated_at:-1})`
  - Compare timestamp to what's shown on page
  - If DB has new briefing but page shows old one, it's a caching issue
- **Fix:** Clear browser cache or add timestamp to API call:
  - `fetch(url + '?t=' + Date.now())` to bypass HTTP cache
  - Or implement React hook for periodic polling: `setInterval(fetchBriefing, 60000)`
  *Reference:* `context-owl-ui/src/pages/Briefing.tsx` (component fetch logic)

## Relevant Files

### Frontend Application
- `context-owl-ui/src/App.tsx` - Root app with route definitions
- `context-owl-ui/src/components/Layout.tsx` - Navigation sidebar and layout
- `context-owl-ui/src/pages/Briefing.tsx` - Briefing page component
- `context-owl-ui/src/pages/Signals.tsx` - Signals page component
- `context-owl-ui/src/pages/Narratives.tsx` - Narratives page component
- `context-owl-ui/src/pages/Articles.tsx` - Articles page component
- `context-owl-ui/src/pages/CostMonitor.tsx` - Cost tracking page

### API Integration
- `context-owl-ui/src/api/client.ts` - API client initialization
- `context-owl-ui/src/api/briefing.ts` - Briefing API calls
- `context-owl-ui/src/api/signals.ts` - Signals API calls
- `context-owl-ui/src/api/narratives.ts` - Narratives API calls
- `context-owl-ui/src/api/articles.ts` - Articles API calls

### Configuration
- `context-owl-ui/.env` or `context-owl-ui/.env.local` - API endpoint URL
- `context-owl-ui/vite.config.ts` - Vite build configuration
- `context-owl-ui/tsconfig.json` - TypeScript configuration

### Backend API Endpoints
- `src/crypto_news_aggregator/api/v1/endpoints/briefing.py` - GET /briefings/latest
- `src/crypto_news_aggregator/api/v1/endpoints/signals.py` - GET /signals
- `src/crypto_news_aggregator/api/v1/endpoints/narratives.py` - GET /narratives
- `src/crypto_news_aggregator/api/v1/endpoints/articles.py` - GET /articles

### CORS & Security
- `src/crypto_news_aggregator/main.py` - CORS middleware configuration
- `src/crypto_news_aggregator/core/config.py` - CORS_ORIGINS setting

## Related Documentation
- **Architecture Overview (00-overview.md)** - System-wide perspective including frontend
- **Entrypoints (10-entrypoints.md)** - How frontend server starts
- **Data Model (50-data-model.md)** - MongoDB collections frontend queries
- **Scheduling (20-scheduling.md)** - When briefings are generated (frontend polling shows latest)

---
*Last updated: 2026-04-25* | *Generated from: 10-frontend-routes.txt* | *Anchor: frontend-routes-api*