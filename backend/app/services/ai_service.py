from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextvars import ContextVar
from difflib import SequenceMatcher
import logging
import threading
import time
from typing import Literal, Optional

import httpx
import json
import re
from pydantic import BaseModel


# =========================================================
# LOCAL AI CONFIG
# =========================================================

LMSTUDIO_BASE_URL = "http://host.docker.internal:1234"

# Özetleme için kullandığımız model
LMSTUDIO_SUMMARY_MODEL = "gemma-3-12b-it-qat"


# Quiz için kullandığımız model

LMSTUDIO_QUIZ_MODEL = "qwen3-8b"

logger = logging.getLogger("uvicorn.error.studyflow.quiz")
_quiz_validation_rejection_reason: ContextVar[Optional[str]] = ContextVar(
    "quiz_validation_rejection_reason",
    default=None,
)

# =========================================================
# ERRORS
# =========================================================

class LMStudioServiceError(RuntimeError):
    """LM Studio servisinden kontrollü olarak dönen hata."""
    pass


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
            timeout=httpx.Timeout(300.0, connect=30.0),
        ) as response:
            if response.is_error:
                response.read()

            response.raise_for_status()

            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue

                event_data = line.removeprefix("data:").strip()

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

                choice = data.get("choices", [{}])[0]
                delta = choice.get("delta") or {}
                message = choice.get("message") or {}
                content = (
                    delta.get("content")
                    or message.get("content")
                )

                if isinstance(content, str) and content:
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


# =========================================================
# JSON CLEANER
# =========================================================

def _clean_json_response(raw_response: str) -> str:

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

    cleaned = cleaned.strip()

    try:
        _, json_end = json.JSONDecoder().raw_decode(cleaned)
        return cleaned[:json_end].strip()

    except json.JSONDecodeError:
        return cleaned


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
        raise ValueError("Özetlenecek metin boş.")

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
    )


# =========================================================
# GEÇİCİ OLARAK DEVRE DIŞI AI ÖZELLİKLERİ
# =========================================================

class QuizQuestion(BaseModel):
    question_type: Literal["multiple_choice"] = "multiple_choice"
    context_text: Optional[str] = None
    question_text: str
    option_a: str
    option_b: str
    option_c: str
    option_d: str
    option_e: str
    correct_answer: Literal["A", "B", "C", "D", "E"]
    explanation: str


class QuizResponse(BaseModel):
    questions: list[QuizQuestion]


_QUIZ_CHUNK_CHARS = 2400
_QUIZ_FALLBACK_CHUNK_CHARS = 1400
_QUIZ_MAX_FILL_ROUNDS = 3
_QUIZ_PREVIOUS_PROMPT_LIMIT = 12
_QUIZ_STREAM_BATCH_SIZE = 2
_QUIZ_STOP_WORDS = {
    "a", "an", "and", "are", "as", "for", "from", "in", "is", "of",
    "or", "that", "the", "this", "to", "with",
    "ama", "bir", "bu", "da", "de", "gibi", "için", "ile", "ise",
    "olan", "olarak", "ve", "veya",
}
_BANNED_QUIZ_OPTIONS = {
    "all", "all of the above", "none", "none of the above",
    "hepsi", "hepsi doğru", "hiçbiri", "yukarıdakilerin hepsi",
}
_META_SOURCE_REFERENCE = re.compile(
    r"\b(?:metne\s+göre|metinde(?:\s+(?:belirtildiği\s+gibi|"
    r"ifade\s+edilmiştir|yer\s+almaktadır))?|belgeye\s+göre|belgede|"
    r"kaynağa\s+göre|kaynakta|yukarıdaki\s+metne\s+göre|bu\s+metinde|"
    r"bu\s+belgede|verilen\s+metinde|source\s+text['’]?e\s+göre)\b",
    re.IGNORECASE,
)
_META_SOURCE_REPAIR_PATTERNS = (
    re.compile(
        r"^\s*(?:(?:metinde|kaynakta|belgede|bu\s+belgede)\s+"
        r"(?:belirtilmiştir|ifade\s+edilir|ifade\s+edilmiştir)\s*(?:ki)?|"
        r"metinde\s+(?:belirtildiği|ifade\s+edildiği)\s+gibi|"
        r"kaynakta\s+(?:belirtildiği|ifade\s+edildiği)\s+gibi|"
        r"metne\s+göre|yukarıdaki\s+metne\s+göre|"
        r"verilen\s+metinde|bu\s+belgede|belgede)"
        r"\s*[,;:\-–—]?\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:kaynakta|metinde|belgede|bu\s+belgede)\s+"
        r"(?:belirtilen|ifade\s+edilen)\s+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:metne\s+göre|yukarıdaki\s+metne\s+göre|"
        r"verilen\s+metinde|bu\s+belgede|kaynakta|belgede|metinde)\b"
        r"\s*[,;:\-–—]?\s*",
        re.IGNORECASE,
    ),
)
_REFERENCE_HEADING = re.compile(
    r"^\s*(?:#{1,6}\s*|\d+[.)]\s*)?"
    r"(?:kaynakça|kaynaklar|references|bibliography|further\s+reading)"
    r"\s*[:\-–—]?\s*$",
    re.IGNORECASE,
)
_REFERENCE_LINE = re.compile(
    r"(?:https?://|www\.|\bdoi\s*:|\barxiv\s*:)",
    re.IGNORECASE,
)
_ACADEMIC_REFERENCE_LINE = re.compile(
    r"(?:\bet\s+al\.|\bvd\.|"
    r"(?:&|,\s*[A-ZÇĞİÖŞÜ]\.)[^\n]{0,120}\(\s*(?:19|20)\d{2}[a-z]?\s*\)|"
    r"^[A-ZÇĞİÖŞÜ][^,]{2,40},\s+[A-ZÇĞİÖŞÜ][^\d]{2,60}"
    r"\b(?:19|20)\d{2}\b)",
    re.IGNORECASE,
)
_QUIZ_RELATION_MARKERS = {
    "amaç", "avant", "etki", "fark", "işlev", "neden", "özellik",
    "sonuç", "süreç", "uygula", "yarar",
}
_QUIZ_CONCEPT_ALIASES = {
    "bilme": "knowledge_visibility",
    "görem": "knowledge_visibility",
    "haberd": "knowledge_visibility",
    "konum": "data_location",
    "nerede": "data_location",
    "saklan": "data_location",
    "tutul": "data_location",
    "şeffaf": "transparency",
    "kontro": "control",
    "hakimi": "control",
    "mahrem": "privacy",
    "gizlil": "privacy",
    "ülke": "cross_border",
    "türkiy": "cross_border",
    "avrupa": "cross_border",
    "işlen": "data_processing",
    "hukuk": "applicable_law",
    "mevzua": "applicable_law",
    "yasa": "applicable_law",
}
_SIMPLE_ANTONYM_PAIRS = (
    ("mümkün", "imkansız"),
    ("artar", "azalır"),
    ("artmıştır", "azalmıştır"),
    ("artırır", "azaltır"),
    ("kazanmıştır", "kaybetmiştir"),
    ("sağlar", "engeller"),
    ("vardır", "yoktur"),
)
_UNNATURAL_QUESTION_PATTERNS = (
    re.compile(r"\bneden\s+.+\s+(?:olduğu|geldiği)\s+nedir\b", re.IGNORECASE),
    re.compile(r"\b(?:nedeni|sebebi)\s+nedir\s+(?:diye|olarak)\b", re.IGNORECASE),
)
_ASSERTIVE_PREMISE_MARKERS = re.compile(
    r"\b(?:için|nedeniyle|sebebiyle|dolayı|olduğundan|sayesinde|sonucunda)\b",
    re.IGNORECASE,
)
_CATEGORY_QUESTION_PATTERN = re.compile(
    r"\bhangi\s+(?:etik\s+)?(?:ilke|kavram|problem|sorun)\w*",
    re.IGNORECASE,
)
_CATEGORY_OPTION_ACTION_PATTERN = re.compile(
    r"\b\w+(?:ması|mesi|abilmesi|ebilmesi)\b",
    re.IGNORECASE,
)
_QUESTION_ANSWER_OPPOSITIONS = (
    (
        re.compile(r"\bgör(?:ür|dü|dük|en|mektedir)\w*", re.IGNORECASE),
        re.compile(r"\bgörm(?:ez|edi|eyen|em|üyor)\w*", re.IGNORECASE),
    ),
    (
        re.compile(r"\b(?:artar|artırır|yükselir)\w*", re.IGNORECASE),
        re.compile(r"\b(?:azalır|azaltır|düşer)\w*", re.IGNORECASE),
    ),
    (
        re.compile(r"\b(?:vardır|mevcuttur|bulunur)\w*", re.IGNORECASE),
        re.compile(r"\b(?:yoktur|bulunmaz)\w*", re.IGNORECASE),
    ),
    (
        re.compile(r"\b(?:zorundadır|gereklidir)\w*", re.IGNORECASE),
        re.compile(r"\b(?:zorunda\s+değildir|gerekmez)\w*", re.IGNORECASE),
    ),
)


