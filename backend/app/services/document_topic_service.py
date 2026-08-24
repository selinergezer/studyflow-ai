import json
import logging
import re
import time
import unicodedata
from collections import deque
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from queue import Queue

from app.services.ai_service import (
    LMStudioServiceError,
    _clean_json_response,
    _generate_with_lmstudio,
    _generate_with_lmstudio_stream,
)


logger = logging.getLogger(__name__)

CHUNK_MAX_CHARS = 4500
LONG_DOCUMENT_MIN_CHARS = 100000


def _is_reference_section_heading(line: str) -> bool:
    normalized = line.strip()
    normalized = re.sub(r"^[#*_\-\s]+", "", normalized)
    normalized = re.sub(r"[#*_\s]+$", "", normalized)
    normalized = re.sub(
        r"^\d+(?:\.\d+)*[.)]?\s*",
        "",
        normalized,
    )
    normalized = normalized.strip().rstrip(":").strip().casefold()

    return normalized in {
        "kaynakça",
        "kaynaklar",
        "references",
        "bibliography",
        "further reading",
    }


def clean_document_text(text: str) -> str:
    if not text:
        return ""

    lines = []

    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()

        if not line:
            continue

        if _is_reference_section_heading(line):
            break

        if re.fullmatch(r"(?:sayfa|page)?\s*\d+(?:\s*/\s*\d+)?", line.casefold()):
            continue

        if re.match(r"https?://|www\.", line.casefold()):
            continue

        lines.append(line)

    return "\n".join(lines).strip()


def split_document_into_chunks(
    text: str,
    max_chars: int = CHUNK_MAX_CHARS,
) -> list[str]:

    text = clean_document_text(text)

    if not text:
        return []

    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n+", text)
        if paragraph.strip()
    ]

    chunks = []
    current_chunk = []

    current_length = 0

    for paragraph in paragraphs:

        paragraph_length = len(paragraph)

        if (
            current_chunk
            and current_length + paragraph_length + 1 > max_chars
        ):
            chunks.append("\n".join(current_chunk))

            current_chunk = []
            current_length = 0

        current_chunk.append(paragraph)
        current_length += paragraph_length + 1

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks


def _is_front_matter_line(line: str) -> bool:
    return bool(
        re.search(
            r"\b(?:isbn|matbaa|iletişim|dizgi|telefon|tel\.?|adres|"
            r"yayınevi|yayınları|copyright|telif|caddesi|sokak|mahallesi|"
            r"bulvarı|organize sanayi|sanayiciler sitesi)\b|"
            r"\bD:\s*\d+\b|https?://|www\.",
            line,
            flags=re.IGNORECASE,
        )
    )


def _clean_long_document_front_matter(text: str) -> str:
    cleaned_lines = []

    for index, raw_line in enumerate(text.splitlines()):
        line = " ".join(raw_line.split()).strip()

        if not line:
            cleaned_lines.append("")
            continue

        if index < 120 and _is_front_matter_line(line):
            continue

        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def _heading_key(line: str) -> str:
    normalized = unicodedata.normalize("NFKD", _clean_section_title(line))
    normalized = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return " ".join(normalized.casefold().split())


def _is_heading_boilerplate(line: str) -> bool:
    return _heading_key(line) in {
        "tarih ders notlari",
        "kapi serisi tarih ders notlari",
        "not aliniz",
    }


def _is_section_heading(line: str, *, coarse: bool = False) -> bool:
    candidate = " ".join(line.split()).strip()

    if (
        not candidate
        or len(candidate) > 100
        or _is_reference_section_heading(candidate)
        or _is_front_matter_line(candidate)
        or _is_heading_boilerplate(candidate)
        or candidate.startswith("(")
        or candidate[0].islower()
        or candidate.endswith("-")
        or candidate.endswith((".", "!", "?", ";"))
    ):
        return False

    words = candidate.strip("#*_ -:").split()

    minimum_words = 4 if coarse else 3

    if not minimum_words <= len(words) <= 12:
        return False

    if re.match(r"^\d+[.)]\s+", candidate):
        return False

    letters = [character for character in candidate if character.isalpha()]

    if not letters:
        return False

    uppercase_ratio = sum(character.isupper() for character in letters) / len(
        letters
    )
    return uppercase_ratio >= (0.95 if coarse else 0.9)


