from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# This is what the user gets when they call GET /documents
class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    document_id: UUID
    filename: str
    upload_date: datetime  # Requirement: ISO timestamp
    status: str  # Values: "processing", "ready", "error"
    page_count: int | None  # Requirement: null while processing


# This is used internally to create the DB record
class DocumentInternalCreate(BaseModel):
    user_id: UUID  # For user isolation
    filename: str
    minio_path: str  # Internal path not exposed to the user
