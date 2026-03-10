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

# -- Subdomain routing --


# Visiting a claimed page's slug on the main domain redirects to the owner's subdomain
def test_slug_redirects_to_subdomain(client):
    create_user_with_username(client, "sd@example.com", "mysite", "sd1")
    r = client.get("/sd1")
    assert r.status_code == 302
    assert "mysite.jottit.localhost:8000" in r.headers["Location"]


# Subdomain homepage lists the user's pages
def test_subdomain_home_lists_pages(client):
    user_id = create_user_with_username(client, "sub@example.com", "subuser", "subp1")
    save_page("subp2", "# Second\n\nMore content", False)
    page_meta = get_page_meta("subp2")
    claim_page(page_meta["id"], user_id)

    update_user_settings(user_id, "Sub User", "subuser")

    host = "subuser.jottit.localhost:8000"
    r = client.get("/", headers={"Host": host})
    assert r.status_code == 200
    assert b"Sub User" in r.data
    assert b"subp1" in r.data
    assert b"subp2" in r.data


# Subdomain serves the correct page content
def test_subdomain_serves_page(client):
    create_user_with_username(client, "sdp@example.com", "sdpuser", "sdpage")
    host = "sdpuser.jottit.localhost:8000"
    r = client.get("/sdpage", headers={"Host": host})
    assert r.status_code == 200
    assert b"Content" in r.data


# Subdomain pages show the user's name as site title with h-card markup
def test_subdomain_page_shows_site_title(client):
    user_id = create_user_with_username(client, "sdt@example.com", "sdtuser", "sdtpage")
    update_user_settings(user_id, "My Site Title", "sdtuser")
    host = "sdtuser.jottit.localhost:8000"
    r = client.get("/sdtpage", headers={"Host": host})
    assert r.status_code == 200
    body = r.data.decode()
    assert "My Site Title" in body
    assert "h-card" in body
    assert "p-name u-url" in body


# A subdomain returns 404 for pages belonging to other users
def test_subdomain_404_for_other_users_page(client):
    create_user_with_username(client, "sdp1@example.com", "user1", "page1")
    create_user_with_username(client, "sdp2@example.com", "user2", "page2")
    host = "user1.jottit.localhost:8000"
    r = client.get("/page2", headers={"Host": host})
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
    assert "rediruser" in r.headers["Location"]


# Old slug redirects work on subdomains too
def test_old_slug_redirects_on_subdomain(client):
    user_id = find_or_create_user("subredir@example.com")
    set_user_username(user_id, "subredir")
    update_user_settings(user_id, "Sub Redir", "subredir")
    save_page("old-slug", "# New Title\n\nContent", False, user_id)
    page = get_page_meta("old-slug", user_id)

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

    rename_page(page["id"], "nice-title")
    r = client.get("/rand123")
    assert r.status_code == 301
    assert "/nice-title" in r.headers["Location"]


# -- Listing --


# New pages default to "listed" listing status
def test_listing_default_is_listed(client):
    user_id = create_user_with_username(client, "list1@example.com", "listuser1", "lp1")
    page_meta = get_page_meta("lp1", user_id)
    assert page_meta["listing"] == "listed"


# Owner can change a page's listing to "unlisted"
def test_update_listing(client):
    user_id = create_user_with_username(client, "list2@example.com", "listuser2", "lp2")
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
    user_id = create_user_with_username(client, "list3@example.com", "listuser3", "lp3")
    host = "listuser3.jottit.localhost:8000"
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/lp3/listing", data={"listing": "unlisted"}, headers={"Host": host})
    r = client.get("/", headers={"Host": "listuser3.jottit.localhost:8000"})
    assert b"lp3" not in r.data


# Pinned pages appear before other pages on the subdomain homepage
def test_pinned_page_shown_first(client):
    user_id = create_user_with_username(
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
    user_id = create_user_with_username(
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
    create_user_with_username(client, "list5@example.com", "listuser5", "lp5")
    host = "listuser5.jottit.localhost:8000"
    r = client.post(
        "/lp5/listing", data={"listing": "unlisted"}, headers={"Host": host}
    )
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

    # Each subdomain shows the correct page
    r = client.get("/about", headers={"Host": "alice.jottit.localhost:8000"})
    assert r.status_code == 200

    r = client.get("/about", headers={"Host": "bob.jottit.localhost:8000"})
    assert r.status_code == 200


# New page on a subdomain gets a title-derived slug
def test_subdomain_new_page_gets_nice_slug(client):
    user_id = create_user_with_username(client, "nice@example.com", "niceslug", "x1")
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
    user_id = create_user_with_username(client, "about@example.com", "aboutuser", "x2")
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
    user_id = create_user_with_username(
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
    create_user_with_username(client, "vis404@example.com", "vis404", "exists2")
    host = "vis404.jottit.localhost:8000"
    r = client.get("/nope", headers={"Host": host})
    assert r.status_code == 404


# Visiting a claimed page's slug on the main domain redirects to the owner's subdomain
def test_main_domain_slug_redirects_to_owner(client):
    create_user_with_username(client, "redir@example.com", "redir", "mypage")
    r = client.get("/mypage")
    assert r.status_code == 302
    assert "redir.jottit.localhost:8000" in r.headers["Location"]


# License appears in the page footer on subdomains
def test_license_shows_in_page_footer(client):
    user_id = create_user_with_username(client, "licfoot@example.com", "licfoot", "lf1")
    update_user_settings(user_id, "Lic Footer", "licfoot", license="cc-by-sa-4.0")

    host = "licfoot.jottit.localhost:8000"
    r = client.get("/lf1", headers={"Host": host})
    assert r.status_code == 200
    assert b"CC BY-SA 4.0" in r.data
    assert b"creativecommons.org" in r.data
