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
    <section className="animate-enter mt-9" aria-labelledby="quick-actions-heading">
      <h2 id="quick-actions-heading" className="sr-only">{t("quickActions")}</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {actions.map((action) => (
          <Link key={action.label} href={action.href} className="group flex items-center gap-3 rounded-2xl bg-white p-4 ring-1 ring-gray-200 transition duration-200 hover:-translate-y-0.5 hover:ring-gray-300 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-gray-100 text-gray-700 transition group-hover:bg-blue-50 group-hover:text-blue-600"><DashboardIcon name={action.icon} /></span>
            <span className="min-w-0">
              <span className="block text-sm font-medium text-gray-950">{t(action.label)}</span>
              <span className="mt-0.5 block truncate text-xs text-gray-500">{t(action.description)}</span>
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}
