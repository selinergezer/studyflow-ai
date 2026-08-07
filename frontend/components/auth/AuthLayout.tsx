"use client";

import type { ReactNode } from "react";
import Logo from "@/components/shared/Logo";
import AuthLeftPanel from "@/components/auth/AuthLeftPanel";
import { useLanguage } from "@/providers/LanguageProvider";

export default function AuthLayout({ children }: { children: ReactNode }) {
  const { t } = useLanguage();
  return (
    <main className="min-h-screen bg-neutral-50">
      <div className="mx-auto flex min-h-screen w-full max-w-[1440px] flex-col px-5 py-6 sm:px-8 sm:py-8 lg:px-12 xl:px-16">
        <header>
          <Logo />
        </header>

        <div className="grid flex-1 items-center gap-14 py-14 lg:grid-cols-[minmax(0,1fr)_440px] lg:gap-20 lg:py-16 xl:gap-28">
          <section className="animate-enter lg:pl-8 xl:pl-14">
            <AuthLeftPanel />
          </section>
          <section className="animate-enter w-full [animation-delay:80ms]">
            {children}
          </section>
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-3 text-xs text-gray-400">
          <p>© {new Date().getFullYear()} StudyFlow</p>
          <p>{t("designedForLearning")}</p>
        </footer>
      </div>
    </main>
  );
}
