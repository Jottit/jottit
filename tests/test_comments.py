from db import (
    claim_page,
    count_comments_by_ip,
    create_comment,
    find_or_create_user,
    get_comment_count,
    get_comments,
    get_page_meta,
    set_user_username,
    update_user_settings,
)


def _create_page(client, slug="testpage", content="# Test\n\nHello"):
    client.post(f"/{slug}/edit", data={"title": "T", "content": content})
    return get_page_meta(slug)


def _create_claimed_page(client, slug="testpage"):
    page_meta = _create_page(client, slug)
    user_id = find_or_create_user("owner@example.com")
    set_user_username(user_id, "owner")
    claim_page(page_meta["id"], user_id)
    return get_page_meta(slug, user_id), user_id


def _commenter(name="Commenter", email="commenter@test.com"):
    uid = find_or_create_user(email)
    update_user_settings(uid, name, "")
    return uid


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


# -- Page view with comments --


def test_page_shows_comment_form(client):
    _create_page(client)
    r = client.get("/testpage")
    assert r.status_code == 200
    assert b"What are your thoughts?" in r.data


def test_page_shows_comments_section(client):
    page_meta = _create_page(client)
    uid = _commenter("Alice")
    create_comment(page_meta["id"], uid, "Great post!", "abc123")
    r = client.get("/testpage")
    assert b"Great post!" in r.data
    assert b"Alice" in r.data


# -- Comment submission --


def test_submit_comment_requires_body(client):
    _create_page(client)
    r = client.post("/testpage/comment", data={"body": ""})
    assert b"cannot be empty" in r.data


def test_submit_comment_enforces_max_length(client):
    _create_page(client)
    body = "x" * 2001
    r = client.post("/testpage/comment", data={"body": body})
    assert b"2000 characters" in r.data


def test_submit_comment_shows_email_step(client):
    _create_page(client)
    r = client.post("/testpage/comment", data={"body": "Nice!"})
    assert r.status_code == 200
    assert b"Almost there" in r.data
    assert b"Email" in r.data


def test_verify_email_step_sends_code(client):
    _create_page(client)
    r = client.post(
        "/testpage/comment/verify",
        data={
            "body": "Nice!",
            "email": "commenter@test.com",
            "author_name": "Bob",
            "parent_id": "",
            "step": "email",
        },
    )
    assert r.status_code == 200
    assert b"Check your email" in r.data


def test_verify_email_step_requires_valid_email(client):
    _create_page(client)
    r = client.post(
        "/testpage/comment/verify",
        data={
            "body": "Nice!",
            "email": "invalid",
            "author_name": "",
            "parent_id": "",
            "step": "email",
        },
    )
    assert r.status_code == 200
    assert b"valid email" in r.data


def test_submit_comment_rejects_disabled_comments(client):
    from db import get_db

    page_meta = _create_page(client)
    with get_db() as conn:
        conn.execute(
            "UPDATE pages SET comments_enabled = FALSE WHERE id = %s",
            (page_meta["id"],),
        )
        conn.commit()
    r = client.post(
        "/testpage/comment",
        data={"body": "Hello"},
    )
    assert r.status_code == 403


def test_submit_comment_404_nonexistent_page(client):
    r = client.post("/nosuchpage/comment", data={"body": "Hi"})
    assert r.status_code == 404


# -- Verification flow --


def test_verify_and_save_comment(client):
    from db import create_verification_code

    page_meta = _create_page(client)
    code = create_verification_code("commenter@test.com", "comment")
    r = client.post(
        "/testpage/comment/verify",
        data={
            "step": "code",
            "code": code,
            "body": "Verified comment!",
            "email": "commenter@test.com",
            "author_name": "Carol",
            "parent_id": "",
        },
    )
    assert r.status_code == 302
    assert "/testpage#comment-" in r.headers["Location"]

    comments = get_comments(page_meta["id"])
    assert len(comments) == 1
    assert comments[0]["body"] == "Verified comment!"

    # Verify user is signed in after commenting
    with client.session_transaction() as sess:
        assert sess.get("user_id") is not None


def test_verify_invalid_code(client):
    _create_page(client)
    r = client.post(
        "/testpage/comment/verify",
        data={
            "step": "code",
            "code": "000000",
            "body": "Test",
            "email": "a@test.com",
            "author_name": "",
            "parent_id": "",
        },
    )
    assert r.status_code == 200
    assert b"Invalid or expired" in r.data


# -- Threading --


def test_reply_to_comment(client):
    from db import create_verification_code

    page_meta = _create_page(client)
    uid = _commenter("Alice", "alice@test.com")
    create_comment(page_meta["id"], uid, "Original", "abc")
    comments = get_comments(page_meta["id"])
    parent_id = comments[0]["id"]

    code = create_verification_code("bob@test.com", "comment")
    r = client.post(
        "/testpage/comment/verify",
        data={
            "step": "code",
            "code": code,
            "body": "Reply!",
            "email": "bob@test.com",
            "author_name": "Bob",
            "parent_id": str(parent_id),
        },
    )
    assert r.status_code == 302

    all_comments = get_comments(page_meta["id"])
    assert len(all_comments) == 2
    reply = [c for c in all_comments if c["parent_id"] is not None][0]
    assert reply["body"] == "Reply!"
    assert reply["parent_id"] == parent_id


