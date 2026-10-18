# AGENTS.md — Project handoff

Read this whole file before changing anything. It is the source of truth for what this project is, what exists, and what to build next.

---

## 1. What we're building

**FEELFLIX** — a web app that shows the **emotional arc of a movie over its runtime** and lets viewers browse films by the feeling they want.

- Input: a movie's subtitle file (`.srt`), committed to `data/` in this repo.
- Processing: split the dialogue into 2-minute time windows, send them to the Gemini API, get back emotion scores as structured JSON.
- Storage: save every window's scores as a time-series row in Tiger Data (managed Postgres + TimescaleDB).
- Output: a Netflix-style page of film cards. Each card shows the film's emotion mix; "Show emotion graph" and "Show moodline" reveal its arc over time. Filter chips ("Most fear", "Most joy"…) sort films by mood.

Context: this is a team entry for **SwampHacks** (University of Florida hackathon). **The event is happening now** — all product code is written during the event. Team of four, software only, no hardware.

---

## 2. Architecture

**A. Prep pipeline — runs offline, once per movie**
`.srt file in data/ → parse → chunk into windows → Gemini scoring → insert into Tiger Data`

**B. Live app — what the judges see**
`browser → website/server.py → Tiger Data (read only)`

`website/server.py` serves the page and its read-only JSON endpoints using Python's standard library HTTP server. A browser cannot open a Postgres connection itself, and the connection string must never ship in client-side JS.

The live app **never calls Gemini**. All scoring happens ahead of time. This keeps the demo fast and immune to API rate limits or outages.

---

## 3. Stack

| Layer | Choice | Status |
|---|---|---|
| LLM | Gemini API via `google-genai` Python SDK, model `gemini-3.5-flash` | Decided |
| Database | Tiger Data (Tiger Cloud Free Plan), TimescaleDB hypertable | Decided |
| Pipeline language | Python 3.9+ | Decided |
| Website server | Python standard-library HTTP server in `website/server.py` | Decided for local use |
| Frontend | `website/index.html` — single HTML page, vanilla JS, hand-drawn SVG charts | In progress |
| Website DB access | Read-only queries through `website/server.py`; Tiger URL stays in root `.env` | Decided for local use |

---

## 4. Repo layout

```
/
├── AGENTS.md             ← this file
├── SCHEMA.md             ← data model quick reference (column → website feature)
├── README.md
├── .gitignore            ← ignores .env, venv/, node_modules, build output, .DS_Store
├── .env.example          ← template for secrets (copy to .env)
├── .vscode/settings.json ← shared git auto-fetch settings
├── test_gemini.py        ← one-shot check that the Gemini key works
├── gemini_schema.json    ← Gemini structured-output schema
├── data/                 ← subtitle inputs; check rights before adding non-public-domain files
├── db/
│   ├── schema.sql        ← DDL (source of truth)
│   ├── run_schema.py     ← applies schema.sql using TIMESCALE_SERVICE_URL
│   └── drop_old_schema.sql ← one-off: removes the original larger schema
├── pipeline/             ← .srt parsing, chunking, Gemini scoring, DB loading
└── website/              ← index.html frontend and server.py local read-only web/API server
```

Ownership: each teammate owns one folder (website, pipeline, db, data) to avoid merge conflicts. Shared files (`db/schema.sql`, `gemini_schema.json`, `.env.example`, dependency manifests) should be changed deliberately and mentioned in the commit message.

---

## 5. Current state

**Exists:**
- `website/index.html` — full UI (cards, search, filter chips, emotion graph, moodline) loaded from the local server API. No fake film data remains.
- `website/server.py` — serves the page and read-only film/arc endpoints backed by Tiger Data. Run with `py -3 website\server.py`; open `http://127.0.0.1:8000`.
- `db/schema.sql` — trimmed to exactly what the website displays (Section 6); year and genre are required.
- `db/migrate_remove_tension.sql` — applied to the existing Tiger Data database; its `emotion_points` table now has no tension column.
- `gemini_schema.json` — matches the five emotion columns in `emotion_points`.
- `data/his_girl_friday.srt` — first movie. Its timestamps use 2-digit fractions (`00:01:01,95`), and the text looks auto-transcribed (noisy). The parser must accept 1–3 fraction digits.
- `.gitignore`, `.env.example`, `test_gemini.py`.
- Python must be installed locally (3.9+) with `pip install google-genai python-dotenv psycopg2-binary`. Don't commit `venv/`.
- The configured Tiger Data database currently has ten films and 555 emotion rows. All ten subtitle-backed films are fully scored, including the previously partial Little Princess and Royal Wedding and the five later additions. The latest successful batch used `gemini-3.5-flash-lite` after the default model hit quota limits.

**Security:** `.env` with the Tiger Data password was committed and pushed. It is now untracked, but it's still in git history, so **the Tiger Data password must be reset** in the Tiger Cloud console and everyone's local `.env` updated.

