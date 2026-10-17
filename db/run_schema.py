import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

url = (os.environ.get("TIGER_DB_URL")
       or os.environ.get("DATABASE_URL")
       or os.environ.get("SERVICE_URL"))

if url:
    conn = psycopg2.connect(url)
else:
    conn = psycopg2.connect(
        host=os.environ["PGHOST"],
        port=os.environ["PGPORT"],
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode="require",
    )

conn.autocommit = True
cur = conn.cursor()
cur.execute(open("db/schema.sql").read())
print("Schema created!")