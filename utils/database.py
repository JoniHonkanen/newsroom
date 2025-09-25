# utils/database.py
import asyncpg
import psycopg
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Database connection pool (GraphQL:lle)
db_pool = None


async def get_db_pool():
    """Get or create database connection pool (GraphQL)"""
    global db_pool
    if db_pool is None:
        try:
            db_pool = await asyncpg.create_pool(
                host=os.getenv("DB_HOST"),
                port=int(os.getenv("DB_PORT", 5432)),
                database=os.getenv("DB_NAME"),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                min_size=1,
                max_size=10,
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create database pool: {e}")
            raise
    return db_pool


async def close_db_pool():
    """Close database connection pool"""
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None
        logger.info("Database connection pool closed")


async def get_db_connection():
    """Simple connection for API routes (psycopg)"""
    DATABASE_URL = os.getenv("DATABASE_URL")
    return await psycopg.AsyncConnection.connect(DATABASE_URL)
