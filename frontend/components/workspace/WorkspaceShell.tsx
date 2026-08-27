"use client";

import {
  useEffect,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import { useLanguage } from "@/providers/LanguageProvider";
import { apiFetch, isAbortError, type CurrentUser } from "@/lib/api";

type NotificationData = {
  id: number;
  title: string;
  message: string;
  notification_type: string;
  is_read: boolean;
  created_at: string;
};

const navigation = [
  { label: "dashboard", href: "/dashboard" },
  { label: "courses", href: "/courses" },
  { label: "quizzes", href: "/quiz" },
  { label: "flashcards", href: "/flashcards" },
  { label: "studyPlan", href: "/study-plan" },
  { label: "studyRoom", href: "/study-room" },
] as const;

export default function WorkspaceShell({
  children,
}: {
  children: ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();

  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [user, setUser] = useState<CurrentUser | null>(null);

  const [notifications, setNotifications] = useState<
    NotificationData[]
  >([]);

  const [unreadCount, setUnreadCount] = useState(0);

  const [notificationsOpen, setNotificationsOpen] =
    useState(false);

  const [notificationsLoading, setNotificationsLoading] =
    useState(false);

  const [notificationsLoaded, setNotificationsLoaded] =
    useState(false);

  const { t, language } = useLanguage();

  const theme = useSyncExternalStore(
    (callback) => {
      window.addEventListener(
        "studyflow-theme-change",
        callback,
      );

      window.addEventListener(
        "storage",
        callback,
      );

      return () => {
        window.removeEventListener(
          "studyflow-theme-change",
          callback,
        );

        window.removeEventListener(
          "storage",
          callback,
        );
      };
    },

    () =>
      localStorage.getItem("studyflow.theme") === "light"
        ? "light"
        : "dark",

    () => "dark",
  );

  // =========================================================
  // KULLANICI OTURUM KONTROLÜ
  // =========================================================

  useEffect(() => {
    const controller = new AbortController();
    function handleExpiredSession() {
      setIsAuthenticated(false);
      router.replace("/login");
    }

    window.addEventListener(
      "studyflow-auth-expired",
      handleExpiredSession,
    );

    queueMicrotask(() => {
      const hasToken = Boolean(
        localStorage.getItem("access_token"),
      );

      setIsAuthenticated(hasToken);
      setAuthChecked(true);

      if (!hasToken) {
        router.replace("/login");
        return;
      }

      apiFetch<CurrentUser>("/users/me", { signal: controller.signal })
        .then(setUser)
        .catch((cause) => {
          if (isAbortError(cause)) return;
        });
    });

    return () => {
      controller.abort();
      window.removeEventListener(
        "studyflow-auth-expired",
        handleExpiredSession,
      );
    };
  }, [router]);

  // =========================================================
  // TEMA
  // =========================================================

  useEffect(() => {
    document.documentElement.classList.toggle(
      "dark",
      theme === "dark",
    );
  }, [theme]);

  // =========================================================
  // KULLANICI BİLGİSİ DEĞİŞTİĞİNDE
  // =========================================================

  useEffect(() => {
    function handleUserChange(event: Event) {
      const updatedUser = (
        event as CustomEvent<CurrentUser>
      ).detail;

      if (updatedUser) {
        setUser(updatedUser);
      }
    }

    window.addEventListener(
      "studyflow-user-change",
      handleUserChange,
    );

    return () => {
      window.removeEventListener(
        "studyflow-user-change",
        handleUserChange,
      );
    };
  }, []);

  // =========================================================
  // BİLDİRİMLERİ YÜKLE
  // =========================================================

  async function loadNotifications(signal?: AbortSignal) {
    try {
      setNotificationsLoading(true);

      const notificationData =
        await apiFetch<NotificationData[]>(
          "/notifications/",
          { signal },
        );

      setNotifications(notificationData);
      setNotificationsLoaded(true);
    } catch (error) {
      if (isAbortError(error)) return;
    } finally {
      if (!signal?.aborted) setNotificationsLoading(false);
    }
  }

  useEffect(() => {
    if (!isAuthenticated) return;
    const controller = new AbortController();
    queueMicrotask(() => {
      apiFetch<{ unread_count: number }>(
        "/notifications/unread-count",
        { signal: controller.signal },
      )
        .then((data) => setUnreadCount(data.unread_count))
        .catch((cause) => {
          if (isAbortError(cause)) return;
        });
    });
    return () => controller.abort();
  }, [isAuthenticated]);

  // =========================================================
  // BİLDİRİMİ OKUNDU YAP
  // =========================================================

  async function markNotificationAsRead(
    notification: NotificationData,
  ) {
    if (notification.is_read) return;

    try {
      await apiFetch(
        `/notifications/${notification.id}/read`,
        {
          method: "PUT",
        },
      );

      setNotifications((current) =>
        current.map((item) =>
          item.id === notification.id
            ? {
                ...item,
                is_read: true,
              }
            : item,
        ),
      );

      setUnreadCount((current) =>
        Math.max(0, current - 1),
      );
    } catch {}
  }

  // =========================================================
  // BİLDİRİMİ SİL
  // =========================================================

  async function deleteNotification(
    notification: NotificationData,
  ) {
    try {
      await apiFetch(
        `/notifications/${notification.id}`,
        {
          method: "DELETE",
        },
      );

      setNotifications((current) =>
        current.filter(
          (item) => item.id !== notification.id,
        ),
      );

      if (!notification.is_read) {
        setUnreadCount((current) =>
          Math.max(0, current - 1),
        );
      }
    } catch {}
  }

  // =========================================================
  // ACTIVE MENU
  // =========================================================

  function isActive(href: string) {
    if (href === "/courses") {
      return (
        pathname === href ||
        pathname.startsWith("/courses/") ||
        pathname.startsWith("/documents/")
      );
    }

    if (href === "/quiz") {
      return (
        pathname === href ||
        pathname.startsWith("/quiz/")
      );
    }

    return pathname === href;
  }

  // =========================================================
  // TEMA DEĞİŞTİR
  // =========================================================

  function setTheme(
    value: "light" | "dark",
  ) {
    localStorage.setItem(
      "studyflow.theme",
      value,
    );

    document.documentElement.classList.toggle(
      "dark",
      value === "dark",
    );

    window.dispatchEvent(
      new Event("studyflow-theme-change"),
    );
  }

  // =========================================================
  // AVATAR
  // =========================================================

  const initials = user?.username
    ? user.username
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0])
        .join("")
        .toLocaleUpperCase("tr-TR")
    : "SF";

  const pageModifier = pathname === "/dashboard"
    ? " workspace-page--dashboard"
    : pathname === "/courses"
      ? " workspace-page--courses"
    : pathname === "/quiz"
      ? " workspace-page--quizzes"
    : pathname.startsWith("/documents/")
      ? " workspace-page--document"
    : pathname === "/library"
      ? " workspace-page--library"
      : pathname === "/upload"
        ? " workspace-page--upload"
        : "";

  // =========================================================
  // AUTH BEKLENİYOR
  // =========================================================

  if (
    !authChecked ||
    !isAuthenticated
  ) {
    return (
      <main
        className="workspace-page min-h-screen"
        data-workspace-theme={theme}
      />
    );
  }

  // =========================================================
  // SAYFA
  // =========================================================

  return (
    <main
      className={`workspace-page${pageModifier}`}
      data-workspace-theme={theme}
    >
      <header className="workspace-header">
        <div className="workspace-topbar">

          {/* LOGO */}

          <Link
            href="/dashboard"
            className="workspace-brand"
            aria-label={t("studyflowHome")}
          >
            <svg
              width="28"
              height="28"
              viewBox="0 0 30 30"
              fill="none"
              aria-hidden="true"
            >
              <rect
                width="30"
                height="30"
                rx="7"
                fill="#e8a33d"
              />

              <path
                d="M8 15 Q 12 8, 15 15 T 22 15"
                stroke="#10141f"
                strokeWidth="2.4"
                fill="none"
                strokeLinecap="round"
              />
            </svg>

            <span>StudyFlow</span>
          </Link>

          {/* NAVIGATION */}

          <nav
            className="workspace-tabs"
            aria-label={t("mainNavigation")}
          >
            {navigation.map((item) => {
              const active =
                isActive(item.href);

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={
                    active
                      ? "page"
                      : undefined
                  }
                  className={
                    active
                      ? "active"
                      : ""
                  }
                >
                  {t(item.label)}
                </Link>
              );
            })}
          </nav>

          {/* SAĞ TARAF */}

          <div className="workspace-top-actions">

            {/* TEMA */}

            <div
              className="workspace-theme-switch"
              role="group"
              aria-label={t("selectTheme")}
            >
              <button
                type="button"
                className={
                  theme === "light"
                    ? "active"
                    : ""
                }
                onClick={() =>
                  setTheme("light")
                }
                aria-label={t("lightMode")}
                aria-pressed={
                  theme === "light"
                }
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <circle
                    cx="12"
                    cy="12"
                    r="4"
                  />

                  <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
                </svg>
              </button>

              <button
                type="button"
                className={
                  theme === "dark"
                    ? "active"
                    : ""
                }
                onClick={() =>
                  setTheme("dark")
                }
                aria-label={t("darkMode")}
                aria-pressed={
                  theme === "dark"
                }
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="currentColor"
                >
                  <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4 7 7 0 0 0 20 14.5Z" />
                </svg>
              </button>
            </div>

            {/* BİLDİRİM */}

            <div className="workspace-notification">
              <button
                type="button"
                className="workspace-notification-button"
                aria-label={t("notifications")}
                aria-expanded={
                  notificationsOpen
                }
                onClick={() => {
                  const nextValue =
                    !notificationsOpen;

                  setNotificationsOpen(
                    nextValue,
                  );

                  if (
                    nextValue &&
                    !notificationsLoaded &&
                    !notificationsLoading
                  ) {
                    loadNotifications();
                  }
                }}
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
                  <path d="M13.7 21a2 2 0 0 1-3.4 0" />
                </svg>

                {unreadCount > 0 ? (
                  <span className="workspace-notification-count">
                    {unreadCount > 9
                      ? "9+"
                      : unreadCount}
                  </span>
                ) : null}
              </button>

              {notificationsOpen ? (
                <div className="workspace-notification-panel">
                  <div className="workspace-notification-panel-head">
                    <div>
                      <strong>
                        {t("notifications")}
                      </strong>

                      <span>
                        {unreadCount} {t(unreadCount === 1 ? "unreadNotification" : "unreadNotifications")}
                      </span>
                    </div>

                    <button
                      type="button"
                      onClick={() =>
                        setNotificationsOpen(
                          false,
                        )
                      }
                      aria-label={t("closeNotifications")}
                    >
                      ×
                    </button>
                  </div>

                  <div className="workspace-notification-list">

                    {notificationsLoading ? (
                      <div className="workspace-notification-empty">
                        {t("notificationsLoading")}
                      </div>
                    ) : notifications.length ===
                      0 ? (
                      <div className="workspace-notification-empty">
                        {t("noNotifications")}
                      </div>
                    ) : (
                      notifications.map(
                        (notification) => (
                          <div
                            key={
                              notification.id
                            }
                            className={`workspace-notification-item ${
                              notification.is_read
                                ? "is-read"
                                : "is-unread"
                            }`}
                          >
                            <button
                              type="button"
                              className="workspace-notification-content"
                              onClick={() =>
                                markNotificationAsRead(
                                  notification,
                                )
                              }
                            >
                              <span className="workspace-notification-title">
                                {
                                  notification.title
                                }
                              </span>

                              <span className="workspace-notification-message">
                                {
                                  notification.message
                                }
                              </span>

                              <span className="workspace-notification-date">
                                {new Date(
                                  notification.created_at,
                                ).toLocaleString(
                                  language === "tr" ? "tr-TR" : "en-US",
                                  {
                                    day: "2-digit",
                                    month: "short",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  },
                                )}
                              </span>
                            </button>

                            <button
                              type="button"
                              className="workspace-notification-delete"
                              onClick={() =>
                                deleteNotification(
                                  notification,
                                )
                              }
                              aria-label={t("deleteNotification")}
                            >
                              ×
                            </button>
                          </div>
                        ),
                      )
                    )}
                  </div>
                </div>
              ) : null}
            </div>

            {/* AVATAR */}

            <Link
              href="/settings"
              className="workspace-avatar"
              aria-label={t(
                "openSettings",
              )}
            >
              {initials}
            </Link>
          </div>
        </div>
      </header>

      {children}
    </main>
  );
}
