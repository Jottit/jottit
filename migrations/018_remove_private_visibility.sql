UPDATE pages SET visibility = 'unlisted' WHERE visibility = 'private';
ALTER TABLE pages ALTER COLUMN visibility SET DEFAULT 'unlisted';
