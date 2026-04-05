from conftest import create_user_with_username
from db import (
    assign_page_to_wiki,
    check_wiki_slug_available,
    claim_page,
    create_wiki,
    find_or_create_user,
    get_default_wiki_for_user,
    get_page_meta,
    get_pages_for_wiki,
    get_public_pages_for_user_wikis,
    get_wiki,
    get_wiki_by_slug,
    get_wikis_for_user,
    save_page,
    set_user_username,
    update_user_settings,
    update_wiki,
)


# -- Wiki creation --


def test_create_wiki(client):
    user_id = find_or_create_user("wiki@example.com")
    set_user_username(user_id, "wikiuser")
    wiki_id = create_wiki("mywiki", "My Wiki", user_id)
    wiki = get_wiki(wiki_id)
    assert wiki["slug"] == "mywiki"
    assert wiki["name"] == "My Wiki"
    assert wiki["owner_id"] == user_id
    assert wiki["visibility"] == "public"


def test_wiki_slug_uniqueness(client):
    user_id = find_or_create_user("wiki2@example.com")
    create_wiki("unique-slug", "Wiki 1", user_id)
    assert not check_wiki_slug_available("unique-slug")
    assert check_wiki_slug_available("other-slug")


def test_get_wiki_by_slug(client):
    user_id = find_or_create_user("wiki3@example.com")
    wiki_id = create_wiki("findme", "Find Me", user_id)
    wiki = get_wiki_by_slug("findme")
    assert wiki is not None
    assert wiki["id"] == wiki_id


def test_get_wikis_for_user(client):
    user_id = find_or_create_user("wiki4@example.com")
    create_wiki("wiki-a", "Wiki A", user_id)
    create_wiki("wiki-b", "Wiki B", user_id)
    wikis = get_wikis_for_user(user_id)
    assert len(wikis) == 2


def test_default_wiki_for_user(client):
    user_id = find_or_create_user("wiki5@example.com")
    create_wiki("first-wiki", "First Wiki", user_id)
    create_wiki("second-wiki", "Second Wiki", user_id)
    default = get_default_wiki_for_user(user_id)
    assert default["slug"] == "first-wiki"


# -- Wiki page association --


def test_page_belongs_to_wiki(client):
    user_id = find_or_create_user("wikip@example.com")
    wiki_id = create_wiki("pagwiki", "Pag Wiki", user_id)
    save_page("wiki-page", "# Wiki Page\n\nContent", "listed", user_id, wiki_id=wiki_id)
    meta = get_page_meta("wiki-page", wiki_id=wiki_id)
    assert meta is not None
    assert meta["wiki_id"] == wiki_id


def test_pages_for_wiki(client):
    user_id = find_or_create_user("wikipp@example.com")
    wiki_id = create_wiki("ppwiki", "PP Wiki", user_id)
    save_page("pp1", "# Page 1\n\nContent", "listed", user_id, wiki_id=wiki_id)
    save_page("pp2", "# Page 2\n\nContent", "listed", user_id, wiki_id=wiki_id)
    pages = get_pages_for_wiki(wiki_id)
    assert len(pages) == 2


# -- Wiki subdomain routing --


def test_wiki_subdomain_serves_content(client):
    user_id = create_user_with_username(client, "sub@example.com", "subwiki", "subpage")
    r = client.get("/subpage", headers={"Host": "subwiki.jottit.localhost:8000"})
    assert r.status_code == 200
    assert b"Content" in r.data


def test_wiki_subdomain_home(client):
    user_id = create_user_with_username(client, "subh@example.com", "subhome", "shpage")
    update_user_settings(user_id, "Sub Home", "subhome")
    r = client.get("/", headers={"Host": "subhome.jottit.localhost:8000"})
    assert r.status_code == 200


def test_wiki_subdomain_does_not_redirect_to_username(client):
    create_user_with_username(client, "noredirect@example.com", "noredir", "nrpage")
    r = client.get("/nrpage", headers={"Host": "noredir.jottit.localhost:8000"})
    # Should serve directly, not redirect to @username
    assert r.status_code == 200


def test_unknown_wiki_subdomain_returns_404(client):
    r = client.get("/", headers={"Host": "nonexistent.jottit.localhost:8000"})
    assert r.status_code == 404


# -- Wiki visibility access control --


def test_public_wiki_viewable_by_anyone(client):
    user_id = create_user_with_username(client, "pubwiki@example.com", "pubwiki", "pubp")
    r = client.get("/pubp", headers={"Host": "pubwiki.jottit.localhost:8000"})
    assert r.status_code == 200


def test_private_wiki_hidden_from_anonymous(client):
    user_id = find_or_create_user("privwiki@example.com")
    set_user_username(user_id, "privwiki")
    wiki_id = create_wiki("privwiki", "Private Wiki", user_id, visibility="private")
    save_page("secret", "# Secret\n\nContent", "listed", user_id, wiki_id=wiki_id)
    assign_page_to_wiki(get_page_meta("secret", user_id)["id"], wiki_id)
    r = client.get("/secret", headers={"Host": "privwiki.jottit.localhost:8000"})
    assert r.status_code == 404


