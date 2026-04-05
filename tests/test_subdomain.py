from conftest import create_user_with_username
from db import (
    assign_page_to_wiki,
    claim_page,
    create_verification_code,
    create_wiki,
    check_wiki_slug_available,
    find_or_create_user,
    get_default_wiki_for_user,
    get_page_meta,
    rename_page,
    save_page,
    set_user_username,
    update_user_settings,
)

# -- Wiki subdomain routing --


# Visiting a claimed page's slug on the main domain redirects to wiki subdomain
def test_slug_redirects_to_wiki_subdomain(client):
    create_user_with_username(client, "sd@example.com", "mysite", "sd1")
    r = client.get("/sd1")
    assert r.status_code == 301
    assert "mysite.jottit.localhost:8000/sd1" in r.headers["Location"]


# Wiki subdomain home lists the wiki's pages
def test_wiki_home_lists_pages(client):
    user_id = create_user_with_username(client, "sub@example.com", "subuser", "subp1")
    wiki = get_default_wiki_for_user(user_id)
    save_page("subp2", "# Second\n\nMore content", "listed", user_id, wiki_id=wiki["id"])

    update_user_settings(user_id, "Sub User", "subuser")

    r = client.get("/", headers={"Host": "subuser.jottit.localhost:8000"})
    assert r.status_code == 200
    assert b"subp1" in r.data
    assert b"subp2" in r.data


# Wiki subdomain serves the correct page content
def test_wiki_serves_page(client):
    create_user_with_username(client, "sdp@example.com", "sdpuser", "sdpage")
    r = client.get("/sdpage", headers={"Host": "sdpuser.jottit.localhost:8000"})
    assert r.status_code == 200
    assert b"Content" in r.data


# Wiki pages show the wiki name as site title
def test_wiki_page_shows_site_title(client):
    user_id = create_user_with_username(client, "sdt@example.com", "sdtuser", "sdtpage")
    update_user_settings(user_id, "My Site Title", "sdtuser")
    r = client.get("/sdtpage", headers={"Host": "sdtuser.jottit.localhost:8000"})
    assert r.status_code == 200
    body = r.data.decode()
    assert "sdtuser" in body


# A wiki returns 404 for pages belonging to other wikis
def test_wiki_404_for_other_wikis_page(client):
    create_user_with_username(client, "sdp1@example.com", "user1", "page1")
    create_user_with_username(client, "sdp2@example.com", "user2", "page2")
    r = client.get("/page2", headers={"Host": "user1.jottit.localhost:8000"})
    assert r.status_code == 404


# -- Old slug redirects --


# Old slug 301-redirects to the new slug on wiki subdomain after a claim rename
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


# Old slug redirects work on wiki subdomains
def test_old_slug_redirects_on_wiki(client):
    user_id = find_or_create_user("subredir@example.com")
    set_user_username(user_id, "subredir")
    update_user_settings(user_id, "Sub Redir", "subredir")
    wiki_id = None
    if check_wiki_slug_available("subredir"):
        wiki_id = create_wiki("subredir", "subredir", user_id)
    save_page("old-slug", "# New Title\n\nContent", "listed", user_id, wiki_id=wiki_id)
    page = get_page_meta("old-slug", user_id)

    rename_page(page["id"], "new-title")
    r = client.get("/old-slug", headers={"Host": "subredir.jottit.localhost:8000"})
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


# Owner can change a page's visibility to "unlisted" on wiki subdomain
def test_update_visibility(client):
    user_id = create_user_with_username(client, "list2@example.com", "listuser2", "lp2")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post(
        "/lp2/visibility",
        data={"visibility": "unlisted"},
        headers={"Host": "listuser2.jottit.localhost:8000"},
    )
    assert r.status_code == 302
    page_meta = get_page_meta("lp2", user_id)
    assert page_meta["visibility"] == "unlisted"


# Unlisted pages don't appear on the wiki home
def test_unlisted_page_hidden_from_wiki_home(client):
    user_id = create_user_with_username(client, "list3@example.com", "listuser3", "lp3")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post(
        "/lp3/visibility",
        data={"visibility": "unlisted"},
        headers={"Host": "listuser3.jottit.localhost:8000"},
    )
    r = client.get("/", headers={"Host": "listuser3.jottit.localhost:8000"})
    assert b"lp3" not in r.data


