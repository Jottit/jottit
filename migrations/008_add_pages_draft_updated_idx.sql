CREATE INDEX IF NOT EXISTS pages_draft_updated_idx ON pages (draft, updated_at DESC);
