import os
import secrets
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from utils import INDEX_PAGE_SLUG

DATABASE = os.environ.get("DATABASE_URL", "dbname=jottit_dev")

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE,
            min_size=2,
            max_size=10,
            open=True,
            kwargs={"row_factory": dict_row, "autocommit": False, "connect_timeout": 5},
        )
    return _pool


def reset_pool():
    """Close and reset the pool (used by tests when DATABASE changes)."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_db():
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        if conn.info.transaction_status != 0:
            conn.rollback()
        pool.putconn(conn)


def init_db():
    with get_db() as conn:
        with open("schema.sql") as f:
            conn.execute(f.read(), prepare=False)
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
                    "SELECT id FROM pages WHERE site_id = %s AND slug = %s",
                    (site["id"], INDEX_PAGE_SLUG),
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
                (site_id, page_slug or INDEX_PAGE_SLUG),
            )
            page_id = cursor.fetchone()["id"]
            conn.execute(
                "INSERT INTO revisions (page_id, revision, content, draft) VALUES (%s, 1, %s, %s)",
                (page_id, content, draft),
            )

        conn.commit()


def get_page(site_id, page_slug=None):
    with get_db() as conn:
        if page_slug:
            return conn.execute(
                """SELECT r.content, r.draft, r.created_at
                   FROM revisions r
                   JOIN pages p ON r.page_id = p.id
                   WHERE p.site_id = %s AND p.slug = %s
                   ORDER BY r.revision DESC LIMIT 1""",
                (site_id, page_slug),
            ).fetchone()
        return conn.execute(
            """SELECT r.content, r.draft, r.created_at
               FROM revisions r
               JOIN pages p ON r.page_id = p.id
               WHERE p.site_id = %s
               ORDER BY r.revision DESC LIMIT 1""",
            (site_id,),
        ).fetchone()


def get_revisions(site_id, page_slug=None):
    with get_db() as conn:
        return conn.execute(
            """SELECT r.revision, r.created_at, r.content FROM revisions r
               JOIN pages p ON r.page_id = p.id
               WHERE p.site_id = %s AND p.slug = %s
               ORDER BY r.revision ASC""",
            (site_id, page_slug or INDEX_PAGE_SLUG),
        ).fetchall()


def get_revisions_paginated(site_id, page_slug=None, page=1, per_page=6):
    offset = (page - 1) * per_page
    with get_db() as conn:
        return conn.execute(
            """SELECT r.revision, r.created_at,
                      LENGTH(r.content) - LENGTH(REPLACE(r.content, ' ', '')) + 1 AS word_count,
                      LAG(LENGTH(r.content) - LENGTH(REPLACE(r.content, ' ', '')) + 1)
                          OVER (ORDER BY r.revision ASC) AS prev_word_count
               FROM revisions r
               JOIN pages p ON r.page_id = p.id
               WHERE p.site_id = %s AND p.slug = %s
               ORDER BY r.revision DESC
               LIMIT %s OFFSET %s""",
            (site_id, page_slug or INDEX_PAGE_SLUG, per_page, offset),
        ).fetchall()


def get_revision_count(site_id, page_slug=None):
    with get_db() as conn:
        row = conn.execute(
            """SELECT COUNT(*) AS cnt FROM revisions r
               JOIN pages p ON r.page_id = p.id
               WHERE p.site_id = %s AND p.slug = %s""",
            (site_id, page_slug or INDEX_PAGE_SLUG),
        ).fetchone()
        return row["cnt"]


def get_revision(site_id, revision, page_slug=None):
    with get_db() as conn:
        return conn.execute(
            """SELECT r.content, r.created_at, r.revision FROM revisions r
               JOIN pages p ON r.page_id = p.id
               WHERE p.site_id = %s AND p.slug = %s AND r.revision = %s""",
            (site_id, page_slug or INDEX_PAGE_SLUG, revision),
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


def claim_site(site_id, user_id):
    with get_db() as conn:
        result = conn.execute(
            "UPDATE sites SET user_id = %s WHERE id = %s AND user_id IS NULL",
            (user_id, site_id),
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


def get_export_pages(site_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT * FROM (
                   SELECT DISTINCT ON (p.id)
                       p.slug AS page_slug,
                       r.content,
                       r.created_at
                   FROM pages p
                   JOIN revisions r ON r.page_id = p.id
                   WHERE p.site_id = %s AND r.draft = FALSE
                   ORDER BY p.id, r.revision DESC
               ) sub
               ORDER BY page_slug ASC""",
            (site_id,),
        ).fetchall()


def get_feed_entries(site_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT * FROM (
                   SELECT DISTINCT ON (p.id)
                       p.slug AS page_slug,
                       r.content,
                       r.created_at
                   FROM pages p
                   JOIN revisions r ON r.page_id = p.id
                   WHERE p.site_id = %s AND r.draft = FALSE
                   ORDER BY p.id, r.revision DESC
               ) sub
               ORDER BY created_at DESC
               LIMIT 20""",
            (site_id,),
        ).fetchall()


def delete_page(site_id, page_slug):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM pages WHERE site_id = %s AND slug = %s",
            (site_id, page_slug),
        )
        conn.commit()


def delete_site(site_id):
    with get_db() as conn:
        conn.execute("DELETE FROM sites WHERE id = %s", (site_id,))
        conn.commit()


def check_subdomain_available(subdomain):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM sites WHERE subdomain = %s", (subdomain,)
        ).fetchone()
        return row is None
