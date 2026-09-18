import asyncio
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from app.db.database import SessionLocal
from app.models.document import Document
from app.services.ai_service import LMStudioServiceError
from app.services.document_topic_service import generate_document_summary_stream


SummaryGenerator = Callable[[str], Any]


@dataclass
class SummaryJob:
    document_id: int
    status: str = "generating"
    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    error: Optional[str] = None
    events: list[dict] = field(default_factory=list)
    task: Optional[asyncio.Task] = None


_jobs: dict[int, SummaryJob] = {}
_jobs_lock = threading.Lock()
_background_tasks: set[asyncio.Task] = set()


def get_summary_job(document_id: int) -> Optional[SummaryJob]:
    with _jobs_lock:
        return _jobs.get(document_id)


def get_summary_job_state(document_id: int) -> Optional[dict]:
    with _jobs_lock:
        job = _jobs.get(document_id)

        if job is None:
            return None

        return {
            "status": job.status,
            "started_at": job.started_at,
            "error": job.error,
        }


def get_summary_job_snapshot(
    document_id: int,
    cursor: int = 0,
) -> tuple[list[dict], int, Optional[str]]:
    with _jobs_lock:
        job = _jobs.get(document_id)

        if job is None:
            return [], cursor, None

        events = list(job.events[cursor:])
        return events, len(job.events), job.status


def _publish(job: SummaryJob, event: str, data: dict) -> None:
    with _jobs_lock:
        job.events.append({"event": event, "data": data})


def _finish_job(
    job: SummaryJob,
    status: str,
    error: Optional[str] = None,
) -> None:
    with _jobs_lock:
        job.status = status
        job.error = error


def _run_summary_job(
    job: SummaryJob,
    document_text: str,
    summary_generator: SummaryGenerator,
) -> None:
    stream_db = SessionLocal()
    final_summary = None

    try:
        for stream_event in summary_generator(document_text):
            if stream_event["event"] == "complete":
                final_summary = stream_event["final_summary"]
                continue

            _publish(
                job,
                stream_event["event"],
                stream_event["data"],
            )

        if not final_summary or not final_summary.strip():
            raise LMStudioServiceError("LM Studio boş özet oluşturdu.")

        stream_document = (
            stream_db.query(Document)
            .filter(Document.id == job.document_id)
            .first()
        )

        if stream_document is None:
            raise ValueError("Document artık mevcut değil.")

        stream_document.summary = final_summary
        stream_db.commit()
        _publish(job, "done", {"status": "completed"})
        _finish_job(job, "completed")

    except Exception as error:
        stream_db.rollback()
        error_message = str(error) or error.__class__.__name__
        _publish(
            job,
            "error",
            {
                "status": "failed",
                "message": "Özet oluşturulurken bir hata oluştu. Tekrar deneyebilirsiniz.",
            },
        )
        _finish_job(job, "failed", error_message)

    finally:
        stream_db.close()


def ensure_summary_job(
    document_id: int,
    document_text: str,
    summary_generator: Optional[SummaryGenerator] = None,
) -> tuple[SummaryJob, bool]:
    """Atomically return the active job or start one detached from the client."""
    with _jobs_lock:
        existing_job = _jobs.get(document_id)

        if existing_job is not None and existing_job.status in {
            "generating",
            "completed",
        }:
            return existing_job, False

        job = SummaryJob(document_id=document_id)
        _jobs[document_id] = job

    if summary_generator is None:
        summary_generator = generate_document_summary_stream

    task = asyncio.create_task(
        asyncio.to_thread(
            _run_summary_job,
            job,
            document_text,
            summary_generator,
        )
    )
    job.task = task
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return job, True


def clear_summary_jobs() -> None:
    """Clear completed test/process state; running threads are not cancelled."""
    with _jobs_lock:
        _jobs.clear()
