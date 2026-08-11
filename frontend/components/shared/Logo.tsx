"use client";

import Link from "next/link";
import { useLanguage } from "@/providers/LanguageProvider";

export default function Logo({ href = "/" }: { href?: string }) {
  const { t } = useLanguage();
  return (
    <Link href={href} className="inline-flex items-center gap-2.5 rounded-lg focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-blue-600" aria-label={t("studyflowHome")}>
      <span className="grid size-8 grid-cols-2 gap-[3px] rounded-[10px] bg-gray-950 p-[7px]" aria-hidden="true">
        <span className="rounded-[2px] bg-white" />
        <span className="rounded-[2px] bg-white/55" />
        <span className="rounded-[2px] bg-white/55" />
        <span className="rounded-[2px] bg-white" />
      </span>
      <span className="text-[15px] font-semibold tracking-[-0.02em] text-gray-950">StudyFlow</span>
    </Link>
  );
}