def _clean_section_title(line: str) -> str:
    title = re.sub(r"^[#*_\-\s]+", "", line.strip())
    title = re.sub(r"[#*_\s]+$", "", title)
    return " ".join(title.split()).rstrip(":").strip()


def _is_heading_continuation(line: str) -> bool:
    candidate = " ".join(line.split()).strip()

    if (
        not candidate
        or len(candidate) > 50
        or candidate.startswith(("(", "-"))
        or candidate.endswith((".", "!", "?", ";", "-"))
        or _is_reference_section_heading(candidate)
        or _is_front_matter_line(candidate)
        or re.match(r"^\d+[.)]?\s*", candidate)
    ):
        return False

    words = candidate.strip("#*_ -:").split()

    if not 1 <= len(words) <= 3:
        return False

    letters = [character for character in candidate if character.isalpha()]

    if not letters:
        return False

    uppercase_ratio = sum(character.isupper() for character in letters) / len(
        letters
    )
    return uppercase_ratio >= 0.9


def _merge_multiline_section_headings(lines: list[str]) -> list[str]:
    merged_lines = []
    index = 0
    heading_connectors = ("VE", "VEYA", "İLE", "YA DA")

    while index < len(lines):
        current_line = lines[index]

        if index + 1 >= len(lines) or not _is_section_heading(current_line):
            merged_lines.append(current_line)
            index += 1
            continue

        next_line = lines[index + 1]
        current_title = _clean_section_title(current_line)
        next_title = _clean_section_title(next_line)
        current_words = current_title.split()
        next_words = next_title.split()
        ends_with_connector = any(
            current_title.upper().endswith(f" {connector}")
            for connector in heading_connectors
        )
        has_short_wrapped_tail = (
            len(current_title) >= 40
            and len(next_words) <= 2
        )
        combined_title = f"{current_title} {next_title}".strip()

        if (
            len(current_words) >= 3
            and _is_heading_continuation(next_line)
            and (ends_with_connector or has_short_wrapped_tail)
            and len(combined_title) <= 100
        ):
            merged_lines.append(combined_title)
            index += 2
            continue

        merged_lines.append(current_line)
        index += 1

    return merged_lines


def _detect_long_document_sections(text: str) -> list[dict[str, str]]:
    prepared_text = _clean_long_document_front_matter(text)
    cleaned_text = clean_document_text(prepared_text)
    lines = _merge_multiline_section_headings(cleaned_text.splitlines())
    strict_heading_indexes = [
        index
        for index, line in enumerate(lines)
        if _is_section_heading(line)
    ]
    heading_counts = Counter(
        _heading_key(lines[index])
        for index in strict_heading_indexes
    )
    repeated_heading_keys = {
        key
        for key, count in heading_counts.items()
        if count >= 2
    }

    if len(repeated_heading_keys) >= 2:
        heading_indexes = []
        seen_heading_keys = set()

        for index in strict_heading_indexes:
            key = _heading_key(lines[index])

            if key in repeated_heading_keys and key not in seen_heading_keys:
                heading_indexes.append(index)
                seen_heading_keys.add(key)

    else:
        heading_indexes = strict_heading_indexes

    if len(heading_indexes) > 40:
        coarse_keys = {
            key
            for key, count in heading_counts.items()
            if count >= 3
        }
        heading_indexes = [
            index
            for index in heading_indexes
            if _heading_key(lines[index]) in coarse_keys
            and _is_section_heading(lines[index], coarse=True)
        ]

    if len(heading_indexes) > 40:
        return []

    spaced_heading_indexes = []

    for heading_index in heading_indexes:
        if spaced_heading_indexes:
            previous_heading_index = spaced_heading_indexes[-1]
            intervening_text = "\n".join(
                lines[previous_heading_index + 1:heading_index]
            ).strip()

            if len(intervening_text) < 3000:
                continue

        spaced_heading_indexes.append(heading_index)

    heading_indexes = spaced_heading_indexes

    if len(heading_indexes) < 2:
        return []

    sections = []

    for position, heading_index in enumerate(heading_indexes):
        content_start = heading_index + 1
        content_end = (
            heading_indexes[position + 1]
            if position + 1 < len(heading_indexes)
            else len(lines)
        )
        section_lines = [
            line
            for line in lines[content_start:content_end]
            if not _is_heading_boilerplate(line)
            and _heading_key(line) != _heading_key(lines[heading_index])
        ]
        section_text = "\n".join(section_lines).strip()

        minimum_section_chars = 500 if position == len(heading_indexes) - 1 else 3000

        if len(section_text) < minimum_section_chars:
            continue

        sections.append(
            {
                "title": _clean_section_title(lines[heading_index]),
                "text": section_text,
            }
        )

    return sections if len(sections) >= 2 else []


