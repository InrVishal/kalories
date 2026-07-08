import logging
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings

logger = logging.getLogger("kalories.db")

db = None
client = None

async def init_db():
    global db, client
    try:
        client = AsyncIOMotorClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=2000,
            maxPoolSize=100,
            minPoolSize=10,
            retryWrites=True
        )
        # Try to ping the database to check if MongoDB is alive
        await client.admin.command('ping')
        db = client.get_default_database()
        logger.info("✅ MongoDB connected successfully!")
        
        # Create database indexes
        await db.scan_results.create_index("scan_id", unique=True)
        await db.model_runs.create_index("scan_id", unique=True)
        await db.scans.create_index("user_id")
        await db.users.create_index("username", unique=True)
        logger.info("✅ MongoDB indexes created successfully!")
    except Exception as e:
        logger.error(f"❌ Failed to connect to MongoDB: {e}. Falling back to in-memory mocks.")
        db = None

async def close_db():
    global client, db
    if client is not None:
        try:
            client.close()
            logger.info("MongoDB connection closed.")
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {e}")
        client = None
        db = None

@asynccontextmanager
async def transaction_session():
    """
    Context manager to wrap database operations in a transaction session.
    Yields the session object if MongoDB client is available, otherwise yields None.
    """
    global client
    if client is None:
        yield None
        return
    async with await client.start_session() as session:
        async with session.start_transaction():
            yield session
