from conftest import create_user_with_username
from db import (
    create_site,
    find_or_create_user,
    get_default_site_for_user,
    get_page_meta,
    get_pages_for_site,
    get_site,
    get_site_by_subdomain,
    get_sites_for_user,
    save_page,
    set_user_username,
    update_site_license,
)
from routes import BASE_DOMAIN


def _subdomain_host(username):
    return {"Host": f"{username}.{BASE_DOMAIN}"}


# -- Site data model --


# Creating a site persists it with correct fields
def test_create_site():
    user_id = find_or_create_user("site1@example.com")
    site_id = create_site(user_id, "mysite")
    site = get_site(site_id)
    assert site is not None
    assert site["user_id"] == user_id
    assert site["subdomain"] == "mysite"
    assert site["visibility"] == "public"
    assert site["license"] is None
    assert site["home_page_id"] is None


# Looking up a site by subdomain returns the site with user info
def test_get_site_by_subdomain():
    user_id = find_or_create_user("site2@example.com")
    set_user_username(user_id, "site2user")
    create_site(user_id, "site2user")
    site = get_site_by_subdomain("site2user")
    assert site is not None
    assert site["subdomain"] == "site2user"
    assert site["username"] == "site2user"


# A user can have multiple sites
def test_multiple_sites_per_user():
    user_id = find_or_create_user("multi@example.com")
    create_site(user_id, "site-a")
    create_site(user_id, "site-b")
    sites = get_sites_for_user(user_id)
    assert len(sites) == 2
    subdomains = {s["subdomain"] for s in sites}
    assert subdomains == {"site-a", "site-b"}


# Default site returns the first created site
def test_default_site():
    user_id = find_or_create_user("default@example.com")
    create_site(user_id, "first-site")
    create_site(user_id, "second-site")
    default = get_default_site_for_user(user_id)
    assert default["subdomain"] == "first-site"


# Updating site license persists the change
def test_update_site_license():
    user_id = find_or_create_user("lic@example.com")
    site_id = create_site(user_id, "licsite")
    update_site_license(site_id, "cc-by-4.0")
    site = get_site(site_id)
    assert site["license"] == "cc-by-4.0"


# -- Pages belong to sites --


# Saving a page with site_id assigns it to that site
def test_page_belongs_to_site():
    user_id = find_or_create_user("psite@example.com")
    site_id = create_site(user_id, "psite")
    save_page("mypage", "# Hello\n\nWorld", "listed", site_id=site_id)
    meta = get_page_meta("mypage", site_id=site_id)
    assert meta is not None
    assert meta["site_id"] == site_id


# Two sites can have pages with the same slug
def test_same_slug_different_sites():
    user_id = find_or_create_user("dup@example.com")
    site_a = create_site(user_id, "site-alpha")
    site_b = create_site(user_id, "site-beta")
    save_page("about", "# About A", "listed", site_id=site_a)
    save_page("about", "# About B", "listed", site_id=site_b)
    meta_a = get_page_meta("about", site_id=site_a)
    meta_b = get_page_meta("about", site_id=site_b)
    assert meta_a is not None
    assert meta_b is not None
    assert meta_a["id"] != meta_b["id"]


# get_pages_for_site returns only that site's pages
def test_get_pages_for_site():
    user_id = find_or_create_user("sitepages@example.com")
    site_id = create_site(user_id, "sitepages")
    save_page("p1", "# Page 1\n\nContent", "listed", site_id=site_id)
    save_page("p2", "# Page 2\n\nContent", "listed", site_id=site_id)
    pages = get_pages_for_site(site_id)
    assert len(pages) == 2
    slugs = {p["slug"] for p in pages}
    assert slugs == {"p1", "p2"}


# -- Subdomain routing --


# Subdomain root shows the site's listed pages
def test_subdomain_root_shows_feed(client):
    user_id = create_user_with_username(client, "feed@example.com", "feedsite", "fp1")
    r = client.get("/", headers=_subdomain_host("feedsite"))
    assert r.status_code == 200
    assert b"fp1" in r.data


