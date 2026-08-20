from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field, ValidationError
from typing import Literal, Optional
from difflib import SequenceMatcher
import httpx
import json
import math
import random
import re
import time
import unicodedata
from app.core.config import settings


# =========================================================
# GEMINI CLIENT
# =========================================================

client = genai.Client(
    api_key=settings.GEMINI_API_KEY
)


# =========================================================
# OLLAMA CLIENT
# =========================================================

class OllamaServiceError(RuntimeError):
    """Yerel yapay zeka servisinden kontrollü olarak dönen hata."""


def _generate_with_ollama(
    prompt: str,
    *,
    json_response: bool = False,
    json_schema: Optional[dict] = None,
    num_predict: int = 450,
) -> str:
    payload = {
        "model": settings.OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "10m",
        "options": {
            "temperature": 0.1,
            "num_predict": num_predict,
        },
    }

    if json_schema is not None:
        payload["format"] = json_schema
    elif json_response:
        payload["format"] = "json"

    try:
        response = httpx.post(
            f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/generate",
            json=payload,
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as error:
        raise OllamaServiceError(
            "Yerel yapay zeka servisine ulaşılamıyor."
        ) from error
    except (json.JSONDecodeError, ValueError) as error:
        raise OllamaServiceError(
            "Yapay zeka geçerli bir yanıt oluşturamadı."
        ) from error

    generated_text = data.get("response")

    if not isinstance(generated_text, str) or not generated_text.strip():
        raise OllamaServiceError(
            "Yapay zeka geçerli bir yanıt oluşturamadı."
        )

    return generated_text.strip()
# =========================================================
# LM STUDIO CLIENT
# =========================================================

def _generate_with_lmstudio(
    prompt: str,
    *,
    json_response: bool = False,
    json_schema: Optional[dict] = None,
    num_predict: int = 900,
) -> str:
    payload = {
        "model": "qwen2.5-3b-instruct-mlx",
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
            "http://host.docker.internal:1234/v1/chat/completions",
            json=payload,
            timeout=120.0,
        )

        response.raise_for_status()
        data = response.json()

    except httpx.HTTPStatusError as error:
        print(
            f"LM Studio HTTP hatası: "
            f"{error.response.status_code} - "
            f"{error.response.text}"
        )
        raise OllamaServiceError(
            "LM Studio geçerli bir yanıt döndürmedi."
        ) from error

    except httpx.RequestError as error:
        print(f"LM Studio bağlantı hatası: {repr(error)}")
        raise OllamaServiceError(
            "LM Studio servisine ulaşılamıyor."
        ) from error

    except (
        json.JSONDecodeError,
        ValueError,
        KeyError,
        IndexError,
    ) as error:
        raise OllamaServiceError(
            "LM Studio geçerli bir yanıt oluşturamadı."
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
        raise OllamaServiceError(
            "LM Studio geçerli bir yanıt oluşturamadı."
        )

    return generated_text.strip()


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
    _, json_end = json.JSONDecoder().raw_decode(cleaned)
    return cleaned[:json_end].strip()


# =========================================================
# QUIZ RESPONSE MODELLERİ
# =========================================================

class QuizQuestion(BaseModel):
    question_type: Literal["multiple_choice"]
    question_text: str

    option_a: str
    option_b: str
    option_c: str
    option_d: str
    option_e: str

    correct_answer: Literal["A", "B", "C", "D", "E"]
    explanation: str


class OllamaQuizQuestion(BaseModel):
    source_fact: str = Field(min_length=1, max_length=500)
    question_text: str
    correct_option: str
    distractors: list[str] = Field(min_length=4, max_length=4)


class QuizResponse(BaseModel):
    questions: list[QuizQuestion]


# =========================================================
# PDF ÖZETLEME
# =========================================================

def generate_summary(text: str):

    prompt = f"""
Aşağıdaki ders notunu Türkçe özetle.

Kurallar:

- En fazla 250 kelime.
- Madde madde yaz.
- Önemli kavramları belirt.

Ders Notu:

{text[:15000]}
"""

    return _generate_with_ollama(prompt)


# =========================================================
# AI QUIZ OLUŞTURMA
# =========================================================

_SUBQUESTION_NUMBERING = re.compile(
    r"(?:^|[\n;]|\s)\d+[.)]\s+",
    re.MULTILINE,
)
_EMBEDDED_OPTION = re.compile(
    r"(?:^|\s)[A-E][.)]\s+",
    re.MULTILINE,
)
_SUBQUESTION_LETTERING = re.compile(
    r"(?:^|[\n;]|\s)[a-e][.)]\s+",
    re.IGNORECASE | re.MULTILINE,
)
_OPTION_PREFIX = re.compile(
    r"^\s*[A-E]\s*(?:[.)]|[-–—:])\s*",
    re.IGNORECASE,
)
_OPEN_ENDED_TASK = re.compile(
    r"\b(?:çiziniz|çizin|açıklayınız|açıklayın|yorumlayınız|yorumlayın|"
    r"ispatlayınız|ispatlayın|gösteriniz|gösterin)\b"
)
_TASK_VERB = re.compile(
    r"\b(?:hesaplayınız|hesaplayın|bulunuz|bulun|bulup|belirleyiniz|"
    r"belirleyin|çiziniz|çizin|açıklayınız|açıklayın|yorumlayınız|"
    r"yorumlayın)\b"
)
_BROKEN_OCR_SUFFIX = re.compile(
    r"\b[bcçdfgğhjklmnprsştvyz]\s+(?:dır|dir|dur|dür|tır|tir|tur|tür)\b",
    re.IGNORECASE,
)
_VAGUE_QUESTION_STEM = re.compile(
    r"\b(?:karşılıklarını\s+seç(?:in|iniz)|hangisini\s+seç(?:in|iniz))\b",
    re.IGNORECASE,
)
_GENERIC_OPTION_VALUES = {
    "doğru",
    "yanlış",
    "evet",
    "hayır",
    "bilinmiyor",
    "belirsiz",
    "başka bir",
    "hiçbiri",
}
_OPTION_SYNONYMS = {
    "diskret": "kesikli",
    "devamlı": "sürekli",
    "evet": "doğru",
    "hayır": "yanlış",
    "kontinuum": "sürekli",
    "kontinüum": "sürekli",
    "kontinüüm": "sürekli",
}
_OPTION_PHRASE_SYNONYMS = {
    "ya da": "veya",
}
_RANGE_QUESTION = re.compile(
    r"\b(?:hangi\s+değerleri\s+alır|hangi\s+aralıkta)\b",
    re.IGNORECASE,
)
_SINGLE_NUMBER_OPTION = re.compile(
    r"^[+-]?(?:\d+(?:[.,]\d+)?|[.,]\d+)\s*%?$"
)
_CONTEXT_DEPENDENT_REFERENCE = re.compile(
    r"\b(?:yukarıdaki\s+bilgileri|aşağıdaki\s+soruları|şekle\s+göre|"
    r"tabloya\s+göre)\b",
    re.IGNORECASE,
)
def _normalized_question_text(question_text: str) -> str:
    return " ".join(
        re.sub(r"[^\w\s]", " ", question_text.casefold()).split()
    )


def _canonical_option(option: str) -> str:
    normalized_option = _normalized_question_text(option)

    for phrase, replacement in _OPTION_PHRASE_SYNONYMS.items():
        normalized_option = re.sub(
            rf"\b{re.escape(phrase)}\b",
            replacement,
            normalized_option,
        )

    tokens = normalized_option.split()
    canonical_tokens = [_OPTION_SYNONYMS.get(token, token) for token in tokens]
    return " ".join(canonical_tokens)


def _prepare_quiz_source(text: str) -> str:
    cleaned_lines = []

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()

        if not line:
            continue

        if any(unicodedata.category(character) == "Co" for character in line):
            continue

        if line.endswith("="):
            continue

        if _CONTEXT_DEPENDENT_REFERENCE.search(line):
            continue

        compact_line = "".join(line.split())
        alphanumeric_count = sum(character.isalnum() for character in compact_line)
        symbol_count = sum(
            not character.isalnum() for character in compact_line
        )
        natural_words = re.findall(r"[^\W\d_]{2,}", line)

        if (
            len(compact_line) >= 8
            and symbol_count > alphanumeric_count * 1.5
            and len(natural_words) < 2
        ):
            continue

        if (
            len(compact_line) < 12
            and len(natural_words) < 2
            and not re.search(r"=\s*\S+", line)
            and not re.search(r"\w\s*[=≤≥+\-/]\s*\w", line)
        ):
            continue

        cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines).strip()

    if cleaned_text:
        return cleaned_text

    fallback_lines = []

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        alpha_count = sum(character.isalpha() for character in line)

        if (
            line
            and alpha_count >= 10
            and not line.endswith("=")
            and not _CONTEXT_DEPENDENT_REFERENCE.search(line)
            and not any(
                unicodedata.category(character) == "Co"
                for character in line
            )
        ):
            fallback_lines.append(line)

    return "\n".join(fallback_lines).strip()


def _validate_ollama_source_fact(generated: OllamaQuizQuestion) -> None:
    source_fact = generated.source_fact.strip()

    if not source_fact:
        raise ValueError("source_fact boş.")

    if len(source_fact) > 500:
        raise ValueError("source_fact çok uzun.")


def _looks_like_information_block(question_text: str) -> bool:
    nonempty_lines = [
        line for line in question_text.splitlines() if line.strip()
    ]
    probability_results = re.findall(
        r"olasılığ[ıi]\s*=",
        question_text.casefold(),
    )
    list_markers = re.findall(
        r"(?:^|\n)\s*(?:[-•*]|\d+[.)]|[a-e][.)])\s+",
        question_text,
        re.IGNORECASE,
    )

    return (
        len(nonempty_lines) >= 5
        or question_text.count("=") >= 3
        or len(probability_results) >= 2
        or len(list_markers) >= 3
        or (
            len(question_text) > 600
            and len(re.findall(r"[.!?]", question_text)) >= 4
        )
    )


def _is_obviously_broken_question(question_text: str) -> bool:
    compact_text = "".join(question_text.split())
    meaningful_char_count = sum(
        character.isalnum() for character in compact_text
    )

    if (
        "�" in question_text
        or meaningful_char_count == 0
        or _BROKEN_OCR_SUFFIX.search(question_text)
    ):
        return True

    if len(compact_text) < 10 and meaningful_char_count < 3:
        return True

    if (
        len(compact_text) >= 8
        and meaningful_char_count / len(compact_text) < 0.2
    ):
        return True

    natural_words = re.findall(r"[^\W\d_]{2,}", question_text)
    formula_symbols = sum(
        not character.isalnum() and not character.isspace()
        for character in question_text
    )
    question_cues = ("nedir", "kaçtır", "hangisi", "seçiniz", "seçin")

    return (
        len(natural_words) <= 1
        and formula_symbols >= 3
        and not any(cue in question_text.casefold() for cue in question_cues)
    )


def _select_fallback_context(context: str, max_chars: int = 4000) -> str:
    chunks = [
        chunk.strip()
        for chunk in re.split(r"\n\s*\n|(?<=[.!?])\s+", context)
        if chunk.strip()
    ]
    preferred_markers = (
        "tanım",
        "kavram",
        "temel",
        "kural",
        "ifade eder",
        "olarak adlandırılır",
        "denir",
        "özelli",
    )
    unsuitable_markers = (
        "alıştırma",
        "grafiğini çiz",
        "grafik çiz",
        "hesaplayınız",
        "hesaplayın",
        "örnek çözüm",
        "çözüm:",
        "tablo",
    )
    suitable_chunks = []

    for position, chunk in enumerate(chunks):
        normalized_chunk = chunk.casefold()

        if (
            _SUBQUESTION_NUMBERING.search(chunk)
            or _SUBQUESTION_LETTERING.search(chunk)
            or _OPEN_ENDED_TASK.search(normalized_chunk)
            or len(_TASK_VERB.findall(normalized_chunk)) >= 2
            or re.match(r"^örnek\s*:", normalized_chunk)
            or any(marker in normalized_chunk for marker in unsuitable_markers)
        ):
            continue

        priority = 0 if any(
            marker in normalized_chunk for marker in preferred_markers
        ) else 1
        suitable_chunks.append((priority, position, chunk))

    suitable_chunks.sort(key=lambda item: (item[0], item[1]))
    selected_chunks = []
    selected_length = 0

    for _, _, chunk in suitable_chunks:
        remaining_chars = max_chars - selected_length

        if remaining_chars <= 0:
            break

        selected_chunk = chunk[:remaining_chars]
        selected_chunks.append(selected_chunk)
        selected_length += len(selected_chunk) + 1

    fallback_context = "\n".join(selected_chunks).strip()
    return fallback_context or context[:max_chars]


def _select_alternate_context(
    text: str,
    avoided_context_starts: list[int],
    max_chars: int = 4000,
) -> str:
    if len(text) <= max_chars:
        return _select_fallback_context(text, max_chars)

    last_start = len(text) - max_chars
    candidate_starts = list(range(0, last_start + 1, max_chars))

    if candidate_starts[-1] != last_start:
        candidate_starts.append(last_start)

    def distance_from_used_contexts(candidate_start: int) -> int:
        if not avoided_context_starts:
            return last_start

        return min(
            abs(candidate_start - used_start)
            for used_start in avoided_context_starts
        )

    alternate_start = max(
        candidate_starts,
        key=distance_from_used_contexts,
    )
    alternate_window = text[
        alternate_start:alternate_start + max_chars
    ]
    return _select_fallback_context(alternate_window, max_chars)


def _quiz_retry_instruction(error: ValueError) -> str:
    if isinstance(error, json.JSONDecodeError):
        return (
            "Önceki yanıt geçersiz JSON'du. Bu kez yalnızca kısa ve "
            "eksiksiz JSON döndür."
        )

    error_message = str(error).casefold()

    if "source_fact" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: source_fact boş veya fazla uzundu.\n"
            "Contextten kısa ve açık bir source_fact seç."
        )

    if "birden fazla alt soru" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: Birden fazla alt soru ürettin.\n"
            "Bu kez question_text içinde TAM OLARAK TEK soru yaz. "
            "1., 2., 3. gibi alt maddeler kullanma."
        )

    if "açık uçlu veya birden fazla görev" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: Açık uçlu veya çok görevli soru yazdın.\n"
            "Bu kez çizme/açıklama istemeyen, tek cevaplı bir multiple-choice "
            "soru yaz."
        )

    if "anlamsız veya eksik" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: Soru metni bozuk veya eksikti.\n"
            "OCR parçasını kopyalama; kavramı düzgün ve tam bir Türkçe soruya dönüştür."
        )

    if "belirsiz" in error_message and "soru kökü" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: Soru kökü neyin sorulduğunu açıklamıyordu.\n"
            "Bu kez tek bir açık bilgiyi soran, bağımsız ve kesin bir soru yaz."
        )

    if "doğru-yanlış kılığı" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: Doğru-yanlış sorusunu 5 şıklı gösterdin.\n"
            "Gerçek bir multiple-choice soru ve kavramsal seçenekler üret."
        )

    if "bilgi bloğu" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: Soru yerine uzun bir bilgi bloğu yazdın.\n"
            "Bu kez tek kavramı soran kısa bir question_text üret."
        )

    if "anlamsal olarak tekrarlanan" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: Seçenekler eş anlamlı kavramlar içeriyordu.\n"
            "Bu kez anlamca farklı 5 seçenek üret ve yalnızca birini doğru yap."
        )

    if "aralık sorusu" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: Aralık sorusuna tekil sayı seçenekleri verdin.\n"
            "Aralık seçenekleri üret veya daha basit bir kavram sor."
        )

    if "seçenek etiketi içeriyor" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: options içinde A), B) gibi etiket kullandın.\n"
            "Seçenek metinlerini harf etiketi olmadan yaz."
        )

    if "tekrarlanan şık" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: Seçenekler tekrar etti.\n"
            "Bu kez options dizisindeki beş seçenek de farklı olsun."
        )

    if "correct_answer" in error_message or "doğru cevabı" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: correct_answer formatı hatalıydı.\n"
            "correct_answer yalnızca tek harf olmalı: A, B, C, D veya E."
        )

    if "question_text içine gömülmüş" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: Seçenekleri soru metnine yazdın.\n"
            "question_text içine seçenek ekleme; seçenekleri yalnızca "
            "options dizisine yaz."
        )

    if "gereksiz sayıda soru işareti" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: Soru metninde birden fazla soru sordun.\n"
            "Bu kez question_text içinde tek ve bağımsız bir soru sor."
        )

    if "aşırı benzer" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: Soru önceki bir soruya çok benziyordu.\n"
            "Bu kez ders notundan farklı bir kavram seç ve farklı bir soru yaz."
        )

    if "eksik veya boş şık" in error_message:
        return (
            "ÖNCEKİ DENEME GEÇERSİZDİ: Bir veya daha fazla seçenek boştu.\n"
            "options dizisine tam 5 dolu seçenek yaz."
        )

    return (
        "ÖNCEKİ DENEME GEÇERSİZDİ: Çıktı quiz kurallarına uymadı.\n"
        "Bu kez question_text, options ve correct_answer alanlarını eksiksiz doldur."
    )


