"use client";

import { useEffect, useState } from "react";
import Button from "@/components/ui/Button";
import { apiFetch, type Quiz, type QuizQuestion } from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

type Difficulty = "easy" | "medium" | "hard";
type ResultItem = { question_id: number; user_answer: string | null; correct_answer: string; is_correct: boolean; explanation: string | null };
type QuizResult = { total_questions: number; correct: number; wrong: number; score: number; results: ResultItem[] };

const optionKeys = ["option_a", "option_b", "option_c", "option_d", "option_e"] as const;
const letters = ["A", "B", "C", "D", "E"];

export default function QuizPanel({ documentId, initialQuiz, initialResult, onQuizCreated }: { documentId: string; initialQuiz?: Quiz | null; initialResult?: QuizResult | null; onQuizCreated?: (quiz: Quiz) => void }) {
  const { language } = useLanguage();
  const tr = language === "tr";
  const [questionCount, setQuestionCount] = useState(10);
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [quiz, setQuiz] = useState<Quiz | null>(initialQuiz ?? null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [result, setResult] = useState<QuizResult | null>(initialResult ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  const questions = quiz?.questions ?? [];
  const currentQuestion = questions[currentIndex];

  useEffect(() => {
    setQuiz(initialQuiz ?? null);
    setCurrentIndex(0);
    setAnswers({});
    setResult(initialResult ?? null);
    setWarning(null);
    setError(null);
  }, [initialQuiz, initialResult]);

  async function generateQuiz() {
    setBusy(true); setError(null); setWarning(null); setResult(null); setAnswers({}); setCurrentIndex(0);
    try { const created = await apiFetch<Quiz>(`/quizzes/generate?document_id=${documentId}&question_count=${questionCount}&difficulty=${difficulty}`, { method: "POST" }); setQuiz(created); onQuizCreated?.(created); }
    catch (cause) { console.error(cause); setError(tr ? "Veriler şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin." : "Data is currently unavailable. Please try again later."); }
    finally { setBusy(false); }
  }

  async function submitQuiz() {
    if (!quiz?.questions) return;
    const firstUnansweredIndex = quiz.questions.findIndex((question) => !answers[question.id]);
    if (firstUnansweredIndex >= 0) {
      const unansweredCount = quiz.questions.filter((question) => !answers[question.id]).length;
      setWarning(tr ? `${unansweredCount} soruyu henüz cevaplamadınız.` : `${unansweredCount} questions are unanswered.`);
      setCurrentIndex(firstUnansweredIndex);
      return;
    }
    setBusy(true); setWarning(null); setError(null);
    try { setResult(await apiFetch<QuizResult>(`/quizzes/${quiz.quiz_id ?? quiz.id}/submit`, { method: "POST", body: JSON.stringify({ answers: quiz.questions.map((question) => ({ question_id: question.id, answer: answers[question.id] })) }) })); }
    catch (cause) { console.error(cause); setError(tr ? "Veriler şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin." : "Data is currently unavailable. Please try again later."); }
    finally { setBusy(false); }
  }

  function restart() { setAnswers({}); setResult(null); setWarning(null); setCurrentIndex(0); }
  function createAnother() { setQuiz(null); setAnswers({}); setResult(null); setWarning(null); setCurrentIndex(0); }

  if (!quiz || !currentQuestion) {
    return <section className="document-quiz-panel is-setup">
      <div className="quiz-builder">
        <div className="quiz-builder-panel">
          <p className="notebook-label">{tr ? "SINAV HAZIRLA" : "PREPARE A QUIZ"}</p>
          <p className="quiz-builder-description">{tr ? "Bu PDF'den kendine özel bir tekrar sınavı oluştur." : "Create a custom review quiz from this PDF."}</p>
          <fieldset className="quiz-setting"><legend>{tr ? "Soru sayısı" : "Question count"}</legend><div className="choice-row">{[5, 10, 15, 20].map((count) => <button key={count} type="button" className={`choice ${questionCount === count ? "active" : ""}`} aria-pressed={questionCount === count} onClick={() => setQuestionCount(count)}>{count}</button>)}</div></fieldset>
          <fieldset className="quiz-setting"><legend>{tr ? "Zorluk seviyesi" : "Difficulty"}</legend><div className="choice-row">{([{ value: "easy", tr: "Kolay", en: "Easy" }, { value: "medium", tr: "Orta", en: "Medium" }, { value: "hard", tr: "Zor", en: "Hard" }] as const).map((option) => <button key={option.value} type="button" className={`choice ${difficulty === option.value ? "active" : ""}`} aria-pressed={difficulty === option.value} onClick={() => setDifficulty(option.value)}>{tr ? option.tr : option.en}</button>)}</div></fieldset>
          <Button className="quiz-create-button" onClick={generateQuiz} disabled={busy}>{busy ? (tr ? "Sınav hazırlanıyor..." : "Preparing quiz...") : (tr ? "Sınavı Oluştur →" : "Create Quiz →")}</Button>
        </div>
        <aside className="quiz-note" aria-hidden="true"><div className="quiz-doodle"><span>✓</span><i>?</i></div><p>{tr ? <>Soru sayısını ve zorluk seviyesini seç,<br />hemen sınavını oluştur!</> : <>Choose the number and difficulty,<br />then start your quiz!</>}</p><div className="hand-underline" /></aside>
      </div>
      {error ? <p className="quiz-message error" role="alert">{error}</p> : null}
    </section>;
  }

  const currentResult = result?.results.find((entry) => entry.question_id === currentQuestion.id);
  const options = optionKeys.map((key, index) => ({ key, letter: letters[index], value: currentQuestion[key] })).filter((option): option is { key: typeof optionKeys[number]; letter: string; value: string } => typeof option.value === "string" && option.value.trim().length > 0);
  const renderedOptions = currentQuestion.question_type === "true_false"
    ? [{ key: "true", letter: "", value: "true", label: tr ? "Doğru" : "True" }, { key: "false", letter: "", value: "false", label: tr ? "Yanlış" : "False" }]
    : options.map((option) => ({ ...option, label: option.value }));

  function resultClass(question: QuizQuestion, option: string) {
    if (!result) return answers[question.id] === option ? "selected" : "";
    const item = result.results.find((entry) => entry.question_id === question.id);
    if (option === item?.correct_answer) return "correct";
    if (option === item?.user_answer && !item.is_correct) return "wrong";
    return "";
  }

  return <section className="document-quiz-panel has-quiz">
    {result ? <div className="quiz-result-summary"><div><p className="notebook-label">{tr ? "SINAV SONUCU" : "QUIZ RESULT"}</p><h2>{result.correct} / {result.total_questions} <span>{tr ? "doğru" : "correct"}</span></h2></div><strong>%{result.score}</strong><div className="quiz-result-counts"><span>✓ {result.correct} {tr ? "Doğru" : "Correct"}</span><span>✕ {result.wrong} {tr ? "Yanlış" : "Wrong"}</span></div></div> : null}
    <div className="quiz-question-header"><span className="notebook-label">{result ? (tr ? "SORU İNCELEME" : "QUESTION REVIEW") : (tr ? "SINAV" : "QUIZ")}</span><span>{currentIndex + 1} / {questions.length}</span></div>
    <h2 className="quiz-question-title">{currentIndex + 1}. {currentQuestion.question_text}</h2>
    {currentResult ? <p className={`quiz-answer-state ${currentResult.is_correct ? "correct" : "wrong"}`}>{currentResult.is_correct ? (tr ? "✓ Doğru" : "✓ Correct") : (tr ? "✕ Yanlış" : "✕ Wrong")}</p> : null}
    {currentQuestion.question_type === "classic" ? <textarea className="quiz-classic-answer" rows={6} value={answers[currentQuestion.id] ?? ""} disabled={Boolean(result)} placeholder={tr ? "Cevabını buraya yaz..." : "Write your answer here..."} onChange={(event) => { setAnswers((current) => ({ ...current, [currentQuestion.id]: event.target.value })); setWarning(null); }} /> : <div className="quiz-options">{renderedOptions.map((option) => { const selected = answers[currentQuestion.id] === option.value; return <button type="button" key={option.key} disabled={Boolean(result)} className={`quiz-option ${resultClass(currentQuestion, option.value)}`} onClick={() => { setAnswers((current) => ({ ...current, [currentQuestion.id]: option.value })); setWarning(null); }}><span className="quiz-radio">{selected ? "●" : "○"}</span>{option.letter ? <strong>{option.letter})</strong> : <strong /> }<span>{option.label}</span></button>; })}</div>}
    {currentResult && !currentResult.is_correct ? <p className="quiz-correction">{tr ? "Doğru cevap" : "Correct answer"}: {letters[optionKeys.findIndex((key) => currentQuestion[key] === currentResult.correct_answer)] ?? "–"}</p> : null}
    {currentResult?.explanation ? <p className="quiz-explanation">{currentResult.explanation}</p> : null}
    {warning ? <p className="quiz-message warning" role="alert">{warning}</p> : null}{error ? <p className="quiz-message error" role="alert">{error}</p> : null}
    <nav className="quiz-navigation" aria-label={tr ? "Sınav soruları" : "Quiz questions"}><button type="button" disabled={currentIndex === 0 || busy} onClick={() => setCurrentIndex((index) => index - 1)}>← {tr ? "Önceki" : "Previous"}</button><span>{currentIndex + 1} / {questions.length}</span>{currentIndex < questions.length - 1 ? <button type="button" disabled={busy} onClick={() => setCurrentIndex((index) => index + 1)}>{tr ? "Sonraki" : "Next"} →</button> : result ? <button type="button" onClick={restart}>{tr ? "Tekrar Çöz" : "Try Again"}</button> : <button type="button" className="finish-quiz" disabled={busy} onClick={submitQuiz}>{busy ? (tr ? "Sonuçlar hesaplanıyor..." : "Calculating results...") : (tr ? "Sınavı Tamamla" : "Finish Quiz")}</button>}</nav>
    {result ? <div className="quiz-result-actions"><button type="button" onClick={createAnother}>{tr ? "Yeni Sınav Oluştur" : "Create New Quiz"}</button></div> : null}
  </section>;
}
