"""Add sites table, move subdomain/license from users to sites, add site_id to pages."""


def migrate(conn):
    # 1. Create sites table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            subdomain TEXT NOT NULL UNIQUE,
            visibility TEXT NOT NULL DEFAULT 'public'
                CHECK (visibility IN ('private', 'public')),
            license TEXT,
            home_page_id INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS sites_user_id_idx ON sites (user_id)")

    # 2. Add site_id column to pages
    conn.execute("""
        ALTER TABLE pages ADD COLUMN IF NOT EXISTS
            site_id INTEGER REFERENCES sites(id) ON DELETE SET NULL
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS pages_site_id_idx ON pages (site_id)")

    # 3. For each user with a username, create a default site and assign their pages
    users = conn.execute(
        "SELECT id, username, license, subdomain FROM users WHERE username IS NOT NULL"
    ).fetchall()

    for user in users:
        subdomain = user["subdomain"] or user["username"]
        row = conn.execute(
            """INSERT INTO sites (user_id, subdomain, visibility, license)
               VALUES (%s, %s, 'public', %s)
               ON CONFLICT (subdomain) DO NOTHING
               RETURNING id""",
            (user["id"], subdomain, user["license"]),
        ).fetchone()

        if row:
            site_id = row["id"]
        else:
            site_id = conn.execute(
                "SELECT id FROM sites WHERE subdomain = %s", (subdomain,)
            ).fetchone()["id"]

        conn.execute(
            "UPDATE pages SET site_id = %s WHERE user_id = %s AND site_id IS NULL",
            (site_id, user["id"]),
        )

    # 4. Add FK from sites.home_page_id -> pages.id
    conn.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'sites_home_page_id_fkey' AND table_name = 'sites'
            ) THEN
                ALTER TABLE sites ADD CONSTRAINT sites_home_page_id_fkey
                    FOREIGN KEY (home_page_id) REFERENCES pages(id) ON DELETE SET NULL;
            END IF;
        END $$
    """)

    # 5. Replace per-user slug uniqueness with per-site slug uniqueness
    conn.execute("DROP INDEX IF EXISTS pages_user_slug_unique")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS pages_site_slug_unique
            ON pages (site_id, slug) WHERE site_id IS NOT NULL
    """)

    # Update unclaimed page uniqueness to account for site_id
    conn.execute("DROP INDEX IF EXISTS pages_slug_unclaimed_unique")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS pages_slug_unclaimed_unique
            ON pages (slug) WHERE user_id IS NULL AND site_id IS NULL
    """)

    # 6. Drop subdomain and license from users (moved to sites)
    conn.execute("ALTER TABLE users DROP COLUMN IF EXISTS subdomain")
    conn.execute("ALTER TABLE users DROP COLUMN IF EXISTS license")
