"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import Card from "@/components/ui/Card";
import Button from "@/components/ui/Button";
import {
  apiErrorMessage,
  apiFetch,
  isAbortError,
  type DocumentData,
  type Flashcard,
  type Quiz,
} from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

type FlashcardDocumentCard = {
  id: number;
  documentId: number;
  filename: string;
  pageCount: number;
  flashcardCount: number;
};

export default function ApiCollectionView({
  kind,
}: {
  kind: "quizzes" | "flashcards";
}) {
  const { t, language } = useLanguage();
  const router = useRouter();

  const quizMode = kind === "quizzes";

  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [quizzes, setQuizzes] = useState<Quiz[]>([]);
  const [flashcards, setFlashcards] = useState<Flashcard[]>([]);

  const [selectedDocumentId, setSelectedDocumentId] =
    useState<number | null>(null);

  const [loading, setLoading] = useState(true);
  const [deletingDocumentId, setDeletingDocumentId] = useState<number | null>(null);
  const [deletingQuizId, setDeletingQuizId] = useState<number | null>(null);
  const [showCreateQuiz, setShowCreateQuiz] = useState(false);
  const [questionCount, setQuestionCount] = useState(10);
  const [creatingQuiz, setCreatingQuiz] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    function handleError(cause: unknown) {
      if (isAbortError(cause)) return;

      setError(quizMode
        ? (language === "tr" ? "Sınavlar şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin." : "Quizzes are currently unavailable. Please try again later.")
        : (language === "tr" ? "Bilgi kartları şu anda yüklenemiyor." : "Flashcards are currently unavailable."));
    }

    if (quizMode) {
      Promise.all([
        apiFetch<Quiz[]>("/quizzes/", { signal: controller.signal }),
        apiFetch<DocumentData[]>("/documents/", { signal: controller.signal }),
      ])
        .then(([quizData, documentData]) => {
          const uniqueQuizzes = [
            ...new Map(
              quizData
                .filter((quiz) => quiz.id != null)
                .map((quiz) => [quiz.id as number, quiz])
            ).values(),
          ];

          setQuizzes(uniqueQuizzes);
          setDocuments(documentData);
          
          const requestedDocumentId = Number(new URLSearchParams(window.location.search).get("document_id"));
          if (Number.isInteger(requestedDocumentId) && documentData.some((document) => (document.id ?? document.document_id) === requestedDocumentId)) {
            setSelectedDocumentId(requestedDocumentId);
          }
        })
        .catch(handleError)
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });

      return () => controller.abort();
    }

    Promise.all([
      apiFetch<Flashcard[]>("/flashcards/", { signal: controller.signal }),
      apiFetch<DocumentData[]>("/documents/", { signal: controller.signal }),
    ])
      .then(([flashcardData, documentData]) => {
        setFlashcards(flashcardData);
        setDocuments(documentData);
      })
      .catch(handleError)
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [quizMode, language]);

  const quizDocuments = useMemo(() => {
    return documents
      .map((document) => {
        const documentId = document.id ?? document.document_id;

        if (documentId == null) return null;

        const documentQuizzes = quizzes.filter(
          (quiz) => quiz.document_id === documentId
        );

        return {
          id: documentId,
          filename: document.filename,
          pageCount: document.page_count,
          quizCount: documentQuizzes.length,
        };
      })
      .filter(Boolean) as Array<{
      id: number;
      filename: string;
      pageCount: number;
      quizCount: number;
    }>;
  }, [documents, quizzes]);

  const flashcardDocuments = useMemo(() => {
    return documents.map((document) => {
      const documentId = document.id ?? document.document_id;
      if (documentId == null) return null;
      return {
        id: documentId,
        documentId,
        filename: document.filename,
        pageCount: document.page_count,
        flashcardCount: flashcards.filter((card) => card.document_id === documentId).length,
      };
    }).filter(Boolean) as FlashcardDocumentCard[];
  }, [documents, flashcards]);

  const selectedDocument = documents.find(
    (document) =>
      (document.id ?? document.document_id) === selectedDocumentId
  );

  const selectedDocumentQuizzes = quizzes.filter(
    (quiz) => quiz.document_id === selectedDocumentId
  );

  function openQuiz(quiz: Quiz) {
    if (!quiz.id) return;
    router.push(`/quiz/${quiz.id}?document_id=${quiz.document_id}`);
  }

  async function createQuiz() {
    if (selectedDocumentId == null || creatingQuiz) return;
    setCreatingQuiz(true);
    setError(null);

    try {
      const created = await apiFetch<Quiz>(`/quizzes/generate?document_id=${selectedDocumentId}&question_count=${questionCount}`, { method: "POST" });
      const quizId = created.quiz_id ?? created.id;
      if (quizId == null) {
        setError("Sınav oluşturuldu ancak açılamadı.");
        return;
      }
      const normalized = { ...created, id: quizId };
      setQuizzes((current) => [...current, normalized]);
      setShowCreateQuiz(false);
      setQuestionCount(10);
      router.push(`/quiz/${quizId}?document_id=${selectedDocumentId}`);
    } catch {
      setError("Sınav oluşturulamadı. Lütfen tekrar deneyin.");
    } finally {
      setCreatingQuiz(false);
    }
  }

  async function deleteDocument(
  event: React.MouseEvent,
  documentId: number,
) {
  event.preventDefault();
  event.stopPropagation();

  const confirmed = window.confirm(
    language === "tr"
      ? "Bu PDF'yi ve bu PDF'ye ait sınavları silmek istediğinize emin misiniz?"
      : "Are you sure you want to delete this PDF and its quizzes?",
  );

  if (!confirmed) return;

  setDeletingDocumentId(documentId);
  setError(null);

  try {
    await apiFetch(`/documents/${documentId}`, {
      method: "DELETE",
    });

    // PDF'yi ekrandan kaldır
    setDocuments((current) =>
      current.filter(
        (document) =>
          (document.id ?? document.document_id) !== documentId,
      ),
    );

    // PDF'ye ait sınavları da ekrandan kaldır
    setQuizzes((current) =>
      current.filter(
        (quiz) => quiz.document_id !== documentId,
      ),
    );

    // Flashcard sayfasında da aynı component kullanılıyorsa
    setFlashcards((current) =>
      current.filter(
        (flashcard) => flashcard.document_id !== documentId,
      ),
    );
  } catch (cause) {
    setError(
      apiErrorMessage(
        cause,
        language === "tr"
          ? "PDF silinirken bir hata oluştu."
          : "An error occurred while deleting the PDF.",
      ),
    );
  } finally {
    setDeletingDocumentId(null);
  }
}

  async function deleteQuiz(
    event: React.MouseEvent,
    quizId: number,
  ) {
    event.preventDefault();
    event.stopPropagation();

    const confirmed = window.confirm(
      language === "tr"
        ? "Bu sınavı silmek istediğinize emin misiniz?"
        : "Are you sure you want to delete this quiz?",
    );

    if (!confirmed) return;

    setDeletingQuizId(quizId);
    setError(null);

    try {
      await apiFetch(`/quizzes/${quizId}`, {
        method: "DELETE",
      });

      setQuizzes((current) =>
        current.filter(
          (quiz) =>
            (quiz.id ?? quiz.quiz_id) !== quizId,
        ),
      );
    } catch (cause) {
      setError(
        apiErrorMessage(
          cause,
          language === "tr"
            ? "Sınav silinemedi."
            : "The quiz could not be deleted.",
        ),
      );
    } finally {
      setDeletingQuizId(null);
    }
  }

  async function deleteFlashcardSet(event: React.MouseEvent, documentId: number) {
    event.preventDefault();
    event.stopPropagation();
    if (!window.confirm("Bu belge için oluşturulan bilgi kartlarını silmek istediğinize emin misiniz?")) return;

    const cards = flashcards.filter((flashcard) => flashcard.document_id === documentId);
    setDeletingDocumentId(documentId);
    setError(null);
    const deletedIds: number[] = [];

    try {
      for (const card of cards) {
        await apiFetch(`/flashcards/${card.id}`, { method: "DELETE" });
        deletedIds.push(card.id);
      }
    } catch (cause) {
      setError(apiErrorMessage(cause, "Bilgi kartları silinirken bir hata oluştu."));
    } finally {
      if (deletedIds.length) {
        setFlashcards((current) => current.filter((card) => !deletedIds.includes(card.id)));
      }
      setDeletingDocumentId(null);
    }
  }

  if (loading) {
    return (
      <div className={quizMode ? "quizzes-page" : "flashcards-page"}>
        <p className={quizMode ? "quizzes-loading" : "flashcards-loading"}>{t("loading")}</p>
      </div>
    );
  }

  if (quizMode && selectedDocumentId === null) {
    return <div className="quizzes-page">
      <header className="quizzes-heading">
        <div className="quizzes-glow" aria-hidden="true" />
        <div><p className="quizzes-eyebrow">{t("practice")}</p><h1>{t("quizzesTitle")}</h1><p className="quizzes-subtitle">{t("quizzesIntro")}</p></div>
        <Link href="/library?action=quiz" className="quizzes-primary-button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M12 5v14M5 12h14"/></svg>{t("createQuizLower")}</Link>
      </header>

      {error ? <p className="quizzes-error" role="alert">{error}</p> : null}
      {quizDocuments.length ? <div className="quizzes-grid">{quizDocuments.map((document) => <article key={document.id} className="quizzes-document-card" role="link" tabIndex={0} onClick={() => router.push(`/documents/${document.id}?tab=quiz`)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") router.push(`/documents/${document.id}?tab=quiz`); }}>
        <span className="quizzes-card-flag" aria-hidden="true" />
        <button
  type="button"
  disabled={deletingDocumentId === document.id}
  onClick={(event) =>
    deleteDocument(event, document.id)
  }
  className="flashcards-delete quizzes-delete"
  aria-label={
    language === "tr"
      ? `${document.filename} dosyasını sil`
      : `Delete ${document.filename}`
  }
  title={language === "tr" ? "Sil" : "Delete"}
>
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.8"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M4 7h16" />
    <path d="M9 7V4h6v3" />
    <path d="m18 7-1 13H7L6 7" />
    <path d="M10 11v5" />
    <path d="M14 11v5" />
  </svg>
</button>
        <span className="quizzes-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg></span>
        <h2>{document.filename}</h2>
        <span className="quizzes-card-rule" aria-hidden="true" />
        <div className="quizzes-card-stats"><span><b>{document.pageCount}</b><small>{t("pages")}</small></span><span><b>{document.quizCount}</b><small>{t("quizzes")}</small></span><button type="button" onClick={(event) => { event.preventDefault(); event.stopPropagation(); router.push(`/documents/${document.id}?tab=quiz`); }}>{t("createQuizLower")}</button></div>
      </article>)}</div> : <div className="quizzes-empty"><p>{language === "tr" ? "Henüz sınav oluşturabileceğin bir materyal yok." : "You don't have material available for a quiz yet."}</p><span>{language === "tr" ? "Önce kütüphanene bir PDF ekle." : "Add a PDF to your library first."}</span><Link href="/upload">{t("addMaterial")} →</Link></div>}
    </div>;
  }

  /*
   * PDF'NİN ESKİ SINAVLARI
   */
  if (quizMode && selectedDocumentId !== null) {
    return (
      <div className="mx-auto max-w-5xl px-5 py-12 sm:px-8 sm:py-16">
        <button
          type="button"
          onClick={() => setSelectedDocumentId(null)}
          className="text-sm font-medium text-blue-600"
        >
          ← PDF&apos;lere dön
        </button>

        <div className="mt-5 flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-3xl font-semibold text-gray-950">{selectedDocument?.filename}</h1>
            <p className="mt-2 text-sm text-gray-500">Daha önce oluşturduğun sınavlar</p>
          </div>
            <Button
  className="shrink-0 self-start"
  onClick={() => {
    setError(null);
    setQuestionCount(10);
    setShowCreateQuiz(true);
  }}
>
            <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
            Yeni Sınav Oluştur
          </Button>
        </div>

        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          {selectedDocumentQuizzes.map((quiz, index) => (
            <Card key={quiz.id} onClick={() => openQuiz(quiz)} className="relative h-full cursor-pointer p-5 pr-16 text-left transition hover:bg-gray-50" role="button" tabIndex={0} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") openQuiz(quiz); }}>
                {quiz.id != null ? <button type="button" disabled={deletingQuizId === quiz.id} onClick={(event) => deleteQuiz(event, quiz.id as number)} className="absolute right-4 top-4 inline-flex size-8 items-center justify-center rounded-lg text-red-600 transition hover:bg-red-50 disabled:opacity-50" aria-label={`Sınav ${index + 1} sil`} title="Sil"><svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" /></svg></button> : null}
                <h2 className="font-medium text-gray-950">
                  Sınav {index + 1}
                </h2>

                <p className="mt-2 text-sm text-gray-500">
                  {quiz.question_count ?? "—"} soru
                </p>

                <p className="mt-3 text-sm font-medium text-blue-600">
                  Görüntüle →
                </p>
            </Card>
          ))}
        </div>

        {showCreateQuiz ? <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/50 p-4" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target && !creatingQuiz) setShowCreateQuiz(false); }}>
          <Card className="w-full max-w-md p-6" role="dialog" aria-modal="true" aria-labelledby="create-quiz-title">
            <h2 id="create-quiz-title" className="text-lg font-semibold text-gray-950">Yeni Sınav Oluştur</h2>
            <p className="mt-2 truncate text-sm text-gray-500">{selectedDocument?.filename}</p>
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <label className="text-sm font-medium text-gray-700">Soru sayısı<select value={questionCount} disabled={creatingQuiz} onChange={(event) => setQuestionCount(Number(event.target.value))} className="mt-2 block h-11 w-full rounded-xl border border-gray-200 bg-white px-3 text-gray-900"><option value={5}>5</option><option value={10}>10</option><option value={15}>15</option></select></label>
            </div>
            {error ? <p className="mt-4 text-sm text-red-600" role="alert">{error}</p> : null}
            <div className="mt-6 flex justify-end gap-3"><Button variant="secondary" disabled={creatingQuiz} onClick={() => setShowCreateQuiz(false)}>İptal</Button><Button disabled={creatingQuiz} onClick={createQuiz}>{creatingQuiz ? "Sınav hazırlanıyor..." : "Sınavı Oluştur"}</Button></div>
          </Card>
        </div> : null}
      </div>
    );
  }

  return (
    <div className="flashcards-page">
      <header className="flashcards-heading">
        <div className="flashcards-glow" aria-hidden="true" />
        <div><p className="flashcards-eyebrow">{t("review")}</p><h1>{t("flashcardsTitle")}</h1><p className="flashcards-subtitle">{language === "tr" ? "Materyallerinden oluşturduğun kartlarla temel kavramları hızlıca tekrar et." : "Quickly review key concepts with cards created from your materials."}</p></div>
        <Link href="/library?action=flashcards" className="flashcards-primary-button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M12 5v14M5 12h14" /></svg>{t("generateFlashcards")}</Link>
      </header>
      {error ? <p className="flashcards-error" role="alert">{error}</p> : null}
      {flashcardDocuments.length ? <div className="flashcards-grid">{flashcardDocuments.map((document) => <article key={document.id} className="flashcards-document-card">
        <span className="flashcards-card-flag" aria-hidden="true" />
        <span className="flashcards-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="4" y="5" width="16" height="14" rx="2"/><path d="M8 9h8M8 13h5"/></svg></span>
        {document.flashcardCount > 0 ? <button type="button" disabled={deletingDocumentId === document.documentId} onClick={(event) => deleteFlashcardSet(event, document.documentId)} className="flashcards-delete" aria-label={`${document.filename} bilgi kartlarını sil`} title="Sil"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" /></svg></button> : null}
        <h2>{document.filename}</h2><span className="flashcards-card-rule" aria-hidden="true" />
        <div className="flashcards-stats"><span><b>{document.pageCount}</b><small>{t("pages")}</small></span><span><b>{document.flashcardCount}</b><small>{language === "tr" ? "Kart" : "Cards"}</small></span></div>
        <div className="flashcards-actions"><Link href={`/documents/${document.documentId}?tab=flashcards`}>{language === "tr" ? "Görüntüle" : "View"}</Link><Link href={`/documents/${document.documentId}?tab=flashcards`}>{document.flashcardCount ? (language === "tr" ? "Yeni kart oluştur" : "Create new card") : t("generateFlashcards")}</Link></div>
      </article>)}</div> : <div className="flashcards-empty"><p>{language === "tr" ? "Henüz bilgi kartı oluşturabileceğin bir materyal yok." : "You don't have material available for flashcards yet."}</p><span>{language === "tr" ? "Önce kütüphanene bir PDF ekle." : "Add a PDF to your library first."}</span><Link href="/upload">{t("addMaterial")} →</Link></div>}
    </div>
  );
}