def test_private_wiki_viewable_by_owner(client):
    user_id = find_or_create_user("privown@example.com")
    set_user_username(user_id, "privown")
    wiki_id = create_wiki("privown", "Private Wiki", user_id, visibility="private")
    save_page("ownsecret", "# Secret\n\nContent", "listed", user_id, wiki_id=wiki_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/ownsecret", headers={"Host": "privown.jottit.localhost:8000"})
    assert r.status_code == 200


# -- Wiki creation UI --


def test_wiki_creation_flow(client):
    user_id = find_or_create_user("newwiki@example.com")
    set_user_username(user_id, "newwikiuser")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/wiki/new")
    assert r.status_code == 200
    r = client.post("/wiki/new", data={
        "name": "My New Wiki",
        "slug": "my-new-wiki",
        "visibility": "public",
    })
    assert r.status_code == 302
    wiki = get_wiki_by_slug("my-new-wiki")
    assert wiki is not None
    assert wiki["name"] == "My New Wiki"
    assert wiki["owner_id"] == user_id


def test_wiki_creation_requires_auth(client):
    r = client.post("/wiki/new", data={
        "name": "Noauth Wiki",
        "slug": "noauth",
        "visibility": "public",
    })
    assert r.status_code == 302
    assert "/signin" in r.headers["Location"]


def test_wiki_duplicate_slug_rejected(client):
    user_id = find_or_create_user("dup@example.com")
    set_user_username(user_id, "dupuser")
    create_wiki("taken-slug", "Existing", user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post("/wiki/new", data={
        "name": "New Wiki",
        "slug": "taken-slug",
        "visibility": "public",
    })
    assert r.status_code == 200
    assert b"already taken" in r.data


# -- @username profile aggregation --


def test_profile_shows_pages_across_public_wikis(client):
    user_id = find_or_create_user("agg@example.com")
    set_user_username(user_id, "agguser")
    update_user_settings(user_id, "Agg User", "agguser")
    wiki1_id = create_wiki("agg-wiki1", "Wiki One", user_id)
    wiki2_id = create_wiki("agg-wiki2", "Wiki Two", user_id)
    save_page("page-one", "# Page One\n\nContent", "listed", user_id, wiki_id=wiki1_id)
    save_page("page-two", "# Page Two\n\nContent", "listed", user_id, wiki_id=wiki2_id)
    r = client.get("/@agguser")
    assert r.status_code == 200
    assert b"Page One" in r.data
    assert b"Page Two" in r.data


def test_profile_hides_private_wiki_pages(client):
    user_id = find_or_create_user("aggpriv@example.com")
    set_user_username(user_id, "aggpriv")
    update_user_settings(user_id, "Priv User", "aggpriv")
    pub_wiki = create_wiki("aggpriv-pub", "Public Wiki", user_id, visibility="public")
    priv_wiki = create_wiki("aggpriv-priv", "Private Wiki", user_id, visibility="private")
    save_page("pub-page", "# Public\n\nContent", "listed", user_id, wiki_id=pub_wiki)
    save_page("priv-page", "# Private\n\nContent", "listed", user_id, wiki_id=priv_wiki)
    r = client.get("/@aggpriv")
    assert r.status_code == 200
    assert b"Public" in r.data
    assert b"priv-page" not in r.data


# -- Unclaimed pages still work --


def test_unclaimed_page_on_apex_domain(client):
    save_page("unclaimed", "# Unclaimed\n\nContent", "unlisted")
    r = client.get("/unclaimed")
    assert r.status_code == 200
    assert b"Unclaimed" in r.data


# -- Page visibility limited to unlisted/listed/pinned --


def test_page_visibility_no_private_option(client):
    user_id = create_user_with_username(client, "nopri@example.com", "nopri", "np1")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post(
        "/np1/visibility",
        data={"visibility": "private"},
        headers={"Host": "nopri.jottit.localhost:8000"},
    )
    # Private is not in VISIBILITY_OPTIONS, should default to "listed"
    meta = get_page_meta("np1", user_id)
    assert meta["visibility"] == "listed"


# -- Wiki switcher in admin banner --


def test_admin_banner_shows_wiki_switcher(client):
    user_id = create_user_with_username(client, "swit@example.com", "switcher", "sw1")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/")
    assert r.status_code == 200
    assert b"wiki-switcher" in r.data
    assert b"switcher" in r.data


# -- @username page routes redirect to wiki subdomain --


def test_profile_page_redirects_to_wiki_subdomain(client):
    create_user_with_username(client, "redir@example.com", "redirwiki", "rp1")
    r = client.get("/@redirwiki/rp1")
    assert r.status_code == 301
    assert "redirwiki.jottit.localhost:8000/rp1" in r.headers["Location"]


# -- Apex domain claimed page redirects to wiki subdomain --


def test_apex_claimed_page_redirects_to_wiki(client):
    create_user_with_username(client, "apex@example.com", "apexwiki", "ap1")
    r = client.get("/ap1")
    assert r.status_code == 301
    assert "apexwiki.jottit.localhost:8000/ap1" in r.headers["Location"]


# -- Wiki update --


def test_update_wiki_settings(client):
    user_id = find_or_create_user("upd@example.com")
    wiki_id = create_wiki("updwiki", "Old Name", user_id)
    update_wiki(wiki_id, name="New Name", visibility="private", license="cc-by-4.0")
    wiki = get_wiki(wiki_id)
    assert wiki["name"] == "New Name"
    assert wiki["visibility"] == "private"
    assert wiki["license"] == "cc-by-4.0"


# -- Migration creates default wiki for existing users --


def test_existing_user_has_default_wiki(client):
    user_id = create_user_with_username(client, "migr@example.com", "migruser", "mp1")
    wiki = get_default_wiki_for_user(user_id)
    assert wiki is not None
    assert wiki["slug"] == "migruser"
