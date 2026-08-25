import unittest
import sys
import json
import asyncio
import inspect
import threading
from types import SimpleNamespace
from types import ModuleType
from unittest.mock import patch

# The project's checked-in virtualenv lacks httpx, while quiz imports the AI
# service transitively. These endpoint unit tests never perform HTTP calls.
sys.modules.setdefault("httpx", ModuleType("httpx"))

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.quiz import (
    _get_previous_document_questions,
    generate_quiz_endpoint,
    get_quiz,
    stream_quiz_generation,
    submit_quiz,
)
from app.services.ai_service import (
    LMStudioServiceError,
    _QUIZ_CHUNK_CHARS,
    _QUIZ_FALLBACK_CHUNK_CHARS,
    _QUIZ_MAX_FILL_ROUNDS,
    _quiz_validation_rejection_reason,
    _request_quiz_questions,
    _split_quiz_source,
    _validate_quiz_question,
    _validate_quiz_question_with_meta_repair,
    _is_duplicate_quiz_question,
    _is_historical_learning_target_duplicate,
    _quiz_duplicate_reason,
    _select_quiz_chunks,
    QuizQuestion,
    generate_quiz_questions,
    generate_quiz_questions_stream,
)
from app.models.achievement import Achievement
from app.models.course import Course
from app.models.document import Document  # noqa: F401
from app.models.email_verification import EmailVerification  # noqa: F401
from app.models.event import Event  # noqa: F401
from app.models.flashcard import Flashcard  # noqa: F401
from app.models.goal import Goal
from app.models.notification import Notification  # noqa: F401
from app.models.question import Question
from app.models.quiz import Quiz
from app.models.quiz_attempt import QuizAttempt  # noqa: F401
from app.models.study_session import StudySession  # noqa: F401
from app.models.user import User  # noqa: F401
from app.db.database import Base
from app.schemas.quiz import QuizAnswer, QuizSubmit


class _Query:
    def __init__(self, first=None, all_items=None):
        self._first = first
        self._all = all_items or []

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._all


class _Session:
    def __init__(self, quiz, questions):
        self.quiz = quiz
        self.questions = questions
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, model):
        if model is Quiz:
            return _Query(first=self.quiz)
        if model is Question:
            return _Query(all_items=self.questions)
        if model is Goal:
            return _Query(all_items=[])
        if model is Achievement:
            return _Query(first=SimpleNamespace(id=1))
        raise AssertionError(f"Unexpected query model: {model}")

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commits += 1

    def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, item):
        item.id = item.id or 1
        item.completed_at = item.completed_at or None

    def close(self):
        pass


class QuizApiTests(unittest.TestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=7)
        self.question = SimpleNamespace(
            id=42,
            question_type="multiple_choice",
            question_text="Soru?",
            option_a="A seçeneği",
            option_b="B seçeneği",
            option_c="C seçeneği",
            option_d="D seçeneği",
            option_e="E seçeneği",
            correct_answer=" B ",
            explanation="Açıklama",
        )
        self.quiz = SimpleNamespace(
            id=3,
            title="Quiz",
            course_id=2,
            document_id=1,
            created_at=None,
            questions=[self.question],
        )

    def _submit(self, answer=None):
        answers = [] if answer is None else [
            QuizAnswer(question_id=self.question.id, answer=answer)
        ]
        db = _Session(self.quiz, [self.question])
        result = submit_quiz(
            self.quiz.id,
            QuizSubmit(answers=answers),
            db,
            self.user,
        )
        return result, db

    def test_correct_answer_is_normalized(self):
        result, db = self._submit("  b ")
        self.assertEqual(result["correct"], 1)
        self.assertTrue(result["results"][0]["is_correct"])
        self.assertEqual(db.commits, 1)

    def test_wrong_answer(self):
        result, _ = self._submit("A")
        self.assertEqual(result["wrong"], 1)
        self.assertFalse(result["results"][0]["is_correct"])

    def test_missing_answer_is_wrong(self):
        result, _ = self._submit()
        self.assertEqual(result["wrong"], 1)
        self.assertFalse(result["results"][0]["is_correct"])

    def test_other_users_quiz_is_not_accessible(self):
        with self.assertRaises(HTTPException) as raised:
            get_quiz(self.quiz.id, _Session(None, []), self.user)
        self.assertEqual(raised.exception.status_code, 404)

    def test_missing_quiz_returns_404_on_submit(self):
        with self.assertRaises(HTTPException) as raised:
            submit_quiz(
                999,
                QuizSubmit(answers=[]),
                _Session(None, []),
                self.user,
            )
        self.assertEqual(raised.exception.status_code, 404)

    def test_get_quiz_hides_answers_and_explanations(self):
        result = get_quiz(self.quiz.id, _Session(self.quiz, []), self.user)
        question = result["questions"][0]
        self.assertNotIn("correct_answer", question)
        self.assertNotIn("explanation", question)


