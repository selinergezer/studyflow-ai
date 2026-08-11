"use client";

import Link from "next/link";
import DashboardIcon, { type DashboardIconName } from "@/components/dashboard/DashboardIcon";
import { useLanguage } from "@/providers/LanguageProvider";
import type { TranslationKey } from "@/lib/translations";

const actions: Array<{ label: TranslationKey; description: TranslationKey; href: string; icon: DashboardIconName }> = [
  { label: "uploadPdf", description: "uploadPdfDesc", href: "/upload", icon: "upload" }, { label: "createQuiz", description: "createQuizDesc", href: "/library?action=quiz", icon: "quiz" }, { label: "generateFlashcards", description: "generateFlashcardsDesc", href: "/library?action=flashcards", icon: "cards" }, { label: "askAi", description: "askAiDesc", href: "/library", icon: "chat" },
];

export default function QuickActions() {
  const { t } = useLanguage();
  return (
    <section className="dashboard-actions animate-enter" aria-labelledby="quick-actions-heading">
      <h2 id="quick-actions-heading" className="sr-only">{t("quickActions")}</h2>
      <div className="dashboard-actions-grid">
        {actions.map((action) => (
          <Link key={action.label} href={action.href} className="dashboard-action-card">
            <span className="dashboard-action-flag" aria-hidden="true" />
            <span className="dashboard-action-icon"><DashboardIcon name={action.icon} /></span>
            <span>
              <span className="dashboard-action-title">{t(action.label)}</span>
              <span className="dashboard-action-description">{t(action.description)}</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
