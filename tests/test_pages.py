from db import (
    claim_page,
    find_or_create_user,
    get_page_meta,
    save_page,
    set_user_username,
)


def _create_anonymous_page(client, slug, title="T", content="C"):
    """Create an anonymous page and follow the token redirect to set the cookie."""
    r = client.post(f"/{slug}/edit", data={"title": title, "content": content})
    assert r.status_code == 302
    # Follow the ?token= redirect to set the page_token cookie
    location = r.headers["Location"]
    if "?token=" in location:
        r = client.get(location)
        # That redirects to the bare slug after setting the cookie
        assert r.status_code == 302
    return r


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


# Anonymous POST /new creates a page with a random slug, not title-based
def test_new_anonymous_gets_random_slug(client):
    r = client.post("/new", data={"title": "Hello World", "content": "Body"})
    assert r.status_code == 302
    location = r.headers["Location"].lstrip("/")
    slug = location.split("?")[0]
    assert slug != "hello-world"
    assert len(slug) == 6


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
    _create_anonymous_page(client, "existslug", "T", "C")
    r = client.get("/existslug/edit")
    assert b'href="/existslug"' in r.data


# Editing an existing page pre-fills the title and content
def test_edit_get_existing_page(client):
    _create_anonymous_page(client, "abc12", "Hello", "World")
    r = client.get("/abc12/edit")
    assert r.status_code == 200
    assert b"Hello" in r.data
    assert b"World" in r.data


# Saving an edit creates the page and redirects to its slug (with token for anon)
def test_publish_creates_page(client):
    r = client.post("/mypage/edit", data={"title": "Test", "content": "Body"})
    assert r.status_code == 302
    location = r.headers["Location"]
    assert location.startswith("/mypage")


# Viewing a page with a trailing slash redirects to canonical URL
def test_trailing_slash_redirects(client):
    _create_anonymous_page(client, "tslash", "Hi", "There")
    r = client.get("/tslash/")
    assert r.status_code == 301
    assert r.headers["Location"] == "/tslash"


# -- View page --


# Published page renders its title and content
def test_view_page(client):
    _create_anonymous_page(client, "viewme", "Hello", "World")
    r = client.get("/viewme")
    assert r.status_code == 200
    assert b"Hello" in r.data
    assert b"World" in r.data


# Markdown content is rendered to HTML on the published page
def test_view_page_renders_markdown(client):
    _create_anonymous_page(client, "mdpage", "", "**bold**")
    r = client.get("/mdpage")
    assert b"<strong>bold</strong>" in r.data


# Markdown tables render as HTML tables
def test_view_page_renders_table(client):
    table_md = "| A | B |\n|---|---|\n| 1 | 2 |"
    _create_anonymous_page(client, "tablepage", "", table_md)
    r = client.get("/tablepage")
    assert b"<table>" in r.data
    assert b"<th>A</th>" in r.data
    assert b"<td>1</td>" in r.data


# Bare URLs in content are auto-linked on the published page
def test_view_page_autolinks_urls(client):
    _create_anonymous_page(client, "linkpage", "", "Visit https://jottit.org")
    r = client.get("/linkpage")
    assert b'<a href="https://jottit.org">https://jottit.org</a>' in r.data


# Viewing a nonexistent slug returns 404
def test_view_nonexistent_page(client):
    r = client.get("/doesnotexist")
    assert r.status_code == 404


# Page creator sees Edit and History action links
def test_view_page_shows_actions_for_creator(client):
    _create_anonymous_page(client, "owned", "Mine", "Content")
    client.post("/owned/edit", data={"title": "Mine", "content": "Updated"})
    r = client.get("/owned")
    assert b"Edit" in r.data
    assert b"History" in r.data


# After editing, the page shows the most recent content
def test_view_page_shows_latest_content(client):
    _create_anonymous_page(client, "evolve", "V1", "First")
    client.post("/evolve/edit", data={"title": "V2", "content": "Second"})
    r = client.get("/evolve")
    assert b"V2" in r.data
    assert b"Second" in r.data


# -- Private visibility --


# Private pages are visible to their creator (via token cookie)
def test_private_visible_to_creator(client):
    from db import get_page_meta, update_page_visibility

    _create_anonymous_page(client, "dv1", "Secret", "Private content")
    page_meta = get_page_meta("dv1")
    update_page_visibility(page_meta["id"], "private")
    r = client.get("/dv1")
    assert r.status_code == 200
    assert b"private" in r.data.lower()


# Private pages return 404 for non-creators
def test_private_hidden_from_non_creator(client):
    from db import get_page_meta, update_page_visibility

    _create_anonymous_page(client, "dv2", "Secret", "Private content")
    page_meta = get_page_meta("dv2")
    update_page_visibility(page_meta["id"], "private")
    with client.session_transaction() as sess:
        sess.clear()
    # Clear the page token cookie too
    client.delete_cookie(f"page_token_dv2")
    r = client.get("/dv2")
    assert r.status_code == 404


