CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    username TEXT UNIQUE,
    name TEXT,
    bio TEXT,
    license TEXT,
    avatar TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pages (
    id SERIAL PRIMARY KEY,
    slug TEXT NOT NULL,
    original_slug TEXT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    draft BOOLEAN NOT NULL DEFAULT FALSE,
    listing TEXT NOT NULL DEFAULT 'listed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS revisions (
    id SERIAL PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (page_id, revision)
);

CREATE TABLE IF NOT EXISTS verification_codes (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    code TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK (purpose IN ('claim', 'signin')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (email, purpose)
);

CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'pages' AND column_name = 'user_id') THEN
        CREATE INDEX IF NOT EXISTS pages_user_id_idx ON pages (user_id);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS revisions_page_id_idx ON revisions (page_id);
CREATE INDEX IF NOT EXISTS revisions_page_revision_idx ON revisions (page_id, revision DESC);
CREATE INDEX IF NOT EXISTS pages_draft_idx ON pages (draft);
CREATE INDEX IF NOT EXISTS pages_original_slug ON pages (original_slug);
CREATE UNIQUE INDEX IF NOT EXISTS pages_user_slug_unique ON pages (user_id, slug) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS pages_slug_unclaimed_unique ON pages (slug) WHERE user_id IS NULL;
CREATE INDEX IF NOT EXISTS pages_draft_updated_idx ON pages (draft, updated_at DESC);

-- On fresh DBs (no sites table), seed historical migrations as already applied
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'sites') THEN
        INSERT INTO schema_migrations (filename) VALUES
            ('001_drop_sites.sql'),
            ('002_add_avatar_bio.sql'),
            ('003_add_license.sql'),
            ('004_add_listing.sql'),
            ('005_per_user_slugs.sql'),
            ('007_add_original_slug.sql')
        ON CONFLICT DO NOTHING;
    END IF;
END $$;
