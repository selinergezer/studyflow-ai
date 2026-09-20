import asyncio
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from app.db.database import SessionLocal
from app.models.document import Document
from app.services.ai_service import LMStudioServiceError
from app.services.document_topic_service import generate_document_summary_stream


logger = logging.getLogger(__name__)
SummaryGenerator = Callable[[str], Any]
SUMMARY_JOB_STALL_WARNING_SECONDS = 90.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class SummaryJob:
    document_id: int
    status: str = "generating"
    started_at: datetime = field(
        default_factory=_utc_now
    )
    last_activity_at: datetime = field(default_factory=_utc_now)
    last_event: Optional[str] = None
    completed_chunks: int = 0
    stall_warning_logged: bool = False
    error: Optional[str] = None
    events: list[dict] = field(default_factory=list)
    task: Optional[asyncio.Task] = None


_jobs: dict[int, SummaryJob] = {}
_jobs_lock = threading.Lock()
_background_tasks: set[asyncio.Task] = set()


def _reconcile_generating_job_locked(job: SummaryJob) -> bool:
    """Return whether a generating job still has a live asyncio task."""
    if job.status != "generating":
        return False

    task = job.task
    stale_reason = None

    if task is None:
        stale_reason = "Background summary task was not created."
    elif task.cancelled():
        stale_reason = "Background summary task was cancelled."
    elif task.done():
        task_error = task.exception()
        stale_reason = (
            f"Background summary task crashed: {task_error}"
            if task_error is not None
            else "Background summary task ended before updating job status."
        )

    if stale_reason is None:
        inactive_for = (_utc_now() - job.last_activity_at).total_seconds()

        if (
            inactive_for >= SUMMARY_JOB_STALL_WARNING_SECONDS
            and not job.stall_warning_logged
        ):
            job.stall_warning_logged = True
            logger.warning(
                "Summary job has no recent activity but task is still live: "
                "document_id=%s inactive_seconds=%.1f last_event=%s",
                job.document_id,
                inactive_for,
                job.last_event,
            )

        # A live but quiet task is never replaced here. The bounded LM/queue
        # timeouts must let its worker exit before a retry can be started.
        return True

    job.status = "failed"
    job.error = stale_reason
    job.last_activity_at = _utc_now()
    job.last_event = "task_failed"
    job.stall_warning_logged = False
    logger.error(
        "Stale summary job marked failed: document_id=%s reason=%s",
        job.document_id,
        stale_reason,
    )
    return False


def _summary_task_done(
    document_id: int,
    job: SummaryJob,
    task: asyncio.Task,
) -> None:
    with _jobs_lock:
        _background_tasks.discard(task)

        # A failed/stale job may already have been replaced. Its callback must
        # never overwrite the state of the replacement job.
        if _jobs.get(document_id) is not job:
            return

        _reconcile_generating_job_locked(job)


def get_summary_job(document_id: int) -> Optional[SummaryJob]:
    with _jobs_lock:
        job = _jobs.get(document_id)

        if job is not None:
            _reconcile_generating_job_locked(job)

        return job


def get_summary_job_state(document_id: int) -> Optional[dict]:
    with _jobs_lock:
        job = _jobs.get(document_id)

        if job is None:
            return None

        _reconcile_generating_job_locked(job)

        state = {
            "status": job.status,
            "started_at": job.started_at,
            "error": job.error,
        }

        if job.status == "generating":
            state.update({
                "last_activity_at": job.last_activity_at,
                "last_event": job.last_event,
                "completed_chunks": job.completed_chunks,
                "inactive_seconds": max(
                    0.0, (_utc_now() - job.last_activity_at).total_seconds()
                ),
            })
            # Reuse metadata already emitted by the generator.
            for event in reversed(job.events):
                total_chunks = event["data"].get("total_chunks")
                if event["event"] in {"status", "progress"} and type(total_chunks) is int:
                    state["total_chunks"] = total_chunks
                    break

        return state


def get_summary_job_snapshot(
    document_id: int,
    cursor: int = 0,
) -> tuple[list[dict], int, Optional[str]]:
    with _jobs_lock:
        job = _jobs.get(document_id)

        if job is None:
            return [], cursor, None

        _reconcile_generating_job_locked(job)

        events = list(job.events[cursor:])
        return events, len(job.events), job.status


def _publish(job: SummaryJob, event: str, data: dict) -> None:
    with _jobs_lock:
        job.events.append({"event": event, "data": data})
        job.last_activity_at = _utc_now()
        job.last_event = event
        job.stall_warning_logged = False

        if event == "progress":
            completed_chunks = data.get("completed_chunks")

            if isinstance(completed_chunks, int):
                job.completed_chunks = completed_chunks

            logger.info(
                "Summary job progress: document_id=%s completed_chunks=%s "
                "total_chunks=%s",
                job.document_id,
                data.get("completed_chunks"),
                data.get("total_chunks"),
            )

        elif event == "done":
            logger.info(
                "Summary job done event: document_id=%s",
                job.document_id,
            )


def _record_activity(job: SummaryJob, event: str) -> None:
    with _jobs_lock:
        job.last_activity_at = _utc_now()
        job.last_event = event
        job.stall_warning_logged = False


def _finish_job(
    job: SummaryJob,
    status: str,
    error: Optional[str] = None,
) -> None:
    with _jobs_lock:
        job.status = status
        job.error = error
        job.last_activity_at = _utc_now()
        job.last_event = f"worker_{status}"
        job.stall_warning_logged = False


def _run_summary_job(
    job: SummaryJob,
    document_text: str,
    summary_generator: SummaryGenerator,
) -> None:
    _record_activity(job, "worker_started")
    logger.info(
        "Summary job worker started: document_id=%s",
        job.document_id,
    )
    stream_db = SessionLocal()
    final_summary = None

    try:
        logger.info(
            "Summary generator iteration starting: document_id=%s",
            job.document_id,
        )

        for stream_event in summary_generator(document_text):
            if stream_event["event"] == "activity":
                _record_activity(job, stream_event["data"]["last_event"])
                continue
            if stream_event["event"] == "complete":
                final_summary = stream_event["final_summary"]
                _record_activity(job, "summary_complete")
                logger.info(
                    "Summary generator completed: document_id=%s",
                    job.document_id,
                )
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
        logger.info(
            "Summary job worker completed: document_id=%s",
            job.document_id,
        )

    except Exception as error:
        stream_db.rollback()
        error_message = str(error) or error.__class__.__name__
        logger.exception(
            "Summary job worker failed: document_id=%s",
            job.document_id,
        )
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
        logger.info(
            "Summary job worker finished: document_id=%s status=%s",
            job.document_id,
            job.status,
        )


def ensure_summary_job(
    document_id: int,
    document_text: str,
    summary_generator: Optional[SummaryGenerator] = None,
) -> tuple[SummaryJob, bool]:
    """Atomically return the active job or start one detached from the client."""
    with _jobs_lock:
        existing_job = _jobs.get(document_id)

        if existing_job is not None:
            if existing_job.status == "completed":
                return existing_job, False

            if _reconcile_generating_job_locked(existing_job):
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
        task.add_done_callback(
            lambda completed_task: _summary_task_done(
                document_id,
                job,
                completed_task,
            )
        )
        return job, True


def clear_summary_jobs() -> None:
    """Clear completed test/process state; running threads are not cancelled."""
    with _jobs_lock:
        _jobs.clear()
