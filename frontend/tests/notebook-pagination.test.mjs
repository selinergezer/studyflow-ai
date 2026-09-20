import assert from "node:assert/strict";
import { test } from "node:test";
import { blockText, notebookPageHtml, paginateNotebook, summaryBlocks } from "../lib/notebook-pagination.ts";

// Unit tests inject a layout oracle. Actual CSS/DOM sizes are covered by the
// companion browser test; the production paginator never estimates characters.
function layout(blocks, capacity) {
  return (page) => page.reduce((height, fragment) => height +
    (fragment.end - fragment.start) * (blocks[fragment.block].kind === "heading" ? 2 : 1) + 8, 0) <= capacity;
}
function assertComplete(result) {
  const rebuilt = result.blocks.map(() => "");
  for (const page of result.pages) for (const fragment of page) {
    assert.equal(fragment.start, rebuilt[fragment.block].length);
    rebuilt[fragment.block] += blockText(result.blocks[fragment.block]).slice(fragment.start, fragment.end);
  }
  assert.deepEqual(rebuilt, result.blocks.map(blockText));
}

test("short summary uses one physical page", () => {
  const blocks = summaryBlocks("# Özet\nKısa paragraf.");
  const result = paginateNotebook(blocks, layout(blocks, 200));
  assert.equal(result.pages.length, 1);
  assertComplete(result);
});

test("headings, long paragraphs and list items split without losing the final sentence", () => {
  const blocks = summaryBlocks(`# Başlık\n${"Türkçe uzun bir paragraf. ".repeat(90)}SON CÜMLE.\n- ${"Uzun liste öğesi ".repeat(40)}\n- Son öğe.`);
  const fits = layout(blocks, 230);
  const result = paginateNotebook(blocks, fits);
  assert.ok(result.pages.length > 2);
  assert.ok(result.pages.every(fits));
  assertComplete(result);
});

test("streaming grows pages and retains the measured prefix", () => {
  const blocks = summaryBlocks("Kelime ".repeat(200));
  const first = paginateNotebook(blocks, layout(blocks, 200));
  const grown = summaryBlocks("Kelime ".repeat(400) + "SON.");
  const next = paginateNotebook(grown, layout(grown, 200), first);
  assert.ok(next.pages.length > first.pages.length);
  assert.equal(next.pages[0], first.pages[0]);
  assertComplete(next);
});

test("resize uses a fresh layout and preserves all content", () => {
  const blocks = summaryBlocks("Uzun paragraf. ".repeat(200));
  const wide = paginateNotebook(blocks, layout(blocks, 400));
  const narrow = paginateNotebook(blocks, layout(blocks, 170));
  assert.ok(narrow.pages.length > wide.pages.length);
  assert.ok(narrow.pages.every(layout(blocks, 170)));
  assertComplete(narrow);
});

test("closing streaming bold markup invalidates affected pages", () => {
  const content = "**" + "Türkçe kelime ".repeat(70);
  const initial = summaryBlocks(content);
  const first = paginateNotebook(initial, layout(initial, 180));
  const final = summaryBlocks(content + "**\nSon paragraf.");
  const result = paginateNotebook(final, layout(final, 180), first);
  assert.notEqual(result.pages[0], first.pages[0]);
  assertComplete(result);
  assert.match(notebookPageHtml(final, result.pages[0]), /<strong>/);
});

test("unbroken Unicode text splits safely and HTML is escaped", () => {
  const blocks = summaryBlocks("😀".repeat(100) + '<script>alert("x")</script>');
  const result = paginateNotebook(blocks, layout(blocks, 70));
  assertComplete(result);
  for (const page of result.pages) {
    const html = notebookPageHtml(blocks, page);
    assert.ok(!html.includes("<script>"));
    for (const fragment of page) {
      assert.ok(!/[\uD800-\uDBFF]$/.test(blockText(blocks[fragment.block]).slice(fragment.start, fragment.end)));
    }
  }
});

test("replacement and empty summaries discard cached pages", () => {
  const blocks = summaryBlocks("Eski özet ".repeat(100));
  const old = paginateNotebook(blocks, layout(blocks, 100));
  const replacement = summaryBlocks("Yeni özetin son cümlesi.");
  const next = paginateNotebook(replacement, layout(replacement, 100), old);
  assert.equal(next.pages.length, 1);
  assertComplete(next);
  assert.deepEqual(paginateNotebook([], () => true, next).pages, []);
});

test("a longer earlier paragraph in the final summary invalidates its old boundary", () => {
  const original = summaryBlocks("İlk paragraf.\n" + "Sonraki paragraf.\n".repeat(30));
  const previous = paginateNotebook(original, layout(original, 120));
  const final = summaryBlocks("İlk paragraf. Yeni eklenen cümle.\n" + "Sonraki paragraf.\n".repeat(30));
  const result = paginateNotebook(final, layout(final, 120), previous);
  assertComplete(result);
});

test("heading moves together with a measured opening when only the heading fits", () => {
  const blocks = summaryBlocks("Önceki metin ".repeat(6) + "\n## Başlık\n" + "Yeni içerik ".repeat(30));
  const fits = layout(blocks, 140);
  const result = paginateNotebook(blocks, fits, undefined, (fragment) => Math.min(fragment.end, fragment.start + 45));
  assert.ok(!result.pages[0].some((fragment) => fragment.block === 1));
  assert.equal(result.pages[1][0].block, 1);
  assert.ok(result.pages[1].some((fragment) => fragment.block === 2 && fragment.end >= 45));
  assertComplete(result);
});

test("heading stays and the long following paragraph fills remaining space", () => {
  const blocks = summaryBlocks("Kısa giriş.\n## Başlık\n" + "Yeni içerik ".repeat(30));
  const fits = layout(blocks, 140);
  const result = paginateNotebook(blocks, fits, undefined, (fragment) => Math.min(fragment.end, fragment.start + 45));
  assert.deepEqual(result.pages[0].map((fragment) => fragment.block), [0, 1, 2]);
  assert.ok(result.pages[0][2].end >= 80);
  assert.ok(result.pages.every(fits));
  assertComplete(result);
});

test("streamed heading gains its following content without losing cached text", () => {
  const source = "Önceki metin ".repeat(50) + "\n## Başlık";
  const first = summaryBlocks(source);
  const old = paginateNotebook(first, layout(first, 140));
  const blocks = summaryBlocks(source + "\n" + "Yeni içerik ".repeat(30));
  const next = paginateNotebook(blocks, layout(blocks, 140), old, (fragment) => Math.min(fragment.end, fragment.start + 45));
  assertComplete(next);
  const headingPage = next.pages.find((page) => page.some((fragment) => fragment.block === 1));
  assert.ok(headingPage.some((fragment) => fragment.block === 2));
});
