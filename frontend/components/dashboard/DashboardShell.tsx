"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
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
  type CurrentUser,
  type DocumentData,
} from "@/lib/api";
import { formatStudyDuration } from "@/lib/formatStudyDuration";
import { translations } from "@/lib/translations";
import Link from "next/link";

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

async function fetchStudySessions(signal?: AbortSignal) {
  return apiFetch<StudySession[]>("/study-sessions/", {
    signal,
  });
}

function localDateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function currentWeekMinutes(sessions: StudySession[], referenceDate: Date) {
  const monday = new Date(referenceDate);
  const mondayOffset = (monday.getDay() + 6) % 7;
  monday.setHours(0, 0, 0, 0);
  monday.setDate(monday.getDate() - mondayOffset);

  const minutesByDate = new Map<string, number>();
  sessions.forEach((session) => {
    minutesByDate.set(
      session.study_date,
      (minutesByDate.get(session.study_date) ?? 0) + session.duration_minutes,
    );
  });

  return Array.from({ length: 7 }, (_, index) => {
    const date = new Date(monday);
    date.setDate(monday.getDate() + index);
    return minutesByDate.get(localDateKey(date)) ?? 0;
  });
}

function todayInputValue() {
  const now = new Date();

  const localDate = new Date(
    now.getTime() - now.getTimezoneOffset() * 60_000,
  );

  return localDate.toISOString().slice(0, 10);
}

