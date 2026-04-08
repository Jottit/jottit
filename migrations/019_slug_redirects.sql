CREATE TABLE IF NOT EXISTS slug_redirects (
    old_slug TEXT NOT NULL,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS slug_redirects_lookup ON slug_redirects (old_slug, user_id);
