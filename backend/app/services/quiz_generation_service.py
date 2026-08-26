#!/usr/bin/env python3
"""LM Studio qwen3-8b için tek istekli, streaming KPSS tarih quiz testi."""

from __future__ import annotations

import argparse
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import math
from queue import Queue
import random
import re
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# ============================================================
# AYARLAR
# ============================================================

BASE_URL = "http://localhost:1234"
MODEL = "qwen3-8b"

TEMPERATURE = 0.1
QUESTION_COUNT = 15
REQUEST_TIMEOUT_SECONDS = 300
MAX_REFILL_ROUNDS = 5
MAX_LM_CONCURRENCY = 1
MAX_REPLACEMENT_BATCH_SIZE = 4
MIN_TOTAL_GENERATION_SECONDS = 120
GENERATION_SECONDS_PER_QUESTION = 16
ENABLE_FULL_PDF_FALLBACK_ACCEPTANCE = False

PDF_PATH = (
    Path(__file__).resolve().parent
    / "test_pdfs"
    / "kpss_tarih.pdf"
)

TOKEN_ROOT_LEN = 5
MIN_EVIDENCE_SUPPORT_OVERLAP = 2
MIN_CANDIDATE_QUALITY = 3.0
REGION_POOL_SIZE = 5
ADAPTIVE_PRIMARY_QUALITY = 2.5
ADAPTIVE_SECONDARY_QUALITY = 1.75
SENTENCE_COMPLETION_EMERGENCY_CAP = 900

logger = logging.getLogger("uvicorn.error.studyflow.quiz")


# ============================================================
# REGEX / SABİTLER
# ============================================================

URL_RE = re.compile(
    r"(?:https?://|www\.)\S+",
    re.I,
)

DOI_RE = re.compile(
    r"\b(?:doi\s*:\s*|10\.\d{4,9}/)\S+",
    re.I,
)

REFERENCE_HEADING_RE = re.compile(
    r"^\s*(?:kaynakça|kaynaklar|references|bibliography)\s*[:.]?\s*$",
    re.I,
)

META_SOURCE_RE = re.compile(
    r"\b(?:metne|parçaya|belgeye|dokümana|kaynağa|"
    r"evidence(?:'a|'e)?)\s+göre\b|"
    r"\b(?:metinde|parçada|belgede|dokümanda|kaynakta|"
    r"yukarıda|aşağıda)\b",
    re.I,
)

NEGATIVE_QUESTION_RE = re.compile(
    r"\b(?:değildir|yanlıştır|söylenemez|çıkarılamaz|"
    r"ulaşılamaz|beklenmez|olamaz|yapılmamalıdır)\b",
    re.I,
)

TOKEN_RE = re.compile(
    r"[0-9a-zçğıöşü]+",
    re.I,
)

PUBLICATION_STRONG_NOISE_RE = re.compile(
    r"\b(?:isbn|copyright|tüm hakları saklıdır|"
    r"çoğaltılması yasaktır|izinsiz çoğaltılamaz|"
    r"basım[\s-]*yayın satış hakları|yayıncı kuruluşun izni|"
    r"kapak tasarımı|fotokopi yoluyla)\b",
    re.I,
)

PUBLICATION_METADATA_RE = re.compile(
    r"\b(?:yayınevi|yayınları|baskı|basım|matbaa|matbaacılık|"
    r"dağıtım|satış|adres|telefon|faks|e[\s-]*posta|web|"
    r"genel yayın yönetmeni|editör|grafik tasarım)\b",
    re.I,
)

FACTUAL_CUE_RE = re.compile(
    r"\b(?:kuruldu|kurmuştur|yapıldı|yapmıştır|oldu|olmuştur|"
    r"seçildi|seçilmiştir|imzalandı|ilan edildi|kabul edildi|"
    r"başladı|sona erdi|fethedildi|kazandı|kaybetti|"
    r"döneminde|tarihinde|yılında|tarafından|sonucunda)\b",
    re.I,
)

YEAR_RE = re.compile(r"\b(?:1[0-9]{3}|20[0-9]{2})\b")
BROKEN_SYMBOL_RE = re.compile(r"[⇒→:=|•]{2,}|(?:⇒|→)")
OCR_FRAGMENT_END_RE = re.compile(
    r"\b(?:geçiril|komutasın|savaşı\s+ya|os|kar)\s*$|\b[bcçdfgğhjklmnprsştvyz]{1,2}\s*$",
    re.I,
)
INCOMPLETE_END_RE = re.compile(
    r"(?:\bile\s+sona|\b(?:tarafından|amacıyla|nedeniyle|sonucunda|"
    r"üzerine|için|fakat|ancak|çünkü|ve|veya|ile)|"
    r"\b\w+(?:lığını|liğini|luğunu|lüğünü)|"
    r"\badına\s+[A-ZÇĞİÖŞÜ][\wçğıöşü]*(?:\s+[A-ZÇĞİÖŞÜ][\wçğıöşü]*){0,2})$",
    re.I,
)
PURPOSE_RE = re.compile(r"\b(?:amacıyla|amacı ile|hedefiyle|üzere)\b", re.I)
QUESTION_RESULT_RE = re.compile(
    r"\b(?:neden olan|yol açan|sonucunda|sonuçlanan|çekilmesine|yıkılmasına)\b", re.I
)
BROAD_CATEGORY_RE = re.compile(
    r"\bhangisi\b.{0,90}\b(?:ile|hakkında)\s+ilgili\b|"
    r"\b(?:ile|hakkında)\s+ilgili\b.{0,60}\bhangisi\b|"
    r"\bbu\s+dönemle\s+ilgili\b",
    re.I,
)
BROAD_INFERENCE_RE = re.compile(
    r"\b(?:bilgiden|verilenlerden|bunlardan)\s+hareketle\s+çıkarılabilir\b|"
    r"\b(?:hangisi\s+)?(?:çıkarılabilir|ulaşılabilir|söylenebilir|ifade\s+edilebilir)\b",
    re.I,
)
SPECIFIC_ANSWER_SLOT_RE = re.compile(
    r"\bkim(?:dir)?\b|"
    r"\bhangi\s+(?:dönemde|yılda|tarihte|devlet(?:tir)?|ülke(?:dir)?|"
    r"kişi(?:dir)?|kurum(?:dur)?|antlaşma(?:dır)?|sözleşme(?:dir)?|"
    r"savaş(?:tır)?|şehir(?:dir)?|yer(?:dir)?|hükümdar(?:dır)?|sistem(?:dir)?)\b",
    re.I,
)
EXACT_YEAR_QUESTION_RE = re.compile(r"\bhangi\s+yıl(?:da)?\b", re.I)
EXACT_NUMBER_QUESTION_RE = re.compile(r"\b(?:hangi\s+yıl(?:da)?|kaç)\b", re.I)
FIRST_SINGULAR_QUESTION_RE = re.compile(
    r"\bilk\s+(?:ülke|devlet|kişi|kurum|antlaşma|savaş|şehir|yer)\b",
    re.I,
)

GENERIC_TOPIC_ROOTS = {
    "devle", "ülke", "savaş", "lider", "hüküm", "tarih", "yıl",
    "mille", "ordu", "siyas", "dönem", "olay", "kişi", "yönet",
}

FALLBACK_RELATION_ROOTS = {
    "imzal", "sağla", "veril", "tanın", "kurul", "seçil", "yapıl",
    "başla", "sona", "kazan", "kaybe", "fetih", "neden", "sonuç",
    "yetki", "denet", "yayıml", "kabul", "ilan", "katıl", "yenil", "uğram",
}

FALLBACK_QUESTION_NOISE_ROOTS = {
    "aşağı", "hangis", "hangi", "nedir", "kimdi", "kaçtı", "bilgi",
    "harek", "ifade", "söyle", "ulaşı", "çıkar", "doğru", "yanlı",
}

STOP_WORDS = {
    "acaba",
    "ancak",
    "bile",
    "bir",
    "bu",
    "da",
    "daha",
    "de",
    "diye",
    "en",
    "gibi",
    "hangi",
    "hangisi",
    "hem",
    "ile",
    "ise",
    "için",
    "mı",
    "mi",
    "mu",
    "mü",
    "nasıl",
    "ne",
    "neden",
    "olarak",
    "olan",
    "olduğu",
    "ve",
    "veya",
    "ya",
    "şu",
    "aşağıdakilerden",
}


# ============================================================
# DATA CLASS'LAR
# ============================================================

@dataclass(frozen=True)
class Evidence:
    evidence_id: int
    text: str
    position: int
    quality: float


@dataclass(frozen=True)
class QuizQuestion:
    evidence_id: int
    question_text: str
    options: tuple[str, str, str, str, str]
    correct_index: int


@dataclass
class Metrics:
    request_start: float
    first_token_at: float | None = None
    first_valid_question_at: float | None = None
    raw_candidates: int = 0
    completed_objects: int = 0
    invalid_json_objects: int = 0
    done_received: bool = False
    local_evidence_accepted: int = 0
    full_pdf_fallback_accepted: int = 0

    accepted_at: list[tuple[int, float]] = field(
        default_factory=list
    )

    rejected: list[tuple[Any, str]] = field(
        default_factory=list
    )


@dataclass
class QuizSession:
    accepted_question_texts: set[str] = field(default_factory=set)
    accepted_question_facts: list[tuple[str, str]] = field(default_factory=list)
    accepted_evidence_ids: set[int] = field(default_factory=set)
    rejected_evidence_ids: set[int] = field(default_factory=set)
    rejected_evidence_texts: set[str] = field(default_factory=set)
    used_evidence_texts: set[str] = field(default_factory=set)
    accepted_count: int = 0
    displayed_count: int = 0


@dataclass
class ProductionBatchMetrics:
    batch_id: int
    requested_count: int
    refill: bool
    started_at: float = field(default_factory=time.monotonic)
    accepted_count: int = 0
    rejected_count: int = 0
    rejection_reasons: Counter[str] = field(default_factory=Counter)

    @property
    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at


@dataclass
class EvidenceCandidateDebug:
    raw_spans: int = 0
    rejected_too_short: int = 0
    rejected_low_meaningful_tokens: int = 0
    rejected_incomplete: int = 0
    rejected_noise: int = 0
    rejected_multi_topic: int = 0
    accepted_candidates: int = 0
    examples: dict[str, list[str]] = field(default_factory=dict)
    sentence_completion_attempts: int = 0
    sentence_completion_success: int = 0
    sentence_completion_rejected: int = 0
    sentence_completed_examples: list[tuple[str, str]] = field(default_factory=list)
    sentence_completed_texts: set[str] = field(default_factory=set)

    def reject(self, category: str, text: str) -> None:
        attribute = f"rejected_{category}"
        setattr(self, attribute, getattr(self, attribute) + 1)
        samples = self.examples.setdefault(category, [])
        if len(samples) < 3:
            samples.append(" ".join(text.split())[:160])


@dataclass
class SelectedGateDebug:
    checked: int = 0
    rejected: int = 0
    reasons: dict[str, int] = field(default_factory=dict)
    examples: list[tuple[str, str]] = field(default_factory=list)

    def record(self, text: str, reason: str | None) -> None:
        self.checked += 1
        if reason is None:
            return
        self.rejected += 1
        label = reason.removeprefix("selected_evidence_")
        if label not in {"metadata", "embedded_heading", "syntactic_break", "context_dependent"}:
            label = "other"
        self.reasons[label] = self.reasons.get(label, 0) + 1
        if len(self.examples) < 5:
            self.examples.append((label, " ".join(text.split())[:320]))


def print_selected_gate_debug(debug: SelectedGateDebug) -> None:
    print(f"selected gate checked={debug.checked}")
    print(f"selected gate rejected={debug.rejected}")
    for label in (
        "metadata", "embedded_heading", "syntactic_break",
        "context_dependent", "other",
    ):
        print(f"selected gate rejected {label}={debug.reasons.get(label, 0)}")
    if debug.examples:
        print("\nSELECTED_GATE_REJECTED examples:")
        for reason, example in debug.examples:
            print(f"- [{reason}] {example}")


def print_evidence_debug(debug: EvidenceCandidateDebug) -> None:
    print("\nEVIDENCE DEBUG:")
    print(f"raw spans={debug.raw_spans}")
    print(f"rejected too short={debug.rejected_too_short}")
    print(f"rejected low meaningful tokens={debug.rejected_low_meaningful_tokens}")
    print(f"rejected incomplete={debug.rejected_incomplete}")
    print(f"rejected noise={debug.rejected_noise}")
    print(f"rejected multi-topic={debug.rejected_multi_topic}")
    print(f"accepted candidates={debug.accepted_candidates}")
    print(f"sentence completion attempts={debug.sentence_completion_attempts}")
    print(f"sentence completion success={debug.sentence_completion_success}")
    print(f"sentence completion rejected={debug.sentence_completion_rejected}")
    if debug.sentence_completed_examples:
        print("\nSENTENCE_COMPLETED examples:")
        for before, after in debug.sentence_completed_examples:
            print(f"- BEFORE: {' '.join(before.split())[:320]}")
            print(f"  AFTER: {' '.join(after.split())[:900]}")

    labels = {
        "too_short": "TOO_SHORT",
        "low_meaningful_tokens": "LOW_MEANINGFUL_TOKENS",
        "incomplete": "INCOMPLETE",
        "noise": "NOISE",
        "multi_topic": "MULTI_TOPIC",
    }
    for category, label in labels.items():
        samples = debug.examples.get(category, [])
        if samples:
            print(f"\n{label} examples:")
            for sample in samples:
                print(f"- {sample}")


@dataclass
class AdaptiveEvidenceDebug:
    raw_blocks: int = 0
    complete_blocks: int = 0
    candidates: int = 0
    context_dependent_blocks: int = 0
    context_completed_blocks: int = 0
    context_rejected_blocks: int = 0
    context_completed_examples: list[str] = field(default_factory=list)
    context_rejected_examples: list[str] = field(default_factory=list)
    enriched_blocks: int = 0
    average_evidence_chars: float = 0.0
    enriched_examples: list[str] = field(default_factory=list)
    rejection_counts: dict[str, int] = field(default_factory=dict)
    rejection_examples: dict[str, list[str]] = field(default_factory=dict)
    accepted_complete_blocks: list[tuple[str, float]] = field(default_factory=list)
    reconstruction_attempts: int = 0
    reconstruction_success: int = 0
    reconstruction_rejected: int = 0
    reconstructed_examples: list[str] = field(default_factory=list)
    reconstruction_rejected_examples: list[str] = field(default_factory=list)
    post_reconstruction_checked: int = 0
    post_reconstruction_rejected: int = 0
    post_reconstruction_rejected_examples: list[str] = field(default_factory=list)
    sentence_completion_attempts: int = 0
    sentence_completion_success: int = 0
    sentence_completion_rejected: int = 0
    sentence_completed_examples: list[tuple[str, str]] = field(default_factory=list)
    sentence_completed_texts: set[str] = field(default_factory=set)

    def reject(self, category: str, text: str) -> None:
        self.rejection_counts[category] = self.rejection_counts.get(category, 0) + 1
        examples = self.rejection_examples.setdefault(category, [])
        if len(examples) < 5:
            examples.append(" ".join(text.split())[:220])


class LMStudioError(RuntimeError):
    """LM Studio bağlantısı veya yanıtı geçersiz olduğunda."""
    pass


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(value: str) -> str:
    value = unicodedata.normalize(
        "NFKC",
        value,
    ).casefold()

    value = re.sub(
        r"[^0-9a-zçğıöşü]+",
        " ",
        value,
    )

    return " ".join(
        value.split()
    )


def meaningful_tokens(value: str) -> set[str]:
    return {
        token
        for token in TOKEN_RE.findall(
            normalize_text(value)
        )
        if len(token) >= 3
        and token not in STOP_WORDS
    }


def token_roots(value: str) -> set[str]:
    """
    Türkçedeki ek farklılıklarını biraz tolere etmek için
    kelimelerin ilk birkaç karakterini kullanır.

    Örnek:
    sunmuş
    sunmuştur

    ikisi de yaklaşık aynı kökle karşılaştırılabilir.
    """

    roots: set[str] = set()

    for token in meaningful_tokens(value):
        if len(token) > TOKEN_ROOT_LEN:
            roots.add(
                token[:TOKEN_ROOT_LEN]
            )
        else:
            roots.add(token)

    return roots


@dataclass(frozen=True)
class GroundingWindow:
    text: str
    normalized: str
    roots: frozenset[str]


@dataclass
class FullPDFGroundingIndex:
    windows: tuple[GroundingWindow, ...]
    postings: dict[str, set[int]]
    variant_postings: dict[str, set[int]] = field(default_factory=dict)

    @classmethod
    def build(cls, text: str) -> "FullPDFGroundingIndex":
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        windows: list[GroundingWindow] = []
        postings: dict[str, set[int]] = {}

        for index in range(len(lines)):
            start = max(0, index - 1)
            end = min(len(lines), index + 2)
            window_text = " ".join(lines[start:end])[:900]
            window = GroundingWindow(
                text=window_text,
                normalized=normalize_text(window_text),
                roots=frozenset(token_roots(window_text)),
            )
            window_id = len(windows)
            windows.append(window)
            for root in window.roots:
                postings.setdefault(root, set()).add(window_id)

        return cls(tuple(windows), postings)

    @staticmethod
    def _one_edit_or_less(first: str, second: str) -> bool:
        if first == second:
            return True
        if abs(len(first) - len(second)) > 1:
            return False
        if len(first) == len(second):
            return sum(a != b for a, b in zip(first, second)) <= 1
        shorter, longer = (first, second) if len(first) < len(second) else (second, first)
        short_at = long_at = edits = 0
        while short_at < len(shorter) and long_at < len(longer):
            if shorter[short_at] == longer[long_at]:
                short_at += 1
                long_at += 1
            else:
                edits += 1
                long_at += 1
                if edits > 1:
                    return False
        return True

    @classmethod
    def _roots_compatible(cls, first: str, second: str) -> bool:
        return first == second or (
            len(first) >= TOKEN_ROOT_LEN
            and len(second) >= TOKEN_ROOT_LEN
            and first[:3] == second[:3]
            and cls._one_edit_or_less(first, second)
        )

    def _posting_ids(self, root: str) -> set[int]:
        cached = self.variant_postings.get(root)
        if cached is not None:
            return cached
        ids: set[int] = set()
        for indexed_root, indexed_ids in self.postings.items():
            if self._roots_compatible(root, indexed_root):
                ids.update(indexed_ids)
        self.variant_postings[root] = ids
        return ids

    @classmethod
    def _matching_roots(cls, wanted: set[str], available: frozenset[str]) -> set[str]:
        return {
            root for root in wanted
            if any(cls._roots_compatible(root, candidate) for candidate in available)
        }

    def supports(self, question_text: str, correct_option: str) -> tuple[bool, str]:
        """Cevap ile soru ilişkisini aynı dar PDF penceresinde arar."""
        answer_roots = token_roots(correct_option) - GENERIC_TOPIC_ROOTS
        if not answer_roots:
            return False, "answer_not_found"

        posting_sets = [self._posting_ids(root) for root in answer_roots]
        if not posting_sets or any(not ids for ids in posting_sets):
            return False, "answer_not_found"
        candidate_ids = set.intersection(*posting_sets)

        question_roots = (
            token_roots(question_text)
            - answer_roots
            - GENERIC_TOPIC_ROOTS
            - FALLBACK_QUESTION_NOISE_ROOTS
        )
        if len(question_roots) < 2:
            return False, "insufficient_question_overlap"

        relation_roots = token_roots(question_text) & FALLBACK_RELATION_ROOTS
        question_numbers = set(re.findall(r"\b\d+\b", question_text))
        saw_answer_support = False
        saw_question_support = False

        for window_id in candidate_ids:
            window = self.windows[window_id]
            matched_answers = self._matching_roots(answer_roots, window.roots)
            if len(matched_answers) != len(answer_roots):
                continue
            saw_answer_support = True

            concept_overlap = self._matching_roots(question_roots, window.roots)
            required_concepts = 3 if len(question_roots) >= 5 else 2
            if len(concept_overlap) < required_concepts:
                continue
            saw_question_support = True
            if relation_roots and not self._matching_roots(relation_roots, window.roots):
                continue
            if question_numbers and not question_numbers <= set(
                re.findall(r"\b\d+\b", window.text)
            ):
                continue
            return True, "supported"

        if not saw_answer_support:
            return False, "answer_not_found"
        if not saw_question_support:
            return False, "insufficient_question_overlap"
        return False, "relation_not_supported"


# ============================================================
# PDF TEMİZLEME
# ============================================================

def clean_pdf_text(raw_text: str) -> str:
    cleaned: list[str] = []

    raw_text = normalize_ocr_text(raw_text)

    for raw_line in raw_text.splitlines():

        line = " ".join(
            raw_line
            .replace("\u00ad", "")
            .split()
        )

        if REFERENCE_HEADING_RE.fullmatch(line):
            break

        line = URL_RE.sub(
            "",
            line,
        )

        line = DOI_RE.sub(
            "",
            line,
        )

        line = line.strip(
            " -–—|•\t"
        )

        if not line:
            continue

        if re.fullmatch(
            r"(?:sayfa\s*)?\d+",
            line,
            re.I,
        ):
            continue

        if len(line) < 18:
            continue

        if len(
            meaningful_tokens(line)
        ) < 3:
            continue

        cleaned.append(line)

    return "\n".join(cleaned)