class QuizContextBudgetTests(unittest.TestCase):
    def test_source_chunks_stay_within_context_budget(self):
        chunks = _split_quiz_source(("Quiz içeriği ve açıklama. " * 500).strip())
        self.assertTrue(chunks)
        self.assertTrue(all(len(chunk) <= _QUIZ_CHUNK_CHARS for chunk in chunks))

    def test_context_error_retries_with_smaller_source(self):
        class _Response:
            text = "Context size has been exceeded"

        context_error = RuntimeError("400 response")
        context_error.response = _Response()
        service_error = LMStudioServiceError("LM Studio geçerli bir yanıt döndürmedi.")
        service_error.__cause__ = context_error
        valid_response = json.dumps({
            "questions": [{
                "question_type": "multiple_choice",
                "context_text": None,
                "question_text": "Soru?",
                "option_a": "A",
                "option_b": "B",
                "option_c": "C",
                "option_d": "D",
                "option_e": "E",
                "correct_answer": "A",
                "explanation": "Açıklama",
            }]
        })

        with patch(
            "app.services.ai_service._generate_with_lmstudio",
            side_effect=[service_error, valid_response],
        ) as generate:
            questions = _request_quiz_questions(
                "Kaynak cümlesi. " * 300,
                1,
                "Turkish",
                [],
                allow_retry=False,
            )

        self.assertEqual(len(questions), 1)
        fallback_prompt = generate.call_args_list[1].args[0]
        fallback_source = fallback_prompt.split("SOURCE TEXT:\n", 1)[1].split(
            "\n\nOUTPUT FORMAT:", 1
        )[0]
        self.assertLessEqual(len(fallback_source), _QUIZ_FALLBACK_CHUNK_CHARS)


class QuizFillRoundTests(unittest.TestCase):
    @staticmethod
    def _question(number):
        concepts = {
            1: "algoritma sıralaması",
            2: "veritabanı bütünlüğü",
            3: "ağ güvenliği",
            4: "işletim sistemi çekirdeği",
            5: "yazılım test otomasyonu",
        }
        concept = concepts[number]
        return QuizQuestion(
            question_text=f"{concept} hangi temel işleve sahiptir?",
            option_a=f"{concept} doğru işlevi",
            option_b=f"Alternatif B{number}",
            option_c=f"Alternatif C{number}",
            option_d=f"Alternatif D{number}",
            option_e=f"Alternatif E{number}",
            correct_answer="A",
            explanation=f"{concept} için desteklenen açıklama.",
        )

    def _run_generator(self, requested_count, initial, fill_side_effect):
        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["güvenli kaynak parçası"],
        ), patch(
            "app.services.ai_service._generate_valid_quiz_chunk",
            return_value=(initial, requested_count),
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=fill_side_effect,
        ) as request, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=lambda raw, source: raw if isinstance(raw, QuizQuestion) else None,
        ):
            result = list(generate_quiz_questions(
                "yeterli quiz kaynak metni",
                requested_count,
            ))
        return result, request

    def test_three_valid_initial_questions_are_filled_to_five(self):
        initial = [self._question(index) for index in range(1, 4)]
        result, request = self._run_generator(
            5,
            initial,
            [[self._question(4), self._question(5)]],
        )
        self.assertEqual(len(result), 5)
        self.assertEqual(request.call_count, 1)

    def test_duplicate_question_gets_replacement(self):
        first = self._question(1)
        result, request = self._run_generator(
            2,
            [first],
            [[first], [self._question(2)]],
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(request.call_count, 2)

    def test_validation_rejections_can_be_recovered(self):
        result, request = self._run_generator(
            2,
            [],
            [["invalid", self._question(1)], [self._question(2)]],
        )
        self.assertEqual(len(result), 2)
        self.assertEqual(request.call_count, 2)

    def test_fill_round_limit_is_enforced(self):
        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["güvenli kaynak parçası"],
        ), patch(
            "app.services.ai_service._generate_valid_quiz_chunk",
            return_value=([], 2),
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            return_value=[],
        ) as request:
            with self.assertRaises(LMStudioServiceError):
                list(generate_quiz_questions("kaynak metni", 2))

        self.assertEqual(request.call_count, _QUIZ_MAX_FILL_ROUNDS)


