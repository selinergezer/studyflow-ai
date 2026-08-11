"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
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
  const completedCount = finished ? cards.length : currentIndex;
  const progress = Math.round((completedCount / cards.length) * 100);
  const score = cards.length ? Math.round((correctCount / cards.length) * 100) : 0;

  async function recordResult(correct: boolean) {
    if (!card || saving) return;
    setSaving(true);
    setError(null);
    try {
      await apiFetch(`/flashcards/${card.id}/review`, {
        method: "POST",
        body: JSON.stringify({ result: correct ? "easy" : "forgot" }),
      });
      if (correct) setCorrectCount((value) => value + 1);
      else setWrongCount((value) => value + 1);

      if (currentIndex === cards.length - 1) {
        setFinished(true);
      } else {
        setCurrentIndex((value) => value + 1);
        setIsFlipped(false);
      }
    } catch (cause) {
      console.error(cause);
      setError(tr ? "Veriler şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin." : "Data is currently unavailable. Please try again later.");
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

  if (finished) {
    return <div className="flashcard-study flashcard-study-finished mx-auto mt-8 max-w-xl rounded-3xl bg-gray-50 p-8 text-center ring-1 ring-gray-200 sm:p-10">
      <span className="mx-auto flex size-12 items-center justify-center rounded-2xl bg-green-50 text-green-600" aria-hidden="true">✓</span>
      <h2 className="mt-5 text-xl font-semibold tracking-[-0.025em] text-gray-950">{tr ? "Çalışma Tamamlandı" : "Study Complete"}</h2>
      <p className="mt-3 text-sm text-gray-500">{cards.length} {tr ? "Kart" : "Cards"}</p>
      <div className="mx-auto mt-6 grid max-w-sm grid-cols-2 gap-3">
        <div className="rounded-2xl bg-white p-4 ring-1 ring-gray-200"><p className="text-lg font-semibold text-green-600">✓ {correctCount}</p><p className="mt-1 text-xs text-gray-500">{tr ? "Doğru" : "Correct"}</p></div>
        <div className="rounded-2xl bg-white p-4 ring-1 ring-gray-200"><p className="text-lg font-semibold text-red-600">✕ {wrongCount}</p><p className="mt-1 text-xs text-gray-500">{tr ? "Yanlış" : "Wrong"}</p></div>
      </div>
      <p className="mt-6 font-medium text-gray-950">{tr ? "Başarı" : "Score"}: %{score}</p>
      <div className="flashcard-finished-actions"><Button onClick={restart}>{tr ? "Aynı Kartları Tekrar Çalış" : "Study the Same Cards Again"}</Button>{onBack ? <Button variant="secondary" onClick={onBack}>{tr ? "Kart Setlerine Dön" : "Back to Card Sets"}</Button> : null}</div>
    </div>;
  }

  return <div className="flashcard-study mx-auto mt-8 max-w-2xl">
    <div className="flex items-end justify-between gap-4">
      <div><p className="text-sm font-medium text-gray-950">{tr ? "Kart" : "Card"} {currentIndex + 1} / {cards.length}</p><p className="mt-1 text-xs text-gray-500"><span className="text-green-600">✓ {correctCount} {tr ? "Doğru" : "Correct"}</span><span className="mx-2">·</span><span className="text-red-600">✕ {wrongCount} {tr ? "Yanlış" : "Wrong"}</span></p></div>
      <span className="text-xs font-medium text-gray-500">%{progress}</span>
    </div>
    <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-gray-100" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><div className="h-full rounded-full bg-blue-600 transition-[width] duration-500" style={{ width: `${progress}%` }} /></div>

    <button type="button" onClick={() => setIsFlipped((value) => !value)} className="mt-6 block h-80 w-full [perspective:1200px] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-blue-600" aria-label={isFlipped ? (tr ? "Soruyu göster" : "Show question") : (tr ? "Cevabı göster" : "Show answer")}>
      <span className={`relative block size-full transition-transform duration-500 [transform-style:preserve-3d] ${isFlipped ? "[transform:rotateY(180deg)]" : ""}`}>
        <span className="absolute inset-0 flex flex-col items-center justify-center rounded-3xl border border-gray-200 bg-white p-7 text-center shadow-sm [backface-visibility:hidden] sm:p-10">
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-blue-600">{tr ? "Soru" : "Question"}</span>
          <span className="mt-7 text-lg font-medium leading-8 text-gray-950 sm:text-xl">{card.question}</span>
          <span className="mt-8 text-xs text-gray-400">{tr ? "Cevabı görmek için karta tıkla" : "Click the card to see the answer"}</span>
        </span>
        <span className="absolute inset-0 flex flex-col items-center justify-center rounded-3xl border border-blue-200 bg-blue-50 p-7 text-center shadow-sm [backface-visibility:hidden] [transform:rotateY(180deg)] sm:p-10">
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-blue-600">{tr ? "Cevap" : "Answer"}</span>
          <span className="mt-7 text-lg font-medium leading-8 text-gray-950 sm:text-xl">{card.answer}</span>
        </span>
      </span>
    </button>

    {error ? <p className="mt-4 text-center text-sm text-red-600" role="alert">{error}</p> : null}
    {isFlipped ? <div className="mt-6 grid gap-3 sm:grid-cols-2"><Button variant="secondary" className="border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700" disabled={saving} onClick={() => recordResult(false)}>✕ {tr ? "Yanlış Bildim" : "I Got It Wrong"}</Button><Button className="bg-green-600 hover:bg-green-700 focus-visible:outline-green-600" disabled={saving} onClick={() => recordResult(true)}>✓ {tr ? "Doğru Bildim" : "I Got It Right"}</Button></div> : null}
  </div>;
}
