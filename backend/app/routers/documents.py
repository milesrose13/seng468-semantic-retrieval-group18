import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import queue, storage, vector
from ..database import get_db
from ..dependencies import get_current_user
from ..models.document import Document, DocumentStatus
from ..models.user import User
from ..schemas.document import DocumentResponse

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", status_code=202)
async def upload_document(
    file: UploadFile,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    doc_id = uuid.uuid4()
    storage_key = f"user{current_user.id}/{doc_id}.pdf"

    file_bytes = await file.read()
    storage.upload_file(file_bytes, storage_key)

    doc = Document(
        id=doc_id,
        user_id=current_user.id,
        filename=file.filename,
        storage_key=storage_key,
        status=DocumentStatus.PROCESSING,
    )
    db.add(doc)
    db.commit()

    try:
        queue.publish_job(str(doc_id), storage_key, current_user.id)
    except Exception as e:
        doc.status = DocumentStatus.ERROR
        db.commit()
        raise HTTPException(
            status_code=500, detail="Failed to enqueue processing job"
        ) from e

    return {
        "message": "PDF uploaded, processing started",
        "document_id": str(doc_id),
        "status": "processing",
    }


@router.get("", response_model=list[DocumentResponse])
async def list_documents(
    db: Session = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    docs = db.query(Document).filter(Document.user_id == current_user.id).all()
    return [
        DocumentResponse(
            document_id=doc.id,
            filename=doc.filename,
            upload_date=doc.upload_date,
            status=doc.status if doc.status else "processing",
            page_count=doc.page_count,
        )
        for doc in docs
    ]


@router.delete("/{document_id}", status_code=200)
async def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
):
    doc = (
        db.query(Document)
        .filter(Document.id == document_id, Document.user_id == current_user.id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    storage.delete_file(doc.storage_key)
    vector.delete_embeddings(str(document_id))

    db.delete(doc)
    db.commit()

    return {"message": "Document deleted"}
