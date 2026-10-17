-- Movie emotional arc — Tiger Data (TimescaleDB) schema
-- Holds only what website/index.html displays. See SCHEMA.md for the column-to-UI mapping.
-- Film time is stored as a timestamptz offset from epoch: t = '1970-01-01'::timestamptz + window_start_ms,
-- so time_bucket() works; extract(epoch FROM t) / 60 gives minutes into the film.
--
-- If the old (larger) schema is already in the database, run db/drop_old_schema.sql first.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ---------------------------------------------------------------
-- Works: one row per film. Feeds the film card header.
-- ---------------------------------------------------------------
CREATE TABLE works (
    work_id     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title       TEXT     NOT NULL UNIQUE,              -- UNIQUE so the pipeline can skip films already scored
    year        SMALLINT,
    genre       TEXT,
    runtime_ms  BIGINT   NOT NULL
);

-- ---------------------------------------------------------------
-- Emotion points: the time series. One row per (work, window).
-- Feeds the emotion graph, the moodline, and the card's emotion averages.
-- ---------------------------------------------------------------
CREATE TABLE emotion_points (
    work_id   BIGINT      NOT NULL REFERENCES works(work_id) ON DELETE CASCADE,
    t         TIMESTAMPTZ NOT NULL,      -- epoch + window_start_ms
    valence   REAL NOT NULL,             -- -1 .. 1   dark .. warm (moodline)
    joy       REAL NOT NULL,             --  0 .. 1
    sadness   REAL NOT NULL,
    fear      REAL NOT NULL,
    anger     REAL NOT NULL,
    tension   REAL NOT NULL,
    surprise  REAL NOT NULL,
    PRIMARY KEY (work_id, t)
);

SELECT create_hypertable('emotion_points', 't', chunk_time_interval => INTERVAL '1 day');

-- ---------------------------------------------------------------
-- Queries the website runs (server-side; never put the DB URL in browser JS)
-- ---------------------------------------------------------------

-- Film cards: header + average emotions. The page turns the six averages into percentages.
-- SELECT w.work_id, w.title, w.year, w.genre, round(w.runtime_ms / 60000.0) AS runtime_min,
--        avg(p.joy) AS joy, avg(p.sadness) AS sadness, avg(p.fear) AS fear,
--        avg(p.anger) AS anger, avg(p.tension) AS tension, avg(p.surprise) AS surprise
-- FROM works w JOIN emotion_points p USING (work_id)
-- GROUP BY w.work_id
-- ORDER BY w.title;

-- One film's arc (emotion graph + moodline):
-- SELECT extract(epoch FROM t) / 60 AS minute,
--        joy, sadness, fear, anger, tension, surprise, valence
-- FROM emotion_points
-- WHERE work_id = $1
-- ORDER BY t;
