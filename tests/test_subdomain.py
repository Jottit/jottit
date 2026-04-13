from conftest import create_user_with_username
from db import (
    claim_page,
    create_verification_code,
    find_or_create_user,
    get_page_meta,
    rename_page,
    save_page,
    set_user_username,
    update_user_settings,
)

# -- Profile routing --


# Visiting a claimed page's slug on the main domain redirects to /@username
def test_slug_redirects_to_profile(client):
    create_user_with_username(client, "sd@example.com", "mysite", "sd1")
    r = client.get("/sd1")
    assert r.status_code == 302
    assert "/@mysite/sd1" in r.headers["Location"]


# Profile homepage lists the user's pages
def test_profile_home_lists_pages(client):
    user_id = create_user_with_username(client, "sub@example.com", "subuser", "subp1")
    save_page("subp2", "# Second\n\nMore content", "listed")
    page_meta = get_page_meta("subp2")
    claim_page(page_meta["id"], user_id)

    update_user_settings(user_id, "Sub User", "subuser")

    r = client.get("/@subuser")
    assert r.status_code == 200
    assert b"Sub User" in r.data
    assert b"subp1" in r.data
    assert b"subp2" in r.data


# Profile serves the correct page content
def test_profile_serves_page(client):
    create_user_with_username(client, "sdp@example.com", "sdpuser", "sdpage")
    r = client.get("/@sdpuser/sdpage")
    assert r.status_code == 200
    assert b"Content" in r.data


# Profile pages show the user's name as site title with h-card markup
def test_profile_page_shows_site_title(client):
    user_id = create_user_with_username(client, "sdt@example.com", "sdtuser", "sdtpage")
    update_user_settings(user_id, "My Site Title", "sdtuser")
    r = client.get("/@sdtuser/sdtpage")
    assert r.status_code == 200
    body = r.data.decode()
    assert "My Site Title" in body
    assert "h-card" in body
    assert "p-name u-url" in body


# A profile returns 404 for pages belonging to other users
def test_profile_404_for_other_users_page(client):
    create_user_with_username(client, "sdp1@example.com", "user1", "page1")
    create_user_with_username(client, "sdp2@example.com", "user2", "page2")
    r = client.get("/@user1/page2")
    assert r.status_code == 404


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
    assert "/@rediruser" in r.headers["Location"]


# Old slug redirects work on profiles too
def test_old_slug_redirects_on_profile(client):
    user_id = find_or_create_user("subredir@example.com")
    set_user_username(user_id, "subredir")
    update_user_settings(user_id, "Sub Redir", "subredir")
    save_page("old-slug", "# New Title\n\nContent", "listed", user_id)
    page = get_page_meta("old-slug", user_id)

    rename_page(page["id"], "new-title")
    r = client.get("/@subredir/old-slug")
    assert r.status_code == 301
    assert "/new-title" in r.headers["Location"]


# A truly nonexistent slug still returns 404
def test_nonexistent_original_slug_still_404(client):
    r = client.get("/totally-bogus")
    assert r.status_code == 404


# Old slug redirects work for unclaimed pages after rename
def test_old_slug_redirects_unclaimed_page(client):
    save_page("rand123", "# Nice Title\n\nBody", "listed")
    page = get_page_meta("rand123")

    rename_page(page["id"], "nice-title")
    r = client.get("/rand123")
    assert r.status_code == 301
    assert "/nice-title" in r.headers["Location"]


# -- Visibility --


# New pages by signed-in users default to "private" visibility
def test_visibility_default_is_private(client):
    from db import find_or_create_user, set_user_username

    user_id = find_or_create_user("list1@example.com")
    set_user_username(user_id, "listuser1")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post(
        "/@listuser1/newpage/edit",
        data={"content": "# Test\n\nContent"},
    )
    page_meta = get_page_meta("newpage", user_id)
    assert page_meta is not None
    assert page_meta["visibility"] == "private"


# Owner can change a page's visibility to "unlisted"
def test_update_visibility(client):
    user_id = create_user_with_username(client, "list2@example.com", "listuser2", "lp2")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post("/@listuser2/lp2/visibility", data={"visibility": "unlisted"})
    assert r.status_code == 302
    page_meta = get_page_meta("lp2", user_id)
    assert page_meta["visibility"] == "unlisted"


