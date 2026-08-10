"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import Card from "@/components/ui/Card";
import { apiFetch, type DocumentData } from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

type LibraryAction = "quiz" | "flashcards";

export default function LibraryView({ action }: { action?: LibraryAction }) {
  const router = useRouter();
  const { t } = useLanguage(); const [documents, setDocuments] = useState<DocumentData[]>([]); const [query, setQuery] = useState(""); const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null);
  useEffect(() => { apiFetch<DocumentData[]>("/documents/").then(setDocuments).catch((cause) => { console.error(cause); setError(cause instanceof Error ? cause.message : "İşlem sırasında bir hata oluştu."); }).finally(() => setLoading(false)); }, []);
  const filtered = useMemo(() => documents.filter((item) => item.filename.toLowerCase().includes(query.toLowerCase())), [documents, query]);
  function selectDocument(id: number) {
    if (action === "quiz") router.push(`/documents/${id}?tab=quiz`);
    else if (action === "flashcards") router.push(`/documents/${id}?tab=flashcards`);
  }
  const documentCard = (item: DocumentData) => <Card className="p-5 text-left transition hover:bg-gray-50"><h2 className="font-medium text-gray-950">{item.filename}</h2><p className="mt-2 text-sm text-gray-500">{item.page_count} {t("pages")}</p></Card>;
  return <div className="mx-auto max-w-5xl px-5 py-12 sm:px-8 sm:py-16"><div className="flex justify-between gap-6"><div><p className="text-sm font-medium text-blue-600">{t("library")}</p><h1 className="mt-3 text-3xl font-semibold text-gray-950">{t("yourMaterials")}</h1><p className="mt-4 text-gray-500">{action ? (action === "quiz" ? t("selectQuizMaterial") : t("selectFlashcardMaterial")) : t("libraryIntro")}</p></div><Link href="/upload" className="inline-flex h-11 items-center rounded-xl bg-blue-600 px-4 text-sm font-medium text-white">{t("addMaterial")}</Link></div><input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("searchPlaceholder")} className="mt-10 h-11 w-full max-w-md rounded-xl border border-gray-200 bg-white px-4 text-sm" />{error ? <p className="mt-5 text-sm text-red-600">{error}</p> : null}{loading ? <p className="mt-8 text-sm text-gray-500">Yükleniyor...</p> : <div className="mt-6 grid gap-3">{filtered.map((item) => action ? <button key={item.id} type="button" onClick={() => selectDocument(item.id!)}>{documentCard(item)}</button> : <Link key={item.id} href={`/documents/${item.id}`}>{documentCard(item)}</Link>)}</div>}</div>;
}
