from conftest import create_user_with_username
from db import (
    claim_page,
    create_site,
    create_verification_code,
    find_or_create_user,
    get_db,
    get_page_meta,
    rename_page,
    save_page,
    set_user_username,
    update_site,
    update_user_settings,
)


def _sub(client, username, path="/", method="get", **kwargs):
    """Make a request with subdomain Host header."""
    headers = kwargs.pop("headers", {})
    headers["Host"] = f"{username}.jottit.localhost:8000"
    fn = getattr(client, method)
    return fn(path, headers=headers, **kwargs)


def _setup_site(user_id, username, *page_slugs):
    """Create a site for a user and assign given pages to it."""
    site_id = create_site(user_id, username)
    if page_slugs:
        with get_db() as conn:
            for slug in page_slugs:
                meta = get_page_meta(slug, user_id)
                if meta:
                    conn.execute(
                        "UPDATE pages SET site_id = %s WHERE id = %s",
                        (site_id, meta["id"]),
                    )
            conn.commit()
    return site_id


# -- Subdomain routing --


# Subdomain serves site home directly (no redirect)
def test_subdomain_serves_site_home(client):
    user_id = create_user_with_username(
        client, "legacy@example.com", "legacyuser", "lp1"
    )
    _setup_site(user_id, "legacyuser", "lp1")
    r = _sub(client, "legacyuser")
    assert r.status_code == 200


# Profile home shows site directory (not pages)
def test_profile_home_lists_sites(client):
    user_id = create_user_with_username(client, "sub@example.com", "subuser", "subp1")
    save_page("subp2", "# Second\n\nMore content", "listed")
    page_meta = get_page_meta("subp2")
    claim_page(page_meta["id"], user_id)

    update_user_settings(user_id, "Sub User", "subuser")
    _setup_site(user_id, "subuser", "subp1", "subp2")

    r = client.get("/@subuser")
    assert r.status_code == 200
    assert b"Sub User" in r.data
    # Profile shows site directory, should link to subdomain
    assert b"subuser" in r.data


# Subdomain serves page content directly
def test_subdomain_serves_page(client):
    user_id = create_user_with_username(client, "sdp@example.com", "sdpuser", "sdpage")
    _setup_site(user_id, "sdpuser", "sdpage")
    r = _sub(client, "sdpuser", "/sdpage")
    assert r.status_code == 200
    assert b"Content" in r.data


# Subdomain pages show the user's name as site title with h-card markup
def test_subdomain_page_shows_site_title(client):
    user_id = create_user_with_username(client, "sdt@example.com", "sdtuser", "sdtpage")
    update_user_settings(user_id, "My Site Title", "sdtuser")
    site_id = _setup_site(user_id, "sdtuser", "sdtpage")
    update_site(site_id, title="My Site Title")
    r = _sub(client, "sdtuser", "/sdtpage")
    assert r.status_code == 200
    body = r.data.decode()
    assert "My Site Title" in body
    assert "h-card" in body
    assert "p-name u-url" in body


# A subdomain returns 404 for pages belonging to other users
def test_subdomain_404_for_other_users_page(client):
    user_id1 = create_user_with_username(client, "sdp1@example.com", "user1", "page1")
    user_id2 = create_user_with_username(client, "sdp2@example.com", "user2", "page2")
    _setup_site(user_id1, "user1", "page1")
    _setup_site(user_id2, "user2", "page2")
    r = _sub(client, "user1", "/page2")
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


# Old slug redirects work on subdomains
def test_old_slug_redirects_on_subdomain(client):
    user_id = find_or_create_user("subredir@example.com")
    set_user_username(user_id, "subredir")
    update_user_settings(user_id, "Sub Redir", "subredir")
    save_page("old-slug", "# New Title\n\nContent", "listed", user_id)
    page = get_page_meta("old-slug", user_id)
    _setup_site(user_id, "subredir", "old-slug")

    rename_page(page["id"], "new-title")
    r = _sub(client, "subredir", "/old-slug")
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
    page_meta = get_page_meta("lp1", user_id)
    assert page_meta["visibility"] == "listed"


