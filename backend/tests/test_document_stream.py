import asyncio
import sys
import threading
import time
import unittest
from contextlib import ExitStack
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

sys.modules.setdefault("httpx", ModuleType("httpx"))

from app.api.document import (  # noqa: E402
    get_document_summary_status,
    stream_document_summary,
)
from app.services.summary_job_service import (  # noqa: E402
    clear_summary_jobs,
    ensure_summary_job,
    get_summary_job,
)


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
            await job.task

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

        self.assertEqual(status["status"], "completed")
        self.assertTrue(status["has_summary"])

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

        self.assertEqual(status["status"], "failed")
        self.assertFalse(status["has_summary"])
        self.assertEqual(status["error"], "LM Studio unavailable")
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
