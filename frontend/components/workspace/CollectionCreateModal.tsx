"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { apiErrorMessage, apiFetch, isAbortError, type DocumentData, type Flashcard, type Quiz } from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

type CreateKind = "quiz" | "flashcards";
type FlashcardGenerationResponse = { document_id: number; flashcards: Flashcard[] };

export default function CollectionCreateModal({ kind, open, onClose, initialDocumentId }: { kind: CreateKind; open: boolean; onClose: () => void; initialDocumentId?: number }) {
  const router = useRouter();
  const { language, t } = useLanguage();
  const tr = language === "tr";
  const quizMode = kind === "quiz";
  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [documentId, setDocumentId] = useState("");
  const [itemCount, setItemCount] = useState(10);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      setDocumentId(initialDocumentId ? String(initialDocumentId) : "");
      setItemCount(10);
      setError(null);
      setLoading(true);
      apiFetch<DocumentData[]>("/documents/", { signal: controller.signal })
        .then(setDocuments)
        .catch((cause) => { if (!isAbortError(cause)) setError(apiErrorMessage(cause, tr ? "Belgeler yüklenemedi." : "Documents could not be loaded.")); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    });
    return () => controller.abort();
  }, [initialDocumentId, open, tr]);

  useEffect(() => {
    if (!open || creating) return;
    function closeOnEscape(event: KeyboardEvent) { if (event.key === "Escape") onClose(); }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [creating, onClose, open]);

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    const previousPaddingRight = document.body.style.paddingRight;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.overflow = "hidden";
    if (scrollbarWidth > 0) document.body.style.paddingRight = `${scrollbarWidth}px`;
    return () => {
      document.body.style.overflow = previousOverflow;
      document.body.style.paddingRight = previousPaddingRight;
    };
  }, [open]);

  const selectedDocument = useMemo(() => documents.find((document) => String(document.id ?? document.document_id) === documentId), [documentId, documents]);

  async function create() {
    if (!selectedDocument || creating) return;
    const selectedId = selectedDocument.id ?? selectedDocument.document_id;
    if (selectedId == null) return;
    setCreating(true);
    setError(null);
    try {
      if (quizMode) {
        const created = await apiFetch<Quiz>(`/quizzes/generate?document_id=${selectedId}&question_count=${itemCount}`, { method: "POST" });
        const quizId = created.quiz_id ?? created.id;
        if (quizId == null) throw new Error("Quiz id missing");
        router.push(`/quiz/${quizId}?document_id=${created.document_id ?? selectedId}`);
      } else {
        const created = await apiFetch<FlashcardGenerationResponse>(`/flashcards/generate?course_id=${selectedDocument.course_id}&document_id=${selectedId}&flashcard_count=${itemCount}`, { method: "POST" });
        const firstCard = created.flashcards[0];
        if (!firstCard?.id) throw new Error("Flashcard set missing");
        router.push(`/documents/${created.document_id}?tab=flashcards&flashcard_id=${firstCard.id}`);
      }
    } catch (cause) {
      if (isAbortError(cause)) return;
      setError(apiErrorMessage(cause, tr ? (quizMode ? "Sınav oluşturulamadı." : "Bilgi kartları oluşturulamadı.") : (quizMode ? "The quiz could not be created." : "The flashcards could not be created.")));
      setCreating(false);
    }
  }

  if (!open) return null;

  return createPortal(
    <div className="collection-create-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !creating) onClose(); }}>
      <section className="collection-create-modal" role="dialog" aria-modal="true" aria-labelledby={`create-${kind}-title`}>
        <header><div><p>{quizMode ? "SINAVLAR" : "BİLGİ KARTLARI"}</p><h2 id={`create-${kind}-title`}>{quizMode ? "Yeni Sınav Oluştur" : "Bilgi Kartları Oluştur"}</h2></div><button type="button" disabled={creating} onClick={onClose} aria-label={t("close")}>×</button></header>
        {creating ? <div className="collection-modal-progress" role="status"><span className="collection-generation-spinner" aria-hidden="true" /><strong>{quizMode ? "Sınav hazırlanıyor..." : "Bilgi kartları hazırlanıyor..."}</strong><small>{selectedDocument?.filename}</small></div> : <>
          <label className="collection-create-field"><span>Belge seç</span><select value={documentId} disabled={loading} onChange={(event) => setDocumentId(event.target.value)}><option value="">{loading ? "Belgeler yükleniyor..." : "Bir PDF belgesi seçin"}</option>{documents.map((document) => { const id = document.id ?? document.document_id; return id == null ? null : <option key={id} value={id}>{document.filename}</option>; })}</select></label>
          <fieldset className="collection-create-count"><legend>{quizMode ? "Soru sayısı" : "Kart sayısı"}</legend><div>{[5,10,15].map((count) => <button key={count} type="button" className={itemCount === count ? "active" : ""} onClick={() => setItemCount(count)}>{count}</button>)}</div></fieldset>
        </>}
        {error ? <p className="collection-create-error" role="alert">{error}</p> : null}
        {!creating ? <footer><button type="button" onClick={onClose}>İptal</button><button type="button" disabled={!documentId || loading} onClick={create}>{quizMode ? "Sınavı Oluştur →" : "Bilgi Kartlarını Oluştur →"}</button></footer> : null}
      </section>
    </div>,
    document.body,
  );
}
