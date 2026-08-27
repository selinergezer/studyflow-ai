"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import Button from "@/components/ui/Button";
import SummaryNotebook from "@/components/documents/SummaryNotebook";
import QuizPanel from "@/components/documents/QuizPanel";
import FlashcardStudy from "@/components/documents/FlashcardStudy";
import {
  apiFetch,
  deleteQuizApi,
  isAbortError,
  type DocumentData,
  type Flashcard,
  type Quiz,
} from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

type Tab = "summary" | "quiz" | "flashcards";

export default function DocumentWorkspace({
  documentId,
  initialTab = "summary",
  initialFlashcardId,
}: {
  documentId: string;
  initialTab?: Tab;
  initialFlashcardId?: number;
}) {
  const { t, language } = useLanguage();
  const languageRef = useRef(language);

  useEffect(() => {
    languageRef.current = language;
  }, [language]);

  const [document, setDocument] = useState<DocumentData | null>(null);
  const [tab, setTab] = useState<Tab>(initialTab);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<"quiz" | "flashcards" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [summaryText, setSummaryText] = useState("");
  const [summaryStreaming, setSummaryStreaming] = useState(false);

  const [flashcardCount, setFlashcardCount] = useState(10);
  const [flashcards, setFlashcards] = useState<Flashcard[]>([]);
  const [activeFlashcards, setActiveFlashcards] =
    useState<Flashcard[] | null>(null);

    const flashcardBatches = Array.from(
  flashcards.reduce((groups, card) => {
    const key = card.batch_id ?? `legacy-${card.id}`;

    if (!groups.has(key)) {
      groups.set(key, []);
    }

    groups.get(key)!.push(card);

    return groups;
  }, new Map<string, Flashcard[]>())
);

  const [quizzes, setQuizzes] = useState<Quiz[]>([]);
  const [selectedQuiz, setSelectedQuiz] = useState<Quiz | null>(null);
  const [loadingQuizId, setLoadingQuizId] = useState<number | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    const { signal } = controller;

    async function loadDocument() {
      try {
        const item = await apiFetch<DocumentData>(
          `/documents/${documentId}`,
          { signal }
        );

        const normalized = {
          ...item,
          document_id: item.document_id ?? item.id,
        };

        setDocument(normalized);

        localStorage.setItem(
          "lastDocument",
          JSON.stringify(normalized)
        );

        setSummaryText(normalized.summary ?? "");

        // Belge detayı hazır; ikincil quiz/flashcard koleksiyonları sayfanın
        // görünmesini bloke etmesin.
        if (!signal.aborted) {
          setLoading(false);
        }

        const [quizResult, flashcardResult] =
          await Promise.allSettled([
            apiFetch<Quiz[]>("/quizzes/", {
              signal,
            }),

            apiFetch<Flashcard[]>(
              `/flashcards/?course_id=${item.course_id}`,
              {
                signal,
              }
            ),
          ]);

        if (signal.aborted) return;

        if (quizResult.status === "fulfilled") {
          const quizItems = quizResult.value;

          const documentQuizzes =
            quizItems.filter(
              (quiz) =>
                quiz.document_id ===
                Number(documentId)
            );

          setQuizzes(documentQuizzes);
        } else if (
          !isAbortError(quizResult.reason) &&
          initialTab === "quiz"
        ) {
          setError(
            languageRef.current === "tr"
              ? "Sınavlar şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin."
              : "Quizzes are currently unavailable. Please try again later."
          );
        }

        if (flashcardResult.status === "fulfilled") {
  const documentFlashcards =
    flashcardResult.value.filter(
      (card) =>
        card.document_id === Number(documentId)
    );

  setFlashcards(documentFlashcards);

  if (initialFlashcardId != null) {
    const selectedCard = documentFlashcards.find(
      (card) => card.id === initialFlashcardId
    );

    if (selectedCard) {
      const selectedBatchId =
        selectedCard.batch_id;

      const selectedBatch =
        selectedBatchId
          ? documentFlashcards.filter(
              (card) =>
                card.batch_id === selectedBatchId
            )
          : [selectedCard];

      setTab("flashcards");
      setActiveFlashcards(selectedBatch);
    }
  }
}else if (
          !isAbortError(
            flashcardResult.reason
          ) &&
          initialTab === "flashcards"
        ) {
          setError(
            languageRef.current === "tr"
              ? "Bilgi kartları şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin."
              : "Flashcards are currently unavailable. Please try again later."
          );
        }
      } catch (cause) {
        if (!isAbortError(cause)) {
          setError(
            languageRef.current === "tr"
              ? "Veriler şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin."
              : "Data is currently unavailable. Please try again later."
          );
        }
      } finally {
        if (!signal.aborted) {
          setLoading(false);
        }
      }
    }

    void loadDocument();

    return () => controller.abort();
  }, [
    documentId,
    initialFlashcardId,
    initialTab,
  ]);

  async function openQuiz(quiz: Quiz) {
    const quizId =
      quiz.id ?? quiz.quiz_id;

    if (quizId == null) return;

    setError(null);

    if (quiz.questions?.length) {
      setSelectedQuiz({
        ...quiz,
      });

      return;
    }

    setLoadingQuizId(quizId);

    try {
      setSelectedQuiz(
        await apiFetch<Quiz>(
          `/quizzes/${quizId}`
        )
      );
    } catch (cause) {
      if (!isAbortError(cause)) {
        setError(
          language === "tr"
            ? "Sınav yüklenemedi. Lütfen tekrar deneyin."
            : "The quiz could not be loaded. Please try again."
        );
      }
    } finally {
      setLoadingQuizId(null);
    }
  }

  function handleQuizCreated(
    created: Quiz
  ) {
    const quizId =
      created.quiz_id ?? created.id;

    const normalized = {
      ...created,
      id: quizId,
      question_count:
        created.questions?.length ??
        created.question_count,
    };

    setQuizzes((current) => [
      ...current.filter(
        (quiz) =>
          (quiz.id ??
            quiz.quiz_id) !==
          quizId
      ),
      normalized,
    ]);

  }

  async function requestQuizDelete(
  event: React.MouseEvent,
  quiz: Quiz
) {
  event.preventDefault();
  event.stopPropagation();

  if (
    !window.confirm(
      language === "tr"
        ? "Bu sınavı silmek istediğinize emin misiniz?"
        : "Are you sure you want to delete this quiz?"
    )
  ) {
    return;
  }

  const quizId = quiz.id ?? quiz.quiz_id;

  if (quizId == null) {
    setError(
      language === "tr"
        ? "Sınav ID'si bulunamadı."
        : "Quiz ID was not found."
    );
    return;
  }

  setError(null);

  try {
    await deleteQuizApi(quizId);

    setQuizzes((current) =>
      current.filter(
        (currentQuiz) =>
          (currentQuiz.id ?? currentQuiz.quiz_id) !== quizId
      )
    );

    if (
      (selectedQuiz?.id ?? selectedQuiz?.quiz_id) === quizId
    ) {
      setSelectedQuiz(null);
    }
  } catch {
    setError(
      language === "tr"
        ? "Sınav silinemedi."
        : "Quiz could not be deleted."
    );
  }
}

  async function deleteFlashcardBatch(
    event: React.MouseEvent,
    batchCards: Flashcard[]
  ) {
    event.preventDefault();
    event.stopPropagation();

    if (
      !window.confirm(
        language === "tr"
          ? `Bu kart setindeki ${batchCards.length} kartın tamamını silmek istediğinize emin misiniz?`
          : `Are you sure you want to delete all ${batchCards.length} cards in this set?`
      )
    ) {
      return;
    }

    setError(null);

    try {
      await Promise.all(
        batchCards.map((card) =>
          apiFetch<void>(`/flashcards/${card.id}`, {
            method: "DELETE",
          })
        )
      );

      const deletedIds = new Set(
        batchCards.map((card) => card.id)
      );

      setFlashcards((current) =>
        current.filter(
          (card) => !deletedIds.has(card.id)
        )
      );

      if (
        activeFlashcards?.some((card) =>
          deletedIds.has(card.id)
        )
      ) {
        setActiveFlashcards(null);
      }
    } catch (cause) {
      if (!isAbortError(cause)) {
        setError(
          language === "tr"
            ? "Kart seti silinemedi."
            : "Card set could not be deleted."
        );
      }
    }
  }
  async function generateSummary() {
  if (!document) return;

  setSummaryStreaming(true);
  setSummaryText("");
  setError(null);

  try {
    const token = localStorage.getItem("access_token");

    const response = await fetch(
      `http://127.0.0.1:8000/documents/${documentId}/summary/stream`,
      {
        method: "GET",
        headers: {
          Accept: "text/event-stream",
          ...(token
            ? {
                Authorization: `Bearer ${token}`,
              }
            : {}),
        },
      }
    );

    if (!response.ok) {
      throw new Error(
        language === "tr"
          ? "Özet oluşturma isteği başarısız oldu."
          : "Summary generation request failed."
      );
    }

    if (!response.body) {
      throw new Error(
        language === "tr"
          ? "Özet akışı başlatılamadı."
          : "Summary stream could not be started."
      );
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    let buffer = "";
    let streamedSummary = "";

    while (true) {
      const { value, done } = await reader.read();

      if (done) break;

      buffer += decoder.decode(value, {
        stream: true,
      });

      const rawEvents = buffer.split("\n\n");
      buffer = rawEvents.pop() ?? "";

      for (const rawEvent of rawEvents) {
        if (!rawEvent.trim()) continue;

        let eventName = "";
        let dataText = "";

        for (const line of rawEvent.split("\n")) {
          if (line.startsWith("event:")) {
            eventName = line.slice(6).trim();
          }

          if (line.startsWith("data:")) {
            dataText += line.slice(5).trim();
          }
        }

        if (!dataText) continue;

        let data: Record<string, unknown>;

        try {
          data = JSON.parse(dataText);
        } catch {
          continue;
        }

        if (eventName === "error") {
          throw new Error(
            typeof data.message === "string"
              ? data.message
              : language === "tr"
              ? "Özet oluşturulurken hata oluştu."
              : "An error occurred while creating the summary."
          );
        }

        if (eventName === "done") {
          continue;
        }

        const incomingText =
          typeof data.text === "string"
            ? data.text
            : typeof data.content === "string"
            ? data.content
            : typeof data.token === "string"
            ? data.token
            : typeof data.chunk === "string"
            ? data.chunk
            : "";

        if (!incomingText) continue;

        streamedSummary += incomingText;
        setSummaryText(streamedSummary);
      }
    }

    const updatedDocument =
      await apiFetch<DocumentData>(
        `/documents/${documentId}`
      );

    const normalizedUpdatedDocument = {
      ...updatedDocument,
      document_id:
        updatedDocument.document_id ??
        updatedDocument.id,
    };

    setDocument(normalizedUpdatedDocument);

    setSummaryText(
      normalizedUpdatedDocument.summary ??
        streamedSummary
    );

    localStorage.setItem(
      "lastDocument",
      JSON.stringify(
        normalizedUpdatedDocument
      )
    );
  } catch (cause) {
    if (!isAbortError(cause)) {
      console.error(
        "Summary generation failed:",
        cause
      );

      setError(
        cause instanceof Error
          ? cause.message
          : language === "tr"
          ? "Özet oluşturulamadı."
          : "Summary could not be generated."
      );
    }
  } finally {
    setSummaryStreaming(false);
  }
}

  async function generateFlashcards() {
    if (!document) return;

    setBusy("flashcards");
    setError(null);

    try {
      const data =
        await apiFetch<{
          flashcards: Flashcard[];
        }>(
          `/flashcards/generate?course_id=${document.course_id}&document_id=${documentId}&flashcard_count=${flashcardCount}`,
          {
            method: "POST",
          }
        );

      setFlashcards((current) => [
        ...current.filter(
          (card) =>
            !data.flashcards.some(
              (created) =>
                created.id === card.id
            )
        ),
        ...data.flashcards,
      ]);

      setActiveFlashcards(
        data.flashcards
      );
    } catch (cause) {
      if (!isAbortError(cause)) {
        setError(
          language === "tr"
            ? "Bilgi kartları şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin."
            : "Flashcards are currently unavailable. Please try again later."
        );
      }
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return (
      <div className="document-detail-page">
        <p className="document-detail-loading">
          {t("loading")}
        </p>
      </div>
    );
  }

  if (!document) {
    return (
      <div className="document-detail-page">
        <div className="document-detail-missing">
          <p>
            {error ??
              (language === "tr"
                ? "Belge bilgisi bulunamadı."
                : "Document information was not found.")}
          </p>
        </div>
      </div>
    );
  }

  const labels: Record<
    Tab,
    string
  > = {
    summary: t("summary"),
    quiz: t("quiz"),
    flashcards: t("flashcards"),
  };

  return (
    <div className="document-detail-page">
      <Link
        className="document-detail-back"
        href={`/courses/${document.course_id}`}
      >
        ← {language === "tr" ? "Kurslara dön" : "Back to courses"}
      </Link>

      <header className="document-detail-heading">
        <div
          className="document-detail-glow"
          aria-hidden="true"
        />

        <span className="document-pdf-icon">
          PDF
        </span>

        <div>
          <h1>{document.filename}</h1>

          <p>
            {document.page_count}{" "}
            {t("pages")}
          </p>
        </div>
      </header>

      <div
        className="document-tabs"
        role="tablist"
        aria-label={t(
          "documentTools"
        )}
      >
        {(
          [
            "summary",
            "quiz",
            "flashcards",
          ] as Tab[]
        ).map((item) => (
          <button
            key={item}
            role="tab"
            aria-selected={
              tab === item
            }
            onClick={() =>
              setTab(item)
            }
            className={
              tab === item
                ? "active"
                : ""
            }
          >
            {labels[item]}
          </button>
        ))}
      </div>

      {error ? (
        <p
          className="document-detail-error"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      {tab === "summary" ? (
        <SummaryNotebook
          key={summaryText}
          summary={summaryText}
          streaming={summaryStreaming}
          language={language}
          onGenerate={generateSummary}
        />
      ) : (
      <div className={`document-paper document-paper-${tab}`}>
        <span
          className="document-paper-tape"
          aria-hidden="true"
        />

        <span
          className="document-paper-holes"
          aria-hidden="true"
        />

        {tab === "quiz" ? (
          <section
            className={`document-quiz-workspace ${
              selectedQuiz
                ? "is-solving"
                : ""
            }`}
          >
            <div className="document-quiz-main">
              {selectedQuiz ? (
                <button
                  type="button"
                  className="quiz-back-button"
                  onClick={() =>
                    setSelectedQuiz(
                      null
                    )
                  }
                >
                  ←{" "}
                  {language === "tr"
                    ? "Sınav listesine dön"
                    : "Back to quiz list"}
                </button>
              ) : null}

              <QuizPanel
                key={
                  selectedQuiz
                    ? selectedQuiz.id ??
                      selectedQuiz.quiz_id
                    : "new"
                }
                documentId={
                  documentId
                }
                sourceName={
                  document.filename
                }
                initialQuiz={
                  selectedQuiz
                }
                onQuizCreated={
                  handleQuizCreated
                }
              />
            </div>

            <aside className="document-quiz-history">
              <header className="quiz-history-heading">
                <div>
                  <span>
                    {language === "tr"
                      ? "SINAV ARŞİVİ"
                      : "QUIZ ARCHIVE"}
                  </span>
                  <h2>
                    {language === "tr"
                      ? "Önceki Sınavlar"
                      : "Previous Quizzes"}
                  </h2>
                </div>

                <strong>
                  {quizzes.length}{" "}
                  {language === "tr"
                    ? "sınav"
                    : "quizzes"}
                </strong>
              </header>

              {quizzes.length ? (
                <div className="quiz-history-list">
                  {quizzes.map(
                    (
                      quiz,
                      index
                    ) => {
                      const quizId =
                        quiz.id ??
                        quiz.quiz_id;

                      const active =
                        quizId != null &&
                        quizId ===
                          (selectedQuiz?.id ??
                            selectedQuiz?.quiz_id);

                      return (
                        <article
                          key={
                            quizId ??
                            `${quiz.title}-${index}`
                          }
                          className={`quiz-history-card ${
                            active
                              ? "active"
                              : ""
                          }`}
                        >
                          <span
                            className="quiz-history-tape"
                            aria-hidden="true"
                          />

                          <h3>
                            {quiz.title ||
                              `${
                                language ===
                                "tr"
                                  ? "Sınav"
                                  : "Quiz"
                              } ${
                                index +
                                1
                              }`}
                          </h3>

                          <p>
                            {quiz.question_count ??
                              quiz
                                .questions
                                ?.length ??
                              "—"}{" "}
                            {language ===
                            "tr"
                              ? "soru"
                              : "questions"}
                          </p>

                          <div>
                            <button
                              type="button"
                              disabled={
                                loadingQuizId ===
                                quizId
                              }
                              onClick={() =>
                                openQuiz(
                                  quiz
                                )
                              }
                            >
                              {loadingQuizId ===
                              quizId
                                ? language ===
                                  "tr"
                                  ? "Yükleniyor..."
                                  : "Loading..."
                                : language ===
                                  "tr"
                                ? "Tekrar Çöz →"
                                : "Solve Again →"}
                            </button>

                            <button
                              type="button"
                              className="quiz-history-delete"
                              onClick={(
                                event
                              ) =>
                                requestQuizDelete(
                                  event,
                                  quiz
                                )
                              }
                              aria-label={
                                language ===
                                "tr"
                                  ? "Sınavı sil"
                                  : "Delete quiz"
                              }
                              title={
                                language ===
                                "tr"
                                  ? "Sil"
                                  : "Delete"
                              }
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
                          </div>
                        </article>
                      );
                    }
                  )}
                </div>
              ) : (
                <div className="quiz-history-empty">
                  <strong>
                    {language ===
                    "tr"
                      ? "Bu PDF için henüz sınav oluşturmadın."
                      : "You haven't created a quiz for this PDF yet."}
                  </strong>

                  <span>
                    {language ===
                    "tr"
                      ? "Soldaki ayarlardan ilk sınavını oluştur."
                      : "Create your first quiz using the settings on the left."}
                  </span>
                </div>
              )}
            </aside>
          </section>
        ) : null}

        {tab ===
        "flashcards" ? (
          <section
            className={`document-flashcards-panel ${
              activeFlashcards
                ? "is-studying"
                : ""
            }`}
          >
            {activeFlashcards ? (
              <>
                <button
                  type="button"
                  className="flashcard-back-button"
                  onClick={() =>
                    setActiveFlashcards(
                      null
                    )
                  }
                >
                  ←{" "}
                  {language ===
                  "tr"
                    ? "Kart setlerine dön"
                    : "Back to card sets"}
                </button>

                <FlashcardStudy
                  key={activeFlashcards
                    .map(
                      (card) =>
                        card.id
                    )
                    .join("-")}
                  cards={
                    activeFlashcards
                  }
                  onBack={() =>
                    setActiveFlashcards(
                      null
                    )
                  }
                />
              </>
            ) : (
              <div className="flashcard-library-layout">
                <div className="document-setup-panel">
                  <p className="document-setup-kicker">
                    {language ===
                    "tr"
                      ? "KARTLARINI HAZIRLA"
                      : "PREPARE YOUR CARDS"}
                  </p>

                  <h2>
                    {language ===
                    "tr"
                      ? "Önemli kavramları tekrar et"
                      : "Review the key concepts"}
                  </h2>

                  <p className="document-setup-description">
                    {language ===
                    "tr"
                      ? "Bu materyalin temel noktalarından hızlı bir bilgi kartı koleksiyonu oluştur."
                      : "Create a quick flashcard collection from the essential points in this material."}
                  </p>

                  <fieldset>
                    <legend>
                      {language ===
                      "tr"
                        ? "Kart sayısı"
                        : "Card count"}
                    </legend>

                    <div className="document-choice-row">
                      {[
                        5,
                        10,
                        15,
                      ].map(
                        (
                          count
                        ) => (
                          <button
                            key={
                              count
                            }
                            type="button"
                            className={
                              flashcardCount ===
                              count
                                ? "active"
                                : ""
                            }
                            aria-pressed={
                              flashcardCount ===
                              count
                            }
                            onClick={() =>
                              setFlashcardCount(
                                count
                              )
                            }
                          >
                            {
                              count
                            }
                          </button>
                        )
                      )}
                    </div>
                  </fieldset>

                  <Button
                    className="document-create-button"
                    onClick={
                      generateFlashcards
                    }
                    disabled={
                      busy !==
                      null
                    }
                  >
                    {busy ===
                    "flashcards"
                      ? language ===
                        "tr"
                        ? "Bilgi kartları hazırlanıyor..."
                        : "Preparing flashcards..."
                      : language ===
                        "tr"
                      ? "Bilgi Kartlarını Oluştur →"
                      : "Create Flashcards →"}
                  </Button>
                </div>

                <aside className="flashcard-history">
                  <p className="notebook-label">
                    {language ===
                    "tr"
                      ? "ÖNCEKİ KARTLAR"
                      : "PREVIOUS CARDS"}
                  </p>
{flashcardBatches.length ? (
  <div
  className="flashcard-history-list"
  style={{
    paddingRight: "10px",
  }}
>
    {flashcardBatches.map(
      ([batchId, batchCards], index) => (
        <article
          key={batchId}
          className="flashcard-history-card"
          style={{ position: "relative" }}
        >
          <span
            className="flashcard-history-tape"
            aria-hidden="true"
          />

          <h3>
            {language === "tr"
              ? `Kart Seti ${index + 1}`
              : `Card Set ${index + 1}`}
          </h3>

          <p>
            {batchCards.length}{" "}
            {language === "tr"
              ? "kart"
              : "cards"}
          </p>

          <div className="flashcard-history-actions">
            <button
              type="button"
              onClick={() =>
                setActiveFlashcards(batchCards)
              }
            >
              {language === "tr"
                ? "Tekrar Çalış →"
                : "Study Again →"}
            </button>

            <button
              type="button"
              className="flashcard-history-delete-btn"
              style={{
                position: "absolute",
                top: "16px",
                right: "16px",
                width: "28px",
                height: "28px",
                padding: 0,
                margin: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: "none",
                background: "transparent",
                color: "#e76f61",
                cursor: "pointer",
                borderRadius: "6px",
              }}
              onClick={(event) =>
                deleteFlashcardBatch(
                  event,
                  batchCards
                )
              }
              aria-label={
                language === "tr"
                  ? "Kart setini sil"
                  : "Delete card set"
              }
              title={
                language === "tr"
                  ? "Kart setini sil"
                  : "Delete card set"
              }
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                width="18"
                height="18"
              >
                <path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7m4 4v5m4-5v5" />
              </svg>
            </button>
          </div>
        </article>
      )
    )}
  </div>
) : (
  <div className="quiz-history-empty">
    <strong>
      {language === "tr"
        ? "Bu PDF için henüz bilgi kartın yok."
        : "You don't have flashcards for this PDF yet."}
    </strong>

    <span>
      {language === "tr"
        ? "Soldaki ayarlardan ilk kartlarını oluştur."
        : "Create your first cards using the settings on the left."}
    </span>
  </div>
  )}
                  
                </aside>
              </div>
            )}
          </section>
        ) : null}
      </div>
      )}
    </div>
  );
}
