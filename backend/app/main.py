import logging
import os
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from app.core.config import settings
from app.core.db import init_db, db, close_db
from app.routers.scans import router as scans_router
from app.routers.auth import router as auth_router
from app.services.nutrition import init_redis, close_redis

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage()
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("kalories.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure JSON logging in production
    if settings.ENVIRONMENT == "production":
        json_formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            handler.setFormatter(json_formatter)
            
    logger.info("Starting up FastAPI application...")
    await init_db()
    await init_redis()
    yield
    logger.info("Shutting down FastAPI application...")
    await close_redis()
    await close_db()

app = FastAPI(
    title="Kalories API",
    description="Multi-model calorie estimation and food portion size backend.",
    version="1.0.0",
    lifespan=lifespan
)

# Secure Headers Middleware
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # Content Security Policy including standard CDNs for Three.js, fonts, CSS and local hosts
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 http://localhost:3000 http://localhost:11434;"
    )
    response.headers["Content-Security-Policy"] = csp
    return response

# CORS policies configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 5MB

@app.middleware("http")
async def limit_upload_size(request: Request, call_next):
    if request.method == "POST":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_UPLOAD_SIZE:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "File size exceeds the 5MB limit"}
                    )
            except ValueError:
                pass
    return await call_next(request)

app.include_router(auth_router)
app.include_router(scans_router)

@app.get("/health/live")
async def health_live():
    return {"status": "alive", "version": "1.0.0"}

@app.get("/health/ready")
async def health_ready():
    mongo_ok = False
    if db is not None:
        try:
            await db.command("ping")
            mongo_ok = True
        except Exception as e:
            logger.error(f"Readiness check failed for MongoDB: {e}")
    
    redis_ok = False
    from app.services.nutrition import redis_client
    if redis_client is not None:
        try:
            await redis_client.ping()
            redis_ok = True
        except Exception as e:
            logger.error(f"Readiness check failed for Redis: {e}")
            
    if not mongo_ok or not redis_ok:
        errors = []
        if not mongo_ok:
            errors.append("MongoDB offline")
        if not redis_ok:
            errors.append("Redis offline")
        
        if settings.ENVIRONMENT == "production":
            return JSONResponse(
                status_code=503,
                content={"status": "error", "errors": errors}
            )
        else:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "degraded",
                    "errors": errors,
                    "version": "1.0.0"
                }
            )
            
    return {"status": "ok", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    return await health_ready()

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