# Owner can change a page's visibility to "unlisted"
def test_update_visibility(client):
    user_id = create_user_with_username(client, "list2@example.com", "listuser2", "lp2")
    _setup_site(user_id, "listuser2", "lp2")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = _sub(
        client,
        "listuser2",
        "/lp2/visibility",
        method="post",
        data={"visibility": "unlisted"},
    )
    assert r.status_code in (302, 204)
    page_meta = get_page_meta("lp2", user_id)
    assert page_meta["visibility"] == "unlisted"


# Unlisted pages don't appear on the subdomain home for non-owners
def test_unlisted_page_hidden_from_subdomain(client):
    user_id = create_user_with_username(client, "list3@example.com", "listuser3", "lp3")
    _setup_site(user_id, "listuser3", "lp3")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    _sub(
        client,
        "listuser3",
        "/lp3/visibility",
        method="post",
        data={"visibility": "unlisted"},
    )
    # Clear session to view as non-owner
    with client.session_transaction() as sess:
        sess.pop("user_id", None)
    r = _sub(client, "listuser3")
    assert b"lp3" not in r.data


# Pinned pages appear before other pages on the subdomain home
def test_pinned_page_shown_first(client):
    user_id = create_user_with_username(
        client, "list4@example.com", "listuser4", "lp4a"
    )
    save_page("lp4b", "# Second\n\nContent", "listed", user_id)
    site_id = _setup_site(user_id, "listuser4", "lp4a")
    # Also assign lp4b to the site
    page_meta2 = get_page_meta("lp4b", user_id)
    with get_db() as conn:
        conn.execute(
            "UPDATE pages SET site_id = %s WHERE id = %s", (site_id, page_meta2["id"])
        )
        conn.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    # Pin lp4a so it appears before lp4b
    _sub(
        client,
        "listuser4",
        "/lp4a/visibility",
        method="post",
        data={"visibility": "pinned"},
    )
    r = _sub(client, "listuser4")
    body = r.data.decode()
    assert "lp4a" in body
    assert "lp4b" in body
    assert body.index("lp4a") < body.index("lp4b")


# Only pinned pages show a pin icon
def test_pinned_page_shows_pin_icon(client):
    user_id = create_user_with_username(
        client, "pinicon@example.com", "pinicon", "pip1"
    )
    save_page("pip2", "# Not Pinned\n\nContent", "listed", user_id)
    site_id = _setup_site(user_id, "pinicon", "pip1")
    page_meta2 = get_page_meta("pip2", user_id)
    with get_db() as conn:
        conn.execute(
            "UPDATE pages SET site_id = %s WHERE id = %s", (site_id, page_meta2["id"])
        )
        conn.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    _sub(
        client,
        "pinicon",
        "/pip1/visibility",
        method="post",
        data={"visibility": "pinned"},
    )
    r = _sub(client, "pinicon")
    body = r.data.decode()
    assert 'class="pin-icon"' in body
    assert body.count('class="pin-icon"') == 1


# Non-owner gets 403 when trying to change visibility
def test_non_owner_cannot_update_visibility(client):
    user_id = create_user_with_username(client, "list5@example.com", "listuser5", "lp5")
    _setup_site(user_id, "listuser5", "lp5")
    r = _sub(
        client,
        "listuser5",
        "/lp5/visibility",
        method="post",
        data={"visibility": "unlisted"},
    )
    assert r.status_code == 403


# -- Per-user slug uniqueness --


# Two different users can each have a page with the same slug
def test_two_users_same_slug(client):
    user1 = create_user_with_username(client, "slug1@example.com", "alice", "about")
    user2 = create_user_with_username(client, "slug2@example.com", "bob", "about")
    _setup_site(user1, "alice", "about")
    _setup_site(user2, "bob", "about")

    meta1 = get_page_meta("about", user1)
    meta2 = get_page_meta("about", user2)
    assert meta1 is not None
    assert meta2 is not None
    assert meta1["id"] != meta2["id"]

    # Each subdomain shows the correct page
    r = _sub(client, "alice", "/about")
    assert r.status_code == 200

    r = _sub(client, "bob", "/about")
    assert r.status_code == 200


