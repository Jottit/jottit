"""Add sites table and migrate pages to be site-aware."""


def migrate(conn):
    # 1. Create sites table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sites (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            subdomain TEXT NOT NULL UNIQUE,
            title TEXT,
            license TEXT,
            visibility TEXT NOT NULL DEFAULT 'public'
                CHECK (visibility IN ('private', 'public', 'open')),
            home_page_slug TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS sites_user_id_idx ON sites (user_id)")

    # 2. Add site_id column to pages (nullable initially)
    conn.execute("""
        ALTER TABLE pages ADD COLUMN IF NOT EXISTS site_id INTEGER
            REFERENCES sites(id) ON DELETE CASCADE
    """)

    # 3. Create a default site for each user that has a username
    #    Copy license from users table to the site
    conn.execute("""
        INSERT INTO sites (user_id, subdomain, title, license)
        SELECT id, username, name, license
        FROM users
        WHERE username IS NOT NULL
        ON CONFLICT (subdomain) DO NOTHING
    """)

    # 4. Set site_id on all claimed pages
    conn.execute("""
        UPDATE pages p
        SET site_id = s.id
        FROM sites s
        WHERE p.user_id = s.user_id
        AND p.site_id IS NULL
        AND p.user_id IS NOT NULL
    """)

    # 5. Create unique index for per-site slugs
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS pages_site_slug_unique
        ON pages (site_id, slug) WHERE site_id IS NOT NULL
    """)

    # 6. Drop the old per-user slug unique index
    conn.execute("DROP INDEX IF EXISTS pages_user_slug_unique")

    # 7. Add index for site_id lookups
    conn.execute("CREATE INDEX IF NOT EXISTS pages_site_id_idx ON pages (site_id)")

    # 8. Drop subdomain and license columns from users table
    conn.execute("ALTER TABLE users DROP COLUMN IF EXISTS subdomain")
    conn.execute("ALTER TABLE users DROP COLUMN IF EXISTS license")