def _normalize_quiz_text(value: str) -> str:
    return " ".join(
        re.sub(r"[^\w\s]", " ", value.casefold()).split()
    )


def _prepare_quiz_source(text: str) -> str:
    content_lines = []

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()

        if _REFERENCE_HEADING.match(line):
            break

        if (
            not line
            or _REFERENCE_LINE.search(line)
            or _ACADEMIC_REFERENCE_LINE.search(line)
        ):
            continue

        content_lines.append(line)

    return "\n".join(content_lines).strip()


def _split_quiz_source(text: str) -> list[str]:
    cleaned_text = _prepare_quiz_source(text)

    if not cleaned_text:
        return []

    chunks = []
    remaining = cleaned_text

    while len(remaining) > _QUIZ_CHUNK_CHARS:
        boundary_start = int(_QUIZ_CHUNK_CHARS * 0.75)
        boundary = max(
            remaining.rfind(marker, boundary_start, _QUIZ_CHUNK_CHARS)
            for marker in (". ", "! ", "? ", "\n")
        )

        if boundary < boundary_start:
            boundary = remaining.rfind(" ", boundary_start, _QUIZ_CHUNK_CHARS)

        if boundary < boundary_start:
            boundary = _QUIZ_CHUNK_CHARS
        elif remaining[boundary:boundary + 2] in {". ", "! ", "? "}:
            boundary += 1

        chunks.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].strip()

    if remaining:
        chunks.append(remaining)

    return chunks


def _select_quiz_chunks(
    chunks: list[str],
    question_count: int,
    previous_questions: Optional[list[object]] = None,
) -> list[str]:
    selected_count = min(len(chunks), question_count, 5)

    if selected_count == 0:
        return []

    historical_tokens = set()
    for previous_question in previous_questions or []:
        historical_tokens.update(_canonical_quiz_concept_tokens(
            " ".join(_historical_question_fields(previous_question))
        ))

    if not historical_tokens:
        if selected_count == 1:
            return chunks[:1]

        indexes = [
            round((len(chunks) - 1) * index / (selected_count - 1))
            for index in range(selected_count)
        ]
        return [chunks[index] for index in indexes]

    usage_key = lambda chunk: (
        _concept_overlap(
            _canonical_quiz_concept_tokens(chunk),
            historical_tokens,
        ),
        -len(chunk),
    )

    if selected_count == 1:
        return [min(chunks, key=usage_key)]

    selected_chunks = []
    for section_index in range(selected_count):
        section_start = len(chunks) * section_index // selected_count
        section_end = len(chunks) * (section_index + 1) // selected_count
        section = chunks[section_start:max(section_end, section_start + 1)]

        selected_chunks.append(min(section, key=usage_key))

    return sorted(selected_chunks, key=usage_key)


def _distribute_quiz_questions(
    question_count: int,
    chunk_count: int,
) -> list[int]:
    base_count, remainder = divmod(question_count, chunk_count)
    return [
        base_count + (1 if index < remainder else 0)
        for index in range(chunk_count)
    ]


def _detect_quiz_language(text: str) -> str:
    words = re.findall(r"[^\W\d_]+", text.casefold())
    turkish_markers = {
        "bir", "bu", "daha", "göre", "için", "ile", "olarak", "ve",
    }
    english_markers = {
        "and", "are", "for", "from", "is", "of", "that", "the", "to",
    }
    turkish_score = sum(word in turkish_markers for word in words)
    turkish_score += sum(character in "çğıöşü" for character in text.casefold())
    english_score = sum(word in english_markers for word in words)
    return "English" if english_score > turkish_score else "Turkish"


def _quiz_json_schema(question_count: int) -> dict:
    question_schema = {
        "type": "object",
        "properties": {
            "question_type": {"type": "string"},
            "context_text": {
                "anyOf": [
                    {"type": "string"},
                    {"type": "null"},
                ],
            },
            "question_text": {"type": "string"},
            "option_a": {"type": "string"},
            "option_b": {"type": "string"},
            "option_c": {"type": "string"},
            "option_d": {"type": "string"},
            "option_e": {"type": "string"},
            "correct_answer": {"type": "string"},
            "explanation": {"type": "string"},
        },
        "required": [
            "question_type", "context_text", "question_text", "option_a",
            "option_b", "option_c", "option_d", "option_e",
            "correct_answer", "explanation",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "minItems": question_count,
                "maxItems": question_count,
                "items": question_schema,
            },
        },
        "required": ["questions"],
        "additionalProperties": False,
    }


