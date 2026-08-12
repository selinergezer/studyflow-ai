"use client";

import Link from "next/link";
import DashboardIcon from "@/components/dashboard/DashboardIcon";
import type { Course, DocumentData } from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

type DashboardSectionProps = {
  courses: Course[];
  documents: DocumentData[];
  loading: boolean;
};

function documentId(document: DocumentData) {
  return document.id ?? document.document_id;
}

export function RecentCourses({ courses, documents, loading }: DashboardSectionProps) {
  const { t } = useLanguage();
  const recentCourses = [...courses]
    .sort((a, b) => {
      const latestDocument = (courseId: number) => documents
        .filter((document) => document.course_id === courseId)
        .reduce((latest, document) => Math.max(latest, document.uploaded_at ? Date.parse(document.uploaded_at) : (documentId(document) ?? 0)), 0);
      return latestDocument(b.id) - latestDocument(a.id) || b.id - a.id;
    })
    .slice(0, 3);

  return (
    <section className="dashboard-section" aria-labelledby="recent-courses-heading">
      <div className="dashboard-section-head">
        <h2 id="recent-courses-heading">{t("recentCourses")}</h2>
        <Link href="/courses">{t("viewAll")} →</Link>
      </div>
      {loading ? <p className="dashboard-loading">{t("loading")}</p> : recentCourses.length ? (
        <div className="dashboard-course-row">
          {recentCourses.map((course) => {
            const count = documents.filter((document) => document.course_id === course.id).length;
            return (
              <Link key={course.id} href={`/courses#course-${course.id}`} className="dashboard-course-card interactive-card">
                <span className="dashboard-course-tag">{t("course")}</span>
                <span className="dashboard-course-icon"><DashboardIcon name="book" /></span>
                <h3>{course.name}</h3>
                {course.description ? <p className="dashboard-course-description">{course.description}</p> : <p className="dashboard-course-description">&nbsp;</p>}
                <span className="dashboard-paper-rule" aria-hidden="true" />
                <span className="dashboard-course-foot"><span>{count} {t("documentsCount")}</span><strong>{t("open")} →</strong></span>
              </Link>
            );
          })}
        </div>
      ) : <p className="dashboard-empty">{t("noCoursesYet")}</p>}
    </section>
  );
}

export function RecentDocuments({ courses, documents, loading }: DashboardSectionProps) {
  const { t } = useLanguage();
  const courseNames = new Map(courses.map((course) => [course.id, course.name]));
  const recentDocuments = [...documents]
    .sort((a, b) => {
      const aTime = a.uploaded_at ? Date.parse(a.uploaded_at) : (documentId(a) ?? 0);
      const bTime = b.uploaded_at ? Date.parse(b.uploaded_at) : (documentId(b) ?? 0);
      return bTime - aTime;
    })
    .slice(0, 5);

  return (
    <section className="dashboard-section" aria-labelledby="recent-documents-heading">
      <div className="dashboard-section-head">
        <h2 id="recent-documents-heading">{t("recentDocuments")}</h2>
        <Link href="/library">{t("viewLibrary")} →</Link>
      </div>
      {loading ? <p className="dashboard-loading">{t("loading")}</p> : recentDocuments.length ? (
        <div className="dashboard-document-list">
          {recentDocuments.map((document) => (
            <Link key={documentId(document)} href={`/documents/${documentId(document)}`} className="dashboard-document-row interactive-row">
              <span className="dashboard-document-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
              </span>
              <span className="dashboard-document-info"><strong>{document.filename}</strong><small>{courseNames.get(document.course_id) ?? t("course")} · {document.page_count} {t("pages")}</small></span>
              <span className="dashboard-document-open">{t("open")} →</span>
            </Link>
          ))}
        </div>
      ) : <p className="dashboard-empty">{t("noDocumentsYet")}</p>}
    </section>
  );
}