def normalize_ocr_text(raw_text: str) -> str:
    """Yalnız yüksek güvenli extraction bölünmelerini düzeltir."""
    # Yalnız fiziksel satır sonunda kalan kelime-içi tire kaldırılır.
    # Aynı satırdaki Türk-Kazak gibi gerçek tireli ifadeler korunur.
    raw_text = re.sub(
        r"(?<=[0-9A-Za-zÇĞİÖŞÜçğıöşü])-\s*\r?\n\s*(?=[a-zçğıöşü])",
        "",
        raw_text,
    )

    replacements = (
        (r"\bTürkis\s+tan\b", "Türkistan"),
        (r"\bKal\s+kınma\b", "Kalkınma"),
        (r"\bİstan\s+bul\b", "İstanbul"),
        (r"\bİş\s+Birli\s+Birliği\b", "İş Birliği"),
        (r"\bBaron\s+dö\s*Tott\b", "Baron de Tott"),
    )
    for pattern, replacement in replacements:
        raw_text = re.sub(pattern, replacement, raw_text, flags=re.I)

    raw_text = re.sub(r"(?<=\w)-\s+(?=\w)", "-", raw_text)
    raw_text = re.sub(
        r"(?<=[a-zçğıöşü])(?=[A-ZÇĞİÖŞÜ][a-zçğıöşü])",
        " ",
        raw_text,
    )
    return raw_text


def extract_pdf_text(
    path: Path,
) -> tuple[str, int]:

    try:
        import fitz  # type: ignore

    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF gerekli: pip install PyMuPDF"
        ) from exc

    with fitz.open(path) as document:

        text = "\n".join(
            page.get_text("text")
            for page in document
        )

        return (
            clean_pdf_text(text),
            len(document),
        )


# ============================================================
# EVIDENCE SEÇİMİ
# ============================================================

def _sentence_completion_boundary(text: str) -> bool:
    stripped = text.strip()
    return bool(
        re.search(r"[.!?]\s*$", stripped)
        or (
            not has_incomplete_ending(stripped)
            and ADAPTIVE_PREDICATE_END_RE.search(stripped.rstrip(".!?"))
        )
    )


def _sentence_completion_stop_fragment(text: str) -> bool:
    stripped = text.strip()
    return bool(
        _adaptive_clear_heading(stripped)
        or _adaptive_quiz_metadata(stripped)
        or ADAPTIVE_CASE_HEADING_RE.search(stripped)
        or re.match(r"^(?:[-*•→]|\d+[.)])\s+", stripped)
        or stripped.count("|") >= 2
        or re.search(r"\b(?:tablo|şekil)\s*\d*\s*[:.]", stripped, re.I)
    )


def _complete_adjacent_sentences(
    fragments: list[tuple[int, str]],
    debug: Any,
) -> list[tuple[int, str]]:
    completed: list[tuple[int, str]] = []
    index = 0
    while index < len(fragments):
        position, original = fragments[index]
        if _sentence_completion_boundary(original) or index + 1 >= len(fragments):
            completed.append((position, original))
            index += 1
            continue

        if debug is not None:
            debug.sentence_completion_attempts += 1
        combined = original
        success = False
        consumed = 1
        remainder: tuple[int, str] | None = None
        for lookahead in range(index + 1, len(fragments)):
            next_position, next_fragment = fragments[lookahead]
            if next_position - position > 700 or _sentence_completion_stop_fragment(next_fragment):
                break
            starts_as_continuation = bool(
                re.match(r"^[a-zçğıöşü]", next_fragment.strip())
            )
            if (
                _sentence_completion_boundary(next_fragment)
                and not starts_as_continuation
            ):
                break
            shared_roots = (
                token_roots(combined) & token_roots(next_fragment)
            ) - GENERIC_TOPIC_ROOTS
            first_entities = topic_entities(combined)
            next_entities = topic_entities(next_fragment)
            if (
                not (starts_as_continuation or shared_roots)
                or (
                    len(first_entities) >= 2
                    and len(next_entities) >= 2
                    and not (first_entities & next_entities)
                )
            ):
                break

            boundary = re.search(r"[.!?]+", next_fragment)
            piece = next_fragment[:boundary.end()] if boundary else next_fragment
            proposed = f"{combined} {piece.strip()}"
            if len(proposed) > SENTENCE_COMPLETION_EMERGENCY_CAP:
                break
            if entity_switch_penalty(proposed) > 0:
                break
            combined = proposed
            consumed = lookahead - index + 1
            if _sentence_completion_boundary(combined):
                trailing = next_fragment[len(piece):].strip()
                if trailing:
                    remainder = (next_position + len(piece), trailing)
                success = True
                break

        if success:
            completed.append((position, combined))
            if remainder is not None:
                completed.append(remainder)
            if debug is not None:
                debug.sentence_completion_success += 1
                debug.sentence_completed_texts.add(normalize_text(combined))
                if len(debug.sentence_completed_examples) < 5:
                    debug.sentence_completed_examples.append((original, combined))
            index += consumed
        else:
            completed.append((position, original))
            if debug is not None:
                debug.sentence_completion_rejected += 1
            index += 1
    return completed

def _sentence_spans(
    text: str,
    debug: EvidenceCandidateDebug | None = None,
) -> list[tuple[int, str]]:

    spans: list[tuple[int, str]] = []

    pattern = (
        r"[^.!?\n]+"
        r"(?:[.!?]+|(?=\n|$))"
    )

    raw_spans: list[tuple[int, str]] = []
    for match in re.finditer(
        pattern,
        text,
    ):

        if debug is not None:
            debug.raw_spans += 1

        sentence = " ".join(
            match.group(0).split()
        ).strip()

        if sentence:
            raw_spans.append((match.start(), sentence))

    raw_spans = _complete_adjacent_sentences(raw_spans, debug)

    for position, sentence in raw_spans:

        if len(sentence) < 45:
            if debug is not None:
                debug.reject("too_short", sentence)
            continue

        if len(
            meaningful_tokens(sentence)
        ) < 6:
            if debug is not None:
                debug.reject("low_meaningful_tokens", sentence)
            continue

        spans.append(
            (
                position,
                sentence,
            )
        )

    return spans


def is_publication_noise(text: str) -> bool:
    """Açık yayın/telif metadatasını tarih içeriğinden ayırır."""
    if PUBLICATION_STRONG_NOISE_RE.search(text):
        return True

    metadata_hits = PUBLICATION_METADATA_RE.findall(text)
    contact_like = bool(
        URL_RE.search(text)
        or re.search(r"\b\d{3,4}[\s.-]\d{2,4}[\s.-]\d{2,4}\b", text)
    )
    return len(metadata_hits) >= 3 or (len(metadata_hits) >= 2 and contact_like)


def topic_entities(text: str) -> set[str]:
    """Birleştirme için genel kelimeler dışındaki güçlü ad/kavram kökleri."""
    entities: set[str] = set()
    for match in re.finditer(
        r"\b[A-ZÇĞİÖŞÜ][a-zçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+)*\b",
        text,
    ):
        for root in token_roots(match.group(0)):
            if root not in GENERIC_TOPIC_ROOTS:
                entities.add(root)
    return entities


def entity_switch_penalty(text: str) -> float:
    """Ardışık parçalardaki tamamen farklı entity kümelerini temkinli cezalandırır."""
    clauses = [part.strip() for part in re.split(r"(?<=[.!?;])\s+", text) if part.strip()]
    entity_sets = [topic_entities(clause) for clause in clauses]
    penalty = 0.0
    for first, second in zip(entity_sets, entity_sets[1:]):
        if len(first) >= 2 and len(second) >= 2 and not (first & second):
            penalty += 3.0
    return penalty


def ocr_fragment_penalty(text: str) -> float:
    penalty = 0.0
    for fragment in re.split(r"[.!?;\n]+", text):
        fragment = fragment.strip()
        if fragment and OCR_FRAGMENT_END_RE.search(fragment):
            penalty += 1.5
    return min(penalty, 4.5)


def has_incomplete_ending(text: str) -> bool:
    """Yüklemi/nesnesi açıkça devam bekleyen conservative bitiş kontrolü."""
    ending = text.strip().rstrip(".!?…:;,-–—").strip()
    return bool(INCOMPLETE_END_RE.search(ending) or OCR_FRAGMENT_END_RE.search(ending))


def independent_fact_penalty(text: str) -> float:
    """Kısa alanda yığılan bağımsız olgu/topic işaretlerini cezalandırır."""
    factual_cues = len(FACTUAL_CUE_RE.findall(text))
    distinct_years = len(set(YEAR_RE.findall(text)))
    entity_count = len(topic_entities(text))
    penalty = max(0, factual_cues - 2) * 1.25
    penalty += max(0, distinct_years - 1) * 1.25
    if entity_count >= 6 and factual_cues >= 2:
        penalty += (entity_count - 5) * 0.75
    return min(penalty, 6.0)


def is_strong_atomic_fact(text: str) -> bool:
    """Tek başına soru kaynağı olabilecek kısa ve açık factual cümle."""
    if (
        not 80 <= len(text) <= 350
        or len(meaningful_tokens(text)) < 8
        or has_incomplete_ending(text)
    ):
        return False
    relation_signal = bool(
        FACTUAL_CUE_RE.search(text)
        or YEAR_RE.search(text)
        or re.search(r"\b(?:verildi|tanındı|kurdu|yayımladı|sundu|kazandı)\b", text, re.I)
    )
    return relation_signal and candidate_quality_score(text) >= MIN_CANDIDATE_QUALITY


def candidate_quality_score(text: str) -> float:
    """Model kullanmadan okunabilir, olgusal evidence adaylarını sıralar."""
    if is_publication_noise(text):
        return -100.0

    if has_incomplete_ending(text):
        return -100.0

    tokens = meaningful_tokens(text)
    score = min(len(tokens), 20) / 4

    if 180 <= len(text) <= 250:
        score += 3
    elif 80 <= len(text) <= 350:
        score += 1.5

    if YEAR_RE.search(text):
        score += 1.5
    if FACTUAL_CUE_RE.search(text):
        score += 1.5
    if len(re.findall(r"\b[A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,}\b", text)) >= 2:
        score += 1

    symbol_count = len(BROKEN_SYMBOL_RE.findall(text))
    score -= min(symbol_count, 4) * 1.5
    score -= max(0, len(re.findall(r"[,;:]", text)) - 5) * 0.5
    score -= entity_switch_penalty(text)
    score -= ocr_fragment_penalty(text)
    score -= independent_fact_penalty(text)
    if len(tokens) < 8:
        score -= 4
    return score


def _can_join_sentences(first: str, second: str) -> bool:
    """Yalnız güçlü ortak entity/kavram bulunan ardışık cümleleri birleştirir."""
    shared_entities = topic_entities(first) & topic_entities(second)
    return bool(shared_entities) and not is_publication_noise(f"{first} {second}")


def _can_complete_incomplete_span(first: str, second: str) -> bool:
    """Yarım spanı yalnız açık devam veya güçlü topic bağıyla tamamlar."""
    starts_as_continuation = bool(re.match(r"^[a-zçğıöşü]", second.strip()))
    shared_entities = topic_entities(first) & topic_entities(second)
    shared_topic_roots = (
        token_roots(first)
        & token_roots(second)
    ) - GENERIC_TOPIC_ROOTS
    return (
        (
            bool(shared_entities)
            or (
                starts_as_continuation
                and bool(shared_topic_roots)
            )
        )
        and not is_publication_noise(f"{first} {second}")
    )


def _evidence_candidates(
    text: str,
    debug: EvidenceCandidateDebug | None = None,
) -> list[tuple[int, str, float]]:

    sentences = _sentence_spans(text, debug)

    candidates: list[tuple[int, str, float]] = []

    for index, (
        position,
        sentence,
    ) in enumerate(sentences):

        evidence = sentence
        next_index = index + 1

        while (
            (
                len(evidence) < 180
                or has_incomplete_ending(evidence)
            )
            and next_index < len(sentences)
        ):

            if is_strong_atomic_fact(evidence):
                break

            # Tamamlanmış bir factual span, yalnız 180 karakter hedefi
            # uğruna başka bir konu/cümleyle birleştirilmez.
            if not has_incomplete_ending(evidence):
                break

            next_position, next_sentence = (
                sentences[next_index]
            )

            if (
                next_position - position
                > 700
            ):
                break

            if (
                len(evidence)
                + len(next_sentence)
                + 1
                > SENTENCE_COMPLETION_EMERGENCY_CAP
            ):
                break

            can_join = _can_complete_incomplete_span(
                evidence,
                next_sentence,
            )

            if not can_join:
                break

            evidence = (
                f"{evidence} "
                f"{next_sentence}"
            )

            next_index += 1

        # Güçlü tek cümleler 80 karakterden itibaren kabul edilir;
        # sırf uzunluk uğruna kopuk cümleler birleştirilmez.
        if len(evidence) < 80:
            if debug is not None:
                debug.reject("too_short", evidence)
            continue

        if len(evidence) > SENTENCE_COMPLETION_EMERGENCY_CAP:
            if debug is not None:
                debug.reject("noise", evidence)
            continue

        if has_incomplete_ending(evidence):
            if debug is not None:
                debug.reject("incomplete", evidence)
            continue

        if is_publication_noise(evidence):
            if debug is not None:
                debug.reject("noise", evidence)
            continue

        quality = candidate_quality_score(evidence)

        if quality >= MIN_CANDIDATE_QUALITY:
            candidates.append(
                (
                    position,
                    evidence,
                    quality,
                )
            )
            if debug is not None:
                debug.accepted_candidates += 1
        elif debug is not None:
            if len(meaningful_tokens(evidence)) < 8:
                debug.reject("low_meaningful_tokens", evidence)
            elif entity_switch_penalty(evidence) > 0 or independent_fact_penalty(evidence) > 0:
                debug.reject("multi_topic", evidence)
            else:
                debug.reject("noise", evidence)

    return candidates


ADAPTIVE_INFO_CUE_RE = re.compile(
    r"\b(?:tanım|neden|sonuç|ilke|hak|risk|kural|özgürlük|sorumluluk|"
    r"etik|güvenlik|gizlilik|iletişim|kültür|davranış|etki|amaç)\w*\b",
    re.I,
)

SLIDE_METADATA_RE = re.compile(
    r"^\s*(?:\d+[.]?|hafta|sayfa|içindekiler|"
    r"[\wçğıöşü\s]+\s+bölümü|ders(?:i)?|sunum)\s*$",
    re.I,
)

ADAPTIVE_DEPENDENT_END_RE = re.compile(
    r"(?:\b(?:ve|veya|ile|için|göre|amacıyla|nedeniyle|sonucunda|sayesinde|"
    r"arasında|olarak|ancak|ifade)|"
    r"\b(?:ve|veya)\s+\w+|"
    r"\bçok\s+kısa\s+sürede|"
    r"\baynı\s+zamanda|"
    r"\b\w+(?:ilen|ılan|ulan|ülen)\s+(?:etik|içerik|bilgi|kural|süreç|denge)|"
    r"\b\w+(?:da|de|ta|te|larda|lerde)\s+(?:etik|içerik|bilgi|denge)|"
    r"\b\w+(?:nın|nin|nun|nün))$",
    re.I,
)

ADAPTIVE_DEPENDENT_START_RE = re.compile(
    r"^(?:böylece|ancak|çünkü|bu\s+(?:durum|süreç|nedenle|sebeple)|"
    r"bunun\s+(?:sonucunda|yanında|aksine))\b",
    re.I,
)

ADAPTIVE_CONTEXT_START_RE = re.compile(
    r"^(?:böylece|daha\s+sonra|bu(?:\s+(?:durum|süreç|olay|iddia|kurallar|"
    r"denge(?:yi|nin|ye)?))?|"
    r"buradaki|bunlar|bunun\s+sonucunda)\b",
    re.I,
)

ADAPTIVE_ADVOCACY_END_RE = re.compile(
    r"\bsavun(?:ur|maktadır)\s*[.!?]?$",
    re.I,
)

ADAPTIVE_EXPLICIT_ADVOCACY_SUBJECT_RE = re.compile(
    r"(?:\b(?:yaklaşım|görüş|kuram|teori|model|savunucu|taraftar|grup|düşünür)\w*\b"
    r"|^[A-ZÇĞİÖŞÜ][\wçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][\wçğıöşü]+)+\b)"
    r".{0,80}\bsavun(?:ur|maktadır)\b",
    re.I,
)

ADAPTIVE_QUIZ_METADATA_RE = re.compile(
    r"\b(?:bu\s+)?(?:sunum|ders|pdf|doküman|materyal)(?:da|de|ın|in|un|ün)?\b"
    r".{0,160}\b(?:kaynak|referans|hazırlan)\w*\b|"
    r"\b(?:kaynak|referans)\w*\b.{0,160}\b"
    r"(?:dayanmaktadır|kullanılmıştır|hazırlanmıştır)\b",
    re.I,
)

ADAPTIVE_SUBJECTLESS_RELATION_RE = re.compile(
    r"^.{0,100}\b\w+(?:nın|nin|nun|nün|ların|lerin)\b.{0,120}"
    r"\b(?:savunur|savunmaktadır|düşünür|düşünmektedir|"
    r"belirtir|belirtmektedir)\s*[.!?]?$",
    re.I,
)

ADAPTIVE_SUBJECT_CONTEXT_RE = re.compile(
    r"(?i:\b(?:yaklaşım|görüş|kuram|teori|model|savunucu|taraftar|"
    r"grup|düşünür|platform|kullanıcı)\w*\b)|"
    r"^[A-ZÇĞİÖŞÜ][\wçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][\wçğıöşü]+)+\b",
)

ADAPTIVE_EXPLICIT_SUBJECT_START_RE = re.compile(
    r"^(?i:(?:kullanıcı|platform|yaklaşım|görüş|grup|kurum|araştırmacı)\w*)\b|"
    r"^[A-ZÇĞİÖŞÜ][\wçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][\wçğıöşü]+)+\b",
)

ADAPTIVE_SYNTACTIC_BREAK_RE = re.compile(
    r"\b(?:için|ile|ve|veya|ancak|fakat|göre|olarak|"
    r"\w+(?:da|de|ta|te|nda|nde))\s+"
    r"(?=(?:Bu\s+(?:durum|olay|iddia|süreç)|Böylece|Daha\s+sonra)\b)",
)

ADAPTIVE_CASE_HEADING_RE = re.compile(
    r"^\s*(?:vaka|örnek|olay)\s*:\s*(.+)",
    re.I,
)


def _adaptive_heading_like(text: str) -> bool:
    words = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", text)
    if not words:
        return True
    letters = "".join(words)
    all_upper = letters.isupper()
    title_case = len(words) <= 5 and all(word[0].isupper() for word in words)
    return len(text) < 35 or all_upper or (
        title_case
        and not FACTUAL_CUE_RE.search(text)
        and not YEAR_RE.search(text)
    )


def _adaptive_clear_heading(text: str) -> bool:
    words = re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", text)
    letters = "".join(words)
    return bool(
        text.rstrip().endswith(":")
        or (letters and letters.isupper())
        or ADAPTIVE_CASE_HEADING_RE.search(text)
    )


def _adaptive_noise(text: str) -> bool:
    normalized = " ".join(text.split()).strip(" -–—|•\t")
    return bool(
        not normalized
        or SLIDE_METADATA_RE.fullmatch(normalized)
        or is_publication_noise(normalized)
        or re.fullmatch(r"\d+[.]?", normalized)
    )


def _adaptive_quiz_metadata(text: str) -> bool:
    normalized = " ".join(text.split()).lstrip("\\*\-•→–—> \t")
    return bool(ADAPTIVE_QUIZ_METADATA_RE.search(normalized))


def _adaptive_dedupe_sentences(text: str) -> str:
    parts = re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", text)
    kept: list[str] = []
    kept_normalized: list[str] = []
    for part in parts:
        sentence = " ".join(part.split()).strip()
        if not sentence:
            continue
        normalized = normalize_text(sentence).strip()
        if normalized in kept_normalized or any(
            normalized in previous for previous in kept_normalized
        ):
            continue
        kept.append(sentence)
        kept_normalized.append(normalized)
    return " ".join(kept)


def _adaptive_case_enrichment_mismatch(base: str, context: str) -> bool:
    match = ADAPTIVE_CASE_HEADING_RE.search(base)
    if not match:
        return False
    identity = re.split(r"[:.!?]", match.group(1), maxsplit=1)[0]
    identity_roots = _adaptive_topic_roots(identity) - {"vaka", "örnek", "olay"}
    context_roots = _adaptive_topic_roots(context)
    return bool(identity_roots) and not (
        identity_roots & context_roots
        or _adaptive_anaphoric_continuation(context)
    )


def _adaptive_syntactic_break(text: str) -> bool:
    return bool(ADAPTIVE_SYNTACTIC_BREAK_RE.search(" ".join(text.split())))


def _adaptive_relation_clauses(text: str) -> list[str]:
    return [
        clause.strip()
        for clause in re.split(r"(?<=[.!?])\s+", text)
        if clause.strip() and _adaptive_complete_fact(clause)
    ]


def _adaptive_unresolved_subjectless(text: str) -> bool:
    clauses = _adaptive_relation_clauses(text)
    subjectless = [
        clause for clause in clauses
        if ADAPTIVE_SUBJECTLESS_RELATION_RE.search(clause)
        and not ADAPTIVE_EXPLICIT_SUBJECT_START_RE.search(clause)
    ]
    if not subjectless:
        return False
    contextual = [
        clause for clause in clauses
        if clause not in subjectless and ADAPTIVE_SUBJECT_CONTEXT_RE.search(clause)
    ]
    return not contextual


def _adaptive_enrichment_atomicity_break(text: str) -> bool:
    clauses = _adaptive_relation_clauses(text)
    if len(clauses) >= 3:
        return True
    if len(clauses) < 2:
        return False
    first_roots = _adaptive_topic_roots(clauses[0])
    second_roots = _adaptive_topic_roots(clauses[1])
    return not (first_roots & second_roots)


