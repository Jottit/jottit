-- Add index on secret_hash for lookup performance
CREATE INDEX IF NOT EXISTS page_secrets_hash_idx ON page_secrets (secret_hash);

-- Clean up expired secrets (older than 30 days)
DELETE FROM page_secrets WHERE created_at < NOW() - INTERVAL '30 days';
