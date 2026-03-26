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
| Publish private | `jottit publish notes.md --visibility private --json` |
| Publish unlisted | `jottit publish notes.md --visibility unlisted --json` |
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
jottit publish [FILE] [--slug SLUG] [--visibility private|unlisted|listed|pinned] [--title TITLE] [--open] [--json]
```

Publishes a new page. Reads content from FILE or stdin. If content has no `# heading` and `--title` is given, prepends it. Default visibility is `private`.

### edit

```
jottit edit SLUG [--file FILE] [--content TEXT] [--visibility private|unlisted|listed|pinned] [--json]
```

Updates an existing page. Content from `--file`, `--content`, or stdin. Can update metadata only with `--visibility`.

### list

```
jottit list [--visibility private|unlisted|listed|pinned] [--json]
```

Lists all your pages. Optionally filter by visibility.

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

### Publish private, then make it public
```bash
jottit publish draft.md --visibility private --json
# later:
jottit edit the-slug --visibility listed --json
```
