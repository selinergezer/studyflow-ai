"use client";

import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useLanguage } from "@/providers/LanguageProvider";
import { apiFetch, type CurrentUser } from "@/lib/api";

const navigation = [
  { label: "dashboard", href: "/dashboard" }, { label: "courses", href: "/courses" }, { label: "library", href: "/library" }, { label: "quizzes", href: "/quiz" }, { label: "flashcards", href: "/flashcards" }, { label: "studyPlan", href: "/study-plan" }, { label: "settings", href: "/settings" },
] as const;

export default function WorkspaceShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const { t } = useLanguage();
  const theme = useSyncExternalStore(
    (callback) => { window.addEventListener("studyflow-theme-change", callback); window.addEventListener("storage", callback); return () => { window.removeEventListener("studyflow-theme-change", callback); window.removeEventListener("storage", callback); }; },
    () => localStorage.getItem("studyflow.theme") === "light" ? "light" : "dark",
    () => "dark",
  );

  useEffect(() => {
    function handleExpiredSession() {
      setIsAuthenticated(false);
      router.replace("/login");
    }
    window.addEventListener("studyflow-auth-expired", handleExpiredSession);
    queueMicrotask(() => {
      const hasToken = Boolean(localStorage.getItem("access_token"));
      setIsAuthenticated(hasToken);
      setAuthChecked(true);
      if (!hasToken) router.replace("/login");
      else apiFetch<CurrentUser>("/users/me").then(setUser).catch((cause) => console.error(cause));
    });
    return () => window.removeEventListener("studyflow-auth-expired", handleExpiredSession);
  }, [router]);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  useEffect(() => {
    function handleUserChange(event: Event) {
      const updatedUser = (event as CustomEvent<CurrentUser>).detail;
      if (updatedUser) setUser(updatedUser);
    }
    window.addEventListener("studyflow-user-change", handleUserChange);
    return () => window.removeEventListener("studyflow-user-change", handleUserChange);
  }, []);

  function isActive(href: string) {
    if (href === "/library") {
      return pathname === href || pathname === "/upload" || pathname.startsWith("/documents/");
    }
    if (href === "/courses") return pathname === href || pathname.startsWith("/courses/");
    if (href === "/quiz") return pathname === href || pathname.startsWith("/quiz/");
    return pathname === href;
  }

  function setTheme(value: "light" | "dark") {
    localStorage.setItem("studyflow.theme", value);
    document.documentElement.classList.toggle("dark", value === "dark");
    window.dispatchEvent(new Event("studyflow-theme-change"));
  }

  const initials = user?.username
    ? user.username.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toLocaleUpperCase("tr-TR")
    : "SF";

  if (!authChecked || !isAuthenticated) {
    return <main className="workspace-page min-h-screen" data-workspace-theme={theme} />;
  }

  return (
    <main className="workspace-page" data-workspace-theme={theme}>
      <header className="workspace-header">
        <div className="workspace-topbar">
          <Link href="/dashboard" className="workspace-brand" aria-label={t("studyflowHome")}><svg width="28" height="28" viewBox="0 0 30 30" fill="none" aria-hidden="true"><rect width="30" height="30" rx="7" fill="#e8a33d"/><path d="M8 15 Q 12 8, 15 15 T 22 15" stroke="#10141f" strokeWidth="2.4" fill="none" strokeLinecap="round"/></svg><span>StudyFlow</span></Link>
          <nav className="workspace-tabs" aria-label={t("mainNavigation")}>
            {navigation.map((item) => {
              const active = isActive(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={active ? "active" : ""}
                >
                  {t(item.label)}
                </Link>
              );
            })}
          </nav>
          <div className="workspace-top-actions"><div className="workspace-theme-switch" role="group" aria-label="Tema seç"><button type="button" className={theme === "light" ? "active" : ""} onClick={() => setTheme("light")} aria-label="Aydınlık mod" aria-pressed={theme === "light"}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg></button><button type="button" className={theme === "dark" ? "active" : ""} onClick={() => setTheme("dark")} aria-label="Karanlık mod" aria-pressed={theme === "dark"}><svg viewBox="0 0 24 24" fill="currentColor"><path d="M20 14.5A8.5 8.5 0 1 1 9.5 4 7 7 0 0 0 20 14.5Z"/></svg></button></div><Link href="/settings" className="workspace-avatar" aria-label={t("openSettings")}>{initials}</Link></div>
        </div>
      </header>
      {children}
    </main>
  );
}
