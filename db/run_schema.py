import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

url = os.environ.get("TIMESCALE_SERVICE_URL")
conn = psycopg2.connect(url)

conn.autocommit = True
cur = conn.cursor()
cur.execute(open("db/schema.sql").read())
print("Schema created!")