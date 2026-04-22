DROP INDEX IF EXISTS comments_page_id_idx;
DROP INDEX IF EXISTS comments_ip_created_idx;
DROP INDEX IF EXISTS comments_user_id_idx;
DROP TABLE IF EXISTS comments;

ALTER TABLE pages DROP COLUMN IF EXISTS comments_enabled;
ALTER TABLE pages DROP COLUMN IF EXISTS notify_on_comments;

DELETE FROM verification_codes WHERE purpose = 'comment';

ALTER TABLE verification_codes DROP CONSTRAINT IF EXISTS verification_codes_purpose_check;
ALTER TABLE verification_codes ADD CONSTRAINT verification_codes_purpose_check
    CHECK (purpose IN ('claim', 'signin', 'email_change', 'oauth'));