def _quiz_prompt(
    source_text: str,
    question_count: int,
    language: str,
    previous_questions: Optional[list[str]] = None,
    retry: bool = False,
    rejection_reason: Optional[str] = None,
) -> str:
    previous_text = "\n".join(
        f"- {question}" for question in (previous_questions or [])
    ) or "- None"
    retry_instruction = (
        "Previous output was invalid. Return complete, valid JSON only."
        if retry
        else ""
    )
    replacement_instruction = (
        "The previous candidate tested a learning target already used in a "
        "previous quiz. Generate a question about a DIFFERENT supported "
        "concept from SOURCE TEXT."
        if rejection_reason == "historical_learning_target"
        else (
            "The previous candidate duplicated this quiz. Generate a question "
            "about a DIFFERENT supported fact or relationship."
            if rejection_reason in {
                "current_quiz_duplicate",
                "current_learning_target_duplicate",
            }
            else (
                "Do not mention the source, text, document, passage, material, "
                "or phrases such as 'metne göre', 'kaynakta', 'bu belgede', "
                "or 'verilen metinde'. Ask the question directly."
                if rejection_reason == "meta_source_reference"
                else ""
            )
        )
    )
    return f"""
Create exactly {question_count} {language} multiple-choice questions.

Rules:
- Ground every question, answer, and concise explanation only in SOURCE TEXT;
  never add general knowledge or mention the text/document/source.
- Never write "metne göre", "metinde", "kaynakta", "belgede", "bu belgede",
  "verilen metinde", or "yukarıdaki metne göre". Ask directly. Explanations
  must explain the concept directly, never say where it was stated.
- Use five distinct, balanced options with one answer (A-E). Distractors must
  be plausible nearby concepts, not absurd, synonymous, duplicated, simple
  negations/reversals, or all/none-of-the-above.
- There must be exactly one clearly best answer. Each distractor must be
  definitively wrong according to SOURCE TEXT, not a partly correct cause,
  consequence, prerequisite, or subcomponent of the correct answer.
- question_type is multiple_choice. Do not repeat PREVIOUS QUESTIONS or test
  the same fact with different wording.
- Do not ask another question that tests a previously used fact, relationship,
  definition, cause, consequence, or learning target, even when rephrased.
  Choose a different concept supported by SOURCE TEXT.
- The question premise must agree logically with its correct answer and
  explanation. Never state a false assumption as fact, especially by reversing
  positive/negative meanings such as sees/does not see, increases/decreases,
  exists/does not exist, or required/not required.
- In Turkish, write natural, concise questions understood in one reading. Avoid
  translated or circular patterns such as "neden önemli hale geldiği nedir".
- Keep stems short and unambiguous. Do not ask for "the main reason" unless the
  source explicitly identifies one unique main reason.
- Match semantic categories: if asking for an ethical principle/concept, all
  options must be peer-level principle/concept labels (for example Mahremiyet,
  Şeffaflık, Adalet, Kullanıcı Kontrolü, Güvenlik), not indirect outcomes.
- context_text is null unless useful. When used, copy only 1-3 short SOURCE TEXT
  sentences; never reveal the answer or add facts.
- When supported, balance direct concepts, cause/effect, comparison,
  relationships, and short grounded inference. Do not force unsupported types.
- Ignore references, bibliography, authors, years, titles, DOI, and URLs.
- Explain why the answer is correct in 1-2 natural sentences. Do not quote the
  source or say "the text states"; clarify likely confusion when useful.
- Return only valid JSON matching OUTPUT FORMAT; no markdown or commentary.
{retry_instruction}
{replacement_instruction}

PREVIOUSLY TESTED LEARNING TARGETS:
{previous_text}

SOURCE TEXT:
{source_text}

OUTPUT FORMAT:
{{"questions":[{{"question_type":"multiple_choice","context_text":null,
"question_text":"...",
"option_a":"...","option_b":"...","option_c":"...","option_d":"...",
"option_e":"...","correct_answer":"A","explanation":"..."}}]}}
/no_think
"""


def _important_quiz_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[^\W\d_]+", value.casefold())
        if len(token) >= 4 and token not in _QUIZ_STOP_WORDS
    }


def _canonical_quiz_concept_tokens(value: str) -> set[str]:
    generic_tokens = {
        "aşağıdakilerden", "belirtilen", "bilgi", "hangisi", "ifade",
        "hangi", "işlev", "işleve", "kavram", "nedir", "nelerdir",
        "sahiptir", "seçenek", "temel", "verilen",
    }
    concepts = set()

    for token in _important_quiz_tokens(value):
        if token in generic_tokens:
            continue

        normalized_token = token[:6] if len(token) >= 7 else token
        alias = next(
            (
                concept
                for prefix, concept in _QUIZ_CONCEPT_ALIASES.items()
                if token.startswith(prefix)
            ),
            None,
        )
        concepts.add(alias or normalized_token)

    return concepts


def _concept_overlap(first: set[str], second: set[str]) -> float:
    smaller_count = min(len(first), len(second))
    return len(first & second) / smaller_count if smaller_count else 0.0


def _historical_question_fields(question: object) -> tuple[str, str, str]:
    if isinstance(question, str):
        return question, "", ""

    if isinstance(question, dict):
        return (
            str(question.get("question_text") or ""),
            str(question.get("correct_option") or ""),
            str(question.get("explanation") or ""),
        )

    return "", "", ""


def _compact_learning_targets(previous_questions: list[object]) -> list[str]:
    targets = []

    for previous_question in previous_questions[:_QUIZ_PREVIOUS_PROMPT_LIMIT]:
        question_text, correct_option, _ = _historical_question_fields(
            previous_question
        )
        question_preview = " ".join(question_text.split())[:110]
        answer_preview = " ".join(correct_option.split())[:60]

        if question_preview:
            targets.append(
                f"{question_preview} -> {answer_preview}"
                if answer_preview
                else question_preview
            )

    return targets


def _quiz_relation_tags(value: str) -> set[str]:
    normalized = _normalize_quiz_text(value)
    return {
        marker
        for marker in _QUIZ_RELATION_MARKERS
        if marker in normalized
    }


def _context_reveals_correct_option(
    context_text: str,
    correct_option: str,
) -> bool:
    normalized_context = _normalize_quiz_text(context_text)
    normalized_answer = _normalize_quiz_text(correct_option)

    if not normalized_answer:
        return True

    answer_word_count = len(normalized_answer.split())

    if (
        normalized_answer in normalized_context
        and (len(normalized_answer) >= 12 or answer_word_count >= 2)
    ):
        return True

    answer_tokens = _canonical_quiz_concept_tokens(correct_option)
    context_tokens = _canonical_quiz_concept_tokens(context_text)
    token_overlap = (
        len(answer_tokens & context_tokens) / len(answer_tokens)
        if answer_tokens
        else 0.0
    )
    literal_similarity = SequenceMatcher(
        None,
        normalized_answer,
        normalized_context,
    ).ratio()
    return (
        literal_similarity >= 0.78
        or (len(answer_tokens) >= 3 and token_overlap >= 0.85)
    )


def _is_simple_antonym_distractor(
    correct_option: str,
    distractor: str,
) -> bool:
    normalized_correct = _normalize_quiz_text(correct_option)
    normalized_distractor = _normalize_quiz_text(distractor)

    for correct_term, opposite_term in _SIMPLE_ANTONYM_PAIRS:
        term_pairs = (
            (correct_term, opposite_term),
            (opposite_term, correct_term),
        )

        for source_term, target_term in term_pairs:
            if (
                source_term in normalized_correct
                and target_term in normalized_distractor
            ):
                repaired_distractor = normalized_distractor.replace(
                    target_term,
                    source_term,
                )

                if SequenceMatcher(
                    None,
                    normalized_correct,
                    repaired_distractor,
                ).ratio() >= 0.86:
                    return True

    return False


def _quiz_question_is_grounded(question: QuizQuestion, source_text: str) -> bool:
    answer = getattr(
        question,
        f"option_{question.correct_answer.casefold()}",
    )
    evidence_text = " ".join((answer, question.explanation))
    evidence_tokens = _important_quiz_tokens(evidence_text)
    source_tokens = _important_quiz_tokens(source_text)

    if not evidence_tokens:
        return False

    matches = sum(
        any(
            token == source_token
            or (
                min(len(token), len(source_token)) >= 6
                and token[:6] == source_token[:6]
            )
            for source_token in source_tokens
        )
        for token in evidence_tokens
    )
    return matches >= 1 and matches / len(evidence_tokens) >= 0.10


def _reject_quiz_question(reason: str, raw_question: object) -> None:
    _quiz_validation_rejection_reason.set(reason)
    question_text = (
        raw_question.get("question_text", "")
        if isinstance(raw_question, dict)
        else ""
    )
    preview = " ".join(str(question_text).split())[:80]
    logger.info("Quiz question rejected: reason=%s preview=%r", reason, preview)