# Pinned pages appear before other pages on the wiki home
def test_pinned_page_shown_first(client):
    user_id = create_user_with_username(client, "list4@example.com", "listuser4", "lp4a")
    wiki = get_default_wiki_for_user(user_id)
    save_page("lp4b", "# Second\n\nContent", "listed", user_id, wiki_id=wiki["id"])
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post(
        "/lp4a/visibility",
        data={"visibility": "pinned"},
        headers={"Host": "listuser4.jottit.localhost:8000"},
    )
    r = client.get("/", headers={"Host": "listuser4.jottit.localhost:8000"})
    body = r.data.decode()
    assert "lp4a" in body
    assert "lp4b" in body
    assert body.index("lp4a") < body.index("lp4b")


# Only pinned pages show a pin icon
def test_pinned_page_shows_pin_icon(client):
    user_id = create_user_with_username(client, "pinicon@example.com", "pinicon", "pip1")
    wiki = get_default_wiki_for_user(user_id)
    save_page("pip2", "# Not Pinned\n\nContent", "listed", user_id, wiki_id=wiki["id"])
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post(
        "/pip1/visibility",
        data={"visibility": "pinned"},
        headers={"Host": "pinicon.jottit.localhost:8000"},
    )
    r = client.get("/", headers={"Host": "pinicon.jottit.localhost:8000"})
    body = r.data.decode()
    assert 'class="pin-icon"' in body
    assert body.count('class="pin-icon"') == 1


# Non-owner gets 403 when trying to change visibility
def test_non_owner_cannot_update_visibility(client):
    create_user_with_username(client, "list5@example.com", "listuser5", "lp5")
    r = client.post(
        "/lp5/visibility",
        data={"visibility": "unlisted"},
        headers={"Host": "listuser5.jottit.localhost:8000"},
    )
    assert r.status_code == 403


# -- Per-wiki slug uniqueness --


# Two different wikis can each have a page with the same slug
def test_two_wikis_same_slug(client):
    user1 = create_user_with_username(client, "slug1@example.com", "alice", "about")
    user2 = create_user_with_username(client, "slug2@example.com", "bob", "about")
    # Both users have /about pages in their wikis
    meta1 = get_page_meta("about", user1)
    meta2 = get_page_meta("about", user2)
    assert meta1 is not None
    assert meta2 is not None
    assert meta1["id"] != meta2["id"]

    # Each wiki serves the correct page
    r = client.get("/about", headers={"Host": "alice.jottit.localhost:8000"})
    assert r.status_code == 200

    r = client.get("/about", headers={"Host": "bob.jottit.localhost:8000"})
    assert r.status_code == 200


# Owner visiting a nonexistent slug on their wiki is redirected to the editor
def test_owner_visiting_nonexistent_page_redirects_to_edit(client):
    user_id = create_user_with_username(client, "owner404@example.com", "owner404", "exists")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/newpage", headers={"Host": "owner404.jottit.localhost:8000"})
    assert r.status_code == 302
    assert "/newpage/edit" in r.headers["Location"]


# Non-owner visiting a nonexistent slug on a wiki gets 404
def test_nonowner_visiting_nonexistent_page_gets_404(client):
    create_user_with_username(client, "vis404@example.com", "vis404", "exists2")
    r = client.get("/nope", headers={"Host": "vis404.jottit.localhost:8000"})
    assert r.status_code == 404


# Visiting a claimed page's slug on the main domain redirects to wiki subdomain
def test_main_domain_slug_redirects_to_wiki(client):
    create_user_with_username(client, "redir@example.com", "redir", "mypage")
    r = client.get("/mypage")
    assert r.status_code == 301
    assert "redir.jottit.localhost:8000/mypage" in r.headers["Location"]


# License appears in the page footer on wiki subdomains
def test_license_shows_in_page_footer(client):
    from db import update_wiki
    user_id = create_user_with_username(client, "licfoot@example.com", "licfoot", "lf1")
    wiki = get_default_wiki_for_user(user_id)
    update_wiki(wiki["id"], license="cc-by-sa-4.0")

    r = client.get("/lf1", headers={"Host": "licfoot.jottit.localhost:8000"})
    assert r.status_code == 200
    assert b"CC BY-SA 4.0" in r.data
    assert b"creativecommons.org" in r.data


# Wiki subdomain serves content directly without redirect
def test_subdomain_serves_directly(client):
    create_user_with_username(client, "legacy@example.com", "legacyuser", "lp1")
    r = client.get("/lp1", headers={"Host": "legacyuser.jottit.localhost:8000"})
    assert r.status_code == 200
    assert b"Content" in r.data
