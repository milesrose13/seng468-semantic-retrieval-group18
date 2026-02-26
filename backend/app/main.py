from fastapi import FastAPI

from backend.app.database import Base, engine

app = FastAPI(
    title="Semantic Retrieval Group 18 API",
    description="Semantic Retrieval Group 18 API",
    version="1.0.0",
)

# TO DO: Add middle ware

# TO DO: Include routers using app.include_router(router)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


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