def _validate_quiz(
    quiz: QuizResponse,
    question_count: int,
    previous_question_texts: Optional[list[str]] = None,
):
    """Validate Ollama quiz output before returning it to the API."""

    if quiz is None or not quiz.questions:
        raise ValueError("AI hiç soru oluşturmadı.")

    if len(quiz.questions) != question_count:
        raise ValueError(
            f"AI {question_count} soru yerine "
            f"{len(quiz.questions)} soru oluşturdu."
        )

    for index, question in enumerate(quiz.questions, start=1):
        if not question.question_text.strip():
            raise ValueError(f"{index}. sorunun soru metni boş.")

        question_text = question.question_text.strip()

        if len(_EMBEDDED_OPTION.findall(question_text)) >= 5:
            raise ValueError(
                f"{index}. sorunun seçenekleri question_text içine gömülmüş."
            )

        normalized_question = _normalized_question_text(question_text)
        comparison_texts = list(previous_question_texts or [])
        comparison_texts.extend(
            item.question_text for item in quiz.questions[:index - 1]
        )

        for previous_text in comparison_texts:
            normalized_previous = _normalized_question_text(previous_text)

            if normalized_question == normalized_previous:
                raise ValueError(
                    f"{index}. soru önceki bir soruyla aynı."
                )

        if not question.correct_answer.strip():
            raise ValueError(f"{index}. sorunun doğru cevabı boş.")

        options = [
            question.option_a,
            question.option_b,
            question.option_c,
            question.option_d,
            question.option_e,
        ]

        if any(option is None or not option.strip() for option in options):
            raise ValueError(
                f"{index}. multiple choice sorusunda eksik veya boş şık var."
            )

        normalized_options = [option.strip().casefold() for option in options]

        if len(set(normalized_options)) != 5:
            raise ValueError(
                f"{index}. multiple choice sorusunda tekrarlanan şık var."
            )

        question.correct_answer = question.correct_answer.strip().upper()

        if question.correct_answer not in {"A", "B", "C", "D", "E"}:
            raise ValueError(
                f"{index}. multiple choice sorusunun doğru cevabı "
                "A, B, C, D veya E olmalı."
            )

    return quiz


