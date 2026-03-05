from fastapi import FastAPI

from .routers import documents

app = FastAPI(
    title="Semantic Retrieval Group 18 API",
    description="Semantic Retrieval Group 18 API",
    version="1.0.0",
)

# TO DO: Add middle ware

app.include_router(documents.router)


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
