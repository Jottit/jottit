-- Drop global uniqueness on slug
ALTER TABLE pages DROP CONSTRAINT IF EXISTS pages_slug_key;

-- Per-user uniqueness for claimed pages
CREATE UNIQUE INDEX IF NOT EXISTS pages_user_slug_unique ON pages (user_id, slug) WHERE user_id IS NOT NULL;

-- Unclaimed pages still need slug uniqueness among themselves
CREATE UNIQUE INDEX IF NOT EXISTS pages_slug_unclaimed_unique ON pages (slug) WHERE user_id IS NULL;