def _remove_meta_source_wording(value: str) -> str:
    repaired = value

    for pattern in _META_SOURCE_REPAIR_PATTERNS:
        repaired = pattern.sub("", repaired)

    repaired = re.sub(r"\s+([,.!?;:])", r"\1", repaired)
    repaired = " ".join(repaired.split()).strip(" ,;:-–—")

    if repaired:
        repaired = repaired[0].upper() + repaired[1:]

    return repaired


def _repair_meta_source_candidate(raw_question: object) -> Optional[dict]:
    if not isinstance(raw_question, dict):
        return None

    question_text = raw_question.get("question_text")
    explanation = raw_question.get("explanation")

    if not isinstance(question_text, str) or not isinstance(explanation, str):
        return None

    repaired_question = _remove_meta_source_wording(question_text)
    repaired_explanation = _remove_meta_source_wording(explanation)

    if (
        not repaired_question
        or not repaired_explanation
        or _META_SOURCE_REFERENCE.search(repaired_question)
        or _META_SOURCE_REFERENCE.search(repaired_explanation)
        or not _canonical_quiz_concept_tokens(repaired_question)
    ):
        return None

    repaired = dict(raw_question)
    repaired["question_text"] = repaired_question
    repaired["explanation"] = repaired_explanation
    return repaired


def _validate_quiz_question_with_meta_repair(
    raw_question: object,
    source_text: str,
) -> Optional[QuizQuestion]:
    question = _validate_quiz_question(raw_question, source_text)

    if question is not None:
        return question

    if _quiz_validation_rejection_reason.get() != "meta_source_reference":
        return None

    logger.info("Quiz meta-source repair attempted")
    repaired_candidate = _repair_meta_source_candidate(raw_question)

    if repaired_candidate is None:
        logger.info("Quiz meta-source repair result=rejected reason=unsafe_cleanup")
        return None

    question = _validate_quiz_question(repaired_candidate, source_text)
    logger.info(
        "Quiz meta-source repair result=%s reason=%s",
        "accepted" if question is not None else "rejected",
        _quiz_validation_rejection_reason.get() or "none",
    )
    return question


def _question_has_false_premise(
    question_text: str,
    correct_option: str,
    explanation: str,
) -> bool:
    if not _ASSERTIVE_PREMISE_MARKERS.search(question_text):
        return False

    answer_text = f"{correct_option} {explanation}"

    return any(
        (
            positive.search(question_text)
            and negative.search(answer_text)
        ) or (
            negative.search(question_text)
            and positive.search(answer_text)
        )
        for positive, negative in _QUESTION_ANSWER_OPPOSITIONS
    )


def _has_ambiguous_distractor(
    correct_option: str,
    explanation: str,
    distractors: list[str],
) -> bool:
    correct_evidence = _canonical_quiz_concept_tokens(
        f"{correct_option} {explanation}"
    )

    for distractor in distractors:
        distractor_tokens = _canonical_quiz_concept_tokens(distractor)
        shared_tokens = correct_evidence & distractor_tokens
        overlap = (
            len(shared_tokens) / len(distractor_tokens)
            if distractor_tokens
            else 0.0
        )

        if SequenceMatcher(
            None,
            _normalize_quiz_text(correct_option),
            _normalize_quiz_text(distractor),
        ).ratio() >= 0.84 or (
            len(shared_tokens) >= 2 and overlap >= 0.80
        ):
            return True

    return False


def _validate_quiz_question(
    raw_question: object,
    source_text: str,
) -> Optional[QuizQuestion]:
    _quiz_validation_rejection_reason.set(None)
    if not isinstance(raw_question, dict):
        _reject_quiz_question("invalid_question_object", raw_question)
        return None

    question_text = raw_question.get("question_text")
    explanation = raw_question.get("explanation")

    if (
        isinstance(question_text, str)
        and _META_SOURCE_REFERENCE.search(question_text)
    ) or (
        isinstance(explanation, str)
        and _META_SOURCE_REFERENCE.search(explanation)
    ):
        _reject_quiz_question("meta_source_reference", raw_question)
        return None

    required_fields = (
        "question_text", "option_a", "option_b", "option_c", "option_d",
        "option_e", "correct_answer", "explanation",
    )

    if any(
        not isinstance(raw_question.get(field), str)
        or not raw_question[field].strip()
        for field in required_fields
    ):
        _reject_quiz_question("missing_field", raw_question)
        return None

    if any(pattern.search(question_text) for pattern in _UNNATURAL_QUESTION_PATTERNS):
        _reject_quiz_question("unnatural_question_pattern", raw_question)
        return None

    if len(question_text) > 220:
        _reject_quiz_question("question_too_long", raw_question)
        return None

    if (
        "temel nedeni" in question_text.casefold()
        and "temel neden" not in source_text.casefold()
    ):
        _reject_quiz_question("unsupported_main_reason", raw_question)
        return None

    options = [raw_question[f"option_{letter}"] for letter in "abcde"]
    normalized_options = [_normalize_quiz_text(option) for option in options]

    if any(not option for option in normalized_options):
        _reject_quiz_question("missing_option", raw_question)
        return None

    if len(set(normalized_options)) != 5:
        _reject_quiz_question("duplicate_options", raw_question)
        return None

    if any(option in _BANNED_QUIZ_OPTIONS for option in normalized_options):
        _reject_quiz_question("banned_option", raw_question)
        return None

    correct_answer = raw_question["correct_answer"].strip().upper()

    if correct_answer not in {"A", "B", "C", "D", "E"}:
        _reject_quiz_question("invalid_correct_answer", raw_question)
        return None

    correct_option = options[ord(correct_answer) - ord("A")]
    distractors = [
        option
        for index, option in enumerate(options)
        if index != ord(correct_answer) - ord("A")
    ]

    if _question_has_false_premise(
        question_text,
        correct_option,
        explanation,
    ):
        _reject_quiz_question("question_answer_contradiction", raw_question)
        return None

    if _has_ambiguous_distractor(correct_option, explanation, distractors):
        _reject_quiz_question("ambiguous_distractor", raw_question)
        return None

    if _CATEGORY_QUESTION_PATTERN.search(question_text) and any(
        len(option.split()) > 4 or _CATEGORY_OPTION_ACTION_PATTERN.search(option)
        for option in options
    ):
        _reject_quiz_question("semantic_category_mismatch", raw_question)
        return None

    explanation_sentence_count = len(
        re.findall(r"[.!?](?:\s|$)", explanation)
    )
    if explanation_sentence_count > 2 or re.search(
        r"[\"“”].+[\"“”]",
        explanation,
    ):
        _reject_quiz_question("invalid_explanation", raw_question)
        return None

    if any(
        _is_simple_antonym_distractor(correct_option, distractor)
        for distractor_index, distractor in enumerate(options)
        if distractor_index != ord(correct_answer) - ord("A")
    ):
        _reject_quiz_question("simple_antonym_distractor", raw_question)
        return None

    context_text = raw_question.get("context_text")

    if context_text is not None:
        if not isinstance(context_text, str) or not context_text.strip():
            _reject_quiz_question("invalid_context_text", raw_question)
            return None

        context_text = context_text.strip()
        sentence_count = len(re.findall(r"[.!?](?:\s|$)", context_text))

        if len(context_text) > 600 or sentence_count > 3:
            _reject_quiz_question("invalid_context_text", raw_question)
            return None

        if not _important_quiz_tokens(context_text).intersection(
            _important_quiz_tokens(source_text)
        ):
            _reject_quiz_question("ungrounded_context_text", raw_question)
            return None

        if _context_reveals_correct_option(context_text, correct_option):
            _reject_quiz_question("context_reveals_answer", raw_question)
            return None

    try:
        question = QuizQuestion(
            question_type="multiple_choice",
            context_text=context_text,
            question_text=raw_question["question_text"].strip(),
            option_a=options[0].strip(),
            option_b=options[1].strip(),
            option_c=options[2].strip(),
            option_d=options[3].strip(),
            option_e=options[4].strip(),
            correct_answer=correct_answer,
            explanation=raw_question["explanation"].strip(),
        )
    except ValueError:
        _reject_quiz_question("schema_validation_failed", raw_question)
        return None

    if not _quiz_question_is_grounded(question, source_text):
        _reject_quiz_question("grounding_failed", raw_question)
        return None

    return question


