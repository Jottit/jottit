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
