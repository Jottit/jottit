import importlib.util
import os

import db
from db import (
    find_or_create_user,
    save_page,
    set_user_username,
    update_user_settings,
)

# The exporter lives in scripts/, which isn't a package; load it by path.
_SPEC = importlib.util.spec_from_file_location(
    "export_to_jottit_pub",
    os.path.join(os.path.dirname(__file__), "..", "scripts", "export_to_jottit_pub.py"),
)
exporter = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(exporter)


def _build():
    with db.get_db() as conn:
        return exporter.build_bundle(conn)


def _profile(bundle, username):
    return next(p for p in bundle["profiles"] if p["username"] == username)


def test_profile_with_pages_and_bio_exported():
    alice = find_or_create_user("alice@example.com")
    set_user_username(alice, "alice")
    update_user_settings(alice, "Alice Smith", "alice", bio="# Alice\n\nHi.")
    save_page("hello", "# Hello\n\nContent.", "listed", user_id=alice)

    bundle = _build()

    p = _profile(bundle, "alice")
    assert p["email"] == "alice@example.com"
    assert p["name"] == "Alice Smith"
    assert p["bio"] == "# Alice\n\nHi."
    assert p["created_at"] is not None
    assert [pg["slug"] for pg in p["pages"]] == ["hello"]


def test_full_revision_history_exported_in_order():
    user = find_or_create_user("multi@example.com")
    set_user_username(user, "multi")
    save_page("post", "# Post\n\nv1.", "listed", user_id=user)
    save_page("post", "# Post\n\nv2.", "pinned", user_id=user)

    bundle = _build()

    revs = _profile(bundle, "multi")["pages"][0]["revisions"]
    assert [r["revision"] for r in revs] == [1, 2]
    assert revs[0]["content"] == "# Post\n\nv1."
    assert revs[1]["content"] == "# Post\n\nv2."


def test_all_visibilities_included():
    user = find_or_create_user("vis@example.com")
    set_user_username(user, "vis")
    save_page("listed-page", "# L", "listed", user_id=user)
    save_page("unlisted-page", "# U", "unlisted", user_id=user)

    slugs = {pg["slug"] for pg in _profile(_build(), "vis")["pages"]}
    assert slugs == {"listed-page", "unlisted-page"}


def test_unclaimed_pages_exported_separately():
    save_page("orphan", "# Orphan", "unlisted", user_id=None)

    bundle = _build()

    assert [u["slug"] for u in bundle["unclaimed_pages"]] == ["orphan"]
    assert bundle["unclaimed_pages"][0]["revisions"][0]["content"] == "# Orphan"


def test_bundle_shape():
    bundle = _build()
    assert bundle["source"] == "jottit.org"
    assert "exported_at" in bundle
    assert isinstance(bundle["profiles"], list)
    assert isinstance(bundle["unclaimed_pages"], list)