def _build_document_plan(text: str) -> dict:
    character_count = len(text)

    if character_count <= LONG_DOCUMENT_MIN_CHARS:
        logger.info("Document mode: normal")
        return {
            "mode": "normal",
            "chunks": split_document_into_chunks(text),
            "section_titles": {},
        }

    logger.info("Document mode: long")
    sections = _detect_long_document_sections(text)

    if not sections:
        logger.info(
            "Long document section detection fallback: characters=%s",
            character_count,
        )
        return {
            "mode": "long_fallback",
            "chunks": split_document_into_chunks(text),
            "section_titles": {},
        }

    chunks = []
    section_titles = {}

    for section_index, section in enumerate(sections, start=1):
        section_chunks = split_document_into_chunks(section["text"])

        if not section_chunks:
            continue

        first_chunk_index = len(chunks) + 1
        section_titles[first_chunk_index] = section["title"]
        chunks.extend(section_chunks)
        logger.info(
            "Section %s: title=%s characters=%s chunks=%s",
            section_index,
            section["title"],
            len(section["text"]),
            len(section_chunks),
        )

    logger.info(
        "Long document: characters=%s sections=%s",
        character_count,
        len(sections),
    )

    if not chunks:
        return {
            "mode": "long_fallback",
            "chunks": split_document_into_chunks(text),
            "section_titles": {},
        }

    return {
        "mode": "long",
        "chunks": chunks,
        "section_titles": section_titles,
    }


def _extractive_chunk_fallback(chunk: str) -> dict:
    candidates = re.split(
        r"(?<=[.!?])\s+|\n+",
        clean_document_text(chunk),
    )
    summary_points = []

    for candidate in candidates:
        sentence = " ".join(candidate.split()).strip()

        if len(sentence) < 30:
            continue

        if len(sentence) > 360:
            sentence = " ".join(sentence.split()[:45]).rstrip(".,;:") + "."

        summary_points.append(sentence)

        if len(summary_points) >= 3:
            break

    if not summary_points:
        fallback_text = " ".join(clean_document_text(chunk).split())

        if fallback_text:
            summary_points.append(
                " ".join(fallback_text.split()[:45]).rstrip(".,;:") + "."
            )

    return {
        "summary_points": summary_points,
        "concepts": [],
        "exam_points": [],
    }


