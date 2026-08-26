import asyncio
import json
import sys
import unittest
from types import SimpleNamespace
from types import ModuleType
from unittest.mock import patch

sys.modules.setdefault("httpx", ModuleType("httpx"))

from app.api.quiz import stream_quiz_generation
from app.services.ai_service import QuizQuestion
from app.models.achievement import Achievement  # noqa: F401
from app.models.course import Course  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.email_verification import EmailVerification  # noqa: F401
from app.models.event import Event  # noqa: F401
from app.models.flashcard import Flashcard  # noqa: F401
from app.models.goal import Goal  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.question import Question  # noqa: F401
from app.models.quiz import Quiz  # noqa: F401
from app.models.quiz_attempt import QuizAttempt  # noqa: F401
from app.models.study_session import StudySession  # noqa: F401
from app.models.user import User  # noqa: F401


def _question(number):
    return QuizQuestion(
        question_text=f"Doğrulanmış soru {number}?",
        option_a=f"Doğru {number}",
        option_b=f"Yanlış B {number}",
        option_c=f"Yanlış C {number}",
        option_d=f"Yanlış D {number}",
        option_e=f"Yanlış E {number}",
        correct_answer="A",
        explanation="Kaynak evidence tarafından desteklenir.",
    )


class _Query:
    def __init__(self, document):
        self.document = document

    def join(self, *_args, **_kwargs):
        return self

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.document

    def all(self):
        return []


class _DocumentDB:
    def __init__(self):
        self.document = SimpleNamespace(
            id=31,
            text="Yeterli quiz kaynak metni.",
            filename="kaynak.pdf",
            course_id=4,
        )

    def query(self, _model):
        return _Query(self.document)


class _StreamDB:
    def __init__(self):
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def add(self, item):
        self.added.append(item)

    def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        pass


class QuizPartialCompletionTests(unittest.TestCase):
    @staticmethod
    async def _read(response):
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    def _run(self, generated):
        stream_db = _StreamDB()
        with patch("app.api.quiz.SessionLocal", return_value=stream_db), patch(
            "app.api.quiz.generate_quiz_questions_stream",
            return_value=iter(generated),
        ):
            response = stream_quiz_generation(
                31, 5, _DocumentDB(), SimpleNamespace(id=7)
            )
            body = asyncio.run(self._read(response))
        return body, stream_db

    def test_four_of_five_is_not_saved(self):
        body, stream_db = self._run([_question(i) for i in range(1, 5)])
        self.assertEqual(body.count("event: question"), 4)
        self.assertIn("event: error", body)
        self.assertNotIn("event: done", body)
        self.assertEqual(stream_db.commits, 0)
        self.assertEqual(stream_db.rollbacks, 1)

    def test_three_of_five_keeps_existing_error_behavior(self):
        body, stream_db = self._run([_question(i) for i in range(1, 4)])
        self.assertIn("event: error", body)
        self.assertNotIn("event: done", body)
        self.assertEqual(stream_db.commits, 0)
        self.assertEqual(stream_db.rollbacks, 1)

    def test_five_of_five_remains_complete_success(self):
        body, stream_db = self._run([_question(i) for i in range(1, 6)])
        self.assertEqual(body.count("event: question"), 5)
        self.assertNotIn("event: error", body)
        self.assertIn("event: done", body)
        self.assertEqual(stream_db.commits, 1)
        self.assertEqual(
            sum(isinstance(item, Question) for item in stream_db.added),
            5,
        )

    def test_only_generator_accepted_questions_are_streamed_in_order(self):
        accepted = [_question(1), _question(2), _question(3), _question(4), _question(5)]
        body, stream_db = self._run(accepted)
        question_payloads = [
            json.loads(block.split("data: ", 1)[1])
            for block in body.strip().split("\n\n")
            if block.startswith("event: question")
        ]
        self.assertEqual(
            [item["question_text"] for item in question_payloads],
            [item.question_text for item in accepted],
        )
        self.assertEqual([item["index"] for item in question_payloads], [1, 2, 3, 4, 5])
        self.assertEqual(stream_db.commits, 1)


if __name__ == "__main__":
    unittest.main()
