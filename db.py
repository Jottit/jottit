import importlib.util
import os
import secrets
import threading
from contextlib import contextmanager

from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE = os.environ.get("DATABASE_URL", "dbname=jottit_dev")

_pool = None
_pool_lock = threading.Lock()


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ConnectionPool(
                    DATABASE,
                    min_size=2,
                    max_size=10,
                    open=True,
                    check=ConnectionPool.check_connection,
                    max_idle=300,
                    kwargs={
                        "row_factory": dict_row,
                        "autocommit": False,
                        "connect_timeout": 5,
                    },
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
        row = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'users')"
        ).fetchone()
        if list(row.values())[0]:
            return
        with open("schema.sql") as f:
            conn.execute(f.read(), prepare=False)
        conn.commit()


def run_migrations():
    migrations_dir = os.path.join(os.path.dirname(__file__), "migrations")
    if not os.path.isdir(migrations_dir):
        return

    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        conn.commit()

        applied = {
            row["filename"]
            for row in conn.execute("SELECT filename FROM schema_migrations").fetchall()
        }

        files = sorted(
            f for f in os.listdir(migrations_dir) if f.endswith((".sql", ".py"))
        )
        for filename in files:
            if filename in applied:
                continue
            path = os.path.join(migrations_dir, filename)
            if filename.endswith(".sql"):
                with open(path) as f:
                    sql = f.read()
                conn.execute(sql, prepare=False)
            else:
                spec = importlib.util.spec_from_file_location(filename, path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                mod.migrate(conn)
            conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (%s) ON CONFLICT DO NOTHING",
                (filename,),
            )
            conn.commit()


def _find_page_by_slug(conn, slug, user_id=None):
    if user_id is not None:
        return conn.execute(
            "SELECT id, slug, user_id, draft, listing FROM pages WHERE slug = %s AND user_id = %s",
            (slug, user_id),
        ).fetchone()
    return conn.execute(
        "SELECT id, slug, user_id, draft, listing FROM pages WHERE slug = %s AND user_id IS NULL",
        (slug,),
    ).fetchone()


def save_page(slug, content, draft, user_id=None):
    with get_db() as conn:
        page = _find_page_by_slug(conn, slug, user_id)

        if page:
            conn.execute(
                """INSERT INTO revisions (page_id, revision, content)
                   VALUES (%s, (SELECT COALESCE(MAX(revision), 0) + 1 FROM revisions WHERE page_id = %s), %s)""",
                (page["id"], page["id"], content),
            )
            conn.execute(
                "UPDATE pages SET draft = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (draft, page["id"]),
            )
        else:
            try:
                cursor = conn.execute(
                    "INSERT INTO pages (slug, original_slug, draft, user_id) VALUES (%s, %s, %s, %s) RETURNING id",
                    (slug, slug, draft, user_id),
                )
                page_id = cursor.fetchone()["id"]
            except pg_errors.UniqueViolation:
                conn.rollback()
                from utils import generate_slug

                slug = generate_slug()
                cursor = conn.execute(
                    "INSERT INTO pages (slug, original_slug, draft, user_id) VALUES (%s, %s, %s, %s) RETURNING id",
                    (slug, slug, draft, user_id),
                )
                page_id = cursor.fetchone()["id"]
            conn.execute(
                "INSERT INTO revisions (page_id, revision, content) VALUES (%s, 1, %s)",
                (page_id, content),
            )

        conn.commit()
    return slug


def get_page(page_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT r.content, p.draft, r.created_at
               FROM revisions r
               JOIN pages p ON r.page_id = p.id
               WHERE p.id = %s
               ORDER BY r.revision DESC LIMIT 1""",
            (page_id,),
        ).fetchone()


def get_page_full(page_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT r.content, p.draft, r.created_at,
                      (SELECT COUNT(*) FROM revisions r2 WHERE r2.page_id = p.id) AS revision_count
               FROM revisions r
               JOIN pages p ON r.page_id = p.id
               WHERE p.id = %s
               ORDER BY r.revision DESC LIMIT 1""",
            (page_id,),
        ).fetchone()


def get_page_meta(slug, user_id=None):
    with get_db() as conn:
        return _find_page_by_slug(conn, slug, user_id)


def find_page_owner_for_redirect(slug):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT user_id FROM pages WHERE slug = %s AND user_id IS NOT NULL LIMIT 2",
            (slug,),
        ).fetchall()
        if len(rows) == 1:
            return rows[0]["user_id"]
        return None


def find_page_by_original_slug(original_slug, user_id=None):
    with get_db() as conn:
        if user_id is not None:
            return conn.execute(
                "SELECT id, slug, user_id FROM pages WHERE original_slug = %s AND user_id = %s",
                (original_slug, user_id),
            ).fetchone()
        return conn.execute(
            "SELECT id, slug, user_id FROM pages WHERE original_slug = %s LIMIT 1",
            (original_slug,),
        ).fetchone()


