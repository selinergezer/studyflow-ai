"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import {
  apiFetch,
  type Quiz,
  type QuizQuestion,
} from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

type ResultItem = {
  question_id: number;
  user_answer: string | null;
  correct_answer: string;
  is_correct: boolean;
  explanation: string | null;
};

type QuizResult = {
  total_questions: number;
  correct: number;
  wrong: number;
  score: number;
  results: ResultItem[];
};

const optionKeys = [
  "option_a",
  "option_b",
  "option_c",
  "option_d",
  "option_e",
] as const;

const letters = ["A", "B", "C", "D", "E"];

export default function QuizPanel({
  documentId,
  initialQuiz,
  initialResult,
  onQuizCreated,
}: {
  documentId: string;
  initialQuiz?: Quiz | null;
  initialResult?: QuizResult | null;
  onQuizCreated?: (quiz: Quiz) => void;
}) {
  const { language } = useLanguage();
  const tr = language === "tr";

  const [questionCount, setQuestionCount] = useState(10);

  const [quiz, setQuiz] = useState<Quiz | null>(
    initialQuiz ?? null
  );

  const [questions, setQuestions] = useState<QuizQuestion[]>(
    initialQuiz?.questions ?? []
  );

  const [
    currentQuestionIndex,
    setCurrentQuestionIndex,
  ] = useState(0);

  const [answers, setAnswers] = useState<
    Record<number, string>
  >({});

  const [result, setResult] = useState<QuizResult | null>(
    initialResult ?? null
  );

  const [busy, setBusy] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [warning, setWarning] = useState<string | null>(
    null
  );

  const [
    generationProgress,
    setGenerationProgress,
  ] = useState({
    completed: 0,
    total: 0,
  });

  const currentQuestion =
    questions[currentQuestionIndex];

  // =====================================================
  // QUIZ OLUŞTUR - STREAMING
  // =====================================================

  async function generateQuiz() {
    setBusy(true);

    setError(null);
    setWarning(null);
    setResult(null);

    setAnswers({});
    setQuiz(null);
    setQuestions([]);

    setCurrentQuestionIndex(0);

    setGenerationProgress({
      completed: 0,
      total: questionCount,
    });

    try {
      const token = localStorage.getItem("access_token");

      const response = await fetch(
        `http://127.0.0.1:8000/quizzes/generate/stream?document_id=${documentId}&question_count=${questionCount}&difficulty=medium`,
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
        let message = tr
          ? "Sınav oluşturma isteği başarısız oldu."
          : "Quiz generation request failed.";

        try {
          const data = await response.json();

          if (typeof data?.detail === "string") {
            message = data.detail;
          }
        } catch {
          // JSON dönmezse varsayılan mesaj kalır.
        }

        throw new Error(message);
      }

      if (!response.body) {
        throw new Error(
          tr
            ? "Sınav akışı başlatılamadı."
            : "Quiz stream could not be started."
        );
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let buffer = "";

      let completedQuizId: number | null = null;

      while (true) {
        const { value, done } = await reader.read();

        if (done) {
          break;
        }

        buffer += decoder.decode(value, {
          stream: true,
        });

        const rawEvents = buffer.split(/\r?\n\r?\n/);

        buffer = rawEvents.pop() ?? "";

        for (const rawEvent of rawEvents) {
          if (!rawEvent.trim()) {
            continue;
          }

          let eventName = "";
          const dataLines: string[] = [];

          for (const line of rawEvent.split(/\r?\n/)) {
            if (line.startsWith("event:")) {
              eventName = line.slice(6).trim();
              continue;
            }

            if (line.startsWith("data:")) {
              dataLines.push(
                line.slice(5).trimStart()
              );
            }
          }

          if (dataLines.length === 0) {
            continue;
          }

          const dataText = dataLines.join("\n");

          let data: Record<string, unknown>;

          try {
            data = JSON.parse(dataText);
          } catch {
            console.warn(
              "SSE JSON parse edilemedi:",
              dataText
            );
            continue;
          }

          // =========================================
          // QUESTION EVENT
          // =========================================

          if (eventName === "question") {
            const possibleQuestion =
              data.question &&
              typeof data.question === "object"
                ? data.question
                : data;

            const question =
              possibleQuestion as unknown as QuizQuestion;

            setQuestions((current) => {
              if (
                question.id != null &&
                current.some(
                  (item) => item.id === question.id
                )
              ) {
                return current;
              }

              return [...current, question];
            });

            continue;
          }

          // =========================================
          // PROGRESS EVENT
          // =========================================

          if (eventName === "progress") {
            const completed =
              typeof data.completed_questions ===
              "number"
                ? data.completed_questions
                : typeof data.completed === "number"
                ? data.completed
                : 0;

            const total =
              typeof data.total_questions === "number"
                ? data.total_questions
                : typeof data.total === "number"
                ? data.total
                : questionCount;

            setGenerationProgress({
              completed,
              total,
            });

            continue;
          }

          // =========================================
          // ERROR EVENT
          // =========================================

          if (eventName === "error") {
            throw new Error(
              typeof data.message === "string"
                ? data.message
                : tr
                ? "Sınav oluşturulamadı."
                : "Quiz could not be generated."
            );
          }

          // =========================================
          // DONE EVENT
          // =========================================

          if (
            eventName === "done" ||
            eventName === "complete"
          ) {
            const possibleQuizId =
              data.quiz_id ?? data.id;

            if (typeof possibleQuizId === "number") {
              completedQuizId = possibleQuizId;
            }

            continue;
          }
        }
      }

      // =================================================
      // STREAM BİTTİKTEN SONRA DB'DEKİ QUIZ'İ AL
      // =================================================

      let created: Quiz | null = null;

      if (completedQuizId != null) {
        created = await apiFetch<Quiz>(
          `/quizzes/${completedQuizId}`
        );
      } else {
        const allQuizzes = await apiFetch<Quiz[]>(
          "/quizzes/"
        );

        const documentQuizzes = allQuizzes.filter(
          (item) =>
            item.document_id === Number(documentId)
        );

        const latest =
          documentQuizzes[
            documentQuizzes.length - 1
          ];

        const latestId =
          latest?.quiz_id ?? latest?.id;

        if (latestId != null) {
          created = await apiFetch<Quiz>(
            `/quizzes/${latestId}`
          );
        }
      }

      if (!created) {
        throw new Error(
          tr
            ? "Sınav oluşturuldu ancak kaydedilen sınav alınamadı."
            : "The quiz was generated but could not be loaded."
        );
      }

      setQuiz(created);

      setQuestions(created.questions ?? []);

      setCurrentQuestionIndex(0);

      setGenerationProgress({
        completed:
          created.questions?.length ?? questionCount,
        total: questionCount,
      });

      onQuizCreated?.(created);
    } catch (cause) {
      console.error(
        "Quiz streaming error:",
        cause
      );

      setQuiz(null);
      setQuestions([]);

      setError(
        cause instanceof Error
          ? cause.message
          : tr
          ? "Sınav oluşturulamadı."
          : "Quiz could not be generated."
      );
    } finally {
      setBusy(false);
    }
  }

  // =====================================================
  // QUIZ SUBMIT
  // =====================================================

  async function submitQuiz() {
    if (!quiz?.questions) {
      return;
    }

    const firstUnansweredIndex =
      quiz.questions.findIndex(
        (question) => !answers[question.id]
      );

    if (firstUnansweredIndex >= 0) {
      const unansweredCount =
        quiz.questions.filter(
          (question) => !answers[question.id]
        ).length;

      setWarning(
        tr
          ? `${unansweredCount} soruyu henüz cevaplamadınız.`
          : `${unansweredCount} questions are unanswered.`
      );

      setCurrentQuestionIndex(
        firstUnansweredIndex
      );

      return;
    }

    setBusy(true);
    setWarning(null);
    setError(null);

    try {
      const quizId =
        quiz.quiz_id ?? quiz.id;

      if (quizId == null) {
        throw new Error(
          tr
            ? "Sınav ID'si bulunamadı."
            : "Quiz ID was not found."
        );
      }

      const response =
        await apiFetch<QuizResult>(
          `/quizzes/${quizId}/submit`,
          {
            method: "POST",

            body: JSON.stringify({
              answers:
                quiz.questions.map(
                  (question) => ({
                    question_id:
                      question.id,

                    answer:
                      answers[
                        question.id
                      ],
                  })
                ),
            }),
          }
        );

      setResult(response);
    } catch (cause) {
      console.error(
        "Quiz submit error:",
        cause
      );

      setError(
        cause instanceof Error
          ? cause.message
          : tr
          ? "Veriler şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin."
          : "Data is currently unavailable. Please try again later."
      );
    } finally {
      setBusy(false);
    }
  }

  // =====================================================
  // TEKRAR ÇÖZ
  // =====================================================

  function restart() {
    setAnswers({});
    setResult(null);
    setWarning(null);
    setCurrentQuestionIndex(0);
  }

  // =====================================================
  // YENİ SINAV
  // =====================================================

  function createAnother() {
    setQuiz(null);
    setQuestions([]);
    setAnswers({});
    setResult(null);
    setWarning(null);
    setError(null);
    setCurrentQuestionIndex(0);

    setGenerationProgress({
      completed: 0,
      total: 0,
    });
  }

  // =====================================================
  // QUIZ OLUŞTURMA EKRANI
  // =====================================================

  /*
   * BURASI ÖNEMLİ:
   *
   * Eskiden:
   *
   * if (!quiz || !currentQuestion)
   *
   * diyorduk.
   *
   * Stream sırasında quiz henüz DB'den gelmemiş
   * olsa bile currentQuestion varsa hemen
   * soruyu göstermek istiyoruz.
   */

  if (!currentQuestion) {
    return (
      <section className="document-quiz-panel is-setup">
        <div className="quiz-builder">
          <div className="quiz-builder-panel">
            <p className="notebook-label">
              {tr
                ? "SINAV HAZIRLA"
                : "PREPARE A QUIZ"}
            </p>

            <p className="quiz-builder-description">
              {tr
                ? "Bu PDF'den kendine özel bir tekrar sınavı oluştur."
                : "Create a custom review quiz from this PDF."}
            </p>

            <fieldset className="quiz-setting">
              <legend>
                {tr
                  ? "Soru sayısı"
                  : "Question count"}
              </legend>

              <div className="choice-row">
                {[5, 10, 15].map((count) => (
                  <button
                    key={count}
                    type="button"
                    className={`choice ${
                      questionCount === count
                        ? "active"
                        : ""
                    }`}
                    aria-pressed={
                      questionCount === count
                    }
                    disabled={busy}
                    onClick={() =>
                      setQuestionCount(count)
                    }
                  >
                    {count}
                  </button>
                ))}
              </div>
            </fieldset>

            <Button
              className="quiz-create-button"
              onClick={generateQuiz}
              disabled={busy}
            >
              {busy
                ? tr
                  ? `Sınav hazırlanıyor... ${generationProgress.completed}/${generationProgress.total}`
                  : `Preparing quiz... ${generationProgress.completed}/${generationProgress.total}`
                : tr
                ? "Sınavı Oluştur →"
                : "Create Quiz →"}
            </Button>

            {busy ? (
              <p
                style={{
                  marginTop: "12px",
                  textAlign: "center",
                }}
              >
                {tr
                  ? `${generationProgress.completed} / ${generationProgress.total} soru hazırlandı`
                  : `${generationProgress.completed} / ${generationProgress.total} questions prepared`}
              </p>
            ) : null}
          </div>

          <aside
            className="quiz-note"
            aria-hidden="true"
          >
            <div className="quiz-doodle">
              <span>✓</span>
              <i>?</i>
            </div>

            <p>
              {tr ? (
                <>
                  Soru sayısını seç,
                  <br />
                  hemen sınavını oluştur!
                </>
              ) : (
                <>
                  Choose the number of questions,
                  <br />
                  then start your quiz!
                </>
              )}
            </p>

            <div className="hand-underline" />
          </aside>
        </div>

        {error ? (
          <p
            className="quiz-message error"
            role="alert"
          >
            {error}
          </p>
        ) : null}
      </section>
    );
  }

  // =====================================================
  // CURRENT RESULT
  // =====================================================

  const currentResult =
    result?.results.find(
      (entry) =>
        entry.question_id ===
        currentQuestion.id
    );

  // =====================================================
  // OPTIONS
  // =====================================================

  const options = optionKeys
    .map((key, index) => ({
      key,
      letter: letters[index],
      value: currentQuestion[key],
    }))
    .filter(
      (
        option
      ): option is {
        key: (typeof optionKeys)[number];
        letter: string;
        value: string;
      } =>
        typeof option.value === "string" &&
        option.value.trim().length > 0
    );

  /*
   * Multiple choice cevaplarında value
   * A/B/C/D/E olarak tutuluyor.
   * label ise ekrana gösterilecek metin.
   */

  const renderedOptions =
    currentQuestion.question_type ===
    "true_false"
      ? [
          {
            key: "true",
            letter: "",
            value: "true",
            label: tr
              ? "Doğru"
              : "True",
          },
          {
            key: "false",
            letter: "",
            value: "false",
            label: tr
              ? "Yanlış"
              : "False",
          },
        ]
      : options.map((option) => ({
          ...option,
          value: option.letter,
          label: option.value,
        }));

  // =====================================================
  // OPTION CLASS
  // =====================================================

  function resultClass(
    question: QuizQuestion,
    option: string
  ) {
    if (!result) {
      return answers[question.id] === option
        ? "selected"
        : "";
    }

    const item =
      result.results.find(
        (entry) =>
          entry.question_id ===
          question.id
      );

    if (
      option ===
      item?.correct_answer
    ) {
      return "correct";
    }

    if (
      option ===
        item?.user_answer &&
      !item.is_correct
    ) {
      return "wrong";
    }

    return "";
  }

  // =====================================================
  // QUIZ EKRANI
  // =====================================================

  return (
    <section className="document-quiz-panel has-quiz">
      {busy && !quiz ? (
        <div
          className="quiz-message"
          style={{
            marginBottom: "16px",
          }}
        >
          {tr
            ? `Sınav hazırlanıyor... ${generationProgress.completed}/${generationProgress.total}`
            : `Preparing quiz... ${generationProgress.completed}/${generationProgress.total}`}
        </div>
      ) : null}

      {result ? (
        <div className="quiz-result-summary">
          <div>
            <p className="notebook-label">
              {tr
                ? "SINAV SONUCU"
                : "QUIZ RESULT"}
            </p>

            <h2>
              {result.correct} /{" "}
              {result.total_questions}{" "}
              <span>
                {tr
                  ? "doğru"
                  : "correct"}
              </span>
            </h2>
          </div>

          <strong>
            %{result.score}
          </strong>

          <div className="quiz-result-counts">
            <span>
              ✓ {result.correct}{" "}
              {tr
                ? "Doğru"
                : "Correct"}
            </span>

            <span>
              ✕ {result.wrong}{" "}
              {tr
                ? "Yanlış"
                : "Wrong"}
            </span>
          </div>
        </div>
      ) : null}

      <div className="quiz-question-header">
        <span className="notebook-label">
          {result
            ? tr
              ? "SORU İNCELEME"
              : "QUESTION REVIEW"
            : tr
            ? "SINAV"
            : "QUIZ"}
        </span>

        <span>
          {currentQuestionIndex + 1} /{" "}
          {questions.length}
        </span>
      </div>

      <h2 className="quiz-question-title">
        {currentQuestionIndex + 1}.{" "}
        {currentQuestion.question_text}
      </h2>

      {currentResult ? (
        <p
          className={`quiz-answer-state ${
            currentResult.is_correct
              ? "correct"
              : "wrong"
          }`}
        >
          {currentResult.is_correct
            ? tr
              ? "✓ Doğru"
              : "✓ Correct"
            : tr
            ? "✕ Yanlış"
            : "✕ Wrong"}
        </p>
      ) : null}

      {currentQuestion.question_type ===
      "classic" ? (
        <textarea
          className="quiz-classic-answer"
          rows={6}
          value={
            answers[currentQuestion.id] ??
            ""
          }
          disabled={Boolean(result)}
          placeholder={
            tr
              ? "Cevabını buraya yaz..."
              : "Write your answer here..."
          }
          onChange={(event) => {
            setAnswers((current) => ({
              ...current,
              [currentQuestion.id]:
                event.target.value,
            }));

            setWarning(null);
          }}
        />
      ) : (
        <div className="quiz-options">
          {renderedOptions.map(
            (option) => {
              const selected =
                answers[
                  currentQuestion.id
                ] === option.value;

              return (
                <button
                  type="button"
                  key={option.key}
                  disabled={Boolean(result)}
                  className={`quiz-option ${resultClass(
                    currentQuestion,
                    option.value
                  )}`}
                  onClick={() => {
                    setAnswers(
                      (current) => ({
                        ...current,
                        [currentQuestion.id]:
                          option.value,
                      })
                    );

                    setWarning(null);
                  }}
                >
                  <span className="quiz-radio">
                    {selected
                      ? "●"
                      : "○"}
                  </span>

                  {option.letter ? (
                    <strong>
                      {option.letter})
                    </strong>
                  ) : (
                    <strong />
                  )}

                  <span>
                    {option.label}
                  </span>
                </button>
              );
            }
          )}
        </div>
      )}

      {currentResult &&
      !currentResult.is_correct ? (
        <p className="quiz-correction">
          {tr
            ? "Doğru cevap"
            : "Correct answer"}
          :{" "}
          {currentResult.correct_answer}
        </p>
      ) : null}

      {currentResult?.explanation ? (
        <p className="quiz-explanation">
          {currentResult.explanation}
        </p>
      ) : null}

      {warning ? (
        <p
          className="quiz-message warning"
          role="alert"
        >
          {warning}
        </p>
      ) : null}

      {error ? (
        <p
          className="quiz-message error"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      <nav
        className="quiz-navigation"
        aria-label={
          tr
            ? "Sınav soruları"
            : "Quiz questions"
        }
      >
        <button
          type="button"
          disabled={currentQuestionIndex === 0}
          onClick={() =>
            setCurrentQuestionIndex(
              (index) => index - 1
            )
          }
        >
          ←{" "}
          {tr
            ? "Önceki"
            : "Previous"}
        </button>

        <span>
          {currentQuestionIndex + 1} /{" "}
          {questions.length}
        </span>

        {currentQuestionIndex <
        questions.length - 1 ? (
          <button
            type="button"
            onClick={() =>
              setCurrentQuestionIndex(
                (index) => index + 1
              )
            }
          >
            {tr
              ? "Sonraki"
              : "Next"}{" "}
            →
          </button>
        ) : result ? (
          <button
            type="button"
            onClick={restart}
          >
            {tr
              ? "Tekrar Çöz"
              : "Try Again"}
          </button>
        ) : busy ? (
          <div className="quiz-stream-waiting">
            {tr
              ? `Yeni sorular hazırlanıyor... ${generationProgress.completed}/${generationProgress.total}`
              : `Preparing more questions... ${generationProgress.completed}/${generationProgress.total}`}
          </div>
        ) : (
          <button
            type="button"
            className="finish-quiz"
            disabled={!quiz}
            onClick={submitQuiz}
          >
            {tr
              ? "Sınavı Tamamla"
              : "Finish Quiz"}
          </button>
        )}
      </nav>

      {result ? (
        <div className="quiz-result-actions">
          <button
            type="button"
            onClick={createAnother}
          >
            {tr
              ? "Yeni Sınav Oluştur"
              : "Create New Quiz"}
          </button>
        </div>
      ) : null}
    </section>
  );
}
