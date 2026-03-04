-- Move draft column from revisions to pages
-- Draft is a property of the page, not a per-revision property

ALTER TABLE pages ADD COLUMN draft BOOLEAN NOT NULL DEFAULT FALSE;

-- Migrate: set each page's draft from its latest revision
UPDATE pages SET draft = sub.draft
FROM (
    SELECT DISTINCT ON (page_id) page_id, draft
    FROM revisions
    ORDER BY page_id, revision DESC
) sub
WHERE pages.id = sub.page_id;

ALTER TABLE revisions DROP COLUMN draft;

DROP INDEX IF EXISTS revisions_draft_created_idx;
CREATE INDEX IF NOT EXISTS pages_draft_idx ON pages (draft);
