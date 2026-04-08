import pytest

from conftest import create_user_with_username
from db import (
    find_or_create_user,
    get_page_meta,
    rename_page,
    save_page,
    set_user_username,
)
from utils import slugify, valid_slug

# -- /{slug}.md --


def test_md_returns_raw_markdown(client):
    client.post("/fmtmd/edit", data={"title": "Hello", "content": "**bold** text"})
    r = client.get("/fmtmd.md")
    assert r.status_code == 200
    assert r.content_type == "text/markdown; charset=utf-8"
    assert b"**bold** text" in r.data


def test_md_includes_title_line(client):
    client.post("/fmttitle/edit", data={"title": "My Title", "content": "Body"})
    r = client.get("/fmttitle.md")
    assert r.status_code == 200
    body = r.data.decode()
    assert body.startswith("# My Title\n")
    assert "Body" in body


def test_md_nonexistent_returns_404(client):
    r = client.get("/nonexistent.md")
    assert r.status_code == 404


# -- /{slug}.txt --


def test_txt_returns_plain_text(client):
    client.post("/fmttxt/edit", data={"title": "Hello", "content": "Some text"})
    r = client.get("/fmttxt.txt")
    assert r.status_code == 200
    assert r.content_type == "text/plain; charset=utf-8"
    assert b"Some text" in r.data


def test_txt_nonexistent_returns_404(client):
    r = client.get("/nonexistent.txt")
    assert r.status_code == 404


def test_txt_converts_links_readably(client):
    md = "Visit [Jottit](https://jottit.org) for more"
    client.post("/fmtlink/edit", data={"title": "", "content": md})
    r = client.get("/fmtlink.txt")
    body = r.data.decode()
    assert "Jottit" in body
    assert "https://jottit.org" in body
    # Should not contain raw HTML tags
    assert "<a " not in body
    assert "</a>" not in body


def test_txt_converts_emphasis_readably(client):
    md = "This is **bold** and *italic*"
    client.post("/fmtemph/edit", data={"title": "", "content": md})
    r = client.get("/fmtemph.txt")
    body = r.data.decode()
    assert "bold" in body
    assert "italic" in body
    assert "<strong>" not in body
    assert "<em>" not in body


def test_txt_converts_headings(client):
    md = "# Main Title\n\nSome paragraph"
    client.post("/fmthdr/edit", data={"title": "", "content": md})
    r = client.get("/fmthdr.txt")
    body = r.data.decode()
    assert "Main Title" in body
    assert "Some paragraph" in body
    assert "<h1" not in body


# -- /@<username>/<slug>.md --


def test_profile_md_returns_raw_markdown(client):
    create_user_with_username(client, "md@example.com", "mduser", "mdpage")
    r = client.get("/@mduser/mdpage.md")
    assert r.status_code == 200
    assert r.content_type == "text/markdown; charset=utf-8"
    assert b"# Test" in r.data


def test_profile_md_nonexistent_returns_404(client):
    create_user_with_username(client, "md2@example.com", "md2user", "md2page")
    r = client.get("/@md2user/nope.md")
    assert r.status_code == 404


# -- /@<username>/<slug>.txt --


def test_profile_txt_returns_plain_text(client):
    create_user_with_username(client, "txt@example.com", "txtuser", "txtpage")
    r = client.get("/@txtuser/txtpage.txt")
    assert r.status_code == 200
    assert r.content_type == "text/plain; charset=utf-8"
    assert b"Content" in r.data


def test_profile_txt_nonexistent_returns_404(client):
    create_user_with_username(client, "txt2@example.com", "txt2user", "txt2page")
    r = client.get("/@txt2user/nope.txt")
    assert r.status_code == 404


# -- Redirect behavior --


def test_claimed_page_redirects_md_to_profile(client):
    create_user_with_username(client, "rmd@example.com", "rmduser", "rmdpage")
    r = client.get("/rmdpage.md")
    assert r.status_code == 302
    assert "/@rmduser/rmdpage.md" in r.headers["Location"]


