---
name: jottit
description: Publish and manage Jottit pages from the terminal
---

# Jottit CLI

Jottit is a simple web publishing tool. Write markdown, get a beautiful page at a URL.

## Always use --json

When calling jottit commands, always pass `--json` for structured output. Parse the `breadcrumbs` array to discover next actions.

## Quick Reference

| Task | Command |
|------|---------|
| Publish a file | `jottit publish notes.md --json` |
| Publish from stdin | `echo "# Hello" \| jottit publish --json` |
| Publish as draft | `jottit publish notes.md --draft --json` |
| Publish private | `jottit publish notes.md --private --json` |
| Edit a page | `jottit edit my-slug --file updated.md --json` |
| List pages | `jottit list --json` |
| Delete a page | `jottit delete my-slug --yes --json` |
| Check auth | `jottit whoami --json` |

## Output Format

All `--json` output uses this envelope:

```json
{"ok": true, "data": {...}, "breadcrumbs": [{"label": "...", "command": "..."}]}
```

On error: `{"ok": false, "error": "message", "breadcrumbs": [...]}`

## Commands

### publish

```
jottit publish [FILE] [--slug SLUG] [--draft] [--private] [--listing listed|unlisted|pinned] [--title TITLE] [--open] [--json]
```

Publishes a new page. Reads content from FILE or stdin. If content has no `# heading` and `--title` is given, prepends it.

### edit

```
jottit edit SLUG [--file FILE] [--content TEXT] [--draft|--no-draft] [--listing listed|unlisted|pinned] [--json]
```

Updates an existing page. Content from `--file`, `--content`, or stdin. Can update metadata only with `--draft`/`--listing`.

### list

```
jottit list [--drafts] [--listing listed|unlisted|pinned] [--json]
```

Lists all your pages.

### delete

```
jottit delete SLUG --yes [--json]
```

Deletes a page. Always pass `--yes` to skip interactive confirmation.

## Authentication

The CLI reads tokens from `~/.jottitrc` or `JOTTIT_TOKEN` env var. If not authenticated, run `jottit login` first.

## Common Workflows

### Turn notes into a published page
```bash
jottit publish meeting-notes.md --json
```

### Update a page with new content
```bash
jottit edit my-page --file revised.md --json
```

### Pipe content directly
```bash
echo "# Quick Thought\n\nSomething worth sharing." | jottit publish --json
```

### Publish a draft, then make it live
```bash
jottit publish draft.md --draft --json
# later:
jottit edit the-slug --no-draft --json
```
