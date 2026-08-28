"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import QuizPanel from "@/components/documents/QuizPanel";
import { apiFetch, isAbortError, type Quiz } from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

export default function QuizSolveView({ quizId, documentId }: { quizId: string; documentId?: string }) {
  const { language } = useLanguage();
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    apiFetch<Quiz>(`/quizzes/${quizId}`, { signal: controller.signal })
      .then((result) => { setQuiz(result); setError(null); })
      .catch((cause) => {
        if (isAbortError(cause)) return;
        setError(language === "tr" ? "Sınav yüklenemedi. Lütfen tekrar deneyin." : "The quiz could not be loaded. Please try again.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [quizId, language]);

  const quizDocumentId = documentId ?? (quiz ? String(quiz.document_id) : undefined);
  const backHref = quizDocumentId ? `/quiz?document_id=${quizDocumentId}` : "/quiz";

  if (loading) return <div className="quiz-solve-page"><p className="document-detail-loading">{language === "tr" ? "Sınav yükleniyor..." : "Loading quiz..."}</p></div>;

  if (!quiz) return <div className="quiz-solve-page"><div className="document-detail-missing"><p role="alert">{error ?? (language === "tr" ? "Sınav bulunamadı." : "Quiz not found.")}</p><Link href={backHref}>← {language === "tr" ? "Sınavlara dön" : "Back to quizzes"}</Link></div></div>;

  return <div className="quiz-solve-page">
    <header className="quiz-solve-heading"><Link href={backHref}>← {language === "tr" ? "Önceki sınavlara dön" : "Back to previous quizzes"}</Link><h1>{quiz.title}</h1><p>{quiz.questions?.length ?? quiz.question_count ?? 0} {language === "tr" ? "soru" : "questions"}</p></header>
    <div className="quiz-solve-notebook document-paper document-paper-quiz"><span className="document-paper-tape" aria-hidden="true" /><span className="document-paper-holes" aria-hidden="true" /><QuizPanel documentId={String(quiz.document_id)} initialQuiz={quiz} /></div>
  </div>;
}
