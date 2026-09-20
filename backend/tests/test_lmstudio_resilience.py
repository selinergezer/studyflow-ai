import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

from app.services import ai_service as ai
from app.services import document_topic_service as summary
from app.services import summary_job_service as jobs
from app.services import quiz_generation_service as quiz
from app.services import lmstudio_request_gate as gate


def response(status=200, text="Tam cümle.", body=None):
    if body is None:
        body = "data: " + json.dumps({"choices": [{"delta": {"content": text}}]}) + "\n\ndata: [DONE]\n\n"
    return httpx.Response(status, text=body, request=httpx.Request("POST", "http://lm.test/v1/chat/completions"))


@contextmanager
def opened(item):
    try:
        yield item
    finally:
        item.close()


class SummaryRetryTests(unittest.TestCase):
    def run_job(self, streams):
        document = SimpleNamespace(summary=None)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = document
        job = jobs.SummaryJob(document_id=10)
        with patch.object(jobs, "SessionLocal", return_value=db), patch.object(
            summary, "_build_document_plan",
            return_value={"chunks": ["Kaynak metin."], "section_titles": {}, "mode": "short"},
        ), patch.object(summary, "_prepare_streaming_chunk", side_effect=lambda text: text), patch.object(
            summary, "SUMMARY_MAIN_RETRY_BACKOFF_SECONDS", (0, 0),
        ), patch.object(ai.httpx, "stream", side_effect=streams) as request:
            jobs._run_summary_job(job, "source", summary.generate_document_summary_stream)
        return job, document, db, request.call_count

    def test_main_500_before_token_retries_and_persists_once(self):
        job, document, db, calls = self.run_job([
            opened(response(500, body="Internal Server Error")), opened(response()),
        ])
        self.assertEqual(calls, 2)
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.completed_chunks, 1)
        self.assertEqual(document.summary, "Tam cümle.")
        db.commit.assert_called_once()
        self.assertEqual([e["data"]["text"] for e in job.events if e["event"] == "token"], ["Tam cümle."])
        self.assertNotIn("activity", [e["event"] for e in job.events])

    def test_500_after_a_token_is_not_retried(self):
        item = response()
        def lines():
            yield 'data: {"choices":[{"delta":{"content":"Partial"}}]}'
            response(500).raise_for_status()
        with patch.object(item, "iter_lines", side_effect=lines):
            job, _, db, calls = self.run_job([opened(item)])
        self.assertEqual(calls, 1)
        self.assertEqual(job.status, "failed")
        self.assertEqual(job.completed_chunks, 0)
        db.commit.assert_not_called()
        self.assertEqual([e["data"]["text"] for e in job.events if e["event"] == "token"], ["Partial"])

    def test_continuation_500_remains_warning_and_done(self):
        job, document, _, calls = self.run_job([
            opened(response(text="Tam cümle. Yarım")), opened(response(500)),
        ])
        self.assertEqual(calls, 2)
        self.assertEqual(job.status, "completed")
        self.assertEqual(document.summary, "Tam cümle.")
        self.assertEqual(job.completed_chunks, 1)

    def test_retry_is_bounded(self):
        job, _, _, calls = self.run_job([opened(response(503)) for _ in range(3)])
        self.assertEqual(calls, 3)
        self.assertEqual(job.status, "failed")

    def test_permanent_errors_are_not_retried(self):
        for status, body in [(400, "bad request"), (401, "unauthorized"), (404, "missing"), (422, "invalid"), (500, "Model does not exist")]:
            with self.subTest(status=status, body=body):
                job, _, _, calls = self.run_job([opened(response(status, body=body))])
                self.assertEqual(calls, 1)
                self.assertEqual(job.status, "failed")

    def test_transient_transport_before_token_retries(self):
        job, _, _, calls = self.run_job([httpx.ConnectError("reset"), opened(response())])
        self.assertEqual(calls, 2)
        self.assertEqual(job.status, "completed")

    def test_classification_excludes_timeouts_and_configuration(self):
        for cause, expected in [
            (httpx.ReadError("reset"), True), (httpx.WriteError("reset"), True),
            (httpx.RemoteProtocolError("disconnect"), True),
            (httpx.ReadTimeout("silent"), False), (httpx.UnsupportedProtocol("bad URL"), False),
        ]:
            error = ai.LMStudioServiceError("wrapped")
            error.__cause__ = cause
            self.assertEqual(ai.is_transient_lmstudio_error(error), expected)
        for status in (500, 502, 503, 504):
            try:
                response(status).raise_for_status()
            except httpx.HTTPStatusError as cause:
                error = ai.LMStudioServiceError("wrapped")
                error.__cause__ = cause
                self.assertTrue(ai.is_transient_lmstudio_error(error))