def test_claimed_page_redirects_txt_to_profile(client):
    create_user_with_username(client, "rtxt@example.com", "rtxtuser", "rtxtpage")
    r = client.get("/rtxtpage.txt")
    assert r.status_code == 302
    assert "/@rtxtuser/rtxtpage.txt" in r.headers["Location"]


def test_original_slug_redirect_preserves_md_suffix(client):
    user_id = create_user_with_username(
        client, "oslug@example.com", "osluguser", "oldname"
    )
    page_meta = get_page_meta("oldname", user_id)
    rename_page(page_meta["id"], "newname")
    r = client.get("/@osluguser/oldname.md")
    assert r.status_code == 301
    assert "newname.md" in r.headers["Location"]


def test_original_slug_redirect_preserves_txt_suffix(client):
    user_id = create_user_with_username(
        client, "oslug2@example.com", "oslug2user", "oldtxt"
    )
    page_meta = get_page_meta("oldtxt", user_id)
    rename_page(page_meta["id"], "newtxt")
    r = client.get("/@oslug2user/oldtxt.txt")
    assert r.status_code == 301
    assert "newtxt.txt" in r.headers["Location"]


# -- Caching --


def test_md_has_cache_header_for_public_page(client):
    client.post("/cachemd/edit", data={"title": "T", "content": "C"})
    r = client.get("/cachemd.md")
    assert "public" in r.headers.get("Cache-Control", "")


def test_txt_has_cache_header_for_public_page(client):
    client.post("/cachetxt/edit", data={"title": "T", "content": "C"})
    r = client.get("/cachetxt.txt")
    assert "public" in r.headers.get("Cache-Control", "")


# -- Dotted slug collision prevention --


def test_valid_slug_rejects_dots():
    assert valid_slug("notes") is True
    assert valid_slug("my-page") is True
    assert valid_slug("notes.md") is False
    assert valid_slug("notes.txt") is False
    assert valid_slug("file.name") is False


def test_slugify_strips_dots():
    assert "." not in slugify("notes.md")
    assert "." not in slugify("my.file.name")
    assert slugify("notes.md") == "notesmd"


def test_edit_dotted_slug_returns_404(client):
    r = client.get("/notes.md/edit")
    assert r.status_code == 404


def test_create_via_edit_dotted_slug_returns_404(client):
    r = client.post("/notes.md/edit", data={"title": "T", "content": "C"})
    assert r.status_code == 404


def test_save_page_rejects_dotted_slug(client):
    with pytest.raises(ValueError):
        save_page("notes.md", "# Test\n\nContent", "listed")


def test_rename_page_rejects_dotted_slug(client):
    save_page("goodslug", "# Test\n\nContent", "listed")
    page_meta = get_page_meta("goodslug")
    with pytest.raises(ValueError):
        rename_page(page_meta["id"], "bad.slug")


def test_title_derived_slug_has_no_dots(client):
    user_id = find_or_create_user("dottest@example.com")
    set_user_username(user_id, "dotuser")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post("/new", data={"title": "notes.md", "content": "Body"})
    assert r.status_code == 302
    location = r.headers["Location"]
    slug = location.split("/")[-1]
    assert "." not in slug


def test_md_route_still_works_after_dot_restriction(client):
    client.post("/dotcheck/edit", data={"title": "Test", "content": "Body"})
    r = client.get("/dotcheck.md")
    assert r.status_code == 200
    assert r.content_type == "text/markdown; charset=utf-8"


def test_txt_route_still_works_after_dot_restriction(client):
    client.post("/dotcheck2/edit", data={"title": "Test", "content": "Body"})
    r = client.get("/dotcheck2.txt")
    assert r.status_code == 200
    assert r.content_type == "text/plain; charset=utf-8"