# -- Delete page --


# Page owner can delete their page
def test_owner_can_delete_page(client):
    user_id = find_or_create_user("del@example.com")
    from db import save_page

    save_page("del1", "# T\n\nX", "listed")
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
    from db import save_page

    save_page("del2", "# T\n\nX", "listed")
    page_meta = get_page_meta("del2")
    claim_page(page_meta["id"], user_id)

    r = client.post("/del2/delete", data={"confirmation": "delete"})
    assert r.status_code == 302
    # Non-owner can't find the claimed page, gets redirected away
    assert r.headers["Location"] in ("/del2", "/")


# -- Export --


# Exporting a page returns a zip file with the correct filename
def test_export_zip(client):
    _create_anonymous_page(client, "exp1", "T", "X")
    r = client.get("/exp1/export")
    assert r.status_code == 200
    assert r.content_type == "application/zip"
    assert 'filename="exp1.zip"' in r.headers["Content-Disposition"]


# -- Microformats --


# Published pages include h-entry, p-name, e-content, dt-published, and u-url microformat classes
def test_page_has_h_entry_markup(client):
    _create_anonymous_page(client, "mf1", "Hello", "World")
    r = client.get("/mf1")
    body = r.data.decode()
    assert 'class="page h-entry"' in body
    assert 'class="p-name"' in body
    assert 'class="e-content"' in body
    assert "dt-published" in body
    assert "datetime=" in body
    assert 'class="u-url"' in body
    assert 'href="/mf1"' in body


# -- Wikilinks --


# slugify() converts titles to lowercase hyphenated slugs
def test_slugify():
    from utils import slugify

    assert slugify("Good Writing") == "good-writing"
    assert slugify("Hello World!") == "hello-world"
    assert slugify("  Multiple   Spaces  ") == "multiple-spaces"
    assert slugify("Already-Slugged") == "already-slugged"
    assert slugify("123 Numbers") == "123-numbers"


# Wikilinks are not supported — render as literal text
def test_wikilink_renders_as_text(client):
    _create_anonymous_page(client, "wl1", "", "See [[About]]")
    r = client.get("/wl1")
    assert b"[[About]]" in r.data
    assert b'<a href="/about">' not in r.data


# -- Homepage tabs --


def _setup_user_with_pages(client):
    user_id = find_or_create_user("tabs@example.com")
    set_user_username(user_id, "tabuser")

    for slug, content, vis in [
        ("pub1", "# Public One\n\nContent", "listed"),
        ("pub2", "# Public Two\n\nContent", "listed"),
        ("pin1", "# Pinned Post\n\nContent", "pinned"),
        ("unl1", "# Unlisted Post\n\nContent", "unlisted"),
        ("prv1", "# Private Post\n\nContent", "private"),
    ]:
        save_page(slug, content, vis, user_id=user_id)
        page_meta = get_page_meta(slug, user_id)
        claim_page(page_meta["id"], user_id)

    return user_id


# Logged-in user sees tabs with counts on homepage
def test_homepage_shows_tabs_when_logged_in(client):
    user_id = _setup_user_with_pages(client)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/")
    body = r.data.decode()
    assert "tab--active" in body
    assert "All" in body
    assert "Private" in body
    assert "Unlisted" in body
    assert "Listed" in body
    assert "Pinned" in body


# All tab shows every page on homepage
def test_homepage_all_tab_shows_all_pages(client):
    user_id = _setup_user_with_pages(client)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/")
    body = r.data.decode()
    assert "Public One" in body
    assert "Pinned Post" in body
    assert "Unlisted Post" in body
    assert "Private Post" in body


# Private tab filters to private pages only
def test_homepage_private_tab_filters(client):
    user_id = _setup_user_with_pages(client)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/?tab=private")
    body = r.data.decode()
    assert "Private Post" in body
    assert "Public One" not in body
    assert "Pinned Post" not in body


# Pinned tab filters to pinned pages only
def test_homepage_pinned_tab_filters(client):
    user_id = _setup_user_with_pages(client)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.get("/?tab=pinned")
    body = r.data.decode()
    assert "Pinned Post" in body
    assert "Public One" not in body
    assert "Private Post" not in body


# Public visitor sees no tabs on profile, only listed and pinned
def test_public_profile_shows_no_tabs(client):
    _setup_user_with_pages(client)
    r = client.get("/@tabuser")
    body = r.data.decode()
    assert "tab--active" not in body
    assert "Public One" in body
    assert "Pinned Post" in body
    assert "Unlisted Post" not in body
    assert "Private Post" not in body


# Logged-out homepage shows landing page, no tabs
def test_homepage_logged_out_shows_landing(client):
    r = client.get("/")
    body = r.data.decode()
    assert "tab--active" not in body
    assert "Write something" in body
