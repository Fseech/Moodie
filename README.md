#Moodie
Find a movie by the ride it takes you on.

Moodie reads a film's subtitles, scores the emotional tone of every minute with Gemini, and draws the result as an emotional arc. You can browse films by mood, see exactly where a story falls apart or lifts off, and (soon) draw the shape of the story you want to feel and get matching movies.

Built at SwampHacks by Faatimah Seecharan, Juhi Shah, Kaylee Rodriguez, and Niki Lin.

## Run the website locally

The website reads scored films from Tiger Data through a small read-only Python
server. The database connection string stays on the server and is loaded from
the project-root `.env` file; it is never sent to the browser.

Install the website's Python dependencies and start the server from the
`Swamphacks` project directory:

```powershell
py -3 -m pip install -r requirements.txt
py -3 website\server.py
```

Open <http://127.0.0.1:8000>. The database must have the schema from
`db/schema.sql` and at least one film with scored rows in `emotion_points`.
If no films have been scored yet, the page shows an empty state. Scoring runs
separately through the Gemini pipeline and may use API quota.

Movie poster URLs and source credits are configured in `website/posters.json`.
Local JPG posters can be placed in `movie_images/` and referenced with a
`/movie_images/<filename>.jpg` URL; the website server serves files from that
folder. Only add artwork that is public domain, openly licensed, user-provided,
or otherwise cleared for use. Include source URLs and credits for externally
hosted art. Restart the website server after changing the poster configuration
or server code. Movies without a configured or loadable poster keep the
existing gradient card header.

The page uses the self-hosted Outfit variable font in `website/fonts/`, licensed
under the SIL Open Font License 1.1; its license is included alongside the font.

From the `Swamphacks` directory, run the commands for the films you want to
score and load into Tiger Data:

```powershell
py -3 "pipeline\parsing code.py" "data\his_girl_friday.srt" --title "His Girl Friday" --year 1940 --genre Comedy
py -3 "pipeline\parsing code.py" "data\Midnight_Manhunt.asr.srt" --title "Midnight Manhunt" --year 1945 --genre Mystery
py -3 "pipeline\parsing code.py" "data\OutpostInMorocco.asr.srt" --title "Outpost in Morocco" --year 1949 --genre "Action / Adventure"
py -3 "pipeline\parsing code.py" "data\little_princess.asr.srt" --title "The Little Princess" --year 1939 --genre Drama
py -3 "pipeline\parsing code.py" "data\royal_wedding.asr.srt" --title "Royal Wedding" --year 1951 --genre "Musical Comedy"
py -3 "pipeline\parsing code.py" "data\Avengers Endgame 2019 NEW 720p HDCAM x264-iMaX.srt" --title "Avengers: Endgame" --year 2019 --genre "Action / Science Fiction"
py -3 "pipeline\parsing code.py" "data\Fight.Club.1999.1080p.BluRay.x264.srt" --title "Fight Club" --year 1999 --genre "Drama / Thriller"
py -3 "pipeline\parsing code.py" "data\Forrest Gump ;[1994];[1080p BDremux];[Shadowl0rd].ENG.srt" --title "Forrest Gump" --year 1994 --genre "Drama / Romance"
py -3 "pipeline\parsing code.py" "data\Inside.Out.2.2024.1080p.WEB-DL.DDP5.1.Atmos.H.srt" --title "Inside Out 2" --year 2024 --genre "Animation / Comedy"
py -3 "pipeline\parsing code.py" "data\Interstellar.2014.720p.BluRay.x264-DAA.srt" --title "Interstellar" --year 2014 --genre "Science Fiction / Drama"
```

These commands send subtitle text to Gemini and use API quota. Refresh the
website after a scoring command finishes to see the movie and its scores.
Existing databases need the one-time schema migration in
`db/migrate_remove_tension.sql` before scoring against the updated schema.

All ten subtitle-backed films are scored and loaded into the database. The five
recently added titles are Avengers: Endgame, Fight Club, Forrest Gump, Inside
Out 2, and Interstellar. Scored windows are cached in `pipeline/scored/` so
interrupted jobs can resume. The latest batch used Gemini's
`gemini-3.5-flash-lite` model because the default model was quota-limited.

What it does
Emotional arcs: turns a movie's subtitles into a minute-by-minute mood curve.
Scene explanations: hover a dip or peak to see the dialogue behind it and why it scored that way.
Browse by mood: rows of films like "Starts sad, ends happy" and "Edge of your seat."
Draw a curve: sketch a story shape and find films that match it.
Compare films: overlay two arcs on one chart.