class QuizQualityTests(unittest.TestCase):
    @staticmethod
    def _raw(question_text):
        return {
            "question_type": "multiple_choice",
            "context_text": None,
            "question_text": question_text,
            "option_a": "Kullanıcı fiziksel donanımı görmez",
            "option_b": "Donanım kullanıcı tarafından yönetilir",
            "option_c": "Her işlem çevrim dışı yapılır",
            "option_d": "Yalnızca yerel depolama kullanılır",
            "option_e": "Hizmete ağ üzerinden erişilemez",
            "correct_answer": "A",
            "explanation": "Bulut bilişimde kullanıcı fiziksel donanımı görmez.",
        }

    def test_false_premise_is_rejected(self):
        raw = self._raw(
            "Kullanıcılar fiziksel donanımı gördükleri için hangi durum ortaya çıkar?"
        )
        self.assertIsNone(_validate_quiz_question(
            raw,
            "Bulut bilişimde kullanıcı fiziksel donanımı görmez.",
        ))

    def test_unnatural_turkish_pattern_is_rejected(self):
        raw = self._raw(
            "Bulut bilişimin neden önemli hale geldiği nedir?"
        )
        self.assertIsNone(_validate_quiz_question(
            raw,
            "Bulut bilişim ölçeklenebilir hizmet sağlar.",
        ))

    def test_meta_source_question_is_repaired_and_validated(self):
        raw = self._raw("Metne göre bulut bilişimde kullanıcı neyi görmez?")
        question = _validate_quiz_question_with_meta_repair(
            raw,
            "Bulut bilişimde kullanıcı fiziksel donanımı görmez.",
        )
        self.assertIsNotNone(question)
        self.assertEqual(
            question.question_text,
            "Bulut bilişimde kullanıcı neyi görmez?",
        )

    def test_meta_source_explanation_is_repaired_and_validated(self):
        raw = self._raw("Bulut bilişimde kullanıcı neyi görmez?")
        raw["explanation"] = (
            "Kaynakta belirtildiği gibi, kullanıcı fiziksel donanımı görmez."
        )
        question = _validate_quiz_question_with_meta_repair(
            raw,
            "Bulut bilişimde kullanıcı fiziksel donanımı görmez.",
        )
        self.assertIsNotNone(question)
        self.assertEqual(
            question.explanation,
            "Kullanıcı fiziksel donanımı görmez.",
        )

    def test_unsafe_meta_source_repair_is_rejected(self):
        raw = self._raw("Metne göre nedir?")
        self.assertIsNone(_validate_quiz_question_with_meta_repair(
            raw,
            "Bulut bilişimde kullanıcı fiziksel donanımı görmez.",
        ))

    def test_identical_historical_question_is_duplicate(self):
        question = "Şeffaflık ilkesi neyi gerektirir?"
        self.assertTrue(_is_duplicate_quiz_question(
            question,
            [],
            [question],
        ))

    def test_rephrased_historical_concept_is_duplicate(self):
        self.assertTrue(_is_duplicate_quiz_question(
            "Şeffaflık ilkesine göre kullanıcı neyi bilmelidir?",
            [],
            ["Şeffaflık ilkesi neyi gerektirir?"],
        ))

    def test_different_historical_concept_is_not_duplicate(self):
        self.assertFalse(_is_duplicate_quiz_question(
            "Veri güvenliği hangi korumayı sağlar?",
            [],
            ["Şeffaflık ilkesi neyi gerektirir?"],
        ))

    def test_ambiguous_second_answer_is_rejected(self):
        raw = self._raw("Veri üzerindeki kontrolün kaybına hangi durum yol açar?")
        raw["option_a"] = "Sağlayıcının kullanıcı verisine geniş erişim sağlaması"
        raw["option_e"] = "Kullanıcı verisine geniş sağlayıcı erişiminin bulunması"
        raw["correct_answer"] = "A"
        raw["explanation"] = (
            "Sağlayıcının kullanıcı verisine geniş erişim sağlaması kontrolü azaltır."
        )
        self.assertIsNone(_validate_quiz_question(
            raw,
            "Sağlayıcının kullanıcı verisine geniş erişimi kullanıcı kontrolünü azaltır.",
        ))

    def test_semantic_category_mismatch_is_rejected(self):
        raw = self._raw("Bu durum hangi etik kavram ile ilişkilidir?")
        raw["option_a"] = "Mahremiyet"
        raw["option_b"] = "Verilerin ekonomik kaynak olarak kullanılması"
        raw["option_c"] = "Adalet"
        raw["option_d"] = "Şeffaflık"
        raw["option_e"] = "Güvenlik"
        raw["correct_answer"] = "A"
        self.assertIsNone(_validate_quiz_question(
            raw,
            "Kişisel verilerin korunması mahremiyet ilkesiyle ilişkilidir.",
        ))

    def test_learning_target_duplicate_uses_question_answer_and_explanation(self):
        candidate = QuizQuestion(
            question_text=(
                "Kullanıcının verisinin nerede saklandığını görememesi "
                "hangi etik sorundur?"
            ),
            option_a="Şeffaflık eksikliği",
            option_b="Adalet",
            option_c="Güvenlik",
            option_d="Mahremiyet",
            option_e="Hesap verebilirlik",
            correct_answer="A",
            explanation=(
                "Verinin konumunun kullanıcı tarafından bilinememesi "
                "şeffaflık eksikliği oluşturur."
            ),
        )
        historical = [{
            "question_text": "Verinin tam konumunu bilmemek hangi probleme yol açar?",
            "correct_option": "Şeffaflık eksikliği",
            "explanation": (
                "Kullanıcının veri konumunu görememesi şeffaflığı azaltır."
            ),
        }]
        self.assertTrue(_is_historical_learning_target_duplicate(
            candidate,
            historical,
        ))

    def test_same_explanation_relationship_is_duplicate(self):
        candidate = self._question_for_target(
            "Sağlayıcı erişimi kullanıcı açısından hangi sonuca yol açar?",
            "Kullanıcı kontrolünün azalması",
            "Geniş sağlayıcı erişimi kullanıcının verisi üzerindeki kontrolünü azaltır.",
        )
        historical = [{
            "question_text": "Veri kontrolü hangi durumda kaybedilebilir?",
            "correct_option": "Kontrol kaybı",
            "explanation": (
                "Geniş sağlayıcı erişimi kullanıcının verisi üzerindeki kontrolünü azaltır."
            ),
        }]
        self.assertTrue(_is_historical_learning_target_duplicate(candidate, historical))

    def test_same_correct_concept_with_different_target_is_allowed(self):
        candidate = self._question_for_target(
            "Konum verisinin paylaşılması hangi ilkeyi ilgilendirir?",
            "Mahremiyet",
            "Konum bilgisi kişinin özel yaşamına ilişkin veri içerir.",
        )
        historical = [{
            "question_text": "Sağlık kaydına yetkisiz erişim hangi ilkeyi ihlal eder?",
            "correct_option": "Mahremiyet",
            "explanation": "Sağlık kayıtları hassas kişisel bilgi içerir.",
        }]
        self.assertFalse(_is_historical_learning_target_duplicate(candidate, historical))

    @staticmethod
    def _question_for_target(question_text, correct_option, explanation):
        return QuizQuestion(
            question_text=question_text,
            option_a=correct_option,
            option_b="Şeffaflık",
            option_c="Adalet",
            option_d="Güvenlik",
            option_e="Hesap verebilirlik",
            correct_answer="A",
            explanation=explanation,
        )

    def test_chunk_selection_prefers_less_used_concepts_per_section(self):
        chunks = [
            "Şeffaflık veri konumunun bilinmesini gerektirir.",
            "Güvenlik şifreleme ve erişim denetimi sağlar.",
            "Adalet ayrımcılığın önlenmesini amaçlar.",
            "Kullanıcı kontrolü izin yönetimiyle korunur.",
        ]
        historical = [{
            "question_text": "Şeffaflık neden gereklidir?",
            "correct_option": "Veri konumunun bilinmesi",
            "explanation": "Şeffaflık veri konumunu görünür kılar.",
        }]
        selected = _select_quiz_chunks(chunks, 2, historical)
        self.assertNotEqual(selected[0], chunks[0])


