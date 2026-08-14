"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  apiErrorMessage,
  apiFetch,
  type Course,
  type DocumentData,
} from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

type ChatResponse = {
  document_id: number;
  question: string;
  answer: string;
};

export default function AskAiView() {
  const { t, language } = useLanguage();
  const documentsLoadFailed = t("documentsLoadFailed");
  const backendUnavailable = t("backendUnavailable");
  const [courses, setCourses] = useState<Course[]>([]);
  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [courseId, setCourseId] = useState("");
  const [documentId, setDocumentId] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");

  const [loading, setLoading] = useState(true);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const [courseData, documentData] = await Promise.all([
          apiFetch<Course[]>("/courses/"),
          apiFetch<DocumentData[]>("/documents/"),
        ]);

        setCourses(courseData);
        setDocuments(documentData);

        if (courseData.length > 0) {
          const initialCourseId = String(courseData[0].id);
          const initialDocument = documentData.find(
            (document) => String(document.course_id) === initialCourseId,
          );
          setCourseId(initialCourseId);
          setDocumentId(initialDocument ? String(initialDocument.id ?? initialDocument.document_id) : "");
        }
      } catch (cause) {
        setError(
          apiErrorMessage(
            cause,
            documentsLoadFailed,
            backendUnavailable,
          ),
        );
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, [language, documentsLoadFailed, backendUnavailable]);

  const filteredDocuments = useMemo(() => {
    if (!courseId) return [];

    return documents.filter(
      (document) => String(document.course_id) === courseId,
    );
  }, [documents, courseId]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!documentId) {
      setError(t("selectDocumentFirst"));
      return;
    }
    if (!question.trim()) {
      setError(t("questionCannotBeEmpty"));
      return;
    }

    setAsking(true);
    setError(null);
    setAnswer("");

    try {
      const result = await apiFetch<ChatResponse>("/chat/", {
        method: "POST",
        body: JSON.stringify({
          document_id: Number(documentId),
          question: question.trim(),
        }),
      });

      setAnswer(result.answer);
    } catch (cause) {
      setError(
        apiErrorMessage(
          cause,
          t("aiAnswerFailed"),
          t("aiUnavailable"),
        ),
      );
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <div className="mb-8">
        <p className="mb-3 text-xs font-semibold tracking-widest">
          {t("aiAssistant")}
        </p>

        <h1 className="text-4xl font-bold">
          {t("askAi")}
        </h1>

        <p className="mt-3 opacity-70">
          {t("askAiIntro")}
        </p>
      </div>

      <div className="rounded-xl border p-6">
        {loading ? (
          <p>{t("documentsLoading")}</p>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="mb-2 block font-semibold">
                {t("course")}
              </label>

              <select
                value={courseId}
                onChange={(event) => {
                  const nextCourseId = event.target.value;
                  const firstDocument = documents.find(
                    (document) => String(document.course_id) === nextCourseId,
                  );
                  setCourseId(nextCourseId);
                  setDocumentId(firstDocument ? String(firstDocument.id ?? firstDocument.document_id) : "");
                  setAnswer("");
                }}
                className="w-full rounded-lg border bg-transparent p-3"
              >
                <option value="">{t("selectCourse")}</option>

                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-2 block font-semibold">
                PDF
              </label>

              <select
                value={documentId}
                onChange={(event) => {
                  setDocumentId(event.target.value);
                  setAnswer("");
                }}
                className="w-full rounded-lg border bg-transparent p-3"
                disabled={!courseId}
              >
                <option value="">{t("selectPdf")}</option>

                {filteredDocuments.map((document) => {
                  const id = document.id ?? document.document_id;

                  return (
                    <option key={id} value={id}>
                      {document.filename}
                    </option>
                  );
                })}
              </select>
            </div>

            <div>
              <label className="mb-2 block font-semibold">
                {t("question")}
              </label>

              <textarea
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder={t("askAiPlaceholder")}
                rows={5}
                className="w-full resize-none rounded-lg border bg-transparent p-4"
              />
            </div>

            {error && (
              <div className="rounded-lg border border-red-400 p-3 text-red-400">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={asking || !documentId || !question.trim()}
              className="rounded-lg bg-[#e8a33d] px-5 py-3 font-semibold text-black disabled:opacity-50"
            >
              {asking ? t("generatingAnswer") : t("ask")}
            </button>
          </form>
        )}
      </div>

      {answer && (
        <div className="mt-6 rounded-xl border p-6">
          <p className="mb-3 text-xs font-bold tracking-widest">
            STUDYFLOW AI
          </p>

          <p className="whitespace-pre-wrap leading-7">
            {answer}
          </p>
        </div>
      )}
    </div>
  );
}
