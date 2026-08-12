"use client";

import Link from "next/link";
import { useSyncExternalStore, type ReactNode } from "react";
import AuthLeftPanel from "@/components/auth/AuthLeftPanel";
import { useLanguage } from "@/providers/LanguageProvider";

export default function AuthLayout({ children }: { children: ReactNode }) {
  const { t } = useLanguage();
  const theme = useSyncExternalStore(
    (callback) => { window.addEventListener("studyflow-theme-change", callback); window.addEventListener("storage", callback); return () => { window.removeEventListener("studyflow-theme-change", callback); window.removeEventListener("storage", callback); }; },
    () => localStorage.getItem("studyflow.theme") === "light" ? "light" : "dark",
    () => "dark",
  );

  function setTheme(value: "light" | "dark") {
    localStorage.setItem("studyflow.theme", value);
    document.documentElement.classList.toggle("dark", value === "dark");
    window.dispatchEvent(new Event("studyflow-theme-change"));
  }

  return (
    <main className="auth-page" data-auth-theme={theme}>
      <div className="auth-shell">
        <div className="auth-lamp-glow" aria-hidden="true" />
        <header className="auth-nav">
          <Link href="/" className="auth-brand" aria-label={t("studyflowHome")}>
            <svg width="30" height="30" viewBox="0 0 30 30" fill="none" aria-hidden="true"><rect width="30" height="30" rx="7" fill="#e8a33d"/><path d="M8 15 Q 12 8, 15 15 T 22 15" stroke="#10141f" strokeWidth="2.4" fill="none" strokeLinecap="round"/></svg>
            <span>StudyFlow</span>
          </Link>
          <div className="auth-nav-actions">
            <span className="auth-card-number">Kart No. 014</span>
            <div className="auth-theme-switch" role="group" aria-label="Tema seç">
              <button type="button" className={theme === "light" ? "active" : ""} onClick={() => setTheme("light")} aria-label="Aydınlık mod" aria-pressed={theme === "light"}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg></button>
              <button type="button" className={theme === "dark" ? "active" : ""} onClick={() => setTheme("dark")} aria-label="Karanlık mod" aria-pressed={theme === "dark"}><svg viewBox="0 0 24 24" fill="currentColor"><path d="M20 14.5A8.5 8.5 0 1 1 9.5 4 7 7 0 0 0 20 14.5Z"/></svg></button>
            </div>
          </div>
        </header>

        <div className="auth-hero">
          <AuthLeftPanel />
          <section className="auth-form-column animate-enter [animation-delay:80ms]">{children}</section>
        </div>

        <footer className="auth-footer">
          <p>© {new Date().getFullYear()} StudyFlow</p>
          <p>{t("designedForLearning")}</p>
        </footer>
      </div>
    </main>
  );
}