def _validate_single_quiz_question(
    question: QuizQuestion,
    previous_question_texts: list[str],
) -> QuizQuestion:
    quiz = QuizResponse(questions=[question])
    _validate_quiz(
        quiz,
        1,
        previous_question_texts=previous_question_texts,
    )
    return question


def _to_quiz_question(generated: OllamaQuizQuestion) -> QuizQuestion:
    correct_option = _OPTION_PREFIX.sub(
        "",
        generated.correct_option,
        count=1,
    ).strip()
    distractors = [
        _OPTION_PREFIX.sub("", item, count=1).strip()
        for item in generated.distractors
    ]

    if not correct_option:
        raise ValueError("correct_option boş.")

    if len(distractors) != 4 or any(
        not distractor for distractor in distractors
    ):
        raise ValueError("Tam 4 dolu distractor gerekli.")

    options = [correct_option, *distractors]
    normalized_options = [
        option.casefold()
        for option in options
    ]

    if len(set(normalized_options)) != 5:
        raise ValueError(
            "correct_option ve distractors toplam 5 benzersiz seçenek olmalı."
        )

    random.shuffle(options)
    correct_index = options.index(correct_option)
    answer_letters = ["A", "B", "C", "D", "E"]
    correct_answer = answer_letters[correct_index]

    return QuizQuestion(
        question_type="multiple_choice",
        question_text=generated.question_text,
        option_a=options[0],
        option_b=options[1],
        option_c=options[2],
        option_d=options[3],
        option_e=options[4],
        correct_answer=correct_answer,
        explanation=f"Doğru cevap: {correct_answer}",
    )


def _source_fact_supported(
    source_fact: str,
    context_window: str,
) -> bool:
    normalized_source_fact = source_fact.strip().casefold()

    if (
        normalized_source_fact
        and normalized_source_fact in context_window.casefold()
    ):
        return True

    stop_words = {
        "and", "are", "for", "from", "have", "is", "of", "that",
        "the", "this", "to", "with",
        "bir", "bu", "göre", "her", "için", "içinde", "ile", "ise",
        "olan", "olarak", "üzerinde", "ve", "veya", "ya",
    }

    def meaningful_tokens(value: str) -> list[str]:
        return [
            token
            for token in re.findall(r"[^\W\d_]+", value.casefold())
            if (
                token not in stop_words
                and len(token) >= 3
            )
        ]

    source_fact_tokens = meaningful_tokens(source_fact)

    if not source_fact_tokens:
        return True

    context_tokens = set(meaningful_tokens(context_window))
    matched_count = sum(
        token in context_tokens
        for token in source_fact_tokens
    )
    return matched_count / len(source_fact_tokens) >= 0.25


def _find_best_source_sentence(
    source_fact: str,
    context_window: str,
) -> Optional[str]:
    def normalize(value: str) -> str:
        return " ".join(
            re.sub(r"[^\w\s]", " ", value.casefold()).split()
        )

    candidates = [
        candidate.strip()
        for candidate in re.split(
            r"(?<=[.!?])\s+|\n+",
            context_window,
        )
        if len(candidate.strip()) >= 12
    ]
    normalized_source_fact = normalize(source_fact)

    if not normalized_source_fact or not candidates:
        return None

    stop_words = {
        "and", "are", "for", "from", "is", "of", "that", "the",
        "this", "to", "with",
        "bir", "bu", "için", "ile", "olan", "olarak", "ve",
    }
    source_tokens = {
        token
        for token in normalized_source_fact.split()
        if token not in stop_words and len(token) >= 3
    }
    best_candidate = None
    best_score = 0.0

    for candidate in candidates:
        normalized_candidate = normalize(candidate)

        if normalized_source_fact in normalized_candidate:
            return candidate

        similarity = SequenceMatcher(
            None,
            normalized_source_fact,
            normalized_candidate,
        ).ratio()
        candidate_tokens = set(normalized_candidate.split())
        token_overlap = (
            len(source_tokens & candidate_tokens) / len(source_tokens)
            if source_tokens
            else 0.0
        )

        if similarity >= 0.45 or token_overlap >= 0.25:
            candidate_score = max(similarity, token_overlap)

            if candidate_score > best_score:
                best_candidate = candidate
                best_score = candidate_score

    return best_candidate


