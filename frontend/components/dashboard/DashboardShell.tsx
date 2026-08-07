"use client";

import QuickActions from "@/components/dashboard/QuickActions";
import {
  RecentCourses,
  RecentDocuments,
} from "@/components/dashboard/DashboardSections";
import { useLanguage } from "@/providers/LanguageProvider";

export default function DashboardShell() {
  const { t } = useLanguage();
  return (
    <div className="mx-auto max-w-7xl px-5 py-10 sm:px-8 sm:py-14">
      <header className="animate-enter">
        <p className="text-sm text-gray-500">{t("yourWorkspace")}</p>
        <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-gray-950 sm:text-4xl">{t("goodMorning")}</h1>
        <p className="mt-3 text-base text-gray-500">{t("dashboardIntro")}</p>
      </header>

      <QuickActions />

      <div className="mt-10 space-y-10">
        <RecentCourses />
        <RecentDocuments />
      </div>
    </div>
  );
}
