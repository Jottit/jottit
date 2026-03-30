import json

from db import create_api_token, find_or_create_user, save_page, set_user_username


def _setup_user():
    user_id = find_or_create_user("mcp@test.com")
    set_user_username(user_id, "mcpuser")
    token, _ = create_api_token(user_id, "mcp test")
    return user_id, token


def _rpc(client, method, params=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params:
        body["params"] = params
    return client.post("/mcp", json=body, headers=headers)


def test_initialize_no_auth_required(client):
    r = _rpc(client, "initialize")
    assert r.status_code == 200
    result = r.get_json()["result"]
    assert result["serverInfo"]["name"] == "Jottit"
    assert "tools" in result["capabilities"]


def test_tools_list_no_auth(client):
    r = _rpc(client, "tools/list")
    assert r.status_code == 200
    tools = r.get_json()["result"]["tools"]
    names = [t["name"] for t in tools]
    assert "list_pages" in names
    assert "create_page" in names
    assert "get_page" in names


def test_list_pages_empty(client):
    _, token = _setup_user()
    r = _rpc(client, "tools/call", {"name": "list_pages", "arguments": {}}, token=token)
    assert r.status_code == 200
    text = r.get_json()["result"]["content"][0]["text"]
    data = json.loads(text)
    assert data["pages"] == []


def test_create_and_get_page(client):
    _, token = _setup_user()

    # Create
    r = _rpc(
        client,
        "tools/call",
        {
            "name": "create_page",
            "arguments": {"content": "# Hello\n\nWorld"},
        },
        token=token,
    )
    assert r.status_code == 200
    text = r.get_json()["result"]["content"][0]["text"]
    page = json.loads(text)
    assert page["title"] == "Hello"
    slug = page["slug"]

    # Get
    r = _rpc(
        client,
        "tools/call",
        {
            "name": "get_page",
            "arguments": {"slug": slug},
        },
        token=token,
    )
    text = r.get_json()["result"]["content"][0]["text"]
    page = json.loads(text)
    assert page["content"] == "# Hello\n\nWorld"

    # List
    r = _rpc(client, "tools/call", {"name": "list_pages", "arguments": {}}, token=token)
    text = r.get_json()["result"]["content"][0]["text"]
    data = json.loads(text)
    assert len(data["pages"]) == 1


def test_update_page(client):
    user_id, token = _setup_user()

    slug = save_page("test-update", "# Old\n\nContent", "listed", user_id, source="mcp")

    r = _rpc(
        client,
        "tools/call",
        {
            "name": "update_page",
            "arguments": {"slug": slug, "content": "# New\n\nContent"},
        },
        token=token,
    )
    text = r.get_json()["result"]["content"][0]["text"]
    page = json.loads(text)
    assert page["title"] == "New"
    assert page["content"] == "# New\n\nContent"


def test_delete_page(client):
    user_id, token = _setup_user()

    slug = save_page("test-delete", "# Delete Me", "listed", user_id)

    r = _rpc(
        client,
        "tools/call",
        {
            "name": "delete_page",
            "arguments": {"slug": slug},
        },
        token=token,
    )
    text = r.get_json()["result"]["content"][0]["text"]
    assert json.loads(text)["ok"] is True

    # Verify deleted
    r = _rpc(
        client,
        "tools/call",
        {
            "name": "get_page",
            "arguments": {"slug": slug},
        },
        token=token,
    )
    text = r.get_json()["result"]["content"][0]["text"]
    assert "not found" in text


def test_get_revisions(client):
    user_id, token = _setup_user()

    slug = save_page("test-revisions", "# V1", "listed", user_id)
    save_page(slug, "# V2", "listed", user_id)

    r = _rpc(
        client,
        "tools/call",
        {
            "name": "get_revisions",
            "arguments": {"slug": slug},
        },
        token=token,
    )
    text = r.get_json()["result"]["content"][0]["text"]
    data = json.loads(text)
    assert len(data["revisions"]) == 2


def test_get_user_profile(client):
    user_id, token = _setup_user()

    save_page("profile-page", "# Public Page", "listed", user_id)

    r = _rpc(
        client,
        "tools/call",
        {
            "name": "get_user_profile",
            "arguments": {"username": "mcpuser"},
        },
        token=token,
    )
    text = r.get_json()["result"]["content"][0]["text"]
    data = json.loads(text)
    assert data["username"] == "mcpuser"
    assert len(data["pages"]) == 1


def test_ping(client):
    r = _rpc(client, "ping")
    assert r.status_code == 200


def test_create_page_without_auth(client):
    r = _rpc(
        client,
        "tools/call",
        {"name": "create_page", "arguments": {"content": "# Anonymous MCP\n\nHello"}},
    )
    assert r.status_code == 200
    text = r.get_json()["result"]["content"][0]["text"]
    data = json.loads(text)
    assert data["title"] == "Anonymous MCP"
    assert data["visibility"] == "unlisted"
    assert "page_secret" in data


def test_update_page_requires_auth(client):
    # Create without auth
    r = _rpc(
        client,
        "tools/call",
        {"name": "create_page", "arguments": {"content": "# Original\n\nBody"}},
    )
    text = r.get_json()["result"]["content"][0]["text"]
    data = json.loads(text)
    slug = data["slug"]

    # Update without auth should fail
    r = _rpc(
        client,
        "tools/call",
        {
            "name": "update_page",
            "arguments": {"slug": slug, "content": "# Updated\n\nNew body"},
        },
    )
    text = r.get_json()["result"]["content"][0]["text"]
    assert "authentication required" in text


def test_list_pages_requires_auth(client):
    r = _rpc(
        client,
        "tools/call",
        {"name": "list_pages", "arguments": {}},
    )
    assert r.status_code == 401


def test_unknown_method(client):
    _, token = _setup_user()
    r = _rpc(client, "nonexistent/method", token=token)
    assert r.status_code == 200
    assert r.get_json()["error"]["code"] == -32601