# Private pages are blocked for non-owners
def test_private_page_blocked_for_non_owner(client):
    from db import update_page_visibility

    user_id = create_user_with_username(
        client, "priv@example.com", "privuser", "privpage"
    )
    page_meta = get_page_meta("privpage", user_id)
    update_page_visibility(page_meta["id"], "private")
    with client.session_transaction() as sess:
        sess.clear()
    r = client.get("/@privuser/privpage")
    assert r.status_code == 404


# Private pages are accessible to the owner
def test_private_page_accessible_for_owner(client):
    from db import update_page_visibility

    user_id = create_user_with_username(
        client, "privo@example.com", "privowner", "privownpage"
    )
    page_meta = get_page_meta("privownpage", user_id)
    update_page_visibility(page_meta["id"], "private")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/@privowner/privownpage")
    assert r.status_code == 200


# Private pages don't appear on the profile for visitors
def test_private_page_hidden_from_profile(client):
    from db import update_page_visibility

    user_id = create_user_with_username(
        client, "privh@example.com", "privhidden", "privhpage"
    )
    page_meta = get_page_meta("privhpage", user_id)
    update_page_visibility(page_meta["id"], "private")
    with client.session_transaction() as sess:
        sess.clear()
    r = client.get("/@privhidden")
    assert b"privhpage" not in r.data


# Unlisted pages don't appear on the profile homepage
def test_unlisted_page_hidden_from_profile(client):
    user_id = create_user_with_username(client, "list3@example.com", "listuser3", "lp3")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/@listuser3/lp3/visibility", data={"visibility": "unlisted"})
    with client.session_transaction() as sess:
        sess.clear()
    r = client.get("/@listuser3")
    assert b"lp3" not in r.data


