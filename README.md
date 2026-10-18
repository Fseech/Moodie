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

From the `Swamphacks` directory, run the commands for the films you want to
score and load into Tiger Data:

```powershell
py -3 "pipeline\parsing code.py" "data\his_girl_friday.srt" --title "His Girl Friday" --year 1940 --genre Comedy
py -3 "pipeline\parsing code.py" "data\Midnight_Manhunt.asr.srt" --title "Midnight Manhunt"
py -3 "pipeline\parsing code.py" "data\OutpostInMorocco.asr.srt" --title "Outpost in Morocco"
```

These commands send subtitle text to Gemini and use API quota. Refresh the
website after a scoring command finishes to see the movie and its scores.

What it does
Emotional arcs: turns a movie's subtitles into a minute-by-minute mood curve.
Scene explanations: hover a dip or peak to see the dialogue behind it and why it scored that way.
Browse by mood: rows of films like "Starts sad, ends happy" and "Edge of your seat."
Draw a curve: sketch a story shape and find films that match it.
Compare films: overlay two arcs on one chart.