def summarize_chunk(
    chunk: str,
    chunk_index: int,
    total_chunks: int,
) -> dict:
    chunk_started_at = time.perf_counter()
    print(
        f"Chunk {chunk_index}/{total_chunks} modele gönderiliyor: "
        f"{len(chunk)} karakter",
        flush=True,
    )

    prompt = f"""
PDF parçasını yalnızca kaynak bilgileriyle kısa JSON olarak özetle.
- summary_points: 2-3 madde; her biri en fazla 25-30 kelime.
- concepts: En fazla 3 önemli kavram; kısa name ve description.
- exam_points: 2-3 kısa, doğrudan bilgi cümlesi; soru yazma.
- Bilgi veya örnek ekleme. Chunk dışına çıkma. Kaynağın dilini koru.
- Kaynakça isimlerine odaklanma ve yarım cümle yazma.

PDF PARÇASI:
{chunk}
"""

    result = None
    last_error = None

    for attempt in range(2):
        attempt_prompt = prompt
        maximum_items = 3 if attempt == 0 else 2
        minimum_items = 2 if attempt == 0 else 1
        schema = {
            "type": "object",
            "properties": {
                "summary_points": {
                    "type": "array",
                    "minItems": minimum_items,
                    "maxItems": maximum_items,
                    "items": {"type": "string", "maxLength": 240},
                },
                "concepts": {
                    "type": "array",
                    "maxItems": maximum_items,
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "maxLength": 80},
                            "description": {
                                "type": "string",
                                "maxLength": 180,
                            },
                        },
                        "required": ["name", "description"],
                        "additionalProperties": False,
                    },
                },
                "exam_points": {
                    "type": "array",
                    "minItems": minimum_items,
                    "maxItems": maximum_items,
                    "items": {"type": "string", "maxLength": 240},
                },
            },
            "required": ["summary_points", "concepts", "exam_points"],
            "additionalProperties": False,
        }

        if attempt == 1:
            attempt_prompt += """

Önceki çıktı eksik veya geçersiz JSON oldu.
Her liste en fazla 2 öğe olsun. Yalnızca eksiksiz JSON döndür ve yapıyı kapat.
"""

        try:
            raw_result = _generate_with_lmstudio(
                attempt_prompt,
                json_schema=schema,
                num_predict=350,
            )
            parsed_result = json.loads(_clean_json_response(raw_result))

            if not isinstance(parsed_result, dict):
                raise ValueError("Chunk özeti JSON nesnesi değil.")

            if any(
                not isinstance(parsed_result.get(field), list)
                for field in ("summary_points", "concepts", "exam_points")
            ):
                raise ValueError("Chunk özeti gerekli listeleri içermiyor.")

            result = parsed_result
            break

        except (
            LMStudioServiceError,
            json.JSONDecodeError,
            ValueError,
            KeyError,
            IndexError,
            TypeError,
        ) as error:
            last_error = error

    if result is None:
        print(
            f"Chunk {chunk_index}/{total_chunks} structured output başarısız, "
            "fallback kullanılıyor",
            flush=True,
        )
        result = _extractive_chunk_fallback(chunk)

    chunk_duration = time.perf_counter() - chunk_started_at
    print(
        f"Chunk {chunk_index}/{total_chunks} tamamlandı: "
        f"{chunk_duration:.1f} sn",
        flush=True,
    )

    return result


def _normalize_text(value: str) -> str:
    return " ".join(
        re.sub(r"[^\w\s]", " ", value.casefold()).split()
    )


def _is_near_duplicate(candidate: str, existing: str) -> bool:
    normalized_candidate = _normalize_text(candidate)
    normalized_existing = _normalize_text(existing)

    if not normalized_candidate or not normalized_existing:
        return True

    if normalized_candidate == normalized_existing:
        return True

    candidate_tokens = set(normalized_candidate.split())
    existing_tokens = set(normalized_existing.split())
    union = candidate_tokens | existing_tokens
    token_overlap = (
        len(candidate_tokens & existing_tokens) / len(union)
        if union
        else 0
    )
    similarity = SequenceMatcher(
        None,
        normalized_candidate,
        normalized_existing,
    ).ratio()

    return token_overlap >= 0.82 or similarity >= 0.9


