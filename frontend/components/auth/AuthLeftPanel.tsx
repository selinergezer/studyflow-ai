"use client";

import { useLanguage } from "@/providers/LanguageProvider";
import type { TranslationKey } from "@/lib/translations";

const features = [
  {
    title: "pdfAnalysis", description: "pdfAnalysisDesc",
  },
  {
    title: "quizGeneration", description: "quizGenerationDesc",
  },
  {
    title: "plannerFeature", description: "plannerFeatureDesc",
  },
] satisfies Array<{ title: TranslationKey; description: TranslationKey }>;

export default function AuthLeftPanel() {
  const { t } = useLanguage();
  return (
    <section className="auth-intro animate-enter">
      <p className="auth-eyebrow">Masa lambası yanık · gece çalışma modu</p>
      <h1 className="auth-title">
        {t("studySmarter")}<br /><span className="auth-annotated">{t("keepFocus")}<svg viewBox="0 0 320 90" aria-hidden="true"><path d="M8,46 C 8,16 60,4 160,6 C 270,8 312,22 308,50 C 304,78 230,86 150,84 C 70,82 8,74 10,50" /></svg></span>
      </h1>
      <p className="auth-subtitle">{t("authIntro")}</p>

      <div className="auth-note-strip">
        {features.map((feature, index) => (
          <div key={feature.title} className="auth-postit">
            <span className="auth-tape" aria-hidden="true" />
            <span className="auth-note-number">not #0{index + 1}</span>
            <h2>{t(feature.title)}</h2>
            <p>{t(feature.description)}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
