"use client";

import { FormEvent, useState } from "react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import type { StudyDocument } from "@/lib/mock-data";
import { useLanguage } from "@/providers/LanguageProvider";
import type { TranslationKey } from "@/lib/translations";

type Tab = "Summary" | "Quiz" | "Flashcards" | "Ask AI";

const tabs: Tab[] = ["Summary", "Quiz", "Flashcards", "Ask AI"];
const tabLabels: Record<Tab, TranslationKey> = { Summary: "summary", Quiz: "quiz", Flashcards: "flashcards", "Ask AI": "askAiTab" };

export default function DocumentWorkspace({ document }: { document: StudyDocument }) {
  const [activeTab, setActiveTab] = useState<Tab>("Summary");
  const [question, setQuestion] = useState("");
  const [submittedQuestion, setSubmittedQuestion] = useState<string | null>(null);
  const [generated, setGenerated] = useState<"quiz" | "flashcards" | null>(null);
  const { t, language } = useLanguage();
  const uploadedAt = new Intl.DateTimeFormat(language === "tr" ? "tr-TR" : "en-US", { day: "numeric", month: "short", year: "numeric" }).format(new Date(`${document.uploadedAt}T00:00:00`));

  function generate(type: "quiz" | "flashcards") {
    // Backend integration point: request generated study content for document.id.
    console.info(`Generate ${type} for document:`, document.id);
    setGenerated(type);
  }

  function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = question.trim();
    if (!value) return;
    // Backend integration point: send the question with document.id as context.
    console.info("Document question submitted:", { documentId: document.id, question: value });
    setSubmittedQuestion(value);
    setQuestion("");
  }

  return (
    <div className="mx-auto max-w-5xl px-5 py-10 sm:px-8 sm:py-14">
      <header className="animate-enter">
        <div className="flex items-start gap-4">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-red-50 text-red-600" aria-hidden="true">
            <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M7 3.75h6.5L18 8.25v12H7V3.75Zm6.25.5V8.5h4.25" /></svg>
          </span>
          <div className="min-w-0">
            <p className="text-sm text-gray-500">{document.course}</p>
            <h1 className="mt-1 truncate text-2xl font-semibold tracking-[-0.035em] text-gray-950 sm:text-3xl">{document.name}</h1>
            <p className="mt-2 text-xs text-gray-400">{document.pageCount} {t("pages")} · {document.size} · {t("uploaded")} {uploadedAt}</p>
          </div>
        </div>
      </header>

      <div className="animate-enter mt-9 overflow-x-auto border-b border-gray-200 [animation-delay:40ms]" role="tablist" aria-label={t("documentTools")}>
        <div className="flex min-w-max gap-6">
          {tabs.map((tab) => {
            const active = activeTab === tab;
            return (
              <button key={tab} type="button" role="tab" aria-selected={active} onClick={() => setActiveTab(tab)} className={`relative pb-3 text-sm transition focus-visible:outline-2 focus-visible:outline-blue-600 ${active ? "font-medium text-gray-950 after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:bg-blue-600" : "text-gray-500 hover:text-gray-900"}`}>
                {t(tabLabels[tab])}
              </button>
            );
          })}
        </div>
      </div>

      <Card className="animate-enter mt-7 min-h-[390px] p-6 [animation-delay:80ms] sm:p-8">
        {activeTab === "Summary" ? (
          <article className="max-w-3xl">
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-gray-400">{t("documentSummary")}</p>
            <h2 className="mt-4 text-xl font-semibold tracking-[-0.025em] text-gray-950">{t("overview")}</h2>
            <p className="mt-3 text-[15px] leading-7 text-gray-600">{t("summaryOverview")}</p>
            <h3 className="mt-8 text-sm font-semibold text-gray-950">{t("keyPoints")}</h3>
            <ul className="mt-4 space-y-3">
              {(["summaryPoint1", "summaryPoint2", "summaryPoint3", "summaryPoint4"] as TranslationKey[]).map((point) => (
                <li key={point} className="flex gap-3 text-sm leading-6 text-gray-600">
                  <span className="mt-2.5 size-1.5 shrink-0 rounded-full bg-blue-600" aria-hidden="true" />
                  {t(point)}
                </li>
              ))}
            </ul>
          </article>
        ) : null}

        {activeTab === "Quiz" ? (
          <div className="flex min-h-72 flex-col items-center justify-center text-center">
            <h2 className="text-lg font-semibold text-gray-950">{t("testUnderstanding")}</h2>
            <p className="mt-2 max-w-md text-sm leading-6 text-gray-500">{t("testDesc")}</p>
            <Button className="mt-6" onClick={() => generate("quiz")}>{t("generateQuiz")}</Button>
            {generated === "quiz" ? <p className="mt-4 text-sm text-green-600" role="status">{t("quizCreated")}</p> : null}
          </div>
        ) : null}

        {activeTab === "Flashcards" ? (
          <div className="flex min-h-72 flex-col items-center justify-center text-center">
            <h2 className="text-lg font-semibold text-gray-950">{t("reviewEssentials")}</h2>
            <p className="mt-2 max-w-md text-sm leading-6 text-gray-500">{t("flashcardsDesc")}</p>
            <Button className="mt-6" onClick={() => generate("flashcards")}>{t("generateFlashcards")}</Button>
            {generated === "flashcards" ? <p className="mt-4 text-sm text-green-600" role="status">{t("flashcardsCreated")}</p> : null}
          </div>
        ) : null}

        {activeTab === "Ask AI" ? (
          <div className="flex min-h-72 flex-col">
            <div className="flex-1">
              <h2 className="text-lg font-semibold text-gray-950">{t("askDocument")}</h2>
              <p className="mt-2 text-sm leading-6 text-gray-500">{t("askDocumentDesc")}</p>
              {submittedQuestion ? <div className="mt-6 rounded-2xl bg-gray-50 p-4 text-sm leading-6 text-gray-700">{submittedQuestion}</div> : null}
            </div>
            <form onSubmit={submitQuestion} className="mt-8 flex items-end gap-3">
              <div className="flex-1">
                <label htmlFor="document-question" className="sr-only">{t("askQuestion")}</label>
                <input id="document-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={t("askPlaceholder")} className="h-11 w-full rounded-xl border border-gray-200 bg-white px-3.5 text-sm text-gray-900 outline-none transition placeholder:text-gray-400 hover:border-gray-300 focus:border-blue-600 focus:ring-4 focus:ring-blue-600/10" />
              </div>
              <Button type="submit" disabled={!question.trim()}>{t("send")}</Button>
            </form>
          </div>
        ) : null}
      </Card>
    </div>
  );
}
