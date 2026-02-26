CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sites (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    slug TEXT NOT NULL UNIQUE,
    title TEXT,
    subdomain TEXT UNIQUE,
    nav TEXT,
    visibility TEXT NOT NULL DEFAULT 'public' CHECK (visibility IN ('public', 'private')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pages (
    id SERIAL PRIMARY KEY,
    site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    nav_order INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (site_id, slug)
);

CREATE TABLE IF NOT EXISTS revisions (
    id SERIAL PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    content TEXT NOT NULL,
    draft BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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

CREATE INDEX IF NOT EXISTS sites_user_id_idx ON sites (user_id);
CREATE INDEX IF NOT EXISTS pages_site_id_idx ON pages (site_id);
CREATE INDEX IF NOT EXISTS revisions_page_id_idx ON revisions (page_id);
