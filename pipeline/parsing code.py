#!/usr/bin/env python3
"""Score one movie's subtitles with Gemini and load them into Tiger Data.

Groups subtitle lines into 2-minute windows, asks Gemini for valence + six
five emotions per window (gemini_schema.json), and writes works + emotion_points
(db/schema.sql). Based on Niki's pipeline/parsing code.py.

Reads GEMINI_API_KEY and TIMESCALE_SERVICE_URL from .env.
Run from the repo root, e.g.

Try a small run first (no database writes):
    python pipeline/score_movie.py data/his_girl_friday.srt --title "His Girl Friday" --limit 5 --no-db

Then the full film (year and genre are required; resumes automatically if it stops):
    python pipeline/score_movie.py data/his_girl_friday.srt --title "His Girl Friday" --year 1940 --genre Comedy
"""
import argparse, json, os, re, sys, time
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")
FIELDS = ["valence", "joy", "sadness", "fear", "anger", "surprise"]
DEFAULT_MODEL = "gemini-3.5-flash"


def ms(h, m, s, frac):
    # Fractions may have 1-3 digits ("01,95" is 950 ms, not 95 ms).
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + round(int(frac) / 10 ** len(frac) * 1000)


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
        cues.append({"start": ms(*g[:4]), "end": ms(*g[4:]), "text": text})
    return cues


def make_windows(cues, window_ms):
    """Group cues by window start. Windows with no dialogue are skipped."""
    windows = {}
    for c in cues:
        start = c["start"] // window_ms * window_ms
        windows.setdefault(start, []).append(c["text"])
    return [{"idx": i, "start_ms": s, "text": " ".join(t)} for i, (s, t) in enumerate(sorted(windows.items()))]


def build_prompt(title, batch, window_min):
    blocks = "\n\n".join(f"[window {w['idx']}, minute {w['start_ms'] // 60000}]\n{w['text']}" for w in batch)
    return f"""You are scoring the emotional arc of the film "{title}" from its subtitles.
Each window below is {window_min} minutes of dialogue. The subtitles may be auto-transcribed and noisy;
judge the overall emotional content of the scene, including sarcasm and banter.

For each window return:
- valence: -1 (very dark/negative) to 1 (very warm/positive), 0 neutral
- joy, sadness, fear, anger, surprise: each 0 (absent) to 1 (very strong), scored independently

Return one object per window, echoing its number as window_idx.

{blocks}"""


def score_batch(client, types, model, schema, title, batch, window_min, tries=4):
    want = {w["idx"] for w in batch}
    best = {}
    for t in range(tries):
        try:
            r = client.models.generate_content(
                model=model,
                contents=build_prompt(title, batch, window_min),
                config=types.GenerateContentConfig(
                    temperature=0,
                    response_mime_type="application/json",
                    response_json_schema=schema,
                ),
            )
            out = {}
            for row in json.loads(r.text)["windows"]:
                if row.get("window_idx") in want:
                    out[row["window_idx"]] = {
                        f: max(-1.0 if f == "valence" else 0.0, min(1.0, float(row[f]))) for f in FIELDS
                    }
            if len(out) > len(best):
                best = out
            if set(out) == want:
                return out
        except Exception as e:  # network, quota (429), bad JSON: wait and retry
            print(f"  retry {t + 1}: {e}", file=sys.stderr)
            time.sleep(5 * (t + 1))
    return best


def load_db(title, year, genre, runtime_ms, window_ms, windows, scores):
    import psycopg2

    rows = [(w["start_ms"], *(scores[str(w["idx"])][f] for f in FIELDS)) for w in windows if str(w["idx"]) in scores]
    with psycopg2.connect(os.environ["TIMESCALE_SERVICE_URL"]) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO works (title, year, genre, runtime_ms) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (title) DO UPDATE SET year = EXCLUDED.year, genre = EXCLUDED.genre, "
            "runtime_ms = EXCLUDED.runtime_ms RETURNING work_id",
            (title, year, genre, runtime_ms),
        )
        work_id = cur.fetchone()[0]
        cur.execute("DELETE FROM emotion_points WHERE work_id = %s", (work_id,))
        cur.executemany(
            "INSERT INTO emotion_points (work_id, t, valence, joy, sadness, fear, anger, surprise) "
            "VALUES (%s, '1970-01-01'::timestamptz + %s * interval '1 millisecond', %s, %s, %s, %s, %s, %s)",
            [(work_id, *r) for r in rows],
        )
    print(f"loaded {title} (work_id {work_id}): {len(rows)} windows into Tiger Data")


def main():
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser()
    ap.add_argument("srt")
    ap.add_argument("--title", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--genre", required=True)
    ap.add_argument("--window-min", type=int, default=2)
    ap.add_argument("--batch", type=int, default=10, help="windows per Gemini request")
    ap.add_argument("--limit", type=int, default=0, help="only score the first N windows (for testing)")
    ap.add_argument("--out", help="scores JSON path (default pipeline/scored/<srt name>.json)")
    ap.add_argument("--no-db", action="store_true")
    a = ap.parse_args()

    cues = parse_srt(a.srt)
    if not cues:
        sys.exit("No cues found. Is this a valid .srt file?")
    window_ms = a.window_min * 60000
    runtime_ms = cues[-1]["end"]
    windows = make_windows(cues, window_ms)
    if a.limit:
        windows = windows[: a.limit]
    print(f"parsed {len(cues)} cues into {len(windows)} windows, film ends at ~{runtime_ms / 60000:.0f} min")

    out = Path(a.out or ROOT / "pipeline" / "scored" / f"{Path(a.srt).stem}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    done = json.loads(out.read_text()) if out.exists() else {}  # resume: str(idx) -> scores
    todo = [w for w in windows if str(w["idx"]) not in done]

    if todo:
        from google import genai
        from google.genai import types

        schema = json.loads((ROOT / "gemini_schema.json").read_text())
        model = os.environ.get("GEMINI_MODEL") or DEFAULT_MODEL
        client = genai.Client()  # reads GEMINI_API_KEY
        for s in range(0, len(todo), a.batch):
            batch = todo[s : s + a.batch]
            res = score_batch(client, types, model, schema, a.title, batch, a.window_min)
            for idx, sc in res.items():
                done[str(idx)] = sc
            out.write_text(json.dumps(done, indent=1))  # save after every batch
            print(f"  scored {len(res)}/{len(batch)} windows in batch, {len(done)}/{len(windows)} total")
            time.sleep(2)

    missing = [w["idx"] for w in windows if str(w["idx"]) not in done]
    if missing:
        print(f"warning: {len(missing)} windows not scored yet; run again to retry them")
    scored = [done[str(w["idx"])] for w in windows if str(w["idx"]) in done]
    if scored:
        print("averages: " + ", ".join(f"{f} {sum(s[f] for s in scored) / len(scored):+.2f}" for f in FIELDS))
    print(f"saved to {out}")

    if not a.no_db:
        load_db(a.title, a.year, a.genre, runtime_ms, window_ms, windows, done)


if __name__ == "__main__":
    main()