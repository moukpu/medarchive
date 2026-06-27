import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = "postgresql+asyncpg://postgres:QfFRwrfTrHHrDcaSGMoGypwMISyYNPFW@reseau.proxy.rlwy.net:21362/railway"

async def clear_db():
    engine = create_async_engine(DATABASE_URL)
    async with engine.begin() as conn:
        # Drop all tables in public schema
        await conn.execute(text("DROP SCHEMA public CASCADE;"))
        await conn.execute(text("CREATE SCHEMA public;"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    print("Database cleared successfully.")
    
if __name__ == "__main__":
    asyncio.run(clear_db())
