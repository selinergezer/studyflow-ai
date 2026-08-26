import threading
import time
import unittest
from unittest.mock import patch

import app.services.quiz_generation_service as service
from app.services.quiz_generation_service import (
    ENABLE_FULL_PDF_FALLBACK_ACCEPTANCE,
    Evidence,
    QuizQuestion,
    validate_question,
)


class ProductionQuizValidationTests(unittest.TestCase):
    def validate(self, evidence_text, question_text, options, answer):
        evidence = Evidence(1, evidence_text, 0, 3.0)
        question = QuizQuestion(1, question_text, tuple(options), answer)
        return validate_question(question, {1: evidence}, set(), set())

    def test_talep_arz_subject_scope(self):
        result = self.validate(
            "Talep, belirli bir mal veya hizmeti farklı fiyat düzeylerinde "
            "satın alma isteğini; arz ise üreticilerin bu mal veya hizmeti "
            "farklı fiyatlarda sunma eğilimini ifade eder.",
            "Talep tanımıyla ilgili aşağıdaki seçeneklerden hangisi doğrudur?",
            [
                "Fiyatlar arttıkça talep artar",
                "Talep, üretici davranışını ifade eder",
                "Talep, mal veya hizmeti satın alma isteğini ifade eder",
                "Talep, piyasa dengesini sağlar",
                "Talep, arz ile aynıdır",
            ],
            2,
        )
        self.assertEqual(result, (True, "accepted"))

    def test_identity_change_causes_trust_problem(self):
        result = self.validate(
            "Çevrimiçi kimliklerin kolayca değiştirilebilmesi güven "
            "problemlerine yol açmaktadır.",
            "Çevrimiçi kimliklerin değiştirilebilmesi hangisine yol açar?",
            ["İletişim hızına", "Güven sorunlarına", "İçerik üretimine",
             "Kimlik doğrulamaya", "Platform düzenine"],
            1,
        )
        self.assertEqual(result, (True, "accepted"))

    def test_hate_speech_effect(self):
        result = self.validate(
            "Nefret söylemi yalnızca bireysel zarar oluşturmaz; toplumsal "
            "kutuplaşmayı ve ayrımcılığı da artırabilir.",
            "Nefret söyleminin bir sonucu nedir?",
            ["Toplumsal kutuplaşmayı artırması", "Eşitliği güçlendirmesi",
             "İletişimi kolaylaştırması", "Güveni artırması", "Zararı önlemesi"],
            0,
        )
        self.assertEqual(result, (True, "accepted"))

    def test_platform_visibility_effect(self):
        result = self.validate(
            "Sosyal medya platformları kullanıcıların ilgisini çeken, yüksek "
            "etkileşim alan ve yoğun yorum yapılan içerikleri daha görünür hâle getirir.",
            "Sosyal medya platformları hangisini yapar?",
            ["İçerikleri siler", "İçerikleri daha görünür hâle getirir",
             "Yorumları engeller", "Hesapları kapatır", "Etkileşimi azaltır"],
            1,
        )
        self.assertEqual(result, (True, "accepted"))

    def test_short_grounded_sunil_answer(self):
        result = self.validate(
            "Bu süreçte, resmi doğrulama olmadan «Sunil Tripathi» yanlış "
            "şekilde saldırıyla ilişkilendirilmiştir.",
            "«Sunil Tripathi» yanlış şekilde hangisiyle ilişkilendirilmiştir?",
            ["Yarışla", "Saldırıyla", "Doğrulamayla", "Ödülle", "Kurumla"],
            1,
        )
        self.assertEqual(result, (True, "accepted"))

    def test_reddit_positive_and_unsupported_negative(self):
        evidence = (
            "Reddit kullanıcıları olayla ilgili fotoğrafları incelemiş, "
            "şüpheli kişileri tartışmış, çok sayıda yorum paylaşmıştır."
        )
        positive = self.validate(
            evidence,
            "Reddit kullanıcıları olayla ilgili ne yapmıştır?",
            ["Fotoğrafları incelemiştir", "Olayı gizlemiştir", "Yorumları silmiştir",
             "Tartışmayı yasaklamıştır", "Hesapları kapatmıştır"],
            0,
        )
        negative = self.validate(
            evidence,
            "Reddit kullanıcıları hangisini yapmamıştır?",
            ["Fotoğrafları incelemek", "Şüphelileri tartışmak", "Yorum paylaşmak",
             "Olay hakkında bilgi vermemek", "Fotoğrafları değerlendirmek"],
            3,
        )
        self.assertEqual(positive, (True, "accepted"))
        self.assertFalse(negative[0])

    def test_explicit_enumeration_rejects_multiple_supported(self):
        result = self.validate(
            "Sermaye piyasasında hisse senetleri, tahviller ve yatırım "
            "fonları işlem görür.",
            "Sermaye piyasasında hangi araçlar işlem görür?",
            ["Hisse senetleri", "Tahviller", "Yatırım fonları", "Mevduatlar", "Çekler"],
            0,
        )
        self.assertEqual(result, (False, "multiple_supported_options"))

    def test_combination_format_is_forbidden(self):
        result = self.validate(
            "Bankalar finansal sistemde aracılık yapar.",
            "I. Bankalar finansal sistemde aracılık yapar. Hangisi doğrudur?",
            ["Yalnız I", "Yanlış", "Eksik", "Belirsiz", "Hiçbiri"],
            0,
        )
        self.assertEqual(result, (False, "combination_format_forbidden"))

    def test_full_pdf_fallback_acceptance_remains_disabled(self):
        self.assertFalse(ENABLE_FULL_PDF_FALLBACK_ACCEPTANCE)