def _adaptive_topic_roots(text: str) -> set[str]:
    return token_roots(text) - GENERIC_TOPIC_ROOTS - {
        "hakkı", "temel", "genel", "öneml", "farkl", "kulla",
    }


def _adaptive_incomplete_end(text: str) -> bool:
    stripped = text.strip()
    if stripped.endswith(":"):
        return True
    ending = stripped.rstrip(".!?…:;,-–—").strip()
    return has_incomplete_ending(text) or bool(ADAPTIVE_DEPENDENT_END_RE.search(ending))


def _adaptive_incomplete_start(text: str) -> bool:
    stripped = text.strip()
    return bool(
        re.match(r"^[a-zçğıöşü]", stripped)
        or ADAPTIVE_DEPENDENT_START_RE.search(stripped)
    )


def _adaptive_context_dependent(text: str) -> bool:
    stripped = text.strip()
    if ADAPTIVE_CONTEXT_START_RE.search(stripped):
        return True
    return bool(
        ADAPTIVE_ADVOCACY_END_RE.search(stripped)
        and not ADAPTIVE_EXPLICIT_ADVOCACY_SUBJECT_RE.search(stripped)
    )


def _adaptive_anaphoric_continuation(text: str) -> bool:
    return bool(ADAPTIVE_CONTEXT_START_RE.search(text.strip()))


def _adaptive_can_link(first: str, second: str) -> bool:
    return bool(
        (
            _adaptive_topic_roots(first)
            & _adaptive_topic_roots(second)
            or _adaptive_anaphoric_continuation(second)
        )
    ) and not _adaptive_noise(f"{first} {second}")


def _adaptive_quality_score(
    text: str,
    joined: bool = False,
    title_body: bool = False,
) -> float:
    tokens = meaningful_tokens(text)
    score = min(len(tokens), 16) / 4
    if 70 <= len(text) <= 180:
        score += 2
    elif 35 <= len(text) <= 220:
        score += 1
    if ADAPTIVE_INFO_CUE_RE.search(text):
        score += 1.5
    if FACTUAL_CUE_RE.search(text) or YEAR_RE.search(text):
        score += 1
    if joined:
        score += 0.75
    if title_body:
        score += 1
    if not _adaptive_incomplete_start(text) and not _adaptive_incomplete_end(text):
        score += 1
    if _adaptive_incomplete_start(text):
        score -= 5
    if _adaptive_incomplete_end(text):
        score -= 5
    score -= ocr_fragment_penalty(text)
    score -= entity_switch_penalty(text)
    score -= independent_fact_penalty(text)
    return score


ADAPTIVE_PREDICATE_END_RE = re.compile(
    r"\b\w+(?:dır|dir|dur|dür|tır|tir|tur|tür|mıştır|miştir|muştur|müştür|"
    r"maktadır|mektedir|acaktır|ecektir|abilir|ebilir|olur|eder|yapar|sağlar|"
    r"oluşturur|yayılır|artırır|azaltır|gösterir|gerektirir|sunar|taşır|"
    r"kapsar|vardır|yoktur|verir|kalır)\s*$",
    re.I,
)


def _adaptive_complete_fact(text: str) -> bool:
    stripped = text.strip()
    if (
        len(stripped) < 45
        or len(meaningful_tokens(stripped)) < 4
        or _adaptive_heading_like(stripped)
        or _adaptive_incomplete_start(stripped)
        or _adaptive_incomplete_end(stripped)
    ):
        return False
    return bool(
        re.search(r"[.!?]\s*$", stripped)
        or ADAPTIVE_PREDICATE_END_RE.search(stripped.rstrip(".!?"))
        or FACTUAL_CUE_RE.search(stripped)
    )


def _adaptive_debug_rejection_reason(text: str) -> str:
    """Mevcut complete-block kontrollerinin ilk başarısızlığını açıklar."""
    stripped = text.strip()
    if len(stripped) < 45 or len(meaningful_tokens(stripped)) < 4:
        return "too_short"
    if _adaptive_heading_like(stripped):
        return "no_factual_predicate"
    if _adaptive_incomplete_start(stripped) or _adaptive_incomplete_end(stripped):
        return "incomplete"
    if not (
        re.search(r"[.!?]\s*$", stripped)
        or ADAPTIVE_PREDICATE_END_RE.search(stripped.rstrip(".!?"))
        or FACTUAL_CUE_RE.search(stripped)
    ):
        return "no_factual_predicate"
    if len(stripped) > 320:
        return "other"
    if _adaptive_syntactic_break(stripped):
        return "syntactic_break"
    if _adaptive_unresolved_subjectless(stripped):
        return "context_dependent"
    if _adaptive_noise(stripped):
        return "noise"
    return "other"


def _adaptive_post_reconstruction_reason(
    parts: list[tuple[int, str, bool, bool]],
    combined: str,
) -> str | None:
    texts = [item[1].strip() for item in parts]
    parallel_items = sum(
        bool(
            re.search(r"\b\w+(?:mak|mek)\s*:?[.!]?$", text, re.I)
            or (
                text.rstrip().endswith(":")
                and not _adaptive_complete_fact(text)
            )
        )
        for text in texts
    )
    embedded_parallel_items = len(
        re.findall(
            r"\b\w+(?:mak|mek)\s*:?[ ]+(?=[A-ZÇĞİÖŞÜ])",
            " ".join(combined.split()),
        )
    )
    if parallel_items >= 2 or embedded_parallel_items >= 2:
        return "list_atomicity"

    for left, right in zip(texts, texts[1:]):
        right_starts_new = bool(
            _adaptive_anaphoric_continuation(right)
            or re.match(r"^(?:Bu\s+(?:durum|olay|iddia|süreç)|Böylece|Daha\s+sonra)\b", right)
        )
        if (
            not re.search(r"[.!?]\s*$", left)
            and right_starts_new
        ):
            return "mid_syntactic_break"

    if _adaptive_syntactic_break(combined):
        return "mid_syntactic_break"

    for marker in re.finditer(
        r"\b(?:Bu\s+(?:durum|olay|iddia|süreç)|Böylece|Daha\s+sonra)\b",
        combined,
    ):
        left = re.split(r"[.!?]", combined[:marker.start()])[-1].strip()
        if len(left) >= 15 and not _adaptive_complete_fact(left):
            return "mid_syntactic_break"

    embedded_heading = re.search(
        r"\s+([A-ZÇĞİÖŞÜ][\wçğıöşü]+"
        r"(?:\s+(?:ve|ile|ya\s+da|[A-ZÇĞİÖŞÜ][\wçğıöşü]+)){0,5})\s*:\s*",
        combined,
    )
    if embedded_heading:
        before = combined[:embedded_heading.start()]
        after = combined[embedded_heading.start():]
        if not (_adaptive_topic_roots(before) & _adaptive_topic_roots(after)):
            return "embedded_heading"

    if entity_switch_penalty(combined) > 0:
        return "multi_topic"
    if _adaptive_enrichment_atomicity_break(combined):
        return "multi_topic"
    return None


def _adaptive_reconstruct_blocks(
    blocks: list[tuple[int, str, bool, bool]],
    debug: AdaptiveEvidenceDebug | None = None,
) -> list[tuple[int, str, bool, bool]]:
    reconstructed: list[tuple[int, str, bool, bool]] = []
    index = 0
    while index < len(blocks):
        first = blocks[index]
        first_text = first[1]
        if index + 1 >= len(blocks):
            reconstructed.append(first)
            break

        next_text = blocks[index + 1][1]
        first_unfinished = (
            not re.search(r"[.!?]\s*$", first_text)
            or _adaptive_incomplete_end(first_text)
            or not _adaptive_complete_fact(first_text)
        )
        continuation = bool(
            re.match(r"^[a-zçğıöşü]", next_text.strip())
            or _adaptive_incomplete_start(next_text)
        )
        if _adaptive_clear_heading(first_text) or not (first_unfinished or continuation):
            reconstructed.append(first)
            index += 1
            continue

        if debug is not None:
            debug.reconstruction_attempts += 1

        parts = [first]
        combined = first_text
        committed = False
        rejection_reason = "uygun continuation bulunamadı"
        for lookahead in range(index + 1, min(index + 3, len(blocks))):
            candidate = blocks[lookahead]
            candidate_text = candidate[1]
            if (
                candidate[0] - first[0] > 650
                or _adaptive_clear_heading(candidate_text)
                or ADAPTIVE_CASE_HEADING_RE.search(candidate_text)
                or _adaptive_quiz_metadata(candidate_text)
            ):
                rejection_reason = "yeni başlık/metadata sınırı"
                break
            if normalize_text(candidate_text) in {
                normalize_text(item[1]) for item in parts
            }:
                rejection_reason = "duplicate fragment"
                break

            proposed = f"{combined} {candidate_text}"
            if len(proposed) > 320:
                rejection_reason = "320 karakter sınırı"
                break
            first_entities = topic_entities(combined)
            next_entities = topic_entities(candidate_text)
            if (
                len(first_entities) >= 2
                and len(next_entities) >= 2
                and not (first_entities & next_entities)
            ):
                rejection_reason = "entity/topic switch"
                break
            if (
                entity_switch_penalty(proposed) > 0
                or independent_fact_penalty(proposed) > 3
                or _adaptive_enrichment_atomicity_break(proposed)
            ):
                rejection_reason = "multi-topic/atomicity"
                break

            parts.append(candidate)
            combined = proposed
            if _adaptive_complete_fact(combined):
                post_reason = _adaptive_post_reconstruction_reason(parts, combined)
                if debug is not None:
                    debug.post_reconstruction_checked += 1
                if post_reason is not None:
                    rejection_reason = f"post_reconstruction:{post_reason}"
                    if debug is not None:
                        debug.post_reconstruction_rejected += 1
                        if len(debug.post_reconstruction_rejected_examples) < 5:
                            debug.post_reconstruction_rejected_examples.append(
                                f"reason={post_reason} | {combined}"[:360]
                            )
                    break
                reconstructed.append((first[0], combined, first[2], True))
                committed = True
                if debug is not None:
                    debug.reconstruction_success += 1
                    if len(debug.reconstructed_examples) < 5:
                        source = " + ".join(item[1] for item in parts)
                        debug.reconstructed_examples.append(
                            f"{source} -> {combined}"[:700]
                        )
                index += len(parts)
                break
        else:
            rejection_reason = "üç fragment içinde tamamlanmadı"

        if committed:
            continue
        reconstructed.append(first)
        if debug is not None:
            debug.reconstruction_rejected += 1
            if len(debug.reconstruction_rejected_examples) < 3:
                preview = " + ".join(item[1] for item in parts)
                debug.reconstruction_rejected_examples.append(
                    f"{rejection_reason}: {preview}"[:320]
                )
        index += 1

    return reconstructed


def _adaptive_evidence_candidates(
    text: str,
    debug: AdaptiveEvidenceDebug | None = None,
) -> list[tuple[int, str, float]]:
    """Kısa/slayt içerikte yakın fiziksel satırlardan complete block üretir."""
    lines: list[tuple[int, str]] = []
    cursor = 0
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        position = text.find(raw_line, cursor)
        if position < 0:
            position = cursor
        cursor = position + len(raw_line)
        if line and not _adaptive_noise(line) and len(meaningful_tokens(line)) >= 2:
            lines.append((position, line))

    lines = _complete_adjacent_sentences(lines, debug)

    blocks: list[tuple[int, str, bool, bool]] = []
    current_position: int | None = None
    current = ""
    current_title = False
    current_has_title = False
    current_joined = False

    def flush() -> None:
        nonlocal current_position, current, current_title, current_has_title, current_joined
        if current_position is not None and current:
            blocks.append((current_position, current, current_has_title, current_joined))
        current_position = None
        current = ""
        current_title = False
        current_has_title = False
        current_joined = False

    for position, line in lines:
        line_title = _adaptive_heading_like(line) or line.rstrip().endswith(":")
        if not current:
            current_position = position
            current = line
            current_title = line_title
            current_has_title = line_title
            continue

        if _adaptive_complete_fact(current) or line_title:
            flush()
            current_position = position
            current = line
            current_title = line_title
            current_has_title = line_title
            continue

        separator = ": " if current_title else " "
        combined = f"{current}{separator}{line}"
        can_continue = (
            position - (current_position or position) <= 650
            and len(combined) <= 220
            and not _adaptive_heading_like(line)
            and _adaptive_can_link(current, line)
        )
        if can_continue:
            current = combined
            current_joined = True
            current_title = False
        else:
            flush()
            current_position = position
            current = line
            current_title = line_title
            current_has_title = line_title

    flush()

    if debug is not None:
        debug.raw_blocks = len(blocks)

    blocks = _adaptive_reconstruct_blocks(blocks, debug)

    complete_blocks: list[tuple[int, str, bool, bool]] = []
    for block_index, (position, block, title_body, joined) in enumerate(blocks):
        if _adaptive_quiz_metadata(block):
            if debug is not None:
                debug.reject("metadata", block)
            continue
        context_dependent = _adaptive_context_dependent(block)
        if context_dependent:
            if debug is not None:
                debug.context_dependent_blocks += 1
            completed: tuple[int, str, bool, bool] | None = None
            context_windows = (
                (block_index - 1, block_index + 1),
                (block_index - 2, block_index + 1),
                (block_index - 1, block_index + 2),
                (block_index, block_index + 2),
                (block_index, block_index + 3),
            )
            for start_index, end_index in context_windows:
                if start_index < 0 or end_index > len(blocks):
                    continue
                context_blocks = blocks[start_index:end_index]
                if any(item[2] for item in context_blocks[1:]):
                    continue
                context_position = context_blocks[0][0]
                context_text = " ".join(
                    item[1] for index, item in enumerate(context_blocks, start_index)
                    if index != block_index
                )
                combined = " ".join(item[1] for item in context_blocks)
                shared_roots = (
                    _adaptive_topic_roots(context_text)
                    & _adaptive_topic_roots(block)
                )
                anaphoric = _adaptive_anaphoric_continuation(block)
                previous_text = " ".join(
                    item[1] for item in blocks[start_index:block_index]
                )
                if (
                    context_blocks[-1][0] - context_position > 650
                    or len(combined) > 320
                    or not (
                        shared_roots
                        or context_blocks[0][2]
                        or (anaphoric and start_index < block_index)
                    )
                    or (
                        anaphoric
                        and not _adaptive_complete_fact(previous_text)
                    )
                    or entity_switch_penalty(combined) > 0
                    or _adaptive_quiz_metadata(combined)
                    or _adaptive_syntactic_break(combined)
                    or _adaptive_unresolved_subjectless(combined)
                    or not _adaptive_complete_fact(combined)
                ):
                    continue
                completed = (
                    context_position,
                    combined,
                    any(item[2] for item in context_blocks),
                    True,
                )
                break
            if completed is None:
                if debug is not None:
                    debug.context_rejected_blocks += 1
                    debug.reject("context_dependent", block)
                    if len(debug.context_rejected_examples) < 3:
                        debug.context_rejected_examples.append(block)
                continue
            position, block, title_body, joined = completed
            if debug is not None:
                debug.context_completed_blocks += 1
                if len(debug.context_completed_examples) < 3:
                    debug.context_completed_examples.append(block)

        if (
            not _adaptive_complete_fact(block)
            or (
                len(block) > 320
                and (
                    debug is None
                    or normalize_text(block) not in debug.sentence_completed_texts
                )
            )
            or _adaptive_syntactic_break(block)
            or _adaptive_unresolved_subjectless(block)
        ):
            if debug is not None:
                debug.reject(_adaptive_debug_rejection_reason(block), block)
            continue
        if debug is not None:
            debug.complete_blocks += 1
            debug.accepted_complete_blocks.append(
                (
                    block,
                    _adaptive_quality_score(
                        block,
                        joined=joined,
                        title_body=title_body,
                    ),
                )
            )
        complete_blocks.append((position, block, title_body, joined))

    enriched_blocks: list[tuple[int, str, bool, bool]] = []
    for block_index, current in enumerate(complete_blocks):
        position, block, title_body, joined = current
        choices = [current]
        windows = (
            (block_index, block_index + 2),
            (block_index - 1, block_index + 1),
            (block_index, block_index + 3),
            (block_index - 2, block_index + 1),
            (block_index - 1, block_index + 2),
        )
        for start, end in windows:
            if start < 0 or end > len(complete_blocks) or end - start <= 1:
                continue
            window = complete_blocks[start:end]
            if any(item[2] for item in window[1:]):
                continue
            context_text = " ".join(
                item[1] for index, item in enumerate(window, start)
                if index != block_index
            )
            window_text = _adaptive_dedupe_sentences(
                " ".join(item[1] for item in window)
            )
            shared_roots = (
                _adaptive_topic_roots(block)
                & _adaptive_topic_roots(context_text)
            )
            if (
                window[-1][0] - window[0][0] > 650
                or len(window_text) > 320
                or not shared_roots
                or _adaptive_case_enrichment_mismatch(block, context_text)
                or entity_switch_penalty(window_text) > 0
                or independent_fact_penalty(window_text) > 3
                or _adaptive_enrichment_atomicity_break(window_text)
                or _adaptive_syntactic_break(window_text)
                or _adaptive_unresolved_subjectless(window_text)
                or _adaptive_quiz_metadata(window_text)
                or not _adaptive_complete_fact(window_text)
            ):
                continue
            choices.append((window[0][0], window_text, window[0][2], True))

        def enrichment_rank(item: tuple[int, str, bool, bool]) -> tuple[int, int, int]:
            length = len(item[1])
            return (
                int(120 <= length <= 260),
                int(90 <= length <= 320),
                min(len(meaningful_tokens(item[1])), 32),
            )

        enriched = max(choices, key=enrichment_rank)
        enriched = (
            enriched[0],
            _adaptive_dedupe_sentences(enriched[1]),
            enriched[2],
            enriched[3],
        )
        enriched_blocks.append(enriched)
        if enriched[1] != block and debug is not None:
            debug.enriched_blocks += 1
            if len(debug.enriched_examples) < 3:
                debug.enriched_examples.append(enriched[1])

    preferred: list[tuple[int, str, bool, bool]] = []
    for item in sorted(enriched_blocks, key=lambda value: len(value[1]), reverse=True):
        normalized = normalize_text(item[1])
        if any(
            normalized in normalize_text(existing[1])
            and abs(item[0] - existing[0]) <= 650
            for existing in preferred
        ):
            continue
        preferred.append(item)

    candidates: list[tuple[int, str, float]] = []
    seen: set[str] = set()
    for position, block, title_body, joined in preferred:
        if (
            _adaptive_quiz_metadata(block)
            or _adaptive_syntactic_break(block)
            or _adaptive_unresolved_subjectless(block)
        ):
            continue
        normalized = normalize_text(block)
        if normalized in seen:
            continue
        score = _adaptive_quality_score(block, joined=joined, title_body=title_body)
        if score < ADAPTIVE_SECONDARY_QUALITY:
            continue
        seen.add(normalized)
        candidates.append((position, block, score))

    if debug is not None:
        debug.candidates = len(candidates)
        if candidates:
            debug.average_evidence_chars = sum(
                len(candidate[1]) for candidate in candidates
            ) / len(candidates)
    return candidates


def _selected_evidence_rejection_reason(text: str) -> str | None:
    """Generation'a girecek evidence için son, konservatif bağımsızlık kapısı."""
    compact = " ".join(text.split())
    if _adaptive_quiz_metadata(compact):
        return "selected_evidence_metadata"
    if _adaptive_syntactic_break(compact) or re.search(
        r"\b\w+(?:dığını|diğini|duğunu|düğünü)\b.{0,90}"
        r"\b\w+(?:madığını|mediğini|müdüğünü|madığı|mediği)\b",
        compact,
        re.I,
    ):
        return "selected_evidence_syntactic_break"
    if _adaptive_incomplete_start(compact) or re.search(
        r"(?:\b(?:bir|iki)\s+(?:alt|ana|temel)|;\s*yani\s+\w+)\s*$",
        compact,
        re.I,
    ):
        return "selected_evidence_syntactic_break"
    for boundary in re.finditer(
        r"\b(?:hâle|hale|neden|amacıyla|için|göre|yönelik|olarak|"
        r"birlikte|rağmen|sonucu)\s+(?=[A-ZÇĞİÖŞÜ])",
        compact,
    ):
        following = compact[boundary.end():].strip()
        preceding = compact[:boundary.end()].strip()
        if (
            len(meaningful_tokens(preceding)) >= 4
            and not _adaptive_complete_fact(preceding)
            and _adaptive_complete_fact(following)
        ):
            return "selected_evidence_syntactic_break"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines[1:-1], 1):
        if not _adaptive_heading_like(line):
            continue
        before = lines[index - 1]
        if not _adaptive_complete_fact(before):
            return "selected_evidence_embedded_heading"
    word_matches = list(re.finditer(r"[A-Za-zÇĞİÖŞÜçğıöşü]+", compact))
    for start in range(1, max(1, len(word_matches) - 3)):
        title_words = word_matches[start:start + 3]
        if len(title_words) < 3 or not all(
            match.group(0)[0].isupper() for match in title_words
        ):
            continue
        next_index = start + 3
        if next_index >= len(word_matches) or not word_matches[next_index].group(0)[0].isupper():
            continue
        title = compact[title_words[0].start():title_words[-1].end()]
        before = compact[:title_words[0].start()].strip()
        if _adaptive_heading_like(title) and before and not _adaptive_complete_fact(before):
            return "selected_evidence_embedded_heading"
    embedded_with_connector = re.search(
        r"\s+([A-ZÇĞİÖŞÜ][\wçğıöşü]+\s*,\s*"
        r"[A-ZÇĞİÖŞÜ][\wçğıöşü]+\s+(?:ve|ile)\s+"
        r"[A-ZÇĞİÖŞÜ][\wçğıöşü]+)\s+"
        r"(?=[A-ZÇĞİÖŞÜ][\wçğıöşü]+(?:\s|,))",
        compact,
    )
    if embedded_with_connector:
        before = compact[:embedded_with_connector.start()].strip()
        title = embedded_with_connector.group(1)
        if before and title and not _adaptive_complete_fact(before):
            return "selected_evidence_embedded_heading"
    if re.match(
        r"^(?:buradaki|burada\s+sözü\s+edilen|bunlar|böylece|bu\s+nedenle|"
        r"temel\s+amacı|"
        r"bu\s+(?:kurallar|düzenlemeler|süreç|sistem|yaklaşım|yöntem|"
        r"durum|olay|koşul|kavram|sepet|göstergeler|"
        r"denge(?:yi|nin|ye)?))\b",
        compact,
        re.I,
    ):
        return "selected_evidence_context_dependent"
    return None


