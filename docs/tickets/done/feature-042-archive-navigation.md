---
id: FEATURE-042
type: feature
status: backlog
priority: low
complexity: low
created: 2026-02-09
updated: 2026-02-09
sprint: Sprint 8
---

# Archive Legacy Docs & Create Navigation

## Problem/Opportunity
After extracting context (FEATURE-041A/B), legacy docs are no longer the source of truth but still have historical value. We need to:
1. Move them to an archive location with clear dating
2. Add banners explaining they're archived
3. Create navigation to help developers find the right docs

This is final cleanup and can be deferred to Sprint 9 without blocking other work.

## Proposed Solution
1. Move legacy docs to `docs/decisions/` with date suffixes
2. Add archive banners (from FEATURE-041B)
3. Create main `docs/README.md` with "which doc to trust" rules
4. Create `docs/_generated/README.md` with regeneration instructions
5. Update any code comments pointing to old doc locations

## User Story
As a developer browsing the repo, I want clear guidance on which docs are current vs historical, so I don't waste time reading outdated information or get confused by contradictory sources.

## Acceptance Criteria

### File Moves
- [ ] Legacy docs moved to `docs/decisions/` with date suffixes:
  - `background-workers.md` → `background-workers-2025-02.md`
  - `news-fetching-architecture.md` → `news-fetching-architecture-2025-02.md`
  - `backend-service-patterns.md` → `backend-service-patterns-2025-02.md`
  - `frontend-architecture.md` → `frontend-architecture-2025-02.md`
  - `technical overview.md` → `technical-overview-2025-02.md`
- [ ] Any other markdown docs in repo root/docs moved appropriately
- [ ] Git history preserved (use `git mv`)

### Archive Banners
- [ ] Each archived doc has banner at top (from FEATURE-041B)
- [ ] Banner includes:
  - Archive date
  - "What changed" summary (if contradictions exist)
  - Links to current system docs
- [ ] Standard banner template:
  ```markdown
  > **ARCHIVED (2026-02-09):** This document is preserved for historical context. The system may have evolved since this was written. For current information, see `docs/_generated/system/`
  >
  > **Key changes since this doc:**
  > - [Change 1]
  > - [Change 2]
  ```

### Navigation - Main README
- [ ] Create `docs/README.md`
- [ ] Includes "Which doc to trust" hierarchy:
  1. `_generated/system/` is current truth (code-derived)
  2. `_generated/context/` is rationale/history (curated)
  3. `decisions/` is immutable legacy reference
  4. When in doubt: **code > system docs > context docs > decisions**
- [ ] Lists all system modules with brief descriptions
- [ ] Links to regeneration instructions
- [ ] Navigation structure:
  ```markdown
  # Backdrop Documentation
  
  ## Quick Navigation
  - **Understanding the system:** Start with `_generated/system/00-overview.md`
  - **Debugging production:** Check `_generated/system/20-scheduling.md`, `50-data-model.md`, `60-llm.md`
  - **Understanding decisions:** See `_generated/context/` for rationale
  - **Historical reference:** See `decisions/` for archived docs
  
  ## Which doc to trust
  1. **_generated/system/** - Current truth (code-derived, regenerable)
  2. **_generated/context/** - Why/history (curated, links to system)
  3. **decisions/** - Historical docs (immutable, dated)
  4. **When in doubt:** code > system > context > decisions
  
  ## System Modules
  [List of all modules with descriptions]
  
  ## Regenerating docs
  See `_generated/README.md` for instructions.
  ```

### Navigation - Generated README
- [ ] Create `docs/_generated/README.md`
- [ ] Explains regeneration workflow:
  1. Run `scripts/generate-evidence.sh`
  2. Use Claude Code to regenerate system docs
  3. Update context docs manually (if code changed)
  4. Validate with `scripts/validate-docs.sh`
- [ ] Includes example prompts for each module
- [ ] Warns: "Never edit system docs by hand - regenerate instead"

### Code Reference Updates
- [ ] Search codebase for references to old doc paths:
  ```bash
  rg "docs/background-workers" --type py
  rg "docs/news-fetching" --type py
  ```
- [ ] Update comments to point to new locations
- [ ] Prefer linking to system docs over archived docs

## Deliverables
1. Archived docs in `docs/decisions/` with date suffixes and banners
2. `docs/README.md` (main navigation)
3. `docs/_generated/README.md` (regeneration guide)
4. Updated code comments (if any existed)
5. Clean repo structure with clear doc hierarchy

## Token Budget
- Generate README content: ~8K tokens
- Review and update code comments: ~3K tokens
- Validation: ~2K tokens

**Total: ~13K tokens** (mostly mechanical work)

## Dependencies
- FEATURE-041B (provides archive banners)

## Open Questions
- [ ] Should we keep technical overview diagram in archive or move to 00-overview.md? → Move to 00-overview.md (hybrid doc)
- [ ] Any docs to permanently delete instead of archive? → No, preserve all
- [ ] Should decisions/ be gitignored or committed? → Committed (historical reference)

## Implementation Notes
<!-- Fill in during development -->

### File Move Commands
```bash
# Create decisions directory
mkdir -p docs/decisions

# Move legacy docs (preserving git history)
git mv docs/background-workers.md docs/decisions/background-workers-2025-02.md
git mv docs/news-fetching-architecture.md docs/decisions/news-fetching-architecture-2025-02.md
git mv docs/backend-service-patterns.md docs/decisions/backend-service-patterns-2025-02.md
git mv docs/frontend-architecture.md docs/decisions/frontend-architecture-2025-02.md
git mv "docs/technical overview.md" docs/decisions/technical-overview-2025-02.md

# Add CLAUDE.md to decisions if exists
git mv docs/CLAUDE.md docs/decisions/CLAUDE-2025-02.md
```

### Adding Banners
Prepend to each file using `str_replace` or manual edit:
```markdown
> **ARCHIVED (2026-02-09):** This document is preserved for historical context. For current information, see `docs/_generated/system/`
>
> **Key changes:**
> - [From FEATURE-041B archive notes]

---

[Original content...]
```

### README Structure
Both READMEs should be concise (≤1 page each):
- Main README: Navigation + trust hierarchy
- Generated README: How to regenerate + validation

## Completion Summary
<!-- Fill in after completion -->
- Actual complexity:
- Docs archived:
- Code references updated:
- Final documentation structure: