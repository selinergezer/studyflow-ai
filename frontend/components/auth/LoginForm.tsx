"use client";

import { useRouter } from "next/navigation";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { useLanguage } from "@/providers/LanguageProvider";

/**
 * MVP entry point for the application.
 *
 * This component intentionally owns the transition into the authenticated area.
 * When authentication is introduced, replace this temporary action with the
 * sign-in form while keeping AuthLayout and the /login route unchanged.
 */
export default function LoginForm() {
  const router = useRouter();
  const { t } = useLanguage();

  function startStudying() {
    router.push("/");
  }

  return (
    <Card className="p-6 sm:p-8 lg:p-9">
      <div className="flex size-11 items-center justify-center rounded-2xl bg-blue-50 text-blue-600" aria-hidden="true">
        <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M5 4.5h10.5A2.5 2.5 0 0 1 18 7v12.5H7.5A2.5 2.5 0 0 1 5 17V4.5Z" />
          <path d="M5 17a2.5 2.5 0 0 1 2.5-2.5H18M9 8h5" />
        </svg>
      </div>

      <div className="mt-7">
        <h2 className="text-2xl font-semibold tracking-[-0.03em] text-gray-950 sm:text-[28px]">
          {t("learningReady")}
        </h2>
        <p className="mt-3 max-w-sm text-sm leading-6 text-gray-500">
          {t("learningReadyDesc")}
        </p>
      </div>

      <Button type="button" fullWidth className="mt-8 h-12" onClick={startStudying}>
        {t("startStudying")}
        <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M5 12h14m-5-5 5 5-5 5" />
        </svg>
      </Button>

      <p className="mt-5 text-center text-xs leading-5 text-gray-400">
        {t("noAccountNeeded")}
      </p>
    </Card>
  );
}