# Private site returns 403 to non-owners
def test_private_site_403_for_non_owner(client):
    user_id = find_or_create_user("priv@example.com")
    set_user_username(user_id, "privsite")
    create_site(user_id, "privsite", visibility="private")
    save_page("secret", "# Secret\n\nHidden", "listed", site_id=get_default_site_for_user(user_id)["id"])

    r = client.get("/", headers=_subdomain_host("privsite"))
    assert r.status_code == 403
    assert b"This site is private" in r.data


# Private site is accessible to the owner
def test_private_site_accessible_to_owner(client):
    user_id = find_or_create_user("privown@example.com")
    set_user_username(user_id, "privown")
    create_site(user_id, "privown", visibility="private")
    site = get_default_site_for_user(user_id)
    save_page("secret", "# Secret\n\nHidden", "listed", site_id=site["id"])

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/", headers=_subdomain_host("privown"))
    assert r.status_code == 200
    assert b"secret" in r.data


# Private site pages are 404 for non-owners
def test_private_site_page_404_for_non_owner(client):
    user_id = find_or_create_user("privp@example.com")
    set_user_username(user_id, "privpage")
    create_site(user_id, "privpage", visibility="private")
    site = get_default_site_for_user(user_id)
    save_page("hidden", "# Hidden\n\nContent", "listed", site_id=site["id"])

    r = client.get("/hidden", headers=_subdomain_host("privpage"))
    assert r.status_code == 404


# Nonexistent subdomain returns 404
def test_nonexistent_subdomain_404(client):
    r = client.get("/", headers=_subdomain_host("doesnotexist"))
    assert r.status_code == 404


# -- Sign-in link --


# Subdomain pages show sign-in link in footer for non-owners
def test_subdomain_footer_has_signin_link(client):
    create_user_with_username(client, "signin@example.com", "signinsite", "sp1")
    r = client.get("/sp1", headers=_subdomain_host("signinsite"))
    assert r.status_code == 200
    assert b"/signin" in r.data


# Owner doesn't see sign-in link
def test_owner_no_signin_link(client):
    user_id = create_user_with_username(client, "ownsign@example.com", "ownsign", "op1")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/op1", headers=_subdomain_host("ownsign"))
    assert r.status_code == 200
    # Owner sees edit actions, not sign-in link
    assert b"Edit" in r.data


# -- Owner sees all pages --


# Owner sees private pages on their subdomain
def test_owner_sees_private_pages_on_subdomain(client):
    user_id = create_user_with_username(client, "allpages@example.com", "allpages", "pub1")
    site = get_default_site_for_user(user_id)
    save_page("priv1", "# Private\n\nSecret", "private", site_id=site["id"])
    from db import claim_page
    meta = get_page_meta("priv1", site_id=site["id"])
    claim_page(meta["id"], user_id)

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/", headers=_subdomain_host("allpages"))
    assert r.status_code == 200
    assert b"priv1" in r.data


# -- Claiming creates a site --


# Claiming a page and picking a username creates a site
def test_claim_creates_site(client):
    from db import create_verification_code
    save_page("claimpage", "# Claimed\n\nContent", "unlisted")
    # Simulate the creator having a page token
    from db import create_page_secret
    meta = get_page_meta("claimpage")
    secret = create_page_secret(meta["id"])
    # Visit with token to get page_token cookie
    client.get(f"/claimpage?token={secret}")

    client.post("/claimpage/claim", data={"email": "newclaim@example.com"})
    code = create_verification_code("newclaim@example.com", "claim")
    client.post("/claimpage/claim/verify", data={"code": code, "email": "newclaim@example.com"})
    client.post("/claimpage/claim/setup", data={"name": "Claim User"})
    client.post("/claimpage/claim/address", data={"username": "claimuser"})

    site = get_site_by_subdomain("claimuser")
    assert site is not None
    assert site["subdomain"] == "claimuser"
