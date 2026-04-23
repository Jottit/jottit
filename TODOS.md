# TODOS

## /export hardening

**What:** Add rate limit, size cap, and a README.md member to the bulk-export zip.

**Why:** Currently `routes/site.py:549-575` builds the entire zip in memory via `io.BytesIO()` + `buf.getvalue()`, has no rate limit, no size cap, and no README explaining filename conventions or the external-image-URL limitation. At current scale (a few MB per user) this is fine; at pathological input it could OOM a gunicorn worker.

**Pros:**
- Protects against a stuffed-account export OOMing a worker.
- Gives users context about what's in the zip and how to use it.
- Flask-Limiter is already wired (see `routes/admin.py:289`), so rate limiting is a one-line decorator.

**Cons:**
- Not urgent. No user has hit this.
- Adds 30-ish lines and a new failure mode (exports can now partially truncate).

**Context:** Reviewed 2026-04-23. Discussed extracting a `build_markdown_zip(pages, filename_base)` helper so per-page export and bulk export share zip-building logic; decided to defer until someone asks for it. When picking this up, do the helper extraction at the same time — otherwise the hardening lives in only one of two near-identical code paths.

**Depends on / blocked by:** None. Can ship standalone. Pairs naturally with the `get_export_pages` rename below (same touch area).

**Files:** `routes/site.py:523-575`, `db.py:470-497`.

---

## Rename `get_export_pages` to `get_export_page` (singular)

**What:** Rename `get_export_pages(page_id)` in `db.py:470` to `get_export_page(page_id)`. Make it return a single row instead of a list. Simplify the caller at `routes/site.py:535` accordingly.

**Why:** Today the function is plural-named but returns at most one row. The caller does `for p in pages:` and writes `f"{slug}.md"` using the outer `slug` variable. If anyone refactors the query to return multiple rows (e.g., revision history export), every row silently overwrites the same filename. That's a quiet data-loss trap.

**Pros:**
- Makes the shape honest.
- Removes a latent refactor trap.

**Cons:**
- Touches a stable helper. Minor risk of breaking anything that calls it.

**Context:** Flagged during the 2026-04-23 `/plan-eng-review`. Safe today because `get_export_pages` is only called from one place. Grep before renaming.

**Depends on / blocked by:** None. Do this alongside the /export hardening above to minimize touches.

**Files:** `db.py:470-479`, `routes/site.py:523-547`.

---

## Custom domains (separate design session needed)

**What:** Decide whether Jottit supports custom domains, and if so, how.

**Why:** Custom domains force a business-model decision (paid tier vs. self-hosting-only vs. free-but-absorbed-cost). The April 22 identity doc says "Jottit isn't a business," which rules out a paid tier without a rewrite. The 2026-04-23 office-hours session explicitly dropped custom domains from the "Truly Portable" bundle because that business-model question wasn't ready to be answered.

**Pros:** Custom domains are the strongest "truly owned" indieweb signal.

**Cons:** Every commercial option (Cloudflare for SaaS, ACME for every domain, etc.) scales cost per user. Self-hosting-only keeps Jottit.org pure OSS but requires making Jottit actually self-hostable.

**Context:** Deferred from 2026-04-23 bundle. Needs a dedicated `/office-hours` session about business model before any engineering happens.

**Depends on / blocked by:** Business-model decision.

**Files:** N/A — pre-design.
