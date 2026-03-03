import os
import secrets

import psycopg
from psycopg.rows import dict_row

DATABASE = os.environ.get("DATABASE_URL", "dbname=jottit_dev")


def get_db():
    conn = psycopg.connect(DATABASE, row_factory=dict_row, autocommit=False)
    return conn


def init_db():
    conn = get_db()
    try:
        with open("schema.sql") as f:
            conn.execute(f.read())
        conn.commit()
    finally:
        conn.close()


def get_latest_revision(slug, page_slug=None):
    conn = get_db()
    try:
        if page_slug:
            row = conn.execute(
                """SELECT r.content, r.draft FROM revisions r
                   JOIN pages p ON r.page_id = p.id
                   JOIN sites s ON p.site_id = s.id
                   WHERE s.slug = %s AND p.slug = %s
                   ORDER BY r.revision DESC LIMIT 1""",
                (slug, page_slug),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT r.content, r.draft FROM revisions r
                   JOIN pages p ON r.page_id = p.id
                   JOIN sites s ON p.site_id = s.id
                   WHERE s.slug = %s
                   ORDER BY r.revision DESC LIMIT 1""",
                (slug,),
            ).fetchone()
        return row
    finally:
        conn.close()


def save_page(slug, content, draft, page_slug=None):
    conn = get_db()
    try:
        site = conn.execute("SELECT id FROM sites WHERE slug = %s", (slug,)).fetchone()

        if site:
            if page_slug:
                page = conn.execute(
                    "SELECT id FROM pages WHERE site_id = %s AND slug = %s",
                    (site["id"], page_slug),
                ).fetchone()
                if not page:
                    page = conn.execute(
                        "INSERT INTO pages (site_id, slug) VALUES (%s, %s) RETURNING id",
                        (site["id"], page_slug),
                    ).fetchone()
            else:
                page = conn.execute(
                    "SELECT id FROM pages WHERE site_id = %s", (site["id"],)
                ).fetchone()
            conn.execute(
                """INSERT INTO revisions (page_id, revision, content, draft)
                   VALUES (%s, (SELECT COALESCE(MAX(revision), 0) + 1 FROM revisions WHERE page_id = %s), %s, %s)""",
                (page["id"], page["id"], content, draft),
            )
            conn.execute(
                "UPDATE pages SET updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (page["id"],),
            )
        else:
            cursor = conn.execute(
                "INSERT INTO sites (slug) VALUES (%s) RETURNING id", (slug,)
            )
            site_id = cursor.fetchone()["id"]
            cursor = conn.execute(
                "INSERT INTO pages (site_id, slug) VALUES (%s, %s) RETURNING id",
                (site_id, page_slug or "-"),
            )
            page_id = cursor.fetchone()["id"]
            conn.execute(
                "INSERT INTO revisions (page_id, revision, content, draft) VALUES (%s, 1, %s, %s)",
                (page_id, content, draft),
            )

        conn.commit()
    finally:
        conn.close()


def get_page(slug, page_slug=None):
    conn = get_db()
    try:
        if page_slug:
            row = conn.execute(
                """SELECT r.content, r.draft, r.created_at, s.user_id
                   FROM revisions r
                   JOIN pages p ON r.page_id = p.id
                   JOIN sites s ON p.site_id = s.id
                   WHERE s.slug = %s AND p.slug = %s
                   ORDER BY r.revision DESC LIMIT 1""",
                (slug, page_slug),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT r.content, r.draft, r.created_at, s.user_id
                   FROM revisions r
                   JOIN pages p ON r.page_id = p.id
                   JOIN sites s ON p.site_id = s.id
                   WHERE s.slug = %s
                   ORDER BY r.revision DESC LIMIT 1""",
                (slug,),
            ).fetchone()
        return row
    finally:
        conn.close()