def _clean_text_point(value: object) -> str:
    if not isinstance(value, str):
        return ""

    cleaned = " ".join(value.split()).strip(" -*•")
    cleaned = re.sub(
        r"^(?:bu chunk|bu bölüm|kaynağa göre)\s*[:,;-]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    if cleaned and cleaned[-1] not in ".!?":
        cleaned += "."

    return cleaned


def _dedupe_text_points(
    points: list[object],
    *,
    limit: int | None = None,
) -> list[str]:
    unique_points = []

    for value in points:
        point = _clean_text_point(value)

        if not point:
            continue

        if any(_is_near_duplicate(point, existing) for existing in unique_points):
            continue

        unique_points.append(point)

        if limit is not None and len(unique_points) >= limit:
            break

    return unique_points


def _dedupe_concepts(concepts: list[object]) -> list[dict[str, str]]:
    unique_concepts = []

    for value in concepts:
        if not isinstance(value, dict):
            continue

        name = value.get("name")
        description = _clean_text_point(value.get("description"))

        if not isinstance(name, str) or not name.strip() or not description:
            continue

        cleaned_name = " ".join(name.split()).strip(" -*•:")

        if any(
            _is_near_duplicate(cleaned_name, concept["name"])
            for concept in unique_concepts
        ):
            continue

        unique_concepts.append(
            {
                "name": cleaned_name,
                "description": description,
            }
        )

        if len(unique_concepts) >= 8:
            break

    return unique_concepts


def _format_summary_markdown(
    summary_points: list[str],
    concepts: list[dict[str, str]],
    exam_points: list[str],
) -> str:
    if not summary_points:
        raise LMStudioServiceError("Chunk özetleri birleştirilemedi.")

    paragraph_break = (
        (len(summary_points) + 1) // 2
        if len(summary_points) > 4
        else len(summary_points)
    )
    summary_paragraphs = [" ".join(summary_points[:paragraph_break])]

    if paragraph_break < len(summary_points):
        summary_paragraphs.append(" ".join(summary_points[paragraph_break:]))

    concept_lines = [
        f"* **{concept['name']}:** {concept['description']}"
        for concept in concepts
    ]
    exam_lines = [f"* {point}" for point in exam_points]

    return "\n\n".join(
        [
            "## Ders Özeti\n\n" + "\n\n".join(summary_paragraphs),
            "## Temel Kavramlar\n\n" + "\n".join(concept_lines),
            "## Sınav İçin Kritik Noktalar\n\n" + "\n".join(exam_lines),
        ]
    ).strip()


def _merge_chunk_summaries(chunk_summaries: list[dict]) -> str:
    merge_started_at = time.perf_counter()
    print("Chunk birleştirme başladı", flush=True)

    summary_values = []
    concept_values = []
    exam_values = []

    for chunk_summary in chunk_summaries:
        summary_values.extend(chunk_summary.get("summary_points", []))
        concept_values.extend(chunk_summary.get("concepts", []))
        exam_values.extend(chunk_summary.get("exam_points", []))

    summary_points = _dedupe_text_points(summary_values)
    concepts = _dedupe_concepts(concept_values)
    exam_points = _dedupe_text_points(exam_values, limit=10)
    final_summary = _format_summary_markdown(
        summary_points,
        concepts,
        exam_points,
    )

    merge_duration = time.perf_counter() - merge_started_at
    print(f"Chunk birleştirme tamamlandı: {merge_duration:.1f} sn", flush=True)
    print(f"Final karakter sayısı: {len(final_summary)}", flush=True)

    return final_summary


def _generate_chunk_summaries(text: str) -> list[dict]:
    document_plan = _build_document_plan(text)
    chunks = document_plan["chunks"]

    if not chunks:
        raise ValueError("PDF metni boş.")

    print(
        f"PDF özetleme başladı: {len(chunks)} chunk oluşturuldu.",
        flush=True,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                summarize_chunk,
                chunk,
                index,
                len(chunks),
            )
            for index, chunk in enumerate(chunks, start=1)
        ]
        return [future.result() for future in futures]


def generate_document_summary(text: str) -> str:
    summary_started_at = time.perf_counter()
    chunk_summaries = _generate_chunk_summaries(text)
    final_summary = _merge_chunk_summaries(chunk_summaries)
    total_duration = time.perf_counter() - summary_started_at
    print(
        f"PDF özeti tamamlandı: toplam {total_duration:.1f} sn",
        flush=True,
    )

    return final_summary


