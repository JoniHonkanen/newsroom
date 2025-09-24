# api/utils/database.py
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

async def get_db_connection():
    """Get database connection"""
    DATABASE_URL = os.getenv("DATABASE_URL")
    return await psycopg.AsyncConnection.connect(DATABASE_URL)