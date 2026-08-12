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
  const [greetingKey, setGreetingKey] = useState<"goodMorning" | "goodAfternoon" | "goodEvening" | "goodNight">("goodMorning");

  useEffect(() => {
    const hour = new Date().getHours();
    setGreetingKey(hour >= 5 && hour < 12 ? "goodMorning" : hour >= 12 && hour < 18 ? "goodAfternoon" : hour >= 18 && hour < 23 ? "goodEvening" : "goodNight");
  }, []);

  useEffect(() => {
    Promise.all([apiFetch<Course[]>("/courses/"), apiFetch<DocumentData[]>("/documents/")])
      .then(([courseItems, documentItems]) => { setCourses(courseItems); setDocuments(documentItems); })
      .catch((cause) => { console.error(cause); setError(language === "tr" ? "Veriler şu anda yüklenemiyor." : "Data is currently unavailable."); })
      .finally(() => setLoading(false));
  }, [language]);
  return (
    <div className="dashboard-page">
      <header className="dashboard-greeting animate-enter">
        <div className="dashboard-glow" aria-hidden="true" />
        <p className="dashboard-eyebrow">{t("yourWorkspace")}</p>
        <h1>{t(greetingKey)}</h1>
        <p className="dashboard-subtitle">{t("dashboardIntro")}</p>
      </header>

      <QuickActions />

      {error ? <p className="dashboard-error" role="alert">{error}</p> : null}

      <div>
        <RecentCourses courses={courses} documents={documents} loading={loading} />
        <RecentDocuments courses={courses} documents={documents} loading={loading} />
      </div>
    </div>
  );
}
