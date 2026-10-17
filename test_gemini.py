"""One-shot check that the Gemini key in .env works. Run: python test_gemini.py"""
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
response = client.models.generate_content(
    model="gemini-3.5-flash",
    contents="In one sentence, describe the emotional tone of this line: "
    "\"They're coming to get you, Barbara.\"",
)
print(response.text)