def _prepare_streaming_chunk(chunk: str) -> str:
    lines = [line.strip() for line in chunk.splitlines() if line.strip()]

    for index, line in enumerate(lines):
        if _is_reference_section_heading(line):
            lesson_content = "\n".join(lines[:index]).strip()
            return lesson_content if len(lesson_content) >= 100 else ""

    if len(lines) < 3:
        return chunk

    reference_lines = 0

    for line in lines:
        has_url_or_identifier = bool(
            re.search(
                r"https?://|www\.|\bdoi\b|\barxiv\b|\bisbn\b|\bissn\b",
                line,
                re.IGNORECASE,
            )
        )
        has_author_year_pattern = bool(
            re.search(
                r"\b[A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü'-]+(?:\s+(?:ve|&|and)\s+"
                r"[A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü'-]+)?[,.( ]+"
                r"(?:19|20)\d{2}[a-z]?\b",
                line,
            )
        )
        looks_like_citation = bool(
            re.search(r"[,( ](?:19|20)\d{2}[a-z]?[)., ]", line)
            and len(line.split()) <= 30
        )
        mentions_publication = bool(
            re.search(
                r"\b(?:journal|proceedings|publisher|publication|yayınları|"
                r"makalesi|akademik makale)\b",
                line,
                re.IGNORECASE,
            )
            and re.search(r"(?:19|20)\d{2}", line)
        )

        if (
            has_url_or_identifier
            or has_author_year_pattern
            or looks_like_citation
            or mentions_publication
        ):
            reference_lines += 1

    if reference_lines / len(lines) >= 0.6:
        return ""

    return chunk


def _trim_incomplete_final_sentence(chunk_text: str) -> str:
    text_without_trailing_space = chunk_text.rstrip()

    if not text_without_trailing_space:
        return ""

    if text_without_trailing_space[-1] in ".!?":
        return text_without_trailing_space

    final_terminator = max(
        text_without_trailing_space.rfind("."),
        text_without_trailing_space.rfind("!"),
        text_without_trailing_space.rfind("?"),
    )

    if final_terminator >= 0:
        return text_without_trailing_space[:final_terminator + 1]

    return ""


def _remove_explicit_meta_intro(chunk_text: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+", chunk_text, maxsplit=1)

    if len(sentences) < 2:
        return chunk_text

    first_sentence = sentences[0].strip()
    is_meta_intro = bool(
        re.match(
            r"^(?:bu belge|bu bölüm|bu metin)\b",
            first_sentence,
            flags=re.IGNORECASE,
        )
        and re.search(
            r"\b(?:ele alır|ele almaktadır|inceler|incelemektedir|"
            r"açıklar|açıklamaktadır|sunar|sunmaktadır)\b",
            first_sentence,
            flags=re.IGNORECASE,
        )
    )

    return sentences[1].strip() if is_meta_intro else chunk_text


def _dedupe_summary_paragraphs(summary: str) -> str:
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n{2,}", summary)
        if paragraph.strip()
    ]
    unique_paragraphs = []

    for paragraph in paragraphs:
        normalized_paragraph = _normalize_text(paragraph)

        if paragraph.startswith("## "):
            if normalized_paragraph not in {
                _normalize_text(existing)
                for existing in unique_paragraphs
                if existing.startswith("## ")
            }:
                unique_paragraphs.append(paragraph)

            continue

        if any(
            SequenceMatcher(
                None,
                normalized_paragraph,
                _normalize_text(existing),
            ).ratio() >= 0.9
            for existing in unique_paragraphs
        ):
            continue

        unique_paragraphs.append(paragraph)

    return "\n\n".join(unique_paragraphs)


