ALTER TABLE pages ADD COLUMN IF NOT EXISTS visibility TEXT NOT NULL DEFAULT 'private';
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'pages' AND column_name = 'draft') THEN
        UPDATE pages SET visibility = CASE
            WHEN draft = TRUE THEN 'private'
            ELSE listing
        END;
    END IF;
END $$;
ALTER TABLE pages DROP COLUMN IF EXISTS draft;
ALTER TABLE pages DROP COLUMN IF EXISTS listing;
DROP INDEX IF EXISTS pages_draft_idx;
DROP INDEX IF EXISTS pages_draft_updated_idx;
CREATE INDEX IF NOT EXISTS pages_visibility_idx ON pages (visibility);
CREATE INDEX IF NOT EXISTS pages_visibility_updated_idx ON pages (visibility, updated_at DESC);
