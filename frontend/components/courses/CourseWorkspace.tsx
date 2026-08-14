"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiErrorMessage, apiFetch, isAbortError, type Course, type DocumentData } from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

export default function CourseWorkspace({ courseId }: { courseId: number }) {
  const { t, language } = useLanguage();
  const [course, setCourse] = useState<Course | null>(null);
  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    Promise.all([
      apiFetch<Course[]>("/courses/", { signal: controller.signal }),
      apiFetch<DocumentData[]>("/documents/", { signal: controller.signal }),
    ])
      .then(([courseItems, documentItems]) => {
        const currentCourse = courseItems.find((item) => item.id === courseId) ?? null;
        setCourse(currentCourse);
        setDocuments(documentItems.filter((item) => item.course_id === courseId));
        setError(currentCourse ? null : language === "tr" ? "Kurs bulunamadı." : "Course not found.");
      })
      .catch((cause) => {
        if (isAbortError(cause)) return;
        setError(apiErrorMessage(cause, "Kurs çalışma alanı yüklenirken bir hata oluştu.", "Kurs şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [courseId, language]);

  function documentId(document: DocumentData) {
    return document.id ?? document.document_id;
  }

  return (
    <div className="course-workspace courses-page">
      <header className="course-workspace-heading">
        <div className="courses-glow" aria-hidden="true" />
        <Link href="/courses" className="course-workspace-back">← {language === "tr" ? "Kurslara dön" : "Back to courses"}</Link>
        <div className="course-workspace-title-row">
          <div>
            <p className="courses-eyebrow">{course?.name ?? t("courses")}</p>
            <h1>{course?.name ?? (language === "tr" ? "Kurs" : "Course")}</h1>
            <p className="courses-subtitle">{documents.length} {t("documentsCount")}</p>
          </div>
          <Link href={`/upload?courseId=${courseId}`} className="courses-primary-button">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
            {language === "tr" ? "PDF Ekle" : "Add PDF"}
          </Link>
        </div>
      </header>

      {error ? <p className="courses-error" role="alert">{error}</p> : null}
      {loading ? <p className="courses-loading">{t("loading")}</p> : course && documents.length ? (
        <section aria-labelledby="course-documents-heading">
          <h2 id="course-documents-heading" className="course-documents-title">{language === "tr" ? "Belgeler" : "Documents"}</h2>
          <div className="library-document-grid">
            {documents.map((document) => {
              const id = documentId(document);
              if (id == null) return null;
              return (
                <Link key={id} href={`/documents/${id}`} className="library-document-card interactive-card">
                  <span className="library-document-flag" aria-hidden="true" />
                  <div className="library-document-top"><span className="library-pdf-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></svg></span></div>
                  <div className="library-document-info"><strong>{document.filename}</strong><span className="library-document-meta">{document.page_count} {t("pages")}</span></div>
                  <div className="library-document-rule" />
                  <div className="library-document-footer"><span className="library-open-link">{language === "tr" ? "Aç →" : "Open →"}</span><span className="library-document-type">PDF</span></div>
                </Link>
              );
            })}
          </div>
        </section>
      ) : !error ? (
        <div className="library-empty"><p>{t("noDocumentsYet")}</p><span>{language === "tr" ? "Bu kursun ilk belgesini eklemek için PDF Ekle butonunu kullan." : "Use Add PDF to upload the first document for this course."}</span></div>
      ) : null}
    </div>
  );
}
