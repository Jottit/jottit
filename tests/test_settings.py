import json

from db import (
    claim_page,
    find_or_create_user,
    get_page_meta,
    get_user,
    save_page,
    set_user_username,
    update_user_settings,
)

# -- User settings --


# Settings page redirects to sign-in when logged out
def test_settings_requires_signin(client):
    r = client.get("/settings")
    assert r.status_code == 302
    assert "/signin" in r.headers["Location"]


# Settings page shows name, bio, account, address, export, and sign out
def test_user_settings_shows_hub(client):
    user_id = find_or_create_user("settings@example.com")
    set_user_username(user_id, "sethub")
    update_user_settings(user_id, "Hub User", "sethub", "My bio")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/settings")
    assert r.status_code == 200
    assert b"Hub User" in r.data
    assert b"My bio" in r.data
    assert b"Account" in r.data
    assert b"Address" in r.data
    assert b"Export" in r.data
    assert b"Sign out" in r.data


# Profile settings page shows name and bio fields
def test_settings_profile_shows_form(client):
    user_id = find_or_create_user("setprof@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/settings/profile")
    assert r.status_code == 200
    assert b"Your name" in r.data
    assert b"Bio" in r.data


# Saving profile updates name and bio in the database
def test_settings_profile_save(client):
    user_id = find_or_create_user("settings2@example.com")
    set_user_username(user_id, "profuser")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/settings/profile", data={"name": "My Name", "bio": "Hello"})
    assert r.status_code == 302

    user = get_user(user_id)
    assert user["name"] == "My Name"
    assert user["bio"] == "Hello"


# Address settings page shows address form
def test_settings_address_shows_form(client):
    user_id = find_or_create_user("setsub@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/settings/address")
    assert r.status_code == 200
    assert b"Address" in r.data
    assert b"jottit.org/@" in r.data


# Saving address updates the username
def test_settings_address_save(client):
    user_id = find_or_create_user("setsub2@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/settings/address", data={"username": "myname"})
    assert r.status_code == 302

    user = get_user(user_id)
    assert user["username"] == "myname"


# Invalid username format is rejected
def test_settings_address_invalid_username(client):
    user_id = find_or_create_user("settings3@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/settings/address", data={"username": "BAD!"})
    assert r.status_code == 200
    assert b"lowercase" in r.data


# Duplicate username is rejected
def test_settings_address_username_uniqueness(client):
    user_id1 = find_or_create_user("settings4@example.com")
    set_user_username(user_id1, "taken")

    user_id2 = find_or_create_user("settings5@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id2

    r = client.post("/settings/address", data={"username": "taken"})
    assert r.status_code == 200
    assert b"already taken" in r.data


# Old /settings/subdomain redirects to /settings/address
def test_settings_subdomain_redirects(client):
    user_id = find_or_create_user("redirsub@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/settings/subdomain")
    assert r.status_code == 301
    assert "/settings/address" in r.headers["Location"]


# Account settings page shows email and delete link
def test_settings_account_page(client):
    user_id = find_or_create_user("account@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/settings/account")
    assert r.status_code == 200
    assert b"account@example.com" in r.data
    assert b"Delete account" in r.data


# Export settings page renders with a download option
def test_settings_export_page(client):
    user_id = find_or_create_user("setexp@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/settings/export")
    assert r.status_code == 200
    assert b"Download" in r.data


# License settings page renders with CC BY 4.0 option
def test_settings_license_page(client):
    user_id = find_or_create_user("license@example.com")
    set_user_username(user_id, "licuser")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/settings/license")
    assert r.status_code == 200
    assert b"License" in r.data
    assert b"CC BY 4.0" in r.data


# Saving a valid license persists it
def test_settings_license_saves(client):
    user_id = find_or_create_user("license2@example.com")
    set_user_username(user_id, "licuser2")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/settings/license", data={"license": "cc-by-4.0"})
    assert r.status_code == 302

    user = get_user(user_id)
    assert user["license"] == "cc-by-4.0"


# Invalid license value is not saved
def test_settings_license_rejects_invalid(client):
    user_id = find_or_create_user("license3@example.com")
    set_user_username(user_id, "licuser3")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    client.post("/settings/license", data={"license": "invalid-license"})
    user = get_user(user_id)
    assert user["license"] is None


# -- Username availability API --


# API returns available=true for unused username
def test_check_username_available(client):
    r = client.get("/api/check-username?username=fresh")
    data = json.loads(r.data)
    assert data["available"] is True


# API returns available=false for taken username
def test_check_username_taken(client):
    user_id = find_or_create_user("ucheck@example.com")
    set_user_username(user_id, "taken1")
    r = client.get("/api/check-username?username=taken1")
    data = json.loads(r.data)
    assert data["available"] is False
    assert "already taken" in data["error"]


# API returns available=false for invalid username format
def test_check_username_invalid(client):
    r = client.get("/api/check-username?username=BAD!")
    data = json.loads(r.data)
    assert data["available"] is False
    assert "lowercase" in data["error"]


# API returns available=false for empty username
def test_check_username_empty(client):
    r = client.get("/api/check-username?username=")
    data = json.loads(r.data)
    assert data["available"] is False


# -- /pages page --


# Pages page lists all of the signed-in user's pages
def test_pages_page_lists_all(client):
    user_id = find_or_create_user("pageslist@example.com")
    for i in range(5):
        slug = f"pl{i}"
        save_page(slug, f"# Page {i}\n\nContent", False)
        page_meta = get_page_meta(slug)
        claim_page(page_meta["id"], user_id)

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/pages")
    assert r.status_code == 200
    body = r.data.decode()
    for i in range(5):
        assert f"pl{i}" in body


# Pages page redirects to sign-in when logged out
def test_pages_page_requires_signin(client):
    r = client.get("/pages")
    assert r.status_code == 302
    assert "/signin" in r.headers["Location"]


# -- Delete account --


def test_delete_account_requires_signin(client):
    r = client.get("/settings/delete")
    assert r.status_code == 302
    assert "/signin" in r.headers["Location"]


def test_delete_account_shows_confirmation(client):
    user_id = find_or_create_user("delme@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/settings/delete")
    assert r.status_code == 200
    assert b"Delete my account" in r.data
    assert b"cannot be undone" in r.data


def test_delete_account_rejects_wrong_confirmation(client):
    user_id = find_or_create_user("delme2@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/settings/delete", data={"confirm": "wrong"})
    assert r.status_code == 200
    assert b"type" in r.data
    assert get_user(user_id) is not None


def test_delete_account_deletes_user_and_clears_session(client):
    user_id = find_or_create_user("delme3@example.com")
    set_user_username(user_id, "delme3")
    save_page("delme3page", "# Test", False, user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/settings/delete", data={"confirm": "delete"})
    assert r.status_code == 302
    assert r.headers["Location"] == "/"

    assert get_user(user_id) is None

    with client.session_transaction() as sess:
        assert "user_id" not in sess

    page = get_page_meta("delme3page")
    assert page is not None
    assert page["user_id"] is None
