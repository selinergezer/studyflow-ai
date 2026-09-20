import asyncio
import sys
import threading
import time
import unittest
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch



from app.api.document import (  # noqa: E402
    get_document_summary_status,
    stream_document_summary,
)
from app.services.summary_job_service import (  # noqa: E402
    SummaryJob,
    _jobs,
    _jobs_lock,
    clear_summary_jobs,
    ensure_summary_job,
    get_summary_job,
)
from app.services.ai_service import LMStudioServiceError  # noqa: E402


class _Query:
    def __init__(self, document):
        self.document = document

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.document


class _StreamSession:
    def __init__(self, document):
        self.document = document
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def query(self, model):
        return _Query(self.document)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class DocumentSummaryStreamTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        clear_summary_jobs()
        self.document = SimpleNamespace(
            id=1,
            text="Kaynak metin",
            summary=None,
        )
        self.stream_session = _StreamSession(self.document)

    async def asyncTearDown(self):
        job = get_summary_job(self.document.id)

        if job is not None and job.task is not None:
            try:
                await job.task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        clear_summary_jobs()

    def _patch_backend(self, generator):
        patches = ExitStack()
        patches.enter_context(patch(
            "app.api.document._get_accessible_document",
            return_value=self.document,
        ))
        patches.enter_context(patch(
            "app.services.summary_job_service.SessionLocal",
            return_value=self.stream_session,
        ))
        patches.enter_context(patch(
            "app.services.summary_job_service.generate_document_summary_stream",
            side_effect=generator,
        ))
        return patches

    async def _wait_for_status(self, expected_status):
        for _ in range(100):
            job = get_summary_job(self.document.id)

            if job is not None and job.status == expected_status:
                return job

            await asyncio.sleep(0.01)

        self.fail(f"Summary job did not reach {expected_status!r}")

    async def test_disconnect_does_not_cancel_generation_or_database_write(self):
        release_generation = threading.Event()

        def generator(text):
            yield {"event": "status", "data": {"status": "started"}}
            release_generation.wait(timeout=1)
            yield {"event": "complete", "final_summary": "Tam özet"}

        with self._patch_backend(generator):
            response = stream_document_summary(
                self.document.id,
                SimpleNamespace(),
                SimpleNamespace(id=7),
            )
            body_iterator = response.body_iterator
            first_event = await body_iterator.__anext__()
            self.assertIn("event: status", first_event)

            await body_iterator.aclose()

            active_job = get_summary_job(self.document.id)
            attached_job, created = ensure_summary_job(
                self.document.id,
                self.document.text,
                generator,
            )
            self.assertIs(attached_job, active_job)
            self.assertFalse(created)
            self.assertEqual(active_job.status, "generating")

            release_generation.set()
            await self._wait_for_status("completed")

        self.assertEqual(self.document.summary, "Tam özet")
        self.assertTrue(self.stream_session.committed)
        self.assertTrue(self.stream_session.closed)

    async def test_duplicate_request_reuses_running_job(self):
        release_generation = threading.Event()
        calls = 0

        def generator(text):
            nonlocal calls
            calls += 1
            release_generation.wait(timeout=1)
            yield {"event": "complete", "final_summary": "Tek özet"}

        with patch(
            "app.services.summary_job_service.SessionLocal",
            return_value=self.stream_session,
        ):
            first_job, first_created = ensure_summary_job(
                self.document.id,
                self.document.text,
                generator,
            )
            second_job, second_created = ensure_summary_job(
                self.document.id,
                self.document.text,
                generator,
            )
            release_generation.set()
            await first_job.task

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertIs(first_job, second_job)
        self.assertEqual(calls, 1)

    async def test_worker_start_and_events_update_activity(self):
        release_generation = threading.Event()

        def generator(text):
            release_generation.wait(timeout=1)
            yield {"event": "progress", "data": {
                "completed_chunks": 1,
                "total_chunks": 1,
            }}
            yield {"event": "complete", "final_summary": "Aktif özet"}

        with patch(
            "app.services.summary_job_service.SessionLocal",
            return_value=self.stream_session,
        ):
            job, _ = ensure_summary_job(
                self.document.id,
                self.document.text,
                generator,
            )

            for _ in range(100):
                if job.last_event == "worker_started":
                    break
                await asyncio.sleep(0.01)

            self.assertEqual(job.last_event, "worker_started")
            started_activity = job.last_activity_at
            release_generation.set()
            await job.task

        self.assertGreaterEqual(job.last_activity_at, started_activity)
        self.assertEqual(job.completed_chunks, 1)
        self.assertEqual(job.status, "completed")

    async def test_quiet_but_live_worker_does_not_allow_duplicate(self):
        release_generation = threading.Event()

        def generator(text):
            release_generation.wait(timeout=1)
            yield {"event": "complete", "final_summary": "Tek özet"}

        with patch(
            "app.services.summary_job_service.SessionLocal",
            return_value=self.stream_session,
        ):
            job, _ = ensure_summary_job(
                self.document.id,
                self.document.text,
                generator,
            )

            for _ in range(100):
                if job.last_event == "worker_started":
                    break
                await asyncio.sleep(0.01)

            with _jobs_lock:
                job.last_activity_at -= timedelta(hours=1)

            attached_job, created = ensure_summary_job(
                self.document.id,
                self.document.text,
                generator,
            )

            self.assertIs(attached_job, job)
            self.assertFalse(created)
            self.assertEqual(job.status, "generating")
            release_generation.set()
            await job.task

    async def test_worker_timeout_finishes_before_retry_starts(self):
        calls = 0

        def generator(text):
            nonlocal calls
            calls += 1

            if calls == 1:
                raise LMStudioServiceError("Summary generation timed out")

            yield {"event": "complete", "final_summary": "Retry özeti"}

        with patch(
            "app.services.summary_job_service.SessionLocal",
            return_value=self.stream_session,
        ):
            timed_out_job, _ = ensure_summary_job(
                self.document.id,
                self.document.text,
                generator,
            )
            await timed_out_job.task

            self.assertTrue(timed_out_job.task.done())
            self.assertEqual(timed_out_job.status, "failed")

            retry_job, created = ensure_summary_job(
                self.document.id,
                self.document.text,
                generator,
            )
            await retry_job.task

        self.assertTrue(created)
        self.assertIsNot(retry_job, timed_out_job)
        self.assertEqual(retry_job.status, "completed")
        self.assertEqual(calls, 2)

    async def test_done_generating_task_is_replaced_as_stale(self):
        finished_task = asyncio.create_task(asyncio.sleep(0))
        await finished_task
        stale_job = SummaryJob(
            document_id=self.document.id,
            task=finished_task,
        )

        with _jobs_lock:
            _jobs[self.document.id] = stale_job

        def generator(text):
            yield {"event": "complete", "final_summary": "Yeni özet"}

        with patch(
            "app.services.summary_job_service.SessionLocal",
            return_value=self.stream_session,
        ):
            replacement, created = ensure_summary_job(
                self.document.id,
                self.document.text,
                generator,
            )
            await replacement.task

        self.assertTrue(created)
        self.assertIsNot(replacement, stale_job)
        self.assertEqual(stale_job.status, "failed")
        self.assertEqual(replacement.status, "completed")

    async def test_generating_job_without_task_is_replaced_as_stale(self):
        stale_job = SummaryJob(document_id=self.document.id)

        with _jobs_lock:
            _jobs[self.document.id] = stale_job

        def generator(text):
            yield {"event": "complete", "final_summary": "Yeni özet"}

        with patch(
            "app.services.summary_job_service.SessionLocal",
            return_value=self.stream_session,
        ):
            replacement, created = ensure_summary_job(
                self.document.id,
                self.document.text,
                generator,
            )
            await replacement.task

        self.assertTrue(created)
        self.assertIsNot(replacement, stale_job)
        self.assertEqual(stale_job.status, "failed")
        self.assertEqual(replacement.status, "completed")

    async def test_cancelled_generating_task_is_replaced_as_stale(self):
        cancelled_task = asyncio.create_task(asyncio.sleep(10))
        cancelled_task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await cancelled_task

        stale_job = SummaryJob(
            document_id=self.document.id,
            task=cancelled_task,
        )

        with _jobs_lock:
            _jobs[self.document.id] = stale_job

        def generator(text):
            yield {"event": "complete", "final_summary": "Yeni özet"}

        with patch(
            "app.services.summary_job_service.SessionLocal",
            return_value=self.stream_session,
        ):
            replacement, created = ensure_summary_job(
                self.document.id,
                self.document.text,
                generator,
            )
            await replacement.task

        self.assertTrue(created)
        self.assertIsNot(replacement, stale_job)
        self.assertEqual(stale_job.status, "failed")
        self.assertEqual(replacement.status, "completed")

    async def test_task_crash_marks_generating_job_failed(self):
        with patch(
            "app.services.summary_job_service.SessionLocal",
            side_effect=RuntimeError("session startup crashed"),
        ):
            job, created = ensure_summary_job(
                self.document.id,
                self.document.text,
                lambda text: iter(()),
            )

            self.assertTrue(created)

            with self.assertRaisesRegex(RuntimeError, "session startup crashed"):
                await job.task

            await asyncio.sleep(0)

        self.assertEqual(job.status, "failed")
        self.assertIn("session startup crashed", job.error)

    async def test_normal_task_completion_remains_completed(self):
        def generator(text):
            yield {"event": "complete", "final_summary": "Normal özet"}

        with patch(
            "app.services.summary_job_service.SessionLocal",
            return_value=self.stream_session,
        ):
            job, created = ensure_summary_job(
                self.document.id,
                self.document.text,
                generator,
            )
            await job.task
            await asyncio.sleep(0)

        self.assertTrue(created)
        self.assertEqual(job.status, "completed")
        self.assertIsNone(job.error)

    async def test_generating_status_exposes_progress_metadata(self):
        now = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
        for source in (None, "status", "progress"):
            with self.subTest(total_chunks_source=source):
                job = SummaryJob(
                    document_id=self.document.id,
                    started_at=now - timedelta(seconds=30),
                    last_activity_at=now - timedelta(seconds=4.2),
                    last_event="progress" if source else None,
                    completed_chunks=3 if source else 0,
                    task=asyncio.current_task(),
                    events=([
                        {"event": source, "data": {"total_chunks": 28}},
                        {"event": "token", "data": {"text": "Özet"}},
                    ] if source else []),
                )
                with _jobs_lock:
                    _jobs[self.document.id] = job
                try:
                    with patch(
                        "app.api.document._get_accessible_document",
                        return_value=self.document,
                    ), patch(
                        "app.services.summary_job_service._utc_now",
                        return_value=now,
                    ):
                        status = get_document_summary_status(
                            self.document.id, SimpleNamespace(), SimpleNamespace(id=7),
                        )
                    expected = {
                        "document_id": self.document.id,
                        "status": "generating",
                        "has_summary": False,
                        "started_at": job.started_at,
                        "last_activity_at": job.last_activity_at,
                        "last_event": job.last_event,
                        "completed_chunks": job.completed_chunks,
                        "inactive_seconds": 4.2,
                    }
                    if source:
                        expected["total_chunks"] = 28
                    self.assertEqual(status, expected)
                    from fastapi.encoders import jsonable_encoder
                    encoded = jsonable_encoder(status)
                    self.assertEqual(encoded["started_at"], job.started_at.isoformat())
                    self.assertEqual(
                        encoded["last_activity_at"], job.last_activity_at.isoformat(),
                    )
                finally:
                    clear_summary_jobs()

    async def test_not_started_status_contract(self):
        with patch(
            "app.api.document._get_accessible_document",
            return_value=self.document,
        ):
            status = get_document_summary_status(
                self.document.id, SimpleNamespace(), SimpleNamespace(id=7),
            )
        self.assertEqual(status, {
            "document_id": self.document.id,
            "status": "not_started",
            "has_summary": False,
        })

    async def test_completed_status_uses_persisted_summary(self):
        self.document.summary = "Kaydedilmiş özet"

        with patch(
            "app.api.document._get_accessible_document",
            return_value=self.document,
        ):
            status = get_document_summary_status(
                self.document.id,
                SimpleNamespace(),
                SimpleNamespace(id=7),
            )

        self.assertEqual(status, {
            "document_id": self.document.id,
            "status": "completed",
            "has_summary": True,
        })

    async def test_failed_generation_is_exposed_by_status_endpoint(self):
        def generator(text):
            raise RuntimeError("LM Studio unavailable")
            yield

        with self._patch_backend(generator):
            job, _ = ensure_summary_job(
                self.document.id,
                self.document.text,
                generator,
            )
            await job.task
            status = get_document_summary_status(
                self.document.id,
                SimpleNamespace(),
                SimpleNamespace(id=7),
            )

        self.assertEqual(status, {
            "document_id": self.document.id,
            "status": "failed",
            "has_summary": False,
            "error": "LM Studio unavailable",
        })
        self.assertTrue(self.stream_session.rolled_back)
        self.assertTrue(self.stream_session.closed)

    async def test_blocking_generation_does_not_block_event_loop(self):
        def generator(text):
            yield {"event": "status", "data": {"status": "started"}}
            time.sleep(0.2)
            yield {"event": "complete", "final_summary": "Özet"}

        with self._patch_backend(generator):
            response = stream_document_summary(
                self.document.id,
                SimpleNamespace(),
                SimpleNamespace(id=7),
            )
            body_iterator = response.body_iterator
            await body_iterator.__anext__()

            started_at = asyncio.get_running_loop().time()
            await asyncio.sleep(0.02)

            self.assertLess(
                asyncio.get_running_loop().time() - started_at,
                0.1,
            )

            async for _ in body_iterator:
                pass
