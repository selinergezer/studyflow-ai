"use client";

import Link from "next/link";
import type { StudyDocument } from "@/lib/mock-data";
import { useLanguage } from "@/providers/LanguageProvider";

type DocumentCardProps = {
  document: StudyDocument;
  compact?: boolean;
};

export default function DocumentCard({ document, compact = false }: DocumentCardProps) {
  const { t, language } = useLanguage();
  const uploadedAt = new Intl.DateTimeFormat(language === "tr" ? "tr-TR" : "en-US", { day: "numeric", month: "short", year: "numeric" }).format(new Date(`${document.uploadedAt}T00:00:00`));
  return (
    <Link
      href={`/documents/${document.id}`}
      className={`group flex rounded-2xl bg-white ring-1 ring-gray-200 transition duration-200 hover:-translate-y-0.5 hover:ring-gray-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 ${compact ? "flex-col p-5" : "items-center gap-4 p-4 sm:p-5"}`}
    >
      <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-red-50 text-red-600" aria-hidden="true">
        <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M7 3.75h6.5L18 8.25v12H7V3.75Zm6.25.5V8.5h4.25M9.75 12h5.5m-5.5 3.25h4" />
        </svg>
      </span>
      <div className={`min-w-0 flex-1 ${compact ? "mt-5" : ""}`}>
        <h3 className="truncate text-sm font-medium text-gray-950">{document.name}</h3>
        <p className="mt-1.5 text-xs text-gray-500">{document.course}</p>
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-400">
          <span>{uploadedAt}</span>
          <span aria-hidden="true">·</span>
          <span>{document.pageCount} {t("pages")}</span>
          {!compact ? <><span aria-hidden="true">·</span><span>{document.size}</span></> : null}
        </div>
      </div>
      {!compact ? (
        <span className="hidden h-9 shrink-0 items-center rounded-lg border border-gray-200 px-3 text-xs font-medium text-gray-700 transition group-hover:bg-gray-50 sm:inline-flex">{t("open")}</span>
      ) : (
        <span className="mt-5 inline-flex items-center gap-1.5 text-xs font-medium text-blue-600">
          {t("openDocument")}
          <svg className="size-3.5 transition-transform group-hover:translate-x-0.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="M4 10h12m-4-4 4 4-4 4" /></svg>
        </span>
      )}
    </Link>
  );
}
