from db import (
    create_api_token,
    find_or_create_user,
    get_page_meta,
    get_revision,
    save_page,
    set_user_username,
)


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _setup_user_with_token(username="testuser"):
    user_id = find_or_create_user(f"{username}@test.com")
    set_user_username(user_id, username)
    token, token_id = create_api_token(user_id, "test token")
    return user_id, token


def test_missing_token_returns_401(client):
    r = client.get("/api/v1/pages")
    assert r.status_code == 401
    assert r.get_json()["error"] == "Unauthorized"


def test_invalid_token_returns_401(client):
    r = client.get("/api/v1/pages", headers=_auth("bad-token"))
    assert r.status_code == 401


def test_valid_token_returns_200(client):
    _, token = _setup_user_with_token()
    r = client.get("/api/v1/pages", headers=_auth(token))
    assert r.status_code == 200


def test_get_current_user(client):
    _, token = _setup_user_with_token()
    r = client.get("/api/v1/user", headers=_auth(token))
    assert r.status_code == 200
    data = r.get_json()
    assert data["username"] == "testuser"


def test_get_user_profile(client):
    user_id, token = _setup_user_with_token()
    slug = save_page("mypage", "# Hello\n\nWorld", "listed", user_id)
    r = client.get("/api/v1/users/testuser", headers=_auth(token))
    assert r.status_code == 200
    data = r.get_json()
    assert data["username"] == "testuser"
    assert len(data["pages"]) == 1
    assert data["pages"][0]["slug"] == slug


def test_get_user_profile_excludes_private(client):
    user_id, token = _setup_user_with_token()
    save_page("private-page", "# Private\n\nContent", "private", user_id)
    r = client.get("/api/v1/users/testuser", headers=_auth(token))
    assert r.get_json()["pages"] == []


def test_get_user_profile_not_found(client):
    _, token = _setup_user_with_token()
    r = client.get("/api/v1/users/nobody", headers=_auth(token))
    assert r.status_code == 404


def test_create_page(client):
    _, token = _setup_user_with_token()
    r = client.post(
        "/api/v1/pages",
        headers=_auth(token),
        json={"content": "# My Page\n\nHello world"},
    )
    assert r.status_code == 201
    data = r.get_json()
    assert data["title"] == "My Page"
    assert data["content"] == "# My Page\n\nHello world"
    assert data["visibility"] == "private"


def test_create_page_with_custom_slug(client):
    _, token = _setup_user_with_token()
    r = client.post(
        "/api/v1/pages",
        headers=_auth(token),
        json={"content": "# Test\n\nBody", "slug": "my-custom-slug"},
    )
    assert r.status_code == 201
    assert r.get_json()["slug"] == "my-custom-slug"


def test_create_page_as_private(client):
    _, token = _setup_user_with_token()
    r = client.post(
        "/api/v1/pages",
        headers=_auth(token),
        json={"content": "# Private\n\nContent", "visibility": "private"},
    )
    assert r.status_code == 201
    assert r.get_json()["visibility"] == "private"


def test_create_page_empty_content_returns_400(client):
    _, token = _setup_user_with_token()
    r = client.post("/api/v1/pages", headers=_auth(token), json={"content": ""})
    assert r.status_code == 400


def test_create_page_no_json_returns_400(client):
    _, token = _setup_user_with_token()
    r = client.post("/api/v1/pages", headers=_auth(token), data="not json")
    assert r.status_code == 400


def test_get_page(client):
    user_id, token = _setup_user_with_token()
    save_page("testslug", "# Title\n\nBody", "listed", user_id)
    r = client.get("/api/v1/pages/testslug", headers=_auth(token))
    assert r.status_code == 200
    data = r.get_json()
    assert data["slug"] == "testslug"
    assert data["content"] == "# Title\n\nBody"


def test_get_page_not_found(client):
    _, token = _setup_user_with_token()
    r = client.get("/api/v1/pages/nonexistent", headers=_auth(token))
    assert r.status_code == 404


def test_list_pages(client):
    user_id, token = _setup_user_with_token()
    save_page("page1", "# One\n\nFirst", "listed", user_id)
    save_page("page2", "# Two\n\nSecond", "listed", user_id)
    r = client.get("/api/v1/pages", headers=_auth(token))
    assert r.status_code == 200
    pages = r.get_json()["pages"]
    assert len(pages) == 2


def test_update_page(client):
    user_id, token = _setup_user_with_token()
    save_page("updme", "# Old\n\nOld content", "listed", user_id)
    r = client.put(
        "/api/v1/pages/updme",
        headers=_auth(token),
        json={"content": "# New\n\nNew content"},
    )
    assert r.status_code == 200
    assert r.get_json()["content"] == "# New\n\nNew content"


def test_update_page_not_found(client):
    _, token = _setup_user_with_token()
    r = client.put(
        "/api/v1/pages/nope",
        headers=_auth(token),
        json={"content": "# X\n\nY"},
    )
    assert r.status_code == 404


def test_update_page_visibility(client):
    user_id, token = _setup_user_with_token()
    save_page("lstpage", "# Test\n\nBody", "listed", user_id)
    r = client.put(
        "/api/v1/pages/lstpage",
        headers=_auth(token),
        json={"visibility": "pinned"},
    )
    assert r.status_code == 200
    assert r.get_json()["visibility"] == "pinned"


def test_delete_page(client):
    user_id, token = _setup_user_with_token()
    save_page("delme", "# Delete\n\nMe", "listed", user_id)
    r = client.delete("/api/v1/pages/delme", headers=_auth(token))
    assert r.status_code == 200
    assert r.get_json()["ok"] is True

    r = client.get("/api/v1/pages/delme", headers=_auth(token))
    assert r.status_code == 404


