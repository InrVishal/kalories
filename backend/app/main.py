import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.core.config import settings
from app.core.db import init_db
from app.routers.scans import router as scans_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("kalories.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up FastAPI application...")
    await init_db()
    yield
    logger.info("Shutting down FastAPI application...")

app = FastAPI(
    title="Kalories API",
    description="Multi-model calorie estimation and food portion size backend.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scans_router)

@app.get("/health")
async def health_check():
    return {"status": "ok", "version": "1.0.0"}

# Serve the HTML dashboard at root
# Use the CWD (we always run from backend/) or fall back to __file__-relative
_static_dir = os.path.abspath(os.path.join(os.getcwd(), "static"))
if not os.path.isdir(_static_dir):
    _static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
logger.info(f"Static directory resolved to: {_static_dir} (exists={os.path.isdir(_static_dir)})")

@app.get("/", response_class=FileResponse)
async def serve_dashboard():
    index = os.path.join(_static_dir, "index.html")
    if not os.path.isfile(index):
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": f"index.html not found at {index}"}, status_code=404)
    return FileResponse(index)

# Mount static assets
if os.path.isdir(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