def test_reply_to_reply_rejected(client):
    page_meta = _create_page(client)
    uid = _commenter()
    create_comment(page_meta["id"], uid, "Top", "abc")
    comments = get_comments(page_meta["id"])
    parent_id = comments[0]["id"]

    result = create_comment(page_meta["id"], uid, "Reply", "abc", parent_id)
    assert result is not None

    result2 = create_comment(page_meta["id"], uid, "Deep reply", "abc", result["id"])
    assert result2 is None


def test_reply_to_form_shown(client):
    page_meta = _create_page(client)
    uid = _commenter()
    create_comment(page_meta["id"], uid, "Top", "abc")
    comments = get_comments(page_meta["id"])
    comment_id = comments[0]["id"]

    r = client.get(f"/testpage?reply_to={comment_id}")
    assert r.status_code == 200
    assert b"Write a reply" in r.data


# -- Author moderation --


def test_owner_can_pin_comment(client):
    page_meta, user_id = _create_claimed_page(client)
    uid = _commenter()
    create_comment(page_meta["id"], uid, "Pin me", "abc")
    comments = get_comments(page_meta["id"])
    comment_id = comments[0]["id"]

    _login(client, user_id)
    r = client.post(f"/@owner/testpage/comment/{comment_id}/pin")
    assert r.status_code == 302

    comments = get_comments(page_meta["id"])
    assert comments[0]["is_pinned"] is True


def test_owner_can_hide_comment(client):
    page_meta, user_id = _create_claimed_page(client)
    uid = _commenter()
    create_comment(page_meta["id"], uid, "Hide me", "abc")
    comments = get_comments(page_meta["id"])
    comment_id = comments[0]["id"]

    _login(client, user_id)
    r = client.post(f"/@owner/testpage/comment/{comment_id}/hide")
    assert r.status_code == 302

    visible_comments = get_comments(page_meta["id"], include_hidden=False)
    assert len(visible_comments) == 0

    all_comments = get_comments(page_meta["id"], include_hidden=True)
    assert len(all_comments) == 1
    assert all_comments[0]["is_hidden"] is True


def test_non_owner_cannot_pin(client):
    page_meta, user_id = _create_claimed_page(client)
    uid = _commenter()
    create_comment(page_meta["id"], uid, "Test", "abc")
    comments = get_comments(page_meta["id"])
    comment_id = comments[0]["id"]

    r = client.post(f"/@owner/testpage/comment/{comment_id}/pin")
    assert r.status_code == 403


def test_non_owner_cannot_hide(client):
    page_meta, user_id = _create_claimed_page(client)
    uid = _commenter()
    create_comment(page_meta["id"], uid, "Test", "abc")
    comments = get_comments(page_meta["id"])
    comment_id = comments[0]["id"]

    r = client.post(f"/@owner/testpage/comment/{comment_id}/hide")
    assert r.status_code == 403


def test_hidden_comments_not_shown_to_visitors(client):
    page_meta, user_id = _create_claimed_page(client)
    uid = _commenter()
    create_comment(page_meta["id"], uid, "Visible", "abc")
    uid2 = _commenter("B", "b@test.com")
    create_comment(page_meta["id"], uid2, "Hidden comment text", "abc")
    comments = get_comments(page_meta["id"])
    hidden_id = comments[1]["id"]

    from db import hide_comment

    hide_comment(hidden_id, page_meta["id"])

    r = client.get("/@owner/testpage")
    assert b"Visible" in r.data
    assert b"Hidden comment text" not in r.data


def test_hidden_comments_shown_to_owner(client):
    page_meta, user_id = _create_claimed_page(client)
    uid = _commenter()
    create_comment(page_meta["id"], uid, "Secret hidden text", "abc")
    comments = get_comments(page_meta["id"])

    from db import hide_comment

    hide_comment(comments[0]["id"], page_meta["id"])

    _login(client, user_id)
    r = client.get("/@owner/testpage")
    assert b"Secret hidden text" in r.data


# -- Rate limiting (DB level) --


def test_rate_limit_count(client):
    page_meta = _create_page(client)
    uid = _commenter()
    ip = "ratelimit_hash"
    for i in range(5):
        create_comment(page_meta["id"], uid, f"Comment {i}", ip)
    assert count_comments_by_ip(ip) == 5


# -- Comment count --


def test_comment_count(client):
    page_meta = _create_page(client)
    uid = _commenter()
    assert get_comment_count(page_meta["id"]) == 0
    create_comment(page_meta["id"], uid, "One", "abc")
    create_comment(page_meta["id"], uid, "Two", "abc")
    assert get_comment_count(page_meta["id"]) == 2


# -- URL auto-linking --


def test_comment_body_autolinks_urls(client):
    page_meta = _create_page(client)
    uid = _commenter()
    create_comment(page_meta["id"], uid, "Check https://example.com for details", "abc")
    r = client.get("/testpage")
    assert b'href="https://example.com"' in r.data
    assert b'target="_blank"' in r.data
