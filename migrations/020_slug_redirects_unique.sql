DELETE FROM slug_redirects a USING slug_redirects b
    WHERE a.created_at < b.created_at AND a.old_slug = b.old_slug
    AND a.user_id IS NOT DISTINCT FROM b.user_id;
DROP INDEX IF EXISTS slug_redirects_lookup;
CREATE UNIQUE INDEX slug_redirects_lookup ON slug_redirects (old_slug, user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX slug_redirects_lookup_unclaimed ON slug_redirects (old_slug) WHERE user_id IS NULL;
