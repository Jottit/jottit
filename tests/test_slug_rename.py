from db import (
    find_slug_redirect,
    find_slug_redirect_with_owner,
    get_page_meta,
    rename_page,
    save_page,
)
from conftest import create_user_with_username


# Rename endpoint returns the new slug
def test_rename_returns_new_slug(client):
    user_id = create_user_with_username(client, "rn@example.com", "rnuser", "oldname")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post("/@rnuser/oldname/rename", data={"new_slug": "newname"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["slug"] == "newname"


# Old slug 301-redirects to the new slug
def test_old_slug_redirects_after_rename(client):
    user_id = create_user_with_username(client, "rd@example.com", "rduser", "before")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/@rduser/before/rename", data={"new_slug": "after"})
    r = client.get("/@rduser/before")
    assert r.status_code == 301
    assert "/after" in r.headers["Location"]


# Multiple renames: all old slugs redirect
def test_multiple_renames_all_redirect(client):
    user_id = create_user_with_username(client, "mr@example.com", "mruser", "first")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/@mruser/first/rename", data={"new_slug": "second"})
    client.post("/@mruser/second/rename", data={"new_slug": "third"})
    r1 = client.get("/@mruser/first")
    assert r1.status_code == 301
    r2 = client.get("/@mruser/second")
    assert r2.status_code == 301
    assert "/third" in r2.headers["Location"]


# Slugs with dots are rejected
def test_rename_rejects_dots(client):
    user_id = create_user_with_username(client, "dt@example.com", "dtuser", "dottest")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post("/@dtuser/dottest/rename", data={"new_slug": "bad.slug"})
    assert r.status_code == 400
    assert r.get_json()["error"]


# Reserved slugs are rejected on main domain
def test_rename_rejects_reserved(client):
    user_id = create_user_with_username(client, "rs@example.com", "rsuser", "rsvtest")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post("/rsvtest/rename", data={"new_slug": "new"})
    assert r.status_code == 400
    assert "reserved" in r.get_json()["error"].lower()


# Already-taken slugs are rejected
def test_rename_rejects_taken(client):
    user_id = create_user_with_username(client, "tk@example.com", "tkuser", "taken1")
    save_page("taken2", "# Other\n\nPage", "listed", user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post("/@tkuser/taken1/rename", data={"new_slug": "taken2"})
    assert r.status_code == 400
    assert "taken" in r.get_json()["error"].lower()


# Unauthenticated users cannot rename owned pages
def test_rename_requires_auth(client):
    create_user_with_username(client, "au@example.com", "auuser", "authtest")
    r = client.post("/@auuser/authtest/rename", data={"new_slug": "hacked"})
    assert r.status_code == 403


# Empty slug is rejected
def test_rename_rejects_empty(client):
    user_id = create_user_with_username(client, "em@example.com", "emuser", "emtest")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post("/@emuser/emtest/rename", data={"new_slug": ""})
    assert r.status_code == 400


# Same slug is a no-op success
def test_rename_same_slug_noop(client):
    user_id = create_user_with_username(client, "no@example.com", "nouser", "nochange")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post("/@nouser/nochange/rename", data={"new_slug": "nochange"})
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


# rename_page stores old slug in slug_redirects
def test_rename_page_stores_redirect(client):
    user_id = create_user_with_username(client, "sr@example.com", "sruser", "srold")
    page_meta = get_page_meta("srold", user_id)
    rename_page(page_meta["id"], "srnew")
    assert find_slug_redirect("srold", user_id) == "srnew"


# Rename then publish keeps the new slug
def test_rename_then_publish_keeps_new_slug(client):
    user_id = create_user_with_username(client, "rp@example.com", "rpuser", "oldslug")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    # Rename via the chip
    r = client.post("/@rpuser/oldslug/rename", data={"new_slug": "newslug"})
    assert r.get_json()["ok"] is True
    # Publish via the edit form (what the browser does after rename)
    r = client.post(
        "/@rpuser/newslug/edit",
        data={"title": "Updated Title", "content": "Updated body"},
    )
    assert r.status_code == 302
    assert "/newslug" in r.headers["Location"]
    # The page should exist at the new slug
    page = get_page_meta("newslug", user_id)
    assert page is not None


# Rename to a 6-char slug should not be overridden by auto-rename
def test_rename_to_short_slug_not_overridden_by_auto_rename(client):
    user_id = create_user_with_username(client, "ar@example.com", "aruser", "artest")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/@aruser/artest/rename", data={"new_slug": "mypost"})
    r = client.post(
        "/@aruser/mypost/edit",
        data={"title": "A Long Title", "content": "Body"},
    )
    assert r.status_code == 302
    # Should stay at "mypost", NOT auto-rename to "a-long-title"
    assert "/mypost" in r.headers["Location"]
    assert "a-long-title" not in r.headers["Location"]


# Root-domain access to old slug of owned page redirects to profile
def test_root_domain_old_slug_redirects_owned_page(client):
    user_id = create_user_with_username(client, "rd2@example.com", "rd2user", "first")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/@rd2user/first/rename", data={"new_slug": "second"})
    client.post("/@rd2user/second/rename", data={"new_slug": "third"})
    # Access intermediate slug on root domain
    r = client.get("/second")
    assert r.status_code == 301
    assert "/@rd2user/third" in r.headers["Location"]


# Slug reuse: redirect resolves to the most recent page
def test_slug_reuse_redirect_resolves_to_latest(client):
    user_id = create_user_with_username(client, "su@example.com", "suuser", "alpha")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    # Page A: alpha -> beta -> gamma
    client.post("/@suuser/alpha/rename", data={"new_slug": "beta"})
    client.post("/@suuser/beta/rename", data={"new_slug": "gamma"})
    # Page B takes "beta" and renames to "delta"
    save_page("beta", "# Page B\n\nContent", "listed", user_id)
    page_b = get_page_meta("beta", user_id)
    rename_page(page_b["id"], "delta")
    # Lookup for "beta" should resolve to "delta" (page B), not "gamma" (page A)
    assert find_slug_redirect("beta", user_id) == "delta"
    r = client.get("/@suuser/beta")
    assert r.status_code == 301
    assert "/delta" in r.headers["Location"]


# find_slug_redirect_with_owner returns owner info for root-domain lookups
def test_find_slug_redirect_with_owner(client):
    user_id = create_user_with_username(client, "wo@example.com", "wouser", "owned")
    page_meta = get_page_meta("owned", user_id)
    rename_page(page_meta["id"], "renamed")
    redir = find_slug_redirect_with_owner("owned")
    assert redir is not None
    assert redir["slug"] == "renamed"
    assert redir["user_id"] == user_id


# Ambiguous old slug shared by two owners returns 404 on root domain
def test_ambiguous_old_slug_returns_404(client):
    # User A: astart -> shared -> a-final
    user_a = create_user_with_username(client, "aa@example.com", "auser", "astart")
    with client.session_transaction() as sess:
        sess["user_id"] = user_a
    client.post("/@auser/astart/rename", data={"new_slug": "shared"})
    client.post("/@auser/shared/rename", data={"new_slug": "a-final"})
    # User B: bstart -> shared -> b-final
    user_b = create_user_with_username(client, "bb@example.com", "buser", "bstart")
    with client.session_transaction() as sess:
        sess["user_id"] = user_b
    client.post("/@buser/bstart/rename", data={"new_slug": "shared"})
    client.post("/@buser/shared/rename", data={"new_slug": "b-final"})
    # Root-domain /shared is ambiguous — two different owners had it
    r = client.get("/shared")
    assert r.status_code == 404


# Special slug AGENTS.md is allowed
def test_rename_to_agents_md(client):
    user_id = create_user_with_username(client, "ag@example.com", "aguser", "agtest")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    r = client.post("/@aguser/agtest/rename", data={"new_slug": "AGENTS.md"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["slug"] == "AGENTS.md"
    page = get_page_meta("AGENTS.md", user_id)
    assert page is not None


# AGENTS.md is viewable at its canonical URL (not treated as .md representation)
def test_agents_md_viewable_at_canonical_url(client):
    user_id = create_user_with_username(client, "av@example.com", "avuser", "avtest")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    client.post("/@avuser/avtest/rename", data={"new_slug": "AGENTS.md"})
    r = client.get("/@avuser/AGENTS.md")
    assert r.status_code == 200
    assert b"Test" in r.data


# Normal .md representation still works for ordinary slugs
def test_normal_md_representation_still_works(client):
    user_id = create_user_with_username(
        client, "md@example.com", "mduser", "mypage"
    )
    r = client.get("/@mduser/mypage.md")
    assert r.status_code == 200
    assert r.content_type.startswith("text/markdown")


# Normal .txt representation still works for ordinary slugs
def test_normal_txt_representation_still_works(client):
    user_id = create_user_with_username(
        client, "tx@example.com", "txuser", "txpage"
    )
    r = client.get("/@txuser/txpage.txt")
    assert r.status_code == 200
    assert r.content_type.startswith("text/plain")
