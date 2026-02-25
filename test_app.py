from db import create_verification_code, find_or_create_user, claim_site, get_site
from routes import _describe_change

# -- Homepage --


def test_homepage(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Jottit" in r.data


# -- Create page --


def test_new_redirects_to_edit(client):
    r = client.get("/new")
    assert r.status_code == 302
    assert "/edit" in r.headers["Location"]


# -- Editor --


def test_edit_get_new_page(client):
    r = client.get("/abc12/edit")
    assert r.status_code == 200
    assert b"Write something" in r.data


def test_edit_get_existing_page(client):
    client.post("/abc12/edit", data={"title": "Hello", "content": "World"})
    r = client.get("/abc12/edit")
    assert r.status_code == 200
    assert b"Hello" in r.data
    assert b"World" in r.data


def test_publish_creates_page(client):
    r = client.post("/mypage/edit", data={"title": "Test", "content": "Body"})
    assert r.status_code == 302
    assert r.headers["Location"] == "/mypage"


def test_publish_with_draft(client):
    client.post(
        "/draftpage/edit", data={"title": "Draft", "content": "WIP", "draft": "on"}
    )
    r = client.get("/draftpage")
    assert r.status_code == 200


# -- View page --


def test_view_page(client):
    client.post("/viewme/edit", data={"title": "Hello", "content": "World"})
    r = client.get("/viewme")
    assert r.status_code == 200
    assert b"Hello" in r.data
    assert b"World" in r.data


def test_view_page_renders_markdown(client):
    client.post("/mdpage/edit", data={"title": "", "content": "**bold**"})
    r = client.get("/mdpage")
    assert b"<strong>bold</strong>" in r.data


def test_view_nonexistent_page(client):
    r = client.get("/doesnotexist")
    assert r.status_code == 404


def test_view_page_shows_actions_for_owner(client):
    client.post("/owned/edit", data={"title": "Mine", "content": "Content"})
    r = client.get("/owned")
    assert b"Edit" in r.data
    assert b"History" in r.data


def test_view_page_shows_latest_content(client):
    client.post("/evolve/edit", data={"title": "V1", "content": "First"})
    client.post("/evolve/edit", data={"title": "V2", "content": "Second"})
    r = client.get("/evolve")
    assert b"V2" in r.data
    assert b"Second" in r.data


# -- Revisions --


def test_edit_creates_revisions(client):
    client.post("/revtest/edit", data={"title": "R1", "content": "A"})
    client.post("/revtest/edit", data={"title": "R1", "content": "B"})
    client.post("/revtest/edit", data={"title": "R1", "content": "C"})
    r = client.get("/revtest/history")
    assert r.status_code == 200
    assert b"#1" in r.data
    assert b"#2" in r.data
    assert b"#3" in r.data


def test_history_shows_created_page(client):
    client.post("/hist1/edit", data={"title": "T", "content": "X"})
    r = client.get("/hist1/history")
    assert b"Created page" in r.data


def test_history_nonexistent_page(client):
    r = client.get("/nope/history")
    assert r.status_code == 404


def test_history_newest_first(client):
    client.post("/order/edit", data={"title": "T", "content": "A"})
    client.post("/order/edit", data={"title": "T", "content": "B"})
    r = client.get("/order/history")
    body = r.data.decode()
    pos_2 = body.index("#2")
    pos_1 = body.index("#1")
    assert pos_2 < pos_1


# -- View specific revision --


def test_view_revision(client):
    client.post("/vrev/edit", data={"title": "V1", "content": "First"})
    client.post("/vrev/edit", data={"title": "V2", "content": "Second"})
    r = client.get("/vrev/history/1")
    assert r.status_code == 200
    assert b"First" in r.data
    assert b"revision #1" in r.data
    assert b"View current version" in r.data


def test_view_revision_nonexistent(client):
    client.post("/vrev2/edit", data={"title": "T", "content": "X"})
    r = client.get("/vrev2/history/99")
    assert r.status_code == 404


# -- Change descriptions --


def test_describe_title_change():
    assert "Changed title" in _describe_change("# Old\n\nBody", "# New\n\nBody")


def test_describe_added_content():
    assert "Added" in _describe_change("# T\n\nA", "# T\n\nA\nB\nC")


def test_describe_removed_content():
    assert "Removed" in _describe_change("# T\n\nA\nB\nC", "# T\n\nA")


def test_describe_changed_content():
    assert "Changed" in _describe_change("# T\n\nHello", "# T\n\nWorld")


def test_describe_same_content():
    assert _describe_change("# T\n\nA", "# T\n\nA") == "Edited page"


# -- Claim banner --


def test_unclaimed_page_shows_claim_banner(client):
    client.post("/uncl/edit", data={"title": "T", "content": "X"})
    r = client.get("/uncl")
    assert b"Claim it" in r.data


def test_claimed_page_hides_claim_banner(client):
    client.post("/clmd/edit", data={"title": "T", "content": "X"})
    user_id = find_or_create_user("owner@example.com")
    claim_site("clmd", user_id)
    r = client.get("/clmd")
    assert b"Claim it" not in r.data


# -- Claim flow --


def test_claim_page_shows_form(client):
    client.post("/cf1/edit", data={"title": "T", "content": "X"})
    r = client.get("/cf1/claim")
    assert r.status_code == 200
    assert b"email" in r.data


def test_claim_already_claimed_redirects(client):
    client.post("/cf2/edit", data={"title": "T", "content": "X"})
    user_id = find_or_create_user("owner@example.com")
    claim_site("cf2", user_id)
    r = client.get("/cf2/claim")
    assert r.status_code == 302


def test_claim_full_flow(client):
    client.post("/cf3/edit", data={"title": "T", "content": "X"})

    # Submit email
    r = client.post("/cf3/claim", data={"email": "user@example.com"})
    assert r.status_code == 302
    assert "/cf3/claim/verify" in r.headers["Location"]

    # Get the code from the DB
    code = create_verification_code("user@example.com", "claim")

    # Submit code
    r = client.post("/cf3/claim/verify", data={"code": code})
    assert r.status_code == 302
    assert r.headers["Location"] == "/cf3"

    # Site is now claimed
    site = get_site("cf3")
    assert site["user_id"] is not None

    # Banner is gone
    r = client.get("/cf3")
    assert b"Claim it" not in r.data


def test_claim_invalid_code_rejected(client):
    client.post("/cf4/edit", data={"title": "T", "content": "X"})
    client.post("/cf4/claim", data={"email": "user@example.com"})
    r = client.post("/cf4/claim/verify", data={"code": "000000"})
    assert r.status_code == 200
    assert b"Invalid" in r.data


# -- Edit protection --


def test_non_owner_redirected_from_edit(client):
    client.post("/prot1/edit", data={"title": "T", "content": "X"})
    user_id = find_or_create_user("owner@example.com")
    claim_site("prot1", user_id)

    # Without session, should redirect
    r = client.get("/prot1/edit")
    assert r.status_code == 302
    assert r.headers["Location"] == "/prot1"


def test_owner_can_edit(client):
    client.post("/prot2/edit", data={"title": "T", "content": "X"})
    user_id = find_or_create_user("owner@example.com")
    claim_site("prot2", user_id)

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/prot2/edit")
    assert r.status_code == 200


def test_unclaimed_page_anyone_can_edit(client):
    client.post("/prot3/edit", data={"title": "T", "content": "X"})
    r = client.get("/prot3/edit")
    assert r.status_code == 200


# -- Sign in flow --


def test_signin_page(client):
    r = client.get("/signin")
    assert r.status_code == 200
    assert b"email" in r.data


def test_signin_full_flow(client):
    # Submit email
    r = client.post("/signin", data={"email": "user@example.com"})
    assert r.status_code == 302
    assert "/signin/verify" in r.headers["Location"]

    # Get code
    code = create_verification_code("user@example.com", "signin")

    # Submit code
    r = client.post("/signin/verify", data={"code": code})
    assert r.status_code == 302
    assert r.headers["Location"] == "/"

    # Session has user_id
    with client.session_transaction() as sess:
        assert "user_id" in sess


def test_signin_invalid_code(client):
    client.post("/signin", data={"email": "user@example.com"})
    r = client.post("/signin/verify", data={"code": "999999"})
    assert r.status_code == 200
    assert b"Invalid" in r.data


# -- Sign out --


def test_signout(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1

    r = client.get("/signout")
    assert r.status_code == 302

    with client.session_transaction() as sess:
        assert "user_id" not in sess


# -- Settings --


def test_settings_requires_signin(client):
    r = client.get("/settings")
    assert r.status_code == 302
    assert "/signin" in r.headers["Location"]


def test_settings_shows_owned_sites(client):
    client.post("/set1/edit", data={"title": "T", "content": "X"})
    user_id = find_or_create_user("owner@example.com")
    claim_site("set1", user_id)

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/settings")
    assert r.status_code == 200
    assert b"set1" in r.data
    assert b"owner@example.com" in r.data


# -- Homepage sign in / settings link --


def test_homepage_shows_signin_when_logged_out(client):
    r = client.get("/")
    assert b"Sign in" in r.data
    assert b"Settings" not in r.data


def test_homepage_shows_settings_when_logged_in(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1

    r = client.get("/")
    assert b"Settings" in r.data
    assert b"Sign in" not in r.data
