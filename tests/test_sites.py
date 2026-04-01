import json

from db import (
    check_subdomain_available,
    create_api_token,
    create_site,
    delete_site,
    find_or_create_user,
    get_default_site,
    get_feed_entries_for_site,
    get_page_meta,
    get_pages_for_site,
    get_site,
    get_site_by_subdomain,
    get_sites_for_user,
    save_page,
    set_user_username,
    update_site,
)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _setup_user_with_token(username="testuser"):
    user_id = find_or_create_user(f"{username}@test.com")
    set_user_username(user_id, username)
    token, _ = create_api_token(user_id, "test token")
    return user_id, token


def _sub(client, subdomain, path="/", method="get", **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Host"] = f"{subdomain}.jottit.localhost:8000"
    fn = getattr(client, method)
    return fn(path, headers=headers, **kwargs)


def _rpc(client, method, params=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    return client.post("/mcp", json=body, headers=headers)


# --- DB functions ---


def test_create_site_returns_id(client):
    user_id, _ = _setup_user_with_token()
    site_id = create_site(user_id, "mysite", title="My Site")
    assert site_id is not None


def test_get_site_returns_fields(client):
    user_id, _ = _setup_user_with_token()
    site_id = create_site(user_id, "mysite", title="My Site", visibility="public")
    site = get_site(site_id)
    assert site["subdomain"] == "mysite"
    assert site["title"] == "My Site"
    assert site["visibility"] == "public"
    assert site["user_id"] == user_id


def test_get_site_by_subdomain(client):
    user_id, _ = _setup_user_with_token()
    create_site(user_id, "lookup", title="Lookup")
    site = get_site_by_subdomain("lookup")
    assert site is not None
    assert site["subdomain"] == "lookup"


def test_get_site_by_subdomain_missing(client):
    assert get_site_by_subdomain("nonexistent") is None


def test_get_sites_for_user(client):
    user_id, _ = _setup_user_with_token()
    create_site(user_id, "alpha")
    create_site(user_id, "beta")
    sites = get_sites_for_user(user_id)
    assert len(sites) == 2
    subdomains = [s["subdomain"] for s in sites]
    assert "alpha" in subdomains
    assert "beta" in subdomains


def test_get_default_site_matches_username(client):
    user_id, _ = _setup_user_with_token("alice")
    create_site(user_id, "other")
    create_site(user_id, "alice")
    default = get_default_site(user_id)
    assert default["subdomain"] == "alice"


def test_get_default_site_falls_back_to_first(client):
    user_id, _ = _setup_user_with_token("bob")
    create_site(user_id, "first")
    create_site(user_id, "second")
    default = get_default_site(user_id)
    assert default["subdomain"] == "first"


def test_get_default_site_none_when_no_sites(client):
    user_id, _ = _setup_user_with_token()
    assert get_default_site(user_id) is None


def test_update_site(client):
    user_id, _ = _setup_user_with_token()
    site_id = create_site(user_id, "mysite", title="Old")
    update_site(site_id, title="New", visibility="private")
    site = get_site(site_id)
    assert site["title"] == "New"
    assert site["visibility"] == "private"


def test_delete_site(client):
    user_id, _ = _setup_user_with_token()
    site_id = create_site(user_id, "todelete")
    delete_site(site_id)
    assert get_site(site_id) is None


def test_check_subdomain_available(client):
    user_id, _ = _setup_user_with_token()
    assert check_subdomain_available("fresh") is True
    create_site(user_id, "fresh")
    assert check_subdomain_available("fresh") is False


def test_get_pages_for_site(client):
    user_id, _ = _setup_user_with_token()
    site_id = create_site(user_id, "wiki")
    save_page("page1", "# Page 1", "listed", user_id, site_id=site_id)
    save_page("page2", "# Page 2", "listed", user_id, site_id=site_id)
    pages = get_pages_for_site(site_id)
    assert len(pages) == 2
    slugs = [p["slug"] for p in pages]
    assert "page1" in slugs
    assert "page2" in slugs


def test_get_feed_entries_for_site(client):
    user_id, _ = _setup_user_with_token()
    site_id = create_site(user_id, "wiki")
    save_page("pub", "# Public", "listed", user_id, site_id=site_id)
    save_page("priv", "# Private", "private", user_id, site_id=site_id)
    entries = get_feed_entries_for_site(site_id)
    assert len(entries) == 1
    assert entries[0]["slug"] == "pub"


def test_per_site_slug_uniqueness(client):
    """Two different sites can have pages with the same slug."""
    user_id, _ = _setup_user_with_token()
    site_a = create_site(user_id, "sitea")
    site_b = create_site(user_id, "siteb")
    save_page("hello", "# Hello A", "listed", user_id, site_id=site_a)
    save_page("hello", "# Hello B", "listed", user_id, site_id=site_b)
    meta_a = get_page_meta("hello", site_id=site_a)
    meta_b = get_page_meta("hello", site_id=site_b)
    assert meta_a is not None
    assert meta_b is not None
    assert meta_a["id"] != meta_b["id"]


# --- API: Site CRUD ---


def test_api_list_sites_empty(client):
    _, token = _setup_user_with_token()
    r = client.get("/api/v1/sites", headers=_auth(token))
    assert r.status_code == 200
    assert r.get_json()["sites"] == []


def test_api_create_site(client):
    _, token = _setup_user_with_token()
    r = client.post(
        "/api/v1/sites",
        json={"subdomain": "newsite", "title": "New Site"},
        headers=_auth(token),
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["subdomain"] == "newsite"
    assert data["title"] == "New Site"


def test_api_create_site_missing_subdomain(client):
    _, token = _setup_user_with_token()
    r = client.post("/api/v1/sites", json={"title": "No Sub"}, headers=_auth(token))
    assert r.status_code == 400
    assert "Subdomain is required" in r.get_json()["error"]


def test_api_create_site_reserved_subdomain(client):
    _, token = _setup_user_with_token()
    r = client.post("/api/v1/sites", json={"subdomain": "www"}, headers=_auth(token))
    assert r.status_code == 400
    assert "reserved" in r.get_json()["error"]


def test_api_create_site_duplicate_subdomain(client):
    _, token = _setup_user_with_token()
    client.post("/api/v1/sites", json={"subdomain": "taken"}, headers=_auth(token))
    r = client.post("/api/v1/sites", json={"subdomain": "taken"}, headers=_auth(token))
    assert r.status_code == 409
    assert "already taken" in r.get_json()["error"]


def test_api_get_site(client):
    _, token = _setup_user_with_token()
    client.post("/api/v1/sites", json={"subdomain": "getme"}, headers=_auth(token))
    r = client.get("/api/v1/sites/getme", headers=_auth(token))
    assert r.status_code == 200
    assert r.get_json()["subdomain"] == "getme"


def test_api_get_site_not_found(client):
    _, token = _setup_user_with_token()
    r = client.get("/api/v1/sites/nope", headers=_auth(token))
    assert r.status_code == 404


def test_api_update_site(client):
    _, token = _setup_user_with_token()
    client.post("/api/v1/sites", json={"subdomain": "upd"}, headers=_auth(token))
    r = client.put(
        "/api/v1/sites/upd",
        json={"title": "Updated"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert r.get_json()["title"] == "Updated"


def test_api_delete_site(client):
    _, token = _setup_user_with_token()
    client.post("/api/v1/sites", json={"subdomain": "del"}, headers=_auth(token))
    r = client.delete("/api/v1/sites/del", headers=_auth(token))
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    r = client.get("/api/v1/sites/del", headers=_auth(token))
    assert r.status_code == 404


def test_api_other_user_cannot_see_site(client):
    _, token_a = _setup_user_with_token("usera")
    _, token_b = _setup_user_with_token("userb")
    client.post("/api/v1/sites", json={"subdomain": "private"}, headers=_auth(token_a))
    r = client.get("/api/v1/sites/private", headers=_auth(token_b))
    assert r.status_code == 404


# --- API: Nested page routes ---


def test_api_list_site_pages(client):
    user_id, token = _setup_user_with_token()
    create_site(user_id, "wiki")
    r = client.post(
        "/api/v1/sites/wiki/pages",
        json={"content": "# Page One"},
        headers=_auth(token),
    )
    assert r.status_code == 201
    r = client.get("/api/v1/sites/wiki/pages", headers=_auth(token))
    assert r.status_code == 200
    assert len(r.get_json()["pages"]) == 1


def test_api_create_site_page(client):
    user_id, token = _setup_user_with_token()
    create_site(user_id, "wiki")
    r = client.post(
        "/api/v1/sites/wiki/pages",
        json={"content": "# Test", "slug": "test-page", "visibility": "listed"},
        headers=_auth(token),
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["slug"] == "test-page"
    assert data["site"] == "wiki"


def test_api_create_site_page_missing_content(client):
    user_id, token = _setup_user_with_token()
    create_site(user_id, "wiki")
    r = client.post("/api/v1/sites/wiki/pages", json={}, headers=_auth(token))
    assert r.status_code == 400


def test_api_get_site_page(client):
    user_id, token = _setup_user_with_token()
    create_site(user_id, "wiki")
    client.post(
        "/api/v1/sites/wiki/pages",
        json={"content": "# Hello", "slug": "hello"},
        headers=_auth(token),
    )
    r = client.get("/api/v1/sites/wiki/pages/hello", headers=_auth(token))
    assert r.status_code == 200
    assert r.get_json()["slug"] == "hello"


def test_api_get_site_page_not_found(client):
    user_id, token = _setup_user_with_token()
    create_site(user_id, "wiki")
    r = client.get("/api/v1/sites/wiki/pages/nope", headers=_auth(token))
    assert r.status_code == 404


def test_api_update_site_page(client):
    user_id, token = _setup_user_with_token()
    create_site(user_id, "wiki")
    client.post(
        "/api/v1/sites/wiki/pages",
        json={"content": "# Old", "slug": "upd"},
        headers=_auth(token),
    )
    r = client.put(
        "/api/v1/sites/wiki/pages/upd",
        json={"content": "# New"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert "New" in r.get_json()["content"]


def test_api_delete_site_page(client):
    user_id, token = _setup_user_with_token()
    create_site(user_id, "wiki")
    client.post(
        "/api/v1/sites/wiki/pages",
        json={"content": "# Gone", "slug": "gone"},
        headers=_auth(token),
    )
    r = client.delete("/api/v1/sites/wiki/pages/gone", headers=_auth(token))
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    r = client.get("/api/v1/sites/wiki/pages/gone", headers=_auth(token))
    assert r.status_code == 404


def test_api_site_pages_isolated_from_other_site(client):
    """Pages on one site are not visible on another."""
    user_id, token = _setup_user_with_token()
    create_site(user_id, "sitea")
    create_site(user_id, "siteb")
    client.post(
        "/api/v1/sites/sitea/pages",
        json={"content": "# A Page", "slug": "shared"},
        headers=_auth(token),
    )
    r = client.get("/api/v1/sites/siteb/pages/shared", headers=_auth(token))
    assert r.status_code == 404


# --- Subdomain routing ---


def test_subdomain_private_site_403_for_visitor(client):
    user_id, _ = _setup_user_with_token()
    site_id = create_site(user_id, "secret", visibility="private")
    save_page("home", "# Home", "listed", user_id, site_id=site_id)
    r = _sub(client, "secret", "/home")
    assert r.status_code == 403


def test_subdomain_private_site_visible_to_owner(client):
    user_id, _ = _setup_user_with_token()
    site_id = create_site(user_id, "secret", visibility="private")
    save_page("home", "# Home", "listed", user_id, site_id=site_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = _sub(client, "secret", "/home")
    assert r.status_code == 200


def test_subdomain_home_page_slug(client):
    user_id, _ = _setup_user_with_token()
    site_id = create_site(user_id, "docs", visibility="public")
    save_page("intro", "# Welcome", "listed", user_id, site_id=site_id)
    update_site(site_id, home_page_slug="intro")
    r = _sub(client, "docs", "/")
    assert r.status_code == 200
    assert "Welcome" in r.get_data(as_text=True)


def test_subdomain_public_site_accessible(client):
    user_id, _ = _setup_user_with_token()
    site_id = create_site(user_id, "pub", visibility="public")
    save_page("page1", "# Public Page", "listed", user_id, site_id=site_id)
    r = _sub(client, "pub", "/page1")
    assert r.status_code == 200
    assert "Public Page" in r.get_data(as_text=True)


def test_subdomain_nonexistent_site_404(client):
    r = _sub(client, "nosuchsite", "/")
    assert r.status_code == 404


# --- MCP tools ---


def test_mcp_list_sites(client):
    user_id, token = _setup_user_with_token()
    create_site(user_id, "mywiki", title="My Wiki")
    r = _rpc(client, "tools/call", {"name": "list_sites", "arguments": {}}, token=token)
    assert r.status_code == 200
    text = r.get_json()["result"]["content"][0]["text"]
    data = json.loads(text)
    assert len(data["sites"]) == 1
    assert data["sites"][0]["subdomain"] == "mywiki"


def test_mcp_create_site(client):
    _, token = _setup_user_with_token()
    r = _rpc(
        client,
        "tools/call",
        {"name": "create_site", "arguments": {"subdomain": "newwiki", "title": "New"}},
        token=token,
    )
    assert r.status_code == 200
    text = r.get_json()["result"]["content"][0]["text"]
    data = json.loads(text)
    assert data["subdomain"] == "newwiki"
    assert data["title"] == "New"


def test_mcp_create_site_reserved(client):
    _, token = _setup_user_with_token()
    r = _rpc(
        client,
        "tools/call",
        {"name": "create_site", "arguments": {"subdomain": "www"}},
        token=token,
    )
    text = r.get_json()["result"]["content"][0]["text"]
    assert "reserved" in text.lower()


def test_mcp_get_site(client):
    user_id, token = _setup_user_with_token()
    create_site(user_id, "getwiki", title="Get Wiki")
    r = _rpc(
        client,
        "tools/call",
        {"name": "get_site", "arguments": {"subdomain": "getwiki"}},
        token=token,
    )
    assert r.status_code == 200
    text = r.get_json()["result"]["content"][0]["text"]
    data = json.loads(text)
    assert data["subdomain"] == "getwiki"


def test_mcp_get_site_not_found(client):
    _, token = _setup_user_with_token()
    r = _rpc(
        client,
        "tools/call",
        {"name": "get_site", "arguments": {"subdomain": "nope"}},
        token=token,
    )
    text = r.get_json()["result"]["content"][0]["text"]
    assert "not found" in text.lower()


def test_mcp_delete_site(client):
    user_id, token = _setup_user_with_token()
    create_site(user_id, "delwiki")
    r = _rpc(
        client,
        "tools/call",
        {"name": "delete_site", "arguments": {"subdomain": "delwiki"}},
        token=token,
    )
    text = r.get_json()["result"]["content"][0]["text"]
    data = json.loads(text)
    assert data["ok"] is True
    assert get_site_by_subdomain("delwiki") is None


def test_mcp_create_page_on_site(client):
    user_id, token = _setup_user_with_token()
    create_site(user_id, "wiki")
    r = _rpc(
        client,
        "tools/call",
        {
            "name": "create_page",
            "arguments": {"content": "# Wiki Page", "site": "wiki"},
        },
        token=token,
    )
    assert r.status_code == 200
    text = r.get_json()["result"]["content"][0]["text"]
    data = json.loads(text)
    assert data["title"] == "Wiki Page"
