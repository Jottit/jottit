import io
import json
import zipfile

from db import (
    claim_site,
    create_page,
    create_verification_code,
    find_or_create_user,
    get_site,
    save_page,
)
from routes import _describe_change, _parse_nav, _slugify

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
    assert b"Make it yours" in r.data


def test_claimed_page_hides_claim_banner(client):
    client.post("/clmd/edit", data={"title": "T", "content": "X"})
    user_id = find_or_create_user("owner@example.com")
    claim_site("clmd", user_id)
    r = client.get("/clmd")
    assert b"Make it yours" not in r.data


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

    # Submit email — renders verify page directly
    r = client.post("/cf3/claim", data={"email": "user@example.com"})
    assert r.status_code == 200
    assert b"Check your email" in r.data

    # Get the code from the DB
    code = create_verification_code("user@example.com", "claim")

    # Submit code
    r = client.post(
        "/cf3/claim/verify", data={"code": code, "email": "user@example.com"}
    )
    assert r.status_code == 302
    assert r.headers["Location"] == "/cf3"

    # Site is now claimed
    site = get_site("cf3")
    assert site["user_id"] is not None

    # Banner is gone
    r = client.get("/cf3")
    assert b"Make it yours" not in r.data


def test_claim_invalid_code_rejected(client):
    client.post("/cf4/edit", data={"title": "T", "content": "X"})
    client.post("/cf4/claim", data={"email": "user@example.com"})
    r = client.post(
        "/cf4/claim/verify", data={"code": "000000", "email": "user@example.com"}
    )
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


