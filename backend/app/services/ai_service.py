from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal, Optional
from difflib import SequenceMatcher
import httpx
import json
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
    options: list[str] = Field(min_length=5, max_length=5)
    correct_answer: Literal["A", "B", "C", "D", "E"]


class OllamaBatchQuestion(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    question_text: str = Field(alias="q")
    options: list[str] = Field(alias="o", min_length=5, max_length=5)
    correct_answer: Literal["A", "B", "C", "D", "E"] = Field(alias="a")


class OllamaQuizBatch(BaseModel):
    questions: list[OllamaBatchQuestion] = Field(min_length=1, max_length=5)


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
_ANSWER_LETTER_OPTION = re.compile(
    r"^\s*[A-E]\s*[.)]?\s*$",
    re.IGNORECASE,
)
_OPEN_ENDED_TASK = re.compile(
    r"\b(?:çiziniz|çizin|açıklayınız|açıklayın|yorumlayınız|yorumlayın|"
    r"ispatlayınız|ispatlayın|gösteriniz|gösterin|inceleyiniz|inceleyin|"
    r"çözümü\s+sununuz|çözümü\s+sunun)\b"
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
_PROMPT_META_QUESTION = re.compile(
    r"\b(?:json\s+(?:oluştur|formatında)|verilen\s+materyali\s+açıkla|"
    r"verilen\s+materyalin\s+sorusu|çözümü\s+sun|(?:bir\s+)?teorem\s+ispatla|"
    r"yukarıdaki\s+talimatlara\s+göre|bu\s+prompt|bu\s+metin)\w*\b",
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

        if question.question_type != "multiple_choice":
            raise ValueError(
                f"{index}. sorunun soru tipi geçersiz: "
                f"{question.question_type}"
            )

        if not question.question_text.strip():
            raise ValueError(f"{index}. sorunun soru metni boş.")

        question_text = question.question_text.strip()

        if _is_obviously_broken_question(question_text):
            raise ValueError(
                f"{index}. sorunun metni anlamsız veya eksik görünüyor."
            )

        if len(_SUBQUESTION_NUMBERING.findall(question_text)) >= 2:
            raise ValueError(
                f"{index}. sorunun metninde birden fazla alt soru var."
            )

        if len(_SUBQUESTION_LETTERING.findall(question_text)) >= 2:
            raise ValueError(
                f"{index}. sorunun metninde birden fazla alt soru var."
            )

        if len(_EMBEDDED_OPTION.findall(question_text)) >= 3:
            raise ValueError(
                f"{index}. sorunun seçenekleri question_text içine gömülmüş."
            )

        if _VAGUE_QUESTION_STEM.search(question_text):
            raise ValueError(
                f"{index}. sorunun soru kökü belirsiz; neyin sorulduğu açık değil."
            )

        if _PROMPT_META_QUESTION.search(question_text):
            raise ValueError(
                f"{index}. soru kaynak yerine prompt veya sistem talimatını soruyor."
            )

        if _looks_like_information_block(question_text):
            raise ValueError(
                f"{index}. sorunun metni soru yerine çok maddeli bir bilgi bloğu içeriyor."
            )

        question_mark_count = question_text.count("?") + question_text.count("؟")

        if question_mark_count > 2:
            raise ValueError(
                f"{index}. sorunun metninde gereksiz sayıda soru işareti var."
            )

        normalized_for_tasks = question_text.casefold()

        if (
            _OPEN_ENDED_TASK.search(normalized_for_tasks)
            or len(_TASK_VERB.findall(normalized_for_tasks)) >= 2
        ):
            raise ValueError(
                f"{index}. soru açık uçlu veya birden fazla görev içeriyor."
            )

        normalized_question = _normalized_question_text(question_text)
        comparison_texts = list(previous_question_texts or [])
        comparison_texts.extend(
            item.question_text for item in quiz.questions[:index - 1]
        )

        for previous_text in comparison_texts:
            normalized_previous = _normalized_question_text(previous_text)
            similarity = SequenceMatcher(
                None,
                normalized_question,
                normalized_previous,
            ).ratio()

            if normalized_question == normalized_previous or similarity >= 0.9:
                raise ValueError(
                    f"{index}. soru önceki bir soruyla aşırı benzer."
                )

        if not question.correct_answer.strip():
            raise ValueError(f"{index}. sorunun doğru cevabı boş.")

        if not question.explanation.strip():
            raise ValueError(f"{index}. sorunun açıklaması boş.")

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

        if any(_ANSWER_LETTER_OPTION.fullmatch(option) for option in options):
            raise ValueError(
                f"{index}. multiple choice sorusunda yalnızca cevap "
                "harfinden oluşan şık var."
            )

        if any(_OPTION_PREFIX.match(option) for option in options):
            raise ValueError(
                f"{index}. multiple choice seçeneği A), B) gibi seçenek etiketi içeriyor."
            )

        normalized_options = [option.strip().casefold() for option in options]

        if len(set(normalized_options)) != 5:
            raise ValueError(
                f"{index}. multiple choice sorusunda tekrarlanan şık var."
            )

        canonical_options = [_canonical_option(option) for option in options]

        if len(set(canonical_options)) != 5:
            raise ValueError(
                f"{index}. soruda anlamsal olarak tekrarlanan seçenek var."
            )

        single_number_option_count = sum(
            _SINGLE_NUMBER_OPTION.fullmatch(option.strip()) is not None
            for option in options
        )

        if (
            _RANGE_QUESTION.search(question_text)
            and single_number_option_count >= 4
        ):
            raise ValueError(
                f"{index}. aralık sorusu yalnızca tekil sayısal seçenekler içeriyor."
            )

        generic_option_count = sum(
            _normalized_question_text(option) in _GENERIC_OPTION_VALUES
            for option in options
        )

        if generic_option_count >= 3:
            raise ValueError(
                f"{index}. soru doğru-yanlış kılığına sokulmuş veya "
                "yapay dolgu seçenekleri içeriyor."
            )

        question.correct_answer = question.correct_answer.strip().upper()

        if question.correct_answer not in {"A", "B", "C", "D", "E"}:
            raise ValueError(
                f"{index}. multiple choice sorusunun doğru cevabı "
                "A, B, C, D veya E olmalı."
            )

    return quiz


def _to_quiz_question(generated) -> QuizQuestion:
    normalized_options = [
        (
            option.strip()
            if _ANSWER_LETTER_OPTION.fullmatch(option)
            else _OPTION_PREFIX.sub("", option, count=1).strip()
        )
        for option in generated.options
    ]

    return QuizQuestion(
        question_type="multiple_choice",
        question_text=generated.question_text,
        option_a=normalized_options[0],
        option_b=normalized_options[1],
        option_c=normalized_options[2],
        option_d=normalized_options[3],
        option_e=normalized_options[4],
        correct_answer=generated.correct_answer,
        explanation=f"Doğru cevap: {generated.correct_answer}",
    )


BATCH_SIZE = 5
BATCH_NUM_PREDICT = 1250


def _previous_questions_prompt(questions: list[QuizQuestion]) -> str:
    return "\n".join(
        f"- {question.question_text[:160]}" for question in questions[-10:]
    ) or "Henüz önceki soru yok."


def _batch_json_schema(expected_count: int) -> dict:
    schema = OllamaQuizBatch.model_json_schema()
    schema["properties"]["questions"]["minItems"] = expected_count
    schema["properties"]["questions"]["maxItems"] = expected_count
    return schema


def _parse_batch_questions(
    raw_response: str,
    expected_count: int,
    label: str,
) -> list[Optional[OllamaBatchQuestion]]:
    try:
        batch_data = json.loads(raw_response)
        raw_questions = batch_data.get("questions")
        if not isinstance(raw_questions, list) or len(raw_questions) != expected_count:
            raise ValueError(
                f"Yanıt tam olarak {expected_count} soru içermiyor."
            )
    except (json.JSONDecodeError, ValueError, AttributeError) as error:
        print(f"{label} structured output hatası: {error}")
        return [None] * expected_count

    generated_items: list[Optional[OllamaBatchQuestion]] = []
    for slot, raw_question in enumerate(raw_questions, start=1):
        try:
            generated_items.append(
                OllamaBatchQuestion.model_validate(raw_question)
            )
        except ValueError as error:
            generated_items.append(None)
            print(f"{label}, soru {slot} structured output hatası: {error}")
    return generated_items


def _validate_batch_questions(
    generated_items: list[Optional[OllamaBatchQuestion]],
    previous_questions: list[QuizQuestion],
    label: str,
) -> tuple[list[QuizQuestion], int, int]:
    valid_questions: list[QuizQuestion] = []
    invalid_count = 0
    similarity_invalid_count = 0

    for slot, generated in enumerate(generated_items, start=1):
        if generated is None:
            invalid_count += 1
            continue
        try:
            candidate = _to_quiz_question(generated)
            _validate_quiz(
                QuizResponse(questions=[candidate]),
                1,
                previous_question_texts=[
                    question.question_text
                    for question in previous_questions + valid_questions
                ],
            )
            valid_questions.append(candidate)
        except ValueError as error:
            invalid_count += 1
            if "aşırı benzer" in str(error).casefold():
                similarity_invalid_count += 1
            print(f"{label}, soru {slot} doğrulama hatası: {error}")

    return valid_questions, invalid_count, similarity_invalid_count


def _repair_num_predict(question_count: int) -> int:
    repair_limits = (350, 500, 700, 900, 1150)
    return repair_limits[question_count - 1]


def _select_batch_context(
    quiz_source: str,
    batch_index: int,
    total_batches: int,
    max_context_chars: int,
) -> tuple[int, str]:
    if total_batches == 1:
        return 0, quiz_source[:max_context_chars]

    source_length = len(quiz_source)
    region_start = source_length * batch_index // total_batches
    region_end = source_length * (batch_index + 1) // total_batches

    if region_start:
        next_line_break = quiz_source.find(
            "\n",
            region_start,
            min(region_start + 500, region_end),
        )
        if next_line_break != -1:
            region_start = next_line_break + 1

    context_end = min(region_end, region_start + max_context_chars)
    return region_start, quiz_source[region_start:context_end]


def _select_repair_context(
    quiz_source: str,
    main_context_start: int,
    main_context_length: int,
) -> tuple[int, str]:
    if not quiz_source or main_context_length <= 0:
        return main_context_start, quiz_source

    window_length = min(main_context_length, len(quiz_source))
    last_start = len(quiz_source) - window_length
    if last_start <= 0:
        return main_context_start, quiz_source[:window_length]

    candidate_starts = list(range(0, last_start + 1, window_length))
    if candidate_starts[-1] != last_start:
        candidate_starts.append(last_start)

    main_context_end = main_context_start + main_context_length

    def candidate_score(candidate_start: int) -> tuple[int, int]:
        candidate_end = candidate_start + window_length
        overlap = max(
            0,
            min(main_context_end, candidate_end)
            - max(main_context_start, candidate_start),
        )
        distance = abs(candidate_start - main_context_start)
        return overlap, -distance

    repair_start = min(candidate_starts, key=candidate_score)
    if repair_start:
        next_line_break = quiz_source.find(
            "\n",
            repair_start,
            min(repair_start + 500, len(quiz_source)),
        )
        if next_line_break != -1:
            repair_start = next_line_break + 1

    repair_end = min(len(quiz_source), repair_start + window_length)
    repair_context = quiz_source[repair_start:repair_end]
    if not repair_context.strip():
        return main_context_start, quiz_source[
            main_context_start:main_context_end
        ]
    return repair_start, repair_context


def generate_quiz(
    text: str,
    question_count: int = 10
):
    quiz_source = _prepare_quiz_source(text)
    questions: list[QuizQuestion] = []
    max_context_chars = 15000
    quiz_started_at = time.perf_counter()
    total_batches = (question_count + BATCH_SIZE - 1) // BATCH_SIZE
    main_call_count = 0
    repair_call_count = 0

    print(f"Quiz üretimi başladı: {question_count} soru")

    for batch_index in range(total_batches):
        context_start, context = _select_batch_context(
            quiz_source,
            batch_index,
            total_batches,
            max_context_chars,
        )
        previous_questions = _previous_questions_prompt(questions)
        batch_prompt = f"""
Yalnızca JSON üret. Kaynaktan tam {BATCH_SIZE} kısa multiple-choice soru yaz.
Her q bağımsız, tek görevli, 1-2 kısa cümle ve yalnızca kaynağa dayalı olsun.
Her o dizisi tam 5 farklı, mümkün olduğunca kısa ve net seçenek içersin.
Yalnızca bir seçenek doğru olsun; a alanına A/B/C/D/E yaz.
Hiçbir seçenek yalnızca A/B/C/D/E harfi olamaz; a harfini option olarak yazma.
Bu batch içindeki sorular birbirinden farklı alt konuları ve kavramları ölçsün.
q hangi cevap türünü istiyorsa tüm o seçenekleri o semantik türde yaz:
yaklaşım sorusuna yaklaşım/metot adları, süreç sorusuna süreç/kavram adları,
avantaj sorusuna avantaj/sonuçlar, aşama sorusuna aşama adları, yıl/dönem
sorusuna tarihler/dönemler, neden sorusuna neden/açıklamalar ver.
Seçenekleri benzer uzunlukta ve aynı dilbilgisel yapıda tut; uzun açıklama ile
tek kelimelik terimleri karıştırma. Kaynakta bulunmayan teknik terim, kategori
ve jargon uydurma; gerçek kaynak kavramları veya açıkça mantıklı yanlışlar kullan.
q doğru cevabı aynen tekrar ederek ya da açıkça işaret ederek ele vermesin.
Dersi kendin belirle. Hesaplama için gereken tüm veriler q içinde yoksa
kavramsal soru seç. Dış bilgi, açık uçlu emir, prompt sorusu veya görünmeyen
tablo/şekil/önceki bilgiye gönderme üretme.
Her soru yalnızca q, o, a alanlarını içersin; başka alan veya açıklama ekleme.

DAHA ÖNCE ÜRETİLEN SORULAR:
{previous_questions}
Bunlarla aynı soruyu, aynı kavramı aynı biçimde veya yalnızca birkaç sözcüğü
değiştirilmiş bir sürümünü üretme. Kaynaktan yeni kavramlar seç.

KAYNAK:
{context}
"""
        batch_started_at = time.perf_counter()
        print(
            f"Batch {batch_index + 1}/{total_batches} ana başladı: "
            f"{BATCH_SIZE} soru, num_predict={BATCH_NUM_PREDICT}, "
            f"context_start={context_start}"
        )
        main_call_count += 1
        raw_response = _generate_with_ollama(
            batch_prompt,
            json_schema=_batch_json_schema(BATCH_SIZE),
            num_predict=BATCH_NUM_PREDICT,
        )
        generated_items = _parse_batch_questions(
            raw_response,
            BATCH_SIZE,
            f"Batch {batch_index + 1} ana",
        )
        (
            valid_batch_questions,
            invalid_count,
            similarity_invalid_count,
        ) = _validate_batch_questions(
            generated_items,
            questions,
            f"Batch {batch_index + 1} ana",
        )
        questions.extend(valid_batch_questions)
        batch_duration = time.perf_counter() - batch_started_at
        print(
            f"Batch {batch_index + 1}/{total_batches} ana: "
            f"{batch_duration:.1f} sn, {len(valid_batch_questions)} valid / "
            f"{invalid_count} invalid"
        )

        if invalid_count:
            repair_context_start = context_start
            repair_context = context
            similarity_repair_instruction = ""
            if similarity_invalid_count:
                repair_context_start, repair_context = _select_repair_context(
                    quiz_source,
                    context_start,
                    len(context),
                )
                similarity_repair_instruction = (
                    "Önceki sorularla aynı ana kavramı yeniden sorma. "
                    "Yalnızca kelimeleri değiştirerek yeni soru üretme. "
                    "Verilen alternatif kaynak bölümündeki farklı bir alt "
                    "konuyu seç."
                )
            repair_prompt = f"""
Yalnızca JSON üret. Kaynaktan tam {invalid_count} YENİ, kısa multiple-choice
soru yaz. Her q bağımsız, tek görevli, 1-2 kısa cümle ve kaynağa dayalı olsun.
Her o dizisi tam 5 farklı, kısa ve net seçenek içersin; yalnızca biri doğru olsun.
a alanına A/B/C/D/E yaz. Dersi kendin belirle.
Hiçbir seçenek yalnızca A/B/C/D/E harfi olamaz; a harfini option olarak yazma.
Eksik verili hesaplama, dış bilgi, açık uçlu emir, prompt sorusu veya
tablo/şekil/önceki bilgiye gönderme üretme.
Repair içindeki sorular da birbirinden farklı alt konuları ve kavramları ölçsün.
q hangi cevap türünü istiyorsa tüm o seçenekleri o türde yaz: yaklaşım/metot,
süreç/kavram, avantaj/sonuç, aşama, tarih/dönem veya neden/açıklama türlerini
birbiriyle karıştırma. Seçenekleri benzer uzunlukta ve aynı dilbilgisel yapıda
tut; uzun cümlelerle tek sözcüklü terimleri karıştırma. Kaynakta bulunmayan
teknik terim, kategori veya jargon uydurma; gerçek kavramlar ya da açıkça
mantıklı yanlışlar kullan. q doğru cevabı aynen tekrar ederek ele vermesin.
Her soru yalnızca q, o, a alanlarını içersin; açıklama veya başka alan ekleme.
{similarity_repair_instruction}

DAHA ÖNCE KABUL EDİLEN SORULAR:
{_previous_questions_prompt(questions)}
Bunlarla aynı soruyu, aynı kavramı aynı biçimde veya yalnızca birkaç sözcüğü
değiştirilmiş bir sürümünü üretme. Kaynaktan yeni kavramlar seç.

KAYNAK:
{repair_context}
"""
            repair_started_at = time.perf_counter()
            repair_num_predict = _repair_num_predict(invalid_count)
            print(
                f"Batch {batch_index + 1} repair başladı: "
                f"{invalid_count} soru, num_predict={repair_num_predict}, "
                f"context_start={repair_context_start}"
            )
            repair_call_count += 1
            repair_response = _generate_with_ollama(
                repair_prompt,
                json_schema=_batch_json_schema(invalid_count),
                num_predict=repair_num_predict,
            )
            repair_items = _parse_batch_questions(
                repair_response,
                invalid_count,
                f"Batch {batch_index + 1} repair",
            )
            (
                repaired_questions,
                repair_invalid_count,
                _,
            ) = _validate_batch_questions(
                repair_items,
                questions,
                f"Batch {batch_index + 1} repair",
            )
            repair_duration = time.perf_counter() - repair_started_at
            print(
                f"Batch {batch_index + 1} repair: {invalid_count} soru, "
                f"{repair_duration:.1f} sn, {len(repaired_questions)} valid / "
                f"{repair_invalid_count} invalid"
            )
            if repair_invalid_count:
                total_duration = time.perf_counter() - quiz_started_at
                print(f"Toplam ana batch çağrısı: {main_call_count}")
                print(f"Toplam repair çağrısı: {repair_call_count}")
                print(
                    "Toplam gerçek Ollama çağrı sayısı: "
                    f"{main_call_count + repair_call_count}"
                )
                print(f"Quiz üretimi kontrollü durduruldu: {total_duration:.1f} sn")
                raise OllamaServiceError(
                    "Yapay zeka geçerli quiz soruları oluşturamadı."
                )
            questions.extend(repaired_questions)

    quiz = QuizResponse(questions=questions)
    quiz = _validate_quiz(quiz, question_count)

    total_duration = time.perf_counter() - quiz_started_at
    print(f"Toplam ana batch çağrısı: {main_call_count}")
    print(f"Toplam repair çağrısı: {repair_call_count}")
    print(
        f"Toplam gerçek Ollama çağrı sayısı: "
        f"{main_call_count + repair_call_count}"
    )
    print(
        f"Quiz tamamlandı: {len(quiz.questions)} soru, "
        f"toplam {total_duration:.1f} sn"
    )

    return quiz


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

    prompt = f"""
Aşağıdaki ders notuna göre {flashcard_count} adet flashcard oluştur.

Kurallar:

- Sorular yalnızca verilen ders notundaki bilgilere dayanmalı.
- Bilgi uydurma.
- Her soru farklı bir kavramı veya önemli bilgiyi ölçmeli.
- Sorular kısa ve anlaşılır olmalı.
- Cevaplar kısa ama yeterince açıklayıcı olmalı.
- Türkçe yaz.
- Flashcard'lar sınava hazırlanmak için kullanılabilecek nitelikte olmalı.
- Gereksiz ayrıntılardan kaçın.
- Aynı bilgiyi tekrar eden kartlar oluşturma.

Ders Notu:

{text[:30000]}

Yalnızca aşağıdaki yapıda geçerli JSON döndür:

{{
  "flashcards": [
    {{
      "question": "...",
      "answer": "..."
    }}
  ]
}}
"""

    try:
        raw_response = _generate_with_ollama(prompt, json_response=True)
        result = FlashcardResponse.model_validate(json.loads(raw_response))
    except (json.JSONDecodeError, ValueError) as error:
        raise OllamaServiceError(
            "Yapay zeka geçerli bir yanıt oluşturamadı."
        ) from error

    if len(result.flashcards) != flashcard_count:
        raise OllamaServiceError(
            "Yapay zeka geçerli bir yanıt oluşturamadı."
        )

    return result


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
