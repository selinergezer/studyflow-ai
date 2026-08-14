"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { formatStudyDuration } from "@/lib/formatStudyDuration";
import { useLanguage } from "@/providers/LanguageProvider";

type StudyPlanItem = {
  day: string;
  course: string;
  duration_minutes: number;
  topics: string[];
  reason: string;
};

type PlannerResponse = {
  weekly_plan: StudyPlanItem[];
  general_advice: string;
};

export default function StudyPlanEmpty() {
  const { t, language } = useLanguage();
  const tr = language === "tr";
  const [availableHours, setAvailableHours] = useState("");
  const [plan, setPlan] = useState<PlannerResponse | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function createPlan(event: React.FormEvent) {
    event.preventDefault();
    const available_hours_per_day = Number(availableHours);
    if (!Number.isFinite(available_hours_per_day) || available_hours_per_day < 0.5) {
      setError(tr ? "Lütfen günlük çalışma süresini girin." : "Enter your available daily study time.");
      return;
    }
    setCreating(true); setError(null);
    try {
      setPlan(await apiFetch<PlannerResponse>("/ai/planner/", {
        method: "POST",
        body: JSON.stringify({ available_hours_per_day }),
      }));
    } catch (cause) {
      console.error(cause);
      setError(tr ? "Çalışma planı oluşturulamadı. Lütfen tekrar deneyin." : "The study plan could not be created. Please try again.");
    } finally {
      setCreating(false);
    }
  }

  return <div className="study-plan-page">
    <header className="study-plan-heading"><div className="study-plan-glow" aria-hidden="true" /><p className="study-plan-eyebrow">{t("planning")}</p><h1>{t("studyPlanTitle")}</h1><p>{tr ? "Materyallerin, sınavların ve hedeflerin doğrultusunda kişisel çalışma düzenini burada takip et." : "Track your personal study routine here based on your materials, quizzes, and goals."}</p></header>
    {!plan ? <section className="study-plan-empty-paper">
      <span className="study-plan-tape" aria-hidden="true" /><span className="study-plan-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M7 3v3m10-3v3M4 9h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Z" /></svg></span>
      <h2>{tr ? "Henüz çalışma planın yok." : "You don't have a study plan yet."}</h2>
      <p>{tr ? "Materyallerin, sınavların ve hedeflerin doğrultusunda sana özel çalışma planı oluştur." : "Create a personal study plan based on your materials, quizzes, and goals."}</p>
      <form className="study-plan-form" onSubmit={createPlan}>
        <label>{tr ? "Günlük ayırabileceğin süre (saat)" : "Available hours per day"}<input type="number" min="0.5" step="0.5" value={availableHours} onChange={(event) => setAvailableHours(event.target.value)} placeholder="2" required /></label>
        <button type="submit" disabled={creating}>{creating ? (tr ? "Plan oluşturuluyor..." : "Creating plan...") : (tr ? "+ Plan Oluştur" : "+ Create Plan")}</button>
      </form>
      {error ? <p className="study-plan-error" role="alert">{error}</p> : null}
      <span className="study-plan-note">{tr ? "planın hazır olduğunda burada buluşacağız." : "we'll meet here when your plan is ready."}</span>
    </section> : <section className="study-plan-result-paper">
      <span className="study-plan-result-tape" aria-hidden="true" />
      <header><div><p className="study-plan-result-label">{tr ? "HAFTALIK PLAN" : "WEEKLY PLAN"}</p><h2>{tr ? "Çalışma Planın" : "Your Study Plan"}</h2></div><button type="button" disabled={creating} onClick={() => setPlan(null)}>{tr ? "Planı Yeniden Oluştur" : "Create Another Plan"}</button></header>
      <div className="study-plan-days">{plan.weekly_plan.map((item, index) => <article key={`${item.day}-${item.course}-${index}`} className="study-plan-task"><span className="study-plan-task-flag" aria-hidden="true" /><p className="study-plan-day">{item.day}</p><h3>{item.course}</h3><p className="study-plan-duration">{formatStudyDuration(item.duration_minutes, language, "minutes")}</p>{item.topics?.length ? <ul>{item.topics.map((topic) => <li key={topic}>{topic}</li>)}</ul> : null}<p className="study-plan-reason">{item.reason}</p></article>)}</div>
      {plan.general_advice ? <aside className="study-plan-advice"><span>{tr ? "GENEL ÖNERİ" : "GENERAL ADVICE"}</span><p>{plan.general_advice}</p></aside> : null}
    </section>}
  </div>;
}