def select_evidence(
    text: str,
    count: int = QUESTION_COUNT,
    candidates: list[tuple[int, str, float]] | None = None,
    excluded_texts: set[str] | None = None,
    first_evidence_id: int = 1,
    selected_gate_debug: SelectedGateDebug | None = None,
) -> list[Evidence]:

    if candidates is None:
        candidates = _evidence_candidates(text)
    excluded = excluded_texts or set()
    eligible_candidates: list[tuple[int, str, float]] = []
    for item in candidates:
        if normalize_text(item[1]) in excluded:
            continue
        gate_reason = _selected_evidence_rejection_reason(item[1])
        if selected_gate_debug is not None:
            selected_gate_debug.record(item[1], gate_reason)
        if gate_reason is None:
            eligible_candidates.append(item)
    candidates = eligible_candidates

    if len(candidates) < count:
        raise RuntimeError(
            f"Yalnızca {len(candidates)} "
            f"uygun evidence bulundu; "
            f"{count} gerekli."
        )

    selected: list[tuple[int, str, float]] = []

    used: set[str] = set()
    chooser = random.SystemRandom()
    document_length = max(len(text), 1)

    for slot in range(count):

        region_start = slot * document_length / count
        region_end = (slot + 1) * document_length / count
        region_center = (region_start + region_end) / 2

        available = [
            item for item in candidates
            if normalize_text(item[1]) not in used
        ]
        regional = [
            item for item in available
            if region_start <= item[0] < region_end
        ]

        # Nadir boş bölgelerde coverage'ı koruyarak en yakın kaliteli
        # adaylara geri dönülür; tüm PDF'den tamamen rastgele seçilmez.
        source = regional or sorted(
            available,
            key=lambda item: abs(item[0] - region_center),
        )[:REGION_POOL_SIZE]

        ranked = sorted(
            source,
            key=lambda item: (
                -item[2],
                abs(item[0] - region_center),
            ),
        )
        pool = ranked[:REGION_POOL_SIZE]
        choice = chooser.choice(pool) if pool else None

        if choice is None:
            raise RuntimeError(
                f"{count} benzersiz "
                "evidence seçilemedi."
            )

        selected.append(choice)

        used.add(
            normalize_text(
                choice[1]
            )
        )

    selected.sort(
        key=lambda item: item[0]
    )

    return [
        Evidence(
            evidence_id=i,
            text=value,
            position=position,
            quality=_quality,
        )
        for i, (position, value, _quality) in enumerate(
            selected,
            first_evidence_id,
        )
    ]


# ============================================================
# QWEN PROMPT
# ============================================================

def build_prompt(
    evidence: list[Evidence],
) -> str:

    rejected = [
        (item.evidence_id, _selected_evidence_rejection_reason(item.text))
        for item in evidence
        if _selected_evidence_rejection_reason(item.text) is not None
    ]
    if rejected:
        evidence_id, reason = rejected[0]
        raise RuntimeError(f"Evidence {evidence_id} final gate: {reason}")

    evidence_block = "\n".join(
        f"{item.evidence_id}|{item.text}"
        for item in evidence
    )
    example_id = evidence[0].evidence_id

    return f"""Create {len(evidence)} Turkish MCQs.
One question per numbered evidence, same order.
Use only evidence.
Correct answer must be explicitly supported by its own evidence.
Write the correct option as a concise phrase explicitly present in its numbered evidence; do not replace it with an unstated synonym or interpretation.
Each question must be grounded in exactly one numbered evidence item; never create a relationship by combining facts from different evidence items.
Do not use outside knowledge.
If evidence is unclear or incomplete, ask a simpler factual question using only explicitly stated facts.
Every question must be a classic five-option A/B/C/D/E MCQ with exactly one correct answer.
Choose one atomic relation only: definition, purpose, cause, result, effect, method, property, behavior, measurement, scope, institution, person, event, date/year, place, or another explicit factual relation.
Never generate premise/combination questions or numbered/lettered statement lists.
Forbidden question/option structures include Roman-numeral markers, numbered premise markers, "Yalnız" premise answers, joined premise answers, and "hangisi veya hangileri".
Specifically forbidden formats: "I.", "II.", "III.", "IV.", "V.", premise markers "1.", "2.", "3.", "Yalnız I", "Yalnız II", "I ve II", "I ve III", "II ve III", "I, II ve III", and "hangisi veya hangileri".
If evidence contains multiple true items under the same membership, scope, cause, element, factor, behavior, effect, property, or result relation, do not ask which one belongs and do not use the other supported items as distractors.
Instead ask about a different atomic relation in the same evidence that has exactly one supported answer.
If no uniquely-answerable atomic relation exists, still return the best normal candidate and allow validation/refill to reject it; never solve ambiguity with a premise/combination format.
Before writing options, verify that only one option can answer the exact current question relation.
t must be an actual question, never copy the evidence as t. Every t must end with ?
Each question must be understandable alone; for generic roles/relations, add a short distinguishing event, period, war, treaty, or date from the evidence.
Keep it concise—do not copy the evidence into t.
Exactly 5 options per question; exactly 1 correct.
The "o" array MUST contain exactly 5 strings.
Never return fewer or more than 5 options.
"a" must be an integer from 0 to 4.
Wrong options must be plausible, false for the current relation, in the same semantic type/category, and within the same lesson/topic domain; avoid obviously unrelated distractors.
All 5 options must be the same semantic type as the correct answer.
year -> 5 years, full date -> 5 full dates, person -> 5 persons, country/state -> 5 countries/states, place -> 5 places, treaty -> 5 treaties, institution -> 5 institutions, event/war -> 5 events/wars.
Date/year options must match the correct answer's granularity and format.
For a full-date question use five full dates; for a year question use five years—never mix a day number with years.
Only the correct option may answer the chosen relation according to the evidence.
Do not turn other true facts from the evidence into distractor propositions.
Never use another evidence-supported member of the asked list/category/relation as a distractor. If uniqueness is impossible, ask a different atomic question.
Never repeat an answer as short and long variants. No option may be a near-copy, expansion, truncation, or paraphrase of another option.
Never create both an individual answer and a combined answer containing that same individual, such as "saving" beside "saving, investment, and borrowing".
For definition questions, copy the grounded definition into exactly one option only. The other four options must be genuinely distinct plausible definitions, not small rewrites of the same evidence sentence.
Choose one concise correct-answer granularity and keep it consistent; do not place both a short correct phrase and its longer explanatory version among the options.
Distractors may be invented plausible same-type alternatives unsupported as correct by the evidence.
Prefer short noun/person/date/place/treaty values; avoid long proposition options.
Target one specific fact/relation, not a broad category; avoid "X ile ilgili hangisidir?".
Ask one specific fact, not an inference question; avoid "çıkarılabilir/söylenebilir/ulaşılabilir".
Only the correct option may be supported by evidence; all four distractors must contradict it or be unsupported.
The stem must make exactly one option uniquely correct.
No source/document/lecture references.
Short natural Turkish.
Avoid ambiguous questions.
Return strict JSON only. Each question object must be valid JSON.
No trailing commas, comments, or markdown. Use only keys i,t,o,a.
{{"q":[{{"i":{example_id},"t":"...","o":["...","...","...","...","..."],"a":0}}]}}

EVIDENCE:
{evidence_block}

/no_think"""


# ============================================================
# STREAMING JSON PARSER
# ============================================================

class QuestionObjectStream:
    """
    Streaming response içindeki q dizisinden
    tamamlanmış JSON question nesnelerini çıkarır.
    """

    def __init__(self) -> None:

        self.buffer = ""
        self.scan_at = 0
        self.array_found = False

        self.object_start: int | None = None

        self.depth = 0
        self.in_string = False
        self.escaped = False
        self.completed_objects = 0
        self.invalid_json_objects = 0


    def _reset_object_state(self) -> None:
        self.object_start = None
        self.depth = 0
        self.in_string = False
        self.escaped = False


    def _log_invalid_object(
        self,
        raw_object: str,
        detail: str,
    ) -> None:
        compact = " ".join(raw_object.replace("\x00", "").split())
        head = compact[:180]
        tail = compact[-180:] if len(compact) > 180 else compact
        print("\nSTREAM_OBJECT_REJECT: invalid_json_object", flush=True)
        print(f"  detail={detail}", flush=True)
        print(f"  raw_head={head}", flush=True)
        if tail != head:
            print(f"  raw_tail={tail}", flush=True)


    def feed(
        self,
        text: str,
    ) -> list[dict[str, Any]]:

        self.buffer += text

        completed: list[
            dict[str, Any]
        ] = []

        if not self.array_found:

            match = re.search(
                r'"q"\s*:\s*\[',
                self.buffer,
            )

            if match is None:
                return completed

            self.array_found = True
            self.scan_at = match.end()


        while (
            self.scan_at
            < len(self.buffer)
        ):

            char = (
                self.buffer[
                    self.scan_at
                ]
            )

            if self.object_start is None:

                if char == "{":

                    self.object_start = (
                        self.scan_at
                    )

                    self.depth = 1
                    self.in_string = False
                    self.escaped = False

                elif char == "]":

                    self.scan_at = (
                        len(self.buffer)
                    )

                    break

            elif self.in_string:

                if self.escaped:
                    self.escaped = False

                elif char == "\\":
                    self.escaped = True

                elif char == '"':
                    self.in_string = False

            elif char == '"':
                self.in_string = True

            elif char == "{":
                self.depth += 1

            elif char == "}":

                self.depth -= 1

                if self.depth == 0:

                    raw_object = (
                        self.buffer[
                            self.object_start:
                            self.scan_at + 1
                        ]
                    )

                    self.completed_objects += 1

                    try:
                        parsed = json.loads(
                            raw_object
                        )

                    except json.JSONDecodeError as exc:

                        self.invalid_json_objects += 1
                        self._log_invalid_object(
                            raw_object,
                            str(exc),
                        )
                        self._reset_object_state()
                        self.scan_at += 1
                        continue

                    if not isinstance(
                        parsed,
                        dict,
                    ):
                        self.invalid_json_objects += 1
                        self._log_invalid_object(
                            raw_object,
                            "completed_value_is_not_object",
                        )
                        self._reset_object_state()
                        self.scan_at += 1
                        continue

                    completed.append(
                        parsed
                    )

                    self._reset_object_state()

            self.scan_at += 1

        return completed


# ============================================================
# COMPACT JSON -> QUESTION
# ============================================================

def compact_to_question(
    candidate: Any,
) -> QuizQuestion:

    if not isinstance(
        candidate,
        dict,
    ):
        raise ValueError(
            "candidate_not_object"
        )

    # Explanation kaldırıldı.
    # Beklenen alanlar sadece:
    # i, t, o, a
    if set(candidate) != {
        "i",
        "t",
        "o",
        "a",
    }:
        raise ValueError(
            "invalid_compact_keys"
        )

    evidence_id = candidate["i"]
    question = candidate["t"]
    options = candidate["o"]
    answer = candidate["a"]

    if (
        isinstance(
            evidence_id,
            bool,
        )
        or not isinstance(
            evidence_id,
            int,
        )
    ):
        raise ValueError(
            "invalid_evidence_id"
        )

    if (
        not isinstance(
            question,
            str,
        )
        or not question.strip()
    ):
        raise ValueError(
            "empty_question"
        )

    if (
        not isinstance(
            options,
            list,
        )
        or len(options) != 5
    ):
        raise ValueError(
            "options_must_be_five_strings"
        )

    normalized_option_values: list[str] = []

    for option in options:
        if isinstance(option, bool) or option is None:
            raise ValueError(
                "options_must_be_five_strings"
            )
        if isinstance(option, str):
            normalized = option.strip()
        elif isinstance(option, int):
            normalized = str(option)
        elif isinstance(option, float) and math.isfinite(option):
            normalized = (
                str(int(option))
                if option.is_integer()
                else format(option, ".15g")
            )
        else:
            raise ValueError(
                "options_must_be_five_strings"
            )

        if not normalized:
            raise ValueError(
                "options_must_be_five_strings"
            )

        normalized_option_values.append(normalized)

    if (
        isinstance(answer, bool)
        or not isinstance(
            answer,
            int,
        )
        or not 0 <= answer <= 4
    ):
        raise ValueError(
            "invalid_correct_answer"
        )

    return QuizQuestion(
        evidence_id=evidence_id,
        question_text=question.strip(),
        options=tuple(
            normalized_option_values
        ),  # type: ignore[arg-type]
        correct_index=answer,
    )


# ============================================================
# VALIDATION
# ============================================================

def explicit_relation_mismatch(
    question_text: str,
    correct_option: str,
    evidence_text: str,
) -> bool:
    """Açık ok ilişkilerini ve amaç-sonuç yönü karışıklığını denetler."""
    question_roots = token_roots(question_text)
    answer_roots = token_roots(correct_option)

    if QUESTION_RESULT_RE.search(question_text):
        answer_clauses = [
            clause for clause in re.split(r"(?<=[.!?;])\s+", evidence_text)
            if answer_roots & token_roots(clause)
        ]
        if answer_clauses and all(PURPOSE_RE.search(clause) for clause in answer_clauses):
            return True

    if "⇒" not in evidence_text and "→" not in evidence_text:
        return False

    for match in re.finditer(r"⇒|→", evidence_text):
        left = re.split(r"[.!?;⇒→]", evidence_text[:match.start()])[-1]
        right = re.split(r"[.!?;⇒→]", evidence_text[match.end():], maxsplit=1)[0]
        left_roots = token_roots(left)
        right_roots = token_roots(right)

        if (
            len(question_roots & left_roots) >= 2
            and right_roots
            and not (answer_roots & right_roots)
        ):
            return True

    return False


def option_explicitly_supported_for_question(
    option: str,
    question_text: str,
    evidence_text: str,
) -> bool:
    supported, _reason = _option_relation_support(
        option,
        question_text,
        evidence_text,
    )
    return supported


def _option_is_grounded_for_question(
    option: str,
    question_text: str,
    evidence_text: str,
    allow_paraphrase: bool = False,
) -> bool:
    supported, _reason = _option_relation_support(
        option,
        question_text,
        evidence_text,
    )
    if supported:
        return True
    if (
        RESTRICTIVE_QUALIFIER_RE.search(option)
        and not _evidence_supports_restrictive_option(option, evidence_text)
    ):
        return False
    option_roots = token_roots(option)
    if not option_roots or len(option_roots) > 14:
        return False
    if (
        CAUSAL_QUESTION_RE.search(question_text)
        and _causal_validation_reason(question_text, option, evidence_text) is None
    ):
        required = len(option_roots) if len(option_roots) <= 5 else math.ceil(
            len(option_roots) * 0.8
        )
        causal_grounded = len(option_roots & token_roots(evidence_text)) >= required
        return causal_grounded or bool(
            allow_paraphrase
            and _correct_option_paraphrase_grounded(
                option,
                question_text,
                evidence_text,
            )
        )
    option_normalized = normalize_text(option)
    proposition_option = bool(
        len(option_roots) >= 4
        and (
            ADAPTIVE_PREDICATE_END_RE.search(option.rstrip(".!?"))
            or re.search(
                r"\b(?:ifade\s+eder|etkiler|içerir|kapsar|sağlar|"
                r"artırır|azaltır)\s*[.!?]?$",
                option,
                re.I,
            )
        )
    )
    family = _predicate_family(question_text)
    subject_roots = _question_subject_roots(question_text)
    if re.match(r"^\s*aşağıdaki\s+ifadelerden\s+hangisi\b", question_text, re.I):
        subject_roots = set()
    relevant_clauses = [
        clause for clause in _predicate_scoped_clauses(evidence_text)
        if (
            not family
            or _predicate_family(clause) == family
        )
        and (
            not subject_roots
            or _subject_matches_relation_clause(subject_roots, clause)
        )
    ]
    if family and not relevant_clauses and _subject_matches_relation_clause(
        subject_roots, evidence_text
    ):
        relevant_clauses = [
            clause for clause in _predicate_scoped_clauses(evidence_text)
            if _predicate_family(clause) == family
        ]
    if family and not relevant_clauses:
        return (
            _correct_option_paraphrase_grounded(option, question_text, evidence_text)
            if allow_paraphrase
            else False
        )
    if proposition_option and not family:
        exact_proposition = option_normalized in normalize_text(evidence_text)
        return exact_proposition or bool(
            allow_paraphrase
            and _correct_option_paraphrase_grounded(
                option,
                question_text,
                evidence_text,
            )
        )
    question_roots = token_roots(question_text)
    missing_roots_allowed = {"ifade", "eder", "birey", "kavra", "eden"}
    strictly_grounded = any(
        (
            option_roots <= token_roots(clause)
            or (
                len(option_roots - token_roots(clause)) <= 3
                and (option_roots - token_roots(clause)) <= missing_roots_allowed
            )
        )
        and option_roots - question_roots
        and _explicit_negation(option) == _explicit_negation(clause)
        for clause in (relevant_clauses or [evidence_text])
    )
    return strictly_grounded or bool(
        allow_paraphrase
        and _correct_option_paraphrase_grounded(
            option,
            question_text,
            evidence_text,
        )
    )


def _correct_option_paraphrase_grounded(
    option: str,
    question_text: str,
    evidence_text: str,
    enforce_causal: bool = True,
) -> bool:
    """Yalnız modelin doğru cevabı için konservatif lokal paraphrase fallback'i."""
    option_numbers = set(re.findall(r"\b\d+\b", option))
    evidence_numbers = set(re.findall(r"\b\d+\b", evidence_text))
    if option_numbers and not option_numbers <= evidence_numbers:
        return False
    if (
        enforce_causal
        and CAUSAL_QUESTION_RE.search(question_text)
        and _causal_validation_reason(question_text, option, evidence_text) is not None
    ):
        return False
    if any(
        _comparison_direction_mismatch(option, clause)
        for clause in _predicate_scoped_clauses(evidence_text)
    ):
        return False

    option_negated = _explicit_negation(option)
    evidence_negated = _explicit_negation(evidence_text)
    condition_frame = _causal_frame(evidence_text)
    if (
        condition_frame is not None
        and re.search(r"\bolmadan\b", normalize_text(evidence_text))
        and token_roots(option) <= condition_frame[1]
    ):
        evidence_negated = False
    not_only_coordination = bool(re.search(
        r"\byalnızca\b.{1,140}\b\w+(?:maz|mez)\b.{1,140}\bda\b",
        normalize_text(evidence_text),
    ))
    if option_negated != evidence_negated and not (
        not option_negated and not_only_coordination
    ):
        return False

    option_family = _predicate_family(option)
    evidence_family = _predicate_family(evidence_text)
    if option_family and evidence_family and option_family != evidence_family:
        return False

    equivalence = {
        "bire": "kişi",
        "kull": "kişi",
        "şirk": "kuruluş",
        "kuru": "kuruluş",
        "prob": "sorun",
        "soru": "sorun",
    }

    def canonical_roots(value: str) -> set[str]:
        roots = {root[:4] for root in token_roots(value.replace("İ", "i"))}
        return {equivalence.get(root, root) for root in roots}

    option_roots = canonical_roots(option)
    evidence_roots = canonical_roots(evidence_text)
    if not option_roots:
        return False
    shared = option_roots & evidence_roots
    missing = option_roots - evidence_roots
    if len(option_roots) <= 2 and option_roots <= evidence_roots:
        return True
    return bool(
        len(shared) >= 3
        and len(shared) / len(option_roots) >= 0.67
        and len(missing) <= 2
    )


def _grounded_option_indices(
    question: QuizQuestion,
    evidence_text: str,
) -> set[int]:
    return {
        index
        for index, option in enumerate(question.options)
        if _option_is_grounded_for_question(
            option,
            question.question_text,
            evidence_text,
        )
    }


