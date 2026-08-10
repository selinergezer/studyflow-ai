"use client";

import { useEffect, useState } from "react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import MarkdownSummary from "@/components/documents/MarkdownSummary";
import QuizPanel from "@/components/documents/QuizPanel";
import FlashcardStudy from "@/components/documents/FlashcardStudy";
import { apiFetch, type DocumentData, type Flashcard } from "@/lib/api";
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

  useEffect(() => {
    apiFetch<DocumentData>(`/documents/${documentId}`).then((item) => {
      const normalized = { ...item, document_id: item.document_id ?? item.id };
      setDocument(normalized); localStorage.setItem("lastDocument", JSON.stringify(normalized));
    }).catch((cause) => { console.error(cause); setError(cause instanceof Error ? cause.message : "İşlem sırasında bir hata oluştu."); }).finally(() => setLoading(false));
  }, [documentId]);


  async function generateFlashcards() {
    if (!document) return; setBusy("flashcards"); setError(null);
    try { const data = await apiFetch<{ flashcards: Flashcard[] }>(`/flashcards/generate?course_id=${document.course_id}&document_id=${documentId}&flashcard_count=${flashcardCount}`, { method: "POST" }); setFlashcards(data.flashcards); }
    catch (cause) { console.error(cause); setError(cause instanceof Error ? cause.message : "İşlem sırasında bir hata oluştu."); }
    finally { setBusy(null); }
  }

  if (loading) return <div className="mx-auto max-w-5xl px-5 py-14 text-sm text-gray-500">Yükleniyor...</div>;
  if (!document) return <div className="mx-auto max-w-5xl px-5 py-14"><Card className="p-6"><p className="text-sm text-gray-500">{error ?? "Belge bilgisi bulunamadı."}</p></Card></div>;
  const labels: Record<Tab, string> = { summary: t("summary"), quiz: t("quiz"), flashcards: t("flashcards") };

  return <div className="mx-auto max-w-5xl px-5 py-10 sm:px-8 sm:py-14">
    <header className="flex items-start gap-4"><span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-red-50 text-red-600">PDF</span><div><h1 className="text-2xl font-semibold text-gray-950 sm:text-3xl">{document.filename}</h1><p className="mt-2 text-xs text-gray-400">{document.page_count} {t("pages")}</p></div></header>
    <div className="mt-9 flex gap-6 border-b border-gray-200">{(["summary", "quiz", "flashcards"] as Tab[]).map((item) => <button key={item} onClick={() => setTab(item)} className={`pb-3 text-sm ${tab === item ? "border-b-2 border-blue-600 font-medium text-gray-950" : "text-gray-500"}`}>{labels[item]}</button>)}</div>
    {error ? <p className="mt-5 text-sm text-red-600" role="alert">{error}</p> : null}
    <Card className="mt-7 min-h-[390px] p-6 sm:p-8">
      {tab === "summary" ? <article className="max-w-3xl"><p className="text-xs font-medium uppercase tracking-[0.14em] text-gray-400">{t("documentSummary")}</p><MarkdownSummary>{document.summary}</MarkdownSummary></article> : null}
      {tab === "quiz" ? <QuizPanel documentId={documentId} /> : null}
      {tab === "flashcards" ? <section><div className="flex flex-wrap items-end gap-3"><label className="text-sm text-gray-700">{language === "tr" ? "Kart sayısı" : "Card count"}<select value={flashcardCount} onChange={(e) => setFlashcardCount(Number(e.target.value))} className="mt-2 block h-11 rounded-xl border border-gray-200 bg-white px-3"><option>5</option><option>10</option><option>20</option><option>30</option></select></label><Button onClick={generateFlashcards} disabled={busy !== null}>{busy === "flashcards" ? "Bilgi kartları oluşturuluyor..." : t("generateFlashcards")}</Button></div>{flashcards.length ? <FlashcardStudy key={flashcards.map((card) => card.id).join("-")} cards={flashcards} /> : null}</section> : null}
    </Card>
  </div>;
}
