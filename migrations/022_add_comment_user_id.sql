ALTER TABLE comments ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS comments_user_id_idx ON comments (user_id);