def _correct_option_supported_by_fact(
    correct_option: str,
    source_fact: str,
) -> bool:
    def normalized_text(value: str) -> str:
        return " ".join(
            re.findall(r"[^\W\d_]+", value.casefold())
        )

    normalized_option = normalized_text(correct_option)
    normalized_fact = normalized_text(source_fact)

    if normalized_option and normalized_option in normalized_fact:
        return True

    stop_words = {
        "and", "are", "for", "from", "of", "the", "to", "with",
        "bir", "bu", "için", "ile", "olan", "olarak", "ve",
    }
    technical_short_terms = {"xp"}
    option_tokens = [
        token
        for token in normalized_option.split()
        if (
            token not in stop_words
            and (
                len(token) >= 3
                or token in technical_short_terms
            )
        )
    ]

    if not option_tokens:
        return False

    fact_tokens = set(normalized_fact.split())
    matched_count = sum(
        token in fact_tokens
        for token in option_tokens
    )
    return matched_count / len(option_tokens) >= 0.25


def _detect_quiz_language(text: str) -> str:
    normalized_text = text.casefold()
    words = re.findall(r"[^\W\d_]+", normalized_text)
    turkish_words = {
        "ve", "bir", "bu", "için", "ile", "olan", "olarak", "daha",
        "göre", "yazılım", "geliştirme", "model", "gereksinim",
        "tasarım", "süreç", "proje", "kullanıcı", "takım",
    }
    english_words = {
        "the", "and", "of", "to", "in", "is", "are", "for", "with",
        "that", "this", "from", "software", "development", "model",
        "requirements", "design", "process", "project", "code", "user",
        "team",
    }
    english_common_words = {
        "the", "and", "of", "to", "in", "is", "are", "for", "with",
        "that", "this", "from",
    }
    turkish_common_words = {
        "ve", "bir", "bu", "için", "ile", "olan", "olarak", "daha",
        "göre",
    }
    english_score = sum(word in english_words for word in words)
    turkish_score = sum(word in turkish_words for word in words)
    turkish_character_count = sum(
        character in "çğıöşü"
        for character in normalized_text
    )
    turkish_score += min(turkish_character_count, 10) * 0.1

    if abs(english_score - turkish_score) <= 1:
        english_common_count = sum(
            word in english_common_words
            for word in words
        )
        turkish_common_count = sum(
            word in turkish_common_words
            for word in words
        )

        if english_common_count != turkish_common_count:
            return (
                "en"
                if english_common_count > turkish_common_count
                else "tr"
            )

    return "en" if english_score > turkish_score else "tr"


def _quiz_item_matches_language(
    question_text: str,
    options: list[str],
    target_language: str,
) -> bool:
    normalized_question = question_text.strip().casefold()

    if target_language == "tr":
        return re.match(
            r"^(?:which(?:\s+of\s+the\s+following)?|what\s+is|how\s+does|why\s+does)\b",
            normalized_question,
        ) is None

    return re.match(
        r"^(?:aşağıdakilerden|hangisi|nedir|nasıl|hangi|ne\s+zaman)\b",
        normalized_question,
    ) is None