def _option_relation_support(
    option: str,
    question_text: str,
    evidence_text: str,
) -> tuple[bool, str]:
    """Proposition seçeneğini tek bir question-conditioned factual clause ile eşler."""
    if (
        RESTRICTIVE_QUALIFIER_RE.search(option)
        and not _evidence_supports_restrictive_option(option, evidence_text)
    ):
        return False, "restrictive_qualifier_mismatch"

    def relation_roots(value: str) -> set[str]:
        return {
            token[:4] if len(token) > 4 else token
            for token in meaningful_tokens(value)
        }

    option_roots = relation_roots(option)
    question_family = _predicate_family(question_text)
    subject_roots = _question_subject_roots(question_text)
    scoped_subject_check = not re.search(r"\bnasıl\b", question_text, re.I)
    if question_family and subject_roots and scoped_subject_check:
        subject_relation_clauses = [
            clause for clause in _predicate_scoped_clauses(evidence_text)
            if _predicate_family(clause) == question_family
            and subject_roots <= token_roots(clause)
        ]
        if subject_relation_clauses and all(
            not _subject_matches_relation_clause(subject_roots, clause)
            for clause in subject_relation_clauses
        ):
            return False, "relation_direction_mismatch"
    action_phrase = bool(
        re.search(r"\b\w+(?:mak|mek|maya|meye)\b", normalize_text(option))
    )
    if len(option_roots) < 4 and not (action_phrase and len(option_roots) >= 2):
        return False, "short_entity"

    option_numbers = set(re.findall(r"\b\d+\b", option))
    evidence_numbers = set(re.findall(r"\b\d+\b", evidence_text))
    if option_numbers and not option_numbers <= evidence_numbers:
        return False, "number_mismatch"

    option_tokens = list(TOKEN_RE.findall(normalize_text(option)))
    predicate_roots = relation_roots(option_tokens[-1]) if option_tokens else set()
    if predicate_roots & {"etme", "olma", "yapm"} and len(option_tokens) >= 2:
        option_roots -= predicate_roots
        predicate_roots = relation_roots(option_tokens[-2])
    relation_noise_roots = {
        root[:4]
        for root in GENERIC_TOPIC_ROOTS | FALLBACK_QUESTION_NOISE_ROOTS
    }
    question_roots = relation_roots(question_text) - relation_noise_roots
    broad_relation_slot = bool(
        re.search(
            r"\bhangi\s+(?:etki|etkiye|etkilere|durum|durumlara|"
            r"alan|alanlarda|sonuç|sonuçlara|davranış|davranışlara)\b",
            question_text,
            re.I,
        )
    )
    clauses = _predicate_scoped_clauses(evidence_text)
    opposite_roots = {
        "artı": {"azal", "düşü", "enge"},
        "azal": {"artı", "yüks", "dest"},
        "dest": {"enge", "azal", "önle"},
        "enge": {"dest", "artı", "sağl"},
        "yüks": {"düşü", "azal"},
        "düşü": {"yüks", "artı"},
        "yara": {"önle", "enge"},
        "önle": {"yara", "artı"},
    }

    saw_opposite = False
    saw_negation_mismatch = False
    saw_direction_mismatch = False
    for clause in clauses:
        clause_roots = relation_roots(clause)
        clause_family = _predicate_family(clause)
        if question_family and clause_family and question_family != clause_family:
            continue
        if subject_roots and scoped_subject_check and not _subject_matches_relation_clause(
            subject_roots, clause
        ):
            if subject_roots <= token_roots(clause):
                saw_direction_mismatch = True
            continue
        if len(question_roots & clause_roots) < 2 and not broad_relation_slot:
            continue
        if _comparison_direction_mismatch(option, clause):
            saw_direction_mismatch = True
            continue
        for predicate_root in predicate_roots:
            if opposite_roots.get(predicate_root, set()) & clause_roots:
                saw_opposite = True
        covered = option_roots & clause_roots
        required = len(option_roots) if len(option_roots) <= 6 else math.ceil(
            len(option_roots) * 0.9
        )
        if (
            len(covered) >= required
            and predicate_roots
            and predicate_roots <= clause_roots
        ):
            if _explicit_negation(option) != _explicit_negation(clause):
                saw_negation_mismatch = True
                continue
            return True, "relation_match"

    if saw_negation_mismatch:
        return False, "negation_mismatch"
    if saw_direction_mismatch:
        return False, "relation_direction_mismatch"
    return False, "opposite_predicate" if saw_opposite else "relation_mismatch"


def short_options_share_supported_relation(
    question_text: str,
    correct_option: str,
    other_option: str,
    evidence_text: str,
) -> bool:
    """Aynı question-conditioned coordination/result zincirindeki kısa cevapları yakalar."""
    if (
        RESTRICTIVE_QUALIFIER_RE.search(other_option)
        and not _evidence_supports_restrictive_option(other_option, evidence_text)
    ):
        return False
    correct_roots = token_roots(correct_option)
    other_roots = token_roots(other_option)
    if not correct_roots or not other_roots:
        return False
    if len(correct_roots) > 5 or len(other_roots) > 5:
        return False

    relation_roots = (
        token_roots(question_text)
        - correct_roots
        - other_roots
        - GENERIC_TOPIC_ROOTS
        - FALLBACK_QUESTION_NOISE_ROOTS
    )
    coordination_re = re.compile(
        r"\b(?:ve|veya|ya\s+da|hem|ancak|fakat|karşılık|"
        r"yalnızca|sadece|değil|aynı\s+zamanda|başlayarak|kadar|"
        r"yol\s+aç|neden\s+ol|suretiyle)\b|"
        r"\b\w+(?:arak|erek|ırken|irken)\b|[,;/]",
        re.I,
    )
    question_family = _predicate_family(question_text)
    subject_roots = _question_subject_roots(question_text)
    for sentence in _predicate_scoped_clauses(evidence_text):
        sentence_roots = token_roots(sentence)
        sentence_family = _predicate_family(sentence)
        if question_family and sentence_family and question_family != sentence_family:
            continue
        if subject_roots and not _subject_matches_relation_clause(
            subject_roots, sentence
        ):
            continue
        if not correct_roots <= sentence_roots or not other_roots <= sentence_roots:
            continue
        if _explicit_negation(other_option) != _explicit_negation(sentence):
            continue
        if len(relation_roots & sentence_roots) < 2:
            continue
        if coordination_re.search(sentence):
            return True
    return False


def _has_forbidden_combination_format(question: QuizQuestion) -> bool:
    values = [question.question_text, *question.options]
    combined = "\n".join(values)
    normalized = normalize_text(combined)
    if re.search(
        r"\b(?:yalnız\s+(?:i|ii|iii)|i\s+ve\s+ii|i\s+ve\s+iii|"
        r"ii\s+ve\s+iii|i\s+ii\s+ve\s+iii|hangisi\s+veya\s+hangileri)\b",
        normalized,
    ):
        return True

    roman_markers = re.findall(
        r"(?:^|\s)(I|II|III|IV|V)[.)]\s+",
        combined,
    )
    numeric_markers = re.findall(
        r"(?:^|\s)([123])[.)]\s+",
        combined,
    )
    return len(roman_markers) >= 2 or len(numeric_markers) >= 2


ENUMERATION_MEMBERSHIP_QUESTION_RE = re.compile(
    r"\bhangisi\b.{0,90}\b(?:arasında\s+yer\s+alır|"
    r"unsur(?:u|udur|larından\s+biridir)|"
    r"faktör(?:ü|üdür|lerinden\s+biridir)|"
    r"üye(?:si|sidir)|örnek(?:tir|lerinden\s+biridir)|"
    r"kapsamında(?:dır)?|dahil(?:dir)?)\b|"
    r"\b(?:hangisine|hangilerinden\s+biri)\b.{0,90}\b(?:ait|dahil|üye)\b",
    re.I,
)


def _split_enumeration_items(value: str) -> list[str]:
    normalized_spacing = " ".join(value.split()).strip(" :;.-–—")
    parts = re.split(
        r"\s*[,;]\s*|\s+(?:ve|veya)\s+",
        normalized_spacing,
        flags=re.I,
    )
    items = [part.strip(" :;.-–—") for part in parts if part.strip(" :;.-–—")]
    return items if len(items) >= 2 and all(len(meaningful_tokens(item)) <= 10 for item in items) else []


def _explicit_enumerations(evidence_text: str) -> list[tuple[str, list[str]]]:
    enumerations: list[tuple[str, list[str]]] = []
    seen: set[tuple[str, ...]] = set()

    def add(relation: str, raw_items: str) -> None:
        items = _split_enumeration_items(raw_items)
        key = tuple(normalize_text(item) for item in items)
        if not items or key in seen:
            return
        seen.add(key)
        enumerations.append((" ".join(relation.split()).strip(" :;.-–—"), items))

    for match in re.finditer(r"\(([^()]{3,220})\)", evidence_text):
        before = re.split(r"[.!?;]", evidence_text[:match.start()])[-1][-140:]
        after = re.split(r"[.!?;]", evidence_text[match.end():], maxsplit=1)[0][:100]
        relation = f"{before} {after}"
        add(relation, match.group(1))

    for match in re.finditer(r"([^.!?;]{2,100}):\s*([^.!?;]{3,220})", evidence_text):
        add(match.group(1), match.group(2))

    for match in re.finditer(
        r"((?:[^,.!?;:()]{1,80}\s*[,;]\s*)+[^.!?:()]{1,120})",
        evidence_text,
    ):
        raw_list = match.group(1)
        relation = re.split(r"[.!?]", evidence_text[:match.start()])[-1][-120:]
        relation = f"{relation} {raw_list}"
        add(relation, raw_list)

    for clause in re.split(r"(?<=[.!?])\s+", evidence_text):
        if re.search(r"[,;]|\s+(?:ve|veya)\s+", clause, re.I):
            add(clause, clause)

    return enumerations


def _enumeration_option_match(option: str, item: str) -> bool:
    option_norm = normalize_text(option)
    item_norm = normalize_text(item)
    if option_norm == item_norm:
        return True
    option_roots = token_roots(option)
    item_roots = token_roots(item)
    return bool(option_roots and item_roots and (
        option_roots == item_roots
        or (
            option_roots <= item_roots
            and len(item_roots - option_roots) <= 4
        )
        or (
            item_roots <= option_roots
            and len(option_roots - item_roots) <= 4
        )
    ))


RESTRICTIVE_QUALIFIER_RE = re.compile(
    r"\b(?:yalnızca|yalnız|sadece|tek\s+başına)\b",
    re.I,
)


def _evidence_supports_restrictive_option(option: str, evidence_text: str) -> bool:
    core = RESTRICTIVE_QUALIFIER_RE.sub(" ", option)
    core_roots = token_roots(core)
    if not core_roots:
        return False
    for qualifier in RESTRICTIVE_QUALIFIER_RE.finditer(evidence_text):
        window = evidence_text[qualifier.start():qualifier.end() + 100]
        if core_roots <= token_roots(window):
            return True
    return False


PREDICATE_FAMILY_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("definition", re.compile(
        r"\b(?:ifade\s+eder(?:ken)?|tanımlar|tanımlanır|anlamına\s+gelir|"
        r"özetidir|yansımasıdır|dönüşüm(?:dür|üdür))\b", re.I
    )),
    ("cause", re.compile(
        r"\b(?:yol\s+aç\w*|neden\s+ol\w*|ortaya\s+çıkar\w*)\b",
        re.I,
    )),
    ("effect", re.compile(r"\betkiler\b", re.I)),
    ("direction", re.compile(r"\byönlendirir\b", re.I)),
    ("information", re.compile(r"\b(?:bilgi\s+verir|gösterir)\b", re.I)),
    ("containment", re.compile(r"\b(?:kapsar|içerir)\b", re.I)),
    ("determination", re.compile(r"\bbelirler\b", re.I)),
    ("measurement", re.compile(r"\bölçer\b", re.I)),
    ("provision", re.compile(r"\bsağlar\b", re.I)),
    ("source", re.compile(r"\bkaynaklanır\b", re.I)),
    ("dependency", re.compile(r"\bbağlı(?:dır|\s+olarak)\b", re.I)),
    ("preference", re.compile(r"\btercih\s+eder\b", re.I)),
    ("usage", re.compile(r"\bkullan(?:ır|ıl\w*|maktadır)\b", re.I)),
    ("importance", re.compile(r"\b(?:önem\s+taşır|önemlidir)\b", re.I)),
    ("purpose", re.compile(r"\bamaçlar\b", re.I)),
    ("increase", re.compile(r"\bartır\w*\b", re.I)),
)


def _predicate_family(text: str) -> str | None:
    normalized = normalize_text(text)
    if re.search(
        r"\b(?:tanımıyla\s+ilgili|tanımına\s+göre|tanımı\s+nedir|"
        r"ne\s+ifade\s+eder)\b",
        normalized,
    ):
        return "definition"
    for family, pattern in PREDICATE_FAMILY_PATTERNS:
        if pattern.search(normalized):
            return family
    return None


def _predicate_scoped_clauses(text: str) -> list[str]:
    """Aynı cümledeki farklı açık predicate complement'lerini ayırır."""
    scoped: list[str] = []
    relation_clauses = _factual_relation_clauses(text)
    for index in range(len(relation_clauses) - 1):
        clause = relation_clauses[index]
        following = relation_clauses[index + 1]
        if (
            _predicate_family(clause) is None
            and _predicate_family(following) == "definition"
            and f"{clause};" in text
        ):
            shared_definition = re.search(
                r"\b(ifade\s+eder|tanımlar|tanımlanır|anlamına\s+gelir)"
                r"\s*[.!?]?\s*$",
                following,
                re.I,
            )
            if shared_definition:
                relation_clauses[index] = (
                    f"{clause.rstrip(' .!?')} {shared_definition.group(1)}"
                )
    for clause in relation_clauses:
        raw_parts = re.split(
            r"\s+(?:ve|ancak|fakat|oysa|buna\s+karşılık)\s+",
            clause,
            flags=re.I,
        )
        parts: list[str] = []
        current = raw_parts[0]
        for index, next_part in enumerate(raw_parts[1:], start=1):
            remaining = " ve ".join(raw_parts[index:])
            if _predicate_family(current) and _predicate_family(remaining):
                parts.append(current)
                current = next_part
            else:
                current = f"{current} ve {next_part}"
        parts.append(current)
        if len(parts) < 2 or sum(_predicate_family(part) is not None for part in parts) < 2:
            scoped.append(clause)
            continue
        first = parts[0].strip()
        scoped.append(first)
        subject_prefix = (
            first.split(",", 1)[0].strip()
            if "," in first
            else " ".join(TOKEN_RE.findall(first)[:2])
        )
        for part in parts[1:]:
            part = part.strip()
            if part:
                scoped.append(f"{subject_prefix} {part}".strip())
    return scoped


def _subject_matches_relation_clause(subject_roots: set[str], clause: str) -> bool:
    if not subject_roots:
        return True
    normalized = normalize_text(clause)
    prefix = normalized.split(",", 1)[0]
    prefix_tokens = TOKEN_RE.findall(prefix)
    leading_roots = token_roots(" ".join(prefix_tokens[:max(4, len(subject_roots) + 2)]))
    return subject_roots <= leading_roots


def _factual_relation_clauses(text: str) -> list[str]:
    clauses: list[str] = []
    for clause in re.split(r"(?<=[.!?;])\s+|;\s*", text):
        clause = clause.strip()
        if not clause:
            continue
        comma_parts = [part.strip() for part in clause.split(",") if part.strip()]
        current = ""
        for part in comma_parts:
            if current and (
                re.search(r"\b(?:değil|yok|olmayan)\b", current, re.I)
                or re.match(r"^(?:ancak|fakat|oysa|buna\s+karşılık)\b", part, re.I)
            ):
                clauses.append(current)
                current = part
            else:
                current = f"{current}, {part}" if current else part
        if current:
            clauses.append(current)
    return clauses


def _explicit_negation(text: str) -> bool:
    normalized = normalize_text(text)
    return bool(
        re.search(
            r"\b(?:değil(?:dir)?|yok(?:tur)?|olmayan|"
            r"\w{2,}(?:maz|mez|madı|medi|madığı|mediği|"
            r"mıyor|miyor|muyor|müyor|mayacak|meyecek|mamak|memek|"
            r"maması|memesi|madan|meden|"
            r"mamış(?:tır|lardır)?|memiş(?:tir|lerdir)?))\b",
            normalized,
            re.I,
        )
    )


def _comparison_parts(text: str) -> tuple[set[str], set[str], set[str]] | None:
    """`X, Y'den daha P` karşılaştırmasının iki tarafını lokal olarak ayırır."""
    tokens = list(TOKEN_RE.findall(normalize_text(text)))
    for index in range(1, len(tokens)):
        if tokens[index] != "daha" or not re.search(
            r"(?:dan|den|tan|ten)$", tokens[index - 1]
        ):
            continue
        comparator_start = max(0, index - 3)
        subject_tokens = tokens[:comparator_start]
        comparator_tokens = tokens[comparator_start:index]
        predicate_tokens = tokens[index + 1:]
        if not subject_tokens or not comparator_tokens or not predicate_tokens:
            continue
        return (
            token_roots(" ".join(subject_tokens)),
            token_roots(" ".join(comparator_tokens)),
            token_roots(" ".join(predicate_tokens)),
        )
    return None


def _comparison_direction_mismatch(option: str, evidence_clause: str) -> bool:
    option_parts = _comparison_parts(option)
    evidence_parts = _comparison_parts(evidence_clause)
    if option_parts is None or evidence_parts is None:
        return False
    option_subject, option_comparator, option_predicate = option_parts
    evidence_subject, evidence_comparator, evidence_predicate = evidence_parts
    if not (option_predicate & evidence_predicate):
        return False
    evidence_subject_only = evidence_subject - evidence_comparator
    evidence_comparator_only = evidence_comparator - evidence_subject
    option_subject_only = option_subject - option_comparator
    option_comparator_only = option_comparator - option_subject
    return bool(
        evidence_subject_only & option_comparator_only
        and evidence_comparator_only & option_subject_only
    )


def _question_subject_roots(question_text: str) -> set[str]:
    relation_membership_match = re.search(
        r"\bhangisi\b\s+(.{1,100}?)\s+"
        r"(?:amaç|sonuç|özellik)(?:larından|lerinden)\s+biridir\b",
        question_text,
        re.I,
    )
    if relation_membership_match:
        return (
            token_roots(relation_membership_match.group(1))
            - FALLBACK_QUESTION_NOISE_ROOTS
            - GENERIC_TOPIC_ROOTS
        )
    prefix_match = re.search(
        r"^(.*?)(?:\bhangisi(?:ni|yle|ne)?\b|\bhangi\b|\bnasıl\b|"
        r"\bne(?:yi|ye|den)?\b|\bnedir\b)",
        question_text,
        re.I,
    )
    prefix = prefix_match.group(1) if prefix_match else question_text
    prefix = re.split(
        r"\b(?:tanımı(?:yla)?|hakkında|ile\s+ilgili|için)\b",
        prefix,
        maxsplit=1,
        flags=re.I,
    )[0]
    roots = (
        token_roots(prefix)
        - FALLBACK_QUESTION_NOISE_ROOTS
        - GENERIC_TOPIC_ROOTS
    )
    if roots:
        return roots

    membership_match = re.search(
        r"\bhangisi\b\s+(.{1,90}?)\s+"
        r"(?:arasında|unsur|faktör|üye|kapsam|dahil)",
        question_text,
        re.I,
    )
    if membership_match:
        return (
            token_roots(membership_match.group(1))
            - FALLBACK_QUESTION_NOISE_ROOTS
            - GENERIC_TOPIC_ROOTS
        )
    return set()


def _enumeration_supported_options(
    question: QuizQuestion,
    evidence_text: str,
) -> tuple[str, list[str], set[int], dict[int, str]] | None:
    question_roots = (
        token_roots(question.question_text)
        - FALLBACK_QUESTION_NOISE_ROOTS
        - GENERIC_TOPIC_ROOTS
    )
    subject_roots = _question_subject_roots(question.question_text)
    factual_clauses = _predicate_scoped_clauses(evidence_text)
    question_family = _predicate_family(question.question_text)
    for relation, items in _explicit_enumerations(evidence_text):
        relation_roots = token_roots(relation) - GENERIC_TOPIC_ROOTS
        required_relation_overlap = 1 if ENUMERATION_MEMBERSHIP_QUESTION_RE.search(
            question.question_text
        ) else 2
        if len(question_roots & relation_roots) < required_relation_overlap:
            continue
        supported: set[int] = set()
        reasons: dict[int, str] = {}
        for option_index, option in enumerate(question.options):
            matches = [
                item for item in items
                if _enumeration_option_match(option, item)
            ]
            if (
                RESTRICTIVE_QUALIFIER_RE.search(option)
                and not _evidence_supports_restrictive_option(option, evidence_text)
            ):
                reasons[option_index] = "unsupported(restrictive_qualifier_mismatch)"
            elif matches:
                option_core = RESTRICTIVE_QUALIFIER_RE.sub(" ", option)
                option_roots = token_roots(option_core)
                option_negated = _explicit_negation(option)
                required_option_roots = set(option_roots)
                if ADAPTIVE_PREDICATE_END_RE.search(option_core.rstrip(".!?")):
                    option_tokens = list(TOKEN_RE.findall(normalize_text(option_core)))
                    if option_tokens:
                        required_option_roots -= token_roots(option_tokens[-1])
                    if (
                        option_tokens
                        and normalize_text(option_tokens[-1]) in {"eder", "yapar", "olur"}
                        and len(option_tokens) >= 2
                    ):
                        required_option_roots -= token_roots(option_tokens[-2])
                same_relation_clauses = [
                    clause for clause in factual_clauses
                    if required_option_roots <= token_roots(clause)
                    and (
                        not question_family
                        or not _predicate_family(clause)
                        or _predicate_family(clause) == question_family
                    )
                    and (
                        _subject_matches_relation_clause(subject_roots, clause)
                        if subject_roots
                        else bool(question_roots & token_roots(clause))
                    )
                ]
                if not same_relation_clauses:
                    reasons[option_index] = "unsupported(subject_relation_mismatch)"
                elif all(
                    _explicit_negation(clause) != option_negated
                    for clause in same_relation_clauses
                ):
                    reasons[option_index] = "unsupported(negation_mismatch)"
                elif all(
                    _comparison_direction_mismatch(option, clause)
                    for clause in same_relation_clauses
                ):
                    reasons[option_index] = "unsupported(relation_direction_mismatch)"
                else:
                    supported.add(option_index)
                    reason = (
                        "enumeration_collection"
                        if len(matches) >= 2
                        else "enumeration_item"
                    )
                    reasons[option_index] = f"supported({reason})"
            else:
                reasons[option_index] = "unsupported(relation_mismatch)"
        if len(supported) >= 2:
            return relation, items, supported, reasons
    return None


