import os
import secrets
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

DATABASE = os.environ.get("DATABASE_URL", "dbname=jottit_dev")


@contextmanager
def get_db():
    conn = psycopg.connect(DATABASE, row_factory=dict_row, autocommit=False)
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        with open("schema.sql") as f:
            conn.execute(f.read())
        conn.commit()


def save_page(slug, content, draft, page_slug=None):
    with get_db() as conn:
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


def get_page(slug, page_slug=None):
    with get_db() as conn:
        if page_slug:
            return conn.execute(
                """SELECT r.content, r.draft, r.created_at, s.user_id
                   FROM revisions r
                   JOIN pages p ON r.page_id = p.id
                   JOIN sites s ON p.site_id = s.id
                   WHERE s.slug = %s AND p.slug = %s
                   ORDER BY r.revision DESC LIMIT 1""",
                (slug, page_slug),
            ).fetchone()
        return conn.execute(
            """SELECT r.content, r.draft, r.created_at, s.user_id
               FROM revisions r
               JOIN pages p ON r.page_id = p.id
               JOIN sites s ON p.site_id = s.id
               WHERE s.slug = %s
               ORDER BY r.revision DESC LIMIT 1""",
            (slug,),
        ).fetchone()


def get_revisions(slug):
    with get_db() as conn:
        return conn.execute(
            """SELECT r.revision, r.created_at, r.content FROM revisions r
               JOIN pages p ON r.page_id = p.id
               JOIN sites s ON p.site_id = s.id
               WHERE s.slug = %s
               ORDER BY r.revision ASC""",
            (slug,),
        ).fetchall()


def get_revision(slug, revision):
    with get_db() as conn:
        return conn.execute(
            """SELECT r.content, r.created_at, r.revision FROM revisions r
               JOIN pages p ON r.page_id = p.id
               JOIN sites s ON p.site_id = s.id
               WHERE s.slug = %s AND r.revision = %s""",
            (slug, revision),
        ).fetchone()


def get_site(slug):
    with get_db() as conn:
        return conn.execute(
            "SELECT id, slug, user_id, visibility, title, subdomain, nav FROM sites WHERE slug = %s",
            (slug,),
        ).fetchone()


def get_site_by_subdomain(subdomain):
    with get_db() as conn:
        return conn.execute(
            "SELECT id, slug, user_id, visibility, title, subdomain, nav FROM sites WHERE subdomain = %s",
            (subdomain,),
        ).fetchone()


def find_or_create_user(email):
    with get_db() as conn:
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


def claim_site(slug, user_id):
    with get_db() as conn:
        result = conn.execute(
            "UPDATE sites SET user_id = %s WHERE slug = %s AND user_id IS NULL",
            (user_id, slug),
        )
        conn.commit()
        return result.rowcount > 0


def create_verification_code(email, purpose):
    code = f"{secrets.randbelow(1000000):06d}"
    with get_db() as conn:
        conn.execute(
            """INSERT INTO verification_codes (email, code, purpose, expires_at)
               VALUES (%s, %s, %s, NOW() + INTERVAL '10 minutes')
               ON CONFLICT (email, purpose)
               DO UPDATE SET code = EXCLUDED.code, expires_at = EXCLUDED.expires_at""",
            (email, code, purpose),
        )
        conn.commit()
        return code


def verify_code(email, code, purpose):
    with get_db() as conn:
        row = conn.execute(
            """DELETE FROM verification_codes
               WHERE email = %s AND code = %s AND purpose = %s AND expires_at > NOW()
               RETURNING id""",
            (email, code, purpose),
        ).fetchone()
        conn.commit()
        return row is not None


def get_sites_for_user(user_id, limit=None):
    with get_db() as conn:
        query = """SELECT slug, title, subdomain, visibility
                   FROM sites
                   WHERE user_id = %s
                   ORDER BY subdomain NULLS LAST, slug"""
        params = [user_id]
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)
        return conn.execute(query, params).fetchall()


def update_site_settings(site_id, title, subdomain, nav=None):
    with get_db() as conn:
        conn.execute(
            "UPDATE sites SET title = %s, subdomain = %s, nav = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (title or None, subdomain or None, nav or None, site_id),
        )
        conn.commit()


def get_pages_for_site(site_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT p.id, p.slug, p.nav_order,
                      (SELECT r.content FROM revisions r WHERE r.page_id = p.id ORDER BY r.revision DESC LIMIT 1) AS content
               FROM pages p
               WHERE p.site_id = %s
               ORDER BY p.nav_order ASC NULLS LAST, p.created_at ASC""",
            (site_id,),
        ).fetchall()


def create_page(site_id, slug):
    with get_db() as conn:
        row = conn.execute(
            "INSERT INTO pages (site_id, slug) VALUES (%s, %s) RETURNING id",
            (site_id, slug),
        ).fetchone()
        conn.commit()
        return row["id"]


def get_export_pages(slug):
    with get_db() as conn:
        return conn.execute(
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


def get_feed_entries(slug):
    with get_db() as conn:
        return conn.execute(
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


def check_subdomain_available(subdomain):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM sites WHERE subdomain = %s", (subdomain,)
        ).fetchone()
        return row is None
