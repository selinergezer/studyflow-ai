"use client";

import Link from "next/link";
import DashboardIcon from "@/components/dashboard/DashboardIcon";
import { mockCourses, mockDocuments } from "@/lib/mock-data";
import { useLanguage } from "@/providers/LanguageProvider";

export function RecentCourses() {
  const { t } = useLanguage();
  return (
    <section aria-labelledby="recent-courses-heading">
      <div className="flex items-center justify-between">
        <h2 id="recent-courses-heading" className="text-sm font-semibold text-gray-950">{t("recentCourses")}</h2>
        <Link href="/courses" className="text-sm text-gray-500 transition hover:text-gray-900">{t("viewAll")}</Link>
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {mockCourses.slice(0, 2).map((course) => (
          <Link key={course.id} href={`/courses#${course.id}`} className="group rounded-2xl bg-white p-5 ring-1 ring-gray-200 transition duration-200 hover:-translate-y-0.5 hover:ring-gray-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">
            <div className="flex items-start justify-between gap-3">
              <span className="flex size-9 items-center justify-center rounded-xl bg-gray-100 text-gray-700"><DashboardIcon name="book" /></span>
              <span className="text-xs font-medium text-gray-700">{course.progress}%</span>
            </div>
            <h3 className="mt-5 text-sm font-medium text-gray-950">{course.name}</h3>
            <p className="mt-1.5 text-xs text-gray-500">{t(course.lastStudied)}</p>
            <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-gray-100"><div className="h-full rounded-full bg-blue-600" style={{ width: `${course.progress}%` }} /></div>
            <span className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-blue-600">{t("continue")} <span className="transition-transform group-hover:translate-x-0.5">→</span></span>
          </Link>
        ))}
      </div>
    </section>
  );
}

export function RecentDocuments() {
  const { t } = useLanguage();
  return (
    <section aria-labelledby="recent-documents-heading">
      <div className="flex items-center justify-between">
        <h2 id="recent-documents-heading" className="text-sm font-semibold text-gray-950">{t("recentDocuments")}</h2>
        <Link href="/library" className="text-sm text-gray-500 transition hover:text-gray-900">{t("viewLibrary")}</Link>
      </div>
      <div className="mt-4 overflow-hidden rounded-2xl bg-white ring-1 ring-gray-200">
        {mockDocuments.map((document, index) => (
          <Link key={document.id} href={`/documents/${document.id}`} className={`group flex flex-col gap-4 p-4 transition hover:bg-gray-50 sm:flex-row sm:items-center sm:p-5 ${index ? "border-t border-gray-100" : ""}`}>
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-red-50 text-red-600" aria-hidden="true">
              <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M7 3.75h6.5L18 8.25v12H7V3.75Zm6.25.5V8.5h4.25" /></svg>
            </span>
            <div className="min-w-0 flex-1">
              <h3 className="truncate text-sm font-medium text-gray-950">{document.name}</h3>
              <p className="mt-1 text-xs text-gray-500">{document.course} · {document.pageCount} {t("pages")}</p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {[t("summaryReady"), t("quizReady"), t("flashcardsReady")].map((status) => <span key={status} className="rounded-md bg-green-50 px-2 py-1 text-[11px] font-medium text-green-700">{status}</span>)}
            </div>
            <span className="text-xs font-medium text-blue-600">{t("open")} →</span>
          </Link>
        ))}
      </div>
    </section>
  );
}
