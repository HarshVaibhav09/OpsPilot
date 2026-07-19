import time
import uuid
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


_jobs: dict[str, dict] = {}


def create_job(filenames: list[str]) -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "job_id": job_id,
        "status": JobStatus.PENDING,
        "created_at": time.time(),
        "files": {
            fname: {"status": JobStatus.PENDING, "result": None, "error": None}
            for fname in filenames
        },
    }
    return job_id


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def mark_job_status(job_id: str, status: JobStatus):
    job = _jobs.get(job_id)
    if job:
        job["status"] = status


def update_file_status(
    job_id: str,
    filename: str,
    status: JobStatus,
    result: dict | None = None,
    error: str | None = None,
):
    job = _jobs.get(job_id)
    if not job or filename not in job["files"]:
        return
    job["files"][filename]["status"] = status
    if result is not None:
        job["files"][filename]["result"] = result
    if error is not None:
        job["files"][filename]["error"] = error


def finalize_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        return
    statuses = [f["status"] for f in job["files"].values()]
    job["status"] = (
        JobStatus.COMPLETED
        if all(s in (JobStatus.COMPLETED, JobStatus.FAILED) for s in statuses)
        else JobStatus.PROCESSING
    )