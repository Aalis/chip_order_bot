import psycopg
from dotenv import load_dotenv
import os

load_dotenv()

try:
    conn = psycopg.connect(
        f"postgresql://postgres:postgres@127.0.0.1:5432/tg"
    )
    print("Connection successful!")
    conn.close()
except Exception as e:
    print(f"Error: {e}") 