"use client";

import Link from "next/link";
import Card from "@/components/ui/Card";
import { useLanguage } from "@/providers/LanguageProvider";
import type { TranslationKey } from "@/lib/translations";

type PlaceholderPageProps = {
  eyebrow: TranslationKey;
  title: TranslationKey;
  description: TranslationKey;
  action: {
    label: TranslationKey;
    href: string;
  };
  items?: Array<{ title: string; titleKey?: TranslationKey; detail: TranslationKey }>;
};

export default function PlaceholderPage({
  eyebrow,
  title,
  description,
  action,
  items = [],
}: PlaceholderPageProps) {
  const { t } = useLanguage();
  return (
    <div className="mx-auto max-w-5xl px-5 py-12 sm:px-8 sm:py-16">
      <div className="animate-enter flex flex-col justify-between gap-6 sm:flex-row sm:items-end">
        <div className="max-w-2xl">
          <p className="text-sm font-medium text-blue-600">{t(eyebrow)}</p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-gray-950 sm:text-4xl">{t(title)}</h1>
          <p className="mt-4 max-w-xl text-base leading-7 text-gray-500">{t(description)}</p>
        </div>
        <Link href={action.href} className="inline-flex h-11 items-center justify-center gap-2 self-start rounded-xl bg-blue-600 px-4 text-sm font-medium text-white transition hover:bg-blue-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 sm:self-auto">
          <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M12 5v14M5 12h14" /></svg>
          {t(action.label)}
        </Link>
      </div>

      {items.length ? (
        <section className="animate-enter mt-10 [animation-delay:60ms]" aria-label={`${t(title)} ${t("items")}`}>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {items.map((item) => (
              <Card key={item.title} className="p-5 shadow-none">
                <span className="flex size-9 items-center justify-center rounded-xl bg-gray-100 text-gray-600" aria-hidden="true">
                  <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M8 12.5 10.5 15 16 9.5M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Z" /></svg>
                </span>
                <h2 className="mt-5 text-sm font-medium text-gray-950">{item.titleKey ? t(item.titleKey) : item.title}</h2>
                <p className="mt-2 text-sm leading-6 text-gray-500">{t(item.detail)}</p>
              </Card>
            ))}
          </div>
        </section>
      ) : (
        <Card className="animate-enter mt-10 flex min-h-72 flex-col items-center justify-center p-8 text-center [animation-delay:60ms]">
          <span className="flex size-11 items-center justify-center rounded-2xl bg-gray-100 text-gray-500" aria-hidden="true">
            <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M5 4.5h10.5A2.5 2.5 0 0 1 18 7v12.5H7.5A2.5 2.5 0 0 1 5 17V4.5ZM5 17a2.5 2.5 0 0 1 2.5-2.5H18" /></svg>
          </span>
          <h2 className="mt-5 text-sm font-medium text-gray-950">{t("workspaceReady")}</h2>
          <p className="mt-2 max-w-sm text-sm leading-6 text-gray-500">{t("workspaceReadyDesc")}</p>
          <Link href={action.href} className="mt-6 text-sm font-medium text-blue-600 transition hover:text-blue-700">{t(action.label)} →</Link>
        </Card>
      )}
    </div>
  );
}
