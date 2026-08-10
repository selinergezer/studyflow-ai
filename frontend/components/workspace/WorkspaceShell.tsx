"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import Logo from "@/components/shared/Logo";
import { useLanguage } from "@/providers/LanguageProvider";

const navigation = [
  { label: "dashboard", href: "/" }, { label: "courses", href: "/courses" }, { label: "library", href: "/library" }, { label: "quizzes", href: "/quiz" }, { label: "flashcards", href: "/flashcards" }, { label: "studyPlan", href: "/study-plan" }, { label: "settings", href: "/settings" },
] as const;

export default function WorkspaceShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const { t } = useLanguage();

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
    });
    return () => window.removeEventListener("studyflow-auth-expired", handleExpiredSession);
  }, [router]);

  function isActive(href: string) {
    if (href === "/library") {
      return pathname === href || pathname === "/upload" || pathname.startsWith("/documents/");
    }
    if (href === "/courses") return pathname === href || pathname.startsWith("/courses/");
    return pathname === href;
  }

  if (!authChecked || !isAuthenticated) {
    return <main className="min-h-screen bg-neutral-50" />;
  }

  return (
    <main className="min-h-screen bg-neutral-50 text-gray-900">
      <header className="border-b border-gray-200/80 bg-white">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-6 px-5 sm:px-8">
          <Logo href="/" />
          <nav className="hidden items-center gap-1 xl:flex" aria-label={t("mainNavigation")}>
            {navigation.map((item) => {
              const active = isActive(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  className={`rounded-lg px-3 py-2 text-sm transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 ${active ? "bg-gray-100 font-medium text-gray-950" : "text-gray-500 hover:bg-gray-50 hover:text-gray-900"}`}
                >
                  {t(item.label)}
                </Link>
              );
            })}
          </nav>
          <Link href={isAuthenticated ? "/settings" : "/login"} className="flex size-9 shrink-0 items-center justify-center rounded-full bg-gray-900 text-xs font-medium text-white transition hover:bg-gray-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600" aria-label={t("openSettings")}>
            SF
          </Link>
        </div>
        <nav className="mx-auto flex max-w-7xl gap-1 overflow-x-auto px-5 pb-3 xl:hidden" aria-label={t("mobileNavigation")}>
          {navigation.map((item) => {
            const active = isActive(item.href);
            return (
              <Link key={item.href} href={item.href} aria-current={active ? "page" : undefined} className={`shrink-0 rounded-lg px-3 py-1.5 text-sm transition ${active ? "bg-gray-100 font-medium text-gray-950" : "text-gray-500"}`}>
                {t(item.label)}
              </Link>
            );
          })}
        </nav>
      </header>
      {children}
    </main>
  );
}
