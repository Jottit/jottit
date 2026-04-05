import json

from conftest import create_user_with_username
from db import (
    assign_page_to_wiki,
    claim_page,
    create_wiki,
    check_wiki_slug_available,
    find_or_create_user,
    get_default_wiki_for_user,
    get_page_meta,
    save_page,
    set_user_username,
    update_page_visibility,
)

# -- RSS Feed --


def _wiki_host(wiki_slug):
    return {"Host": f"{wiki_slug}.jottit.localhost:8000"}


# Single-page RSS feed returns valid RSS XML with title and content
def test_rss_feed(client):
    create_user_with_username(client, "feed1@example.com", "feed1", "feed1")
    r = client.get("/feed1/feed.xml", headers=_wiki_host("feed1"))
    assert r.status_code == 200
    assert r.content_type == "application/rss+xml; charset=utf-8"
    assert b"<title>Test</title>" in r.data
    assert b"Content" in r.data
    assert b'<rss version="2.0"' in r.data


# RSS feed for nonexistent page returns 404
def test_rss_feed_nonexistent(client):
    r = client.get("/nope/feed.xml")
    assert r.status_code == 404


# RSS feed includes source markdown in a custom element
def test_rss_feed_has_source_markdown(client):
    user_id = find_or_create_user("feed5@example.com")
    set_user_username(user_id, "feed5")
    wiki_id = create_wiki("feed5", "feed5", user_id)
    save_page("feed5", "# T\n\n**bold**", "listed", user_id, wiki_id=wiki_id)
    r = client.get("/feed5/feed.xml", headers=_wiki_host("feed5"))
    assert b"<source:markdown>" in r.data
    assert b"**bold**" in r.data


# -- JSON Feed --


# Single-page JSON feed returns valid JSON Feed 1.1 with content and source markdown
def test_json_feed(client):
    user_id = find_or_create_user("jf1@example.com")
    set_user_username(user_id, "jf1")
    wiki_id = create_wiki("jf1", "jf1", user_id)
    save_page("jf1", "# Hello\n\nWorld", "listed", user_id, wiki_id=wiki_id)
    r = client.get("/jf1/feed.json", headers=_wiki_host("jf1"))
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


# Published pages on wiki subdomains include RSS and JSON feed discovery link tags
def test_page_has_feed_discovery_links(client):
    create_user_with_username(client, "disc1@example.com", "disc1", "disc1")
    r = client.get("/disc1", headers=_wiki_host("disc1"))
    assert b'type="application/rss+xml"' in r.data
    assert b"/feed.xml" in r.data
    assert b'type="application/feed+json"' in r.data
    assert b"/feed.json" in r.data


# -- Site-level feeds --


# Wiki RSS feed includes all the wiki's listed pages
def test_site_rss_feed(client):
    user_id = create_user_with_username(client, "rsssite@example.com", "rsssite", "rp1")
    wiki = get_default_wiki_for_user(user_id)
    save_page("rp2", "# Second Post\n\n**bold**", "listed", user_id, wiki_id=wiki["id"])

    r = client.get("/feed.xml", headers=_wiki_host("rsssite"))
    assert r.status_code == 200
    assert r.content_type == "application/rss+xml; charset=utf-8"
    assert b'<rss version="2.0"' in r.data
    assert b"<source:markdown>" in r.data
    assert b"**bold**" in r.data
    assert b"<title>Second Post</title>" in r.data
    assert b"<title>Test</title>" in r.data


# Wiki JSON feed includes all the wiki's listed pages
def test_site_json_feed(client):
    user_id = create_user_with_username(client, "jsonsite@example.com", "jsonsite", "jp1")
    wiki = get_default_wiki_for_user(user_id)
    save_page("jp2", "# Page Two\n\nsome text", "listed", user_id, wiki_id=wiki["id"])

    r = client.get("/feed.json", headers=_wiki_host("jsonsite"))
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
    r = client.get("/@discsite")
    assert r.status_code == 200


# Unlisted pages are excluded from wiki feeds
def test_site_feed_excludes_unlisted(client):
    user_id = create_user_with_username(client, "feedlist@example.com", "feedlist", "flp1")
    wiki = get_default_wiki_for_user(user_id)
    save_page("flp2", "# Unlisted\n\nHidden", "listed", user_id, wiki_id=wiki["id"])
    meta = get_page_meta("flp2", wiki_id=wiki["id"])
    update_page_visibility(meta["id"], "unlisted")

    r = client.get("/feed.xml", headers=_wiki_host("feedlist"))
    assert b"<title>Test</title>" in r.data
    assert b"Unlisted" not in r.data

    r = client.get("/feed.json", headers=_wiki_host("feedlist"))
    feed = json.loads(r.data)
    assert len(feed["items"]) == 1
    assert feed["items"][0]["title"] == "Test"


# Pinned pages are included in wiki feeds
def test_site_feed_includes_pinned(client):
    user_id = create_user_with_username(client, "feedpin@example.com", "feedpin", "fpp1")
    wiki = get_default_wiki_for_user(user_id)
    meta = get_page_meta("fpp1", wiki_id=wiki["id"])
    update_page_visibility(meta["id"], "pinned")

    r = client.get("/feed.json", headers=_wiki_host("feedpin"))
    feed = json.loads(r.data)
    assert len(feed["items"]) == 1
    assert feed["items"][0]["title"] == "Test"


# Site-level feeds on the main domain return 404
def test_site_feed_404_on_main_domain(client):
    r = client.get("/feed.xml")
    assert r.status_code == 404
    r = client.get("/feed.json")
    assert r.status_code == 404