# New page on a subdomain gets a title-derived slug
def test_subdomain_new_page_gets_nice_slug(client):
    user_id = create_user_with_username(client, "nice@example.com", "niceslug", "x1")
    site_id = _setup_site(user_id, "niceslug", "x1")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = _sub(
        client,
        "niceslug",
        "/randomslug/edit",
        method="post",
        data={"title": "About", "content": "My about page"},
    )
    assert r.status_code == 302
    assert "/about" in r.headers["Location"]
    meta = get_page_meta("about", site_id=site_id)
    assert meta is not None


# POST /new on a subdomain creates a page with a title-derived slug
def test_subdomain_new_page_gets_about_slug(client):
    user_id = create_user_with_username(client, "about@example.com", "aboutuser", "x2")
    site_id = _setup_site(user_id, "aboutuser", "x2")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = _sub(
        client,
        "aboutuser",
        "/new",
        method="post",
        data={"title": "About", "content": "My about page"},
    )
    assert r.status_code == 302
    assert "/about" in r.headers["Location"]
    meta = get_page_meta("about", site_id=site_id)
    assert meta is not None


# Owner visiting a nonexistent slug on their subdomain is redirected to the editor
def test_owner_visiting_nonexistent_page_redirects_to_edit(client):
    user_id = create_user_with_username(
        client, "owner404@example.com", "owner404", "exists"
    )
    _setup_site(user_id, "owner404", "exists")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = _sub(client, "owner404", "/newpage")
    assert r.status_code == 302
    assert "/newpage/edit" in r.headers["Location"]


# Non-owner visiting a nonexistent slug on a subdomain gets 404
def test_nonowner_visiting_nonexistent_page_gets_404(client):
    user_id = create_user_with_username(
        client, "vis404@example.com", "vis404", "exists2"
    )
    _setup_site(user_id, "vis404", "exists2")
    r = _sub(client, "vis404", "/nope")
    assert r.status_code == 404


# Visiting a claimed page's slug on the main domain redirects to subdomain
def test_main_domain_slug_redirects_to_subdomain(client):
    user_id = create_user_with_username(client, "redir@example.com", "redir", "mypage")
    _setup_site(user_id, "redir", "mypage")
    r = client.get("/mypage")
    assert r.status_code in (301, 302)
    assert "redir." in r.headers["Location"] or "redir" in r.headers["Location"]
    assert "/mypage" in r.headers["Location"]


# License appears in the page footer on subdomains
def test_license_shows_in_page_footer(client):
    user_id = create_user_with_username(client, "licfoot@example.com", "licfoot", "lf1")
    site_id = _setup_site(user_id, "licfoot", "lf1")
    update_site(site_id, license="cc-by-sa-4.0")

    r = _sub(client, "licfoot", "/lf1")
    assert r.status_code == 200
    assert b"CC BY-SA 4.0" in r.data
    assert b"creativecommons.org" in r.data


# /@username/slug returns 301 redirect to subdomain (backward compat)
def test_at_username_slug_redirects_to_subdomain(client):
    user_id = create_user_with_username(
        client, "compat@example.com", "compatuser", "cp1"
    )
    _setup_site(user_id, "compatuser", "cp1")
    r = client.get("/@compatuser/cp1")
    assert r.status_code == 301
    assert "compatuser." in r.headers["Location"]
    assert "/cp1" in r.headers["Location"]


# Visiting a claimed page's slug on the main domain redirects to subdomain URL
def test_slug_redirects_to_subdomain(client):
    user_id = create_user_with_username(client, "sd@example.com", "mysite", "sd1")
    _setup_site(user_id, "mysite", "sd1")
    r = client.get("/sd1")
    assert r.status_code in (301, 302)
    assert "mysite." in r.headers["Location"]
    assert "/sd1" in r.headers["Location"]
