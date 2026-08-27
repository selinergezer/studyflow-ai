"use client";

import { useEffect, useMemo, useRef, useState } from "react";
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

function CollectionArtwork({ kind }: { kind: "quizzes" | "flashcards" }) {
  return kind === "quizzes" ? <svg className="collection-artwork quiz-artwork" viewBox="0 0 390 220" fill="none" aria-hidden="true">
    <circle cx="40" cy="54" r="5" className="quiz-art-dot"/><circle cx="344" cy="155" r="5" className="quiz-art-dot"/><path d="M20 117l10-14 8 9 14-20" className="quiz-art-squiggle"/>
    <g className="quiz-art-donut" transform="rotate(-8 105 60)"><rect x="61" y="17" width="88" height="82" rx="17"/><circle cx="105" cy="57" r="24"/><path d="M105 33a24 24 0 0 1 23 17L105 57V33Z"/><path d="M105 57 89 75a24 24 0 0 1-8-18h24Z"/></g>
    <g className="quiz-art-bars" transform="rotate(-7 82 150)"><rect x="45" y="108" width="82" height="78" rx="13"/><path d="M64 166v-25h10v25M84 166v-39h10v39M104 166v-53h10v53"/></g>
    <g className="quiz-art-paper" transform="rotate(7 210 112)"><rect x="142" y="29" width="148" height="170" rx="17"/><path d="M175 62h72M173 79h91M170 108h70M168 126h87M165 155h77"/><circle cx="158" cy="75" r="9"/><path d="m154 75 4 4 7-9"/><circle cx="155" cy="110" r="9"/><circle cx="151" cy="146" r="9"/></g>
    <g className="quiz-art-pencil" transform="rotate(8 300 115)"><path d="m261 171 76-113 15 10-79 111-19 9 7-17Z"/><path d="m337 58 7-11 15 10-7 11"/><path d="m254 188 7-17 12 8-19 9Z"/></g>
  </svg> : <svg className="collection-artwork" viewBox="0 0 320 190" fill="none" aria-hidden="true"><rect className="collection-card-back" x="75" y="48" width="154" height="103" rx="17" transform="rotate(-9 75 48)"/><rect className="collection-card-front" x="103" y="30" width="154" height="105" rx="17" transform="rotate(7 103 30)"/><path d="M142 74h74M142 92h49"/><circle cx="220" cy="112" r="15"/><path d="M220 105v9M220 120h.01" strokeLinecap="round"/></svg>;
}

