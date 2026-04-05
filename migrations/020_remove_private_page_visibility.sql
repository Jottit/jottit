-- Convert any remaining 'private' pages to 'unlisted' since page-level privacy
-- is replaced by wiki-level visibility in v2.
UPDATE pages SET visibility = 'unlisted' WHERE visibility = 'private';
