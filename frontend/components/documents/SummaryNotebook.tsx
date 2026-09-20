"use client";

import { useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { blockText, notebookPageHtml, paginateNotebook, summaryBlocks, type NotebookPagination } from "@/lib/notebook-pagination";
import Button from "@/components/ui/Button";
import type { SummaryGenerationStatus } from "@/lib/api";
import type { SummaryProgress } from "@/lib/summary-session";

const DESKTOP_QUERY = "(min-width: 1181px)";
function useDesktopSpread() {
  return useSyncExternalStore(
    (callback) => { const media = window.matchMedia(DESKTOP_QUERY); media.addEventListener("change", callback); return () => media.removeEventListener("change", callback); },
    () => window.matchMedia(DESKTOP_QUERY).matches,
    () => true,
  );
}

type SummaryNotebookProps = {
  summary: string;
  streaming: boolean;
  generationStatus: SummaryGenerationStatus | null;
  progress?: SummaryProgress;
  language: "tr" | "en";
  onGenerate: () => void;
};

export default function SummaryNotebook({ summary, streaming, generationStatus, progress, language, onGenerate }: SummaryNotebookProps) {
  const desktop = useDesktopSpread();
  const [pagination, setPagination] = useState<NotebookPagination>({ blocks: [], pages: [] });
  const [viewIndex, setViewIndex] = useState(0);
  const leftRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const cacheRef = useRef<{ width: number; height: number; pagination: NotebookPagination } | null>(null);
  const updateRef = useRef<(invalidate?: boolean) => void>(() => {});

  useLayoutEffect(() => {
    function update(invalidate = false) {
      const measure = measureRef.current;
      const areas = [leftRef.current, rightRef.current].filter((area) => area !== null);
      if (!measure || !areas.length) return;
      // Both sides may have different padding. Use the smaller real content
      // rectangle so every physical page fits on either side of the binding.
      const width = Math.min(...areas.map((area) => area.getBoundingClientRect().width));
      const height = Math.min(...areas.map((area) => area.getBoundingClientRect().height));
      if (width <= 0 || height <= 0) return;
      measure.style.width = `${width}px`;
      const blocks = summaryBlocks(summary);
      const cache = cacheRef.current;
      const previous = !invalidate && cache?.width === width && cache.height === height ? cache.pagination : undefined;
      const next = paginateNotebook(blocks, (page) => {
        measure.innerHTML = notebookPageHtml(blocks, page);
        // Include block margins (flow-root), leaving a pixel for rounding.
        return measure.getBoundingClientRect().height <= height - 1;
      }, previous, (fragment) => {
        // Find a prefix covering about three actual rendered lines. Short
        // paragraphs are kept whole; no character-count estimate is involved.
        const renderHeight = (end: number) => {
          measure.innerHTML = notebookPageHtml(blocks, [{ ...fragment, end }]);
          const element = measure.querySelector("p, li, h2")!;
          return { height: element.getBoundingClientRect().height, line: parseFloat(getComputedStyle(element).lineHeight) };
        };
        const full = renderHeight(fragment.end);
        const target = Math.min(full.height, full.line * 3);
        const text = blockText(blocks[fragment.block]);
        const boundaries = Array.from(text.slice(fragment.start, fragment.end).matchAll(/\s+/g),
          (match) => fragment.start + match.index! + match[0].length);
        boundaries.push(fragment.end);
        let low = 0;
        let high = boundaries.length - 1;
        while (low < high) {
          const middle = Math.floor((low + high) / 2);
          if (renderHeight(boundaries[middle]).height >= target - 0.5) high = middle;
          else low = middle + 1;
        }
        return boundaries[low];
      });
      cacheRef.current = { width, height, pagination: next };
      setPagination(next);
      setViewIndex((current) => Math.min(current, Math.max(0, Math.ceil(next.pages.length / (desktop ? 2 : 1)) - 1)));
    }
    updateRef.current = update;
    update();
  }, [summary, desktop]);

  useLayoutEffect(() => {
    let frame = 0;
    let disposed = false;
    const schedule = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => { if (!disposed) updateRef.current(true); });
    };
    const observer = new ResizeObserver(schedule);
    if (leftRef.current) observer.observe(leftRef.current);
    if (rightRef.current) observer.observe(rightRef.current);
    document.fonts.addEventListener("loadingdone", schedule);
    void document.fonts.ready.then(() => { if (!disposed) schedule(); });
    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      document.fonts.removeEventListener("loadingdone", schedule);
    };
  }, [desktop]);

  const pages = pagination.pages;
  const pagesPerView = desktop ? 2 : 1;
  const viewCount = Math.max(1, Math.ceil(pages.length / pagesPerView));
  const activeViewIndex = Math.min(viewIndex, viewCount - 1);
  const firstPageIndex = activeViewIndex * pagesPerView;

  function renderEmptyState() {
    if (generationStatus === "generating") {
      return <div className="summary-generation-state" role="status"><span className="summary-generation-spinner" aria-hidden="true" /><strong>{language === "tr" ? "Özet oluşturuluyor..." : "Generating summary..."}</strong><p>{language === "tr" ? "Başka sayfalarda gezinmeye devam edebilirsin." : "You can continue browsing other pages."}</p></div>;
    }

    if (generationStatus === "failed") {
      return <div className="summary-generation-state is-failed" role="alert"><strong>{language === "tr" ? "Özet oluşturulamadı." : "The summary could not be generated."}</strong><Button type="button" onClick={onGenerate}>{language === "tr" ? "Tekrar Dene" : "Try Again"}</Button></div>;
    }

    return <div className="summary-notebook-empty"><p>{language === "tr" ? "Bu PDF için henüz bir özet oluşturulmadı." : "A summary has not been created for this PDF yet."}</p><Button type="button" onClick={onGenerate} disabled={streaming || generationStatus === null}>{language === "tr" ? "Özet Oluştur →" : "Create Summary →"}</Button></div>;
  }

  function renderPage(pageIndex: number, side: "left" | "right") {
    const page = pages[pageIndex];
    return <article className={`summary-notebook-page summary-notebook-page--${side}`}><span className="summary-notebook-margin" aria-hidden="true" /><div ref={side === "left" ? leftRef : rightRef} className="summary-notebook-content">{page ? <div dangerouslySetInnerHTML={{ __html: notebookPageHtml(pagination.blocks, page) }} /> : null}{!summary && side === "left" ? renderEmptyState() : null}</div>{page ? <span className="summary-notebook-page-number">{pageIndex + 1}</span> : null}</article>;
  }

  return <section className="document-summary-view" aria-label={language === "tr" ? "Belge özeti" : "Document summary"}>
    <div className="summary-notebook">{renderPage(firstPageIndex, "left")}<div className="summary-notebook-binding" aria-hidden="true">{Array.from({ length: 12 }, (_, index) => <i key={index} />)}</div>{desktop ? renderPage(firstPageIndex + 1, "right") : null}</div>
    <div ref={measureRef} className="summary-notebook-content summary-notebook-measurer" aria-hidden="true" />
    <div className="summary-notebook-status-slot">
      {generationStatus === "generating" && summary ? <p className="summary-notebook-streaming">{language === "tr" ? "Özet oluşturuluyor..." : "Generating summary..."}{progress?.total_chunks ? ` (${progress.completed_chunks}/${progress.total_chunks})` : null}</p> : null}
      {generationStatus === "failed" && summary ? renderEmptyState() : null}
    </div>
    {pages.length ? <nav className="summary-notebook-pagination" aria-label={language === "tr" ? "Özet sayfaları" : "Summary pages"}><button type="button" disabled={activeViewIndex === 0} onClick={() => setViewIndex((current) => Math.max(0, current - 1))}>← {language === "tr" ? "Önceki Sayfa" : "Previous Page"}</button><span>{activeViewIndex + 1} / {viewCount}</span><button type="button" disabled={activeViewIndex >= viewCount - 1} onClick={() => setViewIndex((current) => Math.min(viewCount - 1, current + 1))}>{language === "tr" ? "Sonraki Sayfa" : "Next Page"} →</button></nav> : null}
  </section>;
}
