from db import save_page
from utils import describe_change

# -- Revisions --


# Multiple edits create numbered revision entries in history
def test_edit_creates_revisions(client):
    client.post("/revtest/edit", data={"title": "R1", "content": "A"})
    client.post("/revtest/edit", data={"title": "R1", "content": "B"})
    client.post("/revtest/edit", data={"title": "R1", "content": "C"})
    r = client.get("/revtest/history")
    assert r.status_code == 200
    assert b"history/1" in r.data
    assert b"history/2" in r.data


# History page shows "Created" label for the first revision
def test_history_shows_created(client):
    client.post("/hist1/edit", data={"title": "T", "content": "X"})
    client.post("/hist1/edit", data={"title": "T", "content": "X Y"})
    r = client.get("/hist1/history")
    assert b"Created" in r.data


# History of a nonexistent page returns 404
def test_history_nonexistent_page(client):
    r = client.get("/nope/history")
    assert r.status_code == 404


# Revisions are listed newest-first
def test_history_newest_first(client):
    client.post("/order/edit", data={"title": "T", "content": "A"})
    client.post("/order/edit", data={"title": "T", "content": "A B"})
    client.post("/order/edit", data={"title": "T", "content": "A B C"})
    r = client.get("/order/history")
    body = r.data.decode()
    pos_2 = body.index("history/2")
    pos_1 = body.index("history/1")
    assert pos_2 < pos_1


# -- View specific revision --


# A specific revision renders its content with a revision number label
def test_view_revision(client):
    client.post("/vrev/edit", data={"title": "V1", "content": "First"})
    client.post("/vrev/edit", data={"title": "V2", "content": "Second"})
    r = client.get("/vrev/history/1")
    assert r.status_code == 200
    assert b"First" in r.data
    assert b"revision #1" in r.data
    assert b"View current version" in r.data


# Requesting a nonexistent revision returns 404
def test_view_revision_nonexistent(client):
    client.post("/vrev2/edit", data={"title": "T", "content": "X"})
    r = client.get("/vrev2/history/99")
    assert r.status_code == 404


# -- Change descriptions --


# Detects a title change between revisions
def test_describe_title_change():
    assert "Changed title" in describe_change("# Old\n\nBody", "# New\n\nBody")


# Detects added content
def test_describe_added_content():
    assert "Added" in describe_change("# T\n\nA", "# T\n\nA\nB\nC")


# Detects removed content
def test_describe_removed_content():
    assert "Removed" in describe_change("# T\n\nA\nB\nC", "# T\n\nA")


# Detects modified content
def test_describe_changed_content():
    assert "Changed" in describe_change("# T\n\nHello", "# T\n\nWorld")


# Returns generic "Edited page" when nothing changed
def test_describe_same_content():
    assert describe_change("# T\n\nA", "# T\n\nA") == "Edited page"


# -- Provenance display --


# AI-assisted revision shows badge in history
def test_history_shows_ai_badge(client):
    save_page("prov1", "# T\n\nFirst", False, source="mcp", ai_assisted=True)
    save_page("prov1", "# T\n\nSecond", False, source="web", ai_assisted=False)
    r = client.get("/prov1/history")
    assert b"AI-assisted" in r.data
    assert b"via mcp" in r.data


# Web-only revision shows no provenance badge
def test_history_no_badge_for_web(client):
    save_page("prov2", "# T\n\nFirst", False)
    r = client.get("/prov2/history")
    assert b"AI-assisted" not in r.data
    assert b"via web" not in r.data


# Individual revision view shows provenance in banner
def test_revision_view_shows_provenance(client):
    save_page("prov3", "# T\n\nAI content", False, source="mcp", ai_assisted=True)
    r = client.get("/prov3/history/1")
    assert b"AI-assisted" in r.data
    assert b"via mcp" in r.data


# Published page footer shows AI attribution
def test_page_footer_ai_attribution(client):
    save_page("prov4", "# T\n\nBody", False, source="mcp", ai_assisted=True)
    r = client.get("/prov4")
    assert b"published with AI via MCP" in r.data


# Published page footer shows source without AI
def test_page_footer_source_only(client):
    save_page("prov5", "# T\n\nBody", False, source="api", ai_assisted=False)
    r = client.get("/prov5")
    assert b"published via API" in r.data


# Web pages show no provenance in footer
def test_page_footer_no_provenance_for_web(client):
    save_page("prov6", "# T\n\nBody", False)
    r = client.get("/prov6")
    assert b"published via" not in r.data
    assert b"published with AI" not in r.data