class ProductionQuizBatchingTests(unittest.TestCase):
    def setUp(self):
        self.pool = [
            (index * 100, f"Geçerli ve tamamlanmış evidence metni {index}.", 3.0)
            for index in range(1, 41)
        ]

    @staticmethod
    def _select(_text, count, *, candidates, first_evidence_id=1, **_kwargs):
        return [
            Evidence(first_evidence_id + offset, item[1], item[0], item[2])
            for offset, item in enumerate(candidates[:count])
        ]

    def _patch_pipeline(self, batch):
        return (
            patch.object(service, "clean_pdf_text", return_value="temiz metin"),
            patch.object(
                service, "_production_candidate_pools", return_value=(self.pool, [])
            ),
            patch.object(service, "select_evidence", side_effect=self._select),
            patch.object(service, "_production_batch", side_effect=batch),
        )

    @staticmethod
    def _accepting_batch(evidence, session, **kwargs):
        lock = kwargs["session_lock"]
        metrics = kwargs["batch_metrics"]
        for item in evidence:
            with lock:
                if session.accepted_count >= kwargs["target_count"]:
                    return
                number = session.accepted_count + 1
                session.accepted_count += 1
                session.accepted_evidence_ids.add(item.evidence_id)
                session.accepted_question_texts.add(f"doğrulanmış soru {number}")
                metrics.accepted_count += 1
            yield QuizQuestion(
                item.evidence_id,
                f"Doğrulanmış soru {number}?",
                ("A", "B", "C", "D", "E"),
                0,
            )

    def _run(self, count, batch=None):
        contexts = self._patch_pipeline(batch or self._accepting_batch)
        with contexts[0], contexts[1], contexts[2], contexts[3]:
            return list(service.generate_production_quiz(
                "kaynak", count, base_url="http://unused"
            ))

    def test_batch_plans(self):
        self.assertEqual(service._production_batch_plan(5), [1, 4])
        self.assertEqual(service._production_batch_plan(10), [1, 3, 3, 3])
        self.assertEqual(service._production_batch_plan(15), [1, 4, 4, 3, 3])
        self.assertEqual(service._refill_call_budget(15), 12)

    def test_replacement_batch_sizes_shrink_with_remaining_questions(self):
        self.assertEqual(service._replacement_batch_size(1), 1)
        self.assertEqual(service._replacement_batch_size(2), 2)
        self.assertEqual(service._replacement_batch_size(3), 3)
        self.assertEqual(service._replacement_batch_size(4), 3)
        self.assertEqual(service._replacement_batch_size(8), 4)

    def test_five_ten_and_fifteen_return_exact_count_without_duplicates(self):
        for count in (5, 10, 15):
            with self.subTest(count=count):
                output = self._run(count)
                self.assertEqual(len(output), count)
                self.assertEqual(len({item.question_text for item in output}), count)
                self.assertEqual(len({item.evidence_id for item in output}), count)

    def test_initial_batches_never_reuse_evidence(self):
        seen = []
        seen_lock = threading.Lock()

        def batch(evidence, session, **kwargs):
            with seen_lock:
                seen.extend(item.text for item in evidence)
            yield from self._accepting_batch(evidence, session, **kwargs)

        self._run(15, batch)
        self.assertEqual(len(seen), len(set(seen)))

    def test_validator_rejection_schedules_refill(self):
        batch_sizes = []
        sizes_lock = threading.Lock()

        def batch(evidence, session, **kwargs):
            metrics = kwargs["batch_metrics"]
            with sizes_lock:
                batch_sizes.append((len(evidence), metrics.refill))
            accepted = evidence
            if not metrics.refill and len(evidence) > 1:
                accepted = evidence[:-1]
                metrics.rejected_count += 1
                metrics.rejection_reasons["correct_answer_not_grounded"] += 1
            yield from self._accepting_batch(accepted, session, **kwargs)

        output = self._run(5, batch)
        self.assertEqual(len(output), 5)
        self.assertTrue(any(refill for _size, refill in batch_sizes))
        self.assertTrue(all(size <= 4 for size, refill in batch_sizes if refill))

    def test_fifteen_completes_with_high_rejection_rate(self):
        def batch(evidence, session, **kwargs):
            metrics = kwargs["batch_metrics"]
            accepted = evidence
            if not metrics.refill:
                accepted = evidence[:1]
                rejected = len(evidence) - len(accepted)
                metrics.rejected_count += rejected
                metrics.rejection_reasons["multiple_supported_options"] += rejected
            yield from self._accepting_batch(accepted, session, **kwargs)

        output = self._run(15, batch)
        self.assertEqual(len(output), 15)

    def test_zero_accept_refills_have_separate_failure_allowance(self):
        refill_calls = 0
        calls_lock = threading.Lock()

        def batch(evidence, session, **kwargs):
            nonlocal refill_calls
            metrics = kwargs["batch_metrics"]
            if not metrics.refill:
                accepted = evidence[:-1] if len(evidence) > 1 else evidence
                metrics.rejected_count += len(evidence) - len(accepted)
                yield from self._accepting_batch(accepted, session, **kwargs)
                return
            with calls_lock:
                refill_calls += 1
                current_call = refill_calls
            if current_call <= 2:
                metrics.rejected_count += len(evidence)
                metrics.rejection_reasons["exact_duplicate_question"] += len(evidence)
                return
            yield from self._accepting_batch(evidence, session, **kwargs)

        output = self._run(15, batch)
        self.assertEqual(len(output), 15)
        self.assertGreaterEqual(refill_calls, 3)

    def test_exact_duplicate_heavy_run_uses_fresh_evidence_and_completes(self):
        seen_evidence = set()
        repeated_evidence = []
        first_refills_to_reject = 2
        refill_calls = 0
        state_lock = threading.Lock()

        def batch(evidence, session, **kwargs):
            nonlocal refill_calls
            metrics = kwargs["batch_metrics"]
            with state_lock:
                for item in evidence:
                    if item.text in seen_evidence:
                        repeated_evidence.append(item.text)
                    seen_evidence.add(item.text)
                if metrics.refill:
                    refill_calls += 1
                    reject = refill_calls <= first_refills_to_reject
                else:
                    reject = len(evidence) > 1
            if reject:
                metrics.rejected_count += len(evidence)
                metrics.rejection_reasons["exact_duplicate_question"] += len(evidence)
                return
            yield from self._accepting_batch(evidence, session, **kwargs)

        output = self._run(15, batch)
        self.assertEqual(len(output), 15)
        self.assertEqual(repeated_evidence, [])

    def test_concurrency_never_exceeds_two(self):
        active = 0
        maximum = 0
        counter_lock = threading.Lock()

        def batch(evidence, session, **kwargs):
            nonlocal active, maximum
            with counter_lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.03)
            yield from self._accepting_batch(evidence, session, **kwargs)
            with counter_lock:
                active -= 1

        self._run(15, batch)
        self.assertEqual(maximum, service.MAX_LM_CONCURRENCY)

    def test_generator_yields_before_slow_batch_finishes(self):
        completed = threading.Event()

        def batch(evidence, session, **kwargs):
            if len(evidence) == 1:
                yield from self._accepting_batch(evidence, session, **kwargs)
                return
            time.sleep(0.15)
            yield from self._accepting_batch(evidence, session, **kwargs)
            completed.set()

        contexts = self._patch_pipeline(batch)
        with contexts[0], contexts[1], contexts[2], contexts[3]:
            generated = service.generate_production_quiz(
                "kaynak", 5, base_url="http://unused"
            )
            first = next(generated)
            self.assertFalse(completed.is_set())
            self.assertEqual(len([first, *generated]), 5)

    def test_refill_can_start_before_other_initial_batch_finishes(self):
        slow_initial_finished = threading.Event()
        refill_started_early = threading.Event()

        def batch(evidence, session, **kwargs):
            metrics = kwargs["batch_metrics"]
            if metrics.refill:
                if not slow_initial_finished.is_set():
                    refill_started_early.set()
                yield from self._accepting_batch(evidence, session, **kwargs)
                return
            if len(evidence) == 1:
                metrics.rejected_count += 1
                metrics.rejection_reasons["correct_answer_not_grounded"] += 1
                return
            time.sleep(0.12)
            yield from self._accepting_batch(evidence, session, **kwargs)
            slow_initial_finished.set()

        output = self._run(5, batch)
        self.assertEqual(len(output), 5)
        self.assertTrue(refill_started_early.is_set())

    def test_lm_error_is_controlled(self):
        def batch(_evidence, _session, **_kwargs):
            if False:
                yield None
            raise service.LMStudioError("LM Studio bağlantı hatası")

        with self.assertRaises(service.LMStudioError):
            self._run(5, batch)

    def test_exhausted_refill_does_not_promote_rejected_candidate(self):
        self.pool = self.pool[:5]

        def batch(evidence, session, **kwargs):
            accepted = evidence[:-1]
            metrics = kwargs["batch_metrics"]
            metrics.rejected_count += 1
            metrics.rejection_reasons["multiple_supported_options"] += 1
            yield from self._accepting_batch(accepted, session, **kwargs)

        with self.assertRaises(service.LMStudioError):
            self._run(5, batch)

    def test_remaining_one_survives_three_zero_refills_and_completes(self):
        refill_calls = 0

        def batch(evidence, session, **kwargs):
            nonlocal refill_calls
            metrics = kwargs["batch_metrics"]
            if not metrics.refill:
                accepted = [item for item in evidence if item.evidence_id != 15]
                if len(accepted) != len(evidence):
                    metrics.rejected_count += 1
                    metrics.rejection_reasons["multiple_supported_options"] += 1
                yield from self._accepting_batch(accepted, session, **kwargs)
                return
            refill_calls += 1
            self.assertEqual(len(evidence), 1)
            if refill_calls <= 3:
                metrics.rejected_count += 1
                metrics.rejection_reasons["exact_duplicate_question"] += 1
                return
            yield from self._accepting_batch(evidence, session, **kwargs)

        output = self._run(15, batch)
        self.assertEqual(len(output), 15)
        self.assertEqual(refill_calls, 4)

    def test_all_zero_refills_stop_when_dynamic_budget_is_exhausted(self):
        self.pool = [
            (index * 100, f"Geçerli ve tamamlanmış evidence metni {index}.", 3.0)
            for index in range(1, 101)
        ]
        refill_calls = 0
        calls_lock = threading.Lock()

        def batch(evidence, _session, **kwargs):
            nonlocal refill_calls
            metrics = kwargs["batch_metrics"]
            metrics.rejected_count += len(evidence)
            metrics.rejection_reasons["correct_answer_not_grounded"] += len(evidence)
            if metrics.refill:
                with calls_lock:
                    refill_calls += 1
            if False:
                yield None

        with self.assertRaises(service.LMStudioError):
            self._run(15, batch)
        self.assertEqual(refill_calls, service._refill_call_budget(15))

    def test_expired_deadline_prevents_refill_and_returns_controlled_error(self):
        refill_calls = 0

        def batch(evidence, _session, **kwargs):
            nonlocal refill_calls
            if kwargs["batch_metrics"].refill:
                refill_calls += 1
            if False:
                yield evidence

        with patch.object(service, "MIN_TOTAL_GENERATION_SECONDS", -1), patch.object(
            service, "GENERATION_SECONDS_PER_QUESTION", 0
        ), self.assertRaises(service.LMStudioError):
            self._run(15, batch)
        self.assertEqual(refill_calls, 0)


if __name__ == "__main__":
    unittest.main()
