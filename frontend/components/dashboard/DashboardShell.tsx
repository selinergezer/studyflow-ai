"use client";

import { useEffect, useState, type FormEvent } from "react";
import QuickActions from "@/components/dashboard/QuickActions";
import {
  RecentCourses,
  RecentDocuments,
} from "@/components/dashboard/DashboardSections";
import { useLanguage } from "@/providers/LanguageProvider";
import {
  apiErrorMessage,
  apiFetch,
  type Course,
  type DocumentData,
} from "@/lib/api";
import { formatStudyDuration } from "@/lib/formatStudyDuration";

type StatsSummary = {
  total_study_minutes: number;
  total_study_hours: number;
};

export default function DashboardShell() {
  const { t, language } = useLanguage();

  const [courses, setCourses] = useState<Course[]>([]);
  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [stats, setStats] = useState<StatsSummary | null>(null);

  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [studyModalOpen, setStudyModalOpen] = useState(false);
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const [studyDate, setStudyDate] = useState("");
  const [studyMinutes, setStudyMinutes] = useState("");
  const [studyDescription, setStudyDescription] = useState("");
  const [studySubmitting, setStudySubmitting] = useState(false);
  const [studyError, setStudyError] = useState<string | null>(null);

  const [greetingKey] = useState<
    "goodMorning" | "goodAfternoon" | "goodEvening" | "goodNight"
  >(() => {
    const hour = new Date().getHours();
    return hour >= 5 && hour < 12
      ? "goodMorning"
      : hour >= 12 && hour < 18
        ? "goodAfternoon"
        : hour >= 18 && hour < 23
          ? "goodEvening"
          : "goodNight";
  });

  useEffect(() => {
    Promise.all([
      apiFetch<Course[]>("/courses/"),
      apiFetch<DocumentData[]>("/documents/"),
      apiFetch<StatsSummary>("/stats/summary"),
    ])
      .then(([courseItems, documentItems, statsData]) => {
        setCourses(courseItems);
        setDocuments(documentItems);
        setStats(statsData);
      })
      .catch((cause) => {
        console.error(cause);

        setError(
          language === "tr"
            ? "Veriler şu anda yüklenemiyor."
            : "Data is currently unavailable.",
        );
      })
      .finally(() => {
        setLoading(false);
        setStatsLoading(false);
      });
  }, [language]);

  useEffect(() => {
    if (!studyModalOpen) return;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !studySubmitting) setStudyModalOpen(false);
    }

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [studyModalOpen, studySubmitting]);

  function openStudyModal() {
    setStudyDate(new Date().toLocaleDateString("en-CA"));
    setStudyError(null);
    setStudyModalOpen(true);
  }

  function closeStudyModal() {
    if (studySubmitting) return;
    setStudyModalOpen(false);
    setStudyError(null);
  }

  async function submitStudySession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedCourseId) {
      setStudyError(t("selectCourseError"));
      return;
    }
    if (!studyDate) {
      setStudyError(t("selectDateError"));
      return;
    }
    if (!studyMinutes || Number(studyMinutes) <= 0) {
      setStudyError(t("studyDurationError"));
      return;
    }

    setStudySubmitting(true);
    setStudyError(null);
    try {
      await apiFetch("/study-sessions/", {
        method: "POST",
        body: JSON.stringify({
          course_id: Number(selectedCourseId),
          study_date: studyDate,
          duration_minutes: Number(studyMinutes),
          description: studyDescription.trim() || null,
        }),
      });
      setSelectedCourseId("");
      setStudyDate("");
      setStudyMinutes("");
      setStudyDescription("");
      setStudyModalOpen(false);

      try {
        const updatedStats = await apiFetch<StatsSummary>("/stats/summary");
        setStats(updatedStats);
      } catch (statsCause) {
        console.error(statsCause);
        setError(
          t("studySessionRefreshFailed"),
        );
      }
    } catch (cause) {
      console.error(cause);
      setStudyError(apiErrorMessage(cause, t("studySessionFailed")));
    } finally {
      setStudySubmitting(false);
    }
  }

  return (
    <div className="dashboard-page">

      <div className="dashboard-hero-row">
        <header className="dashboard-greeting animate-enter">
          <div
            className="dashboard-glow"
            aria-hidden="true"
          />

          <p className="dashboard-eyebrow">
            {t("yourWorkspace")}
          </p>

          <h1>
            {t(greetingKey)}
          </h1>

          <p className="dashboard-subtitle">
            {t("dashboardIntro")}
          </p>
        </header>

        <section className="dashboard-study-summary">
          <div className="dashboard-study-summary-content">
            <div>
              <p className="dashboard-study-summary-label">
                {t("studyTime")}
              </p>

              <h2>
                {statsLoading
                  ? "..."
                  : formatStudyDuration(stats?.total_study_hours ?? 0, language)}
              </h2>

              <p>
                {t("totalRecordedStudyTime")}
              </p>
            </div>

            <button
              type="button"
              className="interactive-button dashboard-study-add-button"
              onClick={openStudyModal}
            >
              {t("addStudySession")}
            </button>
          </div>
        </section>
      </div>

      <QuickActions />

      {error ? (
        <p
          className="dashboard-error"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      <div className="dashboard-bottom-grid">
        <RecentCourses
          courses={courses}
          documents={documents}
          loading={loading}
        />

        <RecentDocuments
          courses={courses}
          documents={documents}
          loading={loading}
        />
      </div>

      {studyModalOpen ? (
        <div className="dashboard-study-modal-overlay" role="presentation" onMouseDown={closeStudyModal}>
          <section
            className="dashboard-study-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="study-modal-title"
            onMouseDown={(event) => event.stopPropagation()}
          >
            <div className="dashboard-study-modal-head">
              <div>
                <h2 id="study-modal-title">{t("addStudySessionTitle")}</h2>
                <p>{t("addStudySessionDescription")}</p>
              </div>
              <button type="button" onClick={closeStudyModal} aria-label={t("close")} disabled={studySubmitting}>×</button>
            </div>

            <form className="dashboard-study-form" onSubmit={submitStudySession}>
              <label className="dashboard-study-field">
                <span>{t("course")}</span>
                <select value={selectedCourseId} onChange={(event) => setSelectedCourseId(event.target.value)}>
                  <option value="">{t("selectCourse")}</option>
                  {courses.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}
                </select>
              </label>
              <label className="dashboard-study-field">
                <span>{t("date")}</span>
                <input type="date" value={studyDate} onChange={(event) => setStudyDate(event.target.value)} />
              </label>
              <label className="dashboard-study-field">
                <span>{t("studyDuration")}</span>
                <input type="number" min="1" placeholder={t("minutesExample")} value={studyMinutes} onChange={(event) => setStudyMinutes(event.target.value)} />
              </label>
              <label className="dashboard-study-field">
                <span>{t("description")} <small>{t("optional")}</small></span>
                <textarea rows={3} placeholder={t("studyDescriptionPlaceholder")} value={studyDescription} onChange={(event) => setStudyDescription(event.target.value)} />
              </label>

              {studyError ? <p className="dashboard-study-modal-error" role="alert">{studyError}</p> : null}

              <div className="dashboard-study-modal-actions">
                <button type="button" className="dashboard-study-cancel" onClick={closeStudyModal} disabled={studySubmitting}>{t("cancel")}</button>
                <button type="submit" className="dashboard-study-save" disabled={studySubmitting}>{studySubmitting ? t("saving") : t("save")}</button>
              </div>
            </form>
          </section>
        </div>
      ) : null}
    </div>
  );
}
