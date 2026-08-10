"use client";

import { useEffect, useState } from "react";
import QuickActions from "@/components/dashboard/QuickActions";
import {
  RecentCourses,
  RecentDocuments,
} from "@/components/dashboard/DashboardSections";
import { useLanguage } from "@/providers/LanguageProvider";
import { apiFetch, type Course, type DocumentData } from "@/lib/api";

export default function DashboardShell() {
  const { t, language } = useLanguage();
  const [courses, setCourses] = useState<Course[]>([]);
  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([apiFetch<Course[]>("/courses/"), apiFetch<DocumentData[]>("/documents/")])
      .then(([courseItems, documentItems]) => { setCourses(courseItems); setDocuments(documentItems); })
      .catch((cause) => { console.error(cause); setError(cause instanceof Error ? cause.message : language === "tr" ? "İşlem sırasında bir hata oluştu." : "Something went wrong."); })
      .finally(() => setLoading(false));
  }, [language]);
  return (
    <div className="mx-auto max-w-7xl px-5 py-10 sm:px-8 sm:py-14">
      <header className="animate-enter">
        <p className="text-sm text-gray-500">{t("yourWorkspace")}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-gray-950 sm:text-4xl">{t("goodMorning")}</h1>
        <p className="mt-3 text-base text-gray-500">{t("dashboardIntro")}</p>
      </header>

      <QuickActions />

      {error ? <p className="mt-6 text-sm text-red-600" role="alert">{error}</p> : null}

      <div className="mt-10 space-y-10">
        <RecentCourses courses={courses} documents={documents} loading={loading} />
        <RecentDocuments courses={courses} documents={documents} loading={loading} />
      </div>
    </div>
  );
}
