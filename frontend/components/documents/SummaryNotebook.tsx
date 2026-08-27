"use client";

import { useMemo, useState, useSyncExternalStore } from "react";

import MarkdownSummary from "@/components/documents/MarkdownSummary";
import Button from "@/components/ui/Button";

const DESKTOP_QUERY = "(min-width: 1181px)";
const TARGET_PAGE_LENGTH = 1150;

function findReadableBreak(text: string, target: number) {
  if (text.length <= target) return text.length;

  const minimum = Math.floor(target * 0.72);
  const maximum = Math.min(text.length, Math.ceil(target * 1.18));
  const window = text.slice(minimum, maximum);
  const paragraphBreak = window.lastIndexOf("\n\n");

  if (paragraphBreak >= 0) return minimum + paragraphBreak;

  const sentenceMatches = Array.from(window.matchAll(/[.!?…](?:["')\]]*)\s+/g));
  const sentenceBreak = sentenceMatches.at(-1);

  if (sentenceBreak?.index != null) {
    return minimum + sentenceBreak.index + sentenceBreak[0].length;
  }

  const wordBreak = window.lastIndexOf(" ");
  return wordBreak >= 0 ? minimum + wordBreak : maximum;
}

export function splitSummaryIntoPages(summary: string) {
  const normalized = summary.replace(/\r\n?/g, "\n").trim();
  if (!normalized) return [];

  const estimatedPageCount = Math.max(
    1,
    Math.ceil(normalized.length / TARGET_PAGE_LENGTH),
  );
  const balancedTarget = Math.ceil(normalized.length / estimatedPageCount);
  const pages: string[] = [];
  let remaining = normalized;

  while (remaining.length > balancedTarget) {
    const breakAt = findReadableBreak(remaining, balancedTarget);
    pages.push(remaining.slice(0, breakAt).trim());
    remaining = remaining.slice(breakAt).trim();
  }

  if (remaining) pages.push(remaining);
  return pages;
}

function useDesktopSpread() {
  return useSyncExternalStore(
    (callback) => {
      const media = window.matchMedia(DESKTOP_QUERY);
      media.addEventListener("change", callback);
      return () => media.removeEventListener("change", callback);
    },
    () => window.matchMedia(DESKTOP_QUERY).matches,
    () => true,
  );
}

type SummaryNotebookProps = {
  summary: string;
  streaming: boolean;
  language: "tr" | "en";
  onGenerate: () => void;
};

export default function SummaryNotebook({
  summary,
  streaming,
  language,
  onGenerate,
}: SummaryNotebookProps) {
  const desktop = useDesktopSpread();
  const pages = useMemo(() => splitSummaryIntoPages(summary), [summary]);
  const pagesPerView = desktop ? 2 : 1;
  const viewCount = Math.max(1, Math.ceil(pages.length / pagesPerView));
  const [viewIndex, setViewIndex] = useState(0);
  const activeViewIndex = Math.min(viewIndex, viewCount - 1);
  const firstPageIndex = activeViewIndex * pagesPerView;

  function renderPage(pageIndex: number, side: "left" | "right") {
    const page = pages[pageIndex];

    return (
      <article className={`summary-notebook-page summary-notebook-page--${side}`}>
        <span className="summary-notebook-margin" aria-hidden="true" />

        <div className="summary-notebook-content">
          {page ? <MarkdownSummary>{page}</MarkdownSummary> : null}

          {!summary && side === "left" ? (
            <div className="summary-notebook-empty">
              <p>
                {language === "tr"
                  ? "Bu PDF için henüz bir özet oluşturulmadı."
                  : "A summary has not been created for this PDF yet."}
              </p>
              <Button type="button" onClick={onGenerate} disabled={streaming}>
                {streaming
                  ? language === "tr"
                    ? "Özet oluşturuluyor..."
                    : "Generating summary..."
                  : language === "tr"
                    ? "Özet Oluştur →"
                    : "Create Summary →"}
              </Button>
            </div>
          ) : null}
        </div>

        {page ? <span className="summary-notebook-page-number">{pageIndex + 1}</span> : null}
      </article>
    );
  }

  return (
    <section className="document-summary-view" aria-label={language === "tr" ? "Belge özeti" : "Document summary"}>
      <div className="summary-notebook">
        {renderPage(firstPageIndex, "left")}

        <div className="summary-notebook-binding" aria-hidden="true">
          {Array.from({ length: 12 }, (_, index) => <i key={index} />)}
        </div>

        {desktop ? renderPage(firstPageIndex + 1, "right") : null}
      </div>

      {streaming && summary ? (
        <p className="summary-notebook-streaming">
          {language === "tr" ? "Özet oluşturuluyor..." : "Generating summary..."}
        </p>
      ) : null}

      {pages.length ? (
        <nav className="summary-notebook-pagination" aria-label={language === "tr" ? "Özet sayfaları" : "Summary pages"}>
          <button
            type="button"
            disabled={activeViewIndex === 0}
            onClick={() => setViewIndex((current) => Math.max(0, current - 1))}
          >
            ← {language === "tr" ? "Önceki Sayfa" : "Previous Page"}
          </button>

          <span>{activeViewIndex + 1} / {viewCount}</span>

          <button
            type="button"
            disabled={activeViewIndex >= viewCount - 1}
            onClick={() => setViewIndex((current) => Math.min(viewCount - 1, current + 1))}
          >
            {language === "tr" ? "Sonraki Sayfa" : "Next Page"} →
          </button>
        </nav>
      ) : null}
    </section>
  );
}
