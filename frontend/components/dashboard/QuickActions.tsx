"use client";

import { useState } from "react";
import Link from "next/link";
import DashboardIcon, { type DashboardIconName } from "@/components/dashboard/DashboardIcon";
import QuizCreateModal from "@/components/workspace/QuizCreateModal";
import FlashcardCreateModal from "@/components/workspace/FlashcardCreateModal";
import { useLanguage } from "@/providers/LanguageProvider";
import type { TranslationKey } from "@/lib/translations";

type NavigationAction = { label: TranslationKey; description: TranslationKey; href: string; icon: DashboardIconName; accent: "pdf" | "ai" };

const navigationActions: NavigationAction[] = [
  { label: "uploadPdf", description: "uploadPdfDesc", href: "/upload", icon: "upload", accent: "pdf" },
  { label: "askAi", description: "askAiDesc", href: "/ask-ai", icon: "chat", accent: "ai" },
];

export default function QuickActions() {
  const { t } = useLanguage();
  const [quizModalOpen, setQuizModalOpen] = useState(false);
  const [flashcardModalOpen, setFlashcardModalOpen] = useState(false);

  const uploadAction = navigationActions[0];
  const aiAction = navigationActions[1];

  function navigationCard(action: NavigationAction) {
    return (
      <Link key={action.label} href={action.href} className={`dashboard-action-card dashboard-action-card--${action.accent} interactive-card`}>
        <span className="dashboard-action-icon"><DashboardIcon name={action.icon} /></span>
        <span className="dashboard-action-copy"><span className="dashboard-action-title">{t(action.label)}</span><span className="dashboard-action-description">{t(action.description)}</span></span>
        <span className="dashboard-action-arrow" aria-hidden="true">→</span>
      </Link>
    );
  }

  return (
    <section className="dashboard-actions animate-enter" aria-labelledby="quick-actions-heading">
      <h2 id="quick-actions-heading" className="dashboard-quick-actions-heading">{t("quickActions")}</h2>
      <div className="dashboard-actions-grid">
        {navigationCard(uploadAction)}
        <button type="button" onClick={() => setQuizModalOpen(true)} className="dashboard-action-card dashboard-action-card--quiz interactive-card">
            <span className="dashboard-action-icon"><DashboardIcon name="quiz" /></span>
            <span className="dashboard-action-copy">
              <span className="dashboard-action-title">{t("createQuiz")}</span>
              <span className="dashboard-action-description">{t("createQuizDesc")}</span>
            </span>
            <span className="dashboard-action-arrow" aria-hidden="true">→</span>
        </button>
        <button type="button" onClick={() => setFlashcardModalOpen(true)} className="dashboard-action-card dashboard-action-card--flashcard interactive-card">
            <span className="dashboard-action-icon"><DashboardIcon name="cards" /></span>
            <span className="dashboard-action-copy">
              <span className="dashboard-action-title">{t("generateFlashcards")}</span>
              <span className="dashboard-action-description">{t("generateFlashcardsDesc")}</span>
            </span>
            <span className="dashboard-action-arrow" aria-hidden="true">→</span>
        </button>
        {navigationCard(aiAction)}
      </div>
      <QuizCreateModal open={quizModalOpen} onClose={() => setQuizModalOpen(false)} />
      <FlashcardCreateModal open={flashcardModalOpen} onClose={() => setFlashcardModalOpen(false)} />
    </section>
  );
}