def _has_question_subject_duplicate(
    question_text: str,
    options: tuple[str, str, str, str, str],
) -> bool:
    """Yalnız soru öznesini tekrarlayarak uzayan eşdeğer seçenekleri yakalar."""
    subject_roots = _question_subject_roots(question_text)
    if not subject_roots:
        return False
    option_roots = [token_roots(option) for option in options]
    for left_index in range(len(option_roots)):
        for right_index in range(left_index + 1, len(option_roots)):
            left = option_roots[left_index]
            right = option_roots[right_index]
            shared_content = (left & right) - subject_roots
            if len(shared_content) < 3:
                continue
            if (left - subject_roots) != (right - subject_roots):
                continue
            if (left ^ right) and (left ^ right) <= subject_roots:
                return True
    return False


def _semantic_option_roots(option: str) -> set[str]:
    roots = token_roots(option)
    if "sorum" in roots and roots & {"göste", "davra"}:
        roots -= {"göste", "davra", "fazla"}
        roots.add("sorumlu_davranış")
    if roots & {"öne", "çıka"} or (
        {"yükse", "etkil", "göste"} <= roots
    ):
        roots -= {"öne", "çıka", "yükse", "etkil", "göste"}
        roots.add("öne_çıkarma")
    return roots


def _has_semantic_duplicate_options(
    question_text: str,
    options: tuple[str, str, str, str, str],
) -> bool:
    subject_roots = _question_subject_roots(question_text)
    roots = [_semantic_option_roots(option) - subject_roots for option in options]
    for left_index, left in enumerate(roots):
        for right_offset, right in enumerate(roots[left_index + 1:], left_index + 1):
            if not left or not right:
                continue
            left_option = options[left_index]
            right_option = options[right_offset]
            if _explicit_negation(left_option) != _explicit_negation(right_option):
                continue
            left_less = bool(re.search(r"\bdaha\s+az\b", left_option, re.I))
            right_less = bool(re.search(r"\bdaha\s+az\b", right_option, re.I))
            if left_less != right_less:
                continue
            left_tokens = set(TOKEN_RE.findall(normalize_text(left_option)))
            right_tokens = set(TOKEN_RE.findall(normalize_text(right_option)))
            directional_suffix_opposite = any(
                re.fullmatch(rf"{re.escape(token[:-3])}(?:lı|li|lu|lü)", other)
                for token in left_tokens
                if re.search(r"s[ıiuü]z$", token)
                for other in right_tokens
            ) or any(
                re.fullmatch(rf"{re.escape(token[:-3])}(?:lı|li|lu|lü)", other)
                for token in right_tokens
                if re.search(r"s[ıiuü]z$", token)
                for other in left_tokens
            )
            if directional_suffix_opposite:
                continue
            shared = left & right
            left_only = left - right
            right_only = right - left
            generic_surface = {"daha", "fazla", "ortam", "şekil"}
            if len(shared) >= 3 and (
                left == right
                or (
                    len(left_only | right_only) <= 1
                    and (left_only | right_only) <= generic_surface
                )
            ):
                return True
    return False


CAUSAL_QUESTION_RE = re.compile(
    r"\b(?:neden\w*|sebep\w*|sonu[çc]\w*|sonuç\s+olarak|"
    r"yol\s+açar|neden\s+olur|meydana\s+getirir|etkisi|"
    r"faktör(?:ü|ün\s+sonucu)|ortaya\s+çık\w*)\b",
    re.I,
)
EXPLICIT_CAUSAL_RE = re.compile(
    r"\b(?:nedeniyle|sebebiyle|yüzünden|etkisiyle|sonucunda|"
    r"sonuç\s+olarak|neden\s+ol\w*|yol\s+aç\w*|"
    r"meydana\s+(?:getir|gel)\w*|"
    r"ortaya\s+çıkar\w*|etkiler|olmadan|"
    r"\w+(?:dığı|diği|duğu|düğü|madığı|mediği)\s+için)\b",
    re.I,
)
CAUSE_SEEKING_QUESTION_RE = re.compile(
    r"\b(?:neden\w*|sebep\w*)\s+(?:nedir|hangisidir|biri)|"
    r"\b(?:nedenidir|sebebidir)\b|"
    r"\bhangi\s+(?:neden\w*|sebep\w*|faktör)|\bhangi\s+faktörün\s+sonucu",
    re.I,
)


def _causal_frame(evidence_text: str) -> tuple[set[str], set[str]] | None:
    normalized = normalize_text(evidence_text)
    marker = re.search(
        r"\b(?:nedeniyle|sebebiyle|yüzünden|etkisiyle|sonucunda|"
        r"sonuç\s+olarak|olmadan)\b",
        normalized,
    )
    if marker:
        cause = token_roots(normalized[:marker.start()])
        effect = token_roots(normalized[marker.end():])
        return (cause, effect) if cause and effect else None

    marker = re.search(
        r"\b\w+(?:dığı|diği|duğu|düğü|madığı|mediği)\s+için\b",
        normalized,
    )
    if marker:
        cause = token_roots(normalized[:marker.end()])
        effect = token_roots(normalized[marker.end():])
        return (cause, effect) if cause and effect else None

    marker = re.search(
        r"\b(?:neden\s+ol\w*|yol\s+aç\w*|meydana\s+getir\w*|"
        r"meydana\s+gel\w*|ortaya\s+çıkar\w*|etkiler)\b",
        normalized,
    )
    if not marker:
        return None
    before = normalized[:marker.start()].strip()
    if "," in evidence_text[:marker.start()]:
        raw_before = evidence_text[:marker.start()]
        subject, result = raw_before.split(",", 1)
        return token_roots(subject), token_roots(result)
    roots = list(TOKEN_RE.findall(before))
    if len(roots) < 2:
        return None
    genitive_index = next(
        (
            index for index, token in enumerate(roots[1:], 1)
            if re.search(r"(?:nın|nin|nun|nün)$", token)
        ),
        None,
    )
    split_at = (
        max(1, genitive_index - 1)
        if genitive_index is not None
        else max(1, len(roots) - 2)
    )
    cause = token_roots(" ".join(roots[:split_at]))
    effect = token_roots(" ".join(roots[split_at:]))
    return (cause, effect) if cause and effect else None


def _causal_validation_reason(
    question_text: str,
    correct_option: str,
    evidence_text: str,
) -> str | None:
    if not CAUSAL_QUESTION_RE.search(question_text):
        return None
    if not EXPLICIT_CAUSAL_RE.search(evidence_text):
        option_family = _predicate_family(correct_option)
        evidence_family = _predicate_family(evidence_text)
        if (
            option_family in {"effect", "increase", "cause", "direction"}
            and option_family == evidence_family
            and _correct_option_paraphrase_grounded(
                correct_option,
                question_text,
                evidence_text,
                enforce_causal=False,
            )
        ):
            return None
        return "causal_relation_not_explicit"
    frame = _causal_frame(evidence_text)
    if frame is None:
        subject_roots = _question_subject_roots(question_text)
        if (
            subject_roots
            and len(subject_roots & token_roots(evidence_text)) >= 2
            and not _subject_matches_relation_clause(subject_roots, evidence_text)
        ):
            return "causal_direction_mismatch"
        return None
    cause_roots, effect_roots = frame

    def causal_argument_roots(roots: set[str]) -> set[str]:
        return {
            "sorun" if root.startswith(("probl", "sorun")) else root
            for root in roots
        }

    cause_roots = causal_argument_roots(cause_roots)
    effect_roots = causal_argument_roots(effect_roots)
    answer_roots = causal_argument_roots(token_roots(correct_option))
    cause_choice_match = re.search(
        r"\b(?:hangisi|ne)\b\s+(.{1,140}?)\s+"
        r"(?:neden\s+ol\w*|yol\s+aç\w*|meydana\s+getir\w*)",
        question_text,
        re.I,
    )
    preposed_cause_match = re.search(
        r"^(.{1,140}?)\s+ne\s+"
        r"(?:neden\s+ol\w*|yol\s+aç\w*|meydana\s+getir\w*)",
        question_text,
        re.I,
    )
    dependent_result_match = re.search(
        r"\bhangisi\s+(.{1,140}?)\s+bağlı\s+olarak\s+"
        r"ortaya\s+çık\w*",
        question_text,
        re.I,
    )
    preposed_result_match = re.search(
        r"^(.{1,140}?)\s+hangisine\s+"
        r"(?:neden\s+ol\w*|yol\s+aç\w*|meydana\s+getir\w*)",
        question_text,
        re.I,
    )
    asks_cause = bool(
        CAUSE_SEEKING_QUESTION_RE.search(question_text)
        or cause_choice_match
        or preposed_cause_match
    )
    result_question = bool(re.search(r"\bsonu[çc]\w*\b", question_text, re.I))
    if result_question:
        subject_roots = causal_argument_roots(
            token_roots(question_text)
            - answer_roots
            - token_roots(
                "sonucu sonucudur sonuçlarından bir biri nedir mudur "
                "aşağıdaki ifadelerden hangisi hangi durum olay"
            )
            - FALLBACK_QUESTION_NOISE_ROOTS
            - GENERIC_TOPIC_ROOTS
        )
    elif cause_choice_match:
        subject_roots = causal_argument_roots(token_roots(cause_choice_match.group(1)))
    elif preposed_cause_match:
        subject_roots = causal_argument_roots(token_roots(preposed_cause_match.group(1)))
    elif dependent_result_match:
        subject_roots = causal_argument_roots(token_roots(dependent_result_match.group(1)))
    elif preposed_result_match:
        subject_roots = causal_argument_roots(token_roots(preposed_result_match.group(1)))
    else:
        subject_prefix = re.split(
            r"\b(?:neden\w*|sebep\w*|sonucu|sonucunda|neyi|neye|hangi)\b",
            question_text,
            maxsplit=1,
            flags=re.I,
        )[0]
        subject_roots = causal_argument_roots(
            token_roots(subject_prefix) or _question_subject_roots(question_text)
        )
    expected_answer = cause_roots if asks_cause else effect_roots
    expected_subject = effect_roots if asks_cause else cause_roots
    reverse_answer = effect_roots if asks_cause else cause_roots
    reverse_subject = cause_roots if asks_cause else effect_roots
    if (
        answer_roots & reverse_answer
        and subject_roots & reverse_subject
        and not (answer_roots & expected_answer and subject_roots & expected_subject)
    ):
        return "causal_direction_mismatch"
    negative_because_cause = bool(
        asks_cause
        and re.search(
            r"(?:\b\w+(?:madığı|mediği|maması|memesi)\s+için\b|"
            r"\bolmadan\b)",
            normalize_text(evidence_text),
        )
    )
    subject_required = (
        min(2, len(subject_roots))
        if negative_because_cause
        else math.ceil(len(subject_roots) * 0.7)
    ) if subject_roots else 0
    if subject_required and len(subject_roots & expected_subject) < subject_required:
        return "causal_argument_mismatch"
    required_overlap = min(2, len(answer_roots))
    if required_overlap and len(answer_roots & expected_answer) < required_overlap:
        return "causal_argument_mismatch"
    expected_text = " ".join(
        token for token in TOKEN_RE.findall(normalize_text(evidence_text))
        if (token_roots(token) & expected_answer)
    )
    expected_negated = (
        True if negative_because_cause else _explicit_negation(expected_text)
    )
    if _explicit_negation(correct_option) != expected_negated:
        return "causal_argument_mismatch"
    return None


def _predicate_argument_supported(
    question_text: str,
    option: str,
    evidence_text: str,
) -> bool | None:
    family = _predicate_family(question_text)
    if family is None:
        return None
    def argument_roots(value: str) -> set[str]:
        return {
            "sorun" if root.startswith(("probl", "sorun")) else root
            for root in token_roots(value)
        }

    option_roots = argument_roots(option)
    if not option_roots:
        return False
    subject_roots = _question_subject_roots(question_text)
    relevant = [
        clause for clause in _predicate_scoped_clauses(evidence_text)
        if _predicate_family(clause) == family
        and (
            not subject_roots
            or _subject_matches_relation_clause(subject_roots, clause)
        )
    ]
    if not relevant and subject_roots and _subject_matches_relation_clause(
        subject_roots, evidence_text
    ):
        relevant = [
            clause for clause in _predicate_scoped_clauses(evidence_text)
            if _predicate_family(clause) == family
        ]
    if not relevant:
        return None
    required = len(option_roots) if len(option_roots) <= 4 else math.ceil(
        len(option_roots) * 0.7
    )
    return any(
        len(option_roots & argument_roots(clause)) >= required
        for clause in relevant
    )


def _context_dependent_question(question_text: str) -> bool:
    return bool(re.match(
        r"^\s*(?:buradaki|bunlar|böylece|bu\s+nedenle|buna\s+göre|"
        r"temel\s+amacı|"
        r"bu\s+(?:kurallar|düzenlemeler|süreçte|süreç|sistem|yaklaşım|"
        r"yöntem|durum|olay|koşul|kavram|sepet|göstergeler|"
        r"denge(?:yi|nin|ye)?))\b",
        question_text,
        re.I,
    ))


def _evidence_copy_question(question_text: str, evidence_text: str) -> bool:
    normalized_question = normalize_text(question_text)
    normalized_evidence = normalize_text(evidence_text)
    if len(normalized_question) < 80 or len(normalized_evidence) < 70:
        return False
    stripped_question = re.sub(
        r"\b(?:bu\s+açıklama|bu\s+tanım|yukarıdaki\s+açıklama)\b.{0,45}$",
        " ",
        normalized_question,
    ).strip()
    question_roots = token_roots(stripped_question)
    evidence_roots = token_roots(normalized_evidence)
    if not question_roots or not evidence_roots:
        return False
    overlap = len(question_roots & evidence_roots) / len(evidence_roots)
    return bool(
        normalized_evidence in normalized_question
        or (
            overlap >= 0.95
            and len(stripped_question) >= len(normalized_evidence) * 0.9
        )
    )


def _semantic_duplicate_question(
    question_text: str,
    correct_option: str,
    accepted_facts: list[tuple[str, str]],
) -> bool:
    question_roots = token_roots(question_text)
    answer_roots = token_roots(correct_option)
    family = _predicate_family(question_text)
    for previous_question, previous_answer in accepted_facts:
        previous_question_roots = token_roots(previous_question)
        previous_answer_roots = token_roots(previous_answer)
        answer_union = answer_roots | previous_answer_roots
        question_union = question_roots | previous_question_roots
        if not answer_union or not question_union:
            continue
        answer_similarity = len(answer_roots & previous_answer_roots) / len(answer_union)
        question_similarity = len(question_roots & previous_question_roots) / len(question_union)
        if (
            answer_similarity >= 0.8
            and question_similarity >= 0.55
            and len(question_roots & previous_question_roots) >= 4
            and family == _predicate_family(previous_question)
        ):
            return True
    return False


def has_precision_escalation(
    question_text: str,
    correct_option: str,
    evidence_text: str,
) -> bool:
    """Evidence'taki yaklaşık/göreli ifadeyi kesin cevaba çevirmeyi engeller."""
    normalized_evidence = normalize_text(evidence_text)
    answer_numbers = set(re.findall(r"\b\d+\b", correct_option))

    if EXACT_YEAR_QUESTION_RE.search(question_text) and answer_numbers:
        after_years = {
            match.group(1)
            for match in re.finditer(
                r"\b(1[0-9]{3}|20[0-9]{2})\b.{0,70}\bsonra\b",
                normalized_evidence,
            )
        }
        if answer_numbers & after_years:
            return True
        if re.search(r"\b(?:1[0-9]{3}|20[0-9]{2})\s+ların\s+başında\b", normalized_evidence):
            return True

    if (
        answer_numbers
        and EXACT_NUMBER_QUESTION_RE.search(question_text)
    ):
        approximation = r"(?:yaklaşık|civarında|dolaylarında|takriben)"
        for number in answer_numbers:
            if re.search(
                rf"(?:\b{approximation}\b.{{0,35}}\b{re.escape(number)}\b|"
                rf"\b{re.escape(number)}\b.{{0,35}}\b{approximation}\b)",
                normalized_evidence,
            ):
                return True

    if (
        FIRST_SINGULAR_QUESTION_RE.search(question_text)
        and re.search(r"\bilk\b.{0,45}\b\w+(?:lerden|lardan)\s+biri\b", normalized_evidence)
    ):
        return True

    return False


def validate_question(
    question: QuizQuestion,
    evidence_by_id: dict[int, Evidence],
    accepted_question_texts: set[str],
    accepted_ids: set[int],
    allow_answer_grounding_fallback: bool = False,
    accepted_question_facts: list[tuple[str, str]] | None = None,
) -> tuple[bool, str]:

    evidence = evidence_by_id.get(
        question.evidence_id
    )

    if evidence is None:
        return (
            False,
            "unknown_evidence_id",
        )

    if (
        question.evidence_id
        in accepted_ids
    ):
        return (
            False,
            "duplicate_evidence_id",
        )

    normalized_question = (
        normalize_text(
            question.question_text
        )
    )

    normalized_options = [
        normalize_text(option)
        for option
        in question.options
    ]

    if not question.question_text.strip().endswith("?"):
        return (
            False,
            "not_a_question",
        )

    # Yalnız birebir normalize edilmiş
    # soru duplicate sayılıyor.
    if (
        normalized_question
        in accepted_question_texts
    ):
        return (
            False,
            "exact_duplicate_question",
        )

    if any(
        not option
        for option
        in normalized_options
    ):
        return (
            False,
            "empty_option",
        )

    if (
        len(
            set(normalized_options)
        )
        != 5
    ):
        return (
            False,
            "duplicate_options",
        )

    if _has_question_subject_duplicate(question.question_text, question.options):
        return (
            False,
            "duplicate_options",
        )

    if _has_semantic_duplicate_options(question.question_text, question.options):
        return (
            False,
            "duplicate_options",
        )

    if _has_forbidden_combination_format(question):
        return (
            False,
            "combination_format_forbidden",
        )

    correct_option = (
        question.options[
            question.correct_index
        ]
    )

    if _context_dependent_question(question.question_text):
        return (
            False,
            "context_dependent_question",
        )

    if _evidence_copy_question(question.question_text, evidence.text):
        return (
            False,
            "evidence_copy_question",
        )

    if _semantic_duplicate_question(
        question.question_text,
        correct_option,
        accepted_question_facts or [],
    ):
        return (
            False,
            "semantic_duplicate_question",
        )

    grounded_indices = _grounded_option_indices(question, evidence.text)
    if _option_is_grounded_for_question(
        correct_option,
        question.question_text,
        evidence.text,
        allow_paraphrase=True,
    ):
        grounded_indices.add(question.correct_index)
    if (
        question.correct_index in grounded_indices
        and len(grounded_indices) > 1
    ):
        labels = "ABCDE"
        logger.debug(
            "supported options: %s",
            ", ".join(labels[index] for index in sorted(grounded_indices)),
        )
        return (
            False,
            "multiple_supported_options",
        )

    causal_reason = _causal_validation_reason(
        question.question_text,
        correct_option,
        evidence.text,
    )
    if causal_reason:
        return False, causal_reason

    if question.correct_index not in grounded_indices:
        if grounded_indices:
            labels = "ABCDE"
            logger.debug("model correct: %s", labels[question.correct_index])
            logger.debug(
                "grounded supported option: %s",
                ",".join(labels[index] for index in sorted(grounded_indices)),
            )
            return (
                False,
                "correct_answer_mismatch",
            )
        if not allow_answer_grounding_fallback:
            answer_roots_for_cross = token_roots(correct_option)
            if any(
                len(answer_roots_for_cross & token_roots(other.text))
                >= min(2, len(answer_roots_for_cross))
                for evidence_id, other in evidence_by_id.items()
                if evidence_id != question.evidence_id and answer_roots_for_cross
            ):
                return (
                    False,
                    "cross_evidence_relation",
                )
            return (
                False,
                "correct_answer_not_grounded",
            )

    predicate_argument_supported = _predicate_argument_supported(
        question.question_text,
        correct_option,
        evidence.text,
    )
    if predicate_argument_supported is False:
        return (
            False,
            "predicate_argument_mismatch",
        )

    combined = (
        f"{question.question_text} "
        f"{correct_option}"
    )

    # "Metne göre", "belgede" vs.
    if META_SOURCE_RE.search(
        combined
    ):
        return (
            False,
            "meta_source_reference",
        )

    # Çok belirsiz kökleri engelle.
    if (
        re.search(
            r"\b(?:bu|şu|hangisi)\s+"
            r"(?:durum|ifade|olay)\b",
            question.question_text,
            re.I,
        )
        and not SPECIFIC_ANSWER_SLOT_RE.search(
            question.question_text
        )
    ):
        return (
            False,
            "ambiguous_category",
        )

    if BROAD_CATEGORY_RE.search(
        question.question_text
    ):
        return (
            False,
            "broad_category_question",
        )

    if BROAD_INFERENCE_RE.search(
        question.question_text
    ):
        return (
            False,
            "broad_inference_question",
        )

    enumeration_support = _enumeration_supported_options(question, evidence.text)
    if enumeration_support is not None:
        (
            enumeration_relation,
            enumeration_items,
            supported_indices,
            enumeration_reasons,
        ) = enumeration_support
        labels = "ABCDE"
        logger.debug(
            "enumeration relation=%s items=%s supported=%s option support=%s",
            enumeration_relation or "(implicit list relation)",
            enumeration_items,
            ",".join(labels[index] for index in sorted(supported_indices)),
            ", ".join(
                f"{labels[index]}={enumeration_reasons[index]}"
                for index in range(5)
            ),
        )
        return False, "multiple_supported_options"

    if has_precision_escalation(
        question.question_text,
        correct_option,
        evidence.text,
    ):
        return (
            False,
            "precision_escalation",
        )

    # Evidence grounding:
    # soru + doğru cevap evidence ile
    # anlamlı kelime kökü paylaşmalı.
    evidence_roots = (
        token_roots(
            evidence.text
        )
    )

    question_roots = (
        token_roots(
            question.question_text
        )
    )

    answer_roots = (
        token_roots(
            correct_option
        )
    )

    support_roots = (
        question_roots
        | answer_roots
    )

    if (
        len(
            evidence_roots
            & support_roots
        )
        < MIN_EVIDENCE_SUPPORT_OVERLAP
    ):
        return (
            False,
            "evidence_grounding",
        )

    # Doğru cevap evidence ile en az
    # bir anlamlı kök paylaşmalı.
    if not (
        evidence_roots
        & answer_roots
    ) and not allow_answer_grounding_fallback:
        other_evidence_support = any(
            len(answer_roots & token_roots(other.text)) >= min(2, len(answer_roots))
            for evidence_id, other in evidence_by_id.items()
            if evidence_id != question.evidence_id and answer_roots
        )
        if other_evidence_support:
            return (
                False,
                "cross_evidence_relation",
            )
        return (
            False,
            "correct_answer_not_grounded",
        )

    if explicit_relation_mismatch(
        question.question_text,
        correct_option,
        evidence.text,
    ):
        return (
            False,
            "explicit_relation_mismatch",
        )

    # Aynı / neredeyse aynı seçenekleri engelle.
    correct_norm = (
        normalized_options[
            question.correct_index
        ]
    )

    for index, option_norm in enumerate(
        normalized_options
    ):

        if (
            index
            == question.correct_index
        ):
            continue

        if option_norm == correct_norm:
            return (
                False,
                "multiple_correct_problem",
            )

        if (
            len(option_norm) >= 8
            and (
                option_norm
                in correct_norm
                or correct_norm
                in option_norm
            )
        ):
            return (
                False,
                "multiple_correct_problem",
            )

    supported_option_indices = {question.correct_index}
    option_support_debug = {
        question.correct_index: "supported(correct_answer)"
    }
    for index, option in enumerate(
        question.options
    ):
        if index == question.correct_index:
            continue
        relation_supported, relation_reason = _option_relation_support(
            option,
            question.question_text,
            evidence.text,
        )
        coordinated_supported = short_options_share_supported_relation(
            question.question_text,
            correct_option,
            option,
            evidence.text,
        )
        if relation_supported or coordinated_supported:
            supported_option_indices.add(index)
            option_support_debug[index] = (
                "supported(relation_match)"
                if relation_supported
                else "supported(coordinated_relation)"
            )
        else:
            option_support_debug[index] = f"unsupported({relation_reason})"

    if len(supported_option_indices) > 1:
        labels = "ABCDE"
        logger.debug(
            "supported options: %s; option support: %s",
            ", ".join(labels[index] for index in sorted(supported_option_indices)),
            ", ".join(
                f"{labels[index]}={option_support_debug[index]}"
                for index in range(5)
            ),
        )
        return (
            False,
            "multiple_supported_options",
        )

    return (
        True,
        "accepted",
    )


