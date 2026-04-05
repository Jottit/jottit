"""Migrate existing users to wikis.

For each user with a username:
1. Create a wiki using the user's subdomain or username as slug.
2. Copy the user's license to the wiki if available.
3. Associate all claimed pages with the new wiki.
"""


def _column_exists(conn, table, column):
    row = conn.execute("""
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        )
    """, (table, column)).fetchone()
    return list(row.values())[0]


def migrate(conn):
    has_subdomain = _column_exists(conn, "users", "subdomain")
    has_license = _column_exists(conn, "users", "license")

    # Build select dynamically based on available columns
    cols = ["u.id", "u.username"]
    if has_subdomain:
        cols.append("u.subdomain")
    if has_license:
        cols.append("u.license")

    sql = f"SELECT DISTINCT {', '.join(cols)} FROM users u WHERE u.username IS NOT NULL"
    users = conn.execute(sql).fetchall()

    for user in users:
        wiki_slug = (user.get("subdomain") if has_subdomain else None) or user["username"]
        if not wiki_slug:
            continue

        wiki_name = wiki_slug
        license_val = user.get("license") if has_license else None

        existing = conn.execute(
            "SELECT id FROM wikis WHERE slug = %s", (wiki_slug,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE pages SET wiki_id = %s WHERE user_id = %s AND wiki_id IS NULL",
                (existing["id"], user["id"]),
            )
            continue

        row = conn.execute(
            """INSERT INTO wikis (slug, name, owner_id, visibility, license)
               VALUES (%s, %s, %s, 'public', %s) RETURNING id""",
            (wiki_slug, wiki_name, user["id"], license_val),
        ).fetchone()
        wiki_id = row["id"]

        conn.execute(
            "UPDATE pages SET wiki_id = %s WHERE user_id = %s AND wiki_id IS NULL",
            (wiki_id, user["id"]),
        )