**Pending:** no movie-scoring jobs remain.

---

## 6. Data the website needs

Taken from `website/index.html`. Store only this.

| Website feature | Data |
|---|---|
| Card header | title, year, genre, runtime |
| Search box | title, genre |
| Card emotion bar, % rows, "Mostly X" badge, "Most X" chips | per-film average of joy, sadness, fear, anger, surprise (page converts to %) |
| Emotion graph | per window: minute + the five emotions (0–1) |
| Moodline | per window: minute + valence (−1 dark … 1 warm) |

Not used by the website, so **not stored**: arousal, summaries, posters, subtitle cues, per-character arcs, job status, model/provenance columns, continuous aggregates, compression.

### 6.1 Data shapes the website consumes

The film-list API returns:

Film list
```json
[{ "id": 1, "title": "His Girl Friday", "year": 1940, "genre": "Comedy", "runtime_min": 92,
   "emotions": { "joy": 0.41, "sadness": 0.12, "fear": 0.08, "anger": 0.22, "surprise": 0.18 } }]
```

`GET /api/films/{id}/points` returns one film's arc:
```json
[{ "minute": 0, "joy": 0.1, "sadness": 0.2, "fear": 0.5, "anger": 0.1, "surprise": 0.2, "valence": -0.2 }]
```
Silent windows (no dialogue) are omitted; the chart connects across the gap. The page computes graph x-coordinates as `minute / runtime_min` and fetches arc points on demand.

### 6.2 Gemini output (`gemini_schema.json`)
Batch request; response `{ "windows": [ { window_idx, valence, joy, sadness, fear, anger, surprise } ] }`. `valence` −1…1, the rest 0…1, all required. Pass via `response_mime_type="application/json"` + `response_schema`.

### 6.3 Database
Two tables — `works (work_id, title UNIQUE, year, genre, runtime_ms)` and the hypertable `emotion_points (work_id, t, valence, joy, sadness, fear, anger, surprise)`. Full DDL in `db/schema.sql`; queries and insert statements in `SCHEMA.md`.

Film time is stored as `'1970-01-01'::timestamptz + window start` so hypertable time functions work; `extract(epoch FROM t) / 60` gives minutes into the movie.

---

## 7. Build order

Get **one movie working end to end** before doing anything else.

1. Reset the Tiger Data password (Section 5). Update `.env`.
2. For a fresh database, apply `db/schema.sql` with `python db/run_schema.py`. For the existing database, confirm every film has a year and genre, then apply `db/migrate_remove_tension.sql`; do not drop stored data to migrate it.
3. `pipeline/`: parse `data/his_girl_friday.srt` → cues → 2-minute windows (skip windows with no dialogue).
4. Score windows with Gemini using `gemini_schema.json`, a few windows per request. Short delay between calls; retry on HTTP 429 (`RESOURCE_EXHAUSTED`). Skip films whose title is already in `works`.
5. Insert into `works` and `emotion_points` (SQL in `SCHEMA.md`). Check the arc query looks sensible.
6. Start the local website with `py -3 website\server.py`; the server reads the DB connection string from root `.env` and exposes read-only queries.
7. Score at least one movie into Tiger Data, then verify its card, emotion graph, and moodline on the website.
8. Add 6–10 public-domain films to `data/` and score them. Only process other subtitle files when their use is authorized.

---

## 8. Rules and constraints

- **Never commit secrets.** Keys live only in `.env` (gitignored). Read them with `python-dotenv`. If a key is ever committed, tell the team immediately so it can be revoked.
- **Never put `TIMESCALE_SERVICE_URL` in browser JS.** Anything shipped to the browser is public; DB queries run server-side only.
- **Use public-domain films** for the sample library (e.g. *His Girl Friday*, *Night of the Living Dead*, *Charade*) so the repo doesn't ship copyrighted subtitle text.
- **Free-tier limits:** Gemini free tier is rate limited per project; Tiger free plan allows 2 services per account. Design for that (batch, cache, don't re-score movies already in the DB).
- **Gemini free tier may use inputs to improve Google's models.** Only send public subtitle text, nothing private.
- Keep commits small and push often. Don't rewrite another teammate's folder without asking.

---

## 9. How to verify your work

- Gemini: `python test_gemini.py` prints a sentence.
- DB: `psql "$TIMESCALE_SERVICE_URL" -c "\dt"` lists `works` and `emotion_points`; `SELECT * FROM timescaledb_information.hypertables;` shows `emotion_points`.
- Pipeline: after scoring one movie, `SELECT count(*) FROM emotion_points WHERE work_id = …` ≈ runtime ÷ 2 minutes (minus silent windows).
- Website data: both reads return data matching Section 6.1.
- Website: cards show real films; emotion graph and moodline render for at least one film; filter chips reorder cards.

When you finish a step, update **Section 5 (Current state)** in this file so the next person or agent knows where things stand.
