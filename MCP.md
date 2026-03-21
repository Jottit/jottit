# Jottit MCP Server

An MCP server that exposes Jottit's API as tools for Claude Desktop, Claude Code, and other MCP clients.

## Setup

1. Create an API token at **Settings > API tokens** on your Jottit site.

2. Install the server:

```
cd mcp-server
pip install .
```

3. Add to your MCP client config:

```json
{
  "mcpServers": {
    "jottit": {
      "command": "jottit-mcp",
      "env": {
        "JOTTIT_API_TOKEN": "your_token_here"
      }
    }
  }
}
```

For local development, also set `JOTTIT_BASE_URL`:

```json
{
  "mcpServers": {
    "jottit": {
      "command": "jottit-mcp",
      "env": {
        "JOTTIT_API_TOKEN": "your_token_here",
        "JOTTIT_BASE_URL": "http://localhost:8000"
      }
    }
  }
}
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JOTTIT_API_TOKEN` | (required) | API token from Settings > API tokens |
| `JOTTIT_BASE_URL` | `https://jottit.org` | Base URL of the Jottit instance |

## Tools

### `get_page`
Get a page by its slug. Returns title, content (markdown), draft status, listing, and last updated timestamp.
- `slug` (string, required)

### `list_pages`
List all pages owned by the authenticated user.

### `create_page`
Create a new page. Content should be markdown starting with `# Title`. Automatically marks the revision as AI-assisted.
- `content` (string, required): Full markdown including `# Title` line
- `slug` (string, optional): Auto-generated from title if omitted
- `draft` (bool, optional): Defaults to `false`
- `listing` (string, optional): `"listed"`, `"unlisted"`, or `"pinned"`. Defaults to `"listed"`

### `update_page`
Update an existing page. Only provided fields are changed. Automatically marks the revision as AI-assisted.
- `slug` (string, required): Page to update
- `content` (string, optional): Full markdown including `# Title` line
- `draft` (bool, optional)
- `listing` (string, optional)

### `delete_page`
Permanently delete a page. Cannot be undone.
- `slug` (string, required)

### `get_revisions`
List revision history for a page, newest first.
- `slug` (string, required)
- `page` (int, optional): Page number, defaults to 1
- `per_page` (int, optional): Results per page, defaults to 20 (max 100)

### `get_user_profile`
Get a user's public profile and their listed/pinned pages.
- `username` (string, required)

## Source Tracking

All writes through the MCP server are automatically tagged with `source: mcp` and `ai_assisted: true` in the revision history.
