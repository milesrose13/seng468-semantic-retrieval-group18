import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import storage
from .config import settings
from .routers import auth, documents, search

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage.ensure_bucket_exists()
    yield


app = FastAPI(
    title="Semantic Retrieval Group 18 API",
    description="Semantic Retrieval Group 18 API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
origins = (
    ["*"]
    if settings.CORS_ORIGINS == "*"
    else [o.strip() for o in settings.CORS_ORIGINS.split(",")]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler for unhandled errors
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error"},
    )


app.include_router(documents.router)
app.include_router(search.router)
app.include_router(auth.router)


@app.get("/")
async def root():
    return {
        "message": "Welcome",
        "docs": "/docs",
        "version": "1.0.0",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
