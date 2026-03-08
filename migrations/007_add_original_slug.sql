ALTER TABLE pages ADD COLUMN IF NOT EXISTS original_slug TEXT;
UPDATE pages SET original_slug = slug WHERE original_slug IS NULL;
CREATE INDEX IF NOT EXISTS pages_original_slug ON pages (original_slug);
