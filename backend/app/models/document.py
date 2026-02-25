import enum
import uuid
from datetime import datetime

from app.database import Base
from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID


class DocumentStatus(str, enum.Enum):
    PROCESSING = "processing"
    READY = "ready"
    ERROR = "error"


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # FK from user table
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    filename = Column(String(255), nullable=False)
    upload_date = Column(DateTime, default=datetime.now)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PROCESSING)
    page_count = Column(Integer, nullable=True)  # Populated later by worker

    # The path where the file lives in MinIO (e.g., "user1/doc-uuid.pdf")
    storage_key = Column(String(512), nullable=False)
