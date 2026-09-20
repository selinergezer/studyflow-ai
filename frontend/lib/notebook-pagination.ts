export type SummaryBlock = {
  kind: "heading" | "paragraph" | "item";
  spans: { text: string; bold: boolean }[];
};
export type PageFragment = { block: number; start: number; end: number };
export type NotebookPagination = { blocks: SummaryBlock[]; pages: PageFragment[][] };

// Match the notebook's existing MarkdownSummary vocabulary, including bold text.
export function summaryBlocks(summary: string): SummaryBlock[] {
  return summary.replace(/\r\n?/g, "\n").split("\n").flatMap((line) => {
    const text = line.trim();
    if (!text) return [];
    const heading = /^(#{1,3})\s+(.+)$/.exec(text);
    const item = /^[-*+]\s+/.test(text);
    const content = heading ? heading[2] : item ? text.replace(/^[-*+]\s+/, "") : text;
    return [{
      kind: heading ? "heading" as const : item ? "item" as const : "paragraph" as const,
      spans: content.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part) => {
        const bold = part.startsWith("**") && part.endsWith("**");
        return { text: bold ? part.slice(2, -2) : part, bold };
      }),
    }];
  });
}

export function blockText(block: SummaryBlock) {
  return block.spans.map((span) => span.text).join("");
}

function escapeHtml(text: string) {
  return text.replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[char]!);
}

function fragmentHtml(block: SummaryBlock, start: number, end: number) {
  let offset = 0;
  return block.spans.map((span) => {
    const from = Math.max(0, start - offset);
    const to = Math.min(span.text.length, end - offset);
    offset += span.text.length;
    if (to <= from) return "";
    const text = escapeHtml(span.text.slice(from, to));
    return span.bold ? `<strong>${text}</strong>` : text;
  }).join("");
}

// All content is escaped; measured and displayed pages use exactly the same markup.
export function notebookPageHtml(blocks: SummaryBlock[], page: PageFragment[]) {
  let html = "";
  let list = false;
  for (const fragment of page) {
    const block = blocks[fragment.block];
    if (list && block.kind !== "item") { html += "</ul>"; list = false; }
    const content = fragmentHtml(block, fragment.start, fragment.end);
    if (block.kind === "item") {
      if (!list) { html += "<ul>"; list = true; }
      html += `<li><span aria-hidden="true"></span><span>${content}</span></li>`;
    } else {
      const tag = block.kind === "heading" ? "h2" : "p";
      html += `<${tag}>${content}</${tag}>`;
    }
  }
  return `<div class="markdown-summary">${html}${list ? "</ul>" : ""}</div>`;
}

export function paginateNotebook(
  blocks: SummaryBlock[],
  fits: (page: PageFragment[]) => boolean,
  previous?: NotebookPagination,
  minimumStart?: (fragment: PageFragment) => number,
): NotebookPagination {
  const pages: PageFragment[][] = [];
  // Retain unchanged full pages. Rebuild the tail; a closing ** may also change
  // the style of an earlier fragment, in which case rebuild from that page.
  for (const page of previous?.pages.slice(0, -1) ?? []) {
    // A heading received at the end of a streaming update needs its new
    // following content considered before this boundary can be kept.
    if (blocks[page.at(-1)!.block]?.kind === "heading") break;
    if (!page.every((fragment) => {
      const before = previous!.blocks[fragment.block];
      const after = blocks[fragment.block];
      return after && before.kind === after.kind &&
        !(fragment.end === blockText(before).length && blockText(after).length !== fragment.end) &&
        blockText(after).length >= fragment.end &&
        fragmentHtml(before, fragment.start, fragment.end) === fragmentHtml(after, fragment.start, fragment.end);
    })) break;
    pages.push(page);
  }
  const last = pages.at(-1)?.at(-1);
  let blockIndex = last?.block ?? 0;
  let start = last?.end ?? 0;
  let page: PageFragment[] = [];

  for (; blockIndex < blocks.length; blockIndex++, start = 0) {
    const text = blockText(blocks[blockIndex]);
    while (start < text.length) {
      const whole = { block: blockIndex, start, end: text.length };
      if (blocks[blockIndex].kind === "heading" && start === 0 && page.length) {
        const group = [whole];
        let next = blockIndex + 1;
        while (blocks[next]?.kind === "heading") {
          group.push({ block: next, start: 0, end: blockText(blocks[next]).length });
          next++;
        }
        if (blocks[next]) {
          const following = { block: next, start: 0, end: blockText(blocks[next]).length };
          group.push({ ...following, end: minimumStart?.(following) ?? following.end });
          // Move only if the group can actually fit on a fresh page. Oversized
          // headings still use safe splitting rather than an endless retry.
          if (!fits([...page, ...group]) && fits(group)) {
            pages.push(page); page = []; continue;
          }
        }
      }
      if (fits([...page, whole])) { page.push(whole); break; }
      if (page.length && (blocks[blockIndex].kind === "heading" ||
        !fits([...page, { ...whole, end: minimumStart?.(whole) ?? start + 1 }]))) {
        pages.push(page); page = []; continue;
      }

      // Fill remaining space too, not just empty pages. Find the largest
      // measured word prefix, retaining every character in the continuation.
      const words = Array.from(text.slice(start).matchAll(/\s+/g), (match) => start + match.index! + match[0].length);
      if (words.at(-1) !== text.length) words.push(text.length);
      function largestFit(boundaries: number[]) {
        let low = 0;
        let high = boundaries.length - 1;
        let end = start;
        while (low <= high) {
          const middle = Math.floor((low + high) / 2);
          if (fits([...page, { block: blockIndex, start, end: boundaries[middle] }])) {
            end = boundaries[middle]; low = middle + 1;
          } else high = middle - 1;
        }
        return end;
      }
      let end = largestFit(words);
      if (end === start) {
        let offset = start;
        const characters = Array.from(text.slice(start, words[0]), (char) => (offset += char.length));
        end = largestFit(characters);
      }
      if (end === start) throw new Error("Notebook content area cannot fit a single character");
      pages.push([...page, { block: blockIndex, start, end }]);
      page = [];
      start = end;
    }
  }
  if (page.length) pages.push(page);
  return { blocks, pages };
}
