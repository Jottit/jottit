import json
import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Jottit")

BASE_URL = os.environ.get("JOTTIT_BASE_URL", "https://jottit.org")
API_TOKEN = os.environ.get("JOTTIT_API_TOKEN", "")

WRITE_HEADERS = {"X-Jottit-Source": "mcp"}


def _client():
    return httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        timeout=30,
    )


def _format_response(resp):
    is_json = "application/json" in resp.headers.get("content-type", "")
    if resp.status_code >= 400:
        if is_json:
            return f"Error {resp.status_code}: {resp.json().get('error', resp.text)}"
        return f"Error {resp.status_code}: {resp.text}"
    return json.dumps(resp.json(), indent=2)


@mcp.tool()
def get_page(slug: str) -> str:
    """Get a Jottit page by its slug. Returns the page's title, content (markdown), draft status, listing, and last updated timestamp."""
    with _client() as client:
        resp = client.get(f"/api/v1/pages/{slug}")
    return _format_response(resp)


@mcp.tool()
def list_pages() -> str:
    """List all pages owned by the authenticated user. Returns each page's slug, title, draft status, listing, and last updated timestamp."""
    with _client() as client:
        resp = client.get("/api/v1/pages")
    return _format_response(resp)


@mcp.tool()
def create_page(
    content: str,
    slug: str = "",
    draft: bool = False,
    listing: str = "listed",
) -> str:
    """Create a new Jottit page. Content should be markdown — start with '# Title' on the first line. Slug is optional (auto-generated from title if omitted). Listing can be 'listed', 'unlisted', or 'pinned'."""
    body = {
        "content": content,
        "draft": draft,
        "listing": listing,
        "ai_assisted": True,
    }
    if slug:
        body["slug"] = slug
    with _client() as client:
        resp = client.post("/api/v1/pages", headers=WRITE_HEADERS, json=body)
    return _format_response(resp)


@mcp.tool()
def update_page(
    slug: str,
    content: str = "",
    draft: bool | None = None,
    listing: str = "",
) -> str:
    """Update an existing Jottit page. All fields except slug are optional — only provided fields are changed. Content should be full markdown including the '# Title' line."""
    body: dict = {"ai_assisted": True}
    if content:
        body["content"] = content
    if draft is not None:
        body["draft"] = draft
    if listing:
        body["listing"] = listing
    with _client() as client:
        resp = client.put(f"/api/v1/pages/{slug}", headers=WRITE_HEADERS, json=body)
    return _format_response(resp)


@mcp.tool()
def delete_page(slug: str) -> str:
    """Permanently delete a Jottit page. This cannot be undone."""
    with _client() as client:
        resp = client.delete(f"/api/v1/pages/{slug}", headers=WRITE_HEADERS)
    return _format_response(resp)


@mcp.tool()
def get_revisions(slug: str, page: int = 1, per_page: int = 20) -> str:
    """List revision history for a page. Returns revision number, timestamp, word count, source (web/api/mcp), and whether it was AI-assisted. Newest revisions first."""
    with _client() as client:
        resp = client.get(
            f"/api/v1/pages/{slug}/revisions",
            params={"page": page, "per_page": per_page},
        )
    return _format_response(resp)


@mcp.tool()
def get_user_profile(username: str) -> str:
    """Get a Jottit user's public profile and their listed/pinned pages."""
    with _client() as client:
        resp = client.get(f"/api/v1/users/{username}")
    return _format_response(resp)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