def _stream_chunk_to_queue(
    chunk: str,
    chunk_index: int,
    total_chunks: int,
    output_queue: Queue,
    num_predict: int,
) -> None:
    chunk_started_at = time.perf_counter()
    logger.info(
        "Chunk %s/%s streaming başladı",
        chunk_index,
        total_chunks,
    )

    streaming_chunk = _prepare_streaming_chunk(chunk)

    if not streaming_chunk:
        logger.info(
            "Chunk %s/%s kaynakça ağırlıklı olduğu için atlandı",
            chunk_index,
            total_chunks,
        )
        chunk_duration = time.perf_counter() - chunk_started_at
        logger.info(
            "Chunk %s/%s tamamlandı: %.1f sn",
            chunk_index,
            total_chunks,
            chunk_duration,
        )
        output_queue.put((chunk_index, "done", None))
        return

    prompt = f"""
Kaynak metindeki ana ders bilgisini doğal Türkçe ile 1-3 kısa paragrafta özetle.
- Önemli kavramları ve ilişkileri koru; gereksiz ayrıntı ve tekrarı azalt.
- Anlamı ve terminolojiyi değiştirme; kaynakta olmayan bilgi veya örnek ekleme.
- Cümleleri tamamla ve son cümleyi yarım bırakma.
- Markdown başlığı, soru listesi, kaynakça/yazar/makale listesi veya okuyucu talimatı yazma.
- "Bu belge", "Bu bölüm", "Bu metin", "Kaynakta", "Ders notunda", "Aşağıdaki" veya "Sınav için" diye başlama.
- Doğrudan konu anlatımına başla.

PDF PARÇASI:
{streaming_chunk}
"""

    first_token_received = False
    chunk_parts = []

    try:
        for content in _generate_with_lmstudio_stream(
            prompt,
            num_predict=num_predict,
        ):
            if not first_token_received:
                first_token_duration = time.perf_counter() - chunk_started_at
                logger.info(
                    "Chunk %s ilk token: %.1f sn",
                    chunk_index,
                    first_token_duration,
                )
                first_token_received = True

            chunk_parts.append(content)
            output_queue.put((chunk_index, "token", content))

        if not first_token_received:
            raise LMStudioServiceError(
                f"Chunk {chunk_index} boş streaming yanıtı oluşturdu."
            )

        chunk_text = "".join(chunk_parts)

        if not chunk_text.rstrip().endswith((".", "!", "?")):
            logger.info(
                "Chunk %s/%s yarım cümle tespit edildi",
                chunk_index,
                total_chunks,
            )
            logger.info(
                "Chunk %s/%s continuation başladı",
                chunk_index,
                total_chunks,
            )
            continuation_started_at = time.perf_counter()
            final_terminator = max(
                chunk_text.rfind("."),
                chunk_text.rfind("!"),
                chunk_text.rfind("?"),
            )
            incomplete_tail = chunk_text[final_terminator + 1:][-600:]
            continuation_prompt = f"""
Aşağıdaki özetin yalnızca yarım kalan son cümlesini tamamla.
Yeni konu veya paragraf ekleme. Önceki cümleleri tekrar etme.
En fazla 1 kısa cümle üret. Sadece devam metnini döndür.
Yalnızca kaynak chunk tarafından desteklenen bilgileri kullan.

Kaynak chunk:
{streaming_chunk}

Yarım özet:
{incomplete_tail}
"""

            try:
                continuation_parts = []

                for content in _generate_with_lmstudio_stream(
                    continuation_prompt,
                    num_predict=70,
                ):
                    continuation_parts.append(content)
                    chunk_parts.append(content)
                    output_queue.put((chunk_index, "token", content))

                continued_text = "".join(continuation_parts)

                if (
                    not continued_text
                    or not "".join(chunk_parts).rstrip().endswith(
                        (".", "!", "?")
                    )
                ):
                    raise LMStudioServiceError(
                        "Continuation tamamlanmış bir cümle oluşturmadı."
                    )

                continuation_duration = (
                    time.perf_counter() - continuation_started_at
                )
                logger.info(
                    "Chunk %s/%s continuation tamamlandı: %.1f sn",
                    chunk_index,
                    total_chunks,
                    continuation_duration,
                )

            except Exception as error:
                logger.warning(
                    "Chunk %s/%s continuation başarısız: %r",
                    chunk_index,
                    total_chunks,
                    error,
                )

        chunk_duration = time.perf_counter() - chunk_started_at
        logger.info(
            "Chunk %s/%s tamamlandı: %.1f sn",
            chunk_index,
            total_chunks,
            chunk_duration,
        )
        output_queue.put((chunk_index, "done", None))

    except Exception as error:
        output_queue.put((chunk_index, "error", error))


