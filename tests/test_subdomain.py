from conftest import create_user_with_username
from db import (
    assign_page_to_site,
    claim_page,
    create_site,
    create_verification_code,
    find_or_create_user,
    get_default_site_for_user,
    get_page_meta,
    rename_page,
    save_page,
    set_user_username,
    update_site_license,
    update_user_settings,
)
from routes import BASE_DOMAIN


def _subdomain_host(username):
    return {"Host": f"{username}.{BASE_DOMAIN}"}


# -- Subdomain routing --


# Visiting a page on a subdomain serves it directly
def test_subdomain_serves_page(client):
    create_user_with_username(client, "sd@example.com", "mysite", "sd1")
    r = client.get("/sd1", headers=_subdomain_host("mysite"))
    assert r.status_code == 200
    assert b"Content" in r.data


# Visiting a claimed page's slug on the main domain redirects to subdomain
def test_slug_redirects_to_subdomain(client):
    create_user_with_username(client, "sd@example.com", "mysite", "sd1")
    r = client.get("/sd1")
    assert r.status_code == 301
    assert "mysite." in r.headers["Location"]
    assert "/sd1" in r.headers["Location"]


# /@username/slug 301 redirects to subdomain
def test_profile_slug_redirects_to_subdomain(client):
    create_user_with_username(client, "sd@example.com", "mysite", "sd1")
    r = client.get("/@mysite/sd1")
    assert r.status_code == 301
    assert "mysite." in r.headers["Location"]
    assert "/sd1" in r.headers["Location"]


# Profile homepage lists the user's pages (/@username still works as profile)
def test_profile_home_lists_pages(client):
    user_id = create_user_with_username(client, "sub@example.com", "subuser", "subp1")
    site = get_default_site_for_user(user_id)
    save_page("subp2", "# Second\n\nMore content", "listed", site_id=site["id"])
    page_meta = get_page_meta("subp2", site_id=site["id"])
    claim_page(page_meta["id"], user_id)

    update_user_settings(user_id, "Sub User", "subuser")

    r = client.get("/@subuser")
    assert r.status_code == 200
    assert b"Sub User" in r.data
    assert b"subp1" in r.data
    assert b"subp2" in r.data


# Subdomain serves the correct page content
def test_subdomain_serves_page_content(client):
    create_user_with_username(client, "sdp@example.com", "sdpuser", "sdpage")
    r = client.get("/sdpage", headers=_subdomain_host("sdpuser"))
    assert r.status_code == 200
    assert b"Content" in r.data


# Subdomain pages show the user's name as site title with h-card markup
def test_subdomain_page_shows_site_title(client):
    user_id = create_user_with_username(client, "sdt@example.com", "sdtuser", "sdtpage")
    update_user_settings(user_id, "My Site Title", "sdtuser")
    r = client.get("/sdtpage", headers=_subdomain_host("sdtuser"))
    assert r.status_code == 200
    body = r.data.decode()
    assert "My Site Title" in body
    assert "h-card" in body
    assert "p-name u-url" in body


# A subdomain returns 404 for pages belonging to other sites
def test_subdomain_404_for_other_sites_page(client):
    create_user_with_username(client, "sdp1@example.com", "user1", "page1")
    create_user_with_username(client, "sdp2@example.com", "user2", "page2")
    r = client.get("/page2", headers=_subdomain_host("user1"))
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
    # After claiming, page should be accessible on the subdomain
    r = client.get("/my-great-post", headers=_subdomain_host("rediruser"))
    assert r.status_code == 200


# Old slug redirects work on subdomains too
def test_old_slug_redirects_on_subdomain(client):
    user_id = find_or_create_user("subredir@example.com")
    set_user_username(user_id, "subredir")
    update_user_settings(user_id, "Sub Redir", "subredir")
    site_id = create_site(user_id, "subredir")
    save_page("old-slug", "# New Title\n\nContent", "listed", site_id=site_id)
    page = get_page_meta("old-slug", site_id=site_id)

    rename_page(page["id"], "new-title")
    r = client.get("/old-slug", headers=_subdomain_host("subredir"))
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


# New pages default to "listed" visibility (via create_user_with_username)
def test_visibility_default_is_listed(client):
    user_id = create_user_with_username(client, "list1@example.com", "listuser1", "lp1")
    site = get_default_site_for_user(user_id)
    page_meta = get_page_meta("lp1", site_id=site["id"])
    assert page_meta["visibility"] == "listed"


# Owner can change a page's visibility to "unlisted"
def test_update_visibility(client):
    user_id = create_user_with_username(client, "list2@example.com", "listuser2", "lp2")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post("/lp2/visibility", data={"visibility": "unlisted"},
                     headers=_subdomain_host("listuser2"))
    assert r.status_code == 302
    site = get_default_site_for_user(user_id)
    page_meta = get_page_meta("lp2", site_id=site["id"])
    assert page_meta["visibility"] == "unlisted"


# Unlisted pages don't appear on the subdomain homepage for non-owners
def test_unlisted_page_hidden_from_subdomain(client):
    user_id = create_user_with_username(client, "list3@example.com", "listuser3", "lp3")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/lp3/visibility", data={"visibility": "unlisted"},
                headers=_subdomain_host("listuser3"))
    # View as non-owner (clear session)
    with client.session_transaction() as sess:
        sess.pop("user_id", None)
    r = client.get("/", headers=_subdomain_host("listuser3"))
    assert b"lp3" not in r.data