export default function ApiCollectionView({
  kind,
}: {
  kind: "quizzes" | "flashcards";
}) {
  const { t, language } = useLanguage();
  const router = useRouter();

  const quizMode = kind === "quizzes";
  const languageRef = useRef(language);

  useEffect(() => {
    languageRef.current = language;
  }, [language]);

  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [quizzes, setQuizzes] = useState<Quiz[]>([]);
  const [flashcards, setFlashcards] = useState<Flashcard[]>([]);

  const [selectedDocumentId, setSelectedDocumentId] =
    useState<number | null>(null);

  const [documentsLoading, setDocumentsLoading] = useState(true);
  const [contentLoading, setContentLoading] = useState(true);

  const [deletingDocumentId, setDeletingDocumentId] =
    useState<number | null>(null);

  const [deletingQuizId, setDeletingQuizId] =
    useState<number | null>(null);

  const [showCreateQuiz, setShowCreateQuiz] = useState(false);
  const [questionCount, setQuestionCount] = useState(10);
  const [creatingQuiz, setCreatingQuiz] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [collectionQuery, setCollectionQuery] = useState("");
  const [collectionView, setCollectionView] = useState<"grid" | "list">("grid");
  const [collectionFilter, setCollectionFilter] = useState<"all" | "created">("all");
  const [collectionSort, setCollectionSort] = useState<"newest" | "oldest">("newest");
  const [quizMenuDocumentId, setQuizMenuDocumentId] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    function handleError(cause: unknown) {
      if (cancelled || isAbortError(cause)) return;

      const requestLanguage = languageRef.current;

      setError(
        quizMode
          ? requestLanguage === "tr"
            ? "Sınavlar şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin."
            : "Quizzes are currently unavailable. Please try again later."
          : requestLanguage === "tr"
            ? "Bilgi kartları şu anda yüklenemiyor."
            : "Flashcards are currently unavailable.",
      );
    }

    /*
     * Belgeler ayrı yükleniyor.
     * Quiz veya flashcard isteğini beklemiyor.
     */
    apiFetch<DocumentData[]>("/documents/", {
      signal: controller.signal,
    })
      .then((documentData) => {
        if (cancelled) return;

        setDocuments(documentData);

        const requestedDocumentId = Number(
          new URLSearchParams(window.location.search).get("document_id"),
        );

        if (
          quizMode &&
          Number.isInteger(requestedDocumentId) &&
          documentData.some(
            (document) =>
              (document.id ?? document.document_id) === requestedDocumentId,
          )
        ) {
          setSelectedDocumentId(requestedDocumentId);
        }
      })
      .catch(handleError)
      .finally(() => {
        if (!cancelled) {
          setDocumentsLoading(false);
        }
      });

    /*
     * Quizler belgelerden bağımsız yükleniyor.
     */
    if (quizMode) {
      apiFetch<Quiz[]>("/quizzes/", {
        signal: controller.signal,
      })
        .then((quizData) => {
          if (cancelled) return;

          const uniqueQuizzes = [
            ...new Map(
              quizData
                .filter((quiz) => (quiz.id ?? quiz.quiz_id) != null)
                .map((quiz) => [
                  (quiz.id ?? quiz.quiz_id) as number,
                  {
                    ...quiz,
                    id: quiz.id ?? quiz.quiz_id,
                  },
                ]),
            ).values(),
          ];

          setQuizzes(uniqueQuizzes);
        })
        .catch(handleError)
        .finally(() => {
          if (!cancelled) {
            setContentLoading(false);
          }
        });
    } else {
      /*
       * Flashcardlar da belgelerden bağımsız yükleniyor.
       */
      apiFetch<Flashcard[]>("/flashcards/", {
        signal: controller.signal,
      })
        .then((flashcardData) => {
          if (cancelled) return;

          setFlashcards(flashcardData);
        })
        .catch(handleError)
        .finally(() => {
          if (!cancelled) {
            setContentLoading(false);
          }
        });
    }

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [quizMode]);

  /*
   * Her belge için quizzes.filter(...) yapmak yerine
   * quiz sayılarını bir kere hesaplıyoruz.
   */
  const quizDocuments = useMemo(() => {
    const quizCountByDocument = new Map<number, number>();

    for (const quiz of quizzes) {
      if (quiz.document_id == null) continue;

      quizCountByDocument.set(
        quiz.document_id,
        (quizCountByDocument.get(quiz.document_id) ?? 0) + 1,
      );
    }

    return documents
      .map((document) => {
        const documentId = document.id ?? document.document_id;

        if (documentId == null) return null;

        return {
          id: documentId,
          filename: document.filename,
          pageCount: document.page_count,
          quizCount: quizCountByDocument.get(documentId) ?? 0,
        };
      })
      .filter(Boolean) as Array<{
      id: number;
      filename: string;
      pageCount: number;
      quizCount: number;
    }>;
  }, [documents, quizzes]);

  /*
   * Flashcard sayılarını da bir kere hesaplıyoruz.
   */
  const flashcardDocuments = useMemo(() => {
    const flashcardCountByDocument = new Map<number, number>();

    for (const card of flashcards) {
      if (card.document_id == null) continue;

      flashcardCountByDocument.set(
        card.document_id,
        (flashcardCountByDocument.get(card.document_id) ?? 0) + 1,
      );
    }

    return documents
      .map((document) => {
        const documentId = document.id ?? document.document_id;

        if (documentId == null) return null;

        return {
          id: documentId,
          documentId,
          filename: document.filename,
          pageCount: document.page_count,
          flashcardCount:
            flashcardCountByDocument.get(documentId) ?? 0,
        };
      })
      .filter(Boolean) as FlashcardDocumentCard[];
  }, [documents, flashcards]);

  const visibleQuizDocuments = useMemo(() => quizDocuments.filter((document) => document.filename.toLocaleLowerCase(language === "tr" ? "tr-TR" : "en-US").includes(collectionQuery.trim().toLocaleLowerCase(language === "tr" ? "tr-TR" : "en-US"))).sort((a, b) => collectionSort === "newest" ? b.id - a.id : a.id - b.id), [collectionQuery, collectionSort, language, quizDocuments]);
  const visibleFlashcardDocuments = useMemo(() => flashcardDocuments.filter((document) => document.filename.toLocaleLowerCase(language === "tr" ? "tr-TR" : "en-US").includes(collectionQuery.trim().toLocaleLowerCase(language === "tr" ? "tr-TR" : "en-US")) && (collectionFilter === "all" || document.flashcardCount > 0)).sort((a, b) => collectionSort === "newest" ? b.id - a.id : a.id - b.id), [collectionFilter, collectionQuery, collectionSort, flashcardDocuments, language]);
  const totalQuestions = quizzes.reduce((total, quiz) => total + (quiz.question_count ?? 0), 0);
  const totalCards = flashcards.length;

  const selectedDocument = documents.find(
    (document) =>
      (document.id ?? document.document_id) === selectedDocumentId,
  );

  const selectedDocumentQuizzes = useMemo(() => {
    if (selectedDocumentId == null) return [];

    return quizzes.filter(
      (quiz) => quiz.document_id === selectedDocumentId,
    );
  }, [quizzes, selectedDocumentId]);

  function openQuiz(quiz: Quiz) {
    const quizId = quiz.id ?? quiz.quiz_id;

    if (quizId == null) return;

    router.push(
      `/quiz/${quizId}?document_id=${quiz.document_id}`,
    );
  }

  async function createQuiz() {
    if (selectedDocumentId == null || creatingQuiz) return;

    setCreatingQuiz(true);
    setError(null);

    try {
      const created = await apiFetch<Quiz>(
        `/quizzes/generate?document_id=${selectedDocumentId}&question_count=${questionCount}`,
        {
          method: "POST",
        },
      );

      const quizId = created.quiz_id ?? created.id;

      if (quizId == null) {
        setError(
          language === "tr"
            ? "Sınav oluşturuldu ancak açılamadı."
            : "The quiz was created but could not be opened.",
        );
        return;
      }

      const normalized = {
        ...created,
        id: quizId,
      };

      setQuizzes((current) => [
        ...current.filter(
          (quiz) => (quiz.id ?? quiz.quiz_id) !== quizId,
        ),
        normalized,
      ]);

      setShowCreateQuiz(false);
      setQuestionCount(10);

      router.push(
        `/quiz/${quizId}?document_id=${selectedDocumentId}`,
      );
    } catch (cause) {
      if (isAbortError(cause)) return;

      setError(
        language === "tr"
          ? "Sınav oluşturulamadı. Lütfen tekrar deneyin."
          : "The quiz could not be created. Please try again.",
      );
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

      setDocuments((current) =>
        current.filter(
          (document) =>
            (document.id ?? document.document_id) !== documentId,
        ),
      );

      setQuizzes((current) =>
        current.filter(
          (quiz) => quiz.document_id !== documentId,
        ),
      );

      setFlashcards((current) =>
        current.filter(
          (flashcard) => flashcard.document_id !== documentId,
        ),
      );

      if (selectedDocumentId === documentId) {
        setSelectedDocumentId(null);
      }
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
          (quiz) => (quiz.id ?? quiz.quiz_id) !== quizId,
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

  async function deleteFlashcardSet(
    event: React.MouseEvent,
    documentId: number,
  ) {
    event.preventDefault();
    event.stopPropagation();

    if (
      !window.confirm(
        language === "tr"
          ? "Bu belge için oluşturulan bilgi kartlarını silmek istediğinize emin misiniz?"
          : "Are you sure you want to delete the flashcards created for this document?",
      )
    ) {
      return;
    }

    const cards = flashcards.filter(
      (flashcard) => flashcard.document_id === documentId,
    );

    setDeletingDocumentId(documentId);
    setError(null);

    const deletedIds: number[] = [];

    try {
      /*
       * Eski kodda silme işlemleri tek tek await ile
       * sırayla yapılıyordu.
       *
       * Burada paralel siliyoruz.
       */
      const results = await Promise.allSettled(
        cards.map((card) =>
          apiFetch(`/flashcards/${card.id}`, {
            method: "DELETE",
          }).then(() => card.id),
        ),
      );

      for (const result of results) {
        if (result.status === "fulfilled") {
          deletedIds.push(result.value);
        }
      }

      const failed = results.some(
        (result) => result.status === "rejected",
      );

      if (failed) {
        setError(
          language === "tr"
            ? "Bazı bilgi kartları silinemedi."
            : "Some flashcards could not be deleted.",
        );
      }
    } catch (cause) {
      setError(
        apiErrorMessage(
          cause,
          language === "tr"
            ? "Bilgi kartları silinirken bir hata oluştu."
            : "An error occurred while deleting flashcards.",
        ),
      );
    } finally {
      if (deletedIds.length) {
        setFlashcards((current) =>
          current.filter(
            (card) => !deletedIds.includes(card.id),
          ),
        );
      }

      setDeletingDocumentId(null);
    }
  }

  /*
   * Sadece belge listesi gelene kadar tam ekran loading göster.
   * Quiz/flashcard isteği yavaşsa bütün sayfayı bloke etmiyoruz.
   */
  if (documentsLoading) {
    return (
      <div
        className={
          quizMode
            ? "quizzes-page"
            : "flashcards-page"
        }
      >
        <p
          className={
            quizMode
              ? "quizzes-loading"
              : "flashcards-loading"
          }
        >
          {t("loading")}
        </p>
      </div>
    );
  }

  /*
   * SINAVLAR ANA SAYFASI
   */
  if (quizMode && selectedDocumentId === null) {
    return (
      <div className="quizzes-page">
        <header className="courses-hero quizzes-hero">
          <div className="courses-hero-copy quizzes-hero-copy">
            <p className="courses-eyebrow">
              SINAVLAR
            </p>

            <h1>{t("quizzesTitle")}</h1>

            <p className="courses-subtitle">
              Ders materyallerinden odaklı sınavlar oluştur ve tekrar etmen gereken konuları takip et.
            </p>
            <div className="courses-stats quizzes-stats">
              <div><span>▤</span><strong>{quizzes.length}</strong><small>Toplam Sınav</small></div>
              <div><span>?</span><strong>{totalQuestions}</strong><small>Toplam Soru</small></div>
              <div><span>◎</span><strong>0%</strong><small>Ortalama Başarı</small></div>
              <div><span>□</span><strong>0</strong><small>Bu Hafta</small></div>
            </div>
          </div>

          <div className="courses-hero-art quizzes-hero-art"><CollectionArtwork kind="quizzes" /></div>

          <Link
            href="/library?action=quiz"
            className="courses-primary-button"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.4"
            >
              <path d="M12 5v14M5 12h14" />
            </svg>

            {t("createQuizLower")}
          </Link>
        </header>

        <div className="courses-toolbar quizzes-toolbar">
          <label className="courses-search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg><span className="sr-only">Sınav ara</span><input type="search" value={collectionQuery} onChange={(event) => setCollectionQuery(event.target.value)} placeholder="Sınav ara..." /></label>
          <select className="courses-filter" value={collectionSort} onChange={(event) => setCollectionSort(event.target.value as "newest" | "oldest")} aria-label="Sınav sıralaması"><option value="newest">En Yeni</option><option value="oldest">En Eski</option></select>
          <div className="courses-view-toggle" role="group" aria-label="Görünüm seç"><button type="button" className={collectionView === "grid" ? "active" : ""} onClick={() => setCollectionView("grid")} aria-label="Izgara görünümü">▦</button><button type="button" className={collectionView === "list" ? "active" : ""} onClick={() => setCollectionView("list")} aria-label="Liste görünümü">☰</button></div>
        </div>

        {error ? (
          <p
            className="quizzes-error"
            role="alert"
          >
            {error}
          </p>
        ) : null}

        {visibleQuizDocuments.length ? (
          <div className={`quizzes-grid collection-grid--${collectionView}`}>
            {visibleQuizDocuments.map((document) => (
              <article
                key={document.id}
                className="quizzes-document-card"
                role="link"
                tabIndex={0}
                onClick={() =>
                  router.push(
                    `/documents/${document.id}?tab=quiz`,
                  )
                }
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" ||
                    event.key === " "
                  ) {
                    router.push(
                      `/documents/${document.id}?tab=quiz`,
                    );
                  }
                }}
              >
                <span
                  className="quizzes-card-flag"
                  aria-hidden="true"
                />
                <span className={`quiz-status ${document.quizCount ? "is-ready" : "is-new"}`}>{document.quizCount ? "Hazır" : "Yeni"}</span>
                <div className="quiz-card-menu"><button type="button" onClick={(event) => { event.preventDefault(); event.stopPropagation(); setQuizMenuDocumentId(quizMenuDocumentId === document.id ? null : document.id); }} aria-label={`${document.filename} menüsü`} aria-expanded={quizMenuDocumentId === document.id}>•••</button>{quizMenuDocumentId === document.id ? <div><button type="button" disabled={deletingDocumentId === document.id} onClick={(event) => deleteDocument(event, document.id)}>{deletingDocumentId === document.id ? "Siliniyor..." : "Belgeyi sil"}</button></div> : null}</div>

                <span className="quizzes-card-icon">
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <path d="M14 2v6h6" />
                  </svg>
                </span>

                <h2>{document.filename}</h2>
                <p className="quiz-card-meta">{document.quizCount ? `${document.quizCount} sınav hazır` : "Henüz sınav oluşturulmadı"}</p>

                <span
                  className="quizzes-card-rule"
                  aria-hidden="true"
                />

                <div className="quizzes-card-stats">
                  <span>
                    <b>{document.pageCount}</b>
                    <small>{t("pages")}</small>
                  </span>

                  <span>
                    <b>
                      {contentLoading
                        ? "..."
                        : document.quizCount}
                    </b>

                    <small>
                      {t("quizzes")}
                    </small>
                  </span>

                  <button
                    className="quiz-open-button"
                    type="button"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();

                      router.push(
                        `/documents/${document.id}?tab=quiz`,
                      );
                    }}
                  >
                    {document.quizCount ? "Sınavı Aç" : t("createQuizLower")} <span aria-hidden="true">→</span>
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="quizzes-empty">
            <p>
              {language === "tr"
                ? "Henüz sınav oluşturabileceğin bir materyal yok."
                : "You don't have material available for a quiz yet."}
            </p>

            <span>
              {language === "tr"
                ? "Önce kütüphanene bir PDF ekle."
                : "Add a PDF to your library first."}
            </span>

            <Link href="/upload">
              {t("addMaterial")} →
            </Link>
          </div>
        )}
      </div>
    );
  }

  /*
   * SEÇİLEN PDF'NİN SINAVLARI
   */
  if (
    quizMode &&
    selectedDocumentId !== null
  ) {
    return (
      <div className="mx-auto max-w-5xl px-5 py-12 sm:px-8 sm:py-16">
        <button
          type="button"
          onClick={() =>
            setSelectedDocumentId(null)
          }
          className="text-sm font-medium text-blue-600"
        >
          ← PDF&apos;lere dön
        </button>

        <div className="mt-5 flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-3xl font-semibold text-gray-950">
              {selectedDocument?.filename}
            </h1>

            <p className="mt-2 text-sm text-gray-500">
              Daha önce oluşturduğun sınavlar
            </p>
          </div>

          <Button
            className="shrink-0 self-start"
            onClick={() => {
              setError(null);
              setQuestionCount(10);
              setShowCreateQuiz(true);
            }}
          >
            <svg
              className="size-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
            >
              <path d="M12 5v14M5 12h14" />
            </svg>

            Yeni Sınav Oluştur
          </Button>
        </div>

        {contentLoading ? (
          <p className="mt-8 text-sm text-gray-500">
            {t("loading")}
          </p>
        ) : (
          <div className="mt-8 grid gap-3 sm:grid-cols-2">
            {selectedDocumentQuizzes.map(
              (quiz, index) => {
                const quizId =
                  quiz.id ?? quiz.quiz_id;

                return (
                  <Card
                    key={quizId}
                    onClick={() =>
                      openQuiz(quiz)
                    }
                    className="relative h-full cursor-pointer p-5 pr-16 text-left transition hover:bg-gray-50"
                    role="button"
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (
                        event.key === "Enter" ||
                        event.key === " "
                      ) {
                        openQuiz(quiz);
                      }
                    }}
                  >
                    {quizId != null ? (
                      <button
                        type="button"
                        disabled={
                          deletingQuizId === quizId
                        }
                        onClick={(event) =>
                          deleteQuiz(
                            event,
                            quizId,
                          )
                        }
                        className="absolute right-4 top-4 inline-flex size-8 items-center justify-center rounded-lg text-red-600 transition hover:bg-red-50 disabled:opacity-50"
                        aria-label={`Sınav ${index + 1} sil`}
                        title="Sil"
                      >
                        <svg
                          className="size-4"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.7"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        >
                          <path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" />
                        </svg>
                      </button>
                    ) : null}

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
                );
              },
            )}
          </div>
        )}

        {showCreateQuiz ? (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/50 p-4"
            role="presentation"
            onMouseDown={(event) => {
              if (
                event.currentTarget === event.target &&
                !creatingQuiz
              ) {
                setShowCreateQuiz(false);
              }
            }}
          >
            <Card
              className="w-full max-w-md p-6"
              role="dialog"
              aria-modal="true"
              aria-labelledby="create-quiz-title"
            >
              <h2
                id="create-quiz-title"
                className="text-lg font-semibold text-gray-950"
              >
                Yeni Sınav Oluştur
              </h2>

              <p className="mt-2 truncate text-sm text-gray-500">
                {selectedDocument?.filename}
              </p>

              <div className="mt-6 grid gap-4 sm:grid-cols-2">
                <label className="text-sm font-medium text-gray-700">
                  Soru sayısı

                  <select
                    value={questionCount}
                    disabled={creatingQuiz}
                    onChange={(event) =>
                      setQuestionCount(
                        Number(
                          event.target.value,
                        ),
                      )
                    }
                    className="mt-2 block h-11 w-full rounded-xl border border-gray-200 bg-white px-3 text-gray-900"
                  >
                    <option value={5}>
                      5
                    </option>

                    <option value={10}>
                      10
                    </option>

                    <option value={15}>
                      15
                    </option>
                  </select>
                </label>
              </div>

              {error ? (
                <p
                  className="mt-4 text-sm text-red-600"
                  role="alert"
                >
                  {error}
                </p>
              ) : null}

              <div className="mt-6 flex justify-end gap-3">
                <Button
                  variant="secondary"
                  disabled={creatingQuiz}
                  onClick={() =>
                    setShowCreateQuiz(false)
                  }
                >
                  İptal
                </Button>

                <Button
                  disabled={creatingQuiz}
                  onClick={createQuiz}
                >
                  {creatingQuiz
                    ? "Sınav hazırlanıyor..."
                    : "Sınavı Oluştur"}
                </Button>
              </div>
            </Card>
          </div>
        ) : null}
      </div>
    );
  }

  /*
   * BİLGİ KARTLARI
   */
  return (
    <div className="flashcards-page">
      <header className="flashcards-heading collection-hero">
        <div className="collection-hero-copy">
          <p className="flashcards-eyebrow">
            BİLGİ KARTLARI
          </p>

          <h1>{t("flashcardsTitle")}</h1>

          <p className="flashcards-subtitle">
            {language === "tr"
              ? "Materyallerinden oluşturduğun kartlarla temel kavramları hızlıca tekrar et."
              : "Quickly review key concepts with cards created from your materials."}
          </p>
          <div className="collection-stats">
            <div><strong>{totalCards}</strong><span>Toplam Kart</span></div>
            <div><strong>{flashcardDocuments.filter((item) => item.flashcardCount > 0).length}</strong><span>Kart Seti</span></div>
          </div>
        </div>

        <CollectionArtwork kind="flashcards" />

        <Link
          href="/library?action=flashcards"
          className="flashcards-primary-button"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>

          {t("generateFlashcards")}
        </Link>
      </header>

      <div className="collection-toolbar">
        <label><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg><input type="search" value={collectionQuery} onChange={(event) => setCollectionQuery(event.target.value)} placeholder="Bilgi kartı ara..." /></label>
        <select value={collectionFilter} onChange={(event) => setCollectionFilter(event.target.value as "all" | "created")} aria-label="Bilgi kartı filtresi"><option value="all">Tümü</option><option value="created">Oluşturduklarım</option></select>
        <select value={collectionSort} onChange={(event) => setCollectionSort(event.target.value as "newest" | "oldest")} aria-label="Bilgi kartı sıralaması"><option value="newest">En Yeni</option><option value="oldest">En Eski</option></select>
        <div className="collection-view-toggle"><button type="button" className={collectionView === "grid" ? "active" : ""} onClick={() => setCollectionView("grid")} aria-label="Izgara görünümü">▦</button><button type="button" className={collectionView === "list" ? "active" : ""} onClick={() => setCollectionView("list")} aria-label="Liste görünümü">☰</button></div>
      </div>

      {error ? (
        <p
          className="flashcards-error"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      {visibleFlashcardDocuments.length ? (
        <div className={`flashcards-grid collection-grid--${collectionView}`}>
          {visibleFlashcardDocuments.map(
            (document) => (
              <article
                key={document.id}
                className="flashcards-document-card"
              >
                <span
                  className="flashcards-card-flag"
                  aria-hidden="true"
                />

                <span className="flashcards-card-icon">
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                  >
                    <rect
                      x="4"
                      y="5"
                      width="16"
                      height="14"
                      rx="2"
                    />

                    <path d="M8 9h8M8 13h5" />
                  </svg>
                </span>

                {!contentLoading &&
                document.flashcardCount > 0 ? (
                  <button
                    type="button"
                    disabled={
                      deletingDocumentId ===
                      document.documentId
                    }
                    onClick={(event) =>
                      deleteFlashcardSet(
                        event,
                        document.documentId,
                      )
                    }
                    className="flashcards-delete"
                    aria-label={`${document.filename} bilgi kartlarını sil`}
                    title="Sil"
                  >
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                    >
                      <path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" />
                    </svg>
                  </button>
                ) : null}

                <h2>{document.filename}</h2>

                <span
                  className="flashcards-card-rule"
                  aria-hidden="true"
                />

                <div className="flashcards-stats">
                  <span>
                    <b>{document.pageCount}</b>

                    <small>{t("pages")}</small>
                  </span>

                  <span>
                    <b>
                      {contentLoading
                        ? "..."
                        : document.flashcardCount}
                    </b>

                    <small>
                      {language === "tr"
                        ? "Kart"
                        : "Cards"}
                    </small>
                  </span>
                </div>

                <div className="flashcards-actions">
                  <Link
                    href={`/documents/${document.documentId}?tab=flashcards`}
                  >
                    {language === "tr"
                      ? "Görüntüle"
                      : "View"}
                  </Link>

                  <Link
                    href={`/documents/${document.documentId}?tab=flashcards`}
                  >
                    {contentLoading
                      ? t("loading")
                      : document.flashcardCount
                        ? language === "tr"
                          ? "Yeni kart oluştur"
                          : "Create new card"
                        : t(
                            "generateFlashcards",
                          )}
                  </Link>
                </div>
              </article>
            ),
          )}
        </div>
      ) : (
        <div className="flashcards-empty">
          <p>
            {language === "tr"
              ? "Henüz bilgi kartı oluşturabileceğin bir materyal yok."
              : "You don't have material available for flashcards yet."}
          </p>

          <span>
            {language === "tr"
              ? "Önce kütüphanene bir PDF ekle."
              : "Add a PDF to your library first."}
          </span>

          <Link href="/upload">
            {t("addMaterial")} →
          </Link>
        </div>
      )}
    </div>
  );
}
