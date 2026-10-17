#!/usr/bin/env python3
"""Score one movie's subtitles with Gemini and load them into Tiger Data (Postgres).
Setup:
pip install google-genai "psycopg[binary]"
export GEMINI_API_KEY=... # never commit this
export GEMINI_MODEL=... # a model name from Google's current docs
export DATABASE_URL=... # connection string from your Tiger Data service
Try a small run first:
python score_movie.py his_girl_friday.asr.srt --id his_girl_friday \
--title "His Girl Friday" --limit 60 --no-db
Then the full film (resumes automatically if it stops):
python score_movie.py his_girl_friday.asr.srt --id his_girl_friday --title "His Girl Friday"
"""
import argparse, json, os, re, sys, time
from pathlib import Path
TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")
EMOTIONS = ["joy", "humor", "love", "sadness", "fear", "anger", "tension", "neutral"]
SCHEMA = """
CREATE TABLE IF NOT EXISTS movies (
id text PRIMARY KEY, title text NOT NULL, runtime_sec real);
CREATE TABLE IF NOT EXISTS cues (
movie_id text REFERENCES movies(id), idx int, start_sec real, end_sec real,
text text, score real, emotion text, PRIMARY KEY (movie_id, idx));
"""

def secs(h, m, s, ms):
return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000

def parse_srt(path):
raw = Path(path).read_text(encoding="utf-8", errors="replace").replace("\r", "")
cues = []
for block in re.split(r"\n\s*\n", raw):
lines = block.strip().split("\n")
k = next((i for i, l in enumerate(lines) if "-->" in l), None)
if k is None:
continue
m = TS.search(lines[k])
if not m:
continue
text = re.sub(r"<[^>]+>|\{[^}]*\}", "", " ".join(lines[k + 1:])).strip()
if not text:
continue
g = m.groups()
cues.append({"idx": len(cues), "start": secs(*g[:4]), "end": secs(*g[4:]), "text": text})
return cues

def build_prompt(title, context, batch):
ctx = "\n".join(f"- {c['text']}" for c in context) or "(start of film)"
lines = "\n".join(f"{c['idx']}: {c['text']}" for c in batch)

return f"""You are scoring the emotional tone of subtitle lines from the film "{title}".
Score each line from -1.0 (very negative or dark) to 1.0 (very positive or warm), judging what is
actually being expressed in context, including sarcasm and banter. 0 means neutral.
Pick one emotion for each line from: {", ".join(EMOTIONS)}.
Earlier lines for context only (do NOT score these):
{ctx}
Lines to score (format "id: text"):
{lines}
Return ONLY a JSON array with exactly one object per id, like:
[{{"i": 12, "score": -0.4, "emotion": "tension"}}]"""

def score_batch(client, types, model, title, context, batch, tries=3):
want = {c["idx"] for c in batch}
best = {}
for t in range(tries):
try:
r = client.models.generate_content(
model=model,
contents=build_prompt(title, context, batch),
config=types.GenerateContentConfig(temperature=0,

response_mime_type="application/json"),
)
out = {}
for row in json.loads(r.text):
if row.get("i") in want:
out[row["i"]] = {
"score": max(-1.0, min(1.0, float(row["score"]))),
"emotion": row.get("emotion") if row.get("emotion") in EMOTIONS else "neutral",
}
if len(out) > len(best):
best = out
if set(out) == want:
return out
except Exception as e: # network, quota, bad JSON: wait and retry
print(f" retry {t + 1}: {e}", file=sys.stderr)
time.sleep(2 * (t + 1))
return best

def load_db(movie_id, title, cues):
import psycopg
rows = [(movie_id, c["idx"], c["start"], c["end"], c["text"], c["score"], c["emotion"]) for c in cues]
with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
cur.execute(SCHEMA)
cur.execute(
"INSERT INTO movies(id, title, runtime_sec) VALUES (%s, %s, %s) "
"ON CONFLICT (id) DO UPDATE SET title = EXCLUDED.title, runtime_sec =
EXCLUDED.runtime_sec",
(movie_id, title, cues[-1]["end"]),
)
cur.execute("DELETE FROM cues WHERE movie_id = %s", (movie_id,))
cur.executemany(
"INSERT INTO cues(movie_id, idx, start_sec, end_sec, text, score, emotion) "

"VALUES (%s, %s, %s, %s, %s, %s, %s)",
rows,
)
print(f"loaded {len(rows)} cues into Tiger Data")

def main():
ap = argparse.ArgumentParser()
ap.add_argument("srt")
ap.add_argument("--id", required=True, help="short slug, e.g. his_girl_friday")
ap.add_argument("--title", required=True)
ap.add_argument("--out", help="scored JSON path (default <id>_scored.json)")
ap.add_argument("--batch", type=int, default=60)
ap.add_argument("--limit", type=int, default=0, help="only score the first N cues (for testing)")
ap.add_argument("--no-db", action="store_true")
a = ap.parse_args()
cues = parse_srt(a.srt)
if not cues:
sys.exit("No cues found. Is this a valid .srt file?")
if a.limit:
cues = cues[: a.limit]
print(f"parsed {len(cues)} cues, last one ends at ~{cues[-1]['end'] / 60:.0f} min")
out = Path(a.out or f"{a.id}_scored.json")
done = json.loads(out.read_text()) if out.exists() else {} # resume: str(idx) -> result
todo = [c for c in cues if str(c["idx"]) not in done]
if todo:
from google import genai
from google.genai import types
model = os.environ.get("GEMINI_MODEL") or sys.exit("Set GEMINI_MODEL (see
Google's docs)")
client = genai.Client() # reads GEMINI_API_KEY
for s in range(0, len(cues), a.batch):
batch = cues[s : s + a.batch]
if all(str(c["idx"]) in done for c in batch):
continue
res = score_batch(client, types, model, a.title, cues[max(0, s - 3) : s], batch)
for c in batch:
done[str(c["idx"])] = res.get(c["idx"], {"score": 0.0, "emotion": "unscored"})
out.write_text(json.dumps(done)) # save after every batch
print(f" scored {min(s + a.batch, len(cues))}/{len(cues)}")
time.sleep(1)
for c in cues:
r = done[str(c["idx"])]
c["score"], c["emotion"] = r["score"], r["emotion"]
missing = sum(c["emotion"] == "unscored" for c in cues)
if missing:
print(f"warning: {missing} cues could not be scored (stored as 0.0, 'unscored')")
avg = sum(c["score"] for c in cues) / len(cues)
print(f"average score {avg:+.2f}; saved to {out}")
if not a.no_db:
load_db(a.id, a.title, cues)

if __name__ == "__main__":
main()