def test_delete_page_not_found(client):
    _, token = _setup_user_with_token()
    r = client.delete("/api/v1/pages/nope", headers=_auth(token))
    assert r.status_code == 404


def test_list_revisions(client):
    user_id, token = _setup_user_with_token()
    save_page("revpage", "# V1\n\nFirst", "listed", user_id)
    save_page("revpage", "# V2\n\nSecond", "listed", user_id)
    r = client.get("/api/v1/pages/revpage/revisions", headers=_auth(token))
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["revisions"]) == 2
    assert data["page"] == 1
    assert data["total_pages"] == 1


def test_revisions_not_found(client):
    _, token = _setup_user_with_token()
    r = client.get("/api/v1/pages/nope/revisions", headers=_auth(token))
    assert r.status_code == 404


def test_default_source_is_api(client):
    user_id, token = _setup_user_with_token()
    r = client.post(
        "/api/v1/pages",
        headers=_auth(token),
        json={"content": "# Test\n\nBody"},
    )
    slug = r.get_json()["slug"]
    meta = get_page_meta(slug, user_id)
    rev = get_revision(meta["id"], 1)
    assert rev["source"] == "api"


def test_mcp_source_via_header(client):
    user_id, token = _setup_user_with_token()
    headers = {**_auth(token), "X-Jottit-Source": "mcp"}
    r = client.post(
        "/api/v1/pages",
        headers=headers,
        json={"content": "# MCP\n\nBody"},
    )
    slug = r.get_json()["slug"]
    meta = get_page_meta(slug, user_id)
    rev = get_revision(meta["id"], 1)
    assert rev["source"] == "mcp"


def test_update_records_source(client):
    user_id, token = _setup_user_with_token()
    save_page("srcpage", "# V1\n\nFirst", "listed", user_id)
    client.put(
        "/api/v1/pages/srcpage",
        headers={**_auth(token), "X-Jottit-Source": "mcp"},
        json={"content": "# V2\n\nUpdated"},
    )
    meta = get_page_meta("srcpage", user_id)
    rev = get_revision(meta["id"], 2)
    assert rev["source"] == "mcp"


def test_ai_assisted_defaults_false(client):
    user_id, token = _setup_user_with_token()
    r = client.post(
        "/api/v1/pages",
        headers=_auth(token),
        json={"content": "# Test\n\nBody"},
    )
    slug = r.get_json()["slug"]
    meta = get_page_meta(slug, user_id)
    rev = get_revision(meta["id"], 1)
    assert rev["ai_assisted"] is False


def test_ai_assisted_set_true(client):
    user_id, token = _setup_user_with_token()
    r = client.post(
        "/api/v1/pages",
        headers=_auth(token),
        json={"content": "# AI\n\nBody", "ai_assisted": True},
    )
    slug = r.get_json()["slug"]
    meta = get_page_meta(slug, user_id)
    rev = get_revision(meta["id"], 1)
    assert rev["ai_assisted"] is True


def test_ai_assisted_in_revisions_response(client):
    user_id, token = _setup_user_with_token()
    save_page("aipage", "# V1\n\nFirst", "listed", user_id, ai_assisted=True)
    r = client.get("/api/v1/pages/aipage/revisions", headers=_auth(token))
    revisions = r.get_json()["revisions"]
    assert revisions[0]["ai_assisted"] is True


def test_ai_assisted_on_update(client):
    user_id, token = _setup_user_with_token()
    save_page("aiupd", "# V1\n\nFirst", "listed", user_id)
    client.put(
        "/api/v1/pages/aiupd",
        headers=_auth(token),
        json={"content": "# V2\n\nAI updated", "ai_assisted": True},
    )
    meta = get_page_meta("aiupd", user_id)
    rev = get_revision(meta["id"], 2)
    assert rev["ai_assisted"] is True


def test_settings_tokens_requires_signin(client):
    r = client.get("/settings/tokens")
    assert r.status_code == 302


def test_create_and_list_tokens(client):
    user_id = find_or_create_user("tok@test.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/settings/tokens", data={"name": "My Token"})
    assert r.status_code == 200
    assert b"My Token" in r.data

    r = client.get("/settings/tokens")
    assert b"My Token" in r.data


def test_revoke_token(client):
    user_id = find_or_create_user("revoke@test.com")
    token, token_id = create_api_token(user_id, "revoke me")

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post(f"/settings/tokens/{token_id}/revoke")
    assert r.status_code == 302

    r = client.get("/api/v1/pages", headers=_auth(token))
    assert r.status_code == 401


def test_api_404_returns_json(client):
    _, token = _setup_user_with_token()
    r = client.get("/api/v1/nonexistent-route", headers=_auth(token))
    assert r.status_code == 404
    assert r.get_json()["error"] == "Not found"


def test_cannot_see_other_users_pages(client):
    user1_id, _ = _setup_user_with_token("user1")
    _, token2 = _setup_user_with_token("user2")
    save_page("secret", "# Secret\n\nContent", "listed", user1_id)

    r = client.get("/api/v1/pages/secret", headers=_auth(token2))
    assert r.status_code == 404


def test_cannot_delete_other_users_pages(client):
    user1_id, token1 = _setup_user_with_token("user1")
    _, token2 = _setup_user_with_token("user2")
    save_page("owned", "# Mine\n\nContent", "listed", user1_id)

    r = client.delete("/api/v1/pages/owned", headers=_auth(token2))
    assert r.status_code == 404

    r = client.get("/api/v1/pages/owned", headers=_auth(token1))
    assert r.status_code == 200
