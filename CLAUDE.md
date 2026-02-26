# CLAUDE.md — Jottit

## What is Jottit?

Jottit is a radically simple web publishing tool. You go to jottit.org, write something in markdown, and get a beautiful page with a shareable URL. That's it.

The original Jottit was co-created by Simon Carstensen and Aaron Swartz in 2007, funded by Paul Graham ($75k, YC first batch 2005). It was a wiki-style tool where you could instantly create and edit web pages. The 2026 version is a spiritual successor — simpler than the original, with dramatically better typography and design.

Jottit is a page, not a blog platform. Jottit is open source.

## Design Philosophy

### What Jottit is
- One interaction: write → publish → share URL
- Beautiful typographic output (Medium-quality reading experience, serif font, generous whitespace, drop caps, perfect reading width)
- Markdown in, beautiful page out
- No accounts required to create a page
- No JavaScript on public pages
- Opinionated design — the design is so good you don't need to change it

### What Jottit is NOT
- A blogging platform
- A CMS
- A wiki
- A site builder

## Stack

- Flask + Jinja2 (server-side rendered)
- Vanilla JS (editor only — no JS on published pages)
- Vanilla CSS
- PostgreSQL (production), SQLite (development)

## Product Spec (v1)

### Homepage
```
                                          sign in
Jottit
[Create a page]
[tagline]
```

"Create a page" takes you directly to the editor at `jottit.org/[random-slug]/edit`. No intermediate steps.

"sign in" in the top right corner. After signing in, it becomes "settings".

### Editor
- Full-screen split preview: markdown on the left, rendered output on the right
- Pre-filled random slug, editable: "Your page will be at: jottit.org/[a7x3k]"
- Publish button
- That's it

### Published Page
- Just the content. Full width, beautiful typography
- No Jottit UI on user pages — no sign in link, no settings, no navigation
- "powered by Jottit" in the footer
- "last edited [timestamp]" with a link to revision history
- The first `# heading` in the markdown becomes the page title (no separate title field)

### Settings
- Accessible from jottit.org after signing in ("settings" link replaces "sign in" in top right)
- Public/private toggle
- Slug change
- Not a dashboard — one simple page

### Auth & Ownership
- No account required to create a page — zero friction
- Unclaimed pages show a "Claim this page" banner
- Claiming: enter your email, receive a 6-digit code, enter the code. Page is yours.
- Every sign-in uses the same flow: email → code. No passwords.
- Once claimed: sign-in required to edit
- Unclaimed pages are editable by anyone with the URL

### Visibility
- Two states: **public** (anyone can view, passcode to edit) and **private** (passcode to view and edit)
- Simple toggle, not a settings page

### Revision History
- Invisible complexity — just a git log under the hood
- Simple "last edited" timestamp that links to revision history
- Diff view between versions

### What's explicitly excluded from v1
- Subdomains (subdomains → sites → pages → navigation → settings → accounts → CMS)
- Multiple pages per site
- Site title / site description
- Images (text only — images mean hosting, storage, uploads, CDN)
- Design/theme settings (the design IS the design)
- Wiki editing mode
- Custom domains
- Accounts / sign-up

### Future considerations (only if people ask for them)
- Subdomains and multiple pages (turns Jottit into a minimal site, not just a page)
- Site title + subdomain + menu = a very minimal site
- Sign-in link (top right, tiny and quiet)
- Settings page (subdomain change, public/private toggle, recovery email)
- Navigation (if pages are added: simple list of page titles at the bottom, no sidebar)
- Images

## Architecture

- No JavaScript on public pages
- Markdown rendering to clean HTML
- Static output where possible
- Git-backed storage for revision history
- Clean, minimal URL structure: `jottit.org/[slug]`

## Commands

- `flask run --debug` — dev server with auto-reload
- `pytest` — run tests
- Commits: one-line messages only, no co-authored-by trailers

## Code Style

- Python: simple, readable, no clever abstractions
- HTML: semantic, minimal classes
- CSS: reuse existing classes and variables before adding new ones. Check what's already defined in stylesheets first. Never use inline styles — always use classes. Never use hardcoded color values — always use design tokens (CSS custom properties).
- JS: vanilla only, no build step, no frameworks. Editor page only — no JS on published pages.
- Keep files small and focused
- Prefer explicit over clever
- Don't swallow errors — let exceptions propagate in development
- Don't add unused imports or reorganize existing ones
- Don't add comments that restate what the code does
- Do only what was asked — no bonus features, no "while I'm at it" additions

## Testing

- Always add tests when implementing new features
- Bug fixes: write a failing test first, then fix the bug, then verify the test passes
- Cover the happy path and obvious edge cases, don't over-test

## Don't

- Add features without discussing the tradeoff
- Introduce dependencies without justification
- Build dashboards or admin UIs
- Over-engineer — this is a simple app, keep it that way

## Relationship to Original Jottit (2007)

Features from the original and their status:

| Original Feature | 2026 Status |
|---|---|
| Homepage textarea | **Replaced** — "Create a page" button instead |
| Split preview editor | **Keep** — simplest honest solution for markdown |
| Subdomains (yourname.jottit.com) | **Skip for v1** |
| Multiple pages with sidebar | **Skip for v1** |
| Wiki editing mode (anyone can edit) | **Drop** — spam, moderation complexity |
| Private/Public/Open modes | **Simplify** to Private/Public only |
| Revision history with diffs | **Keep** — hidden complexity |
| Site title, subtitle, description | **Drop** — first heading is the title |
| Design/theme settings | **Drop** — opinionated design |
| Claim this site flow | **Keep** — zero-friction creation, claim when ready |
| Custom site address | **Drop for v1** |
| Atom export | **Maybe later** |

## Key Reference

The target reading experience for published pages is Medium's article typography: serif font, generous line height, proper reading width, drop caps, lots of whitespace — but with zero UI chrome around it.
