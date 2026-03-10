import io
import json
import os
from unittest.mock import patch

from db import (
    claim_page,
    create_verification_code,
    find_or_create_user,
    get_db,
    get_page_meta,
    get_user,
    run_migrations,
    save_page,
    set_user_username,
    update_page_listing,
    update_user_avatar,
    update_user_settings,
)
from utils import describe_change, render_bio, slugify

# -- Homepage --


# Homepage returns 200 and contains "Jottit"
def test_homepage(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"Jottit" in r.data


# -- Create page --


# GET /new shows the editor with placeholder text
def test_new_shows_editor(client):
    r = client.get("/new")
    assert r.status_code == 200
    assert b"Write something" in r.data


# POST /new creates a page and redirects to a slug derived from the title
def test_new_publish_creates_page_with_nice_slug(client):
    r = client.post("/new", data={"title": "Hello World", "content": "Body"})
    assert r.status_code == 302
    assert r.headers["Location"] == "/hello-world"


# -- Editor --


# Editing a nonexistent slug shows the editor
def test_edit_get_new_page(client):
    r = client.get("/abc12/edit")
    assert r.status_code == 200
    assert b"Write something" in r.data


# Cancel link on a new page points to homepage
def test_edit_cancel_new_page_goes_home(client):
    r = client.get("/newslug/edit")
    assert b'href="/"' in r.data


# Cancel link on an existing page points back to that page
def test_edit_cancel_existing_page_goes_to_page(client):
    client.post("/existslug/edit", data={"title": "T", "content": "C"})
    r = client.get("/existslug/edit")
    assert b'href="/existslug"' in r.data


# Editing an existing page pre-fills the title and content
def test_edit_get_existing_page(client):
    client.post("/abc12/edit", data={"title": "Hello", "content": "World"})
    r = client.get("/abc12/edit")
    assert r.status_code == 200
    assert b"Hello" in r.data
    assert b"World" in r.data


# Saving an edit creates the page and redirects to its slug
def test_publish_creates_page(client):
    r = client.post("/mypage/edit", data={"title": "Test", "content": "Body"})
    assert r.status_code == 302
    assert r.headers["Location"] == "/mypage"


# Viewing a page with a trailing slash still works
def test_trailing_slash_works(client):
    client.post("/tslash/edit", data={"title": "Hi", "content": "There"})
    r = client.get("/tslash/")
    assert r.status_code == 200
    assert b"Hi" in r.data


# -- View page --


# Published page renders its title and content
def test_view_page(client):
    client.post("/viewme/edit", data={"title": "Hello", "content": "World"})
    r = client.get("/viewme")
    assert r.status_code == 200
    assert b"Hello" in r.data
    assert b"World" in r.data


# Markdown content is rendered to HTML on the published page
def test_view_page_renders_markdown(client):
    client.post("/mdpage/edit", data={"title": "", "content": "**bold**"})
    r = client.get("/mdpage")
    assert b"<strong>bold</strong>" in r.data


# Viewing a nonexistent slug returns 404
def test_view_nonexistent_page(client):
    r = client.get("/doesnotexist")
    assert r.status_code == 404


# Page creator sees Edit and History action links
def test_view_page_shows_actions_for_creator(client):
    client.post("/owned/edit", data={"title": "Mine", "content": "Content"})
    client.post("/owned/edit", data={"title": "Mine", "content": "Updated"})
    r = client.get("/owned")
    assert b"Edit" in r.data
    assert b"History" in r.data


# After editing, the page shows the most recent content
def test_view_page_shows_latest_content(client):
    client.post("/evolve/edit", data={"title": "V1", "content": "First"})
    client.post("/evolve/edit", data={"title": "V2", "content": "Second"})
    r = client.get("/evolve")
    assert b"V2" in r.data
    assert b"Second" in r.data


# -- Session-based edit protection --


# The session that created a page can edit it
def test_creator_can_edit_unclaimed_page(client):
    client.post("/prot1/edit", data={"title": "T", "content": "X"})
    r = client.get("/prot1/edit")
    assert r.status_code == 200


# A different session cannot edit an unclaimed page
def test_non_creator_cannot_edit_unclaimed_page(client):
    # Create page in one session
    client.post("/prot2/edit", data={"title": "T", "content": "X"})

    # Clear session to simulate different browser
    with client.session_transaction() as sess:
        sess.clear()

    r = client.get("/prot2/edit")
    assert r.status_code == 302
    assert r.headers["Location"] == "/prot2"


# Non-owner is redirected away from editing a claimed page
def test_non_owner_redirected_from_edit(client):
    client.post("/prot3/edit", data={"title": "T", "content": "X"})
    user_id = find_or_create_user("owner@example.com")
    page_meta = get_page_meta("prot3")
    claim_page(page_meta["id"], user_id)

    with client.session_transaction() as sess:
        sess.clear()

    r = client.get("/prot3/edit")
    assert r.status_code == 302
    assert r.headers["Location"] == "/prot3"


# The claimed owner can edit their page
def test_owner_can_edit(client):
    client.post("/prot4/edit", data={"title": "T", "content": "X"})
    user_id = find_or_create_user("owner@example.com")
    page_meta = get_page_meta("prot4")
    claim_page(page_meta["id"], user_id)

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/prot4/edit")
    assert r.status_code == 200


# -- Revisions --


# Multiple edits create numbered revision entries in history
def test_edit_creates_revisions(client):
    client.post("/revtest/edit", data={"title": "R1", "content": "A"})
    client.post("/revtest/edit", data={"title": "R1", "content": "B"})
    client.post("/revtest/edit", data={"title": "R1", "content": "C"})
    r = client.get("/revtest/history")
    assert r.status_code == 200
    assert b"history/1" in r.data
    assert b"history/2" in r.data


# History page shows "Created" label for the first revision
def test_history_shows_created(client):
    client.post("/hist1/edit", data={"title": "T", "content": "X"})
    client.post("/hist1/edit", data={"title": "T", "content": "X Y"})
    r = client.get("/hist1/history")
    assert b"Created" in r.data


# History of a nonexistent page returns 404
def test_history_nonexistent_page(client):
    r = client.get("/nope/history")
    assert r.status_code == 404


# Revisions are listed newest-first
def test_history_newest_first(client):
    client.post("/order/edit", data={"title": "T", "content": "A"})
    client.post("/order/edit", data={"title": "T", "content": "A B"})
    client.post("/order/edit", data={"title": "T", "content": "A B C"})
    r = client.get("/order/history")
    body = r.data.decode()
    pos_2 = body.index("history/2")
    pos_1 = body.index("history/1")
    assert pos_2 < pos_1


# -- View specific revision --


# A specific revision renders its content with a revision number label
def test_view_revision(client):
    client.post("/vrev/edit", data={"title": "V1", "content": "First"})
    client.post("/vrev/edit", data={"title": "V2", "content": "Second"})
    r = client.get("/vrev/history/1")
    assert r.status_code == 200
    assert b"First" in r.data
    assert b"revision #1" in r.data
    assert b"View current version" in r.data


# Requesting a nonexistent revision returns 404
def test_view_revision_nonexistent(client):
    client.post("/vrev2/edit", data={"title": "T", "content": "X"})
    r = client.get("/vrev2/history/99")
    assert r.status_code == 404


# -- Change descriptions --


# Detects a title change between revisions
def test_describe_title_change():
    assert "Changed title" in describe_change("# Old\n\nBody", "# New\n\nBody")


# Detects added content
def test_describe_added_content():
    assert "Added" in describe_change("# T\n\nA", "# T\n\nA\nB\nC")


# Detects removed content
def test_describe_removed_content():
    assert "Removed" in describe_change("# T\n\nA\nB\nC", "# T\n\nA")


# Detects modified content
def test_describe_changed_content():
    assert "Changed" in describe_change("# T\n\nHello", "# T\n\nWorld")


# Returns generic "Edited page" when nothing changed
def test_describe_same_content():
    assert describe_change("# T\n\nA", "# T\n\nA") == "Edited page"


# -- Claim banner --


# Creator sees the claim banner on their unclaimed page
def test_unclaimed_page_shows_claim_banner_to_creator(client):
    client.post("/uncl/edit", data={"title": "T", "content": "X"})
    r = client.get("/uncl")
    assert b"claim-banner" in r.data


# Non-creator doesn't see the claim banner
def test_unclaimed_page_hides_claim_banner_from_non_creator(client):
    client.post("/uncl2/edit", data={"title": "T", "content": "X"})
    with client.session_transaction() as sess:
        sess.clear()
    r = client.get("/uncl2")
    assert b"claim-banner" not in r.data


# Claimed pages don't show the claim banner
def test_claimed_page_hides_claim_banner(client):
    client.post("/clmd/edit", data={"title": "T", "content": "X"})
    user_id = find_or_create_user("owner@example.com")
    page_meta = get_page_meta("clmd")
    claim_page(page_meta["id"], user_id)
    r = client.get("/clmd")
    assert b"claim-banner" not in r.data


# -- Claim flow --


# Claim page shows an email input form
def test_claim_page_shows_email_form(client):
    client.post("/cf1/edit", data={"title": "T", "content": "X"})
    r = client.get("/cf1/claim")
    assert r.status_code == 200
    assert b"email" in r.data
    assert b"Enter your email" in r.data


# Claiming an already-claimed page redirects away
def test_claim_already_claimed_redirects(client):
    client.post("/cf2/edit", data={"title": "T", "content": "X"})
    user_id = find_or_create_user("owner@example.com")
    page_meta = get_page_meta("cf2")
    claim_page(page_meta["id"], user_id)
    r = client.get("/cf2/claim")
    assert r.status_code == 302


# Full claim flow: email, verify code, set name, set username; slug gets renamed from title
def test_claim_full_flow(client):
    client.post("/cf3/edit", data={"title": "My Great Page", "content": "X"})

    # Step 1: email
    r = client.post("/cf3/claim", data={"email": "user@example.com"})
    assert r.status_code == 302
    assert "/cf3/claim/verify" in r.headers["Location"]

    # Step 2: verify
    code = create_verification_code("user@example.com", "claim")
    r = client.post(
        "/cf3/claim/verify", data={"code": code, "email": "user@example.com"}
    )
    assert r.status_code == 302
    assert "/cf3/claim/setup" in r.headers["Location"]

    # Step 3: name
    r = client.post("/cf3/claim/setup", data={"name": "Test User"})
    assert r.status_code == 302
    assert "/cf3/claim/address" in r.headers["Location"]

    # Step 4: address
    r = client.post("/cf3/claim/address", data={"username": "testuser"})
    assert r.status_code == 302
    # Slug gets renamed to slugified title
    assert "/my-great-page" in r.headers["Location"]

    claimed_user_id = find_or_create_user("user@example.com")
    page_meta = get_page_meta("my-great-page", claimed_user_id)
    assert page_meta["user_id"] is not None

    user = get_user(page_meta["user_id"])
    assert user["username"] == "testuser"
    assert user["name"] == "Test User"


# Claim flow persists the user's name and username
def test_claim_sets_name_and_username(client):
    client.post("/cfun/edit", data={"title": "Unique Title", "content": "X"})

    client.post("/cfun/claim", data={"email": "newuser@example.com"})
    code = create_verification_code("newuser@example.com", "claim")
    client.post(
        "/cfun/claim/verify", data={"code": code, "email": "newuser@example.com"}
    )
    client.post("/cfun/claim/setup", data={"name": "New User"})
    client.post("/cfun/claim/address", data={"username": "newname"})

    claimed_user_id = find_or_create_user("newuser@example.com")
    page_meta = get_page_meta("unique-title", claimed_user_id)
    user = get_user(page_meta["user_id"])
    assert user["username"] == "newname"
    assert user["name"] == "New User"


# Invalid verification code shows an error
def test_claim_invalid_code_rejected(client):
    client.post("/cf4/edit", data={"title": "T", "content": "X"})
    client.post("/cf4/claim", data={"email": "user@example.com"})
    r = client.post(
        "/cf4/claim/verify", data={"code": "000000", "email": "user@example.com"}
    )
    assert r.status_code == 200
    assert b"Invalid" in r.data


# Submitting email during claim stores it in the session
def test_claim_stores_email_in_session(client):
    client.post("/cf5/edit", data={"title": "T", "content": "X"})
    client.post("/cf5/claim", data={"email": "session@example.com"})
    with client.session_transaction() as sess:
        assert sess.get("claim_email") == "session@example.com"


# Submitting a different email in verification than in the session is rejected
def test_claim_rejects_email_substitution(client):
    client.post("/cf6/edit", data={"title": "T", "content": "X"})
    client.post("/cf6/claim", data={"email": "real@example.com"})
    code = create_verification_code("real@example.com", "claim")
    r = client.post(
        "/cf6/claim/verify", data={"code": code, "email": "attacker@example.com"}
    )
    assert r.status_code == 302
    assert "/cf6/claim" in r.headers["Location"]


# Sign-in stores the email in the session
def test_signin_stores_email_in_session(client):
    client.post("/signin", data={"email": "signin@example.com"})
    with client.session_transaction() as sess:
        assert sess.get("signin_email") == "signin@example.com"


# After completing the claim flow, claim-related session keys are removed
def test_claim_cleans_up_session(client):
    client.post("/cf7/edit", data={"title": "T", "content": "X"})
    client.post("/cf7/claim", data={"email": "clean@example.com"})
    code = create_verification_code("clean@example.com", "claim")
    client.post("/cf7/claim/verify", data={"code": code, "email": "clean@example.com"})
    client.post("/cf7/claim/setup", data={"name": "Clean User"})
    client.post("/cf7/claim/address", data={"username": "user7"})
    with client.session_transaction() as sess:
        assert "claim_email" not in sess
        assert "claim_verified" not in sess
        assert "claim_name" not in sess


# Accessing the setup step without verifying redirects back to claim
def test_claim_setup_requires_verification(client):
    client.post("/cf8/edit", data={"title": "T", "content": "X"})
    r = client.get("/cf8/claim/setup")
    assert r.status_code == 302
    assert "/cf8/claim" in r.headers["Location"]


# Empty name is rejected with a validation error
def test_claim_setup_validates_name(client):
    client.post("/cf10/edit", data={"title": "T", "content": "X"})
    client.post("/cf10/claim", data={"email": "nameval@example.com"})
    code = create_verification_code("nameval@example.com", "claim")
    client.post(
        "/cf10/claim/verify", data={"code": code, "email": "nameval@example.com"}
    )

    r = client.post("/cf10/claim/setup", data={"name": ""})
    assert r.status_code == 200
    assert b"required" in r.data


# Invalid or empty username is rejected with validation errors
def test_claim_address_validates_username(client):
    client.post("/cf9/edit", data={"title": "T", "content": "X"})
    client.post("/cf9/claim", data={"email": "val@example.com"})
    code = create_verification_code("val@example.com", "claim")
    client.post("/cf9/claim/verify", data={"code": code, "email": "val@example.com"})
    client.post("/cf9/claim/setup", data={"name": "Val User"})

    r = client.post("/cf9/claim/address", data={"username": "BAD!"})
    assert r.status_code == 200
    assert b"lowercase" in r.data

    r = client.post("/cf9/claim/address", data={"username": ""})
    assert r.status_code == 200
    assert b"required" in r.data


# A username already in use is rejected
def test_claim_address_rejects_taken_username(client):
    user_id = find_or_create_user("existing@example.com")
    set_user_username(user_id, "takensetup")

    client.post("/cf11/edit", data={"title": "T", "content": "X"})
    client.post("/cf11/claim", data={"email": "setup@example.com"})
    code = create_verification_code("setup@example.com", "claim")
    client.post("/cf11/claim/verify", data={"code": code, "email": "setup@example.com"})
    client.post("/cf11/claim/setup", data={"name": "Setup User"})

    r = client.post("/cf11/claim/address", data={"username": "takensetup"})
    assert r.status_code == 200
    assert b"already taken" in r.data


# Accessing the address step without verifying redirects back
def test_claim_address_requires_verification(client):
    client.post("/cf12/edit", data={"title": "T", "content": "X"})
    r = client.get("/cf12/claim/address")
    assert r.status_code == 302
    assert "/cf12/claim" in r.headers["Location"]


# A returning user who already has a name/username skips the setup steps
def test_returning_user_skips_setup(client):
    # First claim: set up name and username
    client.post("/ret1/edit", data={"title": "First Page", "content": "X"})
    client.post("/ret1/claim", data={"email": "returning@example.com"})
    code = create_verification_code("returning@example.com", "claim")
    client.post(
        "/ret1/claim/verify", data={"code": code, "email": "returning@example.com"}
    )
    client.post("/ret1/claim/setup", data={"name": "Return User"})
    client.post("/ret1/claim/address", data={"username": "returnuser"})

    # Second page: returning user should skip setup/address
    with client.session_transaction() as sess:
        sess.pop("user_id", None)
    client.post("/ret2/edit", data={"title": "Second Page", "content": "Y"})
    client.post("/ret2/claim", data={"email": "returning@example.com"})
    code = create_verification_code("returning@example.com", "claim")
    r = client.post(
        "/ret2/claim/verify", data={"code": code, "email": "returning@example.com"}
    )
    assert r.status_code == 302
    # Should skip setup and go straight to subdomain
    assert "returnuser.jottit.localhost:8000" in r.headers["Location"]
    assert "/second-page" in r.headers["Location"]

    claimed_user_id = find_or_create_user("returning@example.com")
    page_meta = get_page_meta("second-page", claimed_user_id)
    assert page_meta is not None
    assert page_meta["user_id"] is not None


# Claiming a new page doesn't overwrite the returning user's existing profile
def test_returning_user_preserves_profile(client):
    # Set up a user with name and username
    user_id = find_or_create_user("preserve@example.com")
    set_user_username(user_id, "preserved")
    update_user_settings(user_id, "Original Name", "preserved", "My bio")

    # Create a page and claim it as this returning user
    client.post("/pres1/edit", data={"title": "T", "content": "X"})
    client.post("/pres1/claim", data={"email": "preserve@example.com"})
    code = create_verification_code("preserve@example.com", "claim")
    client.post(
        "/pres1/claim/verify", data={"code": code, "email": "preserve@example.com"}
    )

    # Verify profile was not overwritten
    user = get_user(user_id)
    assert user["name"] == "Original Name"
    assert user["username"] == "preserved"
    assert user["bio"] == "My bio"


# Accessing the address step without setting a name redirects to setup
def test_claim_address_requires_name(client):
    client.post("/cf13/edit", data={"title": "T", "content": "X"})
    client.post("/cf13/claim", data={"email": "noname@example.com"})
    code = create_verification_code("noname@example.com", "claim")
    client.post(
        "/cf13/claim/verify", data={"code": code, "email": "noname@example.com"}
    )
    r = client.get("/cf13/claim/address")
    assert r.status_code == 302
    assert "/cf13/claim/setup" in r.headers["Location"]


# -- Sign in flow --


# Sign-in page renders with an email field
def test_signin_page(client):
    r = client.get("/signin")
    assert r.status_code == 200
    assert b"email" in r.data


# Full sign-in: submit email, verify code, session contains user_id
def test_signin_full_flow(client):
    r = client.post("/signin", data={"email": "user@example.com"})
    assert r.status_code == 200
    assert b"Check your email" in r.data

    code = create_verification_code("user@example.com", "signin")

    r = client.post("/signin/verify", data={"code": code, "email": "user@example.com"})
    assert r.status_code == 302
    assert r.headers["Location"] == "/"

    with client.session_transaction() as sess:
        assert "user_id" in sess


# Invalid sign-in code shows an error
def test_signin_invalid_code(client):
    client.post("/signin", data={"email": "user@example.com"})
    r = client.post(
        "/signin/verify", data={"code": "999999", "email": "user@example.com"}
    )
    assert r.status_code == 200
    assert b"Invalid" in r.data


# -- Sign out --


# Signing out clears user_id from the session
def test_signout(client):
    user_id = find_or_create_user("signout@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/signout")
    assert r.status_code == 302

    with client.session_transaction() as sess:
        assert "user_id" not in sess


# -- Homepage sign in / settings link --


# Logged-out homepage shows "Sign in"
def test_homepage_shows_signin_when_logged_out(client):
    r = client.get("/")
    assert b"Sign in" in r.data


# Logged-in homepage shows settings link instead of sign in
def test_homepage_shows_avatar_when_logged_in(client):
    user_id = find_or_create_user("logged@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/")
    assert b"/settings" in r.data
    assert b"Sign in" not in r.data


# -- Homepage pages list --


# Homepage doesn't show a "My pages" link
def test_homepage_no_my_pages_link(client):
    user_id = find_or_create_user("pages@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/")
    assert b"My pages" not in r.data


# -- Auto-claim for signed-in users --


# A signed-in user's new page is automatically claimed and slug-renamed
def test_signed_in_user_auto_claims_new_page(client):
    user_id = find_or_create_user("creator@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/auto1/edit", data={"title": "Mine", "content": "Auto claimed"})
    # Page gets renamed to slugified title
    assert r.status_code == 302
    assert r.headers["Location"] == "/mine"
    page_meta = get_page_meta("mine", user_id)
    assert page_meta["user_id"] == user_id


# Auto-claim keeps the original slug if the title-derived slug is already taken
def test_auto_claim_no_rename_on_slug_conflict(client):
    user_id = find_or_create_user("conflict@example.com")
    # Create an existing page with the slug "taken" owned by the same user
    save_page("taken", "# Taken\n\nExisting", False)
    page_meta = get_page_meta("taken")
    claim_page(page_meta["id"], user_id)

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/auto2/edit", data={"title": "Taken", "content": "New"})
    assert r.status_code == 302
    # Keeps original slug since user already has a "taken" page
    assert r.headers["Location"] == "/auto2"


# Completing the claim flow renames the random slug to one derived from the page title
def test_claim_renames_slug_from_title(client):
    client.post("/cf3b/edit", data={"title": "The Brand Age", "content": "Essay"})
    client.post("/cf3b/claim", data={"email": "slugtest@example.com"})
    code = create_verification_code("slugtest@example.com", "claim")
    client.post(
        "/cf3b/claim/verify", data={"code": code, "email": "slugtest@example.com"}
    )
    client.post("/cf3b/claim/setup", data={"name": "Slug User"})
    r = client.post("/cf3b/claim/address", data={"username": "sluguser"})
    assert r.status_code == 302
    user_id = find_or_create_user("slugtest@example.com")
    assert "/the-brand-age" in r.headers["Location"]
    assert get_page_meta("the-brand-age", user_id) is not None
    assert get_page_meta("cf3b") is None


# -- Old slug redirects --


# Old slug 301-redirects to the new slug after a claim rename
def test_old_slug_redirects_after_claim_rename(client):
    client.post("/xk9f/edit", data={"title": "My Great Post", "content": "Body"})
    client.post("/xk9f/claim", data={"email": "redir@example.com"})
    code = create_verification_code("redir@example.com", "claim")
    client.post("/xk9f/claim/verify", data={"code": code, "email": "redir@example.com"})
    client.post("/xk9f/claim/setup", data={"name": "Redir User"})
    client.post("/xk9f/claim/address", data={"username": "rediruser"})
    r = client.get("/xk9f")
    assert r.status_code == 301
    assert "/my-great-post" in r.headers["Location"]
    assert "rediruser" in r.headers["Location"]


# Old slug redirects work on subdomains too
def test_old_slug_redirects_on_subdomain(client):
    user_id = find_or_create_user("subredir@example.com")
    set_user_username(user_id, "subredir")
    update_user_settings(user_id, "Sub Redir", "subredir")
    save_page("old-slug", "# New Title\n\nContent", False, user_id)
    page = get_page_meta("old-slug", user_id)
    from db import rename_page

    rename_page(page["id"], "new-title")
    r = client.get(
        "/old-slug",
        headers={"Host": "subredir.jottit.localhost:8000"},
    )
    assert r.status_code == 301
    assert "/new-title" in r.headers["Location"]


# A truly nonexistent slug still returns 404
def test_nonexistent_original_slug_still_404(client):
    r = client.get("/totally-bogus")
    assert r.status_code == 404


# Old slug redirects work for unclaimed pages after rename
def test_old_slug_redirects_unclaimed_page(client):
    save_page("rand123", "# Nice Title\n\nBody", False)
    page = get_page_meta("rand123")
    from db import rename_page

    rename_page(page["id"], "nice-title")
    r = client.get("/rand123")
    assert r.status_code == 301
    assert "/nice-title" in r.headers["Location"]


# -- User settings --


# Settings page redirects to sign-in when logged out
def test_settings_requires_signin(client):
    r = client.get("/settings")
    assert r.status_code == 302
    assert "/signin" in r.headers["Location"]


# Settings page shows name, bio, address, export, and sign out
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


# Subdomain settings page shows address form
def test_settings_subdomain_shows_form(client):
    user_id = find_or_create_user("setsub@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/settings/subdomain")
    assert r.status_code == 200
    assert b"Address" in r.data
    assert b".jottit.org" in r.data


# Saving subdomain updates the username
def test_settings_subdomain_save(client):
    user_id = find_or_create_user("setsub2@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/settings/subdomain", data={"username": "myname"})
    assert r.status_code == 302

    user = get_user(user_id)
    assert user["username"] == "myname"


# Invalid username format is rejected
def test_settings_subdomain_invalid_username(client):
    user_id = find_or_create_user("settings3@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/settings/subdomain", data={"username": "BAD!"})
    assert r.status_code == 200
    assert b"lowercase" in r.data


# Duplicate username is rejected
def test_settings_subdomain_username_uniqueness(client):
    user_id1 = find_or_create_user("settings4@example.com")
    set_user_username(user_id1, "taken")

    user_id2 = find_or_create_user("settings5@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id2

    r = client.post("/settings/subdomain", data={"username": "taken"})
    assert r.status_code == 200
    assert b"already taken" in r.data


# Export settings page renders with a download option
def test_settings_export_page(client):
    user_id = find_or_create_user("setexp@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/settings/export")
    assert r.status_code == 200
    assert b"Download" in r.data


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


# -- Subdomain routing --


def _create_user_with_username(client, email, username, slug):
    user_id = find_or_create_user(email)
    set_user_username(user_id, username)
    save_page(slug, "# Test\n\nContent", False)
    page_meta = get_page_meta(slug)
    claim_page(page_meta["id"], user_id)
    return user_id


# Visiting a claimed page's slug on the main domain redirects to the owner's subdomain
def test_slug_redirects_to_subdomain(client):
    _create_user_with_username(client, "sd@example.com", "mysite", "sd1")
    r = client.get("/sd1")
    assert r.status_code == 302
    assert "mysite.jottit.localhost:8000" in r.headers["Location"]


# Subdomain homepage lists the user's pages
def test_subdomain_home_lists_pages(client):
    user_id = _create_user_with_username(client, "sub@example.com", "subuser", "subp1")
    save_page("subp2", "# Second\n\nMore content", False)
    page_meta = get_page_meta("subp2")
    claim_page(page_meta["id"], user_id)

    from db import update_user_settings

    update_user_settings(user_id, "Sub User", "subuser")

    host = "subuser.jottit.localhost:8000"
    r = client.get("/", headers={"Host": host})
    assert r.status_code == 200
    assert b"Sub User" in r.data
    assert b"subp1" in r.data
    assert b"subp2" in r.data


# Subdomain serves the correct page content
def test_subdomain_serves_page(client):
    _create_user_with_username(client, "sdp@example.com", "sdpuser", "sdpage")
    host = "sdpuser.jottit.localhost:8000"
    r = client.get("/sdpage", headers={"Host": host})
    assert r.status_code == 200
    assert b"Content" in r.data


# Subdomain pages show the user's name as site title with h-card markup
def test_subdomain_page_shows_site_title(client):
    from db import update_user_settings

    user_id = _create_user_with_username(
        client, "sdt@example.com", "sdtuser", "sdtpage"
    )
    update_user_settings(user_id, "My Site Title", "sdtuser")
    host = "sdtuser.jottit.localhost:8000"
    r = client.get("/sdtpage", headers={"Host": host})
    assert r.status_code == 200
    body = r.data.decode()
    assert "My Site Title" in body
    assert "h-card" in body
    assert 'class="p-name u-url"' in body


# A subdomain returns 404 for pages belonging to other users
def test_subdomain_404_for_other_users_page(client):
    _create_user_with_username(client, "sdp1@example.com", "user1", "page1")
    _create_user_with_username(client, "sdp2@example.com", "user2", "page2")
    host = "user1.jottit.localhost:8000"
    r = client.get("/page2", headers={"Host": host})
    assert r.status_code == 404


# -- RSS Feed --


# Single-page RSS feed returns valid RSS XML with title and content
def test_rss_feed(client):
    client.post("/feed1/edit", data={"title": "Hello", "content": "World"})
    r = client.get("/feed1/feed.xml")
    assert r.status_code == 200
    assert r.content_type == "application/rss+xml; charset=utf-8"
    assert b"<title>Hello</title>" in r.data
    assert b"World" in r.data
    assert b'<rss version="2.0"' in r.data


# RSS feed for nonexistent page returns 404
def test_rss_feed_nonexistent(client):
    r = client.get("/nope/feed.xml")
    assert r.status_code == 404


# RSS feed includes source markdown in a custom element
def test_rss_feed_has_source_markdown(client):
    client.post("/feed5/edit", data={"title": "T", "content": "**bold**"})
    r = client.get("/feed5/feed.xml")
    assert b"<source:markdown>" in r.data
    assert b"**bold**" in r.data


# -- JSON Feed --


# Single-page JSON feed returns valid JSON Feed 1.1 with content and source markdown
def test_json_feed(client):
    client.post("/jf1/edit", data={"title": "Hello", "content": "World"})
    r = client.get("/jf1/feed.json")
    assert r.status_code == 200
    assert r.content_type == "application/feed+json; charset=utf-8"
    feed = json.loads(r.data)
    assert feed["version"] == "https://jsonfeed.org/version/1.1"
    assert feed["title"] == "Hello"
    assert len(feed["items"]) == 1
    assert feed["items"][0]["title"] == "Hello"
    assert "World" in feed["items"][0]["content_html"]
    assert feed["items"][0]["_source_markdown"] == "World"


# JSON feed for nonexistent page returns 404
def test_json_feed_nonexistent(client):
    r = client.get("/nope/feed.json")
    assert r.status_code == 404


# -- Feed discovery --


# Published pages include RSS and JSON feed discovery link tags
def test_page_has_feed_discovery_links(client):
    client.post("/disc1/edit", data={"title": "T", "content": "X"})
    r = client.get("/disc1")
    assert b'type="application/rss+xml"' in r.data
    assert b"/disc1/feed.xml" in r.data
    assert b'type="application/feed+json"' in r.data
    assert b"/disc1/feed.json" in r.data


# -- Site-level feeds --


# Subdomain RSS feed includes all the user's pages with source markdown
def test_site_rss_feed(client):
    user_id = _create_user_with_username(
        client, "rsssite@example.com", "rsssite", "rp1"
    )
    save_page("rp2", "# Second Post\n\n**bold**", False)
    page_meta = get_page_meta("rp2")
    claim_page(page_meta["id"], user_id)

    host = "rsssite.jottit.localhost:8000"
    r = client.get("/feed.xml", headers={"Host": host})
    assert r.status_code == 200
    assert r.content_type == "application/rss+xml; charset=utf-8"
    assert b'<rss version="2.0"' in r.data
    assert b"<source:markdown>" in r.data
    assert b"**bold**" in r.data
    assert b"<title>Second Post</title>" in r.data
    assert b"<title>Test</title>" in r.data


# Subdomain JSON feed includes all the user's pages
def test_site_json_feed(client):
    user_id = _create_user_with_username(
        client, "jsonsite@example.com", "jsonsite", "jp1"
    )
    save_page("jp2", "# Page Two\n\nsome text", False)
    page_meta = get_page_meta("jp2")
    claim_page(page_meta["id"], user_id)

    host = "jsonsite.jottit.localhost:8000"
    r = client.get("/feed.json", headers={"Host": host})
    assert r.status_code == 200
    assert r.content_type == "application/feed+json; charset=utf-8"
    feed = json.loads(r.data)
    assert feed["version"] == "https://jsonfeed.org/version/1.1"
    assert len(feed["items"]) == 2
    titles = {item["title"] for item in feed["items"]}
    assert "Page Two" in titles
    assert "Test" in titles
    assert feed["items"][0]["_source_markdown"]


# Subdomain homepage includes feed discovery links
def test_site_feed_discovery_links(client):
    _create_user_with_username(client, "discsite@example.com", "discsite", "dp1")
    host = "discsite.jottit.localhost:8000"
    r = client.get("/", headers={"Host": host})
    assert b'type="application/rss+xml"' in r.data
    assert b"/feed.xml" in r.data
    assert b'type="application/feed+json"' in r.data
    assert b"/feed.json" in r.data


# Unlisted pages are excluded from site feeds
def test_site_feed_excludes_unlisted(client):
    user_id = _create_user_with_username(
        client, "feedlist@example.com", "feedlist", "flp1"
    )
    save_page("flp2", "# Unlisted\n\nHidden", False)
    page_meta = get_page_meta("flp2")
    claim_page(page_meta["id"], user_id)
    update_page_listing(page_meta["id"], "unlisted")

    host = "feedlist.jottit.localhost:8000"
    r = client.get("/feed.xml", headers={"Host": host})
    assert b"<title>Test</title>" in r.data
    assert b"Unlisted" not in r.data

    r = client.get("/feed.json", headers={"Host": host})
    feed = json.loads(r.data)
    assert len(feed["items"]) == 1
    assert feed["items"][0]["title"] == "Test"


# Pinned pages are included in site feeds
def test_site_feed_includes_pinned(client):
    user_id = _create_user_with_username(
        client, "feedpin@example.com", "feedpin", "fpp1"
    )
    update_page_listing(get_page_meta("fpp1", user_id)["id"], "pinned")

    host = "feedpin.jottit.localhost:8000"
    r = client.get("/feed.json", headers={"Host": host})
    feed = json.loads(r.data)
    assert len(feed["items"]) == 1
    assert feed["items"][0]["title"] == "Test"


# Site-level feeds on the main domain return 404
def test_site_feed_404_on_main_domain(client):
    r = client.get("/feed.xml")
    assert r.status_code == 404
    r = client.get("/feed.json")
    assert r.status_code == 404


# -- Draft visibility --


# Draft pages are visible to their creator
def test_draft_visible_to_creator(client):
    client.post(
        "/dv1/edit", data={"title": "Secret", "content": "Draft content", "draft": "on"}
    )
    r = client.get("/dv1")
    assert r.status_code == 200
    assert b"draft" in r.data.lower()


# Draft pages return 404 for non-creators
def test_draft_hidden_from_non_creator(client):
    client.post(
        "/dv2/edit", data={"title": "Secret", "content": "Draft content", "draft": "on"}
    )
    with client.session_transaction() as sess:
        sess.clear()
    r = client.get("/dv2")
    assert r.status_code == 404


# -- Delete page --


# Page owner can delete their page
def test_owner_can_delete_page(client):
    user_id = find_or_create_user("del@example.com")
    save_page("del1", "# T\n\nX", False)
    page_meta = get_page_meta("del1")
    claim_page(page_meta["id"], user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post("/del1/delete", data={"confirmation": "delete"})
    assert r.status_code == 302
    r = client.get("/del1")
    assert r.status_code == 404


# Non-owner cannot delete a page
def test_non_owner_cannot_delete(client):
    user_id = find_or_create_user("del2@example.com")
    save_page("del2", "# T\n\nX", False)
    page_meta = get_page_meta("del2")
    claim_page(page_meta["id"], user_id)

    r = client.post("/del2/delete", data={"confirmation": "delete"})
    assert r.status_code == 302
    # Non-owner can't find the claimed page, gets redirected away
    assert r.headers["Location"] in ("/del2", "/")


# -- Listing --


# New pages default to "listed" listing status
def test_listing_default_is_listed(client):
    user_id = _create_user_with_username(
        client, "list1@example.com", "listuser1", "lp1"
    )
    page_meta = get_page_meta("lp1", user_id)
    assert page_meta["listing"] == "listed"


# Owner can change a page's listing to "unlisted"
def test_update_listing(client):
    user_id = _create_user_with_username(
        client, "list2@example.com", "listuser2", "lp2"
    )
    host = "listuser2.jottit.localhost:8000"
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post(
        "/lp2/listing", data={"listing": "unlisted"}, headers={"Host": host}
    )
    assert r.status_code == 302
    page_meta = get_page_meta("lp2", user_id)
    assert page_meta["listing"] == "unlisted"


# Unlisted pages don't appear on the subdomain homepage
def test_unlisted_page_hidden_from_subdomain(client):
    user_id = _create_user_with_username(
        client, "list3@example.com", "listuser3", "lp3"
    )
    host = "listuser3.jottit.localhost:8000"
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/lp3/listing", data={"listing": "unlisted"}, headers={"Host": host})
    r = client.get("/", headers={"Host": "listuser3.jottit.localhost:8000"})
    assert b"lp3" not in r.data


# Pinned pages appear before other pages on the subdomain homepage
def test_pinned_page_shown_first(client):
    user_id = _create_user_with_username(
        client, "list4@example.com", "listuser4", "lp4a"
    )
    save_page("lp4b", "# Second\n\nContent", False)
    page_meta2 = get_page_meta("lp4b")
    claim_page(page_meta2["id"], user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    # lp4b is newer, so it would normally appear first
    # Pin lp4a so it appears before lp4b
    host = "listuser4.jottit.localhost:8000"
    client.post("/lp4a/listing", data={"listing": "pinned"}, headers={"Host": host})
    r = client.get("/", headers={"Host": "listuser4.jottit.localhost:8000"})
    body = r.data.decode()
    assert "lp4a" in body
    assert "lp4b" in body
    assert body.index("lp4a") < body.index("lp4b")


# Only pinned pages show a pin icon
def test_pinned_page_shows_pin_icon(client):
    user_id = _create_user_with_username(
        client, "pinicon@example.com", "pinicon", "pip1"
    )
    save_page("pip2", "# Not Pinned\n\nContent", False)
    page_meta2 = get_page_meta("pip2")
    claim_page(page_meta2["id"], user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    host = "pinicon.jottit.localhost:8000"
    client.post("/pip1/listing", data={"listing": "pinned"}, headers={"Host": host})
    r = client.get("/", headers={"Host": host})
    body = r.data.decode()
    assert 'class="pin-icon"' in body
    assert body.count('class="pin-icon"') == 1


# Non-owner gets 403 when trying to change listing
def test_non_owner_cannot_update_listing(client):
    _create_user_with_username(client, "list5@example.com", "listuser5", "lp5")
    host = "listuser5.jottit.localhost:8000"
    r = client.post(
        "/lp5/listing", data={"listing": "unlisted"}, headers={"Host": host}
    )
    assert r.status_code == 403


# -- Export --


# Exporting a page returns a zip file with the correct filename
def test_export_zip(client):
    client.post("/exp1/edit", data={"title": "T", "content": "X"})
    r = client.get("/exp1/export")
    assert r.status_code == 200
    assert r.content_type == "application/zip"
    assert 'filename="exp1.zip"' in r.headers["Content-Disposition"]


# -- Microformats --


# Published pages include h-entry, p-name, e-content, dt-published, and u-url microformat classes
def test_page_has_h_entry_markup(client):
    client.post("/mf1/edit", data={"title": "Hello", "content": "World"})
    r = client.get("/mf1")
    body = r.data.decode()
    assert 'class="page h-entry"' in body
    assert 'class="p-name"' in body
    assert 'class="e-content"' in body
    assert 'class="dt-published' in body
    assert "datetime=" in body
    assert 'class="u-url"' in body
    assert 'href="/mf1"' in body


# -- Wikilinks --


# slugify() converts titles to lowercase hyphenated slugs
def test_slugify():
    assert slugify("Good Writing") == "good-writing"
    assert slugify("Hello World!") == "hello-world"
    assert slugify("  Multiple   Spaces  ") == "multiple-spaces"
    assert slugify("Already-Slugged") == "already-slugged"
    assert slugify("123 Numbers") == "123-numbers"


# [[About]] wikilinks render as HTML links
def test_wikilink_renders(client):
    client.post("/wl1/edit", data={"title": "", "content": "See [[About]]"})
    r = client.get("/wl1")
    assert b'<a href="/about">About</a>' in r.data


# -- Avatar and Bio --


# Profile settings includes a bio field
def test_settings_profile_shows_bio_field(client):
    user_id = find_or_create_user("bio@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/settings/profile")
    assert r.status_code == 200
    assert b"Bio" in r.data


# Saving profile persists the bio
def test_settings_profile_saves_bio(client):
    user_id = find_or_create_user("bio2@example.com")
    set_user_username(user_id, "biouser")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post(
        "/settings/profile", data={"name": "Bio User", "bio": "Hello world"}
    )
    assert r.status_code == 302

    user = get_user(user_id)
    assert user["bio"] == "Hello world"


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


# License appears in the page footer on subdomains
def test_license_shows_in_page_footer(client):
    user_id = _create_user_with_username(
        client, "licfoot@example.com", "licfoot", "lf1"
    )
    update_user_settings(user_id, "Lic Footer", "licfoot", license="cc-by-sa-4.0")

    host = "licfoot.jottit.localhost:8000"
    r = client.get("/lf1", headers={"Host": host})
    assert r.status_code == 200
    assert b"CC BY-SA 4.0" in r.data
    assert b"creativecommons.org" in r.data


# Uploading an avatar saves the image URL to the user record
@patch("routes.upload_image", return_value="/uploads/1/avatar.jpg")
@patch("routes.crop_square")
def test_avatar_upload(mock_crop, mock_upload, client):
    mock_crop.return_value = io.BytesIO(b"cropped")
    user_id = find_or_create_user("avatar@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    data = {
        "avatar": (io.BytesIO(b"fake-image-data"), "photo.jpg", "image/jpeg"),
    }
    r = client.post("/settings/avatar", data=data, content_type="multipart/form-data")
    assert r.status_code == 302
    mock_upload.assert_called_once()
    user = get_user(user_id)
    assert user["avatar"] == "/uploads/1/avatar.jpg"


# Non-image file types are rejected for avatar upload
def test_avatar_upload_rejects_invalid_type(client):
    user_id = find_or_create_user("avatar2@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    data = {
        "avatar": (io.BytesIO(b"not-an-image"), "file.txt", "text/plain"),
    }
    r = client.post("/settings/avatar", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"not allowed" in r.data
    assert b"Profile" in r.data


# Removing an avatar deletes the image and clears the user record
@patch("routes.delete_image")
def test_avatar_removal(mock_delete, client):
    user_id = find_or_create_user("avatar3@example.com")
    update_user_avatar(user_id, "/uploads/1/avatar.jpg")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/settings/avatar/delete")
    assert r.status_code == 302
    mock_delete.assert_called_once_with("1/avatar.jpg")
    user = get_user(user_id)
    assert user["avatar"] is None


# Subdomain homepage displays the user's bio with p-note microformat
def test_subdomain_home_shows_bio(client):
    user_id = _create_user_with_username(
        client, "biohome@example.com", "biohome", "bh1"
    )
    update_user_settings(user_id, "Bio Home", "biohome", "My cool bio")

    host = "biohome.jottit.localhost:8000"
    r = client.get("/", headers={"Host": host})
    assert r.status_code == 200
    assert b"My cool bio" in r.data
    assert b"p-note" in r.data


# Plain text bio renders as-is
def test_render_bio_plain_text():
    assert render_bio("Just a writer") == "Just a writer"


# Bio wikilinks render as HTML links
def test_render_bio_wikilink():
    result = render_bio("See [[About]]")
    assert '<a href="/about">About</a>' in result


# Bio markdown links render as HTML links
def test_render_bio_markdown_link():
    result = render_bio("Check [About](/about)")
    assert '<a href="/about">About</a>' in result


# Bio external links render correctly
def test_render_bio_external_link():
    result = render_bio("[Google](https://google.com)")
    assert '<a href="https://google.com">Google</a>' in result


# Bio strips dangerous HTML tags (XSS protection)
def test_render_bio_strips_html():
    result = render_bio("<script>alert('xss')</script>")
    assert "<script>" not in result


# Bio strips all HTML tags except links
def test_render_bio_strips_other_tags():
    result = render_bio("<b>bold</b> and <em>italic</em>")
    assert "<b>" not in result
    assert "<em>" not in result
    assert "bold" in result


# Subdomain homepage shows avatar with u-photo microformat
def test_subdomain_home_shows_avatar(client):
    user_id = _create_user_with_username(client, "avhome@example.com", "avhome", "ah1")
    update_user_avatar(user_id, "/uploads/test/avatar.jpg")

    host = "avhome.jottit.localhost:8000"
    r = client.get("/", headers={"Host": host})
    assert r.status_code == 200
    assert b"u-photo" in r.data
    assert b"profile-avatar" in r.data


# Subdomain homepage without avatar renders gracefully
def test_subdomain_home_no_avatar_graceful(client):
    user_id = _create_user_with_username(client, "noav@example.com", "noavuser", "na1")
    update_user_settings(user_id, "No Avatar", "noavuser")

    host = "noavuser.jottit.localhost:8000"
    r = client.get("/", headers={"Host": host})
    assert r.status_code == 200
    assert b"u-photo" not in r.data
    assert b"No Avatar" in r.data


# Subdomain pages show a profile header with avatar and bio
def test_subdomain_page_shows_profile_header(client):
    user_id = _create_user_with_username(
        client, "profpage@example.com", "profpage", "pp1"
    )
    update_user_settings(user_id, "Prof Page", "profpage", "Writer")
    update_user_avatar(user_id, "/uploads/test/avatar.jpg")

    host = "profpage.jottit.localhost:8000"
    r = client.get("/pp1", headers={"Host": host})
    assert r.status_code == 200
    assert b"profile-header" in r.data
    assert b"Writer" in r.data
    assert b"u-photo" in r.data


# -- Migrations --


# SQL migrations are applied and tracked in schema_migrations (idempotent)
def test_migration_applies_and_tracks():
    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
    test_file = os.path.join(migrations_dir, "999_test_migration.sql")
    try:
        with open(test_file, "w") as f:
            f.write(
                "CREATE TABLE IF NOT EXISTS migration_test_table (id SERIAL PRIMARY KEY);"
            )

        run_migrations()

        with get_db() as conn:
            row = conn.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'migration_test_table')"
            ).fetchone()
            assert list(row.values())[0] is True

            row = conn.execute(
                "SELECT filename FROM schema_migrations WHERE filename = '999_test_migration.sql'"
            ).fetchone()
            assert row is not None

        # Run again — should be a no-op
        run_migrations()

        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) AS cnt FROM schema_migrations WHERE filename = '999_test_migration.sql'"
            ).fetchone()
            assert count["cnt"] == 1
    finally:
        os.unlink(test_file)


# A failed migration doesn't roll back previously applied ones
def test_migration_failure_does_not_affect_previous():
    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
    good_file = os.path.join(migrations_dir, "998_good.sql")
    bad_file = os.path.join(migrations_dir, "999_bad.sql")
    try:
        with open(good_file, "w") as f:
            f.write(
                "CREATE TABLE IF NOT EXISTS migration_good_table (id SERIAL PRIMARY KEY);"
            )
        with open(bad_file, "w") as f:
            f.write("INVALID SQL STATEMENT;")

        try:
            run_migrations()
        except Exception:
            pass

        with get_db() as conn:
            # Good migration should have been applied
            row = conn.execute(
                "SELECT filename FROM schema_migrations WHERE filename = '998_good.sql'"
            ).fetchone()
            assert row is not None

            # Bad migration should not be tracked
            row = conn.execute(
                "SELECT filename FROM schema_migrations WHERE filename = '999_bad.sql'"
            ).fetchone()
            assert row is None
    finally:
        for f in [good_file, bad_file]:
            if os.path.exists(f):
                os.unlink(f)


def _load_backfill_migration():
    import importlib.util

    path = os.path.join(
        os.path.dirname(__file__), "migrations", "006_backfill_usernames.py"
    )
    spec = importlib.util.spec_from_file_location("backfill_usernames", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Backfill migration generates usernames from email prefixes
def test_backfill_usernames_from_email():
    m = _load_backfill_migration()

    user_id = find_or_create_user("alice@example.com")
    with get_db() as conn:
        conn.execute("UPDATE users SET username = NULL WHERE id = %s", (user_id,))
        conn.commit()

    with get_db() as conn:
        m.migrate(conn)
        conn.commit()

    user = get_user(user_id)
    assert user["username"] == "alice"


# Backfill adds a suffix when the derived username is already taken
def test_backfill_usernames_with_suffix_if_taken():
    m = _load_backfill_migration()

    user1 = find_or_create_user("bob@example.com")
    set_user_username(user1, "bob")

    user2 = find_or_create_user("bob@other.com")
    with get_db() as conn:
        conn.execute("UPDATE users SET username = NULL WHERE id = %s", (user2,))
        conn.commit()

    with get_db() as conn:
        m.migrate(conn)
        conn.commit()

    user = get_user(user2)
    assert user["username"] is not None
    assert user["username"].startswith("bob-")
    assert user["username"] != "bob"


# After backfill, pages are accessible on the generated subdomain
def test_backfill_usernames_makes_page_accessible(client):
    m = _load_backfill_migration()

    user_id = find_or_create_user("legacy@example.com")
    save_page("mypage", "# Hello\n\nWorld", False)
    page_meta = get_page_meta("mypage")
    claim_page(page_meta["id"], user_id)

    with get_db() as conn:
        conn.execute("UPDATE users SET username = NULL WHERE id = %s", (user_id,))
        conn.commit()

    with get_db() as conn:
        m.migrate(conn)
        conn.commit()

    user = get_user(user_id)
    host = f"{user['username']}.jottit.localhost:8000"
    r = client.get("/mypage", headers={"Host": host})
    assert r.status_code == 200


# -- Per-user slug uniqueness --


# Two different users can each have a page with the same slug
def test_two_users_same_slug(client):
    user1 = _create_user_with_username(client, "slug1@example.com", "alice", "about")
    user2 = _create_user_with_username(client, "slug2@example.com", "bob", "about")
    # Both users have /about pages
    meta1 = get_page_meta("about", user1)
    meta2 = get_page_meta("about", user2)
    assert meta1 is not None
    assert meta2 is not None
    assert meta1["id"] != meta2["id"]

    # Each subdomain shows the correct page
    r = client.get("/about", headers={"Host": "alice.jottit.localhost:8000"})
    assert r.status_code == 200

    r = client.get("/about", headers={"Host": "bob.jottit.localhost:8000"})
    assert r.status_code == 200


# New page on a subdomain gets a title-derived slug
def test_subdomain_new_page_gets_nice_slug(client):
    user_id = _create_user_with_username(client, "nice@example.com", "niceslug", "x1")
    host = "niceslug.jottit.localhost:8000"
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post(
        "/randomslug/edit",
        data={"title": "About", "content": "My about page"},
        headers={"Host": host},
    )
    assert r.status_code == 302
    assert r.headers["Location"] == "/about"
    meta = get_page_meta("about", user_id)
    assert meta is not None


# POST /new on a subdomain creates a page with a title-derived slug
def test_subdomain_new_page_gets_about_slug(client):
    user_id = _create_user_with_username(client, "about@example.com", "aboutuser", "x2")
    host = "aboutuser.jottit.localhost:8000"
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post(
        "/new",
        data={"title": "About", "content": "My about page"},
        headers={"Host": host},
    )
    assert r.status_code == 302
    assert r.headers["Location"] == "/about"
    meta = get_page_meta("about", user_id)
    assert meta is not None


# Owner visiting a nonexistent slug on their subdomain is redirected to the editor
def test_owner_visiting_nonexistent_page_redirects_to_edit(client):
    user_id = _create_user_with_username(
        client, "owner404@example.com", "owner404", "exists"
    )
    host = "owner404.jottit.localhost:8000"
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/newpage", headers={"Host": host})
    assert r.status_code == 302
    assert r.headers["Location"] == "/newpage/edit"


# Non-owner visiting a nonexistent slug on a subdomain gets 404
def test_nonowner_visiting_nonexistent_page_gets_404(client):
    _create_user_with_username(client, "vis404@example.com", "vis404", "exists2")
    host = "vis404.jottit.localhost:8000"
    r = client.get("/nope", headers={"Host": host})
    assert r.status_code == 404


# Visiting a claimed page's slug on the main domain redirects to the owner's subdomain
def test_main_domain_slug_redirects_to_owner(client):
    _create_user_with_username(client, "redir@example.com", "redir", "mypage")
    r = client.get("/mypage")
    assert r.status_code == 302
    assert "redir.jottit.localhost:8000" in r.headers["Location"]


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
