-- Migration: Drop sites table, move data to pages and users

-- Add username and name columns to users
ALTER TABLE users ADD COLUMN IF NOT EXISTS username TEXT UNIQUE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS name TEXT;

-- Migrate site subdomain/title to users
UPDATE users u
SET username = s.subdomain, name = s.title
FROM sites s
WHERE s.user_id = u.id AND s.subdomain IS NOT NULL;

-- Create new pages from sites (one page per site, using site slug)
-- First, add user_id to pages
ALTER TABLE pages ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

-- For each site, set user_id on its pages and update slug to be the site slug
-- Since the old model had site_id -> site.slug, we need to give each page a unique slug
-- For index pages, use the site slug; for sub-pages, use siteslug-pageslug
UPDATE pages p
SET user_id = s.user_id
FROM sites s
WHERE p.site_id = s.id;

-- Rename index pages to use the site slug
UPDATE pages p
SET slug = s.slug
FROM sites s
WHERE p.site_id = s.id AND p.slug = '-';

-- Delete non-index sub-pages (they had slugs other than '-', which were not renamed above)
-- After the UPDATE above, index pages now have slug = site.slug, so we identify
-- sub-pages as those whose slug doesn't match their site's slug
DELETE FROM pages p
USING sites s
WHERE p.site_id = s.id AND p.slug != s.slug;

-- Drop old columns and tables
ALTER TABLE pages DROP COLUMN IF EXISTS site_id;
ALTER TABLE pages DROP COLUMN IF EXISTS nav_order;
DROP TABLE IF EXISTS sites CASCADE;