class QuizStreamingTests(unittest.TestCase):
    def setUp(self):
        self.questions = [
            QuizFillRoundTests._question(1),
            QuizFillRoundTests._question(2),
        ]

    def test_difficulty_parameter_is_removed(self):
        self.assertNotIn("difficulty", inspect.signature(generate_quiz_questions).parameters)
        self.assertNotIn("difficulty", inspect.signature(generate_quiz_endpoint).parameters)
        self.assertNotIn("difficulty", inspect.signature(stream_quiz_generation).parameters)

    def test_first_question_priority_batch_requests_one_candidate(self):
        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["kaynak"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=[[self.questions[0]], [self.questions[1]]],
        ) as request, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=lambda raw, source: raw,
        ):
            stream = generate_quiz_questions_stream("kaynak metni", 2)
            self.assertEqual(next(stream), self.questions[0])
            self.assertEqual(next(stream), self.questions[1])
            self.assertEqual(request.call_count, 2)
            self.assertEqual(
                [call.args[1] for call in request.call_args_list],
                [1, 1],
            )

    def test_five_question_priority_batch_call_plan_is_one_two_two(self):
        questions = [QuizFillRoundTests._question(index) for index in range(1, 6)]

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["chunk 1", "chunk 2", "chunk 3"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=[questions[:1], questions[1:3], questions[3:]],
        ) as request, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=lambda raw, source: raw,
        ):
            stream = generate_quiz_questions_stream("kaynak metni", 5)
            self.assertEqual(next(stream), questions[0])
            self.assertEqual(next(stream), questions[1])
            self.assertEqual(next(stream), questions[2])
            self.assertEqual(list(stream), questions[3:])

        requested_sizes = [call.args[1] for call in request.call_args_list]
        self.assertEqual(requested_sizes, [1, 3, 3])

    def test_second_batch_can_win_first_valid_question(self):
        questions = [QuizFillRoundTests._question(index) for index in range(1, 6)]
        first_release = threading.Event()
        second_release = threading.Event()
        first_two_started = threading.Event()
        third_started = threading.Event()
        lock = threading.Lock()
        active = 0
        max_active = 0
        started_chunks = []

        def request(source, requested, *args, **kwargs):
            nonlocal active, max_active
            with lock:
                active += 1
                max_active = max(max_active, active)
                started_chunks.append(source)
                if len(started_chunks) >= 2:
                    first_two_started.set()
                if source == "chunk 3":
                    third_started.set()

            try:
                if source == "chunk 1":
                    first_release.wait(2)
                    return questions[:1]
                if source == "chunk 2":
                    second_release.wait(2)
                    return questions[1:3]
                return questions[3:]
            finally:
                with lock:
                    active -= 1

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["chunk 1", "chunk 2", "chunk 3"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=request,
        ), patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=lambda raw, source: raw,
        ):
            stream = generate_quiz_questions_stream("kaynak metni", 5)
            first_result = []
            consumer = threading.Thread(target=lambda: first_result.append(next(stream)))
            consumer.start()

            self.assertTrue(first_two_started.wait(1))
            self.assertEqual(started_chunks[:2], ["chunk 1", "chunk 2"])
            self.assertEqual(first_result, [])

            # Batch 2 finishes first and now wins the first accepted slot.
            second_release.set()
            consumer.join(1)
            self.assertEqual(first_result, [questions[1]])
            first_release.set()
            self.assertTrue(third_started.wait(1))
            remaining = list(stream)

        accepted_order = [first_result[0], *remaining]
        self.assertEqual(accepted_order[:2], [questions[1], questions[2]])
        self.assertCountEqual(accepted_order, questions)
        self.assertLessEqual(max_active, 2)
        self.assertIn("chunk 3", started_chunks)

    def test_priority_question_streams_while_second_batch_is_still_running(self):
        questions = [QuizFillRoundTests._question(index) for index in range(1, 6)]
        first_release = threading.Event()
        second_release = threading.Event()
        first_two_started = threading.Event()
        third_started = threading.Event()
        started_count = 0
        lock = threading.Lock()

        def request(source, requested, *args, **kwargs):
            nonlocal started_count
            with lock:
                started_count += 1
                if started_count >= 2:
                    first_two_started.set()
            if source == "chunk 1":
                first_release.wait(2)
                return questions[:1]
            if source == "chunk 2":
                second_release.wait(2)
                return questions[1:3]
            third_started.set()
            return questions[3:]

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["chunk 1", "chunk 2", "chunk 3"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=request,
        ), patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=lambda raw, source: raw,
        ):
            stream = generate_quiz_questions_stream("kaynak metni", 5)
            first_result = []
            consumer = threading.Thread(target=lambda: first_result.append(next(stream)))
            consumer.start()

            self.assertTrue(first_two_started.wait(1))
            first_release.set()
            consumer.join(1)

            self.assertEqual(first_result, [questions[0]])
            self.assertTrue(third_started.wait(1))
            self.assertFalse(second_release.is_set())

            second_release.set()
            remaining = list(stream)

        self.assertEqual(
            [first_result[0], *remaining],
            [questions[0], questions[3], questions[4], questions[1], questions[2]],
        )

    def test_concurrent_batch_duplicate_is_rechecked_and_replaced(self):
        questions = [QuizFillRoundTests._question(index) for index in range(1, 4)]

        def request(source, requested, *args, **kwargs):
            if source == "chunk 1":
                return questions[:1]
            if source == "chunk 2":
                return [questions[0], questions[1]]
            return [questions[2]]

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["chunk 1", "chunk 2", "chunk 3"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=request,
        ) as request_mock, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=lambda raw, source: raw,
        ):
            result = list(generate_quiz_questions_stream("kaynak metni", 3))

        self.assertEqual(result, questions)
        self.assertEqual(request_mock.call_count, 3)

    def test_pipeline_batch_plans_for_ten_and_fifteen_questions(self):
        for total, expected_plan in (
            (10, [1, 3, 3, 3, 3, 1]),
            (15, [1, 3, 3, 3, 3, 3, 3, 3]),
        ):
            counter = 0
            requested_sizes = []

            def request(source, requested, *args, **kwargs):
                nonlocal counter
                requested_sizes.append(requested)
                result = []
                for _ in range(requested):
                    counter += 1
                    result.append(QuizQuestion(
                        question_text=f"Benzersiz soru {counter}?",
                        option_a=f"Doğru {counter}",
                        option_b=f"B seçeneği {counter}",
                        option_c=f"C seçeneği {counter}",
                        option_d=f"D seçeneği {counter}",
                        option_e=f"E seçeneği {counter}",
                        correct_answer="A",
                        explanation=f"Benzersiz açıklama {counter}.",
                    ))
                return result

            with patch(
                "app.services.ai_service._split_quiz_source",
                return_value=[f"chunk {index}" for index in range(1, 6)],
            ), patch(
                "app.services.ai_service._request_quiz_questions",
                side_effect=request,
            ), patch(
                "app.services.ai_service._validate_quiz_question",
                side_effect=lambda raw, source: raw,
            ), patch(
                "app.services.ai_service._quiz_duplicate_reason",
                return_value=None,
            ):
                result = list(generate_quiz_questions_stream("kaynak", total))

            self.assertEqual(len(result), total)
            self.assertEqual(requested_sizes, expected_plan)

    def test_final_single_batch_allows_only_one_replacement_call(self):
        questions = [QuizFillRoundTests._question(index) for index in range(1, 5)]

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["chunk 1", "chunk 2", "chunk 3", "chunk 4"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=[
                questions[:1],
                questions[1:3],
                [questions[0]],
                [questions[3]],
            ],
        ) as request, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=lambda raw, source: raw,
        ):
            result = list(generate_quiz_questions_stream("kaynak metni", 4))

        self.assertEqual(result, questions)
        self.assertEqual(
            [call.args[1] for call in request.call_args_list],
            [1, 3, 1, 1],
        )
        self.assertNotEqual(
            request.call_args_list[2].args[0],
            request.call_args_list[3].args[0],
        )

    def test_batch_duplicate_keeps_valid_question_and_replaces_only_missing(self):
        first, second, replacement = [
            QuizFillRoundTests._question(index) for index in range(1, 4)
        ]

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["chunk 1", "chunk 2"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=[[first], [second, second], [replacement]],
        ) as request, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=lambda raw, source: raw,
        ):
            result = list(generate_quiz_questions_stream("kaynak metni", 3))

        self.assertEqual(result, [first, second, replacement])
        self.assertEqual(
            [call.args[1] for call in request.call_args_list],
            [1, 3, 1],
        )

    def test_one_invalid_batch_candidate_streams_other_then_replaces_missing(self):
        first, second, replacement = [
            QuizFillRoundTests._question(index) for index in range(1, 4)
        ]

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["chunk 1", "chunk 2"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=[[first], ["invalid", second], [replacement]],
        ) as request, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=[first, None, second, replacement],
        ):
            stream = generate_quiz_questions_stream("kaynak metni", 3)
            self.assertEqual(next(stream), first)
            self.assertEqual(next(stream), second)
            self.assertEqual(next(stream), replacement)
            self.assertEqual(request.call_count, 3)

    def test_cross_border_questions_are_current_learning_target_duplicates(self):
        first = QuizQualityTests._question_for_target(
            "Verinin Türkiye, Avrupa ve ABD arasında işlenmesindeki sorun nedir?",
            "Uygulanacak hukukun belirsizliği",
            "Sınır ötesi veri işleme hangi ülke hukukunun uygulanacağını belirsizleştirir.",
        )
        second = QuizQualityTests._question_for_target(
            "Veri farklı ülkelerde işlendiğinde hangi hukuki zorluk doğar?",
            "Uygulanacak yasanın belirsizliği",
            "Farklı ülkelerde veri işlenmesi uygulanacak hukuku belirsiz kılar.",
        )
        self.assertEqual(
            _quiz_duplicate_reason(second, [first], []),
            "current_learning_target_duplicate",
        )

    def test_invalid_dedicated_first_candidate_is_not_retried(self):
        def reject(raw, source):
            _quiz_validation_rejection_reason.set("ambiguous_distractor")
            return None

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["chunk 1"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            return_value=["invalid"],
        ) as request, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=reject,
        ):
            with self.assertRaises(LMStudioServiceError):
                list(generate_quiz_questions_stream("kaynak metni", 1))

        self.assertEqual(request.call_count, 1)

    def test_batch_two_first_valid_stops_priority_retry_chain(self):
        first, second, recovery = [
            QuizFillRoundTests._question(index) for index in range(1, 4)
        ]
        priority_release = threading.Event()

        def request(source, requested, *args, **kwargs):
            if source == "chunk 1":
                self.assertTrue(priority_release.wait(1))
                return ["ambiguous"]
            if source == "chunk 2":
                return [first, second]
            return [recovery]

        def validate(raw, source):
            if raw == "ambiguous":
                _quiz_validation_rejection_reason.set("ambiguous_distractor")
                return None
            return raw

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["chunk 1", "chunk 2", "chunk 3"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=request,
        ) as request_mock, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=validate,
        ), self.assertLogs("uvicorn.error.studyflow.quiz", level="INFO") as logs:
            stream = generate_quiz_questions_stream("kaynak metni", 3)
            self.assertEqual(next(stream), first)
            self.assertEqual(next(stream), second)
            priority_release.set()
            self.assertEqual(list(stream), [recovery])

        self.assertEqual(request_mock.call_count, 3)
        self.assertIsNone(request_mock.call_args_list[2].kwargs["rejection_reason"])
        self.assertTrue(any(
            "Quiz priority mode ended first_valid=true batch=2" in message
            for message in logs.output
        ))
        self.assertFalse(any(
            "FIRST_QUESTION_ATTEMPT=2/" in message
            for message in logs.output
        ))

    def test_invalid_worker_a_waits_for_worker_b_without_priority_retry(self):
        first, second, fill = [
            QuizFillRoundTests._question(index) for index in range(1, 4)
        ]
        worker_a_finished = threading.Event()
        worker_b_release = threading.Event()
        fill_started = threading.Event()

        def request(source, requested, *args, **kwargs):
            if source == "chunk 1":
                worker_a_finished.set()
                return ["invalid"]
            if source == "chunk 2":
                self.assertTrue(worker_b_release.wait(1))
                return [first, second]
            fill_started.set()
            return [fill]

        def validate(raw, source):
            if raw == "invalid":
                _quiz_validation_rejection_reason.set("ambiguous_distractor")
                return None
            return raw

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["chunk 1", "chunk 2", "chunk 3"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=request,
        ) as request_mock, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=validate,
        ):
            stream = generate_quiz_questions_stream("kaynak metni", 3)
            first_result = []
            consumer = threading.Thread(
                target=lambda: first_result.append(next(stream))
            )
            consumer.start()

            self.assertTrue(worker_a_finished.wait(1))
            self.assertFalse(fill_started.is_set())
            worker_b_release.set()
            consumer.join(1)

            self.assertEqual(first_result, [first])
            self.assertEqual(next(stream), second)
            self.assertEqual(list(stream), [fill])

        self.assertEqual(request_mock.call_count, 3)

    def test_surplus_valid_duplicate_valid_fills_two_slots_without_replacement(self):
        first, second, third = [
            QuizFillRoundTests._question(index) for index in range(1, 4)
        ]
        regular_batch_release = threading.Event()

        def request(source, requested, *args, **kwargs):
            if source == "chunk 1":
                return [first]
            self.assertTrue(regular_batch_release.wait(1))
            return [second, second, third]

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["chunk 1", "chunk 2", "chunk 3"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=request,
        ) as request_mock, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=lambda raw, source: raw,
        ):
            stream = generate_quiz_questions_stream("kaynak metni", 3)
            self.assertEqual(next(stream), first)
            regular_batch_release.set()
            self.assertEqual(list(stream), [second, third])

        self.assertEqual(request_mock.call_count, 2)
        self.assertEqual(
            [call.args[1] for call in request_mock.call_args_list],
            [1, 3],
        )

    def test_surplus_one_valid_requests_only_one_replacement_candidate(self):
        first, second, replacement = [
            QuizFillRoundTests._question(index) for index in range(1, 4)
        ]

        def validate(raw, source):
            if isinstance(raw, str):
                _quiz_validation_rejection_reason.set("ambiguous_distractor")
                return None
            return raw

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["chunk 1", "chunk 2", "chunk 3"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=[
                [first],
                [second, "invalid 1", "invalid 2"],
                [replacement],
            ],
        ) as request_mock, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=validate,
        ):
            result = list(generate_quiz_questions_stream("kaynak metni", 3))

        self.assertEqual(result, [first, second, replacement])
        self.assertEqual(
            [call.args[1] for call in request_mock.call_args_list],
            [1, 3, 1],
        )

    def test_priority_duplicate_does_not_block_other_worker_valid_question(self):
        duplicate, first, second = [
            QuizFillRoundTests._question(index) for index in range(1, 4)
        ]
        historical = [{
            "question_text": duplicate.question_text,
            "correct_option": duplicate.option_a,
            "explanation": duplicate.explanation,
        }]
        def request(source, requested, *args, **kwargs):
            if source == "chunk 1":
                return [duplicate]
            if source == "chunk 2":
                return [first, second]
            return [QuizFillRoundTests._question(4)]

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["chunk 1", "chunk 2", "chunk 3"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=request,
        ), patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=lambda raw, source: raw,
        ):
            stream = generate_quiz_questions_stream(
                "kaynak metni",
                3,
                previous_questions=historical,
            )
            self.assertEqual(next(stream), first)
            self.assertEqual(next(stream), second)
            self.assertEqual(len(list(stream)), 1)

    def test_repairable_meta_source_candidate_is_yielded_immediately(self):
        raw = QuizQualityTests._raw(
            "Metne göre bulut bilişimde kullanıcı neyi görmez?"
        )
        source = "Bulut bilişimde kullanıcı fiziksel donanımı görmez."

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=[source],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            return_value=[raw],
        ) as request:
            stream = generate_quiz_questions_stream(source, 1)
            question = next(stream)

        self.assertEqual(
            question.question_text,
            "Bulut bilişimde kullanıcı neyi görmez?",
        )
        self.assertEqual(request.call_count, 1)

    def test_duplicate_stream_question_is_replaced(self):
        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["kaynak 1", "kaynak 2", "kaynak 3"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            side_effect=[
                [self.questions[0]],
                [self.questions[0]],
                [self.questions[1]],
            ],
        ) as request, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=lambda raw, source: raw,
        ):
            result = list(generate_quiz_questions_stream("kaynak metni", 2))

        self.assertEqual(result, self.questions)
        self.assertEqual(request.call_count, 3)

    def test_general_historical_learning_target_does_not_block_first_question(self):
        duplicate = QuizQualityTests._question_for_target(
            "Kullanıcının verisinin nerede saklandığını görememesi hangi etik sorundur?",
            "Şeffaflık eksikliği",
            "Veri konumunun bilinememesi şeffaflık eksikliği oluşturur.",
        )
        historical = [{
            "question_text": "Verinin tam konumunu bilmemek hangi probleme yol açar?",
            "correct_option": "Şeffaflık eksikliği",
            "explanation": "Kullanıcının veri konumunu görememesi şeffaflığı azaltır.",
        }]

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["kaynak 1", "kaynak 2"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            return_value=[duplicate],
        ) as request, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=lambda raw, source: raw,
        ):
            result = list(generate_quiz_questions_stream(
                "kaynak metni",
                1,
                previous_questions=historical,
            ))

        self.assertEqual(result, [duplicate])
        self.assertEqual(request.call_count, 1)

    def test_exact_historical_first_question_is_rejected_without_retry(self):
        duplicate = QuizQualityTests._question_for_target(
            "Şeffaflık ilkesi neyi gerektirir?",
            "Bilgilendirme",
            "Şeffaflık kullanıcıya açık bilgi verilmesini gerektirir.",
        )
        historical = [{
            "question_text": duplicate.question_text,
            "correct_option": duplicate.option_a,
            "explanation": duplicate.explanation,
        }]

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["birinci chunk", "ikinci chunk"],
        ), patch(
            "app.services.ai_service._select_quiz_chunks",
            return_value=["birinci chunk", "ikinci chunk"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            return_value=[duplicate],
        ) as request, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=lambda raw, source: raw,
        ):
            with self.assertRaises(LMStudioServiceError):
                list(generate_quiz_questions_stream(
                    "kaynak metni",
                    1,
                    previous_questions=historical,
                ))

        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args_list[0].args[0], "birinci chunk")

    def test_high_textual_similarity_first_question_is_rejected(self):
        candidate = QuizQualityTests._question_for_target(
            "Bulut sistemlerinde veri konumu neden bilinmelidir?",
            "Şeffaflık için",
            "Veri konumunun bilinmesi şeffaflığı destekler.",
        )
        historical = [{
            "question_text": (
                "Bulut sistemlerinde veri konumu niçin bilinmelidir?"
            ),
            "correct_option": "Şeffaflık için",
            "explanation": "Veri konumunun bilinmesi şeffaflığı destekler.",
        }]

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["kaynak"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            return_value=[candidate],
        ) as request, patch(
            "app.services.ai_service._validate_quiz_question",
            return_value=candidate,
        ):
            with self.assertRaises(LMStudioServiceError):
                list(generate_quiz_questions_stream(
                    "kaynak metni",
                    1,
                    previous_questions=historical,
                ))

        self.assertEqual(request.call_count, 1)

    def test_high_historical_count_does_not_block_different_target(self):
        historical = [{
            "question_text": f"Geçmiş öğrenme hedefi {index}",
            "correct_option": f"Eski cevap {index}",
            "explanation": f"Eski ilişki açıklaması {index}",
        } for index in range(12)]

        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["yeni ve güvenli kaynak"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            return_value=[self.questions[0]],
        ), patch(
            "app.services.ai_service._validate_quiz_question",
            return_value=self.questions[0],
        ):
            stream = generate_quiz_questions_stream(
                "kaynak metni",
                1,
                previous_questions=historical,
            )
            self.assertEqual(next(stream), self.questions[0])

    @staticmethod
    async def _read_stream(response):
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        return "".join(chunks)

    def _document_db(self):
        document = SimpleNamespace(
            id=28,
            text="quiz kaynak metni",
            filename="kaynak.pdf",
            course_id=4,
        )

        class _DocumentSession:
            def query(self, model):
                return _Query(first=document)

        return _DocumentSession()

    def test_sse_event_order_and_done_count(self):
        stream_db = _Session(None, [])

        with patch("app.api.quiz.SessionLocal", return_value=stream_db), patch(
            "app.api.quiz.generate_quiz_questions_stream",
            return_value=iter(self.questions),
        ):
            response = stream_quiz_generation(
                28,
                2,
                self._document_db(),
                SimpleNamespace(id=7),
            )
            body = asyncio.run(self._read_stream(response))

        event_names = [
            block.splitlines()[0].removeprefix("event: ")
            for block in body.strip().split("\n\n")
        ]
        self.assertEqual(
            event_names,
            ["status", "question", "progress", "question", "progress", "done"],
        )
        self.assertEqual(stream_db.commits, 1)

    def test_five_questions_finish_with_done(self):
        stream_db = _Session(None, [])
        questions = [QuizFillRoundTests._question(index) for index in range(1, 6)]

        with patch("app.api.quiz.SessionLocal", return_value=stream_db), patch(
            "app.api.quiz.generate_quiz_questions_stream",
            return_value=iter(questions),
        ):
            response = stream_quiz_generation(
                28,
                5,
                self._document_db(),
                SimpleNamespace(id=7),
            )
            body = asyncio.run(self._read_stream(response))

        self.assertEqual(body.count("event: question"), 5)
        self.assertEqual(body.count("event: progress"), 5)
        self.assertEqual(body.count("event: done"), 1)

    def test_stream_failure_does_not_persist_partial_quiz(self):
        stream_db = _Session(None, [])

        def failing_questions():
            yield self.questions[0]
            raise LMStudioServiceError("Quiz soruları oluşturulamadı.")

        with patch("app.api.quiz.SessionLocal", return_value=stream_db), patch(
            "app.api.quiz.generate_quiz_questions_stream",
            return_value=failing_questions(),
        ):
            response = stream_quiz_generation(
                28,
                2,
                self._document_db(),
                SimpleNamespace(id=7),
            )
            body = asyncio.run(self._read_stream(response))

        self.assertIn("event: error", body)
        self.assertNotIn("event: done", body)
        self.assertEqual(stream_db.commits, 0)
        self.assertEqual(stream_db.rollbacks, 1)
        self.assertEqual(stream_db.added, [])


class CrossQuizDatabaseIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(
            self.engine,
            tables=[
                User.__table__,
                Course.__table__,
                Document.__table__,
                Quiz.__table__,
                Question.__table__,
            ],
        )
        self.session = sessionmaker(bind=self.engine)()

        user = User(username="integration", email="i@example.com", password="x")
        course = Course(name="Ders", owner=user)
        document = Document(
            filename="bulut.pdf",
            file_path="unused.pdf",
            text="Bulut sistemlerinde şeffaflık ve güvenlik önemlidir.",
            course=course,
        )
        quiz = Quiz(title="Quiz A", course=course, document=document)
        question = Question(
            quiz=quiz,
            question_type="multiple_choice",
            question_text=(
                "Bulut sistemlerinde kullanıcıların verinin tam konumunu "
                "bilmemesi hangi probleme işaret eder?"
            ),
            option_a="Şeffaflık eksikliği",
            option_b="Adalet",
            option_c="Güvenlik",
            option_d="Mahremiyet",
            option_e="Hesap verebilirlik",
            correct_answer="A",
            explanation=(
                "Verinin konumunun bilinememesi şeffaflık eksikliği oluşturur."
            ),
        )
        self.session.add(question)
        self.session.commit()
        self.document_id = document.id

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def test_real_query_history_rejects_exact_first_candidate_without_retry(self):
        history = _get_previous_document_questions(
            self.session,
            self.document_id,
        )
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["correct_option"], "Şeffaflık eksikliği")

        duplicate = QuizQualityTests._question_for_target(
            history[0]["question_text"],
            history[0]["correct_option"],
            history[0]["explanation"],
        )
        with patch(
            "app.services.ai_service._split_quiz_source",
            return_value=["güvenli kaynak 1", "güvenli kaynak 2"],
        ), patch(
            "app.services.ai_service._request_quiz_questions",
            return_value=[duplicate],
        ) as request, patch(
            "app.services.ai_service._validate_quiz_question",
            side_effect=lambda raw, source: raw,
        ):
            with self.assertRaises(LMStudioServiceError):
                list(generate_quiz_questions_stream(
                    "güvenli kaynak",
                    1,
                    previous_questions=history,
                ))

        self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
