import asyncio
import sys
import time
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from types import ModuleType
from unittest.mock import patch

# The checked-in local virtualenv does not include httpx. This test replaces
# the summary generator, so no HTTP client behavior is exercised.
sys.modules.setdefault("httpx", ModuleType("httpx"))

from app.api.document import stream_document_summary


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

    def query(self, model):
        return _Query(self.document)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


class DocumentSummaryStreamTests(unittest.IsolatedAsyncioTestCase):
    async def test_blocking_summary_generator_does_not_block_event_loop(self):
        document = SimpleNamespace(id=1, text="Kaynak metin", summary=None)
        stream_session = _StreamSession(document)

        def blocking_summary_generator(text):
            yield {
                "event": "status",
                "data": {"status": "started", "total_chunks": 1},
            }
            time.sleep(0.2)
            yield {"event": "token", "data": {"text": "Özet"}}
            yield {"event": "complete", "final_summary": "Özet"}

        with ExitStack() as patches:
            patches.enter_context(patch(
                "app.api.document._get_accessible_document",
                return_value=document,
            ))
            patches.enter_context(patch(
                "app.api.document.generate_document_summary_stream",
                side_effect=blocking_summary_generator,
            ))
            patches.enter_context(patch(
                "app.api.document.SessionLocal",
                return_value=stream_session,
            ))
            response = stream_document_summary(
                document_id=1,
                db=SimpleNamespace(),
                current_user=SimpleNamespace(id=7),
            )
            body_iterator = response.body_iterator

            first_event = await body_iterator.__anext__()
            self.assertIn("event: status", first_event)

            next_event_task = asyncio.create_task(body_iterator.__anext__())
            started_at = asyncio.get_running_loop().time()
            await asyncio.sleep(0.02)

            self.assertLess(
                asyncio.get_running_loop().time() - started_at,
                0.1,
            )
            self.assertFalse(next_event_task.done())
            self.assertIn("event: token", await next_event_task)

            done_event = await body_iterator.__anext__()
            self.assertIn("event: done", done_event)

            with self.assertRaises(StopAsyncIteration):
                await body_iterator.__anext__()

        self.assertTrue(stream_session.committed)
        self.assertEqual(document.summary, "Özet")