class SharedGateTests(unittest.TestCase):
    def test_exception_and_nested_acquisition_release_the_gate(self):
        with self.assertRaisesRegex(RuntimeError, "Nested"):
            with gate.lmstudio_request_gate():
                with gate.lmstudio_request_gate():
                    self.fail("nested gate must not be entered")
        with self.assertRaisesRegex(ValueError, "boom"):
            with gate.lmstudio_request_gate():
                raise ValueError("boom")
        with gate.lmstudio_request_gate():
            pass

    def test_wait_callback_exception_does_not_leak_a_permit(self):
        release = threading.Event()
        held = threading.Event()
        def holder():
            with gate.lmstudio_request_gate():
                held.set()
                release.wait(2)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(holder)
            self.assertTrue(held.wait(1))
            try:
                with self.assertRaisesRegex(ValueError, "callback"):
                    with gate.lmstudio_request_gate(lambda: (_ for _ in ()).throw(ValueError("callback"))):
                        self.fail("must wait")
            finally:
                release.set()
                future.result(2)
        with gate.lmstudio_request_gate():
            pass

    def test_summary_blocks_quiz_and_stream_close_releases(self):
        quiz_http = threading.Event()
        quiz_entered = threading.Event()
        @contextmanager
        def quiz_response(*args, **kwargs):
            quiz_http.set()
            yield object()
        def run_quiz():
            quiz_entered.set()
            return list(quiz._production_batch([quiz.Evidence(1, "Kaynak metin.", 0, 3.0)], quiz.QuizSession(), base_url="http://lm.test", model=ai.LMSTUDIO_QUIZ_MODEL))
        with patch.object(ai.httpx, "stream", side_effect=lambda *a, **kw: opened(response())), patch.object(
            quiz, "urlopen", side_effect=quiz_response,
        ), patch.object(quiz, "iter_sse_content", return_value=iter(())):
            stream = ai._generate_with_lmstudio_stream("summary")
            self.assertEqual(next(stream), "Tam cümle.")
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(run_quiz)
                try:
                    self.assertTrue(quiz_entered.wait(1))
                    self.assertFalse(quiz_http.wait(0.05))
                finally:
                    stream.close()
                future.result(2)
            self.assertTrue(quiz_http.is_set())

    def test_quiz_blocks_summary_and_flashcard_and_sync_requests(self):
        held = threading.Event()
        release = threading.Event()
        sent = threading.Event()
        @contextmanager
        def quiz_response(*args, **kwargs):
            held.set()
            release.wait(2)
            yield object()
        def http_stream(*args, **kwargs):
            sent.set()
            text = json.dumps({"question": "Soru?", "answer": "Yanıt."}) if kwargs["json"]["model"] == ai.LMSTUDIO_QUIZ_MODEL else "Tam cümle."
            return opened(response(text=text))
        with patch.object(quiz, "urlopen", side_effect=quiz_response), patch.object(
            quiz, "iter_sse_content", return_value=iter(()),
        ), patch.object(ai.httpx, "stream", side_effect=http_stream):
            with ThreadPoolExecutor(max_workers=3) as pool:
                job = pool.submit(lambda: list(quiz._production_batch([quiz.Evidence(1, "Kaynak metin.", 0, 3.0)], quiz.QuizSession(), base_url="http://lm.test", model=ai.LMSTUDIO_QUIZ_MODEL)))
                self.assertTrue(held.wait(1))
                summary_job = pool.submit(lambda: list(ai._generate_with_lmstudio_stream("summary")))
                cards = pool.submit(lambda: list(ai.generate_flashcards_stream("Kaynak metin.", 1)))
                try:
                    self.assertFalse(sent.wait(0.05))
                finally:
                    release.set()
                for future in (job, summary_job, cards):
                    future.result(2)
        self.assertEqual(cards.result()[0].question, "Soru?")
        sent.clear()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with patch.object(ai.httpx, "post", side_effect=lambda *a, **kw: (sent.set() or httpx.Response(
                200, json={"choices": [{"message": {"content": "result"}}]},
                request=httpx.Request("POST", "http://lm.test"),
            ))):
                with gate.lmstudio_request_gate():
                    sync = pool.submit(ai._generate_with_lmstudio, "sync")
                    self.assertFalse(sent.wait(0.05))
                self.assertEqual(sync.result(2), "result")

    def test_quiz_budget_excludes_only_gate_wait(self):
        now = [10.0]
        observed = []
        @contextmanager
        def waited_gate():
            now[0] += 150.0
            yield 150.0
        @contextmanager
        def quiz_response(*args, **kwargs):
            observed.append(kwargs["timeout"])
            yield object()
        def tokens(*args):
            now[0] += 119.0
            yield " "
            now[0] += 2.0
            yield " "
        adjusted = []
        with patch.object(quiz, "lmstudio_request_gate", waited_gate), patch.object(
            quiz.time, "monotonic", side_effect=lambda: now[0],
        ), patch.object(quiz, "urlopen", side_effect=quiz_response), patch.object(
            quiz, "iter_sse_content", side_effect=tokens,
        ), self.assertRaisesRegex(quiz.LMStudioError, "süre bütçesi"):
            list(quiz._production_batch([quiz.Evidence(1, "Kaynak metin.", 0, 3.0)], quiz.QuizSession(), base_url="http://lm.test", model="qwen", generation_deadline=130.0, exclude_gate_wait=adjusted.append))
        self.assertEqual(adjusted, [150.0])
        self.assertEqual(observed, [120.0])

    def test_gate_wait_adjustment_survives_quiz_refill(self):
        now = [0.0]
        deadlines = []
        pool = [(index, f"Kaynak evidence metni {index}.", 3.0) for index in range(8)]
        def select(_text, count, *, candidates, first_evidence_id=1, **kwargs):
            return [quiz.Evidence(first_evidence_id + index, item[1], item[0], item[2])
                    for index, item in enumerate(candidates[:count])]
        def batch(evidence, session, **kwargs):
            deadlines.append(kwargs["generation_deadline"])
            if len(deadlines) == 1:
                kwargs["exclude_gate_wait"](150.0)
                now[0] += 160.0  # 150 queued, 10 generating.
            session.accepted_count += 1
            session.accepted_evidence_ids.add(evidence[0].evidence_id)
            kwargs["batch_metrics"].accepted_count += 1
            yield quiz.QuizQuestion(evidence[0].evidence_id, "Soru?", ("A", "B", "C", "D", "E"), 0)
        with patch.object(quiz.time, "monotonic", side_effect=lambda: now[0]), patch.object(
            quiz, "clean_pdf_text", return_value="source",
        ), patch.object(quiz, "_production_candidate_pools", return_value=(pool, [])), patch.object(
            quiz, "select_evidence", side_effect=select,
        ), patch.object(quiz, "_selected_evidence_rejection_reason", return_value=None), patch.object(
            quiz, "_evidence_semantically_close", return_value=False,
        ), patch.object(quiz, "_production_batch", side_effect=batch):
            result = list(quiz.generate_production_quiz("source", 2, base_url="http://lm.test"))
        self.assertEqual(len(result), 2)
        self.assertEqual(deadlines, [120.0, 270.0])

    def test_quiz_http_exception_releases_the_shared_gate(self):
        from urllib.error import URLError
        with patch.object(quiz, "urlopen", side_effect=URLError("reset")), self.assertRaises(quiz.LMStudioError):
            list(quiz._production_batch([quiz.Evidence(1, "Kaynak metin.", 0, 3.0)], quiz.QuizSession(), base_url="http://lm.test", model="qwen"))
        with gate.lmstudio_request_gate():
            pass

    def test_real_inference_silence_after_queue_wait_still_times_out(self):
        acquired = threading.Event()
        def slow_producer(chunk, index, total, queue, predict):
            queue.put((index, "activity", "lm_gate_wait"))
            acquired.set()
            time.sleep(0.06)  # No further gate heartbeats once inference begins.
            queue.put((index, "done", None))
        with patch.object(summary, "_build_document_plan", return_value={
            "chunks": ["source"], "section_titles": {}, "mode": "short",
        }), patch.object(summary, "_stream_chunk_to_queue", side_effect=slow_producer), patch.object(
            summary, "SUMMARY_QUEUE_POLL_INTERVAL_SECONDS", 0.005,
        ), patch.object(summary, "SUMMARY_QUEUE_INACTIVITY_TIMEOUT_SECONDS", 0.02), self.assertRaisesRegex(
            ai.LMStudioServiceError, "ilerleme kaydetmedi",
        ):
            list(summary.generate_document_summary_stream("source"))
        self.assertTrue(acquired.is_set())

    def test_summary_gate_wait_is_activity_but_not_sse(self):
        held = threading.Event()
        release = threading.Event()
        seen_wait = threading.Event()
        plan = {"chunks": ["source"], "section_titles": {}, "mode": "short"}
        def holder():
            with gate.lmstudio_request_gate():
                held.set()
                release.wait(2)
        @contextmanager
        def stream(*args, **kwargs):
            yield response()
        job = jobs.SummaryJob(document_id=10)
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(summary=None)
        original_record = jobs._record_activity
        def record(job, event):
            original_record(job, event)
            if event == "lm_gate_wait": seen_wait.set()
        with patch.object(gate, "GATE_WAIT_POLL_SECONDS", 0.005), patch.object(
            summary, "SUMMARY_QUEUE_POLL_INTERVAL_SECONDS", 0.005,
        ), patch.object(summary, "SUMMARY_QUEUE_INACTIVITY_TIMEOUT_SECONDS", 0.03), patch.object(
            summary, "_build_document_plan", return_value=plan,
        ), patch.object(summary, "_prepare_streaming_chunk", side_effect=lambda x: x), patch.object(
            ai.httpx, "stream", side_effect=stream,
        ), patch.object(jobs, "SessionLocal", return_value=db), patch.object(jobs, "_record_activity", side_effect=record):
            with ThreadPoolExecutor(max_workers=2) as pool:
                blocker = pool.submit(holder)
                self.assertTrue(held.wait(1))
                worker = pool.submit(jobs._run_summary_job, job, "source", summary.generate_document_summary_stream)
                try:
                    self.assertTrue(seen_wait.wait(1))
                    time.sleep(0.09)  # Three times the real inactivity limit, all queued.
                    self.assertFalse(worker.done())
                    self.assertEqual(job.status, "generating")
                    self.assertEqual(job.last_event, "lm_gate_wait")
                    self.assertLess((jobs._utc_now() - job.last_activity_at).total_seconds(), 0.03)
                finally:
                    release.set()
                blocker.result(2)
                worker.result(2)
        self.assertEqual(job.status, "completed")
        self.assertNotIn("activity", [event["event"] for event in job.events])


if __name__ == "__main__":
    unittest.main()