def _is_duplicate_quiz_question(
    question_text: str,
    accepted_questions: list[QuizQuestion],
    previous_questions: Optional[list[str]] = None,
) -> bool:
    normalized = _normalize_quiz_text(question_text)
    candidates = [
        (accepted.question_text, False)
        for accepted in accepted_questions
    ] + [
        (previous_question, True)
        for previous_question in (previous_questions or [])
    ]

    for previous_question, is_historical in candidates:
        previous = _normalize_quiz_text(previous_question)

        if normalized == previous or SequenceMatcher(
            None,
            normalized,
            previous,
        ).ratio() >= 0.91:
            return True

        concept_tokens = _canonical_quiz_concept_tokens(question_text)
        previous_tokens = _canonical_quiz_concept_tokens(
            previous_question
        )
        shared_tokens = concept_tokens & previous_tokens
        smaller_token_count = min(
            len(concept_tokens),
            len(previous_tokens),
        )
        concept_overlap = (
            len(shared_tokens) / smaller_token_count
            if smaller_token_count
            else 0.0
        )
        shared_relations = _quiz_relation_tags(
            question_text
        ) & _quiz_relation_tags(previous_question)
        relation_sets_match = (
            _quiz_relation_tags(question_text)
            == _quiz_relation_tags(previous_question)
        )

        if (
            len(shared_tokens) >= 3
            and concept_overlap >= 0.72
            and (shared_relations or concept_overlap >= 0.86)
        ):
            return True

        if (
            is_historical
            and len(shared_tokens) >= 2
            and concept_overlap >= 0.65
            and relation_sets_match
        ):
            return True

    return False


def _is_historical_learning_target_duplicate(
    question: QuizQuestion,
    previous_questions: list[object],
) -> bool:
    correct_option = getattr(
        question,
        f"option_{question.correct_answer.casefold()}",
    )
    question_tokens = _canonical_quiz_concept_tokens(question.question_text)
    answer_tokens = _canonical_quiz_concept_tokens(correct_option)
    explanation_tokens = _canonical_quiz_concept_tokens(question.explanation)

    for previous_question in previous_questions:
        previous_text, previous_answer, previous_explanation = (
            _historical_question_fields(previous_question)
        )

        if not previous_text:
            continue

        normalized_candidate = _normalize_quiz_text(question.question_text)
        normalized_previous = _normalize_quiz_text(previous_text)

        if normalized_candidate == normalized_previous:
            logger.info(
                "CrossQuiz duplicate result=exact candidate=%r historical=%r",
                question.question_text[:80],
                previous_text[:80],
            )
            return True

        text_similarity = SequenceMatcher(
            None,
            normalized_candidate,
            normalized_previous,
        ).ratio()

        if text_similarity >= 0.90:
            logger.info(
                "CrossQuiz duplicate result=text_similarity similarity=%.3f "
                "candidate=%r historical=%r",
                text_similarity,
                question.question_text[:80],
                previous_text[:80],
            )
            return True

        previous_question_tokens = _canonical_quiz_concept_tokens(previous_text)
        previous_answer_tokens = _canonical_quiz_concept_tokens(previous_answer)
        previous_explanation_tokens = _canonical_quiz_concept_tokens(
            previous_explanation
        )
        question_overlap = _concept_overlap(
            question_tokens,
            previous_question_tokens,
        )
        answer_overlap = _concept_overlap(answer_tokens, previous_answer_tokens)
        explanation_overlap = _concept_overlap(
            explanation_tokens,
            previous_explanation_tokens,
        )
        answer_similarity = SequenceMatcher(
            None,
            _normalize_quiz_text(correct_option),
            _normalize_quiz_text(previous_answer),
        ).ratio()
        explanation_similarity = SequenceMatcher(
            None,
            _normalize_quiz_text(question.explanation),
            _normalize_quiz_text(previous_explanation),
        ).ratio()
        answer_matches = answer_similarity >= 0.82 or answer_overlap >= 0.75

        if (
            answer_matches
            and question_overlap >= 0.30
            and explanation_overlap >= 0.30
        ):
            logger.info(
                "CrossQuiz duplicate result=learning_target answer=%.3f "
                "question=%.3f explanation=%.3f",
                answer_overlap,
                question_overlap,
                explanation_overlap,
            )
            return True

        if (
            explanation_similarity >= 0.85
            and (question_overlap >= 0.15 or answer_overlap >= 0.25)
        ):
            logger.info(
                "CrossQuiz duplicate result=explanation similarity=%.3f",
                explanation_similarity,
            )
            return True

    return False


def _quiz_duplicate_reason(
    question: QuizQuestion,
    accepted_questions: list[QuizQuestion],
    previous_questions: list[object],
) -> Optional[str]:
    if _is_duplicate_quiz_question(
        question.question_text,
        accepted_questions,
    ):
        logger.info(
            "CrossQuiz candidate historical_count=%s result=current_quiz_duplicate",
            len(previous_questions),
        )
        return "current_quiz_duplicate"

    accepted_learning_targets = [
        {
            "question_text": accepted.question_text,
            "correct_option": getattr(
                accepted,
                f"option_{accepted.correct_answer.casefold()}",
            ),
            "explanation": accepted.explanation,
        }
        for accepted in accepted_questions
    ]
    if _is_historical_learning_target_duplicate(
        question,
        accepted_learning_targets,
    ):
        logger.info(
            "CrossQuiz candidate historical_count=%s "
            "result=current_learning_target_duplicate",
            len(previous_questions),
        )
        return "current_learning_target_duplicate"

    if _is_historical_learning_target_duplicate(question, previous_questions):
        logger.info(
            "CrossQuiz candidate historical_count=%s "
            "result=historical_learning_target",
            len(previous_questions),
        )
        return "historical_learning_target"

    logger.info(
        "CrossQuiz candidate historical_count=%s result=accepted preview=%r",
        len(previous_questions),
        question.question_text[:80],
    )

    return None


def _first_stream_question_historical_duplicate_reason(
    question: QuizQuestion,
    previous_questions: list[object],
) -> Optional[str]:
    normalized_candidate = _normalize_quiz_text(question.question_text)

    for previous_question in previous_questions:
        previous_text, _, _ = _historical_question_fields(previous_question)
        normalized_previous = _normalize_quiz_text(previous_text)

        if not normalized_previous:
            continue

        if normalized_candidate == normalized_previous:
            logger.info("CrossQuiz first candidate result=historical_exact")
            return "historical_exact_duplicate"

        similarity = SequenceMatcher(
            None,
            normalized_candidate,
            normalized_previous,
        ).ratio()
        if similarity >= 0.90:
            logger.info(
                "CrossQuiz first candidate result=historical_textual "
                "similarity=%.3f",
                similarity,
            )
            return "historical_textual_duplicate"

    return None


