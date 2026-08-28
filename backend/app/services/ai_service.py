import json
import re
from typing import Literal, Optional

import httpx
from pydantic import BaseModel


# =========================================================
# LOCAL AI CONFIG
# =========================================================

LMSTUDIO_BASE_URL = "http://host.docker.internal:1234"

# Özetleme modeli
LMSTUDIO_SUMMARY_MODEL = "gemma-3-12b-it-qat"

# Quiz modeli
LMSTUDIO_QUIZ_MODEL = "qwen3-8b"


# =========================================================
# ERRORS
# =========================================================

class LMStudioServiceError(RuntimeError):
    """LM Studio servisinden kontrollü olarak dönen hata."""


# =========================================================
# LM STUDIO CLIENT
# =========================================================

def _generate_with_lmstudio(
    prompt: str,
    *,
    json_response: bool = False,
    json_schema: Optional[dict] = None,
    num_predict: int = 1800,
    model: Optional[str] = None,
) -> str:
    selected_model = model or LMSTUDIO_SUMMARY_MODEL

    payload = {
        "model": selected_model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0.1,
        "max_tokens": num_predict,
        "stream": False,
    }

    if json_schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "structured_response",
                "schema": json_schema,
            },
        }

    elif json_response:
        payload["response_format"] = {
            "type": "json_object",
        }

    try:
        response = httpx.post(
            f"{LMSTUDIO_BASE_URL}/v1/chat/completions",
            json=payload,
            timeout=300.0,
        )

        response.raise_for_status()
        data = response.json()

    except httpx.HTTPStatusError as error:
        print(
            "LM Studio HTTP hatası:",
            error.response.status_code,
            error.response.text,
        )

        raise LMStudioServiceError(
            "LM Studio geçerli bir yanıt döndürmedi."
        ) from error

    except httpx.RequestError as error:
        print(
            "LM Studio bağlantı hatası:",
            repr(error),
        )

        raise LMStudioServiceError(
            "LM Studio servisine ulaşılamıyor."
        ) from error

    except (json.JSONDecodeError, ValueError) as error:
        raise LMStudioServiceError(
            "LM Studio yanıtı okunamadı."
        ) from error

    generated_text = (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content")
    )

    if (
        not isinstance(generated_text, str)
        or not generated_text.strip()
    ):
        raise LMStudioServiceError(
            "LM Studio boş yanıt oluşturdu."
        )

    return generated_text.strip()


def _generate_with_lmstudio_stream(
    prompt: str,
    *,
    num_predict: int = 850,
):
    """
    Özet veya diğer LM Studio özelliklerinde kullanılabilecek
    genel streaming istemcisi.

    Quiz kendi streaming sistemini
    quiz_generation_service.py içinde kullanıyor.
    """

    payload = {
        "model": LMSTUDIO_SUMMARY_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": 0.1,
        "max_tokens": num_predict,
        "stream": True,
    }

    try:
        with httpx.stream(
            "POST",
            f"{LMSTUDIO_BASE_URL}/v1/chat/completions",
            json=payload,
            timeout=httpx.Timeout(
                300.0,
                connect=30.0,
            ),
        ) as response:

            if response.is_error:
                response.read()

            response.raise_for_status()

            for line in response.iter_lines():

                if not line.startswith("data:"):
                    continue

                event_data = (
                    line
                    .removeprefix("data:")
                    .strip()
                )

                if event_data == "[DONE]":
                    return

                if not event_data:
                    continue

                try:
                    data = json.loads(event_data)

                except json.JSONDecodeError as error:
                    raise LMStudioServiceError(
                        "LM Studio streaming yanıtı okunamadı."
                    ) from error

                choice = data.get(
                    "choices",
                    [{}],
                )[0]

                delta = (
                    choice.get("delta")
                    or {}
                )

                message = (
                    choice.get("message")
                    or {}
                )

                content = (
                    delta.get("content")
                    or message.get("content")
                )

                if (
                    isinstance(content, str)
                    and content
                ):
                    yield content

    except httpx.HTTPStatusError as error:

        print(
            "LM Studio streaming HTTP hatası:",
            error.response.status_code,
            error.response.text,
        )

        raise LMStudioServiceError(
            "LM Studio geçerli bir streaming yanıtı döndürmedi."
        ) from error

    except httpx.RequestError as error:

        print(
            "LM Studio streaming bağlantı hatası:",
            repr(error),
        )

        raise LMStudioServiceError(
            "LM Studio streaming servisine ulaşılamıyor."
        ) from error


def _clean_json_response(
    raw_response: str,
) -> str:
    """
    LM Studio yanıtında varsa markdown JSON bloklarını temizler.
    """

    cleaned = raw_response.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned,
        )

    return cleaned.strip()


# =========================================================
# PDF SUMMARY
# =========================================================

