"use client";

import { useLanguage } from "@/providers/LanguageProvider";
import type { TranslationKey } from "@/lib/translations";

const features = [
  {
    title: "pdfAnalysis", description: "pdfAnalysisDesc",
    icon: <path d="M7 3.75h6.5L18 8.25v12H7V3.75Zm6.25.5V8.5h4.25M9.75 12h5.5m-5.5 3.25h4" />,
  },
  {
    title: "quizGeneration", description: "quizGenerationDesc",
    icon: <path d="M9.5 9a2.5 2.5 0 1 1 3.8 2.15c-.8.5-1.3.9-1.3 1.85m0 3.25h.01M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z" />,
  },
  {
    title: "plannerFeature", description: "plannerFeatureDesc",
    icon: <path d="M6.5 3v3m11-3v3M4 9h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Zm3 8h3v3H8v-3Z" />,
  },
] satisfies Array<{ title: TranslationKey; description: TranslationKey; icon: React.ReactNode }>;

export default function AuthLeftPanel() {
  const { t } = useLanguage();
  return (
    <div className="max-w-xl">
      <p className="mb-5 text-sm font-medium text-blue-600">{t("calmerLearning")}</p>
      <h1 className="max-w-lg text-4xl font-semibold leading-[1.08] tracking-[-0.045em] text-gray-950 sm:text-5xl lg:text-[56px]">
        {t("studySmarter")}<br />{t("keepFocus")}
      </h1>
      <p className="mt-6 max-w-md text-base leading-7 text-gray-500">
        {t("authIntro")}
      </p>

      <div className="mt-10 grid gap-3 sm:grid-cols-3 lg:mt-14 lg:grid-cols-1 xl:grid-cols-3">
        {features.map((feature) => (
          <div key={feature.title} className="group rounded-2xl bg-white p-4 ring-1 ring-gray-200/80 transition duration-200 hover:-translate-y-0.5 hover:ring-gray-300">
            <svg className="size-5 text-gray-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              {feature.icon}
            </svg>
            <h2 className="mt-4 text-sm font-medium text-gray-900">{t(feature.title)}</h2>
            <p className="mt-1.5 text-xs leading-5 text-gray-500">{t(feature.description)}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