# ============================================================
# SSE
# ============================================================

def iter_sse_content(
    response: Any,
    metrics: Metrics,
) -> Iterator[str]:

    while True:

        raw_line = response.readline()

        if not raw_line:
            break

        line = raw_line.decode(
            "utf-8",
            errors="replace",
        ).strip()

        if not line:
            continue

        if line.startswith(":"):
            continue

        if not line.startswith(
            "data:"
        ):
            continue

        data = line[5:].strip()

        if data == "[DONE]":
            metrics.done_received = True
            break

        try:

            event = json.loads(
                data
            )

            content = (
                event["choices"][0]
                .get(
                    "delta",
                    {},
                )
                .get(
                    "content"
                )
            )

        except (
            json.JSONDecodeError,
            KeyError,
            IndexError,
            TypeError,
        ) as exc:

            raise LMStudioError(
                "Geçersiz SSE olayı: "
                f"{data[:160]}"
            ) from exc

        if content:

            if (
                metrics.first_token_at
                is None
            ):
                metrics.first_token_at = (
                    time.monotonic()
                )

            yield str(content)


# ============================================================
# TERMINAL OUTPUT
# ============================================================

def shuffle_question_options(
    question: QuizQuestion,
    chooser: random.SystemRandom,
) -> QuizQuestion:
    indexed_options = list(enumerate(question.options))
    chooser.shuffle(indexed_options)
    shuffled_options = tuple(option for _old_index, option in indexed_options)
    new_correct_index = next(
        new_index
        for new_index, (old_index, _option) in enumerate(indexed_options)
        if old_index == question.correct_index
    )
    return QuizQuestion(
        evidence_id=question.evidence_id,
        question_text=question.question_text,
        options=shuffled_options,  # type: ignore[arg-type]
        correct_index=new_correct_index,
    )


def print_question(
    question: QuizQuestion,
    elapsed: float,
    validation_source: str = "local_evidence",
    display_number: int | None = None,
) -> None:

    labels = "ABCDE"

    print(
        f"\nSoru "
        f"{display_number or question.evidence_id} "
        f"accepted at: "
        f"{elapsed:.1f}s",
        flush=True,
    )

    print(
        "Question type: normal",
        flush=True,
    )

    print(
        question.question_text,
        flush=True,
    )

    for index, option in enumerate(
        question.options
    ):

        print(
            f"  {labels[index]}) "
            f"{option}",
            flush=True,
        )

    print(
        f"  Doğru: "
        f"{labels[question.correct_index]}",
        flush=True,
    )

    if validation_source == "full_pdf_fallback":
        print(
            "  Validation: full_pdf_fallback",
            flush=True,
        )


def print_rejected(
    candidate_id: Any,
    reason: str,
    candidate: Any,
) -> None:

    print(
        f"\nSoru "
        f"{candidate_id!r} "
        f"reddedildi: "
        f"{reason}",
        flush=True,
    )

    if not isinstance(
        candidate,
        dict,
    ):
        return

    text = candidate.get("t")
    options = candidate.get("o")
    answer = candidate.get("a")

    if isinstance(
        text,
        str,
    ):
        print(
            f"  Soru metni: {text}",
            flush=True,
        )

    if isinstance(
        options,
        list,
    ):

        if reason == "options_must_be_five_strings":
            option_types = [
                type(option).__name__
                for option in options
            ]
            print(
                f"  Option tipleri: {option_types}",
                flush=True,
            )

        labels = "ABCDE"

        for index, option in enumerate(
            options
        ):

            marker = ""

            if index == answer:
                marker = " <-- doğru"

            label = (
                labels[index]
                if index < len(labels)
                else str(index)
            )

            print(
                f"    {label}) "
                f"{option}"
                f"{marker}",
                flush=True,
            )


# ============================================================
# LM STUDIO REQUEST
# ============================================================

def stream_quiz(
    evidence: list[Evidence],
    full_pdf_index: FullPDFGroundingIndex,
    session: QuizSession,
) -> Metrics:

    prompt = build_prompt(
        evidence
    )

    body = {
        "model": MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": TEMPERATURE,
        "stream": True,
    }

    request = Request(
        (
            f"{BASE_URL}"
            "/v1/chat/completions"
        ),
        data=json.dumps(
            body,
            ensure_ascii=False,
        ).encode("utf-8"),
        headers={
            "Content-Type":
                "application/json",
            "Accept":
                "text/event-stream",
        },
        method="POST",
    )

    metrics = Metrics(
        request_start=time.monotonic()
    )

    parser = (
        QuestionObjectStream()
    )

    evidence_by_id = {
        item.evidence_id: item
        for item in evidence
    }

    accepted_texts = session.accepted_question_texts
    accepted_ids = session.accepted_evidence_ids
    option_chooser = random.SystemRandom()

    try:

        with urlopen(
            request,
            timeout=REQUEST_TIMEOUT_SECONDS,
        ) as response:

            for content in iter_sse_content(
                response,
                metrics,
            ):

                candidates = (
                    parser.feed(content)
                )

                metrics.completed_objects = parser.completed_objects
                metrics.invalid_json_objects = parser.invalid_json_objects

                for candidate in candidates:

                    metrics.raw_candidates += 1

                    candidate_id = (
                        candidate.get("i")
                        if isinstance(
                            candidate,
                            dict,
                        )
                        else None
                    )

                    try:

                        question = (
                            compact_to_question(
                                candidate
                            )
                        )

                    except ValueError as exc:

                        reason = str(exc)

                        metrics.rejected.append(
                            (
                                candidate_id,
                                reason,
                            )
                        )

                        print_rejected(
                            candidate_id,
                            reason,
                            candidate,
                        )

                        continue

                    valid, reason = (
                        validate_question(
                            question,
                            evidence_by_id,
                            accepted_texts,
                            accepted_ids,
                            accepted_question_facts=session.accepted_question_facts,
                        )
                    )

                    validation_source = "local_evidence"
                    fallback_debug: str | None = None
                    if (
                        ENABLE_FULL_PDF_FALLBACK_ACCEPTANCE
                        and not valid
                        and reason == "correct_answer_not_grounded"
                    ):
                        fallback_supported, fallback_debug = full_pdf_index.supports(
                            question.question_text,
                            question.options[question.correct_index],
                        )
                    else:
                        fallback_supported = False

                    if fallback_supported:
                        valid, reason = validate_question(
                            question,
                            evidence_by_id,
                            accepted_texts,
                            accepted_ids,
                            allow_answer_grounding_fallback=True,
                            accepted_question_facts=session.accepted_question_facts,
                        )
                        if valid:
                            validation_source = "full_pdf_fallback"

                    if not valid:

                        if (
                            reason == "correct_answer_not_grounded"
                            and fallback_debug
                        ):
                            print(
                                f"  fallback: {fallback_debug}",
                                flush=True,
                            )

                        metrics.rejected.append(
                            (
                                question.evidence_id,
                                reason,
                            )
                        )

                        print_rejected(
                            question.evidence_id,
                            reason,
                            candidate,
                        )

                        continue

                    now = (
                        time.monotonic()
                    )

                    if (
                        metrics
                        .first_valid_question_at
                        is None
                    ):
                        metrics.first_valid_question_at = (
                            now
                        )

                    accepted_texts.add(
                        normalize_text(
                            question.question_text
                        )
                    )

                    session.accepted_question_facts.append(
                        (
                            question.question_text,
                            question.options[question.correct_index],
                        )
                    )

                    accepted_ids.add(
                        question.evidence_id
                    )

                    session.accepted_count += 1
                    session.displayed_count += 1

                    elapsed = (
                        now
                        - metrics.request_start
                    )

                    metrics.accepted_at.append(
                        (
                            question.evidence_id,
                            elapsed,
                        )
                    )

                    if validation_source == "full_pdf_fallback":
                        metrics.full_pdf_fallback_accepted += 1
                    else:
                        metrics.local_evidence_accepted += 1

                    print_question(
                        shuffle_question_options(
                            question,
                            option_chooser,
                        ),
                        elapsed,
                        validation_source,
                        session.displayed_count,
                    )

    except HTTPError as exc:

        details = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        raise LMStudioError(
            f"HTTP {exc.code}: "
            f"{details}"
        ) from exc

    except (
        URLError,
        TimeoutError,
    ) as exc:

        raise LMStudioError(
            "LM Studio bağlantı "
            f"hatası: {exc}"
        ) from exc

    metrics.completed_objects = parser.completed_objects
    metrics.invalid_json_objects = parser.invalid_json_objects

    if metrics.raw_candidates < len(evidence):
        tail = parser.buffer[-500:]
        tail = " ".join(tail.replace("\x00", "").split())
        print("\nSTREAM_DEBUG:", flush=True)
        print(f"requested={len(evidence)}", flush=True)
        print(f"completed_objects={metrics.completed_objects}", flush=True)
        print(f"parsed_candidates={metrics.raw_candidates}", flush=True)
        print(f"invalid_json_objects={metrics.invalid_json_objects}", flush=True)
        print(f"array_found={str(parser.array_found).lower()}", flush=True)
        print(
            f"unfinished_object={str(parser.object_start is not None).lower()}",
            flush=True,
        )
        print(f"done_received={str(metrics.done_received).lower()}", flush=True)
        print(f"buffer_tail={tail}", flush=True)

    return metrics


# ============================================================
# METRICS
# ============================================================

def _format_latency(
    timestamp: float | None,
    start: float,
) -> str:

    if timestamp is None:
        return "alınamadı"

    return (
        f"{timestamp - start:.1f}s"
    )


# ============================================================
# BACKEND PRODUCTION ADAPTER
# ============================================================

def _production_candidate_pools(
    text: str,
    requested_count: int,
) -> tuple[list[tuple[int, str, float]], list[tuple[int, str, float]]]:
    """Build the same strict/primary/secondary pools as the CLI prototype."""
    strict_candidates = _evidence_candidates(text)
    if len(strict_candidates) >= requested_count:
        return strict_candidates, []

    adaptive_candidates = _adaptive_evidence_candidates(text)
    adaptive_primary = [
        item for item in adaptive_candidates
        if item[2] >= ADAPTIVE_PRIMARY_QUALITY
    ]
    adaptive_secondary = [
        item for item in adaptive_candidates
        if item[2] < ADAPTIVE_PRIMARY_QUALITY
        and ocr_fragment_penalty(item[1]) == 0
        and entity_switch_penalty(item[1]) == 0
    ]

    primary: list[tuple[int, str, float]] = []
    secondary: list[tuple[int, str, float]] = []
    seen: set[str] = set()
    for item in strict_candidates + adaptive_primary:
        normalized = normalize_text(item[1])
        if not _adaptive_quiz_metadata(item[1]) and normalized not in seen:
            seen.add(normalized)
            primary.append(item)
    for item in adaptive_secondary:
        normalized = normalize_text(item[1])
        if not _adaptive_quiz_metadata(item[1]) and normalized not in seen:
            seen.add(normalized)
            secondary.append(item)
    return primary, secondary


def _production_batch(
    evidence: list[Evidence],
    session: QuizSession,
    *,
    base_url: str,
    model: str,
    session_lock: threading.Lock | None = None,
    batch_metrics: ProductionBatchMetrics | None = None,
    target_count: int | None = None,
    validation_evidence_by_id: dict[int, Evidence] | None = None,
    generation_deadline: float | None = None,
) -> Iterator[QuizQuestion]:
    """Stream, parse and validate one initial/refill LM Studio request."""
    body = {
        "model": model,
        "messages": [{"role": "user", "content": build_prompt(evidence)}],
        "temperature": TEMPERATURE,
        "stream": True,
    }
    request = Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    parser = QuestionObjectStream()
    metrics = Metrics(request_start=time.monotonic())
    evidence_by_id = validation_evidence_by_id or {
        item.evidence_id: item for item in evidence
    }
    try:
        request_timeout = REQUEST_TIMEOUT_SECONDS
        if generation_deadline is not None:
            request_timeout = max(
                1.0,
                min(request_timeout, generation_deadline - time.monotonic()),
            )
        with urlopen(request, timeout=request_timeout) as response:
            for content in iter_sse_content(response, metrics):
                if (
                    generation_deadline is not None
                    and time.monotonic() >= generation_deadline
                ):
                    raise LMStudioError("Quiz üretim süre bütçesi aşıldı.")
                for candidate in parser.feed(content):
                    try:
                        question = compact_to_question(candidate)
                    except ValueError as exc:
                        if batch_metrics is not None:
                            batch_metrics.rejected_count += 1
                            batch_metrics.rejection_reasons[str(exc)] += 1
                        candidate_id = (
                            candidate.get("i") if isinstance(candidate, dict) else None
                        )
                        if isinstance(candidate_id, int) and candidate_id in evidence_by_id:
                            lock = session_lock or threading.Lock()
                            with lock:
                                session.rejected_evidence_ids.add(candidate_id)
                                session.rejected_evidence_texts.add(normalize_text(
                                    evidence_by_id[candidate_id].text
                                ))
                        logger.info("Quiz candidate rejected reason=%s", exc)
                        continue
                    lock = session_lock or threading.Lock()
                    with lock:
                        if target_count is not None and session.accepted_count >= target_count:
                            continue
                        valid, reason = validate_question(
                            question,
                            evidence_by_id,
                            session.accepted_question_texts,
                            session.accepted_evidence_ids,
                            accepted_question_facts=session.accepted_question_facts,
                        )
                        if valid:
                            session.accepted_question_texts.add(
                                normalize_text(question.question_text)
                            )
                            session.accepted_question_facts.append(
                                (question.question_text, question.options[question.correct_index])
                            )
                            session.accepted_evidence_ids.add(question.evidence_id)
                            session.accepted_count += 1
                            if batch_metrics is not None:
                                batch_metrics.accepted_count += 1
                        elif batch_metrics is not None:
                            batch_metrics.rejected_count += 1
                            batch_metrics.rejection_reasons[reason] += 1
                            session.rejected_evidence_ids.add(question.evidence_id)
                            session.rejected_evidence_texts.add(normalize_text(
                                evidence_by_id[question.evidence_id].text
                            ))
                    if not valid:
                        logger.info(
                            "Quiz candidate rejected evidence=%s reason=%s",
                            question.evidence_id,
                            reason,
                        )
                        continue
                    yield shuffle_question_options(question, random.SystemRandom())
    except HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise LMStudioError(f"HTTP {exc.code}: {details}") from exc
    except (URLError, TimeoutError) as exc:
        raise LMStudioError(f"LM Studio bağlantı hatası: {exc}") from exc


def _production_batch_plan(question_count: int) -> list[int]:
    """Keep first-question latency low without creating tiny normal batches."""
    if question_count <= 0:
        return []
    if question_count == 1:
        return [1]
    if question_count <= 5:
        return [1, question_count - 1]

    remaining = question_count - 1
    batch_count = math.ceil(remaining / 4)
    base, extra = divmod(remaining, batch_count)
    return [1] + [base + (1 if index < extra else 0) for index in range(batch_count)]


def _refill_call_budget(question_count: int) -> int:
    """Bound retries while giving larger quizzes enough completion attempts."""
    return max(MAX_REFILL_ROUNDS, min(12, math.ceil(question_count * 0.8)))


def _replacement_batch_size(missing_count: int) -> int:
    if missing_count <= 0:
        return 0
    if missing_count <= 2:
        return missing_count
    if missing_count <= 4:
        return min(3, missing_count)
    return MAX_REPLACEMENT_BATCH_SIZE


def _evidence_semantically_close(left: str, right: str) -> bool:
    left_roots = token_roots(left)
    right_roots = token_roots(right)
    shared = left_roots & right_roots
    if len(shared) < 5:
        return False
    union = left_roots | right_roots
    smaller = min(len(left_roots), len(right_roots))
    return bool(
        union and len(shared) / len(union) >= 0.72
        or smaller and len(shared) / smaller >= 0.85
    )


