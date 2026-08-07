"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import DocumentCard from "@/components/documents/DocumentCard";
import { mockDocuments } from "@/lib/mock-data";
import { useLanguage } from "@/providers/LanguageProvider";

export default function LibraryView() {
  const [query, setQuery] = useState("");
  const { t } = useLanguage();
  const filteredDocuments = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return mockDocuments;
    return mockDocuments.filter((document) =>
      `${document.name} ${document.course}`.toLowerCase().includes(normalizedQuery),
    );
  }, [query]);

  return (
    <div className="mx-auto max-w-5xl px-5 py-12 sm:px-8 sm:py-16">
      <div className="animate-enter flex flex-col justify-between gap-6 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm font-medium text-blue-600">{t("library")}</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-gray-950 sm:text-4xl">{t("yourMaterials")}</h1>
          <p className="mt-4 text-base text-gray-500">{t("libraryIntro")}</p>
        </div>
        <Link href="/upload" className="inline-flex h-11 items-center justify-center gap-2 self-start rounded-xl bg-blue-600 px-4 text-sm font-medium text-white transition hover:bg-blue-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 sm:self-auto">
          <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
          {t("addMaterial")}
        </Link>
      </div>

      <div className="animate-enter relative mt-10 max-w-md [animation-delay:40ms]">
        <svg className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m16.5 16.5 4 4" /></svg>
        <label htmlFor="library-search" className="sr-only">{t("searchMaterials")}</label>
        <input id="library-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("searchPlaceholder")} className="h-11 w-full rounded-xl border border-gray-200 bg-white pl-10 pr-3.5 text-sm text-gray-900 outline-none transition placeholder:text-gray-400 hover:border-gray-300 focus:border-blue-600 focus:ring-4 focus:ring-blue-600/10" />
      </div>

      <section className="animate-enter mt-6 [animation-delay:80ms]" aria-label={t("studyMaterials")}>
        {mockDocuments.length === 0 ? (
          <div className="rounded-3xl bg-white px-6 py-16 text-center ring-1 ring-gray-200">
            <span className="mx-auto flex size-11 items-center justify-center rounded-2xl bg-gray-100 text-gray-500" aria-hidden="true">
              <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M7 3.75h6.5L18 8.25v12H7V3.75Zm6.25.5V8.5h4.25" /></svg>
            </span>
            <h2 className="mt-5 text-sm font-medium text-gray-950">{t("firstMaterial")}</h2>
            <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-gray-500">{t("firstMaterialDesc")}</p>
            <Link href="/upload" className="mt-5 inline-flex text-sm font-medium text-blue-600 transition hover:text-blue-700">{t("uploadPdf")} →</Link>
          </div>
        ) : filteredDocuments.length > 0 ? (
          <div className="grid gap-3">
            {filteredDocuments.map((document) => <DocumentCard key={document.id} document={document} />)}
          </div>
        ) : (
          <div className="rounded-3xl bg-white px-6 py-16 text-center ring-1 ring-gray-200">
            <span className="mx-auto flex size-11 items-center justify-center rounded-2xl bg-gray-100 text-gray-500" aria-hidden="true">
              <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><circle cx="11" cy="11" r="7" /><path d="m16.5 16.5 4 4" /></svg>
            </span>
            <h2 className="mt-5 text-sm font-medium text-gray-950">{t("noMaterials")}</h2>
            <p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-gray-500">{t("noMaterialsDesc")}</p>
            <button type="button" onClick={() => setQuery("")} className="mt-5 text-sm font-medium text-blue-600 transition hover:text-blue-700">{t("clearSearch")}</button>
          </div>
        )}
      </section>
    </div>
  );
}
