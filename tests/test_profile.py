import io
from unittest.mock import patch

from conftest import create_user_with_username
from db import (
    find_or_create_user,
    get_user,
    set_user_username,
    update_user_avatar,
    update_user_settings,
)
from utils import render_bio

# -- Avatar --


# Uploading an avatar saves the image URL to the user record
@patch("routes.admin.upload_image", return_value="/uploads/1/avatar.jpg")
@patch("routes.admin.crop_square")
def test_avatar_upload(mock_crop, mock_upload, client):
    mock_crop.return_value = io.BytesIO(b"cropped")
    user_id = find_or_create_user("avatar@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    data = {
        "avatar": (io.BytesIO(b"fake-image-data"), "photo.jpg", "image/jpeg"),
    }
    r = client.post("/settings/avatar", data=data, content_type="multipart/form-data")
    assert r.status_code == 302
    mock_upload.assert_called_once()
    user = get_user(user_id)
    assert user["avatar"] == "/uploads/1/avatar.jpg"


# Non-image file types are rejected for avatar upload
def test_avatar_upload_rejects_invalid_type(client):
    user_id = find_or_create_user("avatar2@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    data = {
        "avatar": (io.BytesIO(b"not-an-image"), "file.txt", "text/plain"),
    }
    r = client.post("/settings/avatar", data=data, content_type="multipart/form-data")
    assert r.status_code == 200
    assert b"not allowed" in r.data
    assert b"Profile" in r.data


# Removing an avatar deletes the image and clears the user record
@patch("routes.admin.delete_image")
def test_avatar_removal(mock_delete, client):
    user_id = find_or_create_user("avatar3@example.com")
    update_user_avatar(user_id, "/uploads/1/avatar.jpg")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post("/settings/avatar/delete")
    assert r.status_code == 302
    mock_delete.assert_called_once_with("1/avatar.jpg")
    user = get_user(user_id)
    assert user["avatar"] is None


# -- Bio --


# Profile settings includes a bio field
def test_settings_profile_shows_bio_field(client):
    user_id = find_or_create_user("bio@example.com")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.get("/settings/profile")
    assert r.status_code == 200
    assert b"Bio" in r.data


# Saving profile persists the bio
def test_settings_profile_saves_bio(client):
    user_id = find_or_create_user("bio2@example.com")
    set_user_username(user_id, "biouser")
    with client.session_transaction() as sess:
        sess["user_id"] = user_id

    r = client.post(
        "/settings/profile", data={"name": "Bio User", "bio": "Hello world"}
    )
    assert r.status_code == 302

    user = get_user(user_id)
    assert user["bio"] == "Hello world"


# -- Bio rendering --


# Plain text bio renders as-is
def test_render_bio_plain_text():
    assert render_bio("Just a writer") == "Just a writer"


# Bio wikilinks render as plain text (wikilinks not supported)
def test_render_bio_wikilink_plain():
    result = render_bio("See [[About]]")
    assert "[[About]]" in result
    assert "<a" not in result


# Bio markdown links render as HTML links
def test_render_bio_markdown_link():
    result = render_bio("Check [About](/about)")
    assert '<a href="/about">About</a>' in result


# Bio external links render correctly
def test_render_bio_external_link():
    result = render_bio("[Google](https://google.com)")
    assert '<a href="https://google.com">Google</a>' in result


# Bio strips dangerous HTML tags (XSS protection)
def test_render_bio_strips_html():
    result = render_bio("<script>alert('xss')</script>")
    assert "<script>" not in result


# Bio strips all HTML tags except links
def test_render_bio_strips_other_tags():
    result = render_bio("<b>bold</b> and <em>italic</em>")
    assert "<b>" not in result
    assert "<em>" not in result
    assert "bold" in result


# -- Profile display --


# Profile homepage without avatar renders gracefully
def test_profile_home_no_avatar_graceful(client):
    user_id = create_user_with_username(client, "noav@example.com", "noavuser", "na1")
    update_user_settings(user_id, "No Avatar", "noavuser")

    r = client.get("/@noavuser")
    assert r.status_code == 200
    assert b"u-photo" not in r.data
    assert b"No Avatar" in r.data


# Profile pages show a profile header with avatar and bio
def test_profile_page_shows_profile_header(client):
    user_id = create_user_with_username(
        client, "profpage@example.com", "profpage", "pp1"
    )
    update_user_settings(user_id, "Prof Page", "profpage", "Writer")
    update_user_avatar(user_id, "/uploads/test/avatar.jpg")

    r = client.get("/@profpage/pp1")
    assert r.status_code == 200
    assert b"site-header" in r.data
    assert b"Prof Page" in r.data


# Visitor sees profile header with identity
def test_profile_header_visible_to_visitor(client):
    create_user_with_username(client, "side2@example.com", "sideuser2", "sp2")
    r = client.get("/@sideuser2")
    assert r.status_code == 200
    assert b"profile-header" in r.data
