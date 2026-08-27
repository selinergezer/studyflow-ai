"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { apiErrorMessage, apiFetch, isAbortError, type Course, type DocumentData } from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

function CodeIllustration() {
  return (
    <div className="course-workspace-illustration" aria-hidden="true">
      <span className="course-illustration-dots" />
      <span className="course-code-sheet"><i /><i /><i /><i /><i /></span>
      <span className="course-code-token course-code-token--braces">{"{}"}</span>
      <span className="course-code-token course-code-token--tag">{"</>"}</span>
      <span className="course-code-circle" />
      <span className="course-code-quarter" />
    </div>
  );
}

function DocumentIllustration({ finance }: { finance: boolean }) {
  if (finance) {
    return (
      <svg className="course-document-art" viewBox="0 0 340 140" aria-hidden="true">
        <g className="course-finance-bars"><path d="M48 112V94h17v18M73 112V78h17v34M98 112V58h17v54M123 112V38h17v74" /></g>
        <path className="course-finance-pie-a" d="M186 69V28a41 41 0 0 1 35 20Z" />
        <path className="course-finance-pie-b" d="M186 69 221 48a41 41 0 0 1-5 48Z" />
        <path className="course-finance-pie-c" d="M186 69 216 96a41 41 0 0 1-68-18Z" />
        <path className="course-finance-line" d="M246 91c18-26 29 18 45-7s25-41 44-21" />
        <g className="course-finance-nodes"><circle cx="246" cy="91" r="4"/><circle cx="275" cy="84" r="4"/><circle cx="307" cy="61" r="4"/><circle cx="335" cy="63" r="4"/></g>
      </svg>
    );
  }

  return (
    <svg className="course-document-art" viewBox="0 0 340 140" aria-hidden="true">
      <g className="course-model-lines"><path d="M43 71 111 111 179 72 247 111 313 69"/><path d="M111 111 111 54M179 72 179 35M247 111 247 82"/></g>
      <g className="course-model-nodes"><circle cx="43" cy="71" r="6"/><circle cx="111" cy="111" r="6"/><circle cx="179" cy="35" r="6"/><circle cx="179" cy="72" r="6"/><circle cx="247" cy="111" r="6"/><circle cx="313" cy="69" r="6"/></g>
      <path className="course-model-cube-a" d="m123 52 40-24 40 24-40 24Z" />
      <path className="course-model-cube-b" d="m123 52 40 24v48l-40-24Z" />
      <path className="course-model-cube-c" d="m203 52-40 24v48l40-24Z" />
    </svg>
  );
}

export default function CourseWorkspace({ courseId }: { courseId: number }) {
  const { t, language } = useLanguage();
  const languageRef = useRef(language);

  useEffect(() => {
    languageRef.current = language;
  }, [language]);
  const [course, setCourse] = useState<Course | null>(null);
  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [view, setView] = useState<"grid" | "list">("grid");
  const [sortOrder, setSortOrder] = useState("recent");

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
        setError(currentCourse ? null : languageRef.current === "tr" ? "Kurs bulunamadı." : "Course not found.");
      })
      .catch((cause) => {
        if (isAbortError(cause)) return;
        setError(apiErrorMessage(cause, "Kurs çalışma alanı yüklenirken bir hata oluştu.", "Kurs şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [courseId]);

  function documentId(document: DocumentData) {
    return document.id ?? document.document_id;
  }

  const visibleDocuments = [...documents]
    .filter((document) => document.filename.toLocaleLowerCase(language === "tr" ? "tr-TR" : "en-US").includes(query.trim().toLocaleLowerCase(language === "tr" ? "tr-TR" : "en-US")))
    .sort((a, b) => {
      const aId = documentId(a) ?? 0;
      const bId = documentId(b) ?? 0;
      return sortOrder === "oldest" ? aId - bId : bId - aId;
    });

  return (
    <div className="course-workspace">
      <header className="course-workspace-hero">
        <div className="course-workspace-copy">
          <Link href="/courses" className="course-workspace-back">← {language === "tr" ? "Kurslara dön" : "Back to courses"}</Link>
          <p className="course-workspace-eyebrow">{course?.name ?? t("courses")}</p>
          <h1>{course?.name ?? (language === "tr" ? "Kurs" : "Course")}</h1>
          <p className="course-workspace-description">{course?.description || (language === "tr" ? "Yazılım geliştirme süreçleri, algoritmalar, veri yapıları ve daha fazlası." : "Software development processes, algorithms, data structures, and more.")}</p>
          <div className="course-workspace-stat">
            <span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h5"/></svg></span>
            <strong>{documents.length}</strong>
            <small>{language === "tr" ? "Belge" : "Documents"}</small>
          </div>
        </div>
        <CodeIllustration />
        <div className="course-workspace-action">
          <Link href={`/upload?courseId=${courseId}`} className="courses-primary-button">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
            {language === "tr" ? "PDF Ekle" : "Add PDF"}
          </Link>
        </div>
      </header>

      {error ? <p className="courses-error" role="alert">{error}</p> : null}
      {loading ? <p className="courses-loading">{t("loading")}</p> : course && documents.length ? (
        <section className="course-documents-panel" aria-labelledby="course-documents-heading">
          <div className="course-documents-toolbar">
            <h2 id="course-documents-heading">{language === "tr" ? "Belgeler" : "Documents"}</h2>
            <label className="course-documents-search">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg>
              <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={language === "tr" ? "Belgelerde ara..." : "Search documents..."} />
            </label>
            <div className="course-documents-view" aria-label={language === "tr" ? "Görünüm" : "View"}>
              <button type="button" className={view === "grid" ? "active" : ""} onClick={() => setView("grid")} aria-label="Grid"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"/></svg></button>
              <button type="button" className={view === "list" ? "active" : ""} onClick={() => setView("list")} aria-label="List"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/></svg></button>
            </div>
            <select className="course-documents-sort" value={sortOrder} onChange={(event) => setSortOrder(event.target.value)} aria-label={language === "tr" ? "Belgeleri sırala" : "Sort documents"}>
              <option value="recent">{language === "tr" ? "Son eklenen" : "Most recent"}</option>
              <option value="oldest">{language === "tr" ? "En eski" : "Oldest"}</option>
            </select>
          </div>
          <div className={`course-document-grid course-document-grid--${view}`}>
            {visibleDocuments.map((document) => {
              const id = documentId(document);
              if (id == null) return null;
              const finance = /ekonomi|finans|econom|finance/i.test(document.filename);
              return (
                <Link key={id} href={`/documents/${id}`} className="course-document-card interactive-card">
                  <span className="course-document-tape" aria-hidden="true" />
                  <span className="course-document-visual">
                    <span className="course-document-pdf"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg><small>PDF</small></span>
                    <DocumentIllustration finance={finance} />
                  </span>
                  <span className="course-document-body">
                    <strong title={document.filename}>{document.filename}</strong>
                    <span className="course-document-meta">{document.page_count} {t("pages")}</span>
                    <span className="course-document-rule" />
                    <span className="course-document-footer"><span>{language === "tr" ? "Aç →" : "Open →"}</span><b>PDF</b></span>
                  </span>
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
