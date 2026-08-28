import json
import logging
import re
import time
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
    model: Optional[str] = None,
):
    """
    Özet veya diğer LM Studio özelliklerinde kullanılabilecek
    genel streaming istemcisi.

    Quiz kendi streaming sistemini
    quiz_generation_service.py içinde kullanıyor.
    """

    payload = {
        "model": model or LMSTUDIO_SUMMARY_MODEL,
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

class FlashcardItem(BaseModel):
    question: str
    answer: str


class FlashcardResponse(BaseModel):
    flashcards: list[FlashcardItem]


_flashcard_logger = logging.getLogger(
    "uvicorn.error.studyflow.flashcards"
)
_FLASHCARD_MAX_REFILLS = 2
_FLASHCARD_MAX_QUESTION_LENGTH = 500
_FLASHCARD_MAX_ANSWER_LENGTH = 2000


def _extract_complete_json_objects(
    buffer: str,
) -> tuple[list[str], str]:
    """
    Stream buffer'ındaki tamamlanmış üst seviye JSON objelerini ayırır.

    String içindeki süslü parantezleri ve escape edilmiş tırnakları JSON
    sınırı olarak değerlendirmez. Tamamlanmamış son obje sonraki chunk için
    buffer'da tutulur.
    """
    objects: list[str] = []
    object_start: Optional[int] = None
    depth = 0
    in_string = False
    escaped = False

    for index, character in enumerate(buffer):
        if object_start is None:
            if character == "{":
                object_start = index
                depth = 1
                in_string = False
                escaped = False
            continue

        if escaped:
            escaped = False
            continue

        if in_string and character == "\\":
            escaped = True
            continue

        if character == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                objects.append(
                    buffer[object_start:index + 1]
                )
                object_start = None

    remainder = (
        buffer[object_start:]
        if object_start is not None
        else ""
    )
    return objects, remainder


def _normalize_flashcard_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _validate_streamed_flashcard(
    value: object,
    seen_questions: set[str],
) -> Optional[FlashcardItem]:
    if not isinstance(value, dict):
        return None

    question = value.get("question")
    answer = value.get("answer")

    if not isinstance(question, str) or not isinstance(answer, str):
        return None

    question = _normalize_flashcard_text(question)
    answer = _normalize_flashcard_text(answer)

    if not question or not answer:
        return None

    if (
        len(question) > _FLASHCARD_MAX_QUESTION_LENGTH
        or len(answer) > _FLASHCARD_MAX_ANSWER_LENGTH
    ):
        return None

    question_key = question.casefold()
    if question_key in seen_questions:
        return None

    seen_questions.add(question_key)
    return FlashcardItem(
        question=question,
        answer=answer,
    )


def generate_flashcards_stream(
    text: str,
    flashcard_count: int = 10,
):
    if not text or not text.strip():
        raise ValueError(
            "Flashcard oluşturmak için kaynak metin bulunamadı."
        )

    if flashcard_count < 1 or flashcard_count > 30:
        raise ValueError(
            "Flashcard sayısı 1 ile 30 arasında olmalıdır."
        )

    max_context_chars = 18000

    if len(text) <= max_context_chars:
        context = text
    else:
        chunk_size = max_context_chars // 3

        start_chunk = text[:chunk_size]

        middle_start = max(
            0,
            (len(text) // 2) - (chunk_size // 2),
        )

        middle_chunk = text[
            middle_start:middle_start + chunk_size
        ]

        end_chunk = text[-chunk_size:]

        context = (
            start_chunk
            + "\n\n--- MIDDLE SECTION ---\n\n"
            + middle_chunk
            + "\n\n--- FINAL SECTION ---\n\n"
            + end_chunk
        )

    started_at = time.perf_counter()
    first_card_seconds: Optional[float] = None
    accepted_cards: list[FlashcardItem] = []
    seen_questions: set[str] = set()
    rejected_cards = 0
    lm_calls = 0
    refill_calls = 0

    try:
        for call_index in range(_FLASHCARD_MAX_REFILLS + 1):
            missing_count = flashcard_count - len(accepted_cards)
            if missing_count <= 0:
                break

            if call_index > 0:
                refill_calls += 1

            lm_calls += 1
            excluded_questions = "\n".join(
                f"- {card.question}"
                for card in accepted_cards
            ) or "- None"

            prompt = f"""
/no_think

Create EXACTLY {missing_count} high-quality flashcards from the course material.

RULES:
- Use ONLY information from the course material.
- Write in the same language as the source material.
- Each card must cover a different important concept.
- Questions must be clear, specific and suitable for exam preparation.
- Answers must be concise and directly answer the question.
- Do not repeat any excluded question.
- Output JSON Lines only: one complete JSON object per line.
- Do not output an array, wrapper object, markdown, numbering or commentary.

Each line must have exactly this shape:
{{"question":"...","answer":"..."}}

EXCLUDED QUESTIONS:
{excluded_questions}

COURSE MATERIAL:
{context}
"""

            buffer = ""
            num_predict = min(
                4000,
                max(500, missing_count * 180),
            )

            for chunk in _generate_with_lmstudio_stream(
                prompt,
                num_predict=num_predict,
                model=LMSTUDIO_SUMMARY_MODEL,
            ):
                buffer += chunk
                raw_objects, buffer = (
                    _extract_complete_json_objects(buffer)
                )

                for raw_object in raw_objects:
                    try:
                        value = json.loads(raw_object)
                    except json.JSONDecodeError:
                        rejected_cards += 1
                        continue

                    card = _validate_streamed_flashcard(
                        value,
                        seen_questions,
                    )
                    if card is None:
                        rejected_cards += 1
                        continue

                    accepted_cards.append(card)
                    if first_card_seconds is None:
                        first_card_seconds = (
                            time.perf_counter() - started_at
                        )

                    yield card

                    if len(accepted_cards) >= flashcard_count:
                        break

                if len(accepted_cards) >= flashcard_count:
                    break

        if len(accepted_cards) != flashcard_count:
            raise LMStudioServiceError(
                f"LM Studio {flashcard_count} yerine "
                f"{len(accepted_cards)} geçerli flashcard oluşturdu."
            )
    finally:
        total_seconds = time.perf_counter() - started_at
        _flashcard_logger.info(
            "FLASHCARD PERF requested=%s first_card_seconds=%s "
            "accepted_cards=%s rejected_cards=%s lm_calls=%s "
            "refill_calls=%s total_seconds=%.3f",
            flashcard_count,
            (
                f"{first_card_seconds:.3f}"
                if first_card_seconds is not None
                else "none"
            ),
            len(accepted_cards),
            rejected_cards,
            lm_calls,
            refill_calls,
            total_seconds,
        )

def generate_flashcards(
    text: str,
    flashcard_count: int = 10,
) -> FlashcardResponse:

    if not text or not text.strip():
        raise ValueError("Flashcard oluşturmak için kaynak metin bulunamadı.")

    if flashcard_count < 1 or flashcard_count > 30:
        raise ValueError("Flashcard sayısı 1 ile 30 arasında olmalıdır.")

    max_context_chars = 18000

    if len(text) <= max_context_chars:
        context = text
    else:
        chunk_size = max_context_chars // 3

        start_chunk = text[:chunk_size]

        middle_start = max(
            0,
            (len(text) // 2) - (chunk_size // 2),
        )
        middle_chunk = text[
            middle_start:middle_start + chunk_size
        ]

        end_chunk = text[-chunk_size:]

        context = (
            start_chunk
            + "\n\n--- MIDDLE SECTION ---\n\n"
            + middle_chunk
            + "\n\n--- FINAL SECTION ---\n\n"
            + end_chunk
        )

    schema = FlashcardResponse.model_json_schema()

    prompt = f"""
/no_think

Create EXACTLY {flashcard_count} high-quality flashcards from the course material below.

RULES:
- Use ONLY information from the course material.
- Do not invent or add outside information.
- Write in the same language as the source material.
- Create exactly {flashcard_count} flashcards.
- Each flashcard must cover a different important concept.
- Prefer important definitions, causes, effects, dates, people, events,
  processes, comparisons and key facts.
- Questions must be clear, specific and suitable for exam preparation.
- Avoid duplicate or nearly identical questions.
- Avoid overly broad questions.
- Answers must be concise and directly answer the question.
- Do not include unnecessary information.
- Return valid JSON only.
- Do not use markdown or explanations outside the JSON.
- Prefer active-recall questions over simple recognition questions.
- Avoid one-word answers unless the question specifically asks for a name, date, or single fact.
- When the source contains multiple important items, include the important items instead of only one.
- Answers should contain enough key information to fully answer the question.

COURSE MATERIAL:

{context}

Return ONLY:

{{
    "flashcards": [
        {{
            "question": "...",
            "answer": "..."
        }}
    ]
}}
"""

    num_predict = min(
    6000,
    max(1200, flashcard_count * 300),
)

    raw_response = _generate_with_lmstudio(
        prompt,
        json_schema=schema,
        num_predict=num_predict,
        model=LMSTUDIO_QUIZ_MODEL,
    )

    try:
        data = json.loads(raw_response)
        result = FlashcardResponse.model_validate(data)

    except (json.JSONDecodeError, ValueError) as error:
        print("FLASHCARD RAW RESPONSE:")
        print(raw_response)
        print("FLASHCARD PARSE ERROR:")
        print(repr(error))

        raise LMStudioServiceError(
        "LM Studio geçerli Flashcard JSON'u döndürmedi."
        ) from error

    if len(result.flashcards) != flashcard_count:
        raise LMStudioServiceError(
            f"Yapay zeka {flashcard_count} kart yerine "
            f"{len(result.flashcards)} kart oluşturdu."
        )

    for card in result.flashcards:
        if not card.question.strip() or not card.answer.strip():
            raise LMStudioServiceError(
                "Yapay zeka boş Flashcard alanı oluşturdu."
            )

    return result


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
