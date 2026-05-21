import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

logger = logging.getLogger("kalories.db")

db = None
client = None

async def init_db():
    global db, client
    try:
        client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=2000)
        # Try to ping the database to check if MongoDB is alive
        await client.admin.command('ping')
        db = client.get_default_database()
        logger.info("✅ MongoDB connected successfully!")
    except Exception as e:
        logger.error(f"❌ Failed to connect to MongoDB: {e}. Falling back to in-memory mocks.")
        db = None
