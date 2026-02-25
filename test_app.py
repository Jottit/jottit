from routes import _describe_change


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
    client.post("/draftpage/edit", data={"title": "Draft", "content": "WIP", "draft": "on"})
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
