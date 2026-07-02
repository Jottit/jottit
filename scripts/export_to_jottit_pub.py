"""Export all jottit.org content to a JSON bundle for import into jottit.pub.

jottit.pub's top-level object is a *site*; jottit.org has no sites, only user
profiles that own pages. This dumps each profile with its pages and full
revision history, plus unclaimed pages (user_id IS NULL) separately, so the
importer can turn each profile into a site and each unclaimed page into its own
standalone site.

Usage:
    DATABASE_URL="dbname=jottit_dev" python scripts/export_to_jottit_pub.py [out.json]

Run from the repo root (imports the app's `db` module).
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import db  # noqa: E402


def _iso(value):
    return value.isoformat() if value is not None else None


def _revisions_for_page(conn, page_id):
    rows = conn.execute(
        "SELECT revision, content, created_at FROM revisions "
        "WHERE page_id = %s ORDER BY revision ASC",
        (page_id,),
    ).fetchall()
    return [
        {
            "revision": r["revision"],
            "content": r["content"],
            "created_at": _iso(r["created_at"]),
        }
        for r in rows
    ]


def _pages_for_user(conn, user_id):
    rows = conn.execute(
        "SELECT id, slug, created_at FROM pages "
        "WHERE user_id = %s ORDER BY created_at ASC, id ASC",
        (user_id,),
    ).fetchall()
    pages = []
    for row in rows:
        pages.append(
            {
                "slug": row["slug"],
                "created_at": _iso(row["created_at"]),
                "revisions": _revisions_for_page(conn, row["id"]),
            }
        )
    return pages


def build_bundle(conn):
    from datetime import datetime, timezone

    profiles = []
    users = conn.execute(
        "SELECT id, email, username, name, bio, created_at FROM users ORDER BY id ASC"
    ).fetchall()
    for user in users:
        profiles.append(
            {
                "username": user["username"],
                "email": user["email"],
                "name": user["name"],
                "bio": user["bio"],
                "created_at": _iso(user["created_at"]),
                "pages": _pages_for_user(conn, user["id"]),
            }
        )

    unclaimed = []
    rows = conn.execute(
        "SELECT id, slug, created_at FROM pages "
        "WHERE user_id IS NULL ORDER BY created_at ASC, id ASC"
    ).fetchall()
    for row in rows:
        unclaimed.append(
            {
                "slug": row["slug"],
                "created_at": _iso(row["created_at"]),
                "revisions": _revisions_for_page(conn, row["id"]),
            }
        )

    return {
        "source": "jottit.org",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "profiles": profiles,
        "unclaimed_pages": unclaimed,
    }


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "jottit_pub_export.json"

    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        db.DATABASE = database_url
        db.reset_pool()

    with db.get_db() as conn:
        bundle = build_bundle(conn)

    with open(out_path, "w") as f:
        json.dump(bundle, f, indent=2)

    page_count = sum(len(p["pages"]) for p in bundle["profiles"])
    print(
        f"Exported {len(bundle['profiles'])} profiles, {page_count} owned pages, "
        f"{len(bundle['unclaimed_pages'])} unclaimed pages -> {out_path}"
    )


if __name__ == "__main__":
    main()