def test_signed_in_user_auto_claims_new_page(client):
    user_id = find_or_create_user("creator@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    client.post("/auto1/edit", data={"title": "Mine", "content": "Auto claimed"})
    site = get_site("auto1")
    assert site["user_id"] == user_id


# -- Sign in flow --


def test_signin_page(client):
    r = client.get("/signin")
    assert r.status_code == 200
    assert b"email" in r.data


def test_signin_full_flow(client):
    # Submit email — renders verify page directly
    r = client.post("/signin", data={"email": "user@example.com"})
    assert r.status_code == 200
    assert b"Check your email" in r.data

    # Get code
    code = create_verification_code("user@example.com", "signin")

    # Submit code
    r = client.post("/signin/verify", data={"code": code, "email": "user@example.com"})
    assert r.status_code == 302
    assert r.headers["Location"] == "/"

    # Session has user_id
    with client.session_transaction() as sess:
        assert "user_id" in sess


def test_signin_invalid_code(client):
    client.post("/signin", data={"email": "user@example.com"})
    r = client.post(
        "/signin/verify", data={"code": "999999", "email": "user@example.com"}
    )
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


def test_homepage_shows_signout_when_logged_in(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1

    r = client.get("/")
    assert b"Sign out" in r.data
    assert b"Sign in" not in r.data


# -- Homepage sites list --


def test_homepage_shows_my_sites_link(client):
    user_id = find_or_create_user("sites@example.com")
    client.post("/mysite1/edit", data={"title": "First", "content": "A"})
    claim_site("mysite1", user_id)

    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/")
    assert b"My sites" in r.data
    assert b"/sites" in r.data


def test_homepage_no_my_sites_link_when_none(client):
    user_id = find_or_create_user("nosites@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/")
    assert b"My sites" not in r.data


# -- Per-site settings --


def _create_claimed_site(client, slug="stest"):
    client.post(f"/{slug}/edit", data={"title": "T", "content": "X"})
    user_id = find_or_create_user("owner@example.com")
    claim_site(slug, user_id)
    return user_id


def test_site_settings_requires_owner(client):
    _create_claimed_site(client, "ss1")
    r = client.get("/ss1/settings")
    assert r.status_code == 302
    assert r.headers["Location"] == "/ss1"


def test_site_settings_shows_form(client):
    user_id = _create_claimed_site(client, "ss2")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/ss2/settings")
    assert r.status_code == 200
    assert b"Site title" in r.data
    assert b"Subdomain" in r.data


def test_site_settings_save_title(client):
    user_id = _create_claimed_site(client, "ss3")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/ss3/settings", data={"title": "My Site", "subdomain": ""})
    assert r.status_code == 302

    site = get_site("ss3")
    assert site["title"] == "My Site"


def test_site_settings_save_subdomain(client):
    user_id = _create_claimed_site(client, "ss4")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/ss4/settings", data={"title": "", "subdomain": "mysite"})
    assert r.status_code == 302

    site = get_site("ss4")
    assert site["subdomain"] == "mysite"


def test_subdomain_invalid_chars_rejected(client):
    user_id = _create_claimed_site(client, "ss5")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/ss5/settings", data={"title": "", "subdomain": "My Site!"})
    assert r.status_code == 200
    assert b"lowercase" in r.data


def test_subdomain_uniqueness(client):
    user_id = _create_claimed_site(client, "ss6")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/ss6/settings", data={"title": "", "subdomain": "taken"})

    user_id2 = _create_claimed_site(client, "ss7")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id2
    r = client.post("/ss7/settings", data={"title": "", "subdomain": "taken"})
    assert r.status_code == 200
    assert b"already taken" in r.data


def test_nav_via_textarea(client):
    user_id = _create_claimed_site(client, "ss8")
    site = get_site("ss8")
    create_page(site["id"], "about")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    client.post(
        "/ss8/edit", data={"title": "About", "content": "Info", "page": "about"}
    )
    client.post(
        "/ss8/settings",
        data={"title": "", "subdomain": "", "nav": "About: about"},
    )
    r = client.get("/ss8")
    assert b"/ss8/about" in r.data
    assert b"About" in r.data


def test_nav_remove_item(client):
    user_id = _create_claimed_site(client, "ss9")
    site = get_site("ss9")
    create_page(site["id"], "about")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    client.post(
        "/ss9/edit", data={"title": "About", "content": "Info", "page": "about"}
    )
    client.post(
        "/ss9/settings",
        data={"title": "", "subdomain": "", "nav": "About: about"},
    )
    # Remove by saving empty nav
    client.post(
        "/ss9/settings",
        data={"title": "", "subdomain": "", "nav": ""},
    )
    r = client.get("/ss9")
    assert b"site-nav" not in r.data


def test_nav_custom_label(client):
    user_id = _create_claimed_site(client, "ss8b")
    site = get_site("ss8b")
    create_page(site["id"], "blog")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    client.post(
        "/ss8b/edit", data={"title": "Blog", "content": "Posts", "page": "blog"}
    )
    client.post(
        "/ss8b/settings",
        data={"title": "", "subdomain": "", "nav": "Writing: blog"},
    )
    r = client.get("/ss8b")
    assert b"Writing" in r.data
    assert b"/ss8b/blog" in r.data


def test_nav_nonexisting_page(client):
    user_id = _create_claimed_site(client, "ss8c")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    client.post(
        "/ss8c/settings",
        data={"title": "", "subdomain": "", "nav": "Ideas: ideas"},
    )
    r = client.get("/ss8c")
    assert b'class="wikilink-new"' in r.data
    assert b"Ideas" in r.data


def test_nav_index_links_to_home(client):
    user_id = _create_claimed_site(client, "ss8d")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    client.post(
        "/ss8d/settings",
        data={"title": "", "subdomain": "", "nav": "Home: index"},
    )
    r = client.get("/ss8d")
    assert b'href="/ss8d"' in r.data
    assert b"Home" in r.data
    assert b"wikilink-new" not in r.data


def test_parse_nav():
    items = _parse_nav("About\nWriting: blog\n\nContact: contact")
    assert len(items) == 3
    assert items[0] == {"label": "About", "slug": "about"}
    assert items[1] == {"label": "Writing", "slug": "blog"}
    assert items[2] == {"label": "Contact", "slug": "contact"}


def test_page_shows_settings_link_for_owner(client):
    user_id = _create_claimed_site(client, "ss10")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/ss10")
    assert b"Settings" in r.data


def test_page_hides_settings_link_for_non_owner(client):
    _create_claimed_site(client, "ss11")
    r = client.get("/ss11")
    assert b"/ss11/settings" not in r.data


def test_settings_page_links_to_site_settings(client):
    user_id = _create_claimed_site(client, "ss12")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/settings")
    assert b"/ss12/settings" in r.data


# -- RSS Feed --


def test_rss_feed(client):
    client.post("/feed1/edit", data={"title": "Hello", "content": "World"})
    r = client.get("/feed1/feed.xml")
    assert r.status_code == 200
    assert r.content_type == "application/rss+xml; charset=utf-8"
    assert b"<title>Hello</title>" in r.data
    assert b"World" in r.data
    assert b'<rss version="2.0"' in r.data


def test_rss_feed_nonexistent_site(client):
    r = client.get("/nope/feed.xml")
    assert r.status_code == 404


def test_rss_feed_excludes_drafts(client):
    client.post(
        "/feed2/edit", data={"title": "Draft", "content": "Hidden", "draft": "on"}
    )
    r = client.get("/feed2/feed.xml")
    assert r.status_code == 200
    assert b"Hidden" not in r.data


def test_rss_feed_latest_revision_only(client):
    client.post("/feed3/edit", data={"title": "V1", "content": "Old"})
    client.post("/feed3/edit", data={"title": "V2", "content": "New"})
    r = client.get("/feed3/feed.xml")
    body = r.data.decode()
    assert body.count("<item>") == 1
    assert "V2" in body
    assert "New" in body


def test_rss_feed_site_title(client):
    user_id = _create_claimed_site(client, "feed4")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/feed4/settings", data={"title": "My Blog", "subdomain": ""})
    r = client.get("/feed4/feed.xml")
    body = r.data.decode()
    assert "<title>My Blog</title>" in body


def test_rss_feed_has_source_markdown(client):
    client.post("/feed5/edit", data={"title": "T", "content": "**bold**"})
    r = client.get("/feed5/feed.xml")
    assert b"<source:markdown>" in r.data
    assert b"**bold**" in r.data


# -- JSON Feed --


def test_json_feed(client):
    client.post("/jf1/edit", data={"title": "Hello", "content": "World"})
    r = client.get("/jf1/feed.json")
    assert r.status_code == 200
    assert r.content_type == "application/feed+json; charset=utf-8"
    feed = json.loads(r.data)
    assert feed["version"] == "https://jsonfeed.org/version/1.1"
    assert feed["title"] == "jf1"
    assert len(feed["items"]) == 1
    assert feed["items"][0]["title"] == "Hello"
    assert "World" in feed["items"][0]["content_html"]
    assert feed["items"][0]["_source_markdown"] == "World"


def test_json_feed_nonexistent_site(client):
    r = client.get("/nope/feed.json")
    assert r.status_code == 404


def test_json_feed_excludes_drafts(client):
    client.post(
        "/jf2/edit", data={"title": "Draft", "content": "Hidden", "draft": "on"}
    )
    r = client.get("/jf2/feed.json")
    feed = json.loads(r.data)
    assert len(feed["items"]) == 0


# -- Feed discovery --


def test_page_has_feed_discovery_links(client):
    client.post("/disc1/edit", data={"title": "T", "content": "X"})
    r = client.get("/disc1")
    assert b'type="application/rss+xml"' in r.data
    assert b"/disc1/feed.xml" in r.data
    assert b'type="application/feed+json"' in r.data
    assert b"/disc1/feed.json" in r.data


# -- Export --


def test_export_requires_owner(client):
    _create_claimed_site(client, "exp1")
    r = client.get("/exp1/export")
    assert r.status_code == 302
    assert r.headers["Location"] == "/exp1"


def test_export_zip(client):
    user_id = _create_claimed_site(client, "exp2")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/exp2/export")
    assert r.status_code == 200
    assert r.content_type == "application/zip"
    assert 'filename="exp2.zip"' in r.headers["Content-Disposition"]

    zf = zipfile.ZipFile(io.BytesIO(r.data))
    names = zf.namelist()
    assert "exp2/index.md" in names
    content = zf.read("exp2/index.md").decode()
    assert "title: T" in content
    assert "date:" in content
    assert "X" in content


def test_export_excludes_drafts(client):
    user_id = _create_claimed_site(client, "exp3")
    # Add a draft-only page
    site = get_site("exp3")
    create_page(site["id"], "draftpage")
    client.post(
        "/exp3/edit",
        data={
            "title": "Draft",
            "content": "Hidden",
            "page": "draftpage",
            "draft": "on",
        },
    )
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/exp3/export")
    zf = zipfile.ZipFile(io.BytesIO(r.data))
    names = zf.namelist()
    assert "exp3/draftpage.md" not in names


def test_export_settings_has_link(client):
    user_id = _create_claimed_site(client, "exp4")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/exp4/settings")
    assert b"/exp4/export" in r.data


# -- Wikilinks --


def test_slugify():
    assert _slugify("Good Writing") == "good-writing"
    assert _slugify("Hello World!") == "hello-world"
    assert _slugify("  Multiple   Spaces  ") == "multiple-spaces"
    assert _slugify("Already-Slugged") == "already-slugged"
    assert _slugify("123 Numbers") == "123-numbers"


def test_wikilink_existing_page(client):
    user_id = _create_claimed_site(client, "wl1")
    site = get_site("wl1")
    create_page(site["id"], "about")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/wl1/edit", data={"title": "", "content": "See [[About]]"})
    r = client.get("/wl1")
    assert b'<a href="/wl1/about">About</a>' in r.data


def test_wikilink_nonexisting_page(client):
    client.post("/wl2/edit", data={"title": "", "content": "See [[New Page]]"})
    r = client.get("/wl2")
    assert b'class="wikilink-new"' in r.data
    assert b'href="/wl2/edit?page=new-page"' in r.data
    assert b"New Page</a>" in r.data


def test_wikilink_preserves_regular_markdown(client):
    client.post(
        "/wl3/edit",
        data={"title": "", "content": "A [link](http://example.com) and [[Wiki]]"},
    )
    r = client.get("/wl3")
    assert b'href="http://example.com"' in r.data
    assert b"Wiki</a>" in r.data


def test_view_subpage(client):
    client.post("/sp1/edit", data={"title": "Main", "content": "Home"})
    client.post(
        "/sp1/edit", data={"title": "About", "content": "Info", "page": "about"}
    )
    r = client.get("/sp1/about")
    assert r.status_code == 200
    assert b"Info" in r.data


def test_view_subpage_404(client):
    client.post("/sp2/edit", data={"title": "Main", "content": "Home"})
    r = client.get("/sp2/nope")
    assert r.status_code == 404


# -- Microformats --


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


def test_site_header_has_h_card(client):
    user_id = _create_claimed_site(client, "mf2")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/mf2/settings", data={"title": "My Site", "subdomain": ""})
    r = client.get("/mf2")
    body = r.data.decode()
    assert "h-card" in body
    assert 'class="p-name u-url"' in body
    assert "My Site</a>" in body


def test_subpage_u_url_includes_page_slug(client):
    client.post("/mf3/edit", data={"title": "Main", "content": "Home"})
    client.post(
        "/mf3/edit", data={"title": "About", "content": "Info", "page": "about"}
    )
    r = client.get("/mf3/about")
    assert b'href="/mf3/about" hidden' in r.data


def test_edit_subpage_redirects_to_subpage(client):
    client.post("/sp3/edit", data={"title": "Main", "content": "Home"})
    r = client.post(
        "/sp3/edit", data={"title": "About", "content": "Info", "page": "about"}
    )
    assert r.status_code == 302
    assert r.headers["Location"] == "/sp3/about"


# -- Subdomain routing --


def test_slug_redirects_to_subdomain(client):
    user_id = _create_claimed_site(client, "sd1")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/sd1/settings", data={"title": "", "subdomain": "mysite", "nav": ""})
    r = client.get("/sd1")
    assert r.status_code == 302
    assert "mysite.jottit.localhost:8000" in r.headers["Location"]


def test_slug_subpage_redirects_to_subdomain(client):
    user_id = _create_claimed_site(client, "sd2")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/sd2/settings", data={"title": "", "subdomain": "sub2", "nav": ""})
    client.post(
        "/sd2/edit", data={"title": "About", "content": "Info", "page": "about"}
    )
    r = client.get("/sd2/about")
    assert r.status_code == 302
    assert "/about" in r.headers["Location"]


def test_settings_redirects_to_subdomain_after_save(client):
    user_id = _create_claimed_site(client, "sd3")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post(
        "/sd3/settings", data={"title": "", "subdomain": "newname", "nav": ""}
    )
    assert r.status_code == 302
    assert "newname.jottit.localhost:8000" in r.headers["Location"]
    assert "/settings" in r.headers["Location"]


# -- Home page sites limit --


def _create_user_with_sites(client, count):
    user_id = find_or_create_user(f"limit{count}@example.com")
    for i in range(count):
        slug = f"limit{count}s{i}"
        save_page(slug, f"# Site {i}\n\nContent", False)
        claim_site(slug, user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return user_id


# -- /sites page --


def test_sites_page_lists_all(client):
    _create_user_with_sites(client, 5)
    r = client.get("/sites")
    assert r.status_code == 200
    body = r.data.decode()
    assert body.count("all-sites-list") >= 1
    for i in range(5):
        assert f"limit5s{i}" in body


def test_sites_page_requires_signin(client):
    r = client.get("/sites")
    assert r.status_code == 302
    assert "/signin" in r.headers["Location"]