# Pinned pages appear before other pages on the profile homepage
def test_pinned_page_shown_first(client):
    user_id = create_user_with_username(
        client, "list4@example.com", "listuser4", "lp4a"
    )
    save_page("lp4b", "# Second\n\nContent", "listed")
    page_meta2 = get_page_meta("lp4b")
    claim_page(page_meta2["id"], user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    # lp4b is newer, so it would normally appear first
    # Pin lp4a so it appears before lp4b
    client.post("/@listuser4/lp4a/visibility", data={"visibility": "pinned"})
    r = client.get("/@listuser4")
    body = r.data.decode()
    assert "lp4a" in body
    assert "lp4b" in body
    assert body.index("lp4a") < body.index("lp4b")


# Only pinned pages show a pin icon
def test_pinned_page_shows_pin_icon(client):
    user_id = create_user_with_username(
        client, "pinicon@example.com", "pinicon", "pip1"
    )
    save_page("pip2", "# Not Pinned\n\nContent", "listed")
    page_meta2 = get_page_meta("pip2")
    claim_page(page_meta2["id"], user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/@pinicon/pip1/visibility", data={"visibility": "pinned"})
    r = client.get("/@pinicon")
    body = r.data.decode()
    assert 'class="pin-icon"' in body
    assert body.count('class="pin-icon"') == 1


# Non-owner gets 403 when trying to change visibility
def test_non_owner_cannot_update_visibility(client):
    create_user_with_username(client, "list5@example.com", "listuser5", "lp5")
    r = client.post("/@listuser5/lp5/visibility", data={"visibility": "unlisted"})
    assert r.status_code == 403


# -- Per-user slug uniqueness --


# Two different users can each have a page with the same slug
def test_two_users_same_slug(client):
    user1 = create_user_with_username(client, "slug1@example.com", "alice", "about")
    user2 = create_user_with_username(client, "slug2@example.com", "bob", "about")
    # Both users have /about pages
    meta1 = get_page_meta("about", user1)
    meta2 = get_page_meta("about", user2)
    assert meta1 is not None
    assert meta2 is not None
    assert meta1["id"] != meta2["id"]

    # Each profile shows the correct page
    r = client.get("/@alice/about")
    assert r.status_code == 200

    r = client.get("/@bob/about")
    assert r.status_code == 200


# New page on a profile gets a title-derived slug
def test_profile_new_page_gets_nice_slug(client):
    user_id = create_user_with_username(client, "nice@example.com", "niceslug", "x1")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post(
        "/@niceslug/randomslug/edit",
        data={"title": "About", "content": "My about page"},
    )
    assert r.status_code == 302
    assert r.headers["Location"] == "/@niceslug/about"
    meta = get_page_meta("about", user_id)
    assert meta is not None


# POST /new on a profile creates a page with a title-derived slug
def test_profile_new_page_gets_about_slug(client):
    user_id = create_user_with_username(client, "about@example.com", "aboutuser", "x2")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post(
        "/@aboutuser/new",
        data={"title": "About", "content": "My about page"},
    )
    assert r.status_code == 302
    assert r.headers["Location"] == "/@aboutuser/about"
    meta = get_page_meta("about", user_id)
    assert meta is not None


# Owner visiting a nonexistent slug on their profile is redirected to the editor
def test_owner_visiting_nonexistent_page_redirects_to_edit(client):
    user_id = create_user_with_username(
        client, "owner404@example.com", "owner404", "exists"
    )
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/@owner404/newpage")
    assert r.status_code == 302
    assert r.headers["Location"] == "/@owner404/newpage/edit"


# Non-owner visiting a nonexistent slug on a profile gets 404
def test_nonowner_visiting_nonexistent_page_gets_404(client):
    create_user_with_username(client, "vis404@example.com", "vis404", "exists2")
    r = client.get("/@vis404/nope")
    assert r.status_code == 404


# Visiting a claimed page's slug on the main domain redirects to /@owner
def test_main_domain_slug_redirects_to_owner(client):
    create_user_with_username(client, "redir@example.com", "redir", "mypage")
    r = client.get("/mypage")
    assert r.status_code == 302
    assert "/@redir/mypage" in r.headers["Location"]


# License appears in the page footer on profiles
def test_license_shows_in_page_footer(client):
    user_id = create_user_with_username(client, "licfoot@example.com", "licfoot", "lf1")
    update_user_settings(user_id, "Lic Footer", "licfoot", license="cc-by-sa-4.0")

    r = client.get("/@licfoot/lf1")
    assert r.status_code == 200
    assert b"CC BY-SA 4.0" in r.data
    assert b"creativecommons.org" in r.data


# Old subdomain URLs redirect to /@username equivalents
def test_subdomain_redirects_to_profile(client):
    create_user_with_username(client, "legacy@example.com", "legacyuser", "lp1")
    r = client.get("/lp1", headers={"Host": "legacyuser.jottit.localhost:8000"})
    assert r.status_code == 301
    assert "/@legacyuser" in r.headers["Location"]


# INDEX.md: page with slug "index" renders as profile content
def test_index_page_renders_on_profile(client):
    user_id = find_or_create_user("idx@example.com")
    set_user_username(user_id, "idxuser")
    save_page("index", "# Welcome\n\nThis is my profile.", "listed")
    page_meta = get_page_meta("index")
    claim_page(page_meta["id"], user_id)
    r = client.get("/@idxuser")
    assert r.status_code == 200
    assert b"This is my profile" in r.data


# INDEX.md: private index page visible to owner but not visitors
def test_index_page_private_hidden_from_visitors(client):
    from db import update_page_visibility

    user_id = find_or_create_user("idxp@example.com")
    set_user_username(user_id, "idxpriv")
    save_page("index", "# Secret\n\nPrivate index.", "listed")
    page_meta = get_page_meta("index")
    claim_page(page_meta["id"], user_id)
    update_page_visibility(page_meta["id"], "private")
    with client.session_transaction() as sess:
        sess.clear()
    r = client.get("/@idxpriv")
    assert b"Private index" not in r.data


# INDEX.md: private index page visible to owner
def test_index_page_private_visible_to_owner(client):
    from db import update_page_visibility

    user_id = find_or_create_user("idxo@example.com")
    set_user_username(user_id, "idxown")
    save_page("index", "# My Index\n\nOwner sees this.", "listed")
    page_meta = get_page_meta("index")
    claim_page(page_meta["id"], user_id)
    update_page_visibility(page_meta["id"], "private")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/@idxown")
    assert b"Owner sees this" in r.data