def generate_summary(text: str) -> str:
    """
    Kısa metinler için doğrudan özet üretir.

    Uzun PDF'lerde asıl özetleme akışı
    document_topic_service.py tarafından yapılacaktır.
    """

    if not text or not text.strip():
        raise ValueError(
            "Özetlenecek metin boş."
        )

    prompt = f"""
Sen StudyFlow uygulamasının akademik özetleme asistanısın.

Aşağıdaki ders içeriğini yalnızca verilen bilgilerden yararlanarak
Türkçe ve anlaşılır biçimde özetle.

Kurallar:
- Kaynakta bulunmayan bilgi ekleme.
- Önemli kavramları atlama.
- Tanımları koru.
- Teknik terimleri koru.
- Gereksiz tekrarları kaldır.
- Öğrencinin ders çalışabileceği şekilde yaz.
- Doğal Türkçe kullan.

DERS İÇERİĞİ:

{text}
"""

    return _generate_with_lmstudio(
        prompt,
        num_predict=1800,
        model=LMSTUDIO_SUMMARY_MODEL,
    )


# =========================================================
# QUIZ RESPONSE MODELS
# =========================================================

class QuizQuestion(BaseModel):
    question_type: Literal[
        "multiple_choice"
    ] = "multiple_choice"

    context_text: Optional[str] = None

    question_text: str

    option_a: str
    option_b: str
    option_c: str
    option_d: str
    option_e: str

    correct_answer: Literal[
        "A",
        "B",
        "C",
        "D",
        "E",
    ]

    explanation: str


class QuizResponse(BaseModel):
    questions: list[QuizQuestion]


# =========================================================
# PRODUCTION QUIZ
# =========================================================

def _generate_quiz_questions_production(
    text: str,
    question_count: int,
    previous_questions: Optional[
        list[object]
    ] = None,
):
    """
    Production quiz oluşturma akışı.

    Gerçek quiz üretimi, evidence seçimi,
    streaming, validation ve refill işlemleri
    quiz_generation_service.py içindedir.
    """

    from app.services.quiz_generation_service import (
        LMStudioError as QuizGenerationError,
        generate_production_quiz,
        normalize_text as normalize_quiz_text,
    )

    if not text or not text.strip():
        raise LMStudioServiceError(
            "Quiz soruları oluşturulamadı."
        )

    if question_count < 1:
        raise LMStudioServiceError(
            "Soru sayısı en az 1 olmalıdır."
        )

    previous_texts: set[str] = set()

    for item in previous_questions or []:

        if isinstance(item, str):
            value = item

        elif isinstance(item, dict):
            value = item.get(
                "question_text"
            )

        else:
            value = getattr(
                item,
                "question_text",
                None,
            )

        if (
            isinstance(value, str)
            and value.strip()
        ):
            previous_texts.add(
                normalize_quiz_text(
                    value
                )
            )

    labels = "ABCDE"

    try:

        for question in generate_production_quiz(
            text,
            question_count,
            base_url=LMSTUDIO_BASE_URL,
            model=LMSTUDIO_QUIZ_MODEL,
            previous_question_texts=previous_texts,
        ):

            options = question.options

            yield QuizQuestion(
                question_type="multiple_choice",
                context_text=None,
                question_text=question.question_text,
                option_a=options[0],
                option_b=options[1],
                option_c=options[2],
                option_d=options[3],
                option_e=options[4],
                correct_answer=(
                    labels[
                        question.correct_index
                    ]
                ),
                explanation=(
                    "Doğru cevap kaynak metindeki "
                    "ilgili bilgiyle doğrudan "
                    "desteklenmektedir."
                ),
            )

    except QuizGenerationError as error:

        raise LMStudioServiceError(
            str(error)
        ) from error


# =========================================================
# QUIZ PUBLIC FUNCTIONS
# =========================================================

def generate_quiz_questions(
    text: str,
    question_count: int = 10,
    previous_questions: Optional[
        list[object]
    ] = None,
):
    """
    Quiz sorularını production quiz servisi üzerinden üretir.
    """

    yield from _generate_quiz_questions_production(
        text,
        question_count,
        previous_questions,
    )


def generate_quiz_questions_stream(
    text: str,
    question_count: int = 10,
    previous_questions: Optional[
        list[object]
    ] = None,
):
    """
    Soruları hazır oldukça API katmanına iletir.

    Gerçek LM Studio streaming ve JSON object parsing
    quiz_generation_service.py içinde yapılır.
    """

    yield from _generate_quiz_questions_production(
        text,
        question_count,
        previous_questions,
    )


def generate_quiz(
    text: str,
    question_count: int = 10,
    previous_questions: Optional[
        list[object]
    ] = None,
) -> QuizResponse:

    questions = list(
        generate_quiz_questions(
            text,
            question_count,
            previous_questions=previous_questions,
        )
    )

    return QuizResponse(
        questions=questions
    )


# =========================================================
# GEÇİCİ OLARAK DEVRE DIŞI AI ÖZELLİKLERİ
# =========================================================

def generate_flashcards(
    *args,
    **kwargs,
):
    raise LMStudioServiceError(
        "Flashcard oluşturma özelliği yeniden geliştiriliyor."
    )


def generate_study_recommendation(
    *args,
    **kwargs,
):
    return None


def ask_ai_about_document(
    *args,
    **kwargs,
):
    raise LMStudioServiceError(
        "PDF sohbet özelliği yeniden geliştiriliyor."
    )


def generate_study_plan(
    *args,
    **kwargs,
):
    raise LMStudioServiceError(
        "Çalışma planı özelliği yeniden geliştiriliyor."
    )


class PlannerServiceUnavailableError(Exception):
    pass