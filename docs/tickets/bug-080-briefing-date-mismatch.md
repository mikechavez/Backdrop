---
id: BUG-080
type: bug
status: complete
priority: high
severity: high
created: 2026-04-15
updated: 2026-04-15
resolved: 2026-04-15
---

# Briefing date mismatch: prompt says April 15, header says April 14

## Problem
The evening briefing generated on April 14 at 6:00 PM CST contains the sentence "Crypto markets experienced a severe contraction on April 15, 2026." The frontend header correctly shows "Tuesday, April 14, 2026 · 6:00 PM CST." The LLM is writing about the wrong date because it receives the wrong date in its prompt.

## Expected Behavior
The date in the LLM prompt should match the date displayed in the frontend header. An evening briefing rendered as April 14 CST should tell the LLM it is April 14.

## Actual Behavior
`briefing_agent.py` computes `now = datetime.now(timezone.utc)` at generation time (line 116). For a 6:00 PM CST briefing, UTC is 00:00 the next day. `_build_generation_prompt()` formats this UTC timestamp directly (line 563), so the prompt says "April 15" while the frontend (which uses the browser's local timezone via `Intl.DateTimeFormat`) shows "April 14."

## Steps to Reproduce
1. Observe any evening briefing generated at 6:00 PM CST (= 00:00 UTC next day)
2. Compare the date in the narrative text vs. the date in the frontend header
3. They will always disagree by one day for evening briefings

## Environment
- Environment: production
- User impact: high — every evening briefing has the wrong date in its narrative

---

## Resolution

**Status:** ✅ COMPLETE — 2026-04-15

### Root Cause
`_build_generation_prompt()` formats `generated_at` (which is UTC) directly with `strftime`, producing the UTC date. The frontend renders in the browser's local timezone. For evening briefings near midnight UTC, these disagree.

### Changes Made

**File: `crypto_news_aggregator/services/briefing_agent.py`**

**Change 1 — Add import (after line 18)**

Find:
```python
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
```

Replace with:
```python
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from zoneinfo import ZoneInfo
```

**Change 2 — Add display timezone constant (after line 54)**

Find:
```python
BRIEFING_PRIMARY_MODEL = "claude-haiku-4-5-20251001"
BRIEFING_FALLBACK_MODEL = "claude-sonnet-4-5-20250929"
```

Replace with:
```python
BRIEFING_PRIMARY_MODEL = "claude-haiku-4-5-20251001"
BRIEFING_FALLBACK_MODEL = "claude-sonnet-4-5-20250929"

# Display timezone for briefing date context in LLM prompt.
# Must match the timezone used by the frontend schedule (CST/CDT).
BRIEFING_DISPLAY_TZ = ZoneInfo("America/Chicago")
```

**Change 3 — Convert to display timezone before formatting (line 563)**

Find:
```python
        # Time context
        time_str = briefing_input.generated_at.strftime("%A, %B %d, %Y")
        parts.append(f"Generate the {briefing_input.briefing_type} crypto briefing for {time_str}.\n")
```

Replace with:
```python
        # Time context — convert UTC to display timezone so prompt date matches frontend header
        display_time = briefing_input.generated_at.astimezone(BRIEFING_DISPLAY_TZ)
        time_str = display_time.strftime("%A, %B %d, %Y")
        parts.append(f"Generate the {briefing_input.briefing_type} crypto briefing for {time_str}.\n")
```

### Testing
1. Unit test: call `_build_generation_prompt()` with `generated_at = datetime(2026, 4, 15, 0, 0, tzinfo=timezone.utc)` (midnight UTC = 7 PM CDT April 14). Verify the prompt string contains "Tuesday, April 14, 2026", not April 15.
2. Unit test: call with `generated_at = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)` (2 PM UTC = 9 AM CDT April 15). Verify the prompt contains "Tuesday, April 15, 2026".
3. Production: trigger a test evening briefing and confirm the narrative date matches the header date.

### Files Changed
- `crypto_news_aggregator/services/briefing_agent.py` (import + constant + timezone conversion)
- `tests/services/test_briefing_prompts.py` (2 new unit tests)

### Commit
- **Branch:** `fix/bug-080-briefing-date-mismatch`
- **Commit:** 13d0ecc (fix(briefing): Convert UTC timestamp to display timezone in LLM prompt)
- **Validation:** All 5 briefing prompt tests pass ✅