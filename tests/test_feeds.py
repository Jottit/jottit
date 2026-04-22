import json

from conftest import create_user_with_username, sd
from db import (
    claim_page,
    find_or_create_user,
    get_page_meta,
    save_page,
    set_user_username,
    update_page_visibility,
)

# -- RSS Feed --


def _create_claimed_page(slug, title, content):
    user_id = find_or_create_user(f"{slug}@example.com")
    set_user_username(user_id, slug)
    save_page(slug, f"# {title}\n\n{content}", "listed")
    page_meta = get_page_meta(slug)
    claim_page(page_meta["id"], user_id)
    return user_id


# Single-page RSS feed returns valid RSS XML with title and content
def test_rss_feed(client):
    _create_claimed_page("feed1", "Hello", "World")
    r = client.get("/feed1/feed.xml", base_url=sd("feed1"))
    assert r.status_code == 200
    assert r.content_type == "application/rss+xml; charset=utf-8"
    assert b"<title>Hello</title>" in r.data
    assert b"World" in r.data
    assert b'<rss version="2.0"' in r.data


# RSS feed for nonexistent page returns 404
def test_rss_feed_nonexistent(client):
    r = client.get("/nope/feed.xml")
    assert r.status_code == 404


# RSS feed includes source markdown in a custom element
def test_rss_feed_has_source_markdown(client):
    _create_claimed_page("feed5", "T", "**bold**")
    r = client.get("/feed5/feed.xml", base_url=sd("feed5"))
    assert b"<source:markdown>" in r.data
    assert b"**bold**" in r.data


# -- JSON Feed --


# Single-page JSON feed returns valid JSON Feed 1.1 with content and source markdown
def test_json_feed(client):
    _create_claimed_page("jf1", "Hello", "World")
    r = client.get("/jf1/feed.json", base_url=sd("jf1"))
    assert r.status_code == 200
    assert r.content_type == "application/feed+json; charset=utf-8"
    feed = json.loads(r.data)
    assert feed["version"] == "https://jsonfeed.org/version/1.1"
    assert feed["title"] == "Hello"
    assert len(feed["items"]) == 1
    assert feed["items"][0]["title"] == "Hello"
    assert "World" in feed["items"][0]["content_html"]
    assert feed["items"][0]["_source_markdown"] == "World"


# JSON feed for nonexistent page returns 404
def test_json_feed_nonexistent(client):
    r = client.get("/nope/feed.json")
    assert r.status_code == 404


# -- Feed discovery --


# Published pages on profiles include RSS and JSON feed discovery link tags
def test_page_has_feed_discovery_links(client):
    _create_claimed_page("disc1", "T", "X")
    r = client.get("/disc1", base_url=sd("disc1"))
    assert b'type="application/rss+xml"' in r.data
    assert b"/feed.xml" in r.data
    assert b'type="application/feed+json"' in r.data
    assert b"/feed.json" in r.data


# -- Site-level feeds --


# Profile RSS feed includes all the user's pages with source markdown
def test_site_rss_feed(client):
    user_id = create_user_with_username(client, "rsssite@example.com", "rsssite", "rp1")
    save_page("rp2", "# Second Post\n\n**bold**", "listed")
    page_meta = get_page_meta("rp2")
    claim_page(page_meta["id"], user_id)

    r = client.get("/feed.xml", base_url=sd("rsssite"))
    assert r.status_code == 200
    assert r.content_type == "application/rss+xml; charset=utf-8"
    assert b'<rss version="2.0"' in r.data
    assert b"<source:markdown>" in r.data
    assert b"**bold**" in r.data
    assert b"<title>Second Post</title>" in r.data
    assert b"<title>Test</title>" in r.data


# Profile JSON feed includes all the user's pages
def test_site_json_feed(client):
    user_id = create_user_with_username(
        client, "jsonsite@example.com", "jsonsite", "jp1"
    )
    save_page("jp2", "# Page Two\n\nsome text", "listed")
    page_meta = get_page_meta("jp2")
    claim_page(page_meta["id"], user_id)

    r = client.get("/feed.json", base_url=sd("jsonsite"))
    assert r.status_code == 200
    assert r.content_type == "application/feed+json; charset=utf-8"
    feed = json.loads(r.data)
    assert feed["version"] == "https://jsonfeed.org/version/1.1"
    assert len(feed["items"]) == 2
    titles = {item["title"] for item in feed["items"]}
    assert "Page Two" in titles
    assert "Test" in titles
    assert feed["items"][0]["_source_markdown"]


# Profile homepage includes feed discovery links
def test_site_feed_discovery_links(client):
    create_user_with_username(client, "discsite@example.com", "discsite", "dp1")
    r = client.get("/", base_url=sd("discsite"))
    assert b'type="application/rss+xml"' in r.data
    assert b"/feed.xml" in r.data
    assert b'type="application/feed+json"' in r.data
    assert b"/feed.json" in r.data


# Unlisted pages are excluded from site feeds
def test_site_feed_excludes_unlisted(client):
    user_id = create_user_with_username(
        client, "feedlist@example.com", "feedlist", "flp1"
    )
    save_page("flp2", "# Unlisted\n\nHidden", "listed")
    page_meta = get_page_meta("flp2")
    claim_page(page_meta["id"], user_id)
    update_page_visibility(page_meta["id"], "unlisted")

    r = client.get("/feed.xml", base_url=sd("feedlist"))
    assert b"<title>Test</title>" in r.data
    assert b"Unlisted" not in r.data

    r = client.get("/feed.json", base_url=sd("feedlist"))
    feed = json.loads(r.data)
    assert len(feed["items"]) == 1
    assert feed["items"][0]["title"] == "Test"


# Pinned pages are included in site feeds
def test_site_feed_includes_pinned(client):
    user_id = create_user_with_username(
        client, "feedpin@example.com", "feedpin", "fpp1"
    )
    update_page_visibility(get_page_meta("fpp1", user_id)["id"], "pinned")

    r = client.get("/feed.json", base_url=sd("feedpin"))
    feed = json.loads(r.data)
    assert len(feed["items"]) == 1
    assert feed["items"][0]["title"] == "Test"


# Site-level feeds on the main domain return 404
def test_site_feed_404_on_main_domain(client):
    r = client.get("/feed.xml")
    assert r.status_code == 404
    r = client.get("/feed.json")
    assert r.status_code == 404
