from db import (
    claim_page,
    create_page_secret,
    create_verification_code,
    find_or_create_user,
    get_page_meta,
    get_user,
    save_page,
    set_user_username,
    update_user_settings,
)


def _set_page_token(client, slug):
    """Create a page secret and set the token cookie so the claim flow is accessible."""
    page_meta = get_page_meta(slug)
    secret = create_page_secret(page_meta["id"])
    client.set_cookie(f"page_token_{slug}", secret)
    return secret


# -- Session-based edit protection --


# The session that created a page can edit it (via page token cookie)
def test_creator_can_edit_unclaimed_page(client):
    r = client.post("/prot1/edit", data={"title": "T", "content": "X"})
    # Follow the ?token= redirect to set the cookie
    location = r.headers["Location"]
    if "?token=" in location:
        client.get(location)
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


# -- Claim banner --


# Creator with page token sees the claim banner on their unclaimed page
def test_unclaimed_page_shows_claim_banner_to_creator(client):
    client.post("/uncl/edit", data={"title": "T", "content": "X"})
    _set_page_token(client, "uncl")
    r = client.get("/uncl")
    assert b"claim-banner" in r.data


# Visitor without page token does NOT see the claim banner
def test_unclaimed_page_hides_claim_banner_without_token(client):
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
    _set_page_token(client, "cf1")
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
    _set_page_token(client, "cf3")

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

    # Step 4: address — redirects to homepage
    r = client.post("/cf3/claim/address", data={"username": "testuser"})
    assert r.status_code == 302
    assert r.headers["Location"] == "/"

    claimed_user_id = find_or_create_user("user@example.com")
    page_meta = get_page_meta("my-great-page", claimed_user_id)
    assert page_meta["user_id"] is not None

    user = get_user(page_meta["user_id"])
    assert user["username"] == "testuser"
    assert user["name"] == "Test User"


# Claim flow persists the user's name and username
def test_claim_sets_name_and_username(client):
    client.post("/cfun/edit", data={"title": "Unique Title", "content": "X"})
    _set_page_token(client, "cfun")

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
    _set_page_token(client, "cf4")
    client.post("/cf4/claim", data={"email": "user@example.com"})
    r = client.post(
        "/cf4/claim/verify", data={"code": "000000", "email": "user@example.com"}
    )
    assert r.status_code == 200
    assert b"Invalid" in r.data


# Submitting email during claim stores it in the session
def test_claim_stores_email_in_session(client):
    client.post("/cf5/edit", data={"title": "T", "content": "X"})
    _set_page_token(client, "cf5")
    client.post("/cf5/claim", data={"email": "session@example.com"})
    with client.session_transaction() as sess:
        assert sess.get("claim_email") == "session@example.com"


# Submitting a different email in verification than in the session is rejected
def test_claim_rejects_email_substitution(client):
    client.post("/cf6/edit", data={"title": "T", "content": "X"})
    _set_page_token(client, "cf6")
    client.post("/cf6/claim", data={"email": "real@example.com"})
    code = create_verification_code("real@example.com", "claim")
    r = client.post(
        "/cf6/claim/verify", data={"code": code, "email": "attacker@example.com"}
    )
    assert r.status_code == 302
    assert "/cf6/claim" in r.headers["Location"]


# Sign-in stores the email in the session
def test_signin_stores_email_in_session(client):
    find_or_create_user("signin@example.com")
    client.post("/signin", data={"email": "signin@example.com"})
    with client.session_transaction() as sess:
        assert sess.get("signin_email") == "signin@example.com"


# After completing the claim flow, claim-related session keys are removed
def test_claim_cleans_up_session(client):
    client.post("/cf7/edit", data={"title": "T", "content": "X"})
    _set_page_token(client, "cf7")
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
    _set_page_token(client, "cf8")
    r = client.get("/cf8/claim/setup")
    assert r.status_code == 302
    assert "/cf8/claim" in r.headers["Location"]


# Empty name is rejected with a validation error
def test_claim_setup_validates_name(client):
    client.post("/cf10/edit", data={"title": "T", "content": "X"})
    _set_page_token(client, "cf10")
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
    _set_page_token(client, "cf9")
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
    _set_page_token(client, "cf11")
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
    _set_page_token(client, "cf12")
    r = client.get("/cf12/claim/address")
    assert r.status_code == 302
    assert "/cf12/claim" in r.headers["Location"]


# A returning user who already has a name/username skips the setup steps
def test_returning_user_skips_setup(client):
    # First claim: set up name and username
    client.post("/ret1/edit", data={"title": "First Page", "content": "X"})
    _set_page_token(client, "ret1")
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
    _set_page_token(client, "ret2")
    client.post("/ret2/claim", data={"email": "returning@example.com"})
    code = create_verification_code("returning@example.com", "claim")
    r = client.post(
        "/ret2/claim/verify", data={"code": code, "email": "returning@example.com"}
    )
    assert r.status_code == 302
    # Should skip setup and go straight to homepage
    assert r.headers["Location"] == "/"

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
    _set_page_token(client, "pres1")
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
    _set_page_token(client, "cf13")
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


# Sign-in with unknown email is rejected
def test_signin_rejects_unknown_email(client):
    r = client.post("/signin", data={"email": "nobody@example.com"})
    assert r.status_code == 200
    assert b"Email not found" in r.data
    assert b"Create a page" in r.data
    assert b"Try another email" in r.data


# Full sign-in: submit email, verify code, session contains user_id
def test_signin_full_flow(client):
    find_or_create_user("user@example.com")

    r = client.post("/signin", data={"email": "user@example.com"})
    assert r.status_code == 302
    assert "/signin/verify" in r.headers["Location"]

    r = client.get("/signin/verify")
    assert r.status_code == 200
    assert b"Check your email" in r.data

    code = create_verification_code("user@example.com", "signin")

    r = client.post("/signin/verify", data={"code": code, "email": "user@example.com"})
    assert r.status_code == 302
    assert r.headers["Location"] == "/"

    with client.session_transaction() as sess:
        assert "user_id" in sess


# Sign-in with username redirects to profile
def test_signin_with_username_redirects_to_profile(client):
    user_id = find_or_create_user("signinuser@example.com")
    set_user_username(user_id, "signinuser")

    client.post("/signin", data={"email": "signinuser@example.com"})
    code = create_verification_code("signinuser@example.com", "signin")
    r = client.post(
        "/signin/verify", data={"code": code, "email": "signinuser@example.com"}
    )
    assert r.status_code == 302
    assert r.headers["Location"] == "/@signinuser"


# Invalid sign-in code shows an error
def test_signin_invalid_code(client):
    find_or_create_user("user@example.com")

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
    _set_page_token(client, "cf3b")
    client.post("/cf3b/claim", data={"email": "slugtest@example.com"})
    code = create_verification_code("slugtest@example.com", "claim")
    client.post(
        "/cf3b/claim/verify", data={"code": code, "email": "slugtest@example.com"}
    )
    client.post("/cf3b/claim/setup", data={"name": "Slug User"})
    r = client.post("/cf3b/claim/address", data={"username": "sluguser"})
    assert r.status_code == 302
    user_id = find_or_create_user("slugtest@example.com")
    assert r.headers["Location"] == "/"
    assert get_page_meta("the-brand-age", user_id) is not None
    assert get_page_meta("cf3b") is None
