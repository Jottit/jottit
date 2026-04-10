CREATE TABLE IF NOT EXISTS comments (
    id SERIAL PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES comments(id) ON DELETE CASCADE,
    author_name TEXT NOT NULL DEFAULT '',
    author_email TEXT NOT NULL,
    body TEXT NOT NULL,
    is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
    is_hidden BOOLEAN NOT NULL DEFAULT FALSE,
    ip_hash TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS comments_page_id_idx ON comments (page_id);
CREATE INDEX IF NOT EXISTS comments_ip_created_idx ON comments (ip_hash, created_at);

ALTER TABLE pages ADD COLUMN IF NOT EXISTS comments_enabled BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE pages ADD COLUMN IF NOT EXISTS notify_on_comments BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE verification_codes DROP CONSTRAINT IF EXISTS verification_codes_purpose_check;
ALTER TABLE verification_codes ADD CONSTRAINT verification_codes_purpose_check
    CHECK (purpose IN ('claim', 'signin', 'email_change', 'oauth', 'comment'));
