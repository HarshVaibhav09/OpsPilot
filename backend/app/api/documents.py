import concurrent.futures

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from app.db.vector_store import vector_store
from app.models.schemas import (
    DocumentMetadata,
    FileJobStatus,
    JobStatusResponse,
    UploadJobResponse,
    UploadResponse,
)
from app.services.document_analysis_service import analyze_document, clear_document
from app.services.ingestion_service import ingest_document
from app.services.job_service import (
    JobStatus,
    create_job,
    finalize_job,
    get_job,
    mark_job_status,
    update_file_status,
)

router = APIRouter(prefix="/documents", tags=["documents"])

INGESTION_TIMEOUT_SECONDS = 180  # per-file ceiling, prevents one bad file hanging the batch


@router.post("/upload", response_model=UploadJobResponse)
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
):
    accepted = []
    rejected = []

    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            rejected.append(f"'{file.filename}' is not a PDF.")
            continue
        content = await file.read()
        accepted.append((file.filename, content))

    if not accepted:
        raise HTTPException(
            status_code=400,
            detail=rejected or ["No valid PDF uploaded."],
        )

    job_id = create_job([fname for fname, _ in accepted])
    background_tasks.add_task(_run_ingestion_job, job_id, accepted)

    return UploadJobResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        accepted_files=[fname for fname, _ in accepted],
        rejected_files=rejected,
    )


def _run_ingestion_job(job_id: str, files: list[tuple[str, bytes]]):
    mark_job_status(job_id, JobStatus.PROCESSING)

    for filename, content in files:
        update_file_status(job_id, filename, JobStatus.PROCESSING)
        try:
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(ingest_document, content, filename)
                result = future.result(timeout=INGESTION_TIMEOUT_SECONDS)

            chunks = result.pop("chunks")
            update_file_status(job_id, filename, JobStatus.COMPLETED, result=result)

        except concurrent.futures.TimeoutError:
            update_file_status(
                job_id, filename, JobStatus.FAILED,
                error=f"Processing '{filename}' took too long and was stopped.",
            )
            continue
        except ValueError as e:
            update_file_status(job_id, filename, JobStatus.FAILED, error=str(e))
            continue
        except Exception as e:
            update_file_status(
                job_id, filename, JobStatus.FAILED,
                error=f"Failed to process '{filename}': {e}",
            )
            continue

        # Contradiction analysis is a separate, non-critical step.
        # If it fails, the document stays marked as successfully ingested —
        # only the analysis itself is skipped.
        try:
            analyze_document(
                doc_id=result["doc_id"],
                filename=filename,
                chunks=chunks,
            )
        except Exception as e:
            print(f"Contradiction analysis failed for '{filename}': {e}")

    finalize_job(job_id)


@router.get("/upload/{job_id}/status", response_model=JobStatusResponse)
def get_upload_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    return JobStatusResponse(
        job_id=job["job_id"],
        status=job["status"],
        files=[
            FileJobStatus(
                filename=fname,
                status=info["status"],
                result=DocumentMetadata(**info["result"]) if info["result"] else None,
                error=info["error"],
            )
            for fname, info in job["files"].items()
        ],
    )


@router.get("", response_model=UploadResponse)
def list_documents():
    return UploadResponse(
        documents=[DocumentMetadata(**doc) for doc in vector_store.list_documents()]
    )


@router.delete("/{doc_id}")
def delete_document(doc_id: str):
    vector_store.delete_document(doc_id)
    clear_document(doc_id)
    return {"status": "deleted", "doc_id": doc_id}