"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import Card from "@/components/ui/Card";
import {
  apiFetch,
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

  const quizMode = kind === "quizzes";

  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [quizzes, setQuizzes] = useState<Quiz[]>([]);
  const [flashcards, setFlashcards] = useState<Flashcard[]>([]);

  const [selectedDocumentId, setSelectedDocumentId] =
    useState<number | null>(null);

  const [selectedQuiz, setSelectedQuiz] = useState<Quiz | null>(null);

  const [loading, setLoading] = useState(true);
  const [quizLoading, setQuizLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setSelectedDocumentId(null);
    setSelectedQuiz(null);

    function handleError(cause: unknown) {
      console.error(cause);

      setError(
        cause instanceof Error
          ? cause.message
          : language === "tr"
            ? "İşlem sırasında bir hata oluştu."
            : "Something went wrong."
      );
    }

    if (quizMode) {
      Promise.all([
        apiFetch<Quiz[]>("/quizzes/"),
        apiFetch<DocumentData[]>("/documents/"),
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
        })
        .catch(handleError)
        .finally(() => setLoading(false));

      return;
    }

    Promise.all([
      apiFetch<Flashcard[]>("/flashcards/"),
      apiFetch<DocumentData[]>("/documents/"),
    ])
      .then(([flashcardData, documentData]) => {
        setFlashcards(flashcardData);
        setDocuments(documentData);
      })
      .catch(handleError)
      .finally(() => setLoading(false));
  }, [quizMode, language]);

  const quizDocuments = useMemo(() => {
    return documents
      .map((document) => {
        const documentId = document.id ?? document.document_id;

        if (documentId == null) return null;

        const documentQuizzes = quizzes.filter(
          (quiz) => quiz.document_id === documentId
        );

        if (documentQuizzes.length === 0) return null;

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
    const documentMap = new Map(
      documents.map((document) => [
        document.id ?? document.document_id,
        document,
      ])
    );

    const grouped = new Map<number, FlashcardDocumentCard>();

    flashcards.forEach((flashcard) => {
      if (flashcard.document_id == null) return;

      const document = documentMap.get(flashcard.document_id);

      if (!document) return;

      const existing = grouped.get(flashcard.document_id);

      if (existing) {
        existing.flashcardCount += 1;
        return;
      }

      grouped.set(flashcard.document_id, {
        id: flashcard.document_id,
        documentId: flashcard.document_id,
        filename: document.filename,
        pageCount: document.page_count,
        flashcardCount: 1,
      });
    });

    return Array.from(grouped.values());
  }, [documents, flashcards]);

  const selectedDocument = documents.find(
    (document) =>
      (document.id ?? document.document_id) === selectedDocumentId
  );

  const selectedDocumentQuizzes = quizzes.filter(
    (quiz) => quiz.document_id === selectedDocumentId
  );

  async function openQuiz(quiz: Quiz) {
    if (!quiz.id) return;

    setQuizLoading(true);
    setError(null);

    try {
      const detail = await apiFetch<Quiz>(`/quizzes/${quiz.id}`);
      setSelectedQuiz(detail);
    } catch (cause) {
      console.error(cause);

      setError(
        cause instanceof Error
          ? cause.message
          : "Sınav yüklenirken bir hata oluştu."
      );
    } finally {
      setQuizLoading(false);
    }
  }

  const createHref = quizMode
    ? "/library?action=quiz"
    : "/library?action=flashcards";

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-5 py-16">
        <p className="text-sm text-gray-500">{t("loading")}</p>
      </div>
    );
  }

  /*
   * QUIZ DETAYI
   */
  if (quizMode && selectedQuiz) {
    return (
      <div className="mx-auto max-w-5xl px-5 py-12 sm:px-8 sm:py-16">
        <button
          type="button"
          onClick={() => setSelectedQuiz(null)}
          className="text-sm font-medium text-blue-600"
        >
          ← Önceki sınavlara dön
        </button>

        <h1 className="mt-5 text-3xl font-semibold text-gray-950">
          {selectedQuiz.title}
        </h1>

        <p className="mt-2 text-sm text-gray-500">
          {selectedQuiz.questions?.length ?? selectedQuiz.question_count ?? 0} soru
        </p>

        <div className="mt-8 space-y-5">
          {selectedQuiz.questions?.map((question, index) => (
            <Card key={question.id} className="p-6">
              <p className="font-semibold text-gray-950">
                {index + 1}. {question.question_text}
              </p>

              <div className="mt-5 space-y-2 text-sm text-gray-600">
                <p>A) {question.option_a}</p>
                <p>B) {question.option_b}</p>
                <p>C) {question.option_c}</p>
                <p>D) {question.option_d}</p>
                <p>E) {question.option_e}</p>
              </div>
            </Card>
          ))}
        </div>
      </div>
    );
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
          ← PDF'lere dön
        </button>

        <h1 className="mt-5 text-3xl font-semibold text-gray-950">
          {selectedDocument?.filename}
        </h1>

        <p className="mt-2 text-sm text-gray-500">
          Daha önce oluşturduğun sınavlar
        </p>

        {quizLoading ? (
          <p className="mt-8 text-sm text-gray-500">
            Sınav yükleniyor...
          </p>
        ) : null}

        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          {selectedDocumentQuizzes.map((quiz, index) => (
            <button
              key={quiz.id}
              type="button"
              onClick={() => openQuiz(quiz)}
              className="text-left"
            >
              <Card className="h-full p-5 transition hover:bg-gray-50">
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
            </button>
          ))}
        </div>
      </div>
    );
  }

  /*
   * ANA SAYFA
   */
  return (
    <div className="mx-auto max-w-5xl px-5 py-12 sm:px-8 sm:py-16">
      <div className="flex justify-between gap-6">
        <div>
          <p className="text-sm font-medium text-blue-600">
            {t(quizMode ? "practice" : "review")}
          </p>

          <h1 className="mt-3 text-3xl font-semibold text-gray-950">
            {t(quizMode ? "quizzesTitle" : "flashcardsTitle")}
          </h1>

          <p className="mt-4 text-gray-500">
            {t(quizMode ? "quizzesIntro" : "flashcardsIntro")}
          </p>
        </div>

        <Link
          href={createHref}
          className="inline-flex h-11 items-center rounded-xl bg-blue-600 px-4 text-sm font-medium text-white"
        >
          {t(
            quizMode
              ? "createQuizLower"
              : "generateFlashcards"
          )}
        </Link>
      </div>

      {error ? (
        <p className="mt-5 text-sm text-red-600">{error}</p>
      ) : null}

      {quizMode ? (
        <div className="mt-10 grid gap-3 sm:grid-cols-2">
          {quizDocuments.map((document) => (
            <button
              key={document.id}
              type="button"
              onClick={() => setSelectedDocumentId(document.id)}
              className="text-left"
            >
              <Card className="h-full p-5 transition hover:bg-gray-50">
                <h2 className="font-medium text-gray-950">
                  {document.filename}
                </h2>

                <p className="mt-2 text-sm text-gray-500">
                  {document.pageCount} {t("pages")}
                </p>

                <p className="mt-1 text-sm text-gray-500">
                  {document.quizCount} sınav
                </p>
              </Card>
            </button>
          ))}
        </div>
      ) : (
        <div className="mt-10 grid gap-3 sm:grid-cols-2">
          {flashcardDocuments.map((document) => (
            <Link
              key={document.id}
              href={`/documents/${document.documentId}?tab=flashcards`}
            >
              <Card className="h-full p-5 transition hover:bg-gray-50">
                <h2 className="font-medium text-gray-950">
                  {document.filename}
                </h2>

                <p className="mt-2 text-sm text-gray-500">
                  {document.pageCount} {t("pages")}
                </p>

                <p className="mt-1 text-sm text-gray-500">
                  {document.flashcardCount} bilgi kartı
                </p>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}