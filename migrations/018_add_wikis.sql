-- Create wikis table
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

CREATE INDEX IF NOT EXISTS wikis_owner_id_idx ON wikis (owner_id);
CREATE INDEX IF NOT EXISTS wikis_slug_idx ON wikis (slug);

-- Add wiki_id to pages (nullable initially for migration)
ALTER TABLE pages ADD COLUMN IF NOT EXISTS wiki_id INTEGER REFERENCES wikis(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS pages_wiki_id_idx ON pages (wiki_id);
CREATE UNIQUE INDEX IF NOT EXISTS pages_wiki_slug_unique ON pages (wiki_id, slug) WHERE wiki_id IS NOT NULL;
