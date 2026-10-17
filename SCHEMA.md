# Data model

Movie emotional arc — Tiger Data (TimescaleDB). The DDL in [`db/schema.sql`](./db/schema.sql) is the source of truth; this is the quick reference.
The schema stores only what [`website/index.html`](./website/index.html) displays.

## Tables

### `works` — one row per film

| Column | Type | Used by the website for |
|---|---|---|
| `work_id` | bigint PK | identifying the film |
| `title` | text, unique | card title, search |
| `year` | smallint | card subtitle |
| `genre` | text | card subtitle, search |
| `runtime_ms` | bigint | card runtime ("1h 36m"), chart x-axis labels |

### `emotion_points` — hypertable, one row per scored window

| Column | Type | Range | Used by the website for |
|---|---|---|---|
| `work_id` | bigint PK, FK → works | | |
| `t` | timestamptz PK | | chart x-axis (minutes into the film) |
| `joy` `sadness` `fear` `anger` `tension` `surprise` | real | 0 … 1 | emotion graph lines; averaged for the card's % breakdown, "Mostly X" badge and "Most X" filter chips |
| `valence` | real | −1 … 1 | moodline (dark ↔ warm) |

Windows with no dialogue are not stored; the chart connects across the gap.

## How film time is stored

```
t = '1970-01-01 00:00:00+00'::timestamptz + (window_start_ms || ' milliseconds')::interval
```

A window starting 01:32:00 into the film is stored as `1970-01-01 01:32:00+00`. Convert back with `extract(epoch FROM t) / 60` (minutes).

## Queries

Film cards (`works` + average emotions):

```sql
SELECT w.work_id, w.title, w.year, w.genre, round(w.runtime_ms / 60000.0) AS runtime_min,
       avg(p.joy) AS joy, avg(p.sadness) AS sadness, avg(p.fear) AS fear,
       avg(p.anger) AS anger, avg(p.tension) AS tension, avg(p.surprise) AS surprise
FROM works w JOIN emotion_points p USING (work_id)
GROUP BY w.work_id
ORDER BY w.title;
```

One film's arc:

```sql
SELECT extract(epoch FROM t) / 60 AS minute,
       joy, sadness, fear, anger, tension, surprise, valence
FROM emotion_points
WHERE work_id = $1
ORDER BY t;
```

Insert a film (pipeline; skip if the title already exists):

```sql
INSERT INTO works (title, year, genre, runtime_ms)
VALUES ($1, $2, $3, $4)
ON CONFLICT (title) DO NOTHING
RETURNING work_id;
```

Insert a scored window:

```sql
INSERT INTO emotion_points
    (work_id, t, valence, joy, sadness, fear, anger, tension, surprise)
VALUES
    ($1, '1970-01-01'::timestamptz + ($2 || ' milliseconds')::interval,
     $3, $4, $5, $6, $7, $8, $9)
ON CONFLICT (work_id, t) DO UPDATE SET
    valence = EXCLUDED.valence, joy = EXCLUDED.joy, sadness = EXCLUDED.sadness,
    fear = EXCLUDED.fear, anger = EXCLUDED.anger, tension = EXCLUDED.tension,
    surprise = EXCLUDED.surprise;
```

## Gemini scoring contract

Request: a batch of windows `[{window_idx, text}, …]` with `response_mime_type = "application/json"` and [`gemini_schema.json`](./gemini_schema.json) as `response_schema`.

Response: `{ "windows": [ { window_idx, valence, joy, sadness, fear, anger, tension, surprise }, … ] }`.
Map each result back to its window by `window_idx` and insert with the query above.

## Setup

```bash
python db/run_schema.py                                   # reads TIMESCALE_SERVICE_URL from .env
# If the old schema was already applied, first run:
psql "$TIMESCALE_SERVICE_URL" -f db/drop_old_schema.sql
```
