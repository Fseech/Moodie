-- Remove tension from stored scores and require display metadata for all films.
ALTER TABLE emotion_points DROP COLUMN IF EXISTS tension;
ALTER TABLE works ALTER COLUMN year SET NOT NULL;
ALTER TABLE works ALTER COLUMN genre SET NOT NULL;
