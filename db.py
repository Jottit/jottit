import hashlib
import importlib.util
import os
import secrets
import threading
from contextlib import contextmanager

from psycopg import errors as pg_errors
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from utils import SPECIAL_SLUGS, generate_slug, valid_slug

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

        # Advisory lock prevents concurrent workers from running migrations simultaneously
        conn.execute("SELECT pg_advisory_lock(1)")
        try:
            applied = {
                row["filename"]
                for row in conn.execute(
                    "SELECT filename FROM schema_migrations"
                ).fetchall()
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
        finally:
            conn.execute("SELECT pg_advisory_unlock(1)")


def _find_page_by_slug(conn, slug, user_id=None):
    if user_id is not None:
        return conn.execute(
            "SELECT id, slug, original_slug, user_id, visibility FROM pages WHERE slug = %s AND user_id = %s",
            (slug, user_id),
        ).fetchone()
    return conn.execute(
        "SELECT id, slug, original_slug, user_id, visibility FROM pages WHERE slug = %s AND user_id IS NULL",
        (slug,),
    ).fetchone()


def save_page(
    slug, content, visibility="unlisted", user_id=None, source="web", ai_assisted=False
):
    if not valid_slug(slug):
        raise ValueError(f"Invalid slug: {slug!r} (dots are not allowed)")
    with get_db() as conn:
        page = _find_page_by_slug(conn, slug, user_id)

        if page:
            conn.execute(
                """INSERT INTO revisions (page_id, revision, content, source, ai_assisted)
                   VALUES (%s, (SELECT COALESCE(MAX(revision), 0) + 1 FROM revisions WHERE page_id = %s), %s, %s, %s)""",
                (page["id"], page["id"], content, source, ai_assisted),
            )
            conn.execute(
                "UPDATE pages SET visibility = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (visibility, page["id"]),
            )
        else:
            original_slug = slug
            for _attempt in range(3):
                try:
                    cursor = conn.execute(
                        "INSERT INTO pages (slug, original_slug, visibility, user_id) VALUES (%s, %s, %s, %s) RETURNING id",
                        (slug, original_slug, visibility, user_id),
                    )
                    page_id = cursor.fetchone()["id"]
                    break
                except pg_errors.UniqueViolation:
                    conn.rollback()
                    slug = generate_slug()
            else:
                raise RuntimeError("Failed to generate unique slug after 3 attempts")
            conn.execute(
                "INSERT INTO revisions (page_id, revision, content, source, ai_assisted) VALUES (%s, 1, %s, %s, %s)",
                (page_id, content, source, ai_assisted),
            )

        conn.commit()
    return slug


def get_page(page_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT r.content, p.visibility, r.created_at,
                      p.comments_enabled, p.notify_on_comments
               FROM revisions r
               JOIN pages p ON r.page_id = p.id
               WHERE p.id = %s
               ORDER BY r.revision DESC LIMIT 1""",
            (page_id,),
        ).fetchone()


def get_page_full(page_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT r.content, p.visibility, r.created_at, r.source, r.ai_assisted,
                      p.comments_enabled, p.notify_on_comments,
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
            """SELECT r.revision, r.created_at, r.content, r.source, r.ai_assisted FROM revisions r
               WHERE r.page_id = %s
               ORDER BY r.revision ASC""",
            (page_id,),
        ).fetchall()


def get_revisions_paginated(page_id, page=1, per_page=6):
    offset = (page - 1) * per_page
    with get_db() as conn:
        return conn.execute(
            """SELECT r.revision, r.created_at, r.source, r.ai_assisted,
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
            """SELECT r.content, r.created_at, r.revision, r.source, r.ai_assisted FROM revisions r
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
    if not valid_slug(new_slug):
        raise ValueError(f"Invalid slug: {new_slug!r} (dots are not allowed)")
    with get_db() as conn:
        old = conn.execute(
            "SELECT slug, user_id FROM pages WHERE id = %s", (page_id,)
        ).fetchone()
        if old and old["slug"] != new_slug:
            conn.execute(
                "DELETE FROM slug_redirects WHERE old_slug = %s AND user_id IS NOT DISTINCT FROM %s",
                (old["slug"], old["user_id"]),
            )
            conn.execute(
                "INSERT INTO slug_redirects (old_slug, page_id, user_id) VALUES (%s, %s, %s)",
                (old["slug"], page_id, old["user_id"]),
            )
        result = conn.execute(
            "UPDATE pages SET slug = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (new_slug, page_id),
        )
        conn.commit()
        return result.rowcount > 0


def find_slug_redirect(slug, user_id=None):
    with get_db() as conn:
        if user_id is not None:
            row = conn.execute(
                """SELECT p.slug FROM slug_redirects sr
                   JOIN pages p ON p.id = sr.page_id
                   WHERE sr.old_slug = %s AND sr.user_id = %s
                   ORDER BY sr.created_at DESC LIMIT 1""",
                (slug, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT p.slug FROM slug_redirects sr
                   JOIN pages p ON p.id = sr.page_id
                   WHERE sr.old_slug = %s AND sr.user_id IS NULL
                   ORDER BY sr.created_at DESC LIMIT 1""",
                (slug,),
            ).fetchone()
        return row["slug"] if row else None


def find_slug_redirect_with_owner(slug):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT DISTINCT p.slug, p.user_id FROM slug_redirects sr
               JOIN pages p ON p.id = sr.page_id
               WHERE sr.old_slug = %s LIMIT 2""",
            (slug,),
        ).fetchall()
        if len(rows) == 1:
            return rows[0]
        return None


def get_pages_for_user(user_id):
    with get_db() as conn:
        return conn.execute(
            """SELECT p.slug, p.visibility, p.updated_at, r.content
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


def update_page_visibility(page_id, visibility):
    with get_db() as conn:
        conn.execute(
            "UPDATE pages SET visibility = %s WHERE id = %s",
            (visibility, page_id),
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
               WHERE p.id = %s
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
                   WHERE p.user_id = %s
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
               WHERE p.id = %s AND p.visibility IN ('listed', 'pinned')
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
                   WHERE p.user_id = %s AND p.visibility IN ('listed', 'pinned')
                   AND p.slug != ALL(%s)
                   ORDER BY p.id, r.revision DESC
               ) sub
               ORDER BY created_at DESC
               LIMIT 20""",
            (user_id, list(SPECIAL_SLUGS)),
        ).fetchall()


def get_public_pages():
    with get_db() as conn:
        return conn.execute(
            """SELECT p.slug, p.updated_at, u.username
               FROM pages p
               LEFT JOIN users u ON p.user_id = u.id
               WHERE p.visibility != 'private' AND p.slug != ALL(%s)
               ORDER BY p.updated_at DESC""",
            (list(SPECIAL_SLUGS),),
        ).fetchall()


def delete_page(page_id):
    with get_db() as conn:
        conn.execute("DELETE FROM pages WHERE id = %s", (page_id,))
        conn.commit()


def update_user_email(user_id, email):
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET email = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (email, user_id),
        )
        conn.commit()


def delete_user(user_id):
    with get_db() as conn:
        conn.execute("UPDATE pages SET user_id = NULL WHERE user_id = %s", (user_id,))
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()


def create_api_token(user_id, name):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with get_db() as conn:
        row = conn.execute(
            "INSERT INTO api_tokens (user_id, token_hash, name) VALUES (%s, %s, %s) RETURNING id",
            (user_id, token_hash, name),
        ).fetchone()
        conn.commit()
    return token, row["id"]


def get_api_tokens(user_id):
    with get_db() as conn:
        return conn.execute(
            "SELECT id, name, last_used_at, created_at FROM api_tokens WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()


def delete_api_token(token_id, user_id):
    with get_db() as conn:
        result = conn.execute(
            "DELETE FROM api_tokens WHERE id = %s AND user_id = %s",
            (token_id, user_id),
        )
        conn.commit()
        return result.rowcount > 0


def create_oauth_client(redirect_uris, client_name=""):
    client_id = secrets.token_urlsafe(32)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO oauth_clients (id, redirect_uris, client_name) VALUES (%s, %s, %s)",
            (client_id, redirect_uris, client_name),
        )
        conn.commit()
    return client_id


def get_oauth_client(client_id):
    with get_db() as conn:
        return conn.execute(
            "SELECT id, redirect_uris, client_name FROM oauth_clients WHERE id = %s",
            (client_id,),
        ).fetchone()


def create_oauth_code(client_id, user_id, redirect_uri, code_challenge):
    code = secrets.token_urlsafe(32)
    with get_db() as conn:
        conn.execute(
            """INSERT INTO oauth_codes (code, client_id, user_id, redirect_uri, code_challenge, expires_at)
               VALUES (%s, %s, %s, %s, %s, NOW() + INTERVAL '10 minutes')""",
            (code, client_id, user_id, redirect_uri, code_challenge),
        )
        conn.commit()
    return code


def consume_oauth_code(code, client_id, redirect_uri):
    with get_db() as conn:
        row = conn.execute(
            """DELETE FROM oauth_codes
               WHERE code = %s AND client_id = %s AND redirect_uri = %s AND expires_at > NOW()
               RETURNING user_id, code_challenge""",
            (code, client_id, redirect_uri),
        ).fetchone()
        conn.commit()
        return row


def create_page_secret(page_id):
    secret = secrets.token_urlsafe(32)
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO page_secrets (page_id, secret_hash) VALUES (%s, %s) ON CONFLICT (page_id) DO UPDATE SET secret_hash = EXCLUDED.secret_hash",
            (page_id, secret_hash),
        )
        conn.commit()
    return secret


def verify_page_secret(slug, secret):
    secret_hash = hashlib.sha256(secret.encode()).hexdigest()
    with get_db() as conn:
        return conn.execute(
            """SELECT p.id, p.slug, p.user_id, p.visibility FROM page_secrets ps
               JOIN pages p ON ps.page_id = p.id
               WHERE p.slug = %s AND p.user_id IS NULL AND ps.secret_hash = %s
               AND ps.created_at > NOW() - INTERVAL '30 days'""",
            (slug, secret_hash),
        ).fetchone()


def claim_page_with_secret(page_id, user_id):
    with get_db() as conn:
        result = conn.execute(
            "UPDATE pages SET user_id = %s, visibility = 'listed' WHERE id = %s AND user_id IS NULL",
            (user_id, page_id),
        )
        if result.rowcount == 0:
            conn.rollback()
            return False
        conn.execute("DELETE FROM page_secrets WHERE page_id = %s", (page_id,))
        conn.commit()
        return True


def get_user_by_token_hash(token_hash):
    with get_db() as conn:
        row = conn.execute(
            """SELECT u.id, u.email, u.username, u.name, u.bio, u.avatar, u.license
               FROM api_tokens t
               JOIN users u ON t.user_id = u.id
               WHERE t.token_hash = %s""",
            (token_hash,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE api_tokens SET last_used_at = NOW() WHERE token_hash = %s",
                (token_hash,),
            )
            conn.commit()
        return row


# --- Comments ---


def create_comment(page_id, user_id, body, ip_hash, parent_id=None):
    with get_db() as conn:
        if parent_id is not None:
            parent = conn.execute(
                "SELECT id, parent_id FROM comments WHERE id = %s AND page_id = %s",
                (parent_id, page_id),
            ).fetchone()
            if not parent:
                return None
            if parent["parent_id"] is not None:
                return None
        row = conn.execute(
            """INSERT INTO comments (page_id, parent_id, user_id, body, ip_hash)
               VALUES (%s, %s, %s, %s, %s)
               RETURNING id, created_at""",
            (page_id, parent_id, user_id, body, ip_hash),
        ).fetchone()
        conn.commit()
        return row


def get_comments(page_id, include_hidden=False):
    with get_db() as conn:
        hidden_filter = "" if include_hidden else "AND c.is_hidden = FALSE"
        rows = conn.execute(
            f"""SELECT c.id, c.parent_id, c.body,
                       c.is_hidden, c.created_at,
                       u.name AS author_name, u.username, u.avatar
                FROM comments c
                JOIN users u ON c.user_id = u.id
                WHERE c.page_id = %s {hidden_filter}
                ORDER BY c.created_at ASC""",
            (page_id,),
        ).fetchall()
        return rows


def get_comment(comment_id):
    with get_db() as conn:
        return conn.execute(
            "SELECT id, page_id, parent_id FROM comments WHERE id = %s",
            (comment_id,),
        ).fetchone()


def hide_comment(comment_id, page_id):
    with get_db() as conn:
        conn.execute(
            "UPDATE comments SET is_hidden = NOT is_hidden WHERE id = %s AND page_id = %s",
            (comment_id, page_id),
        )
        conn.commit()


def count_comments_by_ip(ip_hash):
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM comments WHERE ip_hash = %s AND created_at > NOW() - INTERVAL '1 hour'",
            (ip_hash,),
        ).fetchone()
        return row["cnt"]


def get_comment_count(page_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM comments WHERE page_id = %s AND is_hidden = FALSE",
            (page_id,),
        ).fetchone()
        return row["cnt"]
