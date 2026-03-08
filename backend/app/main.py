from contextlib import asynccontextmanager

from fastapi import FastAPI

from . import storage
from .routers import documents, search


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

# TO DO: Add middle ware

app.include_router(documents.router)
app.include_router(search.router)


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
