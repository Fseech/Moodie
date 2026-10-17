-- Movie emotional arc — Tiger Data (TimescaleDB) schema
-- Film time is stored as a timestamptz offset from epoch: t = '1970-01-01'::timestamptz + window_start_ms.
-- That lets time_bucket(), continuous aggregates, and compression work unchanged.

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ---------------------------------------------------------------
-- Works: one row per film (later: books, scripts). Plain table.
-- ---------------------------------------------------------------
CREATE TABLE works (
    work_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title         TEXT        NOT NULL,
    year          SMALLINT,
    genre         TEXT,                                    -- catalog genre shown by the film browser
    medium        TEXT        NOT NULL DEFAULT 'film'      -- film | book | screenplay
                              CHECK (medium IN ('film','book','screenplay')),
    source        TEXT        NOT NULL DEFAULT 'srt',      -- srt | gutenberg | imsdb | upload
    runtime_ms    BIGINT,                                  -- total length; set after parsing
    window_ms     INTEGER     NOT NULL DEFAULT 60000,      -- scoring window used for this work
    status        TEXT        NOT NULL DEFAULT 'queued'    -- queued | parsing | scoring | ready | failed
                              CHECK (status IN ('queued','parsing','scoring','ready','failed')),
    windows_total INTEGER,
    windows_done  INTEGER     NOT NULL DEFAULT 0,
    model         TEXT,                                    -- e.g. gemini-2.5-flash
    profile       JSONB,                                   -- cached film-card summary:
                                                           -- {avg:{joy,sadness,fear,anger,tension,surprise},
                                                           --  peak:{joy,sadness,fear,anger,tension,surprise}}
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------
-- Cues: raw parsed subtitle lines. Kept so hover/explain can
-- pull exact dialogue, and so re-scoring never needs the file.
-- ---------------------------------------------------------------
CREATE TABLE cues (
    work_id   BIGINT   NOT NULL REFERENCES works(work_id) ON DELETE CASCADE,
    cue_idx   INTEGER  NOT NULL,
    start_ms  BIGINT   NOT NULL,
    end_ms    BIGINT   NOT NULL,
    speaker   TEXT,                                        -- from screenplay or "NAME:" prefix; usually NULL for .srt
    text      TEXT     NOT NULL,
    PRIMARY KEY (work_id, cue_idx)
);
CREATE INDEX cues_work_time ON cues (work_id, start_ms);

-- ---------------------------------------------------------------
-- Emotion points: the time series. One row per (work, window).
-- Hypertable partitioned on t.
-- ---------------------------------------------------------------
CREATE TABLE emotion_points (
    work_id     BIGINT      NOT NULL REFERENCES works(work_id) ON DELETE CASCADE,
    t           TIMESTAMPTZ NOT NULL,              -- epoch + window_start_ms
    window_ms   INTEGER     NOT NULL,
    cue_count   SMALLINT    NOT NULL DEFAULT 0,    -- 0 => silent window; valence should be NULL
    valence     REAL,                              -- -1 .. 1   negative .. positive
    arousal     REAL,                              --  0 .. 1   calm .. intense
    joy         REAL,                              --  0 .. 1
    sadness     REAL,
    fear        REAL,
    anger       REAL,
    tension     REAL,                              -- suspense / anticipation
    surprise    REAL,
    summary     TEXT,                              -- one-line scene summary from Gemini
    explanation TEXT,                              -- lazy: filled on first hover request
    model       TEXT,
    scored_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (work_id, t)
);

SELECT create_hypertable('emotion_points', 't', chunk_time_interval => INTERVAL '1 day');

-- ---------------------------------------------------------------
-- Optional: per-character series. Same shape, extra key.
-- Leave empty for v1; the chart endpoint can union it later.
-- ---------------------------------------------------------------
CREATE TABLE character_points (
    work_id    BIGINT      NOT NULL REFERENCES works(work_id) ON DELETE CASCADE,
    character  TEXT        NOT NULL,
    t          TIMESTAMPTZ NOT NULL,
    window_ms  INTEGER     NOT NULL,
    line_count SMALLINT    NOT NULL DEFAULT 0,
    valence    REAL,
    arousal    REAL,
    PRIMARY KEY (work_id, character, t)
);
SELECT create_hypertable('character_points', 't', chunk_time_interval => INTERVAL '1 day');

-- ---------------------------------------------------------------
-- Continuous aggregate: 5-minute smoothed arc, refreshed automatically.
-- The chart endpoint reads this for the default view and falls back
-- to raw time_bucket() for other resolutions.
-- ---------------------------------------------------------------
CREATE MATERIALIZED VIEW emotion_5m
WITH (timescaledb.continuous) AS
SELECT
    work_id,
    time_bucket('5 minutes', t) AS bucket,
    avg(valence)  AS valence,
    avg(arousal)  AS arousal,
    avg(joy)      AS joy,
    avg(sadness)  AS sadness,
    avg(fear)     AS fear,
    avg(anger)    AS anger,
    avg(tension)  AS tension,
    avg(surprise) AS surprise,
    sum(cue_count) AS cue_count
FROM emotion_points
GROUP BY work_id, bucket
WITH NO DATA;

SELECT add_continuous_aggregate_policy('emotion_5m',
    start_offset    => NULL,
    end_offset      => INTERVAL '0',
    schedule_interval => INTERVAL '1 minute');

-- ---------------------------------------------------------------
-- Compression (optional; cheap win for the demo DB)
-- ---------------------------------------------------------------
ALTER TABLE emotion_points SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'work_id',
    timescaledb.compress_orderby   = 't'
);
SELECT add_compression_policy('emotion_points', INTERVAL '7 days');