def _quiz_context_windows(
    text: str,
    question_count: int,
    window_chars: int = 1600,
) -> list[str]:
    cleaned_text = text.strip()

    if not cleaned_text:
        return [""] * question_count

    window_size = min(window_chars, len(cleaned_text))
    windows = []

    for index in range(question_count):
        anchor = (
            len(cleaned_text) // 2
            if question_count == 1
            else round(
                (len(cleaned_text) - 1)
                * index
                / (question_count - 1)
            )
        )
        window_start = max(
            0,
            min(
                anchor - (window_size // 2),
                len(cleaned_text) - window_size,
            ),
        )
        window_end = min(
            len(cleaned_text),
            window_start + window_size,
        )

        if window_start > 0:
            boundary_end = min(window_start + 120, window_end)
            boundary = cleaned_text.find(
                "\n",
                window_start,
                boundary_end,
            )

            if boundary == -1:
                boundary = cleaned_text.find(
                    " ",
                    window_start,
                    boundary_end,
                )

            if boundary != -1:
                window_start = boundary + 1

        if window_end < len(cleaned_text):
            boundary_start = max(
                window_start,
                window_end - 160,
            )
            sentence_boundaries = [
                cleaned_text.rfind(marker, boundary_start, window_end)
                for marker in (".", "!", "?", "\n")
            ]
            boundary = max(sentence_boundaries)

            if boundary > window_start:
                window_end = boundary + 1

        windows.append(
            cleaned_text[window_start:window_end].strip()
        )

    return windows


def generate_quiz(
    text: str,
    question_count: int = 10
):
    quiz_source = _prepare_quiz_source(text)
    quiz_started_at = time.perf_counter()
    quiz_language = _detect_quiz_language(quiz_source)
    language_instruction = (
        "OUTPUT LANGUAGE: ENGLISH\n"
        "- question_text MUST be English.\n"
        "- correct_option MUST be English.\n"
        "- all distractors MUST be English.\n"
        "- The entire quiz must remain in English.\n"
        "- Even if the current source section contains a few Turkish "
        "sentences, translate that information into natural English.\n"
        "- Do not mix Turkish and English except for technical proper names.\n"
        "- Use only instructional course content to create questions.\n"
        "- Ignore document metadata such as university names, department "
        "names, course codes, lecturer names, page numbers, slide numbers, "
        "headers and footers.\n"
        "- Do not mention the university, department, course code, lecturer, "
        "slide or document metadata in question_text.\n"
        "- Do not use phrases such as 'according to [university/department]'.\n"
        "- source_fact must represent actual instructional content, not "
        "document metadata.\n"
        "- Preserve the exact meaning and terminology of the source.\n"
        "- If the source names a specific phase, stage, role, model or "
        "concept, do not replace it with a different one.\n"
        "- Do not ask about Requirements Planning using a fact that belongs "
        "to User Design.\n"
        "- Do not rename or merge distinct stages.\n"
        "- Do not introduce terminology that contradicts the source.\n"
        "- If the source says a concept is not a methodology, do not call it "
        "a methodology; prefer the source's terminology, such as Agile "
        "approach or Agile software development.\n"
        "- Do not output these examples."
        if quiz_language == "en"
        else
        "ÇIKTI DİLİ: TÜRKÇE\n"
        "- question_text Türkçe olmalı.\n"
        "- correct_option Türkçe olmalı.\n"
        "- tüm distractors Türkçe olmalı.\n"
        "- Quiz boyunca dil Türkçe kalmalı.\n"
        "- Teknik özel isimler gerektiğinde İngilizce kalabilir.\n"
        "- Soruları yalnızca öğretici ders içeriğinden oluştur.\n"
        "- Üniversite ve bölüm adları, ders kodları, öğretim elemanı adları, "
        "sayfa ve slayt numaraları, üstbilgi ve altbilgi gibi belge "
        "metadatalarını yok say.\n"
        "- question_text içinde üniversite, bölüm, ders kodu, öğretim "
        "elemanı, slayt veya belge metadatasından bahsetme.\n"
        "- '[üniversite/bölüm] bilgisine göre' gibi ifadeler kullanma.\n"
        "- source_fact belge metadatasını değil, gerçek öğretici ders "
        "içeriğini temsil etmelidir.\n"
        "- Kaynağın anlamını ve terminolojisini tam olarak koru.\n"
        "- Kaynak belirli bir aşama, evre, rol, model veya kavram adlandırıyorsa "
        "onu başka bir aşama, evre, rol, model veya kavramla değiştirme.\n"
        "- User Design aşamasına ait bir bilgiyle Requirements Planning "
        "hakkında soru sorma.\n"
        "- Birbirinden farklı aşamaları yeniden adlandırma veya birleştirme.\n"
        "- Kaynakla çelişen terminoloji kullanma.\n"
        "- Kaynak bir kavramın metodoloji olmadığını söylüyorsa onu metodoloji "
        "olarak adlandırma; Agile yaklaşımı veya Agile yazılım geliştirme gibi "
        "kaynağın terminolojisini tercih et.\n"
        "- Bu örnekleri çıktıya yazma."
    )
    batch_size_limit = 2
    window_count = max(
        question_count * 2,
        8,
    )
    context_windows = _quiz_context_windows(
        quiz_source,
        window_count,
    )
    accepted_questions: list[QuizQuestion] = []
    accepted_source_facts: list[str] = []
    used_context_indices: set[int] = set()
    expected_batches = math.ceil(
        question_count / batch_size_limit
    )
    extra_attempts = 3 if question_count <= 5 else 4
    max_batch_attempts = expected_batches + extra_attempts
    batch_attempts = 0
    last_error = None
    retry_instruction = ""

    print(
        f"LM Studio Quiz target language: {quiz_language}"
    )

    while (
        len(accepted_questions) < question_count
        and batch_attempts < max_batch_attempts
    ):
        remaining = question_count - len(accepted_questions)
        batch_size = min(
            batch_size_limit,
            remaining,
        )
        available_indices = [
            index
            for index in range(len(context_windows))
            if index not in used_context_indices
        ]

        if len(available_indices) < batch_size:
            used_context_indices.clear()
            available_indices = list(range(len(context_windows)))

        context_indices = available_indices[:batch_size]

        for context_index in context_indices:
            used_context_indices.add(context_index)

        selected_contexts = [
            context_windows[context_index]
            for context_index in context_indices
        ]
        source_sections = "\n\n".join(
            f"SOURCE SECTION {section_index}:\n{context_window}"
            for section_index, context_window in enumerate(
                selected_contexts,
                start=1,
            )
        )
        section_rules = "\n".join(
            f"- Question {section_index} must use ONLY SOURCE SECTION "
            f"{section_index}."
            for section_index in range(1, batch_size + 1)
        )
        recent_source_facts = accepted_source_facts[-6:]
        used_facts_prompt = "\n".join(
            f"- {source_fact}"
            for source_fact in recent_source_facts
        ) or "- None"
        batch_num_predict = (
            350
            if batch_size == 1
            else 550
        )
        batch_schema = {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "minItems": batch_size,
                    "maxItems": batch_size,
                    "items": {
                        "type": "object",
                        "properties": {
                            "source_fact": {"type": "string"},
                            "question_text": {"type": "string"},
                            "correct_option": {"type": "string"},
                            "distractors": {
                                "type": "array",
                                "minItems": 4,
                                "maxItems": 4,
                                "items": {"type": "string"},
                            },
                        },
                        "required": [
                            "source_fact",
                            "question_text",
                            "correct_option",
                            "distractors",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["questions"],
            "additionalProperties": False,
        }
        prompt = f"""
Create EXACTLY {batch_size} multiple-choice question(s).

{language_instruction}

PREVIOUSLY USED FACTS:
{used_facts_prompt}

RULES:
- Use a different fact or concept for each question.
- Do not create a question from any previously used fact.
- Choose a different fact or concept from the assigned source section.
- Do not reproduce any previously generated question.
- The wording may be similar, but the tested fact must be different.
- Do not repeat the exact same question.
- Copy source_fact as closely as possible from its assigned SOURCE SECTION.
- source_fact must be at most one short sentence.
- question_text must test exactly the fact expressed in source_fact.
- Do not broaden, narrow or change the meaning of source_fact.
- If source_fact describes one stage, ask about that stage only.
- If source_fact describes one principle, ask about that principle only.
- The question stem and correct_option must refer to the same concept or stage described by source_fact.
- question_text must be short and direct.
- correct_option must be clearly correct according to source_fact.
- correct_option must be at most 12 words.
- Produce exactly 4 plausible but incorrect distractors, each at most 12 words.
- correct_option and 4 distractors must be EXACTLY 5 distinct texts.
- Do not repeat an option with a different label or minor wording changes.
- correct_option must not match any distractor.
- Distractors must not match each other.
- Before returning JSON, internally verify that all five options are unique.
- Before returning JSON, internally verify that correct_option directly answers question_text.
- Verify that question_text and correct_option are supported by the same source_fact.
- If they do not match, rewrite the question before returning JSON.
- Do not write this internal check in the output.
- Do not use information outside the assigned SOURCE SECTION.
{section_rules}
- Do not produce explanations or markdown.
- Return only the requested JSON and write nothing after it.
{retry_instruction}

OUTPUT:
{{
  "questions": [
    {{
      "source_fact": "...",
      "question_text": "...",
      "correct_option": "...",
      "distractors": ["...", "...", "...", "..."]
    }}
  ]
}}

{source_sections}
"""
        batch_attempts += 1
        batch_started_at = time.perf_counter()
        produced_count = 0
        accepted_in_batch = 0
        rejected_in_batch = 0

        try:
            raw_response = _generate_with_lmstudio(
                prompt,
                json_schema=batch_schema,
                num_predict=batch_num_predict,
            )
            cleaned_response = _clean_json_response(raw_response)
            parsed = json.loads(cleaned_response)

            if not isinstance(parsed, dict):
                raise ValueError(
                    "LM Studio yanıtı JSON nesnesi değil."
                )

            raw_questions = parsed.get("questions")

            if not isinstance(raw_questions, list):
                raise ValueError(
                    "LM Studio yanıtında questions listesi bulunamadı."
                )

            produced_count = len(raw_questions)

            for raw_index, raw_question in enumerate(
                raw_questions[:batch_size]
            ):
                context_window = selected_contexts[raw_index]

                try:
                    raw_question_for_validation = raw_question

                    if isinstance(raw_question, dict):
                        raw_question_for_validation = dict(raw_question)
                        source_fact = raw_question_for_validation.get(
                            "source_fact"
                        )

                        if isinstance(source_fact, str):
                            source_fact = source_fact.strip()

                            if len(source_fact) > 500:
                                shortened_source_fact = source_fact[:500]
                                sentence_end = max(
                                    shortened_source_fact.rfind(marker)
                                    for marker in (".", "!", "?")
                                )
                                source_fact = (
                                    shortened_source_fact[:sentence_end + 1]
                                    if sentence_end >= 0
                                    else shortened_source_fact
                                )

                            raw_question_for_validation[
                                "source_fact"
                            ] = source_fact

                        if not isinstance(source_fact, str) or not source_fact:
                            raw_question_for_validation["source_fact"] = "."

                        for field_name in (
                            "question_text",
                            "correct_option",
                        ):
                            field_value = raw_question_for_validation.get(
                                field_name
                            )

                            if isinstance(field_value, str):
                                raw_question_for_validation[field_name] = (
                                    field_value.strip()
                                )

                        distractors = raw_question_for_validation.get(
                            "distractors"
                        )

                        if not isinstance(distractors, list):
                            raise ValueError("distractors list olmalı.")

                        if len(distractors) != 4:
                            raise ValueError(
                                "Tam 4 distractor gerekli."
                            )

                        raw_question_for_validation["distractors"] = [
                            distractor.strip()
                            if isinstance(distractor, str)
                            else distractor
                            for distractor in distractors
                        ]

                        correct_option = raw_question_for_validation.get(
                            "correct_option"
                        )

                        if (
                            isinstance(correct_option, str)
                            and not correct_option
                        ):
                            raise ValueError("correct_option boş.")

                    try:
                        generated = OllamaQuizQuestion.model_validate(
                            raw_question_for_validation
                        )
                    except ValidationError as error:
                        last_error = error
                        rejected_in_batch += 1
                        first_error = error.errors()[0]
                        field_name = ".".join(
                            str(item)
                            for item in first_error.get("loc", ())
                        )
                        print(
                            f"LM Studio Quiz batch {batch_attempts} "
                            f"soru {raw_index + 1} Pydantic hatası: "
                            f"{field_name} {first_error.get('msg', error)}"
                        )
                        continue

                    best_source_sentence = _find_best_source_sentence(
                        generated.source_fact,
                        context_window,
                    )

                    if best_source_sentence is None:
                        raise ValueError(
                            "source_fact kaynak bölümü tarafından "
                            "yeterince desteklenmiyor."
                        )

                    generated.source_fact = best_source_sentence

                    if not _source_fact_supported(
                        generated.source_fact,
                        context_window,
                    ):
                        raise ValueError(
                            "source_fact kaynak bölümü tarafından "
                            "yeterince desteklenmiyor."
                        )

                    generated_question = _to_quiz_question(generated)
                    options = [
                        generated_question.option_a,
                        generated_question.option_b,
                        generated_question.option_c,
                        generated_question.option_d,
                        generated_question.option_e,
                    ]

                    if not _quiz_item_matches_language(
                        generated_question.question_text,
                        options,
                        quiz_language,
                    ):
                        raise ValueError(
                            "Quiz sorusu hedef dille tutarlı değil."
                        )

                    _validate_single_quiz_question(
                        generated_question,
                        [
                            question.question_text
                            for question in accepted_questions
                        ],
                    )
                    accepted_questions.append(generated_question)
                    accepted_source_facts.append(generated.source_fact)
                    accepted_in_batch += 1

                except ValueError as error:
                    last_error = error
                    rejected_in_batch += 1
                    print(
                        f"LM Studio Quiz batch {batch_attempts} "
                        f"soru {raw_index + 1} reddedildi: {error}"
                    )

        except json.JSONDecodeError as error:
            last_error = error
            print(
                f"LM Studio Quiz batch {batch_attempts} "
                f"JSON decode hatası: {error}"
            )

        except ValueError as error:
            last_error = error
            print(
                f"LM Studio Quiz batch {batch_attempts} "
                f"reddedildi: {error}"
            )

        missing_outputs = max(
            0,
            batch_size - min(produced_count, batch_size),
        )
        rejected_in_batch += missing_outputs
        batch_duration = time.perf_counter() - batch_started_at
        print(
            f"LM Studio Quiz batch {batch_attempts}: "
            f"{batch_size} istendi, "
            f"{produced_count} üretildi, "
            f"{accepted_in_batch} kabul edildi, "
            f"{rejected_in_batch} reddedildi, "
            f"süre {batch_duration:.1f} sn"
        )

        retry_instruction = (
            "- Previous batch had invalid or missing questions. Use new "
            "facts and different question forms."
            if accepted_in_batch < batch_size
            else ""
        )

    if len(accepted_questions) != question_count:
        raise OllamaServiceError(
            f"LM Studio {question_count} geçerli soru üretemedi. "
            f"{len(accepted_questions)} soru kabul edildi."
        ) from last_error

    result = QuizResponse(
        questions=accepted_questions
    )
    result = _validate_quiz(
        result,
        question_count,
    )
    total_duration = time.perf_counter() - quiz_started_at
    print(
        f"LM Studio Quiz tamamlandı: "
        f"{len(result.questions)} soru, "
        f"{batch_attempts} LM Studio çağrısı, "
        f"toplam {total_duration:.1f} sn"
    )
    return result

# =========================================================
# QUIZ TEST
# =========================================================

if __name__ == "__main__":

    test_text = """
    Olasılık, bir olayın gerçekleşme ihtimalini ifade eder.
    Bir olayın olasılığı 0 ile 1 arasında değer alır.
    Kesin olayın olasılığı 1, imkansız olayın olasılığı 0'dır.

    Örneğin adil bir zar atıldığında 6 gelme olasılığı 1/6'dır.
    """

    result = generate_quiz(
        test_text,
        3
    )

    print("\n===== QUIZ TEST =====")

    for i, question in enumerate(
        result.questions,
        start=1
    ):

        print(f"\nSoru {i}")

        print(
            "Tip:",
            question.question_type
        )

        print(
            "Soru:",
            question.question_text
        )

        print(
            "A:",
            question.option_a
        )

        print(
            "B:",
            question.option_b
        )

        print(
            "C:",
            question.option_c
        )

        print(
            "D:",
            question.option_d
        )

        print(
            "E:",
            question.option_e
        )

        print(
            "Cevap:",
            question.correct_answer
        )

        print(
            "Açıklama:",
            question.explanation
        )


# =========================================================
# AI FLASHCARD OLUŞTURMA
# =========================================================

class FlashcardItem(BaseModel):
    question: str
    answer: str


class FlashcardResponse(BaseModel):
    flashcards: list[FlashcardItem]


def generate_flashcards(
    text: str,
    flashcard_count: int = 10
):
    flashcard_started_at = time.perf_counter()

    max_context_chars = 18000

    if len(text) <= max_context_chars:
        context = text
    else:
        chunk_size = max_context_chars // 3

        start_chunk = text[:chunk_size]

        middle_start = max(
            0,
            (len(text) // 2) - (chunk_size // 2)
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
Create EXACTLY {flashcard_count} flashcards using only the course material below.

RULES:

- Create exactly {flashcard_count} flashcards.
- Use only information explicitly supported by the course material.
- Do not invent facts.
- Preserve the language of the source material.
- If the source is English, write the flashcards in English.
- If the source is Turkish, write the flashcards in Turkish.
- Each flashcard must test a different important concept.
- Avoid duplicate or nearly identical flashcards.
- Questions should be short, clear and understandable on their own.
- Answers should be concise but sufficiently explanatory.
- Do not create questions whose answers cannot be directly supported by the source.
- Prefer definitions, concepts, responsibilities, relationships, processes and key facts.
- Avoid unnecessary detail.
- Return valid JSON only.
- Do not return markdown or explanatory text outside the JSON.

COURSE MATERIAL:

{context}

Return only this structure:

{{
  "flashcards": [
    {{
      "question": "...",
      "answer": "..."
    }}
  ]
}}
"""

    max_attempts = 2
    last_error = None

    for attempt in range(1, max_attempts + 1):
        attempt_started_at = time.perf_counter()

        try:
            num_predict = min(
                4000,
                max(700, flashcard_count * 180)
            )

            raw_response = _generate_with_ollama(
                prompt,
                json_schema=schema,
                num_predict=num_predict,
            )

            result = FlashcardResponse.model_validate(
                json.loads(raw_response)
            )

            if len(result.flashcards) < flashcard_count:
                missing_count = flashcard_count - len(result.flashcards)

                existing_cards = "\n".join(
                    f"- {card.question} -> {card.answer}"
                    for card in result.flashcards
                )

                completion_prompt = f"""
            The previous generation produced only {len(result.flashcards)}
            flashcards instead of {flashcard_count}.
            
            Create EXACTLY {missing_count} ADDITIONAL flashcards.

            RULES:
            - Use only the course material below.
            - Do not invent information.
            - Do not repeat any of the existing flashcards.
            - Each new flashcard must test a different important concept.
            - Preserve the language of the source material.
            - Questions must be short and clear.
            - Answers must be concise but sufficiently explanatory.
            - Return valid JSON only.
            - Return EXACTLY {missing_count} flashcards.

            EXISTING FLASHCARDS:

            {existing_cards}

            COURSE MATERIAL:

            {context}

            Return only:

            {{
              "flashcards": [
                {{
                  "question": "...",
                  "answer": "..."
                 }}
               ]
            }}
            """

                completion_schema = {
                    "type": "object",
                    "properties": {
                        "flashcards": {
                            "type": "array",
                            "minItems": missing_count,
                            "maxItems": missing_count,
                            "items": FlashcardItem.model_json_schema(),
                         }
                    },
                    "required": ["flashcards"],
                    "additionalProperties": False,
                }

                completion_response = _generate_with_ollama(
                    completion_prompt,
                    json_schema=completion_schema,
                    num_predict=max(500, missing_count * 180),
                )

                completion_result = FlashcardResponse.model_validate(
                    json.loads(completion_response)
                )

                result.flashcards.extend(completion_result.flashcards)

            if len(result.flashcards) != flashcard_count:
                raise ValueError(
                    f"{flashcard_count} flashcard bekleniyordu, "
                    f"{len(result.flashcards)} üretildi."
                )

            normalized_questions = [
                card.question.strip().lower()
                for card in result.flashcards
            ]

            if len(set(normalized_questions)) != len(normalized_questions):
                raise ValueError(
                    "Tekrarlanan flashcard soruları üretildi."
                )

            attempt_duration = (
                time.perf_counter() - attempt_started_at
            )

            total_duration = (
                time.perf_counter() - flashcard_started_at
            )

            print(
                f"Ollama Flashcard tamamlandı: "
                f"{len(result.flashcards)} kart, "
                f"AI süresi {attempt_duration:.1f} sn, "
                f"toplam {total_duration:.1f} sn"
            )

            return result

        except (
            json.JSONDecodeError,
            ValueError,
        ) as error:
            last_error = error

            duration = (
                time.perf_counter() - attempt_started_at
            )

            print(
                f"Ollama flashcard doğrulama hatası "
                f"(deneme {attempt}/{max_attempts}, "
                f"{duration:.1f} sn): {error}"
            )

            prompt += f"""

THE PREVIOUS OUTPUT WAS INVALID.

Error:
{error}

Generate the flashcards again.
Return EXACTLY {flashcard_count} unique flashcards.
Return JSON only.
"""

    raise OllamaServiceError(
        "Yapay zeka geçerli bilgi kartları oluşturamadı."
    ) from last_error


# =========================================================
# AI ÇALIŞMA ÖNERİSİ
# =========================================================

class StudyRecommendation(BaseModel):
    message: str
    priority: str
    recommended_action: str


def generate_study_recommendation(
    total_courses: int,
    total_quizzes: int,
    quiz_average: float,
    total_flashcards: int,
    flashcard_reviews: int,
    weakest_course: Optional[str] = None,    
    study_hours: float = 0
):

    prompt = f"""
Bir öğrencinin çalışma verilerini analiz et ve
ona kişiselleştirilmiş bir çalışma önerisi oluştur.

Öğrenci verileri:

- Toplam ders sayısı: {total_courses}
- Toplam quiz sayısı: {total_quizzes}
- Quiz ortalaması: {quiz_average}
- Toplam flashcard sayısı: {total_flashcards}
- Yapılan flashcard tekrar sayısı: {flashcard_reviews}
- En zayıf ders: {weakest_course or "Belirlenmemiş"}
- Çalışma süresi: {study_hours} saat

Kurallar:

- Türkçe yaz.
- Öğrencinin verilerine göre gerçekçi bir öneri oluştur.
- Verilmeyen bilgileri uydurma.
- Kısa ve net ol.
- Öğrenciye bugün ne yapması gerektiğini söyle.
- Eğer quiz ortalaması düşükse quiz çalışmasına ağırlık ver.
- Eğer flashcard tekrarları düşükse tekrar yapmasını öner.
- En zayıf ders belli ise önceliği o derse ver.
- Çalışma süresi düşükse uygulanabilir bir çalışma süresi öner.
- Priority değeri yalnızca "low", "medium" veya "high" olabilir.

message alanında öğrencinin mevcut durumunu
kısa şekilde açıkla.

recommended_action alanında öğrencinin bugün
uygulayabileceği somut bir çalışma görevi ver.
"""

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=StudyRecommendation,
        ),
    )

    return response.parsed

# =========================================================
# PDF ÜZERİNDEN AI SOHBET
# =========================================================

def ask_ai_about_document(
    document_text: str,
    question: str
):
    prompt = f"""
Sen StudyFlow AI adlı kişisel öğrenme platformunun
ders asistanısın.

Aşağıdaki ders notunu kaynak olarak kullanarak
öğrencinin sorusunu cevapla.

Kurallar:
- Yalnızca verilen ders notundaki bilgilere dayan.
- Ders notunda cevap yoksa bunu açıkça belirt.
- Bilgi uydurma.
- Türkçe cevap ver.
- Anlaşılır ve öğretici ol.
- Gereksiz uzun cevap verme.

DERS NOTU:
{document_text[:30000]}

ÖĞRENCİNİN SORUSU:
{question}
"""

    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=prompt,
    )

    return response.text


# =========================================================
# AI ÇALIŞMA PLANI OLUŞTURMA
# =========================================================

class StudyPlanItem(BaseModel):
    day: str
    course: str
    duration_minutes: int
    reason: str


class PlannerResponse(BaseModel):
    weekly_plan: list[StudyPlanItem]
    general_advice: str


class PlannerServiceUnavailableError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__("Gemini planner service is temporarily unavailable.")


def _transient_gemini_status(error: errors.APIError) -> Optional[int]:
    code = getattr(error, "code", None)

    if code in (429, 503):
        return code

    message = str(error).upper()

    if "RESOURCE_EXHAUSTED" in message or "RATE LIMIT" in message:
        return 429

    if "UNAVAILABLE" in message:
        return 503

    return None


def generate_study_plan(
    courses,
    events,
    goals,
    available_hours_per_day: float,
    weekly_hours_target: float
):

    # ---------------------------------------------------------
    # DERS BİLGİLERİ
    # ---------------------------------------------------------

    course_info = []

    for course in courses:
        course_info.append({
            "id": course.id,
            "name": course.name,
            "description": course.description
        })

    # ---------------------------------------------------------
    # EVENT BİLGİLERİ
    # ---------------------------------------------------------

    event_info = []

    for event in events:
        event_info.append({
            "title": event.title,
            "event_type": event.event_type,
            "start_date": str(event.start_date),
            "end_date": str(event.end_date) if event.end_date else None,
            "course_id": event.course_id
        })

    # ---------------------------------------------------------
    # HEDEF BİLGİLERİ
    # ---------------------------------------------------------

    goal_info = []

    for goal in goals:
        goal_info.append({
            "title": goal.title,
            "goal_type": goal.goal_type,
            "target_value": goal.target_value,
            "current_value": goal.current_value,
            "start_date": str(goal.start_date),
            "end_date": str(goal.end_date),
            "completed": goal.completed,
            "course_id": goal.course_id
        })

    # ---------------------------------------------------------
    # GERÇEK DERS İSİMLERİ
    # ---------------------------------------------------------

    course_names = [
        course.name
        for course in courses
    ]

    # ---------------------------------------------------------
    # PLANLAMA KAPASİTESİ
    # ---------------------------------------------------------

    daily_limit_minutes = int(
        available_hours_per_day * 60
    )

    weekly_target_minutes = int(
        weekly_hours_target * 60
    )

    maximum_weekly_minutes = (
        daily_limit_minutes * 7
    )

    # Haftalık hedef günlük kapasiteden büyükse
    # AI'ya gerçekçi maksimum süreyi bildiriyoruz.
    effective_weekly_target_minutes = min(
        weekly_target_minutes,
        maximum_weekly_minutes
    )

    effective_weekly_target_hours = (
        effective_weekly_target_minutes / 60
    )

    # ---------------------------------------------------------
    # PROMPT
    # ---------------------------------------------------------

    prompt = f"""
Sen StudyFlow AI adlı kişisel öğrenme platformunun
AI çalışma planlayıcısısın.

Öğrencinin mevcut verilerini analiz ederek
önümüzdeki 7 gün için gerçekçi, dengeli ve
uygulanabilir bir çalışma planı oluştur.

==================================================
ÖĞRENCİNİN BİLGİLERİ
==================================================

Günlük maksimum çalışma süresi:
{available_hours_per_day} saat

Günlük maksimum çalışma süresi:
{daily_limit_minutes} dakika

Öğrencinin haftalık çalışma hedefi:
{weekly_hours_target} saat

Öğrencinin uygulanabilir maksimum haftalık çalışma kapasitesi:
{maximum_weekly_minutes} dakika

Planlanması gereken haftalık çalışma süresi:
{effective_weekly_target_minutes} dakika
({effective_weekly_target_hours} saat)


==================================================
ÖĞRENCİNİN DERSLERİ
==================================================

{course_info}


==================================================
YAKLAŞAN ETKİNLİKLER
==================================================

{event_info}


==================================================
ÖĞRENCİNİN AKTİF HEDEFLERİ
==================================================

{goal_info}


==================================================
PLANLAMA KURALLARI
==================================================

1. Türkçe yaz.

2. Tam olarak 7 günlük plan oluştur:
   Pazartesi
   Salı
   Çarşamba
   Perşembe
   Cuma
   Cumartesi
   Pazar

3. Günlük toplam çalışma süresi
   {daily_limit_minutes} dakikayı kesinlikle geçmemelidir.

4. Haftalık toplam çalışma süresi
   mümkün olduğunca tam olarak
   {effective_weekly_target_minutes} dakika olmalıdır.

5. Haftalık hedef günlük kapasiteden büyükse,
   günlük kapasiteyi aşma.
   Bu durumda maksimum uygulanabilir süreyi kullan.

6. Dersleri yalnızca öğrencinin gerçek
   ders listesinden seç.

7. Öğrencinin ders listesinde olmayan hiçbir
   ders oluşturma.

8. Ders isimlerini kesinlikle birleştirme.

   Örneğin:

   YANLIŞ:
   "Matematik ve Veri Yapıları"

   DOĞRU:
   "Matematik"

   veya:

   "Veri Yapıları"

9. Her plan öğesinde yalnızca BİR ders bulunmalıdır.

10. Bir güne birden fazla çalışma kaydı
    koyabilirsin.

11. Yaklaşan sınavlara öncelik ver.

12. Yaklaşan ödevlere öncelik ver.

13. Yaklaşan projelere öncelik ver.

14. Aktif hedefleri dikkate al.

15. Dersleri mümkün olduğunca dengeli dağıt.

16. Aynı dersi gereksiz şekilde her güne koyma.

17. Ancak yaklaşan sınav veya önemli bir
    deadline varsa ilgili derse daha fazla
    çalışma süresi ayırabilirsin.

18. Konu bilgisi verilmediği için konu
    uydurma.

19. Output içinde topics alanı bulunmayacaktır.

20. Her çalışma kaydının duration_minutes
    değeri gerçekçi olmalıdır.

21. Çalışma süreleri dakika cinsinden olmalıdır.

22. Her gün mutlaka çalışma kaydı oluşturmak
    zorunda değilsin.

23. Fakat 7 günlük plan içerisinde toplam
    çalışma süresini haftalık hedefe
    mümkün olduğunca tam olarak ulaştır.

24. Tamamlanmış hedefleri dikkate alma.

25. Tamamlanmış eventleri dikkate alma.

26. Verilmeyen bilgileri uydurma.

27. general_advice içerisinde yanlış bir
    haftalık toplam süre belirtme.

28. Planın toplam süresini hesaplarken
    duration_minutes değerlerini dikkate al.

29. Haftalık hedef:
    {effective_weekly_target_minutes} dakika.

30. Bu hedefi aşma.

31. Mümkünse bu hedefin altında da kalma.


==================================================
GEÇERLİ DERSLER
==================================================

course alanı SADECE aşağıdaki değerlerden
biri olabilir:

{course_names}


==================================================
ÇIKTI KURALLARI
==================================================

JSON dışında hiçbir şey döndürme.

weekly_plan içerisindeki her nesne şu alanlara
sahip olmalıdır:

- day
- course
- duration_minutes
- reason

topics ALANI KULLANMA.

Her nesnede yalnızca bir ders olmalıdır.

course değeri yukarıdaki gerçek derslerden
biri olmalıdır.

duration_minutes pozitif bir sayı olmalıdır.

general_advice kısa ve Türkçe olmalıdır.

Plan öğrencinin günlük ve haftalık çalışma
kapasitesini aşmamalıdır.
"""

    # ---------------------------------------------------------
    # GEMINI
    # ---------------------------------------------------------

    maximum_attempts = 3

    for attempt in range(1, maximum_attempts + 1):
        try:
            response = client.models.generate_content(
                model="gemini-3.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=PlannerResponse,
                ),
            )
            break
        except errors.APIError as error:
            transient_status = _transient_gemini_status(error)

            if transient_status is None:
                raise

            if attempt == maximum_attempts:
                raise PlannerServiceUnavailableError(
                    transient_status
                ) from error

            time.sleep(2 ** (attempt - 1))

    # ---------------------------------------------------------
    # AI CEVABI KONTROL
    # ---------------------------------------------------------

    if response.parsed is None:

        print("AI PLANNER RESPONSE PARSED NONE")
        print("AI RESPONSE TEXT:")
        print(response.text)

        raise ValueError(
            "AI Planner geçerli bir plan oluşturamadı."
        )

    result = response.parsed

    # ---------------------------------------------------------
    # BACKEND KONTROLLERİ
    # ---------------------------------------------------------

    valid_course_names = set(course_names)

    total_minutes = 0

    for item in result.weekly_plan:

        # Geçersiz ders kontrolü
        if item.course not in valid_course_names:

            raise ValueError(
                f"AI geçersiz bir ders oluşturdu: {item.course}"
            )

        # Günlük limit kontrolü daha aşağıda
        total_minutes += item.duration_minutes

    # ---------------------------------------------------------
    # HAFTALIK TOPLAM KONTROLÜ
    # ---------------------------------------------------------

    if total_minutes > effective_weekly_target_minutes:

        raise ValueError(
            f"AI haftalık çalışma hedefini aştı. "
            f"Hedef: {effective_weekly_target_minutes} dakika, "
            f"oluşturulan: {total_minutes} dakika."
        )

    # ---------------------------------------------------------
    # GÜNLÜK TOPLAM KONTROLÜ
    # ---------------------------------------------------------

    daily_totals = {}

    for item in result.weekly_plan:

        daily_totals[item.day] = (
            daily_totals.get(item.day, 0)
            + item.duration_minutes
        )

    for day, total in daily_totals.items():

        if total > daily_limit_minutes:

            raise ValueError(
                f"{day} günü günlük çalışma limitini aşıyor. "
                f"Limit: {daily_limit_minutes} dakika, "
                f"oluşturulan: {total} dakika."
            )

    # ---------------------------------------------------------
    # SONUÇ
    # ---------------------------------------------------------

    print(
        f"AI Planner oluşturuldu. "
        f"Haftalık toplam: {total_minutes} dakika / "
        f"{effective_weekly_target_minutes} dakika"
    )

    return result