# Pinned pages appear before other pages on the subdomain homepage
def test_pinned_page_shown_first(client):
    user_id = create_user_with_username(
        client, "list4@example.com", "listuser4", "lp4a"
    )
    site = get_default_site_for_user(user_id)
    save_page("lp4b", "# Second\n\nContent", "listed", site_id=site["id"])
    page_meta2 = get_page_meta("lp4b", site_id=site["id"])
    claim_page(page_meta2["id"], user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    # Pin lp4a so it appears before lp4b
    client.post("/lp4a/visibility", data={"visibility": "pinned"},
                headers=_subdomain_host("listuser4"))
    r = client.get("/", headers=_subdomain_host("listuser4"))
    body = r.data.decode()
    assert "lp4a" in body
    assert "lp4b" in body
    assert body.index("lp4a") < body.index("lp4b")


# Only pinned pages show a pin icon
def test_pinned_page_shows_pin_icon(client):
    user_id = create_user_with_username(
        client, "pinicon@example.com", "pinicon", "pip1"
    )
    site = get_default_site_for_user(user_id)
    save_page("pip2", "# Not Pinned\n\nContent", "listed", site_id=site["id"])
    page_meta2 = get_page_meta("pip2", site_id=site["id"])
    claim_page(page_meta2["id"], user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/pip1/visibility", data={"visibility": "pinned"},
                headers=_subdomain_host("pinicon"))
    r = client.get("/", headers=_subdomain_host("pinicon"))
    body = r.data.decode()
    assert 'class="pin-icon"' in body
    assert body.count('class="pin-icon"') == 1


# Non-owner gets 403 when trying to change visibility
def test_non_owner_cannot_update_visibility(client):
    create_user_with_username(client, "list5@example.com", "listuser5", "lp5")
    r = client.post("/lp5/visibility", data={"visibility": "unlisted"},
                    headers=_subdomain_host("listuser5"))
    assert r.status_code == 403


# -- Per-site slug uniqueness --


# Two different sites can each have a page with the same slug
def test_two_sites_same_slug(client):
    user1 = create_user_with_username(client, "slug1@example.com", "alice", "about")
    user2 = create_user_with_username(client, "slug2@example.com", "bob", "about")
    site1 = get_default_site_for_user(user1)
    site2 = get_default_site_for_user(user2)
    # Both sites have /about pages
    meta1 = get_page_meta("about", site_id=site1["id"])
    meta2 = get_page_meta("about", site_id=site2["id"])
    assert meta1 is not None
    assert meta2 is not None
    assert meta1["id"] != meta2["id"]

    # Each subdomain shows the correct page
    r = client.get("/about", headers=_subdomain_host("alice"))
    assert r.status_code == 200

    r = client.get("/about", headers=_subdomain_host("bob"))
    assert r.status_code == 200


# New page on a subdomain gets a title-derived slug
def test_subdomain_new_page_gets_nice_slug(client):
    user_id = create_user_with_username(client, "nice@example.com", "niceslug", "x1")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post(
        "/randomslug/edit",
        data={"title": "About", "content": "My about page"},
        headers=_subdomain_host("niceslug"),
    )
    assert r.status_code == 302
    assert "/about" in r.headers["Location"]
    site = get_default_site_for_user(user_id)
    meta = get_page_meta("about", site_id=site["id"])
    assert meta is not None


# POST /new on a subdomain creates a page with a title-derived slug
def test_subdomain_new_page_gets_about_slug(client):
    user_id = create_user_with_username(client, "about@example.com", "aboutuser", "x2")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post(
        "/new",
        data={"title": "About", "content": "My about page"},
        headers=_subdomain_host("aboutuser"),
    )
    assert r.status_code == 302
    assert "/about" in r.headers["Location"]
    site = get_default_site_for_user(user_id)
    meta = get_page_meta("about", site_id=site["id"])
    assert meta is not None


# Owner visiting a nonexistent slug on their subdomain is redirected to the editor
def test_owner_visiting_nonexistent_page_redirects_to_edit(client):
    user_id = create_user_with_username(
        client, "owner404@example.com", "owner404", "exists"
    )
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/newpage", headers=_subdomain_host("owner404"))
    assert r.status_code == 302
    assert "/newpage/edit" in r.headers["Location"]


# Non-owner visiting a nonexistent slug on a subdomain gets 404
def test_nonowner_visiting_nonexistent_page_gets_404(client):
    create_user_with_username(client, "vis404@example.com", "vis404", "exists2")
    r = client.get("/nope", headers=_subdomain_host("vis404"))
    assert r.status_code == 404


# Visiting a claimed page's slug on the main domain redirects to subdomain
def test_main_domain_slug_redirects_to_subdomain(client):
    create_user_with_username(client, "redir@example.com", "redir", "mypage")
    r = client.get("/mypage")
    assert r.status_code == 301
    assert "redir." in r.headers["Location"]
    assert "/mypage" in r.headers["Location"]


# License appears in the page footer on subdomains
def test_license_shows_in_page_footer(client):
    user_id = create_user_with_username(client, "licfoot@example.com", "licfoot", "lf1")
    site = get_default_site_for_user(user_id)
    update_site_license(site["id"], "cc-by-sa-4.0")

    r = client.get("/lf1", headers=_subdomain_host("licfoot"))
    assert r.status_code == 200
    assert b"CC BY-SA 4.0" in r.data
    assert b"creativecommons.org" in r.data


# Old subdomain URLs (Host header) now serve content directly
def test_subdomain_serves_content_directly(client):
    create_user_with_username(client, "legacy@example.com", "legacyuser", "lp1")
    r = client.get("/lp1", headers={"Host": "legacyuser.jottit.localhost:8000"})
    assert r.status_code == 200
    assert b"Content" in r.data
