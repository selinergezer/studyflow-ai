"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import MarkdownSummary from "@/components/documents/MarkdownSummary";
import Button from "@/components/ui/Button";

const DESKTOP_QUERY = "(min-width: 1181px)";
const STREAM_BUFFER_MS = 120;
type NotebookPage = { content: string; committed: boolean };

function findReadableBreak(text: string, target: number) {
  if (text.length <= target) return text.length;
  const minimum = Math.max(1, Math.floor(target * 0.72));
  const maximum = Math.min(text.length, Math.ceil(target * 1.18));
  const window = text.slice(minimum, maximum);
  const paragraphBreak = window.lastIndexOf("\n\n");
  if (paragraphBreak >= 0) return minimum + paragraphBreak;
  const sentenceMatches = Array.from(window.matchAll(/[.!?…](?:["')\]]*)\s+/g));
  const sentenceBreak = sentenceMatches.at(-1);
  if (sentenceBreak?.index != null) return minimum + sentenceBreak.index + sentenceBreak[0].length;
  const wordBreak = window.lastIndexOf(" ");
  return wordBreak >= 0 ? minimum + wordBreak : maximum;
}

function useDesktopSpread() {
  return useSyncExternalStore(
    (callback) => { const media = window.matchMedia(DESKTOP_QUERY); media.addEventListener("change", callback); return () => media.removeEventListener("change", callback); },
    () => window.matchMedia(DESKTOP_QUERY).matches,
    () => true,
  );
}

type SummaryNotebookProps = { summary: string; streaming: boolean; language: "tr" | "en"; onGenerate: () => void };

export default function SummaryNotebook({ summary, streaming, language, onGenerate }: SummaryNotebookProps) {
  const desktop = useDesktopSpread();
  const [pages, setPages] = useState<NotebookPage[]>([]);
  const [viewIndex, setViewIndex] = useState(0);
  const previousSummaryRef = useRef("");
  const streamBufferRef = useRef("");
  const resetPendingRef = useRef(false);
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const measureRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const previous = previousSummaryRef.current;
    const normalized = summary.replace(/\r\n?/g, "\n");
    const reset = !normalized.startsWith(previous);
    if (reset) {
      resetPendingRef.current = true;
      streamBufferRef.current = normalized;
    } else {
      streamBufferRef.current += normalized.slice(previous.length);
    }
    previousSummaryRef.current = normalized;

    function flushBuffer() {
      const incoming = streamBufferRef.current;
      const shouldReset = resetPendingRef.current;
      streamBufferRef.current = "";
      resetPendingRef.current = false;
      if (!incoming) {
        if (shouldReset) setPages([]);
        return;
      }
      setPages((current) => {
        if (shouldReset || !current.length) return [{ content: incoming, committed: false }];
        const active = current.at(-1);
        if (!active) return [{ content: incoming, committed: false }];
        return [...current.slice(0, -1), { content: active.content + incoming, committed: false }];
      });
    }

    if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
    if (streamBufferRef.current.length >= 180 || !streaming) flushBuffer();
    else flushTimerRef.current = setTimeout(flushBuffer, STREAM_BUFFER_MS);
    return () => { if (flushTimerRef.current) clearTimeout(flushTimerRef.current); };
  }, [streaming, summary]);

  const activePage = pages.at(-1);

  useEffect(() => {
    const measure = measureRef.current;
    if (!activePage || activePage.committed || !measure || measure.scrollHeight <= measure.clientHeight + 1) return;
    const ratio = Math.max(0.42, Math.min(0.94, measure.clientHeight / measure.scrollHeight));
    const breakAt = findReadableBreak(activePage.content, Math.max(80, Math.floor(activePage.content.length * ratio * 0.96)));
    const committedContent = activePage.content.slice(0, breakAt).trimEnd();
    const overflowContent = activePage.content.slice(breakAt).trimStart();
    if (!committedContent || !overflowContent) return;
    setPages((current) => {
      const latest = current.at(-1);
      if (!latest || latest.committed || latest.content !== activePage.content) return current;
      return [...current.slice(0, -1), { content: committedContent, committed: true }, { content: overflowContent, committed: false }];
    });
  }, [activePage]);

  useEffect(() => () => { if (flushTimerRef.current) clearTimeout(flushTimerRef.current); }, []);

  const pagesPerView = desktop ? 2 : 1;
  const viewCount = Math.max(1, Math.ceil(pages.length / pagesPerView));
  const activeViewIndex = Math.min(viewIndex, viewCount - 1);
  const firstPageIndex = activeViewIndex * pagesPerView;

  function renderPage(pageIndex: number, side: "left" | "right") {
    const page = pages[pageIndex];
    return <article className={`summary-notebook-page summary-notebook-page--${side}`}><span className="summary-notebook-margin" aria-hidden="true" /><div className="summary-notebook-content">{page?.content ? <MarkdownSummary>{page.content}</MarkdownSummary> : null}{!summary && side === "left" ? <div className="summary-notebook-empty"><p>{language === "tr" ? "Bu PDF için henüz bir özet oluşturulmadı." : "A summary has not been created for this PDF yet."}</p><Button type="button" onClick={onGenerate} disabled={streaming}>{streaming ? (language === "tr" ? "Özet oluşturuluyor..." : "Generating summary...") : (language === "tr" ? "Özet Oluştur →" : "Create Summary →")}</Button></div> : null}</div>{page?.content ? <span className="summary-notebook-page-number">{pageIndex + 1}</span> : null}</article>;
  }

  return <section className="document-summary-view" aria-label={language === "tr" ? "Belge özeti" : "Document summary"}>
    <div className="summary-notebook">{renderPage(firstPageIndex, "left")}<div className="summary-notebook-binding" aria-hidden="true">{Array.from({ length: 12 }, (_, index) => <i key={index} />)}</div>{desktop ? renderPage(firstPageIndex + 1, "right") : null}</div>
    <article className="summary-notebook-page summary-notebook-measurer" aria-hidden="true"><div ref={measureRef} className="summary-notebook-content">{activePage?.content ? <MarkdownSummary>{activePage.content}</MarkdownSummary> : null}</div></article>
    <div className="summary-notebook-status-slot">{streaming && summary ? <p className="summary-notebook-streaming">{language === "tr" ? "Özet oluşturuluyor..." : "Generating summary..."}</p> : null}</div>
    {pages.length ? <nav className="summary-notebook-pagination" aria-label={language === "tr" ? "Özet sayfaları" : "Summary pages"}><button type="button" disabled={activeViewIndex === 0} onClick={() => setViewIndex((current) => Math.max(0, current - 1))}>← {language === "tr" ? "Önceki Sayfa" : "Previous Page"}</button><span>{activeViewIndex + 1} / {viewCount}</span><button type="button" disabled={activeViewIndex >= viewCount - 1} onClick={() => setViewIndex((current) => Math.min(viewCount - 1, current + 1))}>{language === "tr" ? "Sonraki Sayfa" : "Next Page"} →</button></nav> : null}
  </section>;
}
