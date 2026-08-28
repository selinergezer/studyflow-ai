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

const genericExplanationPatterns = [
  /Doğru cevap kaynak metindeki ilgili bilgiyle doğrudan desteklenmektedir\.?/gi,
  /The correct answer is directly supported by the relevant information in the source text\.?/gi,
];

function cleanQuizExplanation(explanation: string | null | undefined) {
  if (!explanation) return "";

  return genericExplanationPatterns
    .reduce((text, pattern) => text.replace(pattern, ""), explanation)
    .replace(/\s{2,}/g, " ")
    .trim();
}

export default function QuizPanel({
  documentId,
  sourceName = "",
  initialQuiz,
  initialResult,
  onQuizCreated,
}: {
  documentId: string;
  sourceName?: string;
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

      setQuestions((current) => {
        const incoming = created?.questions ?? [];
        if (!incoming.length) return current;

        return incoming.map((question, index) => ({
          ...current[index],
          ...question,
        }));
      });

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
        (_, index) => !answers[index]
      );

    if (firstUnansweredIndex >= 0) {
      const unansweredCount =
        quiz.questions.filter(
          (_, index) => !answers[index]
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
                  (question, index) => ({
                    question_id:
                      question.id,

                    answer:
                      answers[index],
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
            <p className="quiz-landing-kicker">
              {tr
                ? "YENİ SINAV"
                : "NEW QUIZ"}
            </p>

            <h2>
              {tr
                ? "Yeni Sınav Oluştur"
                : "Create a New Quiz"}
            </h2>

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
              <p className="quiz-builder-progress">
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
  const reviewExplanation = cleanQuizExplanation(
    currentResult?.explanation,
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
    option: string,
    questionIndex: number,
  ) {
    if (!result) {
      return answers[questionIndex] === option
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

  const totalQuestions = Math.max(
    questions.length,
    generationProgress.total,
    quiz?.question_count ?? 0,
  );
  const answeredCount = questions.filter((_, index) => {
    const answer = answers[index];
    return typeof answer === "string" && answer.trim().length > 0;
  }).length;

  return (
    <section className={`document-quiz-panel has-quiz ${result ? "is-reviewing" : ""}`}>
      <div className="quiz-solving-layout">
        <div className="quiz-question-notebook">
          <div className="quiz-notebook-rings" aria-hidden="true">
            {Array.from({ length: 13 }, (_, index) => <i key={index} />)}
          </div>

          <div className="quiz-question-topline">
            <span>{result ? (tr ? "Soru İnceleme" : "Question Review") : (tr ? "Sınav Modu: Tekrar Sınavı" : "Quiz Mode: Review Quiz")}</span>

            {!result && !busy && quiz ? (
              <button type="button" onClick={submitQuiz}>
                {tr ? "Sınavı Bitir" : "Finish Quiz"}
              </button>
            ) : null}
          </div>

          {result ? (
            <div className="quiz-result-summary">
              <div>
                <p className="notebook-label">{tr ? "SINAV SONUCU" : "QUIZ RESULT"}</p>
                <h2>{result.correct} / {result.total_questions} <span>{tr ? "doğru" : "correct"}</span></h2>
              </div>
              <strong>%{result.score}</strong>
              <div className="quiz-result-counts">
                <span>✓ {result.correct} {tr ? "Doğru" : "Correct"}</span>
                <span>✕ {result.wrong} {tr ? "Yanlış" : "Wrong"}</span>
              </div>
            </div>
          ) : null}

          <div className="quiz-question-scroll">

            {busy && !quiz ? (
              <div className="quiz-message quiz-generation-message">
                {tr
                  ? `Sınav hazırlanıyor... ${generationProgress.completed}/${generationProgress.total}`
                  : `Preparing quiz... ${generationProgress.completed}/${generationProgress.total}`}
              </div>
            ) : null}

            <div className="quiz-question-header">
              <strong>{currentQuestionIndex + 1}. {tr ? "Soru" : "Question"} / {totalQuestions}</strong>
            </div>

            <h2 className="quiz-question-title">{currentQuestion.question_text}</h2>

            {currentResult ? (
              <p className={`quiz-answer-state ${currentResult.is_correct ? "correct" : "wrong"}`}>
                {currentResult.is_correct ? (tr ? "✓ Doğru" : "✓ Correct") : (tr ? "✕ Yanlış" : "✕ Wrong")}
              </p>
            ) : null}

            {currentQuestion.question_type === "classic" ? (
              <textarea
                className="quiz-classic-answer"
                rows={6}
                value={answers[currentQuestionIndex] ?? ""}
                disabled={Boolean(result)}
                placeholder={tr ? "Cevabını buraya yaz..." : "Write your answer here..."}
                onChange={(event) => {
                  setAnswers((current) => ({ ...current, [currentQuestionIndex]: event.target.value }));
                  setWarning(null);
                }}
              />
            ) : (
              <div className="quiz-options">
                {renderedOptions.map((option) => {
                  const selected = answers[currentQuestionIndex] === option.value;

                  return (
                    <button
                      type="button"
                      key={option.key}
                      disabled={Boolean(result)}
                      className={`quiz-option ${resultClass(currentQuestion, option.value, currentQuestionIndex)}`}
                      onClick={() => {
                        setAnswers((current) => ({ ...current, [currentQuestionIndex]: option.value }));
                        setWarning(null);
                      }}
                    >
                      <strong className="quiz-option-badge">{option.letter || (option.value === "true" ? "D" : "Y")}</strong>
                      <span>{option.label}</span>
                      {selected ? <span className="quiz-option-check" aria-hidden="true">✓</span> : null}
                    </button>
                  );
                })}
              </div>
            )}

            {currentResult && !currentResult.is_correct ? (
              <p className="quiz-correction">{tr ? "Doğru cevap" : "Correct answer"}: {currentResult.correct_answer}</p>
            ) : null}

            {reviewExplanation ? <p className="quiz-explanation">{reviewExplanation}</p> : null}
            {warning ? <p className="quiz-message warning" role="alert">{warning}</p> : null}
            {error ? <p className="quiz-message error" role="alert">{error}</p> : null}
          </div>

          <nav className="quiz-navigation" aria-label={tr ? "Sınav soruları" : "Quiz questions"}>
            <button
              type="button"
              disabled={currentQuestionIndex === 0}
              onClick={() => setCurrentQuestionIndex((index) => index - 1)}
            >
              ← {tr ? "Önceki Soru" : "Previous Question"}
            </button>

            {currentQuestionIndex < questions.length - 1 ? (
              <button type="button" onClick={() => setCurrentQuestionIndex((index) => index + 1)}>
                {tr ? "Sonraki Soru" : "Next Question"} →
              </button>
            ) : result ? (
              <button type="button" onClick={restart}>{tr ? "Tekrar Çöz" : "Try Again"}</button>
            ) : busy ? (
              <span className="quiz-stream-waiting">
                {tr
                  ? `Yeni sorular hazırlanıyor... ${generationProgress.completed}/${generationProgress.total}`
                  : `Preparing more questions... ${generationProgress.completed}/${generationProgress.total}`}
              </span>
            ) : (
              <button type="button" className="finish-quiz" disabled={!quiz} onClick={submitQuiz}>
                {tr ? "Sınavı Bitir" : "Finish Quiz"}
              </button>
            )}
          </nav>
        </div>

        <aside className="quiz-solving-sidebar">
          <section className="quiz-question-list-card">
            <span className="quiz-card-tape quiz-card-tape--mint" aria-hidden="true" />
            <h2>{tr ? "Soru Listesi" : "Question List"}</h2>
            <div className="quiz-status-legend">
              <span><i className="answered" />{tr ? "Cevaplandı" : "Answered"}</span>
              <span><i />{tr ? "Cevaplanmadı" : "Unanswered"}</span>
            </div>
            <div className="quiz-question-jump-list">
              {questions.map((question, index) => {
                const answered = Boolean(answers[index]?.trim());
                return (
                  <button
                    type="button"
                    key={question.id ?? index}
                    className={`${answered ? "answered" : ""} ${index === currentQuestionIndex ? "active" : ""}`}
                    aria-current={index === currentQuestionIndex ? "step" : undefined}
                    aria-label={`${index + 1}. ${tr ? "soru" : "question"}`}
                    onClick={() => setCurrentQuestionIndex(index)}
                  >
                    {index + 1}
                  </button>
                );
              })}
            </div>
            <div className="quiz-answer-progress" aria-label={`${answeredCount} / ${totalQuestions}`}>
              <span style={{ width: `${totalQuestions ? (answeredCount / totalQuestions) * 100 : 0}%` }} />
            </div>
            <small>{answeredCount} / {totalQuestions} {tr ? "Soru" : "Questions"}</small>
          </section>

          <section className="quiz-info-card">
            <span className="quiz-card-tape" aria-hidden="true" />
            <h2>{tr ? "Sınav Bilgileri" : "Quiz Information"}</h2>
            <dl>
              <div><dt>{tr ? "Soru Sayısı" : "Questions"}</dt><dd>{totalQuestions}</dd></div>
              {quiz?.created_at ? (
                <div><dt>{tr ? "Oluşturulma" : "Created"}</dt><dd>{new Intl.DateTimeFormat(tr ? "tr-TR" : "en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(quiz.created_at))}</dd></div>
              ) : null}
              {sourceName ? (
                <div><dt>{tr ? "Kaynak" : "Source"}</dt><dd title={sourceName}>{sourceName}</dd></div>
              ) : null}
            </dl>
          </section>

          {result ? (
            <button type="button" className="quiz-create-another" onClick={createAnother}>
              {tr ? "Yeni Sınav Oluştur" : "Create New Quiz"}
            </button>
          ) : null}
        </aside>
      </div>
    </section>
  );
}
