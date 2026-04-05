CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    username TEXT UNIQUE,
    name TEXT,
    bio TEXT,
    avatar TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS wikis (
    id SERIAL PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    owner_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    visibility TEXT NOT NULL DEFAULT 'public' CHECK (visibility IN ('public', 'private')),
    license TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pages (
    id SERIAL PRIMARY KEY,
    slug TEXT NOT NULL,
    original_slug TEXT,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    wiki_id INTEGER REFERENCES wikis(id) ON DELETE SET NULL,
    visibility TEXT NOT NULL DEFAULT 'unlisted',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS revisions (
    id SERIAL PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    content TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'web',
    ai_assisted BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (page_id, revision)
);

CREATE TABLE IF NOT EXISTS verification_codes (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    code TEXT NOT NULL,
    purpose TEXT NOT NULL CHECK (purpose IN ('claim', 'signin', 'email_change', 'oauth')),
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (email, purpose)
);

CREATE TABLE IF NOT EXISTS api_tokens (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL DEFAULT '',
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oauth_clients (
    id TEXT PRIMARY KEY,
    redirect_uris TEXT[] NOT NULL,
    client_name TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS oauth_codes (
    code TEXT PRIMARY KEY,
    client_id TEXT NOT NULL REFERENCES oauth_clients(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    redirect_uri TEXT NOT NULL,
    code_challenge TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS page_secrets (
    page_id INTEGER PRIMARY KEY REFERENCES pages(id) ON DELETE CASCADE,
    secret_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
CREATE INDEX IF NOT EXISTS pages_visibility_idx ON pages (visibility);
CREATE INDEX IF NOT EXISTS pages_original_slug ON pages (original_slug);
CREATE UNIQUE INDEX IF NOT EXISTS pages_user_slug_unique ON pages (user_id, slug) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS pages_slug_unclaimed_unique ON pages (slug) WHERE user_id IS NULL;
CREATE INDEX IF NOT EXISTS pages_visibility_updated_idx ON pages (visibility, updated_at DESC);
CREATE INDEX IF NOT EXISTS pages_wiki_id_idx ON pages (wiki_id);
CREATE UNIQUE INDEX IF NOT EXISTS pages_wiki_slug_unique ON pages (wiki_id, slug) WHERE wiki_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS wikis_owner_id_idx ON wikis (owner_id);
CREATE INDEX IF NOT EXISTS api_tokens_user_id_idx ON api_tokens (user_id);
CREATE INDEX IF NOT EXISTS oauth_codes_expires_idx ON oauth_codes (expires_at);
CREATE INDEX IF NOT EXISTS page_secrets_hash_idx ON page_secrets (secret_hash);

-- On fresh DBs (no sites table), seed historical migrations as already applied
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'sites') THEN
        INSERT INTO schema_migrations (filename) VALUES
            ('001_drop_sites.sql'),
            ('002_add_avatar_bio.sql'),
            ('003_add_license.sql'),
            ('004_add_listing.sql'),
            ('005_per_user_slugs.sql'),
            ('006_backfill_usernames.py'),
            ('007_add_original_slug.sql'),
            ('008_add_pages_draft_updated_idx.sql'),
            ('009_add_subdomain.sql'),
            ('010_add_email_change_purpose.sql'),
            ('011_add_api_tokens.sql'),
            ('012_add_revision_source.sql'),
            ('013_add_revision_ai_assisted.sql'),
            ('014_add_oauth.sql'),
            ('015_unify_visibility.sql'),
            ('016_add_page_secrets.sql'),
            ('017_page_secret_expiry_and_index.sql'),
            ('018_add_wikis.sql'),
            ('019_migrate_users_to_wikis.py'),
            ('020_remove_private_page_visibility.sql')
        ON CONFLICT DO NOTHING;
    END IF;
END $$;
