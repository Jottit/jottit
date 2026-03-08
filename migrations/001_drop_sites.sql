-- Migration: Drop sites table, move data to pages and users

BEGIN;

-- Add username and name columns to users
ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT;

-- Migrate site subdomain/title to users (pick the site with the most pages)
UPDATE users u
SET username = best.subdomain, name = best.title
FROM (
    SELECT DISTINCT ON (s.user_id)
        s.user_id, s.subdomain, s.title
    FROM sites s
    JOIN pages p ON p.site_id = s.id
    WHERE s.subdomain IS NOT NULL AND s.subdomain <> ''
    GROUP BY s.user_id, s.id, s.subdomain, s.title
    ORDER BY s.user_id, COUNT(p.id) DESC, s.id ASC
) best
WHERE best.user_id = u.id;

-- Add user_id to pages
ALTER TABLE pages ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

-- Set user_id on pages from their site
UPDATE pages p
SET user_id = s.user_id
FROM sites s
WHERE p.site_id = s.id;

-- Generate slugs for index pages (slug = '-') from first heading, fallback to site slug
UPDATE pages p
SET slug = COALESCE(
    NULLIF(
        TRIM(BOTH '-' FROM
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    LOWER(TRIM(
                        (SELECT (REGEXP_MATCH(r.content, '^#\s+([^\n\r]+)'))[1]
                         FROM revisions r
                         WHERE r.page_id = p.id
                         ORDER BY r.revision DESC LIMIT 1)
                    )),
                    '[^a-z0-9\s-]', '', 'g'),
                '\s+', '-', 'g')
        ),
        ''),
    s.slug)
FROM sites s
WHERE p.site_id = s.id AND p.slug = '-';

-- Handle duplicate slugs by appending the old site slug as suffix
WITH dupes AS (
    SELECT id, slug, ROW_NUMBER() OVER (PARTITION BY slug ORDER BY id) as rn,
           site_id
    FROM pages
)
UPDATE pages p
SET slug = p.slug || '-' || s.slug
FROM dupes d
JOIN sites s ON d.site_id = s.id
WHERE p.id = d.id AND d.rn > 1;

-- Drop old columns and tables
ALTER TABLE pages DROP COLUMN IF EXISTS site_id;
ALTER TABLE pages DROP COLUMN IF EXISTS nav_order;
DROP TABLE IF EXISTS sites CASCADE;

-- Replace unique constraint: was (site_id, slug), now just (slug)
ALTER TABLE pages DROP CONSTRAINT IF EXISTS pages_site_id_slug_key;
ALTER TABLE pages ADD CONSTRAINT pages_slug_key UNIQUE (slug);

COMMIT;