def _parse_quiz_response(raw_response: str) -> list[object]:
    parsed = json.loads(_clean_json_response(raw_response))

    if not isinstance(parsed, dict) or not isinstance(
        parsed.get("questions"),
        list,
    ):
        raise ValueError("LM Studio quiz yanıtında questions listesi yok.")

    return parsed["questions"]


def _is_context_size_error(error: LMStudioServiceError) -> bool:
    current_error = error

    while current_error is not None:
        response = getattr(current_error, "response", None)
        response_text = getattr(response, "text", "")
        error_text = f"{current_error} {response_text}".casefold()

        if (
            "context size" in error_text
            or "context length" in error_text
            or "context_length_exceeded" in error_text
        ):
            return True

        current_error = getattr(current_error, "__cause__", None)

    return False


def _shrink_quiz_source(source_text: str) -> str:
    if len(source_text) <= _QUIZ_FALLBACK_CHUNK_CHARS:
        return source_text

    shortened = source_text[:_QUIZ_FALLBACK_CHUNK_CHARS]
    boundary = max(shortened.rfind(marker) for marker in (". ", "! ", "? ", "\n"))

    if boundary >= int(_QUIZ_FALLBACK_CHUNK_CHARS * 0.65):
        shortened = shortened[:boundary + 1]

    return shortened.strip()


def _request_quiz_questions(
    source_text: str,
    question_count: int,
    language: str,
    previous_questions: list[str],
    *,
    allow_retry: bool,
    rejection_reason: Optional[str] = None,
) -> list[object]:
    attempts = 2 if allow_retry else 1
    last_error = None
    logger.info(
        "CrossQuiz prompt learning_target_count=%s",
        len(previous_questions),
    )

    for attempt in range(attempts):
        try:
            prompt = _quiz_prompt(
                source_text,
                question_count,
                language,
                previous_questions,
                retry=attempt > 0,
                rejection_reason=rejection_reason,
            )
            raw_response = _generate_with_lmstudio(
                prompt,
                json_schema=_quiz_json_schema(question_count),
                num_predict=max(420, question_count * 260),
                model=LMSTUDIO_QUIZ_MODEL,
            )
            return _parse_quiz_response(raw_response)
        except LMStudioServiceError as error:
            if not _is_context_size_error(error):
                raise

            fallback_source = _shrink_quiz_source(source_text)

            if fallback_source == source_text:
                raise

            logger.warning(
                "Quiz context limit exceeded; retrying with %s characters",
                len(fallback_source),
            )
            fallback_prompt = _quiz_prompt(
                fallback_source,
                question_count,
                language,
                previous_questions,
                retry=True,
                rejection_reason=rejection_reason,
            )
            raw_response = _generate_with_lmstudio(
                fallback_prompt,
                json_schema=_quiz_json_schema(question_count),
                num_predict=max(420, question_count * 260),
                model=LMSTUDIO_QUIZ_MODEL,
            )
            return _parse_quiz_response(raw_response)
        except (json.JSONDecodeError, ValueError) as error:
            last_error = error
            logger.warning(
                "Quiz JSON attempt %s/%s failed: %s",
                attempt + 1,
                attempts,
                error,
            )

    logger.warning("Quiz chunk skipped after invalid JSON: %s", last_error)
    return []


def _generate_valid_quiz_chunk(
    chunk: str,
    requested_count: int,
    language: str,
    previous_questions: list[str],
) -> tuple[list[QuizQuestion], int]:
    raw_questions = _request_quiz_questions(
        chunk,
        requested_count,
        language,
        previous_questions,
        allow_retry=True,
    )
    valid_questions = [
        question
        for raw_question in raw_questions[:requested_count]
        if (
            question := _validate_quiz_question_with_meta_repair(
                raw_question,
                chunk,
            )
        ) is not None
    ]
    return valid_questions, len(raw_questions)


def generate_quiz_questions(
    text: str,
    question_count: int = 10,
    previous_questions: Optional[list[object]] = None,
):
    if not text or not text.strip():
        raise LMStudioServiceError("Quiz soruları oluşturulamadı.")

    chunks = _split_quiz_source(text)
    historical_questions = (previous_questions or [])[
        :_QUIZ_PREVIOUS_PROMPT_LIMIT
    ]
    prompt_targets = _compact_learning_targets(historical_questions)
    selected_chunks = _select_quiz_chunks(
        chunks,
        question_count,
        historical_questions,
    )

    if not selected_chunks:
        raise LMStudioServiceError("Quiz soruları oluşturulamadı.")

    language = _detect_quiz_language(text)
    distribution = _distribute_quiz_questions(
        question_count,
        len(selected_chunks),
    )
    accepted_questions: list[QuizQuestion] = []
    last_duplicate_reason = None
    logger.info("Quiz generation started")
    logger.info("Selected chunks: %s", len(selected_chunks))

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = []

        for chunk_index, (chunk, requested_count) in enumerate(
            zip(selected_chunks, distribution),
            start=1,
        ):
            logger.info(
                "Chunk %s requested questions=%s",
                chunk_index,
                requested_count,
            )
            futures.append(
                executor.submit(
                    _generate_valid_quiz_chunk,
                    chunk,
                    requested_count,
                    language,
                    prompt_targets,
                )
            )

        for chunk_index, future in enumerate(futures, start=1):
            valid_questions, raw_question_count = future.result()
            accepted_in_chunk = 0
            duplicate_count = 0

            for question in valid_questions:
                duplicate_reason = _quiz_duplicate_reason(
                    question,
                    accepted_questions,
                    historical_questions,
                )
                if duplicate_reason:
                    last_duplicate_reason = duplicate_reason
                    duplicate_count += 1
                    logger.info(
                        "Quiz question rejected: reason=%s preview=%r",
                        duplicate_reason,
                        question.question_text[:80],
                    )
                    continue

                accepted_questions.append(question)
                accepted_in_chunk += 1
                logger.info(
                    "Question %s validated",
                    len(accepted_questions),
                )
                yield question

            logger.info(
                "Quiz chunk result: chunk=%s requested_count=%s "
                "raw_count=%s validated_count=%s duplicate_count=%s "
                "accepted_total=%s",
                chunk_index,
                distribution[chunk_index - 1],
                raw_question_count,
                len(valid_questions),
                duplicate_count,
                len(accepted_questions),
            )

    missing_count = question_count - len(accepted_questions)

    for fill_round in range(1, _QUIZ_MAX_FILL_ROUNDS + 1):
        missing_count = question_count - len(accepted_questions)

        if missing_count <= 0:
            break

        fill_source = selected_chunks[(fill_round - 1) % len(selected_chunks)]
        logger.info(
            "Quiz fill round started: round=%s requested_count=%s chunk=%s",
            fill_round,
            missing_count,
            ((fill_round - 1) % len(selected_chunks)) + 1,
        )
        fill_questions = _request_quiz_questions(
            fill_source,
            missing_count,
            language,
            (
                [question.question_text for question in accepted_questions]
                + prompt_targets
            )[:_QUIZ_PREVIOUS_PROMPT_LIMIT],
            allow_retry=False,
            rejection_reason=last_duplicate_reason,
        )
        validated_count = 0
        duplicate_count = 0

        for raw_question in fill_questions[:missing_count]:
            question = _validate_quiz_question_with_meta_repair(
                raw_question,
                fill_source,
            )

            if question is None:
                continue

            validated_count += 1

            duplicate_reason = _quiz_duplicate_reason(
                question,
                accepted_questions,
                historical_questions,
            )
            if duplicate_reason:
                last_duplicate_reason = duplicate_reason
                duplicate_count += 1
                logger.info(
                    "Quiz fill question rejected: reason=%s preview=%r",
                    duplicate_reason,
                    question.question_text[:80],
                )
                continue

            accepted_questions.append(question)
            logger.info("Question %s validated", len(accepted_questions))
            yield question

            if len(accepted_questions) == question_count:
                break

        logger.info(
            "Quiz fill round result: round=%s requested_count=%s raw_count=%s "
            "validated_count=%s duplicate_count=%s accepted_total=%s",
            fill_round,
            missing_count,
            len(fill_questions),
            validated_count,
            duplicate_count,
            len(accepted_questions),
        )

    if len(accepted_questions) != question_count:
        raise LMStudioServiceError("Quiz soruları oluşturulamadı.")

    logger.info(
        "Quiz generation completed: %s questions",
        len(accepted_questions),
    )


