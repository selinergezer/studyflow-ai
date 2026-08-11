"use client";

import { useEffect, useState } from "react";
import Button from "@/components/ui/Button";
import MarkdownSummary from "@/components/documents/MarkdownSummary";
import QuizPanel from "@/components/documents/QuizPanel";
import FlashcardStudy from "@/components/documents/FlashcardStudy";
import { apiFetch, type DocumentData, type Flashcard, type Quiz } from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

type Tab = "summary" | "quiz" | "flashcards";

export default function DocumentWorkspace({ documentId, initialTab = "summary" }: { documentId: string; initialTab?: Tab }) {
  const { t, language } = useLanguage();
  const [document, setDocument] = useState<DocumentData | null>(null);
  const [tab, setTab] = useState<Tab>(initialTab);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"quiz" | "flashcards" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [flashcardCount, setFlashcardCount] = useState(10);
  const [flashcards, setFlashcards] = useState<Flashcard[]>([]);
  const [activeFlashcards, setActiveFlashcards] = useState<Flashcard[] | null>(null);
  const [quizzes, setQuizzes] = useState<Quiz[]>([]);
  const [selectedQuiz, setSelectedQuiz] = useState<Quiz | null>(null);
  const [loadingQuizId, setLoadingQuizId] = useState<number | null>(null);

  useEffect(() => {
    apiFetch<DocumentData>(`/documents/${documentId}`).then(async (item) => {
      const normalized = { ...item, document_id: item.document_id ?? item.id };
      setDocument(normalized); localStorage.setItem("lastDocument", JSON.stringify(normalized));
      try {
        const quizItems = await apiFetch<Quiz[]>("/quizzes/");
        const documentQuizzes = quizItems.filter((quiz) => quiz.document_id === Number(documentId));
        const detailedQuizzes = await Promise.all(documentQuizzes.map(async (quiz) => {
          if (quiz.id == null) return quiz;
          try { const detail = await apiFetch<Quiz>(`/quizzes/${quiz.id}`); return { ...quiz, ...detail, question_count: detail.questions?.length ?? quiz.question_count }; }
          catch (cause) { console.error(cause); return quiz; }
        }));
        setQuizzes(detailedQuizzes);
      } catch (cause) {
        console.error(cause);
        if (initialTab === "quiz") setError(language === "tr" ? "Sınavlar şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin." : "Quizzes are currently unavailable. Please try again later.");
      }
      try {
        const cards = await apiFetch<Flashcard[]>(`/flashcards/?course_id=${item.course_id}`);
        setFlashcards(cards.filter((card) => card.document_id === Number(documentId)));
      } catch (cause) {
        console.error(cause);
        if (initialTab === "flashcards") setError(language === "tr" ? "Bilgi kartları şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin." : "Flashcards are currently unavailable. Please try again later.");
      }
    }).catch((cause) => { console.error(cause); setError(language === "tr" ? "Veriler şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin." : "Data is currently unavailable. Please try again later."); }).finally(() => setLoading(false));
  }, [documentId, initialTab]);

  async function openQuiz(quiz: Quiz) {
    const quizId = quiz.id ?? quiz.quiz_id;
    if (quizId == null) return;
    setError(null);
    if (quiz.questions?.length) { setSelectedQuiz({ ...quiz }); return; }
    setLoadingQuizId(quizId);
    try { setSelectedQuiz(await apiFetch<Quiz>(`/quizzes/${quizId}`)); }
    catch (cause) { console.error(cause); setError(language === "tr" ? "Sınav yüklenemedi. Lütfen tekrar deneyin." : "The quiz could not be loaded. Please try again."); }
    finally { setLoadingQuizId(null); }
  }

  function handleQuizCreated(created: Quiz) {
    const quizId = created.quiz_id ?? created.id;
    const normalized = { ...created, id: quizId, question_count: created.questions?.length ?? created.question_count };
    setQuizzes((current) => [...current.filter((quiz) => (quiz.id ?? quiz.quiz_id) !== quizId), normalized]);
    setSelectedQuiz(normalized);
  }

  function requestQuizDelete(event: React.MouseEvent, quiz: Quiz) {
    event.preventDefault(); event.stopPropagation();
    if (!window.confirm(language === "tr" ? "Bu sınavı silmek istediğinize emin misiniz?" : "Are you sure you want to delete this quiz?")) return;
    setError(language === "tr" ? "Sınav silme işlemi backend tarafından henüz desteklenmiyor." : "Quiz deletion is not supported by the backend yet.");
  }


  async function generateFlashcards() {
    if (!document) return; setBusy("flashcards"); setError(null);
    try { const data = await apiFetch<{ flashcards: Flashcard[] }>(`/flashcards/generate?course_id=${document.course_id}&document_id=${documentId}&flashcard_count=${flashcardCount}`, { method: "POST" }); setFlashcards((current) => [...current.filter((card) => !data.flashcards.some((created) => created.id === card.id)), ...data.flashcards]); setActiveFlashcards(data.flashcards); }
    catch (cause) { console.error(cause); setError(language === "tr" ? "Bilgi kartları şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin." : "Flashcards are currently unavailable. Please try again later."); }
    finally { setBusy(null); }
  }

  if (loading) return <div className="document-detail-page"><p className="document-detail-loading">{t("loading")}</p></div>;
  if (!document) return <div className="document-detail-page"><div className="document-detail-missing"><p>{error ?? (language === "tr" ? "Belge bilgisi bulunamadı." : "Document information was not found.")}</p></div></div>;
  const labels: Record<Tab, string> = { summary: t("summary"), quiz: t("quiz"), flashcards: t("flashcards") };

  return <div className="document-detail-page">
    <header className="document-detail-heading"><div className="document-detail-glow" aria-hidden="true" /><span className="document-pdf-icon">PDF</span><div><h1>{document.filename}</h1><p>{document.page_count} {t("pages")}</p></div></header>
    <div className="document-tabs" role="tablist" aria-label={t("documentTools")}>{(["summary", "quiz", "flashcards"] as Tab[]).map((item) => <button key={item} role="tab" aria-selected={tab === item} onClick={() => setTab(item)} className={tab === item ? "active" : ""}>{labels[item]}</button>)}</div>
    {error ? <p className="document-detail-error" role="alert">{error}</p> : null}
    <div className={`document-paper document-paper-${tab}`}>
      <span className="document-paper-tape" aria-hidden="true" />
      <span className="document-paper-holes" aria-hidden="true" />
      {tab === "summary" ? <article className="document-summary"><p className="document-content-label">{t("documentSummary")}</p><MarkdownSummary>{document.summary}</MarkdownSummary></article> : null}
      {tab === "quiz" ? <section className={`document-quiz-workspace ${selectedQuiz ? "is-solving" : ""}`}><div className="document-quiz-main">{selectedQuiz ? <button type="button" className="quiz-back-button" onClick={() => setSelectedQuiz(null)}>← {language === "tr" ? "Sınav listesine dön" : "Back to quiz list"}</button> : null}<QuizPanel key={selectedQuiz ? (selectedQuiz.id ?? selectedQuiz.quiz_id) : "new"} documentId={documentId} initialQuiz={selectedQuiz} onQuizCreated={handleQuizCreated} /></div><aside className="document-quiz-history"><p className="notebook-label">{language === "tr" ? "ÖNCEKİ SINAVLAR" : "PREVIOUS QUIZZES"}</p>{quizzes.length ? <div className="quiz-history-list">{quizzes.map((quiz, index) => { const quizId = quiz.id ?? quiz.quiz_id; const active = quizId != null && quizId === (selectedQuiz?.id ?? selectedQuiz?.quiz_id); return <article key={quizId ?? `${quiz.title}-${index}`} className={`quiz-history-card ${active ? "active" : ""}`}><span className="quiz-history-tape" aria-hidden="true" /><h3>{quiz.title || `${language === "tr" ? "Sınav" : "Quiz"} ${index + 1}`}</h3><p>{quiz.question_count ?? quiz.questions?.length ?? "—"} {language === "tr" ? "soru" : "questions"}</p><div><button type="button" disabled={loadingQuizId === quizId} onClick={() => openQuiz(quiz)}>{loadingQuizId === quizId ? (language === "tr" ? "Yükleniyor..." : "Loading...") : (language === "tr" ? "Tekrar Çöz →" : "Solve Again →")}</button><button type="button" className="quiz-history-delete" onClick={(event) => requestQuizDelete(event, quiz)} aria-label={language === "tr" ? "Sınavı sil" : "Delete quiz"} title={language === "tr" ? "Sil" : "Delete"}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" /></svg></button></div></article>; })}</div> : <div className="quiz-history-empty"><strong>{language === "tr" ? "Bu PDF için henüz sınav oluşturmadın." : "You haven't created a quiz for this PDF yet."}</strong><span>{language === "tr" ? "Soldaki ayarlardan ilk sınavını oluştur." : "Create your first quiz using the settings on the left."}</span></div>}</aside></section> : null}
      {tab === "flashcards" ? <section className={`document-flashcards-panel ${activeFlashcards ? "is-studying" : ""}`}>{activeFlashcards ? <><button type="button" className="flashcard-back-button" onClick={() => setActiveFlashcards(null)}>← {language === "tr" ? "Kart setlerine dön" : "Back to card sets"}</button><FlashcardStudy key={activeFlashcards.map((card) => card.id).join("-")} cards={activeFlashcards} onBack={() => setActiveFlashcards(null)} /></> : <div className="flashcard-library-layout"><div className="document-setup-panel"><p className="document-setup-kicker">{language === "tr" ? "KARTLARINI HAZIRLA" : "PREPARE YOUR CARDS"}</p><h2>{language === "tr" ? "Önemli kavramları tekrar et" : "Review the key concepts"}</h2><p className="document-setup-description">{language === "tr" ? "Bu materyalin temel noktalarından hızlı bir bilgi kartı koleksiyonu oluştur." : "Create a quick flashcard collection from the essential points in this material."}</p><fieldset><legend>{language === "tr" ? "Kart sayısı" : "Card count"}</legend><div className="document-choice-row">{[5, 10, 15, 20].map((count) => <button key={count} type="button" className={flashcardCount === count ? "active" : ""} aria-pressed={flashcardCount === count} onClick={() => setFlashcardCount(count)}>{count}</button>)}</div></fieldset><Button className="document-create-button" onClick={generateFlashcards} disabled={busy !== null}>{busy === "flashcards" ? (language === "tr" ? "Bilgi kartları hazırlanıyor..." : "Preparing flashcards...") : (language === "tr" ? "Bilgi Kartlarını Oluştur →" : "Create Flashcards →")}</Button></div><aside className="flashcard-history"><p className="notebook-label">{language === "tr" ? "ÖNCEKİ KARTLAR" : "PREVIOUS CARDS"}</p>{flashcards.length ? <article className="flashcard-history-card"><span className="flashcard-history-tape" aria-hidden="true" /><h3>{language === "tr" ? "Bu PDF'nin Kartları" : "Cards for This PDF"}</h3><p>{flashcards.length} {language === "tr" ? "kart" : "cards"}</p><button type="button" onClick={() => setActiveFlashcards(flashcards)}>{language === "tr" ? "Tekrar Çalış →" : "Study Again →"}</button></article> : <div className="quiz-history-empty"><strong>{language === "tr" ? "Bu PDF için henüz bilgi kartın yok." : "You don't have flashcards for this PDF yet."}</strong><span>{language === "tr" ? "Soldaki ayarlardan ilk kartlarını oluştur." : "Create your first cards using the settings on the left."}</span></div>}</aside></div>}</section> : null}
    </div>
  </div>;
}