-- ---------------------------------------------------------------
-- Reference queries the API will use
-- ---------------------------------------------------------------

-- Arc at arbitrary resolution (bucket in seconds), x as film seconds:
-- SELECT extract(epoch FROM time_bucket(make_interval(secs => $2), t)) AS sec,
--        avg(valence) AS valence, avg(arousal) AS arousal,
--        avg(joy) AS joy, avg(sadness) AS sadness, avg(fear) AS fear,
--        avg(anger) AS anger, avg(tension) AS tension, avg(surprise) AS surprise
-- FROM emotion_points
-- WHERE work_id = $1
-- GROUP BY 1 ORDER BY 1;

-- Film-card data for the website. The six values in profile.avg are model
-- scores (0..1); normalize them in the API to the percentages shown by the UI.
-- SELECT work_id, title, year, genre, runtime_ms, profile->'avg' AS avg_emotions
-- FROM works
-- WHERE medium = 'film' AND status = 'ready' AND profile IS NOT NULL
-- ORDER BY title;

-- Default website timeline at five-minute resolution; convert minute to the
-- chart's x-axis and preserve each emotion as its independent 0..1 score.
-- SELECT extract(epoch FROM bucket) / 60.0 AS minute,
--        joy, sadness, fear, anger, tension, surprise
-- FROM emotion_5m
-- WHERE work_id = $1
-- ORDER BY bucket;

-- Normalized arc for comparing two works (x = 0..100 % of runtime, 50 buckets):
-- SELECT floor(extract(epoch FROM t) * 1000.0 / w.runtime_ms * 50) AS pct_bucket,
--        avg(valence) AS valence
-- FROM emotion_points p JOIN works w USING (work_id)
-- WHERE work_id = ANY($1)
-- GROUP BY work_id, 1 ORDER BY work_id, 1;

-- Dialogue behind a point (for the hover/explain call):
-- SELECT text FROM cues
-- WHERE work_id = $1 AND start_ms >= $2 AND start_ms < $2 + $3
-- ORDER BY cue_idx;

-- Lowest and highest moments:
-- SELECT t, valence, summary FROM emotion_points
-- WHERE work_id = $1 AND valence IS NOT NULL
-- ORDER BY valence ASC LIMIT 3;
