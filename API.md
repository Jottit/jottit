# Jottit API

Base URL: `/api/v1`

## Authentication

All endpoints require a Bearer token in the `Authorization` header:

```
Authorization: Bearer jot_your_token_here
```

Create tokens from **Settings > API tokens** in the web UI. Tokens are shown once at creation — store them securely.

## Source Tracking

Every write records how it arrived. Set the `X-Jottit-Source` header to `mcp` for MCP-originated requests. Without the header, writes are recorded as `api`. Web UI writes are recorded as `web`.

## AI Assisted Flag

Pass `"ai_assisted": true` on create or update to mark a revision as AI-assisted. Defaults to `false`. Returned in revision responses.

## Errors

All errors return JSON:

```json
{"error": "Error message"}
```

Status codes: 400 (bad request), 401 (unauthorized), 404 (not found), 429 (rate limited).

## Endpoints

### User

#### `GET /api/v1/user`

Returns the authenticated user's profile.

```json
{
  "username": "simon",
  "name": "Simon",
  "bio": "Writer",
  "avatar": "https://..."
}
```

#### `GET /api/v1/users/:username`

Returns a public user profile and their listed/pinned pages.

```json
{
  "username": "simon",
  "name": "Simon",
  "bio": "Writer",
  "avatar": "https://...",
  "pages": [
    {
      "slug": "hello",
      "title": "Hello World",
      "draft": false,
      "listing": "listed",
      "updated_at": "2026-03-21T12:00:00+00:00"
    }
  ]
}
```

### Pages

#### `GET /api/v1/pages`

Lists all pages for the authenticated user.

```json
{
  "pages": [
    {
      "slug": "hello",
      "title": "Hello World",
      "draft": false,
      "listing": "listed",
      "updated_at": "2026-03-21T12:00:00+00:00"
    }
  ]
}
```

#### `POST /api/v1/pages`

Creates a new page. Returns 201.

Request:

```json
{
  "content": "# Hello World\n\nThis is my page.",
  "slug": "hello",
  "draft": false,
  "listing": "listed",
  "ai_assisted": false
}
```

- `content` (required): Full markdown including `# Title` line.
- `slug` (optional): Defaults to slugified title, or a random slug.
- `draft` (optional): Defaults to `false`.
- `listing` (optional): `"listed"`, `"unlisted"`, or `"pinned"`. Defaults to `"listed"`.
- `ai_assisted` (optional): Defaults to `false`.

Response:

```json
{
  "slug": "hello",
  "title": "Hello World",
  "content": "# Hello World\n\nThis is my page.",
  "draft": false,
  "listing": "listed",
  "updated_at": "2026-03-21T12:00:00+00:00"
}
```

#### `GET /api/v1/pages/:slug`

Returns a single page.

```json
{
  "slug": "hello",
  "title": "Hello World",
  "content": "# Hello World\n\nThis is my page.",
  "draft": false,
  "listing": "listed",
  "updated_at": "2026-03-21T12:00:00+00:00"
}
```

#### `PUT /api/v1/pages/:slug`

Updates an existing page.

Request:

```json
{
  "content": "# Hello World\n\nUpdated content.",
  "draft": false,
  "listing": "pinned",
  "ai_assisted": true
}
```

All fields are optional. Omitted fields keep their current values (except `ai_assisted`, which defaults to `false` per revision).

#### `DELETE /api/v1/pages/:slug`

Deletes a page. Returns:

```json
{"ok": true}
```

### Revisions

#### `GET /api/v1/pages/:slug/revisions`

Lists revisions for a page, newest first.

Query params:
- `page` (default 1)
- `per_page` (default 20, max 100)

```json
{
  "revisions": [
    {
      "revision": 2,
      "created_at": "2026-03-21T12:00:00+00:00",
      "word_count": 42,
      "source": "api",
      "ai_assisted": false
    }
  ],
  "page": 1,
  "total_pages": 1
}
```
