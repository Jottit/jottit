import json
import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Jottit")

BASE_URL = os.environ.get("JOTTIT_BASE_URL", "https://jottit.org")
API_TOKEN = os.environ.get("JOTTIT_API_TOKEN", "")

WRITE_HEADERS = {"X-Jottit-Source": "mcp"}


def _client():
    headers = {}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    return httpx.Client(
        base_url=BASE_URL,
        headers=headers,
        timeout=30,
    )


def _format_response(resp):
    is_json = "application/json" in resp.headers.get("content-type", "")
    if resp.status_code >= 400:
        if is_json:
            return f"Error {resp.status_code}: {resp.json().get('error', resp.text)}"
        return f"Error {resp.status_code}: {resp.text}"
    return json.dumps(resp.json(), indent=2)


def _pages_base(site: str) -> str:
    if site:
        return f"/api/v1/sites/{site}/pages"
    return "/api/v1/pages"


@mcp.tool()
def get_page(slug: str, site: str = "") -> str:
    """Get a Jottit page by its slug. Returns the page's title, content (markdown), visibility, and last updated timestamp. Specify which wiki to target by subdomain. Defaults to your default wiki if omitted."""
    with _client() as client:
        resp = client.get(f"{_pages_base(site)}/{slug}")
    return _format_response(resp)


@mcp.tool()
def list_pages(site: str = "") -> str:
    """List all pages owned by the authenticated user. Returns each page's slug, title, visibility, and last updated timestamp. Specify which wiki to target by subdomain. Defaults to your default wiki if omitted."""
    with _client() as client:
        resp = client.get(_pages_base(site))
    return _format_response(resp)


@mcp.tool()
def create_page(
    content: str,
    slug: str = "",
    visibility: str = "private",
    site: str = "",
) -> str:
    """Create a new Jottit page. Content should be markdown — start with '# Title' on the first line. Slug is optional (auto-generated from title if omitted). Visibility can be 'private', 'unlisted', 'listed', or 'pinned'. Works without authentication — the page will be unlisted and a page_secret is returned for editing and claiming later. Specify which wiki to target by subdomain. Defaults to your default wiki if omitted."""
    body = {
        "content": content,
        "visibility": visibility,
        "ai_assisted": True,
    }
    if slug:
        body["slug"] = slug
    with _client() as client:
        resp = client.post(_pages_base(site), headers=WRITE_HEADERS, json=body)
    return _format_response(resp)


@mcp.tool()
def update_page(
    slug: str,
    content: str = "",
    visibility: str = "",
    site: str = "",
) -> str:
    """Update an existing Jottit page. All fields except slug are optional — only provided fields are changed. Content should be full markdown including the '# Title' line. Requires authentication. Specify which wiki to target by subdomain. Defaults to your default wiki if omitted."""
    body: dict = {"ai_assisted": True}
    if content:
        body["content"] = content
    if visibility:
        body["visibility"] = visibility
    with _client() as client:
        resp = client.put(
            f"{_pages_base(site)}/{slug}", headers=WRITE_HEADERS, json=body
        )
    return _format_response(resp)


@mcp.tool()
def delete_page(slug: str, site: str = "") -> str:
    """Permanently delete a Jottit page. This cannot be undone. Specify which wiki to target by subdomain. Defaults to your default wiki if omitted."""
    with _client() as client:
        resp = client.delete(f"{_pages_base(site)}/{slug}", headers=WRITE_HEADERS)
    return _format_response(resp)


@mcp.tool()
def get_revisions(slug: str, page: int = 1, per_page: int = 20, site: str = "") -> str:
    """List revision history for a page. Returns revision number, timestamp, word count, source (web/api/mcp), and whether it was AI-assisted. Newest revisions first. Specify which wiki to target by subdomain. Defaults to your default wiki if omitted."""
    with _client() as client:
        resp = client.get(
            f"{_pages_base(site)}/{slug}/revisions",
            params={"page": page, "per_page": per_page},
        )
    return _format_response(resp)


@mcp.tool()
def get_user_profile(username: str) -> str:
    """Get a Jottit user's public profile and their listed/pinned pages."""
    with _client() as client:
        resp = client.get(f"/api/v1/users/{username}")
    return _format_response(resp)


@mcp.tool()
def list_sites() -> str:
    """List all wikis (sites) owned by the authenticated user."""
    with _client() as client:
        resp = client.get("/api/v1/sites")
    return _format_response(resp)


@mcp.tool()
def get_site(subdomain: str) -> str:
    """Get a wiki by its subdomain."""
    with _client() as client:
        resp = client.get(f"/api/v1/sites/{subdomain}")
    return _format_response(resp)


@mcp.tool()
def create_site(
    subdomain: str,
    title: str = "",
    visibility: str = "public",
    license: str = "",
) -> str:
    """Create a new wiki with the given subdomain."""
    body: dict = {"subdomain": subdomain}
    if title:
        body["title"] = title
    if visibility:
        body["visibility"] = visibility
    if license:
        body["license"] = license
    with _client() as client:
        resp = client.post("/api/v1/sites", headers=WRITE_HEADERS, json=body)
    return _format_response(resp)


@mcp.tool()
def update_site(
    subdomain: str,
    title: str = "",
    visibility: str = "",
    license: str = "",
    home_page_slug: str = "",
) -> str:
    """Update a wiki's settings."""
    body: dict = {}
    if title:
        body["title"] = title
    if visibility:
        body["visibility"] = visibility
    if license:
        body["license"] = license
    if home_page_slug:
        body["home_page_slug"] = home_page_slug
    with _client() as client:
        resp = client.put(
            f"/api/v1/sites/{subdomain}", headers=WRITE_HEADERS, json=body
        )
    return _format_response(resp)


@mcp.tool()
def delete_site(subdomain: str) -> str:
    """Permanently delete a wiki and all its pages. This cannot be undone."""
    with _client() as client:
        resp = client.delete(f"/api/v1/sites/{subdomain}", headers=WRITE_HEADERS)
    return _format_response(resp)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