def get_revisions(slug):
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT r.revision, r.created_at, r.content FROM revisions r
               JOIN pages p ON r.page_id = p.id
               JOIN sites s ON p.site_id = s.id
               WHERE s.slug = %s
               ORDER BY r.revision ASC""",
            (slug,),
        ).fetchall()
        return rows
    finally:
        conn.close()


def get_revision(slug, revision):
    conn = get_db()
    try:
        row = conn.execute(
            """SELECT r.content, r.created_at, r.revision FROM revisions r
               JOIN pages p ON r.page_id = p.id
               JOIN sites s ON p.site_id = s.id
               WHERE s.slug = %s AND r.revision = %s""",
            (slug, revision),
        ).fetchone()
        return row
    finally:
        conn.close()


def get_site(slug):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, slug, user_id, visibility, title, subdomain, nav FROM sites WHERE slug = %s",
            (slug,),
        ).fetchone()
        return row
    finally:
        conn.close()


def get_site_by_subdomain(subdomain):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT id, slug, user_id, visibility, title, subdomain, nav FROM sites WHERE subdomain = %s",
            (subdomain,),
        ).fetchone()
        return row
    finally:
        conn.close()


def find_or_create_user(email):
    conn = get_db()
    try:
        row = conn.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
        if row:
            user_id = row["id"]
        else:
            row = conn.execute(
                "INSERT INTO users (email) VALUES (%s) RETURNING id", (email,)
            ).fetchone()
            user_id = row["id"]
        conn.commit()
        return user_id
    finally:
        conn.close()


def claim_site(slug, user_id):
    conn = get_db()
    try:
        result = conn.execute(
            "UPDATE sites SET user_id = %s WHERE slug = %s AND user_id IS NULL",
            (user_id, slug),
        )
        conn.commit()
        return result.rowcount > 0
    finally:
        conn.close()


def create_verification_code(email, purpose):
    code = f"{secrets.randbelow(1000000):06d}"
    conn = get_db()
    try:
        conn.execute(
            """INSERT INTO verification_codes (email, code, purpose, expires_at)
               VALUES (%s, %s, %s, NOW() + INTERVAL '10 minutes')
               ON CONFLICT (email, purpose)
               DO UPDATE SET code = EXCLUDED.code, expires_at = EXCLUDED.expires_at""",
            (email, code, purpose),
        )
        conn.commit()
        return code
    finally:
        conn.close()


def verify_code(email, code, purpose):
    conn = get_db()
    try:
        row = conn.execute(
            """DELETE FROM verification_codes
               WHERE email = %s AND code = %s AND purpose = %s AND expires_at > NOW()
               RETURNING id""",
            (email, code, purpose),
        ).fetchone()
        conn.commit()
        return row is not None
    finally:
        conn.close()


def get_sites_for_user(user_id, limit=None):
    conn = get_db()
    try:
        query = """SELECT s.slug, s.title, s.subdomain, s.visibility
                   FROM sites s
                   LEFT JOIN pages p ON s.id = p.site_id
                   LEFT JOIN revisions r ON p.id = r.page_id
                   WHERE s.user_id = %s
                   GROUP BY s.id, s.slug, s.title, s.subdomain, s.visibility
                   ORDER BY MAX(r.created_at) DESC NULLS LAST"""
        params = [user_id]
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        rows = conn.execute(query, params).fetchall()
        return rows
    finally:
        conn.close()


def count_sites_for_user(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM sites WHERE user_id = %s",
            (user_id,),
        ).fetchone()
        return row["count"]
    finally:
        conn.close()


def get_user_email(user_id):
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT email FROM users WHERE id = %s", (user_id,)
        ).fetchone()
        return row["email"] if row else None
    finally:
        conn.close()


def update_site_settings(site_id, title, subdomain, nav=None):
    conn = get_db()
    try:
        conn.execute(
            "UPDATE sites SET title = %s, subdomain = %s, nav = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (title or None, subdomain or None, nav or None, site_id),
        )
        conn.commit()
    finally:
        conn.close()


def get_pages_for_site(site_id):
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT p.id, p.slug, p.nav_order,
                      (SELECT r.content FROM revisions r WHERE r.page_id = p.id ORDER BY r.revision DESC LIMIT 1) AS content
               FROM pages p
               WHERE p.site_id = %s
               ORDER BY p.nav_order ASC NULLS LAST, p.created_at ASC""",
            (site_id,),
        ).fetchall()
        return rows
    finally:
        conn.close()


def create_page(site_id, slug):
    conn = get_db()
    try:
        row = conn.execute(
            "INSERT INTO pages (site_id, slug) VALUES (%s, %s) RETURNING id",
            (site_id, slug),
        ).fetchone()
        conn.commit()
        return row["id"]
    finally:
        conn.close()


def get_export_pages(slug):
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM (
                   SELECT DISTINCT ON (p.id)
                       p.slug AS page_slug,
                       r.content,
                       r.created_at
                   FROM pages p
                   JOIN revisions r ON r.page_id = p.id
                   JOIN sites s ON p.site_id = s.id
                   WHERE s.slug = %s AND r.draft = FALSE
                   ORDER BY p.id, r.revision DESC
               ) sub
               ORDER BY page_slug ASC""",
            (slug,),
        ).fetchall()
        return rows
    finally:
        conn.close()


def get_feed_entries(slug):
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT * FROM (
                   SELECT DISTINCT ON (p.id)
                       p.slug AS page_slug,
                       r.content,
                       r.created_at
                   FROM pages p
                   JOIN revisions r ON r.page_id = p.id
                   JOIN sites s ON p.site_id = s.id
                   WHERE s.slug = %s AND r.draft = FALSE
                   ORDER BY p.id, r.revision DESC
               ) sub
               ORDER BY created_at DESC
               LIMIT 20""",
            (slug,),
        ).fetchall()
        return rows
    finally:
        conn.close()


def check_subdomain_available(subdomain, exclude_site_id=None):
    conn = get_db()
    try:
        if exclude_site_id:
            row = conn.execute(
                "SELECT id FROM sites WHERE subdomain = %s AND id != %s",
                (subdomain, exclude_site_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM sites WHERE subdomain = %s", (subdomain,)
            ).fetchone()
        return row is None
    finally:
        conn.close()
