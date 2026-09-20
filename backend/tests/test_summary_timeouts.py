import unittest
import time
from unittest.mock import patch

import httpx

from app.services.ai_service import (
    LMSTUDIO_STREAM_CONNECT_TIMEOUT_SECONDS,
    LMSTUDIO_STREAM_POOL_TIMEOUT_SECONDS,
    LMSTUDIO_STREAM_READ_TIMEOUT_SECONDS,
    LMSTUDIO_STREAM_WRITE_TIMEOUT_SECONDS,
    LMStudioServiceError,
    _generate_with_lmstudio_stream,
)
from app.services import document_topic_service


class _StreamingResponse:
    is_error = False

    def __init__(self, lines=None, error=None):
        self.lines = lines or []
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        if self.error is not None:
            raise self.error

        yield from self.lines


class SummaryTimeoutTests(unittest.TestCase):
    def test_lm_studio_read_timeout_becomes_service_error(self):
        response = _StreamingResponse(
            error=httpx.ReadTimeout("stream was silent"),
        )

        with patch("app.services.ai_service.httpx.stream", return_value=response):
            with self.assertRaisesRegex(
                LMStudioServiceError,
                "uzun süre veri göndermedi",
            ):
                list(_generate_with_lmstudio_stream("prompt"))

    def test_lm_studio_stream_uses_explicit_inactivity_timeouts(self):
        response = _StreamingResponse([
            'data: {"choices":[{"delta":{"content":"Token"}}]}',
        ])

        with patch(
            "app.services.ai_service.httpx.stream",
            return_value=response,
        ) as stream:
            self.assertEqual(
                list(_generate_with_lmstudio_stream("prompt")),
                ["Token"],
            )

        timeout = stream.call_args.kwargs["timeout"]
        self.assertEqual(timeout.connect, LMSTUDIO_STREAM_CONNECT_TIMEOUT_SECONDS)
        self.assertEqual(timeout.read, LMSTUDIO_STREAM_READ_TIMEOUT_SECONDS)
        self.assertEqual(timeout.write, LMSTUDIO_STREAM_WRITE_TIMEOUT_SECONDS)
        self.assertEqual(timeout.pool, LMSTUDIO_STREAM_POOL_TIMEOUT_SECONDS)

    @staticmethod
    def _document_plan():
        return {
            "chunks": ["Kaynak metin."],
            "section_titles": {},
            "mode": "short",
        }

    def test_queue_producer_without_event_fails_instead_of_waiting_forever(self):
        with patch.object(
            document_topic_service,
            "_build_document_plan",
            return_value=self._document_plan(),
        ), patch.object(
            document_topic_service,
            "_stream_chunk_to_queue",
            return_value=None,
        ), patch.object(
            document_topic_service,
            "SUMMARY_QUEUE_POLL_INTERVAL_SECONDS",
            0.01,
        ):
            with self.assertRaisesRegex(
                LMStudioServiceError,
                "terminal event",
            ):
                list(document_topic_service.generate_document_summary_stream(
                    "Kaynak metin.",
                ))

    def test_running_but_silent_queue_producer_hits_inactivity_timeout(self):
        def silent_producer(*args, **kwargs):
            time.sleep(0.06)

        with patch.object(
            document_topic_service,
            "_build_document_plan",
            return_value=self._document_plan(),
        ), patch.object(
            document_topic_service,
            "_stream_chunk_to_queue",
            side_effect=silent_producer,
        ), patch.object(
            document_topic_service,
            "SUMMARY_QUEUE_POLL_INTERVAL_SECONDS",
            0.005,
        ), patch.object(
            document_topic_service,
            "SUMMARY_QUEUE_INACTIVITY_TIMEOUT_SECONDS",
            0.02,
        ):
            with self.assertRaisesRegex(
                LMStudioServiceError,
                "ilerleme kaydetmedi",
            ):
                list(document_topic_service.generate_document_summary_stream(
                    "Kaynak metin.",
                ))

    def test_normal_queue_token_and_progress_flow_does_not_timeout(self):
        def produce(chunk, chunk_index, total_chunks, output_queue, num_predict):
            output_queue.put((chunk_index, "token", "Tam cümle."))
            output_queue.put((chunk_index, "done", None))

        with patch.object(
            document_topic_service,
            "_build_document_plan",
            return_value=self._document_plan(),
        ), patch.object(
            document_topic_service,
            "_stream_chunk_to_queue",
            side_effect=produce,
        ), patch.object(
            document_topic_service,
            "SUMMARY_QUEUE_POLL_INTERVAL_SECONDS",
            0.01,
        ), patch.object(
            document_topic_service,
            "SUMMARY_QUEUE_INACTIVITY_TIMEOUT_SECONDS",
            0.02,
        ):
            events = list(
                document_topic_service.generate_document_summary_stream(
                    "Kaynak metin.",
                )
            )

        event_names = [event["event"] for event in events]
        self.assertIn("token", event_names)
        self.assertIn("progress", event_names)
        self.assertIn("complete", event_names)
