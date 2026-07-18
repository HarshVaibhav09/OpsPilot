from fastapi import APIRouter, File, HTTPException, UploadFile

from app.db.vector_store import vector_store
from app.models.schemas import (
    DocumentMetadata,
    UploadResponse,
)
from app.services.document_analysis_service import clear_document
from app.services.ingestion_service import ingest_document

router = APIRouter(
    prefix="/documents",
    tags=["documents"],
)


@router.post(
    "/upload",
    response_model=UploadResponse,
)
async def upload_documents(
    files: list[UploadFile] = File(...),
):

    documents = []
    errors = []

    for file in files:

        if not file.filename.lower().endswith(".pdf"):
            errors.append(f"'{file.filename}' is not a PDF.")
            continue

        try:
            result = ingest_document(
                await file.read(),
                file.filename,
            )

            documents.append(
                DocumentMetadata(**result)
            )

        except ValueError as e:
            errors.append(str(e))

        except Exception as e:
            errors.append(
                f"Failed to process '{file.filename}': {e}"
            )

    if not documents:
        raise HTTPException(
            status_code=400,
            detail=errors or ["No valid PDF uploaded."],
        )

    return UploadResponse(
        documents=documents,
    )


@router.get(
    "",
    response_model=UploadResponse,
)
def list_documents():

    return UploadResponse(
        documents=[
            DocumentMetadata(**doc)
            for doc in vector_store.list_documents()
        ]
    )


@router.delete("/{doc_id}")
def delete_document(doc_id: str):

    vector_store.delete_document(doc_id)
    clear_document(doc_id)

    return {
        "status": "deleted",
        "doc_id": doc_id,
    }