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
    <section aria-labelledby="recent-courses-heading">
      <div className="flex items-center justify-between">
        <h2 id="recent-courses-heading" className="text-sm font-semibold text-gray-950">{t("recentCourses")}</h2>
        <Link href="/courses" className="text-sm text-gray-500 transition hover:text-gray-900">{t("viewAll")}</Link>
      </div>
      {loading ? <p className="mt-4 text-sm text-gray-500">{t("loading")}</p> : recentCourses.length ? (
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {recentCourses.map((course) => {
            const count = documents.filter((document) => document.course_id === course.id).length;
            return (
              <Link key={course.id} href={`/courses#course-${course.id}`} className="group rounded-2xl bg-white p-5 ring-1 ring-gray-200 transition duration-200 hover:-translate-y-0.5 hover:ring-gray-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">
                <span className="flex size-9 items-center justify-center rounded-xl bg-gray-100 text-gray-700"><DashboardIcon name="book" /></span>
                <h3 className="mt-5 text-sm font-medium text-gray-950">{course.name}</h3>
                {course.description ? <p className="mt-1.5 line-clamp-2 text-xs text-gray-500">{course.description}</p> : null}
                <p className="mt-3 text-xs text-gray-500">{count} {t("documentsCount")}</p>
                <span className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-blue-600">{t("open")} <span className="transition-transform group-hover:translate-x-0.5">→</span></span>
              </Link>
            );
          })}
        </div>
      ) : <p className="mt-4 rounded-2xl bg-white p-5 text-sm text-gray-500 ring-1 ring-gray-200">{t("noCoursesYet")}</p>}
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
    <section aria-labelledby="recent-documents-heading">
      <div className="flex items-center justify-between">
        <h2 id="recent-documents-heading" className="text-sm font-semibold text-gray-950">{t("recentDocuments")}</h2>
        <Link href="/library" className="text-sm text-gray-500 transition hover:text-gray-900">{t("viewLibrary")}</Link>
      </div>
      {loading ? <p className="mt-4 text-sm text-gray-500">{t("loading")}</p> : recentDocuments.length ? (
        <div className="mt-4 overflow-hidden rounded-2xl bg-white ring-1 ring-gray-200">
          {recentDocuments.map((document, index) => (
            <Link key={documentId(document)} href={`/documents/${documentId(document)}`} className={`group flex items-center gap-4 p-4 transition hover:bg-gray-50 sm:p-5 ${index ? "border-t border-gray-100" : ""}`}>
              <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-red-50 text-red-600" aria-hidden="true">
                <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M7 3.75h6.5L18 8.25v12H7V3.75Zm6.25.5V8.5h4.25" /></svg>
              </span>
              <div className="min-w-0 flex-1">
                <h3 className="truncate text-sm font-medium text-gray-950">{document.filename}</h3>
                <p className="mt-1 text-xs text-gray-500">{courseNames.get(document.course_id) ?? t("course")} · {document.page_count} {t("pages")}</p>
              </div>
              <span className="text-xs font-medium text-blue-600">{t("open")} →</span>
            </Link>
          ))}
        </div>
      ) : <p className="mt-4 rounded-2xl bg-white p-5 text-sm text-gray-500 ring-1 ring-gray-200">{t("noDocumentsYet")}</p>}
    </section>
  );
}
