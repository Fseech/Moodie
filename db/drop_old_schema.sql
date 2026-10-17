-- One-off: removes the original, larger schema so db/schema.sql can be applied.
-- Deletes all rows in these tables. Only run before real data has been loaded.
DROP MATERIALIZED VIEW IF EXISTS emotion_5m CASCADE;
DROP TABLE IF EXISTS character_points CASCADE;
DROP TABLE IF EXISTS emotion_points CASCADE;
DROP TABLE IF EXISTS cues CASCADE;
DROP TABLE IF EXISTS works CASCADE;
