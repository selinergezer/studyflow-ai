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
  isAbortError,
  type Course,
  type DocumentData,
} from "@/lib/api";
import { formatStudyDuration } from "@/lib/formatStudyDuration";
import { translations } from "@/lib/translations";

type StudySession = {
  id: number;
  course_id: number;
  study_date: string;
  duration_minutes: number;
  description: string | null;
};

type DashboardErrors = {
  courses: string | null;
  documents: string | null;
  sessions: string | null;
};

const emptyDashboardErrors: DashboardErrors = {
  courses: null,
  documents: null,
  sessions: null,
};

async function fetchTotalStudyMinutes(signal?: AbortSignal) {
  const sessions = await apiFetch<StudySession[]>("/study-sessions/", { signal });
  return sessions.reduce(
    (total, session) => total + session.duration_minutes,
    0,
  );
}

function todayInputValue() {
  const now = new Date();
  const localDate = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return localDate.toISOString().slice(0, 10);
}

export default function DashboardShell() {
  const { t, language } = useLanguage();

  const [courses, setCourses] = useState<Course[]>([]);
  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [totalStudyMinutes, setTotalStudyMinutes] = useState(0);

  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [errors, setErrors] = useState<DashboardErrors>(emptyDashboardErrors);
  const [studyModalOpen, setStudyModalOpen] = useState(false);
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const [studyDate, setStudyDate] = useState("");
  const [studyMinutes, setStudyMinutes] = useState("");
  const [studyDescription, setStudyDescription] = useState("");
  const [studySubmitting, setStudySubmitting] = useState(false);
  const [studyError, setStudyError] = useState<string | null>(null);
  const [studyStatus, setStudyStatus] = useState<string | null>(null);

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
    let cancelled = false;
    const controller = new AbortController();

    queueMicrotask(() => {
      if (cancelled) return;
      setErrors(emptyDashboardErrors);
      setLoading(true);
      setStatsLoading(true);
    });

    Promise.allSettled([
      apiFetch<Course[]>("/courses/", { signal: controller.signal }),
      apiFetch<DocumentData[]>("/documents/", { signal: controller.signal }),
      fetchTotalStudyMinutes(controller.signal),
    ]).then(([courseResult, documentResult, sessionResult]) => {
      if (cancelled) return;

      const messageFor = (cause: unknown) => {
        return apiErrorMessage(
          cause,
          translations[language].genericError,
          translations[language].operationUnavailable,
        );
      };

      if (courseResult.status === "fulfilled") {
        setCourses(courseResult.value);
      }

      if (documentResult.status === "fulfilled") {
        setDocuments(documentResult.value);
      }

      if (sessionResult.status === "fulfilled") {
        setTotalStudyMinutes(sessionResult.value);
      }

      setErrors({
        courses: courseResult.status === "rejected" ? messageFor(courseResult.reason) : null,
        documents: documentResult.status === "rejected" ? messageFor(documentResult.reason) : null,
        sessions: sessionResult.status === "rejected" ? messageFor(sessionResult.reason) : null,
      });

      if (!cancelled) {
        setLoading(false);
        setStatsLoading(false);
      }
    });

    return () => {
      cancelled = true;
      controller.abort();
    };
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
    setStudyDate(todayInputValue());
    setStudyError(null);
    setStudyStatus(null);
    setStudyModalOpen(true);
  }

  function closeStudyModal() {
    if (studySubmitting) return;
    setStudyModalOpen(false);
    setStudyError(null);
  }

  async function submitStudySession(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (studySubmitting) return;

    if (!selectedCourseId) {
      setStudyError(t("selectCourseError"));
      return;
    }
    if (!studyDate) {
      setStudyError(t("selectDateError"));
      return;
    }
    const durationMinutes = Number(studyMinutes);
    if (!studyMinutes || !Number.isInteger(durationMinutes) || durationMinutes <= 0) {
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
          duration_minutes: durationMinutes,
          description: studyDescription.trim() || null,
        }),
      });
      setSelectedCourseId("");
      setStudyDate("");
      setStudyMinutes("");
      setStudyDescription("");
      setStudyModalOpen(false);

      try {
        const updatedTotal = await fetchTotalStudyMinutes();
        setTotalStudyMinutes(updatedTotal);
        setErrors((current) => ({ ...current, sessions: null }));
        setStudyStatus(t("studySessionSaved"));
      } catch (statsCause) {
        if (isAbortError(statsCause)) return;
        setErrors((current) => ({
          ...current,
          sessions: apiErrorMessage(
            statsCause,
            t("studySessionRefreshFailed"),
            t("operationUnavailable"),
          ),
        }));
      }
    } catch (cause) {
      if (isAbortError(cause)) return;
      setStudyError(
        apiErrorMessage(cause, t("studySessionFailed"), t("operationUnavailable")),
      );
    } finally {
      setStudySubmitting(false);
    }
  }

  const error = errors.courses ?? errors.documents ?? errors.sessions;

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
                  : formatStudyDuration(totalStudyMinutes, language, "minutes")}
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

      {studyStatus ? (
        <p className="dashboard-study-status" role="status">
          {studyStatus}
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
                <input type="number" min="1" step="1" placeholder={t("minutesExample")} value={studyMinutes} onChange={(event) => setStudyMinutes(event.target.value)} />
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