def generate_production_quiz(
    text: str,
    question_count: int,
    *,
    base_url: str,
    model: str = MODEL,
    previous_question_texts: set[str] | None = None,
) -> Iterator[QuizQuestion]:
    """Yield exactly ``question_count`` locally grounded normal MCQs."""
    if not text or not text.strip():
        raise LMStudioError("Quiz soruları oluşturulamadı.")

    cleaned_text = clean_pdf_text(text)
    try:
        primary_pool, secondary_pool = _production_candidate_pools(
            cleaned_text, question_count
        )
        initial_evidence = select_evidence(
            cleaned_text, question_count, candidates=primary_pool
        )
    except RuntimeError as error:
        raise LMStudioError("Quiz için yeterli uygun içerik bulunamadı.") from error
    session = QuizSession()
    session.accepted_question_texts.update(previous_question_texts or set())
    session.used_evidence_texts.update(
        normalize_text(item.text) for item in initial_evidence
    )

    plan = _production_batch_plan(question_count)
    initial_batches: list[list[Evidence]] = []
    offset = 0
    for size in plan:
        initial_batches.append(initial_evidence[offset:offset + size])
        offset += size

    quiz_started_at = time.monotonic()
    first_question_at: float | None = None
    session_lock = threading.Lock()
    event_queue: Queue[tuple[str, int, Any]] = Queue()
    pending: deque[tuple[list[Evidence], bool]] = deque(
        (batch, False) for batch in initial_batches
    )
    active = 0
    next_batch_id = 1
    next_evidence_id = max(item.evidence_id for item in initial_evidence) + 1
    refill_calls = 0
    refill_call_budget = _refill_call_budget(question_count)
    failed_refill_batches = 0
    lm_calls = 0
    pending_replacements = 0
    all_metrics: list[ProductionBatchMetrics] = []
    validation_evidence_by_id = {
        item.evidence_id: item for item in initial_evidence
    }
    generation_deadline = quiz_started_at + max(
        MIN_TOTAL_GENERATION_SECONDS,
        question_count * GENERATION_SECONDS_PER_QUESTION,
    )

    logger.info(
        "QUIZ PERF requested=%s initial_batches=%s max_concurrency=%s",
        question_count,
        plan,
        MAX_LM_CONCURRENCY,
    )

    def run_batch(
        batch_id: int,
        evidence: list[Evidence],
        refill: bool,
        metrics: ProductionBatchMetrics,
    ) -> None:
        try:
            for question in _production_batch(
                evidence,
                session,
                base_url=base_url,
                model=model,
                session_lock=session_lock,
                batch_metrics=metrics,
                target_count=question_count,
                validation_evidence_by_id=validation_evidence_by_id,
                generation_deadline=generation_deadline,
            ):
                event_queue.put(("question", batch_id, question))
        except BaseException as exc:
            event_queue.put(("error", batch_id, exc))
        finally:
            event_queue.put(("done", batch_id, metrics))

    def make_refill(count: int) -> list[Evidence]:
        nonlocal next_evidence_id
        unused_primary_all = [
            item for item in primary_pool
            if normalize_text(item[1]) not in session.used_evidence_texts
            and normalize_text(item[1]) not in session.rejected_evidence_texts
            and _selected_evidence_rejection_reason(item[1]) is None
        ]
        unused_secondary_all = [
            item for item in secondary_pool
            if normalize_text(item[1]) not in session.used_evidence_texts
            and normalize_text(item[1]) not in session.rejected_evidence_texts
            and _selected_evidence_rejection_reason(item[1]) is None
        ]
        previous_evidence = list(session.used_evidence_texts)

        def diverse(items: list[tuple[int, str, float]]) -> list[tuple[int, str, float]]:
            return [
                item for item in items
                if not any(
                    _evidence_semantically_close(item[1], previous)
                    for previous in previous_evidence
                )
            ]

        diverse_primary = diverse(unused_primary_all)
        diverse_secondary = diverse(unused_secondary_all)
        # Completion is more important than diversity once the diverse pool is empty.
        if diverse_primary or diverse_secondary:
            unused_primary = diverse_primary
            unused_secondary = diverse_secondary
        else:
            unused_primary = unused_primary_all
            unused_secondary = unused_secondary_all
        refill_count = min(count, len(unused_primary) + len(unused_secondary))
        primary_count = min(refill_count, len(unused_primary))
        refill: list[Evidence] = []
        if primary_count:
            refill.extend(select_evidence(
                cleaned_text,
                primary_count,
                candidates=unused_primary,
                first_evidence_id=next_evidence_id,
            ))
        secondary_count = refill_count - primary_count
        if secondary_count:
            refill.extend(select_evidence(
                cleaned_text,
                secondary_count,
                candidates=unused_secondary,
                first_evidence_id=next_evidence_id + primary_count,
            ))
        refill.sort(key=lambda item: item.position)
        next_evidence_id += len(refill)
        with session_lock:
            session.used_evidence_texts.update(
                normalize_text(item.text) for item in refill
            )
            validation_evidence_by_id.update(
                (item.evidence_id, item) for item in refill
            )
        return refill

    error: BaseException | None = None
    with ThreadPoolExecutor(max_workers=MAX_LM_CONCURRENCY) as executor:
        while pending or active or pending_replacements:
            while active < MAX_LM_CONCURRENCY:
                with session_lock:
                    completion_reached = session.accepted_count >= question_count
                if completion_reached:
                    pending.clear()
                    pending_replacements = 0
                    break
                if pending:
                    evidence, is_refill = pending.popleft()
                elif (
                    pending_replacements
                    and refill_calls < refill_call_budget
                    and time.monotonic() < generation_deadline
                ):
                    refill_size = _replacement_batch_size(pending_replacements)
                    evidence = make_refill(refill_size)
                    if not evidence:
                        pending_replacements = 0
                        break
                    pending_replacements -= len(evidence)
                    is_refill = True
                    refill_calls += 1
                else:
                    break
                batch_id = next_batch_id
                next_batch_id += 1
                metrics = ProductionBatchMetrics(batch_id, len(evidence), is_refill)
                all_metrics.append(metrics)
                lm_calls += 1
                active += 1
                executor.submit(run_batch, batch_id, evidence, is_refill, metrics)

            if not active:
                break
            event_type, batch_id, payload = event_queue.get()
            if event_type == "question":
                if first_question_at is None:
                    first_question_at = time.monotonic()
                yield payload
            elif event_type == "error":
                error = payload
            else:
                active -= 1
                metrics = payload
                if metrics.refill:
                    if metrics.accepted_count == 0:
                        failed_refill_batches += 1
                    else:
                        failed_refill_batches = 0
                with session_lock:
                    remaining_questions = max(
                        0, question_count - session.accepted_count
                    )
                if remaining_questions:
                    pending_replacements += max(
                        0, metrics.requested_count - metrics.accepted_count
                    )
                else:
                    pending.clear()
                    pending_replacements = 0
                remaining_evidence = sum(
                    1 for item in primary_pool + secondary_pool
                    if normalize_text(item[1]) not in session.used_evidence_texts
                    and normalize_text(item[1]) not in session.rejected_evidence_texts
                    and _selected_evidence_rejection_reason(item[1]) is None
                )
                logger.info(
                    "Quiz LM batch batch_id=%s requested_count=%s accepted_count=%s "
                    "rejected_count=%s elapsed_seconds=%.2f refill=%s "
                    "remaining_questions=%s remaining_evidence=%s "
                    "refill_budget_remaining=%s failed_refill_batches=%s "
                    "rejection_reasons=%s",
                    metrics.batch_id,
                    metrics.requested_count,
                    metrics.accepted_count,
                    metrics.rejected_count,
                    metrics.elapsed_seconds,
                    str(metrics.refill).lower(),
                    remaining_questions,
                    remaining_evidence,
                    max(0, refill_call_budget - refill_calls),
                    failed_refill_batches,
                    dict(metrics.rejection_reasons),
                )
            if error is not None:
                pending.clear()
                pending_replacements = 0

    total_elapsed = time.monotonic() - quiz_started_at
    rejection_totals: Counter[str] = Counter()
    for metrics in all_metrics:
        rejection_totals.update(metrics.rejection_reasons)
    logger.info(
        "QUIZ PERF requested=%s initial_batches=%s lm_calls=%s refill_calls=%s "
        "rejected_candidates=%s accepted_questions=%s first_question_seconds=%s "
        "total_seconds=%.2f remaining_questions=%s remaining_evidence=%s "
        "refill_budget_remaining=%s failed_refill_batches=%s rejection_reasons=%s",
        question_count,
        plan,
        lm_calls,
        refill_calls,
        sum(item.rejected_count for item in all_metrics),
        session.accepted_count,
        (
            f"{first_question_at - quiz_started_at:.2f}"
            if first_question_at is not None else "none"
        ),
        total_elapsed,
        max(0, question_count - session.accepted_count),
        sum(
            1 for item in primary_pool + secondary_pool
            if normalize_text(item[1]) not in session.used_evidence_texts
            and normalize_text(item[1]) not in session.rejected_evidence_texts
            and _selected_evidence_rejection_reason(item[1]) is None
        ),
        max(0, refill_call_budget - refill_calls),
        failed_refill_batches,
        dict(rejection_totals),
    )

    if error is not None:
        if isinstance(error, LMStudioError):
            raise error
        raise LMStudioError("Quiz soruları oluşturulamadı.") from error

    if session.accepted_count != question_count:
        logger.error(
            "Quiz generation exhausted requested=%s accepted=%s refill_rounds=%s",
            question_count,
            session.accepted_count,
            refill_calls,
        )
        raise LMStudioError("Quiz soruları oluşturulamadı.")


# ============================================================
# MAIN
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Qwen3-8B compact streaming quiz testi.",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=QUESTION_COUNT,
        choices=(5, 10, 15),
        help="Üretilecek soru sayısı (default: 15).",
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=PDF_PATH,
        help=f"Kaynak PDF yolu (default: {PDF_PATH}).",
    )
    return parser.parse_args()


def main() -> int:

    args = parse_args()
    requested_count = args.count
    pdf_path = args.pdf.expanduser()
    if not pdf_path.is_absolute():
        pdf_path = (Path.cwd() / pdf_path).resolve()

    if not pdf_path.is_file():

        print(
            f"HATA: PDF bulunamadı: "
            f"{pdf_path}",
            file=sys.stderr,
        )

        return 1

    try:

        text, pages = (
            extract_pdf_text(
                pdf_path
            )
        )

        evidence_debug = EvidenceCandidateDebug()
        strict_candidates = (
            _evidence_candidates(
                text,
                evidence_debug,
            )
        )

        if len(strict_candidates) >= requested_count:
            candidate_pool = strict_candidates
            print("EVIDENCE MODE: strict")
        else:
            print_evidence_debug(evidence_debug)
            adaptive_debug = AdaptiveEvidenceDebug()
            adaptive_candidates = _adaptive_evidence_candidates(
                text,
                adaptive_debug,
            )
            adaptive_primary_candidates = [
                candidate for candidate in adaptive_candidates
                if candidate[2] >= ADAPTIVE_PRIMARY_QUALITY
            ]
            adaptive_secondary_candidates = [
                candidate for candidate in adaptive_candidates
                if candidate[2] < ADAPTIVE_PRIMARY_QUALITY
                and ocr_fragment_penalty(candidate[1]) == 0
                and entity_switch_penalty(candidate[1]) == 0
            ]
            combined_candidates = [
                candidate
                for candidate in strict_candidates + adaptive_primary_candidates
                if not _adaptive_quiz_metadata(candidate[1])
            ]
            candidate_pool = []
            candidate_texts: set[str] = set()
            for candidate in combined_candidates:
                normalized_candidate = normalize_text(candidate[1])
                if normalized_candidate not in candidate_texts:
                    candidate_texts.add(normalized_candidate)
                    candidate_pool.append(candidate)
            secondary_candidate_pool = []
            for candidate in adaptive_secondary_candidates:
                if _adaptive_quiz_metadata(candidate[1]):
                    continue
                normalized_candidate = normalize_text(candidate[1])
                if normalized_candidate not in candidate_texts:
                    candidate_texts.add(normalized_candidate)
                    secondary_candidate_pool.append(candidate)
            print("\nEVIDENCE MODE: adaptive")
            print(f"strict candidates={len(strict_candidates)}")
            print(f"adaptive raw blocks={adaptive_debug.raw_blocks}")
            print(
                "sentence completion attempts="
                f"{adaptive_debug.sentence_completion_attempts}"
            )
            print(
                "sentence completion success="
                f"{adaptive_debug.sentence_completion_success}"
            )
            print(
                "sentence completion rejected="
                f"{adaptive_debug.sentence_completion_rejected}"
            )
            if adaptive_debug.sentence_completed_examples:
                print("\nSENTENCE_COMPLETED examples:")
                for before, after in adaptive_debug.sentence_completed_examples:
                    print(f"- BEFORE: {' '.join(before.split())[:320]}")
                    print(f"  AFTER: {' '.join(after.split())[:900]}")
            print(
                "reconstruction attempts="
                f"{adaptive_debug.reconstruction_attempts}"
            )
            print(
                "reconstruction success="
                f"{adaptive_debug.reconstruction_success}"
            )
            print(
                "reconstruction rejected="
                f"{adaptive_debug.reconstruction_rejected}"
            )
            print(
                "post_reconstruction_checked="
                f"{adaptive_debug.post_reconstruction_checked}"
            )
            print(
                "post_reconstruction_rejected="
                f"{adaptive_debug.post_reconstruction_rejected}"
            )
            print(f"adaptive complete blocks={adaptive_debug.complete_blocks}")
            print(
                "context-dependent blocks="
                f"{adaptive_debug.context_dependent_blocks}"
            )
            print(
                "context-completed blocks="
                f"{adaptive_debug.context_completed_blocks}"
            )
            print(
                "context-rejected blocks="
                f"{adaptive_debug.context_rejected_blocks}"
            )
            print(f"adaptive enriched blocks={adaptive_debug.enriched_blocks}")
            print(
                "adaptive avg evidence chars="
                f"{adaptive_debug.average_evidence_chars:.1f}"
            )
            adaptive_rejection_labels = (
                ("incomplete", "INCOMPLETE"),
                ("context_dependent", "CONTEXT_DEPENDENT"),
                ("metadata", "METADATA"),
                ("no_factual_predicate", "NO_FACTUAL_PREDICATE"),
                ("too_short", "TOO_SHORT"),
                ("noise", "NOISE"),
                ("multi_topic", "MULTI_TOPIC"),
                ("atomicity", "ATOMICITY"),
                ("syntactic_break", "SYNTACTIC_BREAK"),
                ("entity_switch", "ENTITY_SWITCH"),
                ("other", "OTHER"),
            )
            adaptive_rejection_names = {
                "context_dependent": "context-dependent",
                "no_factual_predicate": "no factual predicate",
                "too_short": "too short",
                "multi_topic": "multi-topic",
                "syntactic_break": "syntactic break",
                "entity_switch": "entity-switch",
            }
            for category, _label in adaptive_rejection_labels:
                print(
                    "adaptive rejected "
                    f"{adaptive_rejection_names.get(category, category)}="
                    f"{adaptive_debug.rejection_counts.get(category, 0)}"
                )
            adaptive_total_rejected = sum(
                adaptive_debug.rejection_counts.values()
            )
            print(f"adaptive accepted complete={adaptive_debug.complete_blocks}")
            print(f"adaptive total rejected={adaptive_total_rejected}")
            for category, label in adaptive_rejection_labels:
                examples = adaptive_debug.rejection_examples.get(category, [])
                if examples:
                    print(f"\nADAPTIVE_{label} examples:")
                    for example in examples:
                        print(f"- {example}")
            if adaptive_debug.accepted_complete_blocks:
                print("\nADAPTIVE COMPLETE BLOCKS:")
                for index, (complete_block, quality) in enumerate(
                    adaptive_debug.accepted_complete_blocks,
                    1,
                ):
                    display_block = " ".join(complete_block.split())[:320]
                    print(f"{index}|[Q={quality:.1f}]|{display_block}")
            if adaptive_debug.reconstructed_examples:
                print("\nRECONSTRUCTED examples:")
                for example in adaptive_debug.reconstructed_examples:
                    print(f"- {example}")
            if adaptive_debug.reconstruction_rejected_examples:
                print("\nRECONSTRUCTION_REJECTED examples:")
                for example in adaptive_debug.reconstruction_rejected_examples:
                    print(f"- {example}")
            if adaptive_debug.post_reconstruction_rejected_examples:
                print("\nPOST_RECONSTRUCTION_REJECTED examples:")
                for example in adaptive_debug.post_reconstruction_rejected_examples:
                    print(f"- {example}")
            if adaptive_debug.context_completed_examples:
                print("\nCONTEXT_COMPLETED examples:")
                for example in adaptive_debug.context_completed_examples:
                    print(f"- {example}")
            if adaptive_debug.context_rejected_examples:
                print("\nCONTEXT_REJECTED examples:")
                for example in adaptive_debug.context_rejected_examples:
                    print(f"- {example}")
            if adaptive_debug.enriched_examples:
                print("\nENRICHED examples:")
                for example in adaptive_debug.enriched_examples:
                    print(f"- {example}")
            print(f"adaptive primary candidates={len(candidate_pool)}")
            print(f"adaptive secondary candidates={len(secondary_candidate_pool)}")

        if len(strict_candidates) >= requested_count:
            secondary_candidate_pool = []

        selected_gate_debug = SelectedGateDebug()
        evidence = (
            select_evidence(
                text,
                requested_count,
                candidates=candidate_pool,
                selected_gate_debug=selected_gate_debug,
            )
        )
        print_selected_gate_debug(selected_gate_debug)

        full_pdf_index = (
            FullPDFGroundingIndex.build(
                text
            )
        )

    except (
        RuntimeError,
        OSError,
    ) as exc:

        print(
            f"HATA: {exc}",
            file=sys.stderr,
        )

        return 1

    print(
        f"PDF: {pdf_path} "
        f"| Sayfa: {pages} "
        f"| Temiz karakter: "
        f"{len(text)}"
    )

    print(
        "\nEVIDENCE:"
    )

    for item in evidence:

        position_percent = (
            item.position
            / max(len(text) - 1, 1)
            * 100
        )

        print(
            f"{item.evidence_id}|"
            f"[%{position_percent:.1f}]"
            f"[Q={item.quality:.1f}]|"
            f"{item.text}"
        )

    print(
        "\nREQUEST_START: "
        f"{time.strftime('%Y-%m-%d %H:%M:%S')}",
        flush=True,
    )

    session = QuizSession()
    session.used_evidence_texts.update(
        normalize_text(item.text)
        for item in evidence
    )
    quiz_started_at = time.monotonic()

    try:

        metrics = (
            stream_quiz(
                evidence,
                full_pdf_index,
                session,
            )
        )

        initial_accepted = session.accepted_count
        refill_accepted = 0
        refill_requests = 0
        next_evidence_id = max(item.evidence_id for item in evidence) + 1
        refill_evidence_serial = 0

        while (
            session.accepted_count < requested_count
            and refill_requests < MAX_REFILL_ROUNDS
        ):
            missing = requested_count - session.accepted_count
            unused_primary = [
                candidate for candidate in candidate_pool
                if normalize_text(candidate[1]) not in session.used_evidence_texts
                and _selected_evidence_rejection_reason(candidate[1]) is None
            ]
            unused_secondary = [
                candidate for candidate in secondary_candidate_pool
                if normalize_text(candidate[1]) not in session.used_evidence_texts
                and _selected_evidence_rejection_reason(candidate[1]) is None
            ]
            if len(unused_primary) + len(unused_secondary) < missing:
                print(
                    "REFILL DURDU: "
                    f"Yalnızca {len(unused_primary) + len(unused_secondary)} "
                    f"uygun evidence bulundu; {missing} gerekli.",
                    flush=True,
                )
                print(f"unused primary={len(unused_primary)}", flush=True)
                print(f"unused secondary={len(unused_secondary)}", flush=True)
                break

            primary_count = min(missing, len(unused_primary))
            secondary_count = missing - primary_count
            refill_evidence: list[Evidence] = []
            refill_sources: dict[int, str] = {}
            if primary_count:
                primary_evidence = select_evidence(
                    text,
                    primary_count,
                    candidates=unused_primary,
                    first_evidence_id=next_evidence_id,
                    selected_gate_debug=selected_gate_debug,
                )
                refill_evidence.extend(primary_evidence)
                refill_sources.update(
                    (item.evidence_id, "P") for item in primary_evidence
                )
            if secondary_count:
                secondary_evidence = select_evidence(
                    text,
                    secondary_count,
                    candidates=unused_secondary,
                    first_evidence_id=next_evidence_id + primary_count,
                    selected_gate_debug=selected_gate_debug,
                )
                refill_evidence.extend(secondary_evidence)
                refill_sources.update(
                    (item.evidence_id, "S") for item in secondary_evidence
                )
            refill_evidence.sort(key=lambda item: item.position)
            print_selected_gate_debug(selected_gate_debug)

            refill_requests += 1
            next_evidence_id += len(refill_evidence)
            session.used_evidence_texts.update(
                normalize_text(item.text)
                for item in refill_evidence
            )

            print("\nREFILL EVIDENCE:", flush=True)
            for item in refill_evidence:
                refill_evidence_serial += 1
                position_percent = (
                    item.position
                    / max(len(text) - 1, 1)
                    * 100
                )
                print(
                    f"R{refill_evidence_serial}[{refill_sources[item.evidence_id]}]|"
                    f"[%{position_percent:.1f}]"
                    f"[Q={item.quality:.1f}]|"
                    f"{item.text}",
                    flush=True,
                )

            before_refill = session.accepted_count
            refill_metrics = stream_quiz(
                refill_evidence,
                full_pdf_index,
                session,
            )
            refill_accepted += session.accepted_count - before_refill

            metrics.completed_objects += refill_metrics.completed_objects
            metrics.raw_candidates += refill_metrics.raw_candidates
            metrics.invalid_json_objects += refill_metrics.invalid_json_objects
            metrics.local_evidence_accepted += refill_metrics.local_evidence_accepted
            metrics.full_pdf_fallback_accepted += refill_metrics.full_pdf_fallback_accepted
            metrics.rejected.extend(refill_metrics.rejected)

    except LMStudioError as exc:

        print(
            f"HATA: {exc}",
            file=sys.stderr,
        )

        return 1

    total_elapsed = time.monotonic() - quiz_started_at

    # Önceki EOL syntax hatasının
    # oluştuğu bölüm düzeltildi.
    first_token_text = (
        _format_latency(
            metrics.first_token_at,
            metrics.request_start,
        )
    )

    first_valid_text = (
        _format_latency(
            metrics.first_valid_question_at,
            metrics.request_start,
        )
    )

    print(
        "\n--- METRICS ---"
    )

    print(
        f"Requested: "
        f"{requested_count}"
    )

    print(f"Initial accepted: {initial_accepted}")

    print(f"Refill accepted: {refill_accepted}")

    print(f"Refill requests: {refill_requests}")

    print(
        f"Final accepted: "
        f"{session.accepted_count}"
        f"/{requested_count}"
    )

    print(
        f"Completed objects: "
        f"{metrics.completed_objects}"
    )

    print(
        f"Parsed candidates: "
        f"{metrics.raw_candidates}"
    )

    print(
        f"Invalid JSON objects: "
        f"{metrics.invalid_json_objects}"
    )

    print(
        f"Local evidence accepted: "
        f"{metrics.local_evidence_accepted}"
    )

    print(
        f"Full PDF fallback accepted: "
        f"{metrics.full_pdf_fallback_accepted}"
    )

    print(
        f"First token: "
        f"{first_token_text}"
    )

    print(
        f"First valid question: "
        f"{first_valid_text}"
    )

    print(
        f"TOTAL_ELAPSED: "
        f"{total_elapsed:.1f}s"
    )

    print(
        f"Rejected: "
        f"{metrics.rejected}"
    )

    return (
        0
        if session.accepted_count
        == requested_count
        else 2
    )


if __name__ == "__main__":
    sys.exit(
        main()
    )