export default function DashboardShell() {
  const { t, language } = useLanguage();
  const languageRef = useRef(language);

  useEffect(() => {
    languageRef.current = language;
  }, [language]);

  const [courses, setCourses] = useState<Course[]>([]);
  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [username, setUsername] = useState("");
  const [studySessions, setStudySessions] = useState<StudySession[]>([]);
  const [dashboardDate] = useState(() => new Date());

  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);

  const [errors, setErrors] =
    useState<DashboardErrors>(emptyDashboardErrors);

  const [studyModalOpen, setStudyModalOpen] = useState(false);
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const [studyDate, setStudyDate] = useState("");
  const [studyMinutes, setStudyMinutes] = useState("");
  const [studyDescription, setStudyDescription] = useState("");
  const [studySubmitting, setStudySubmitting] = useState(false);

  const [studyError, setStudyError] =
    useState<string | null>(null);

  const [studyStatus, setStudyStatus] =
    useState<string | null>(null);

  const [greetingKey] = useState<
    "goodMorning" |
    "goodAfternoon" |
    "goodEvening" |
    "goodNight"
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

  /*
   * DASHBOARD VERİLERİ
   *
   * Kurslar, belgeler ve çalışma süresi birbirini beklemez.
   * Bir veri geldiği anda ekrana yazılır.
   */
  useEffect(() => {
    let cancelled = false;

    const controller = new AbortController();

    setErrors(emptyDashboardErrors);
    setLoading(true);
    setStatsLoading(true);

    const messageFor = (cause: unknown) =>
      apiErrorMessage(
        cause,
        translations[languageRef.current].genericError,
        translations[languageRef.current].operationUnavailable,
      );

    /*
     * KURSLAR
     */
    const coursesPromise = apiFetch<Course[]>("/courses/", {
      signal: controller.signal,
    })
      .then((data) => {
        if (cancelled) return;

        setCourses(data);

        setErrors((current) => ({
          ...current,
          courses: null,
        }));
      })
      .catch((cause) => {
        if (cancelled || isAbortError(cause)) return;

        setErrors((current) => ({
          ...current,
          courses: messageFor(cause),
        }));
      });

    /*
     * BELGELER
     */
    const documentsPromise = apiFetch<DocumentData[]>(
      "/documents/",
      {
        signal: controller.signal,
      },
    )
      .then((data) => {
        if (cancelled) return;

        setDocuments(data);

        setErrors((current) => ({
          ...current,
          documents: null,
        }));
      })
      .catch((cause) => {
        if (cancelled || isAbortError(cause)) return;

        setErrors((current) => ({
          ...current,
          documents: messageFor(cause),
        }));
      });

    apiFetch<CurrentUser>("/users/me", { signal: controller.signal })
      .then((currentUser) => {
        if (!cancelled) setUsername(currentUser.username);
      })
      .catch(() => undefined);

    /*
     * Kurslar + belgeler bitince sadece
     * alt kısımdaki loading kapatılır.
     *
     * Çalışma süresini beklemez.
     */
    Promise.allSettled([
      coursesPromise,
      documentsPromise,
    ]).then(() => {
      if (!cancelled) {
        setLoading(false);
      }
    });

    /*
     * ÇALIŞMA SÜRESİ
     *
     * Tamamen bağımsız çalışıyor.
     */
    fetchStudySessions(controller.signal)
      .then((sessions) => {
        if (cancelled) return;

        setStudySessions(sessions);

        setErrors((current) => ({
          ...current,
          sessions: null,
        }));
      })
      .catch((cause) => {
        if (cancelled || isAbortError(cause)) return;

        setErrors((current) => ({
          ...current,
          sessions: messageFor(cause),
        }));
      })
      .finally(() => {
        if (!cancelled) {
          setStatsLoading(false);
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, []);

  /*
   * MODAL ESC KONTROLÜ
   */
  useEffect(() => {
    if (!studyModalOpen) return;

    function handleKeyDown(event: KeyboardEvent) {
      if (
        event.key === "Escape" &&
        !studySubmitting
      ) {
        setStudyModalOpen(false);
      }
    }

    document.body.style.overflow = "hidden";

    window.addEventListener(
      "keydown",
      handleKeyDown,
    );

    return () => {
      document.body.style.overflow = "";

      window.removeEventListener(
        "keydown",
        handleKeyDown,
      );
    };
  }, [
    studyModalOpen,
    studySubmitting,
  ]);

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

  async function submitStudySession(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault();

    if (studySubmitting) return;

    if (!selectedCourseId) {
      setStudyError(
        t("selectCourseError"),
      );

      return;
    }

    if (!studyDate) {
      setStudyError(
        t("selectDateError"),
      );

      return;
    }

    const durationMinutes =
      Number(studyMinutes);

    if (
      !studyMinutes ||
      !Number.isInteger(durationMinutes) ||
      durationMinutes <= 0
    ) {
      setStudyError(
        t("studyDurationError"),
      );

      return;
    }

    setStudySubmitting(true);
    setStudyError(null);

    try {
      await apiFetch(
        "/study-sessions/",
        {
          method: "POST",

          body: JSON.stringify({
            course_id:
              Number(selectedCourseId),

            study_date:
              studyDate,

            duration_minutes:
              durationMinutes,

            description:
              studyDescription.trim() ||
              null,
          }),
        },
      );

      setSelectedCourseId("");
      setStudyDate("");
      setStudyMinutes("");
      setStudyDescription("");

      setStudyModalOpen(false);

      /*
       * Çalışma kaydı eklendikten sonra
       * toplam süre yeniden çekiliyor.
       */
      try {
        const updatedSessions =
          await fetchStudySessions();

        setStudySessions(updatedSessions);

        setErrors((current) => ({
          ...current,
          sessions: null,
        }));

        setStudyStatus(
          t("studySessionSaved"),
        );
      } catch (statsCause) {
        if (isAbortError(statsCause)) {
          return;
        }

        setErrors((current) => ({
          ...current,

          sessions:
            apiErrorMessage(
              statsCause,
              t(
                "studySessionRefreshFailed",
              ),
              t(
                "operationUnavailable",
              ),
            ),
        }));
      }
    } catch (cause) {
      if (isAbortError(cause)) {
        return;
      }

      setStudyError(
        apiErrorMessage(
          cause,
          t("studySessionFailed"),
          t("operationUnavailable"),
        ),
      );
    } finally {
      setStudySubmitting(false);
    }
  }

  const error =
    errors.courses ??
    errors.documents ??
    errors.sessions;

  const totalStudyMinutes = studySessions.reduce(
    (total, session) => total + session.duration_minutes,
    0,
  );
  const weeklyMinutes = currentWeekMinutes(studySessions, dashboardDate);
  const maxWeeklyMinutes = Math.max(...weeklyMinutes);
  const activeDayIndex = (dashboardDate.getDay() + 6) % 7;

  return (
    <div className="dashboard-page">

      <div className="dashboard-hero-row">

        <header className="dashboard-greeting animate-enter">
          <p className="dashboard-eyebrow">
            {t("yourWorkspace")}
          </p>

          <h1>
            {t(greetingKey).replace(/[.!]$/, "")}{username ? `, ${username}` : ""}! 👋
          </h1>

          <p className="dashboard-subtitle">
            {t("dashboardIntro")}
          </p>

          <Link href="/courses" className="dashboard-continue-button interactive-button">
            <span aria-hidden="true">▶</span> {language === "tr" ? "Çalışmaya Devam Et" : "Continue Studying"}
          </Link>

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
                  : formatStudyDuration(
                      totalStudyMinutes,
                      language,
                      "minutes",
                    )}
              </h2>

              <p>
                {t(
                  "totalRecordedStudyTime",
                )}
              </p>

            </div>

          </div>

          <div className="dashboard-study-visuals" aria-hidden="true">
            <div className="dashboard-week-chart">
              {["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"].map((day, index) => (
                <span className={index === activeDayIndex ? "active" : ""} key={day} title={`${weeklyMinutes[index]} ${language === "tr" ? "dakika" : "minutes"}`}>
                  <i style={{ height: weeklyMinutes[index] > 0 && maxWeeklyMinutes > 0 ? `${Math.max(8, Math.round((weeklyMinutes[index] / maxWeeklyMinutes) * 50))}px` : "0px" }} />
                  <small>{language === "tr" ? day : ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][index]}</small>
                </span>
              ))}
            </div>
            <div className="dashboard-clock">
              <svg viewBox="0 0 120 120">
                <circle className="dashboard-clock-track" cx="60" cy="60" r="48" />
                <circle className="dashboard-clock-progress" cx="60" cy="60" r="48" />
                <path d="M60 34v27l19 0M60 61 46 76" />
                <circle cx="60" cy="61" r="4" />
              </svg>
            </div>
          </div>

          <button
            type="button"
            className="interactive-button dashboard-study-add-button"
            onClick={openStudyModal}
          >
            {t("addStudySession")}
          </button>

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
        <p
          className="dashboard-study-status"
          role="status"
        >
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

        <div
          className="dashboard-study-modal-overlay"
          role="presentation"
          onMouseDown={closeStudyModal}
        >

          <section
            className="dashboard-study-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="study-modal-title"
            onMouseDown={(event) =>
              event.stopPropagation()
            }
          >

            <div className="dashboard-study-modal-head">

              <div>

                <h2 id="study-modal-title">
                  {t(
                    "addStudySessionTitle",
                  )}
                </h2>

                <p>
                  {t(
                    "addStudySessionDescription",
                  )}
                </p>

              </div>

              <button
                type="button"
                onClick={closeStudyModal}
                aria-label={t("close")}
                disabled={studySubmitting}
              >
                ×
              </button>

            </div>

            <form
              className="dashboard-study-form"
              onSubmit={submitStudySession}
            >

              <label className="dashboard-study-field">

                <span>
                  {t("course")}
                </span>

                <select
                  value={selectedCourseId}
                  onChange={(event) =>
                    setSelectedCourseId(
                      event.target.value,
                    )
                  }
                >

                  <option value="">
                    {t("selectCourse")}
                  </option>

                  {courses.map(
                    (course) => (
                      <option
                        key={course.id}
                        value={course.id}
                      >
                        {course.name}
                      </option>
                    ),
                  )}

                </select>

              </label>

              <label className="dashboard-study-field">

                <span>
                  {t("date")}
                </span>

                <input
                  type="date"
                  value={studyDate}
                  onChange={(event) =>
                    setStudyDate(
                      event.target.value,
                    )
                  }
                />

              </label>

              <label className="dashboard-study-field">

                <span>
                  {t("studyDuration")}
                </span>

                <input
                  type="number"
                  min="1"
                  step="1"
                  placeholder={t(
                    "minutesExample",
                  )}
                  value={studyMinutes}
                  onChange={(event) =>
                    setStudyMinutes(
                      event.target.value,
                    )
                  }
                />

              </label>

              <label className="dashboard-study-field">

                <span>
                  {t("description")}{" "}
                  <small>
                    {t("optional")}
                  </small>
                </span>

                <textarea
                  rows={3}
                  placeholder={t(
                    "studyDescriptionPlaceholder",
                  )}
                  value={studyDescription}
                  onChange={(event) =>
                    setStudyDescription(
                      event.target.value,
                    )
                  }
                />

              </label>

              {studyError ? (

                <p
                  className="dashboard-study-modal-error"
                  role="alert"
                >
                  {studyError}
                </p>

              ) : null}

              <div className="dashboard-study-modal-actions">

                <button
                  type="button"
                  className="dashboard-study-cancel"
                  onClick={closeStudyModal}
                  disabled={studySubmitting}
                >
                  {t("cancel")}
                </button>

                <button
                  type="submit"
                  className="dashboard-study-save"
                  disabled={studySubmitting}
                >
                  {studySubmitting
                    ? t("saving")
                    : t("save")}
                </button>

              </div>

            </form>

          </section>

        </div>

      ) : null}

    </div>
  );
}
