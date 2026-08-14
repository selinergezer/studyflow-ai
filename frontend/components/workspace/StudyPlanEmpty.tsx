"use client";

import { useState, type FormEvent } from "react";
import { apiErrorMessage, apiFetch } from "@/lib/api";
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
  const [availableHours, setAvailableHours] = useState("");
  const [plan, setPlan] = useState<PlannerResponse | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsedHours = Number(availableHours);
  const durationPreview =
    availableHours && Number.isFinite(parsedHours) && parsedHours > 0 && parsedHours <= 24
      ? formatStudyDuration(parsedHours, language)
      : null;

  async function createPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (creating) return;

    const available_hours_per_day = Number(availableHours);
    if (
      !Number.isFinite(available_hours_per_day) ||
      available_hours_per_day <= 0 ||
      available_hours_per_day > 24
    ) {
      setError(t("plannerHoursError"));
      return;
    }

    setCreating(true);
    setError(null);

    try {
      const result = await apiFetch<PlannerResponse>("/ai/planner/", {
        method: "POST",
        body: JSON.stringify({ available_hours_per_day }),
      });

      setPlan({
        ...result,
        weekly_plan: Array.isArray(result.weekly_plan) ? result.weekly_plan : [],
      });
    } catch (cause) {
      console.error(cause);
      setError(
        apiErrorMessage(
          cause,
          t("plannerCreateFailed"),
          t("operationUnavailable"),
        ),
      );
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="study-plan-page">
      <header className="study-plan-heading">
        <div className="study-plan-glow" aria-hidden="true" />
        <p className="study-plan-eyebrow">{t("planning")}</p>
        <h1>{t("studyPlanTitle")}</h1>
        <p>{t("plannerPageIntro")}</p>
      </header>

      {!plan ? (
        <section className="study-plan-empty-paper">
          <span className="study-plan-tape" aria-hidden="true" />
          <span className="study-plan-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
              <path d="M7 3v3m10-3v3M4 9h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Z" />
            </svg>
          </span>
          <h2>{t("noStudyPlan")}</h2>
          <p>{t("plannerEmptyDescription")}</p>

          <form className="study-plan-form" onSubmit={createPlan}>
            <label>
              {t("plannerDailyHours")}
              <input
                type="number"
                min="0.1"
                max="24"
                step="0.1"
                value={availableHours}
                onChange={(event) => setAvailableHours(event.target.value)}
                placeholder="2"
                required
              />
              {durationPreview ? (
                <small className="study-plan-duration-preview">
                  {t("plannerDailyEquivalent", { duration: durationPreview })}
                </small>
              ) : null}
            </label>
            <button type="submit" disabled={creating}>
              {creating ? t("plannerCreating") : t("plannerCreateButton")}
            </button>
          </form>

          {error ? <p className="study-plan-error" role="alert">{error}</p> : null}
          <span className="study-plan-note">{t("plannerEmptyNote")}</span>
        </section>
      ) : (
        <section className="study-plan-result-paper">
          <span className="study-plan-result-tape" aria-hidden="true" />
          <header>
            <div>
              <p className="study-plan-result-label">{t("weeklyPlanLabel")}</p>
              <h2>{t("yourStudyPlan")}</h2>
            </div>
            <button type="button" disabled={creating} onClick={() => setPlan(null)}>
              {t("createAnotherPlan")}
            </button>
          </header>

          {plan.weekly_plan.length ? (
            <div className="study-plan-days">
              {plan.weekly_plan.map((item, index) => (
                <article key={`${item.day}-${item.course}-${index}`} className="study-plan-task">
                  <span className="study-plan-task-flag" aria-hidden="true" />
                  <p className="study-plan-day">{item.day}</p>
                  <h3>{item.course}</h3>
                  <p className="study-plan-duration">
                    {formatStudyDuration(item.duration_minutes, language, "minutes")}
                  </p>

                  {item.topics?.length ? (
                    <div className="study-plan-topics">
                      <span className="study-plan-detail-label">{t("plannerTopics")}</span>
                      <ul>
                        {item.topics.map((topic, topicIndex) => (
                          <li key={`${topic}-${topicIndex}`}>{topic}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  <div className="study-plan-reason">
                    <span className="study-plan-detail-label">{t("plannerReason")}</span>
                    <p>{item.reason}</p>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <p className="study-plan-result-empty">{t("plannerNoSuitablePlan")}</p>
          )}

          {plan.general_advice ? (
            <aside className="study-plan-advice">
              <span>{t("generalAdvice")}</span>
              <p>{plan.general_advice}</p>
            </aside>
          ) : null}
        </section>
      )}
    </div>
  );
}
