"use client";

import { useState } from "react";
import Button from "@/components/ui/Button";
import { apiFetch, type Quiz, type QuizQuestion } from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

type Difficulty = "easy" | "medium" | "hard";
type ResultItem = { question_id: number; user_answer: string | null; correct_answer: string; is_correct: boolean; explanation: string | null };
type QuizResult = { total_questions: number; correct: number; wrong: number; score: number; results: ResultItem[] };

const optionKeys = ["option_a", "option_b", "option_c", "option_d", "option_e"] as const;
const letters = ["A", "B", "C", "D", "E"];

export default function QuizPanel({

  documentId,

  initialQuiz,

  initialResult,

}: {

  documentId: string;

  initialQuiz?: Quiz | null;

  initialResult?: QuizResult | null;

}) {
  const { language, t } = useLanguage();
  const [questionCount, setQuestionCount] = useState(10);
  const [difficulty, setDifficulty] = useState<Difficulty>("medium");
  const [quiz, setQuiz] = useState<Quiz | null>(initialQuiz ?? null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [result, setResult] = useState<QuizResult | null>(initialResult ?? null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  async function generateQuiz() {
    setBusy(true); setError(null); setWarning(null); setResult(null); setAnswers({});
    try { setQuiz(await apiFetch<Quiz>(`/quizzes/generate?document_id=${documentId}&question_count=${questionCount}&difficulty=${difficulty}`, { method: "POST" })); }
    catch (cause) { console.error(cause); setError(cause instanceof Error ? cause.message : "İşlem sırasında bir hata oluştu."); }
    finally { setBusy(false); }
  }

  async function submitQuiz() {
    if (!quiz?.questions) return;
    const unanswered = quiz.questions.filter((question) => !answers[question.id]);
    if (unanswered.length) {
      setWarning(language === "tr" ? `${unanswered.length} soruyu henüz cevaplamadınız.` : `${unanswered.length} questions are unanswered.`);
      document.getElementById(`quiz-question-${unanswered[0].id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
      return;
    }
    setBusy(true); setWarning(null); setError(null);
    try { setResult(await apiFetch<QuizResult>(`/quizzes/${quiz.quiz_id ?? quiz.id}/submit`, { method: "POST", body: JSON.stringify({ answers: quiz.questions.map((question) => ({ question_id: question.id, answer: answers[question.id] })) }) })); }
    catch (cause) { console.error(cause); setError(cause instanceof Error ? cause.message : "İşlem sırasında bir hata oluştu."); }
    finally { setBusy(false); }
  }

  function optionClass(question: QuizQuestion, option: string) {
    if (!result) return "border-gray-200 text-gray-600";
    const item = result.results.find((entry) => entry.question_id === question.id);
    if (option === item?.correct_answer) return "border-green-300 bg-green-50 text-green-700";
    if (option === item?.user_answer && !item.is_correct) return "border-red-300 bg-red-50 text-red-700";
    return "border-gray-200 text-gray-500";
  }

  return <section>
    {!quiz ? <div className="flex flex-wrap items-end gap-4"><label className="text-sm text-gray-700">{language === "tr" ? "Soru sayısı" : "Question count"}<select value={questionCount} onChange={(e) => setQuestionCount(Number(e.target.value))} className="mt-2 block h-11 rounded-xl border border-gray-200 bg-white px-3"><option>5</option><option>10</option><option>15</option><option>20</option></select></label><label className="text-sm text-gray-700">{language === "tr" ? "Zorluk" : "Difficulty"}<select value={difficulty} onChange={(e) => setDifficulty(e.target.value as Difficulty)} className="mt-2 block h-11 rounded-xl border border-gray-200 bg-white px-3"><option value="easy">{language === "tr" ? "Kolay" : "Easy"}</option><option value="medium">{language === "tr" ? "Orta" : "Medium"}</option><option value="hard">{language === "tr" ? "Zor" : "Hard"}</option></select></label><Button onClick={generateQuiz} disabled={busy}>{busy ? "Quiz oluşturuluyor..." : t("generateQuiz")}</Button></div> : null}
    {error ? <p className="mt-4 text-sm text-red-600">{error}</p> : null}{warning ? <p className="mt-4 text-sm text-amber-600">{warning}</p> : null}
    {result ? <div className="mt-6 rounded-2xl bg-gray-50 p-5"><h2 className="text-lg font-semibold text-gray-950">{language === "tr" ? "Quiz Tamamlandı" : "Quiz Completed"}</h2><p className="mt-3 text-sm text-gray-700">{result.correct} / {result.total_questions} {language === "tr" ? "Doğru" : "Correct"}</p><p className="mt-1 text-sm text-gray-700">{result.wrong} {language === "tr" ? "Yanlış" : "Wrong"}</p><p className="mt-1 font-medium text-gray-950">{language === "tr" ? "Başarı" : "Score"}: %{result.score}</p></div> : null}
    {quiz?.questions?.map((question, index) => { const item = result?.results.find((entry) => entry.question_id === question.id); return <div id={`quiz-question-${question.id}`} key={question.id} className="mt-6 border-t border-gray-100 pt-5"><p className="font-medium text-gray-950">{index + 1}. {question.question_text}</p>{item ? <p className={`mt-2 text-sm font-medium ${item.is_correct ? "text-green-600" : "text-red-600"}`}>{item.is_correct ? "✓ Doğru" : "✗ Yanlış"}</p> : null}<div className="mt-3 space-y-2">{optionKeys.map((key, optionIndex) => { const option = question[key]; return <label key={key} className={`flex gap-3 rounded-xl border p-3 text-sm ${optionClass(question, option)}`}><input type="radio" name={`q-${question.id}`} checked={answers[question.id] === option} disabled={Boolean(result)} onChange={() => setAnswers((current) => ({ ...current, [question.id]: option }))} /><span>{letters[optionIndex]}) {option}</span></label>; })}</div>{item && !item.is_correct ? <p className="mt-3 text-sm text-gray-600">{language === "tr" ? "Senin cevabın" : "Your answer"}: {letters[optionKeys.findIndex((key) => question[key] === item.user_answer)] || "-"} · {language === "tr" ? "Doğru cevap" : "Correct answer"}: {letters[optionKeys.findIndex((key) => question[key] === item.correct_answer)]}</p> : null}{item?.explanation ? <p className="mt-2 text-sm text-gray-500">{item.explanation}</p> : null}</div>; })}
    {quiz?.questions?.length && !result ? <Button className="mt-6" onClick={submitQuiz} disabled={busy}>{busy ? (language === "tr" ? "Değerlendiriliyor..." : "Submitting...") : (language === "tr" ? "Quizi Tamamla" : "Submit Quiz")}</Button> : null}
    {result ? <div className="mt-6 flex flex-wrap gap-3"><Button variant="secondary" onClick={() => { setAnswers({}); setResult(null); setWarning(null); }}>{language === "tr" ? "Tekrar Çöz" : "Try Again"}</Button><Button onClick={() => { setQuiz(null); setAnswers({}); setResult(null); }}>{language === "tr" ? "Yeni Quiz Oluştur" : "Create New Quiz"}</Button></div> : null}
  </section>;
}