def get_revisions(page_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT r.revision, r.created_at, r.content FROM revisions r
               WHERE r.page_id = %s
               ORDER BY r.revision ASC""",
            (page_id,),
        ).fetchall()


def get_revisions_paginated(page_id, page=1, per_page=6):
    offset = (page - 1) * per_page
    with get_db() as conn:
        return conn.execute(
            """SELECT r.revision, r.created_at,
                      LENGTH(r.content) - LENGTH(REPLACE(r.content, ' ', '')) + 1 AS word_count,
                      LAG(LENGTH(r.content) - LENGTH(REPLACE(r.content, ' ', '')) + 1)
                          OVER (ORDER BY r.revision ASC) AS prev_word_count
               FROM revisions r
               WHERE r.page_id = %s
               ORDER BY r.revision DESC
               LIMIT %s OFFSET %s""",
            (page_id, per_page, offset),
        ).fetchall()


def get_revision_count(page_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM revisions WHERE page_id = %s",
            (page_id,),
        ).fetchone()
        return row["cnt"]


def get_revision(page_id, revision):
    with get_db() as conn:
        return conn.execute(
            """SELECT r.content, r.created_at, r.revision FROM revisions r
               WHERE r.page_id = %s AND r.revision = %s""",
            (page_id, revision),
        ).fetchone()


def get_user(user_id):
    with get_db() as conn:
        return conn.execute(
            "SELECT id, email, username, name, bio, avatar, license, subdomain FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()


def get_user_by_username(username):
    with get_db() as conn:
        return conn.execute(
            "SELECT id, email, username, name, bio, avatar, license, subdomain FROM users WHERE username = %s",
            (username,),
        ).fetchone()


def user_exists(email):
    with get_db() as conn:
        row = conn.execute("SELECT 1 FROM users WHERE email = %s", (email,)).fetchone()
        return row is not None


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


def set_user_username(user_id, username):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET username = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (username, user_id),
        )
        conn.commit()


def claim_page(page_id, user_id):
    with get_db() as conn:
        result = conn.execute(
            "UPDATE pages SET user_id = %s WHERE id = %s AND user_id IS NULL",
            (user_id, page_id),
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


def rename_page(page_id, new_slug):
    with get_db() as conn:
        result = conn.execute(
            "UPDATE pages SET slug = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (new_slug, page_id),
        )
        conn.commit()
        return result.rowcount > 0


def get_pages_for_user(user_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT p.slug, p.draft, p.listing, p.updated_at, r.content
               FROM pages p
               JOIN revisions r ON r.page_id = p.id
               WHERE p.user_id = %s
               AND r.revision = (SELECT MAX(r2.revision) FROM revisions r2 WHERE r2.page_id = p.id)
               ORDER BY p.updated_at DESC""",
            (user_id,),
        ).fetchall()


def get_slugs_for_user(user_id):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT slug FROM pages WHERE user_id = %s", (user_id,)
        ).fetchall()
        return {row["slug"] for row in rows}


def update_page_listing(page_id, listing):
    with get_db() as conn:
        conn.execute(
            "UPDATE pages SET listing = %s WHERE id = %s",
            (listing, page_id),
        )
        conn.commit()


def update_user_settings(user_id, name, username, bio=None, license=None):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET name = %s, username = %s, bio = %s, license = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (name or None, username or None, bio or None, license or None, user_id),
        )
        conn.commit()


def update_user_avatar(user_id, avatar_url):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET avatar = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (avatar_url, user_id),
        )
        conn.commit()


def check_username_available(username):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE username = %s", (username,)
        ).fetchone()
        return row is None


def get_export_pages(page_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT p.slug, r.content, r.created_at
               FROM pages p
               JOIN revisions r ON r.page_id = p.id
               WHERE p.id = %s AND p.draft = FALSE
               AND r.revision = (SELECT MAX(r2.revision) FROM revisions r2 WHERE r2.page_id = p.id)""",
            (page_id,),
        ).fetchall()


def get_export_pages_for_user(user_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT * FROM (
                   SELECT DISTINCT ON (p.id)
                       p.slug,
                       r.content,
                       r.created_at
                   FROM pages p
                   JOIN revisions r ON r.page_id = p.id
                   WHERE p.user_id = %s AND p.draft = FALSE
                   ORDER BY p.id, r.revision DESC
               ) sub
               ORDER BY slug ASC""",
            (user_id,),
        ).fetchall()


def get_feed_entries(page_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT p.slug, r.content, r.created_at
               FROM pages p
               JOIN revisions r ON r.page_id = p.id
               WHERE p.id = %s AND p.draft = FALSE
               AND r.revision = (SELECT MAX(r2.revision) FROM revisions r2 WHERE r2.page_id = p.id)""",
            (page_id,),
        ).fetchall()


def get_feed_entries_for_user(user_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT * FROM (
                   SELECT DISTINCT ON (p.id)
                       p.slug,
                       r.content,
                       r.created_at
                   FROM pages p
                   JOIN revisions r ON r.page_id = p.id
                   WHERE p.user_id = %s AND p.draft = FALSE
                   AND p.listing IN ('listed', 'pinned')
                   ORDER BY p.id, r.revision DESC
               ) sub
               ORDER BY created_at DESC
               LIMIT 20""",
            (user_id,),
        ).fetchall()


def get_public_pages():
    with get_db() as conn:
        return conn.execute(
            """SELECT p.slug, p.updated_at, u.username
               FROM pages p
               LEFT JOIN users u ON p.user_id = u.id
               WHERE p.draft = FALSE
               ORDER BY p.updated_at DESC""",
        ).fetchall()


def delete_page(page_id):
    with get_db() as conn:
        conn.execute("DELETE FROM pages WHERE id = %s", (page_id,))
        conn.commit()


def delete_user(user_id):
    with get_db() as conn:
        conn.execute("UPDATE pages SET user_id = NULL WHERE user_id = %s", (user_id,))
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
