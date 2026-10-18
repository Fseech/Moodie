#!/usr/bin/env python3
"""Serve Moodie locally and expose read-only endpoints for scored films."""

import json
import logging
import os
import re
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor


ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "website" / "index.html"
EMOTIONS = ("joy", "sadness", "fear", "anger", "tension", "surprise")
load_dotenv(ROOT / ".env")


def query_database(sql, params=()):
    database_url = os.environ.get("TIMESCALE_SERVICE_URL")
    if not database_url:
        raise RuntimeError("Set TIMESCALE_SERVICE_URL in the project .env file.")

    with closing(psycopg2.connect(database_url, connect_timeout=8)) as connection:
        connection.set_session(readonly=True)
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]


class MoodieHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = unquote(urlsplit(self.path).path)
        if path in ("/", "/index.html"):
            self.serve_index()
            return

        try:
            if path == "/api/films":
                self.serve_films()
                return

            points_match = re.fullmatch(r"/api/films/(\d+)/points", path)
            if points_match:
                self.serve_points(int(points_match.group(1)))
                return
        except (psycopg2.Error, RuntimeError):
            logging.exception("Moodie could not read film data from the database")
            self.send_json(
                503,
                {"error": "Movie data is unavailable. Check the local database configuration."},
            )
            return

        self.send_json(404, {"error": "Not found"})

    def serve_index(self):
        try:
            content = INDEX.read_bytes()
        except OSError:
            logging.exception("Could not read the Moodie page")
            self.send_json(500, {"error": "The Moodie page could not be loaded."})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def serve_films(self):
        rows = query_database(
            """
            SELECT w.work_id AS id, w.title, w.year, w.genre,
                   ROUND(w.runtime_ms / 60000.0)::integer AS runtime_min,
                   AVG(p.joy)::double precision AS joy,
                   AVG(p.sadness)::double precision AS sadness,
                   AVG(p.fear)::double precision AS fear,
                   AVG(p.anger)::double precision AS anger,
                   AVG(p.tension)::double precision AS tension,
                   AVG(p.surprise)::double precision AS surprise
            FROM works AS w
            JOIN emotion_points AS p USING (work_id)
            GROUP BY w.work_id
            ORDER BY w.title
            """
        )
        films = []
        for row in rows:
            films.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "year": row["year"],
                    "genre": row["genre"],
                    "runtime_min": row["runtime_min"],
                    "emotions": {key: row[key] for key in EMOTIONS},
                }
            )
        self.send_json(200, films)

    def serve_points(self, work_id):
        rows = query_database(
            """
            SELECT (EXTRACT(EPOCH FROM t) / 60.0)::double precision AS minute,
                   joy, sadness, fear, anger, tension, surprise, valence
            FROM emotion_points
            WHERE work_id = %s
            ORDER BY t
            """,
            (work_id,),
        )
        self.send_json(200, rows)

    def send_json(self, status, payload):
        content = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format_string, *args):
        logging.info("%s - %s", self.address_string(), format_string % args)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer(("127.0.0.1", 8000), MoodieHandler)
    print("Moodie is running at http://127.0.0.1:8000 (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Moodie.")
    finally:
        server.server_close()