def generate_document_summary_stream(text: str):
    summary_started_at = time.perf_counter()
    document_plan = _build_document_plan(text)
    chunks = document_plan["chunks"]
    section_titles = document_plan["section_titles"]
    streaming_num_predict = (
        350 if document_plan["mode"] == "long" else 350
    )

    if not chunks:
        raise ValueError("PDF metni boş.")

    total_chunks = len(chunks)
    logger.info(
        "PDF özetleme başladı: %s chunk oluşturuldu.",
        total_chunks,
    )
    yield {
        "event": "status",
        "data": {
            "status": "started",
            "total_chunks": total_chunks,
        },
    }

    output_queue = Queue()
    buffered_events = {
        index: deque()
        for index in range(1, total_chunks + 1)
    }
    final_parts = []
    chunk_parts = {
        index: []
        for index in range(1, total_chunks + 1)
    }
    completed_db_chunks = []
    first_visible_token = False
    next_chunk_index = 1
    completed_chunks = 0
    separated_chunks = set()
    emitted_section_titles = set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                _stream_chunk_to_queue,
                chunk,
                index,
                total_chunks,
                output_queue,
                streaming_num_predict,
            )
            for index, chunk in enumerate(chunks, start=1)
        ]

        while next_chunk_index <= total_chunks:
            chunk_index, event_type, value = output_queue.get()

            if event_type == "error":
                raise value

            buffered_events[chunk_index].append((event_type, value))

            while (
                next_chunk_index <= total_chunks
                and buffered_events[next_chunk_index]
            ):
                buffered_type, buffered_value = (
                    buffered_events[next_chunk_index].popleft()
                )

                if buffered_type == "done":
                    completed_chunk_text = _trim_incomplete_final_sentence(
                        "".join(chunk_parts[next_chunk_index])
                    )
                    completed_chunk_text = _remove_explicit_meta_intro(
                        completed_chunk_text
                    )

                    if completed_chunk_text:
                        if next_chunk_index in section_titles:
                            completed_chunk_text = (
                                f"## {section_titles[next_chunk_index]}\n\n"
                                f"{completed_chunk_text}"
                            )

                        completed_db_chunks.append(completed_chunk_text)

                    completed_chunks += 1
                    yield {
                        "event": "progress",
                        "data": {
                            "completed_chunks": completed_chunks,
                            "total_chunks": total_chunks,
                        },
                    }
                    next_chunk_index += 1
                    continue

                if (
                    next_chunk_index > 1
                    and final_parts
                    and next_chunk_index not in separated_chunks
                ):
                    separator = "\n\n"
                    final_parts.append(separator)
                    yield {
                        "event": "token",
                        "data": {"text": separator},
                    }
                    separated_chunks.add(next_chunk_index)

                if (
                    next_chunk_index in section_titles
                    and next_chunk_index not in emitted_section_titles
                ):
                    section_heading = (
                        f"## {section_titles[next_chunk_index]}\n\n"
                    )
                    final_parts.append(section_heading)
                    yield {
                        "event": "token",
                        "data": {"text": section_heading},
                    }
                    emitted_section_titles.add(next_chunk_index)

                if not first_visible_token:
                    first_visible_duration = (
                        time.perf_counter() - summary_started_at
                    )
                    logger.info(
                        "İlk kullanıcı görünür token: %.1f sn",
                        first_visible_duration,
                    )
                    first_visible_token = True

                chunk_parts[next_chunk_index].append(buffered_value)
                final_parts.append(buffered_value)
                yield {
                    "event": "token",
                    "data": {"text": buffered_value},
                }

        for future in futures:
            future.result()

    final_summary = _dedupe_summary_paragraphs(
        "\n\n".join(completed_db_chunks)
    )

    if not final_summary.strip():
        raise LMStudioServiceError("LM Studio boş özet oluşturdu.")

    logger.info("Final karakter sayısı: %s", len(final_summary))

    yield {
        "event": "complete",
        "final_summary": final_summary,
    }

    total_duration = time.perf_counter() - summary_started_at
    logger.info(
        "PDF özeti tamamlandı: toplam %.1f sn",
        total_duration,
    )
