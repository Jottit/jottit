from db import claim_page, find_or_create_user, get_page_meta

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
    slug = r.headers["Location"].lstrip("/")
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
    client.post("/existslug/edit", data={"title": "T", "content": "C"})
    r = client.get("/existslug/edit")
    assert b'href="/existslug"' in r.data


# Editing an existing page pre-fills the title and content
def test_edit_get_existing_page(client):
    client.post("/abc12/edit", data={"title": "Hello", "content": "World"})
    r = client.get("/abc12/edit")
    assert r.status_code == 200
    assert b"Hello" in r.data
    assert b"World" in r.data


# Saving an edit creates the page and redirects to its slug
def test_publish_creates_page(client):
    r = client.post("/mypage/edit", data={"title": "Test", "content": "Body"})
    assert r.status_code == 302
    assert r.headers["Location"] == "/mypage"


# Viewing a page with a trailing slash redirects to canonical URL
def test_trailing_slash_redirects(client):
    client.post("/tslash/edit", data={"title": "Hi", "content": "There"})
    r = client.get("/tslash/")
    assert r.status_code == 301
    assert r.headers["Location"] == "/tslash"


# -- View page --


# Published page renders its title and content
def test_view_page(client):
    client.post("/viewme/edit", data={"title": "Hello", "content": "World"})
    r = client.get("/viewme")
    assert r.status_code == 200
    assert b"Hello" in r.data
    assert b"World" in r.data


# Markdown content is rendered to HTML on the published page
def test_view_page_renders_markdown(client):
    client.post("/mdpage/edit", data={"title": "", "content": "**bold**"})
    r = client.get("/mdpage")
    assert b"<strong>bold</strong>" in r.data


# Markdown tables render as HTML tables
def test_view_page_renders_table(client):
    table_md = "| A | B |\n|---|---|\n| 1 | 2 |"
    client.post("/tablepage/edit", data={"title": "", "content": table_md})
    r = client.get("/tablepage")
    assert b"<table>" in r.data
    assert b"<th>A</th>" in r.data
    assert b"<td>1</td>" in r.data


# Bare URLs in content are auto-linked on the published page
def test_view_page_autolinks_urls(client):
    client.post(
        "/linkpage/edit", data={"title": "", "content": "Visit https://jottit.org"}
    )
    r = client.get("/linkpage")
    assert b'<a href="https://jottit.org">https://jottit.org</a>' in r.data


# Viewing a nonexistent slug returns 404
def test_view_nonexistent_page(client):
    r = client.get("/doesnotexist")
    assert r.status_code == 404


# Page creator sees Edit and History action links
def test_view_page_shows_actions_for_creator(client):
    client.post("/owned/edit", data={"title": "Mine", "content": "Content"})
    client.post("/owned/edit", data={"title": "Mine", "content": "Updated"})
    r = client.get("/owned")
    assert b"Edit" in r.data
    assert b"History" in r.data


# After editing, the page shows the most recent content
def test_view_page_shows_latest_content(client):
    client.post("/evolve/edit", data={"title": "V1", "content": "First"})
    client.post("/evolve/edit", data={"title": "V2", "content": "Second"})
    r = client.get("/evolve")
    assert b"V2" in r.data
    assert b"Second" in r.data


# -- Private visibility --


# Private pages are visible to their creator
def test_private_visible_to_creator(client):
    from db import get_page_meta, update_page_visibility

    client.post("/dv1/edit", data={"title": "Secret", "content": "Private content"})
    page_meta = get_page_meta("dv1")
    update_page_visibility(page_meta["id"], "private")
    r = client.get("/dv1")
    assert r.status_code == 200
    assert b"private" in r.data.lower()


# Private pages return 404 for non-creators
def test_private_hidden_from_non_creator(client):
    from db import get_page_meta, update_page_visibility

    client.post("/dv2/edit", data={"title": "Secret", "content": "Private content"})
    page_meta = get_page_meta("dv2")
    update_page_visibility(page_meta["id"], "private")
    with client.session_transaction() as sess:
        sess.clear()
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
    client.post("/exp1/edit", data={"title": "T", "content": "X"})
    r = client.get("/exp1/export")
    assert r.status_code == 200
    assert r.content_type == "application/zip"
    assert 'filename="exp1.zip"' in r.headers["Content-Disposition"]


# -- Microformats --


# Published pages include h-entry, p-name, e-content, dt-published, and u-url microformat classes
def test_page_has_h_entry_markup(client):
    client.post("/mf1/edit", data={"title": "Hello", "content": "World"})
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
    client.post("/wl1/edit", data={"title": "", "content": "See [[About]]"})
    r = client.get("/wl1")
    assert b"[[About]]" in r.data
    assert b'<a href="/about">' not in r.data
