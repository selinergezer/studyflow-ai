"use client";

import { useState } from "react";
import { apiFetch, type Flashcard } from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

export default function FlashcardStudy({ cards, onBack }: { cards: Flashcard[]; onBack?: () => void }) {
  const { language } = useLanguage();
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [correctCount, setCorrectCount] = useState(0);
  const [wrongCount, setWrongCount] = useState(0);
  const [finished, setFinished] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tr = language === "tr";
  const card = cards[currentIndex];
  const progress = cards.length ? Math.round(((finished ? cards.length : currentIndex + 1) / cards.length) * 100) : 0;
  const score = cards.length ? Math.round((correctCount / cards.length) * 100) : 0;

  async function recordResult(correct: boolean) {
    if (!card || saving || !isFlipped) return;
    setSaving(true);
    setError(null);
    try {
      await apiFetch(`/flashcards/${card.id}/review`, {
        method: "POST",
        body: JSON.stringify({ result: correct ? "easy" : "forgot" }),
      });
      if (correct) setCorrectCount((value) => value + 1);
      else setWrongCount((value) => value + 1);

      if (currentIndex === cards.length - 1) setFinished(true);
      else {
        setCurrentIndex((value) => value + 1);
        setIsFlipped(false);
      }
    } catch {
      setError(tr ? "Sonuç kaydedilemedi. Lütfen tekrar deneyin." : "The result could not be saved. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  function restart() {
    setCurrentIndex(0);
    setIsFlipped(false);
    setCorrectCount(0);
    setWrongCount(0);
    setFinished(false);
    setError(null);
  }

  if (!cards.length) return <div className="flashcard-workspace-empty">{tr ? "Bu sette çalışılacak kart yok." : "There are no cards to study in this set."}</div>;

  if (finished) {
    return <section className="flashcard-session flashcard-session--finished">
      <div className="flashcard-result-icon" aria-hidden="true">✓</div>
      <p className="flashcard-session-kicker">{tr ? "KART SETİ TAMAMLANDI" : "CARD SET COMPLETE"}</p>
      <h2>{tr ? "Çalışma tamamlandı" : "Study complete"}</h2>
      <p className="flashcard-result-description">{cards.length} {tr ? "kartı tamamladın." : "cards completed."}</p>
      <div className="flashcard-result-stats">
        <div className="correct"><strong>✓ {correctCount}</strong><span>{tr ? "Doğru" : "Correct"}</span></div>
        <div className="wrong"><strong>× {wrongCount}</strong><span>{tr ? "Yanlış" : "Wrong"}</span></div>
        <div><strong>%{score}</strong><span>{tr ? "Başarı" : "Score"}</span></div>
      </div>
      <div className="flashcard-result-actions">
        <button type="button" className="primary" onClick={restart}>{tr ? "Tekrar Çalış" : "Study Again"}</button>
        {onBack ? <button type="button" onClick={onBack}>{tr ? "Kart Setlerine Dön" : "Back to Card Sets"}</button> : null}
      </div>
    </section>;
  }

  return <section className="flashcard-session">
    <header className="flashcard-session-status">
      <div className="flashcard-session-count"><span aria-hidden="true">▤</span><strong>{tr ? "Kart" : "Card"} {currentIndex + 1} / {cards.length}</strong></div>
      <div className="flashcard-session-score correct"><span>✓</span>{tr ? "Doğru" : "Correct"} <strong>{correctCount}</strong></div>
      <div className="flashcard-session-score wrong"><span>×</span>{tr ? "Yanlış" : "Wrong"} <strong>{wrongCount}</strong></div>
      <div className="flashcard-session-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}>
        <div><i style={{ width: `${progress}%` }} /></div><span>%{progress}</span>
      </div>
    </header>

    <div className="flashcard-stage">
      <button type="button" className="flashcard-flip-button" onClick={() => setIsFlipped((value) => !value)} aria-label={isFlipped ? (tr ? "Soruyu göster" : "Show question") : (tr ? "Cevabı göster" : "Show answer")}>
        <span className={`flashcard-flip-inner ${isFlipped ? "is-flipped" : ""}`}>
          <span className="flashcard-face flashcard-face--front">
            <small>{tr ? "SORU" : "QUESTION"}</small>
            <strong>{card.question}</strong>
            <em>☝ {tr ? "Kartı çevirmek için tıkla" : "Click to flip the card"}</em>
          </span>
          <span className="flashcard-face flashcard-face--back">
            <small>{tr ? "CEVAP" : "ANSWER"}</small>
            <strong>{card.answer}</strong>
            <em>↶ {tr ? "Soruya dönmek için tıkla" : "Click to return to the question"}</em>
          </span>
        </span>
      </button>

      <div className={`flashcard-review-actions ${isFlipped ? "is-visible" : ""}`} aria-hidden={!isFlipped}>
        <div><span>{tr ? "Bilmiyorsan" : "If you don't know"}</span><button type="button" className="wrong" disabled={saving || !isFlipped} onClick={() => void recordResult(false)} aria-label={tr ? "Yanlış bildim" : "I got it wrong"}>×</button></div>
        <div><span>{tr ? "Biliyorsan" : "If you know"}</span><button type="button" className="correct" disabled={saving || !isFlipped} onClick={() => void recordResult(true)} aria-label={tr ? "Doğru bildim" : "I got it right"}>✓</button></div>
      </div>
      {error ? <p className="flashcard-session-error" role="alert">{error}</p> : null}
    </div>
  </section>;
}