def generate_quiz_questions_stream(
    text: str,
    question_count: int = 10,
    previous_questions: Optional[list[object]] = None,
):
    """Pipeline micro-batches concurrently and yield validated questions in order."""
    if not text or not text.strip():
        raise LMStudioServiceError("Quiz soruları oluşturulamadı.")

    chunks = _split_quiz_source(text)
    historical_questions = (previous_questions or [])[
        :_QUIZ_PREVIOUS_PROMPT_LIMIT
    ]
    prompt_targets = _compact_learning_targets(historical_questions)
    selected_chunks = _select_quiz_chunks(
        chunks,
        question_count,
        historical_questions,
    )

    if not selected_chunks:
        raise LMStudioServiceError("Quiz soruları oluşturulamadı.")

    language = _detect_quiz_language(text)
    accepted_questions: list[QuizQuestion] = []
    batch_plan = [1] + [
        min(_QUIZ_STREAM_BATCH_SIZE, question_count - start)
        for start in range(1, question_count, _QUIZ_STREAM_BATCH_SIZE)
    ]
    chunk_cursor = 0
    stream_started_at = time.monotonic()
    active_lock = threading.Lock()
    active_batch_count = 0
    priority_mode_active = True
    lm_call_count = 0
    total_replacement_count = 0

    def request_batch(
        batch_id: int,
        output_slots: int,
        candidate_count: int,
        source_chunk: str,
        previous_targets: list[str],
        rejection_reason: Optional[str],
        replacement: bool,
        priority: bool,
        source_chunk_index: int,
    ) -> dict:
        nonlocal active_batch_count
        started_wall = time.time()
        started_monotonic = time.monotonic()

        with active_lock:
            active_batch_count += 1
            active_now = active_batch_count

        logger.info(
            "Quiz pipeline batch=%s slots=%s candidates_requested=%s "
            "priority=%s "
            "started start_time=%.3f active=%s replacement=%s source_chunk=%s",
            batch_id,
            output_slots,
            candidate_count,
            priority,
            started_wall,
            active_now,
            replacement,
            source_chunk_index,
        )

        try:
            raw_questions = _request_quiz_questions(
                source_chunk,
                candidate_count,
                language,
                previous_targets,
                allow_retry=False,
                rejection_reason=rejection_reason,
            )
            return {
                "raw_questions": raw_questions,
                "source_chunk": source_chunk,
                "source_chunk_index": source_chunk_index,
                "lm_duration": time.monotonic() - started_monotonic,
                "completed_monotonic": time.monotonic(),
            }
        finally:
            finished_wall = time.time()
            duration = time.monotonic() - started_monotonic
            with active_lock:
                active_batch_count -= 1
                active_now = active_batch_count
            logger.info(
                "Quiz pipeline batch=%s completed finish_time=%.3f "
                "lm_duration=%.1fs active=%s replacement=%s priority=%s",
                batch_id,
                finished_wall,
                duration,
                active_now,
                replacement,
                priority,
            )

    def next_source_chunk() -> tuple[int, str]:
        nonlocal chunk_cursor
        source_chunk_index = chunk_cursor % len(selected_chunks)
        chunk_cursor += 1
        return source_chunk_index, selected_chunks[source_chunk_index]

    def prompt_snapshot() -> list[str]:
        return (
            [question.question_text for question in accepted_questions]
            + prompt_targets
        )[:_QUIZ_PREVIOUS_PROMPT_LIMIT]

    with ThreadPoolExecutor(max_workers=2) as executor:
        pending_futures = {}
        batch_states = {}
        next_batch_to_submit = 1
        fill_batch_submitted = False

        def submit_batch(
            batch_id: int,
            requested_count: int,
            *,
            priority: bool,
            replacement: bool = False,
            rejection_reason: Optional[str] = None,
        ) -> bool:
            nonlocal lm_call_count, total_replacement_count
            state = batch_states.get(batch_id)
            if state is None:
                state = {
                    "requested": requested_count,
                    "priority": priority,
                    "attempt": 0,
                    "accepted": 0,
                    "raw": 0,
                    "candidates_requested": 0,
                    "valid": 0,
                    "duplicates": 0,
                    "replacements": 0,
                    "lm_duration": 0.0,
                    "started_at": time.monotonic(),
                }
                batch_states[batch_id] = state

            source_chunk_index, source_chunk = next_source_chunk()
            state["attempt"] += 1
            if replacement:
                state["replacements"] += 1
                total_replacement_count += 1

            candidate_count = (
                requested_count + 1
                if requested_count == _QUIZ_STREAM_BATCH_SIZE
                else requested_count
            )
            state["candidates_requested"] += candidate_count
            lm_call_count += 1

            future = executor.submit(
                request_batch,
                batch_id,
                requested_count,
                candidate_count,
                source_chunk,
                prompt_snapshot(),
                rejection_reason,
                replacement,
                priority,
                source_chunk_index + 1,
            )
            pending_futures[future] = batch_id
            return True

        def submit_next_planned_batch() -> bool:
            nonlocal next_batch_to_submit
            if next_batch_to_submit > len(batch_plan):
                return False

            batch_id = next_batch_to_submit
            next_batch_to_submit += 1
            return submit_batch(
                batch_id,
                batch_plan[batch_id - 1],
                priority=batch_id == 1,
            )

        while next_batch_to_submit <= min(2, len(batch_plan)):
            submit_next_planned_batch()

        while len(accepted_questions) < question_count:
            if not pending_futures:
                if submit_next_planned_batch():
                    continue

                if not accepted_questions and len(batch_plan) == 1:
                    raise LMStudioServiceError("Quiz soruları oluşturulamadı.")

                if fill_batch_submitted:
                    raise LMStudioServiceError("Quiz soruları oluşturulamadı.")

                missing_count = question_count - len(accepted_questions)
                fill_batch_submitted = True
                fill_batch_id = len(batch_plan) + 1
                if not submit_batch(
                    fill_batch_id,
                    min(_QUIZ_STREAM_BATCH_SIZE, missing_count),
                    priority=False,
                ):
                    raise LMStudioServiceError("Quiz soruları oluşturulamadı.")
                continue

            completed, _ = wait(
                tuple(pending_futures),
                return_when=FIRST_COMPLETED,
            )
            completed_results = []
            for future in completed:
                batch_id = pending_futures.pop(future)
                result = future.result()
                completed_results.append((
                    result["completed_monotonic"],
                    batch_id,
                    result,
                ))

            for _, batch_id, result in sorted(completed_results):
                state = batch_states[batch_id]
                requested_batch_size = state["requested"]
                raw_questions = result["raw_questions"]
                source_chunk = result["source_chunk"]
                source_chunk_index = result["source_chunk_index"]
                state["lm_duration"] += result["lm_duration"]
                state["raw"] += len(raw_questions)
                newly_accepted = []
                attempt_rejection_reason = None
                rejection_reason = None

                for raw_question in raw_questions:
                    slot = len(accepted_questions) + 1
                    question = _validate_quiz_question_with_meta_repair(
                        raw_question,
                        source_chunk,
                    )

                    if question is None:
                        rejection_reason = (
                            _quiz_validation_rejection_reason.get() or "unknown"
                        )
                        attempt_rejection_reason = rejection_reason
                        logger.info(
                            "Quiz stream validation: slot=%s batch=%s attempt=%s "
                            "valid=false reason=%s",
                            slot,
                            batch_id,
                            state["attempt"],
                            rejection_reason,
                        )
                        continue

                    state["valid"] += 1
                    if not accepted_questions:
                        rejection_reason = (
                            _first_stream_question_historical_duplicate_reason(
                                question,
                                historical_questions,
                            )
                        )
                    else:
                        rejection_reason = _quiz_duplicate_reason(
                            question,
                            accepted_questions,
                            historical_questions,
                        )

                    if rejection_reason:
                        attempt_rejection_reason = rejection_reason
                        state["duplicates"] += 1
                        logger.info(
                            "Quiz stream duplicate: slot=%s batch=%s attempt=%s "
                            "result=%s preview=%r",
                            slot,
                            batch_id,
                            state["attempt"],
                            rejection_reason,
                            question.question_text[:80],
                        )
                        continue

                    if state["accepted"] >= requested_batch_size:
                        logger.info(
                            "Quiz stream surplus candidate ignored: "
                            "batch=%s attempt=%s preview=%r",
                            batch_id,
                            state["attempt"],
                            question.question_text[:80],
                        )
                        continue

                    accepted_questions.append(question)
                    newly_accepted.append(question)
                    state["accepted"] += 1

                    if priority_mode_active:
                        priority_mode_active = False
                        logger.info(
                            "Quiz priority mode ended first_valid=true batch=%s",
                            batch_id,
                        )

                missing_in_batch = requested_batch_size - state["accepted"]
                max_batch_attempts = (
                    1
                    if state["priority"]
                    else 2
                )

                if state["priority"]:
                    logger.info(
                        "Quiz first-question attempt "
                        "FIRST_QUESTION_ATTEMPT=%s/%s rejection_reason=%s "
                        "source_chunk=%s duration=%.1fs result=%s",
                        state["attempt"],
                        max_batch_attempts,
                        attempt_rejection_reason or (
                            "none" if missing_in_batch == 0 else "no_candidate"
                        ),
                        source_chunk_index,
                        result["lm_duration"],
                        "accepted" if missing_in_batch == 0 else "rejected",
                    )

                successor_submitted = False
                if (
                    missing_in_batch > 0
                    and state["attempt"] < max_batch_attempts
                    and not (
                        state["priority"] and not priority_mode_active
                    )
                ):
                    successor_submitted = submit_batch(
                        batch_id,
                        missing_in_batch,
                        priority=state["priority"],
                        replacement=True,
                        rejection_reason=rejection_reason,
                    )

                if not successor_submitted:
                    should_wait_for_first_normal_batch = (
                        state["priority"]
                        and priority_mode_active
                        and bool(pending_futures)
                    )
                    if not should_wait_for_first_normal_batch:
                        submit_next_planned_batch()

                for question in newly_accepted:
                    accepted_index = accepted_questions.index(question) + 1
                    if accepted_index == 1:
                        first_valid_latency = (
                            time.monotonic() - stream_started_at
                        )
                        latency_logger = (
                            logger.warning
                            if first_valid_latency > 40
                            else logger.info
                        )
                        latency_logger(
                            "Quiz first valid question streamed "
                            "FIRST_VALID_QUESTION_LATENCY=%.1fs batch=%s",
                            first_valid_latency,
                            batch_id,
                        )
                    logger.info(
                        "Quiz stream question accepted: completed=%s total=%s",
                        accepted_index,
                        question_count,
                    )
                    yield question

                if not successor_submitted:
                    logger.info(
                        "Quiz batch=%s slots=%s candidates_requested=%s "
                        "priority=%s lm_duration=%.1fs raw=%s valid=%s "
                        "accepted=%s duplicates=%s replacements=%s "
                        "replacement_needed=%s streamed=%s elapsed=%.1fs",
                        batch_id,
                        requested_batch_size,
                        state["candidates_requested"],
                        state["priority"],
                        state["lm_duration"],
                        state["raw"],
                        state["valid"],
                        state["accepted"],
                        state["duplicates"],
                        state["replacements"],
                        missing_in_batch,
                        state["accepted"],
                        time.monotonic() - stream_started_at,
                    )

                if missing_in_batch > 0 and not successor_submitted:
                    deficit_action = (
                        "error"
                        if state["priority"] and len(batch_plan) == 1
                        else (
                            "normal_pipeline"
                            if state["priority"]
                            else "single_fill_or_error"
                        )
                    )
                    logger.warning(
                        "Quiz stream batch exhausted: batch=%s requested=%s "
                        "streamed=%s attempts=%s historical_count=%s "
                        "batch_elapsed=%.1fs deficit_action=%s",
                        batch_id,
                        requested_batch_size,
                        state["accepted"],
                        state["attempt"],
                        len(historical_questions),
                        time.monotonic() - state["started_at"],
                        deficit_action,
                    )

                if len(accepted_questions) == question_count:
                    break

    if len(accepted_questions) != question_count:
        logger.error(
                    "Quiz stream exhausted: requested=%s accepted=%s "
                    "historical_count=%s elapsed=%.1fs",
                    question_count,
                    len(accepted_questions),
                    len(historical_questions),
                    time.monotonic() - stream_started_at,
                )
        raise LMStudioServiceError("Quiz soruları oluşturulamadı.")

    total_elapsed = time.monotonic() - stream_started_at
    performance_logger = logger.warning if total_elapsed > 120 else logger.info
    performance_logger(
        "Quiz performance requested=%s lm_calls=%s "
        "replacements=%s total_elapsed=%.1fs",
        question_count,
        lm_call_count,
        total_replacement_count,
        total_elapsed,
    )


def generate_quiz(
    text: str,
    question_count: int = 10,
    previous_questions: Optional[list[object]] = None,
) -> QuizResponse:
    questions = list(
        generate_quiz_questions(
            text,
            question_count,
            previous_questions=previous_questions,
        )
    )
    return QuizResponse(questions=questions)


def generate_flashcards(*args, **kwargs):
    raise LMStudioServiceError(
        "Flashcard oluşturma özelliği yeniden geliştiriliyor."
    )


def generate_study_recommendation(*args, **kwargs):
    return None


def ask_ai_about_document(*args, **kwargs):
    raise LMStudioServiceError(
        "PDF sohbet özelliği yeniden geliştiriliyor."
    )


def generate_study_plan(*args, **kwargs):
    raise LMStudioServiceError(
        "Çalışma planı özelliği yeniden geliştiriliyor."
    )


class PlannerServiceUnavailableError(Exception):
    pass
