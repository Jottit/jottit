import random

import psycopg
from psycopg.rows import dict_row

DATABASE = "dbname=jottit_dev"


def get_db():
    conn = psycopg.connect(DATABASE, row_factory=dict_row, autocommit=False)
    return conn


def init_db():
    conn = get_db()
    with open("schema.sql") as f:
        conn.execute(f.read())
    conn.commit()
    conn.close()


def get_latest_revision(slug):
    conn = get_db()
    row = conn.execute(
        """SELECT r.content, r.draft FROM revisions r
           JOIN pages p ON r.page_id = p.id
           JOIN sites s ON p.site_id = s.id
           WHERE s.slug = %s
           ORDER BY r.revision DESC LIMIT 1""",
        (slug,),
    ).fetchone()
    conn.close()
    return row


def save_page(slug, content, draft):
    conn = get_db()
    site = conn.execute("SELECT id FROM sites WHERE slug = %s", (slug,)).fetchone()

    if site:
        page = conn.execute(
            "SELECT id FROM pages WHERE site_id = %s", (site["id"],)
        ).fetchone()
        next_rev = conn.execute(
            "SELECT COALESCE(MAX(revision), 0) + 1 AS next_rev FROM revisions WHERE page_id = %s",
            (page["id"],),
        ).fetchone()["next_rev"]
        conn.execute(
            "INSERT INTO revisions (page_id, revision, content, draft) VALUES (%s, %s, %s, %s)",
            (page["id"], next_rev, content, draft),
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
            "INSERT INTO pages (site_id, slug) VALUES (%s, '-') RETURNING id",
            (site_id,),
        )
        page_id = cursor.fetchone()["id"]
        conn.execute(
            "INSERT INTO revisions (page_id, revision, content, draft) VALUES (%s, 1, %s, %s)",
            (page_id, content, draft),
        )

    conn.commit()
    conn.close()


def get_page(slug):
    conn = get_db()
    row = conn.execute(
        """SELECT r.content, r.draft, r.created_at, s.user_id
           FROM revisions r
           JOIN pages p ON r.page_id = p.id
           JOIN sites s ON p.site_id = s.id
           WHERE s.slug = %s
           ORDER BY r.revision DESC LIMIT 1""",
        (slug,),
    ).fetchone()
    conn.close()
    return row


def get_revisions(slug):
    conn = get_db()
    rows = conn.execute(
        """SELECT r.revision, r.created_at, r.content FROM revisions r
           JOIN pages p ON r.page_id = p.id
           JOIN sites s ON p.site_id = s.id
           WHERE s.slug = %s
           ORDER BY r.revision ASC""",
        (slug,),
    ).fetchall()
    conn.close()
    return rows


def get_revision(slug, revision):
    conn = get_db()
    row = conn.execute(
        """SELECT r.content, r.created_at, r.revision FROM revisions r
           JOIN pages p ON r.page_id = p.id
           JOIN sites s ON p.site_id = s.id
           WHERE s.slug = %s AND r.revision = %s""",
        (slug, revision),
    ).fetchone()
    conn.close()
    return row


def get_site(slug):
    conn = get_db()
    row = conn.execute(
        "SELECT id, slug, user_id, visibility FROM sites WHERE slug = %s", (slug,)
    ).fetchone()
    conn.close()
    return row


def find_or_create_user(email):
    conn = get_db()
    row = conn.execute("SELECT id FROM users WHERE email = %s", (email,)).fetchone()
    if row:
        user_id = row["id"]
    else:
        row = conn.execute(
            "INSERT INTO users (email) VALUES (%s) RETURNING id", (email,)
        ).fetchone()
        user_id = row["id"]
    conn.commit()
    conn.close()
    return user_id


def claim_site(slug, user_id):
    conn = get_db()
    result = conn.execute(
        "UPDATE sites SET user_id = %s WHERE slug = %s AND user_id IS NULL", (user_id, slug)
    )
    conn.commit()
    claimed = result.rowcount > 0
    conn.close()
    return claimed


def create_verification_code(email, purpose):
    code = f"{random.randint(0, 999999):06d}"
    conn = get_db()
    conn.execute(
        """INSERT INTO verification_codes (email, code, purpose, expires_at)
           VALUES (%s, %s, %s, NOW() + INTERVAL '10 minutes')
           ON CONFLICT (email, purpose)
           DO UPDATE SET code = EXCLUDED.code, expires_at = EXCLUDED.expires_at""",
        (email, code, purpose),
    )
    conn.commit()
    conn.close()
    return code


def verify_code(email, code, purpose):
    conn = get_db()
    row = conn.execute(
        """DELETE FROM verification_codes
           WHERE email = %s AND code = %s AND purpose = %s AND expires_at > NOW()
           RETURNING id""",
        (email, code, purpose),
    ).fetchone()
    conn.commit()
    conn.close()
    return row is not None


def get_sites_for_user(user_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT slug, visibility FROM sites WHERE user_id = %s ORDER BY created_at", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def get_user_email(user_id):
    conn = get_db()
    row = conn.execute("SELECT email FROM users WHERE id = %s", (user_id,)).fetchone()
    conn.close()
    return row["email"] if row else None
