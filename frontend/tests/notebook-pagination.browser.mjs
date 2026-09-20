// Run with NOTEBOOK_TEST_TOOLS pointing to a directory containing installed
// playwright and esbuild packages. Chromium must be installed for Playwright.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { blockText, summaryBlocks } from "../lib/notebook-pagination.ts";

const frontend = fileURLToPath(new URL("../", import.meta.url));
const requireTool = createRequire(path.join(process.env.NOTEBOOK_TEST_TOOLS ?? frontend, "package.json"));
const { chromium } = requireTool("playwright");
const { build } = requireTool("esbuild");
const bundle = await build({
  stdin: {
    contents: `import React from 'react'; import {createRoot} from 'react-dom/client';
      import SummaryNotebook from './components/documents/SummaryNotebook';
      const root = createRoot(document.getElementById('root'));
      window.showSummary = (summary, streaming = false) => root.render(
        <React.StrictMode><SummaryNotebook summary={summary} streaming={streaming}
          generationStatus={streaming ? 'generating' : 'completed'} language="tr" onGenerate={() => {}} /></React.StrictMode>);`,
    resolveDir: frontend, loader: "tsx",
  },
  tsconfig: path.join(frontend, "tsconfig.json"), bundle: true, write: false,
  define: { "process.env.NODE_ENV": '"development"' },
});
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const css = await readFile(path.join(frontend, "app/globals.css"), "utf8");
  await page.setContent(`<style>${css}</style><style>*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif}#root{width:1100px;margin:auto}</style><div class="workspace-page workspace-page--document"><div id="root"></div></div>`);
  await page.addScriptTag({ content: bundle.outputFiles[0].text });
  const settle = () => page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => requestAnimationFrame(resolve)))));
  async function show(text, streaming = false) {
    await page.evaluate(({ text, streaming }) => window.showSummary(text, streaming), { text, streaming });
    await settle();
  }
  const indicator = () => page.locator(".summary-notebook-pagination > span").innerText();
  async function verifyAll(text) {
    const previous = page.getByRole("button", { name: /Önceki Sayfa/ });
    while (await previous.isEnabled()) { await previous.click(); await settle(); }
    let allText = "";
    let physicalPages = 0;
    while (true) {
      const result = await page.evaluate(() => {
        const violations = [];
        let text = "";
        const numbers = [];
        for (const article of document.querySelectorAll(".summary-notebook > .summary-notebook-page")) {
          const area = article.querySelector(".summary-notebook-content").getBoundingClientRect();
          const content = article.querySelector(".markdown-summary");
          if (!content) continue;
          text += content.textContent;
          const footer = article.querySelector(".summary-notebook-page-number");
          numbers.push(Number(footer.textContent));
          if (content.getBoundingClientRect().bottom > area.bottom + 0.5) violations.push("content exceeds usable height");
          if (content.getBoundingClientRect().bottom > footer.getBoundingClientRect().top) violations.push("footer overlap");
          for (const node of content.querySelectorAll("h2,p,li,li > span:last-child,strong")) {
            const box = node.getBoundingClientRect();
            if (box.left < area.left - 0.5 || box.right > area.right + 0.5) violations.push("horizontal overflow");
          }
          const binding = document.querySelector(".summary-notebook-binding");
          if (getComputedStyle(binding).display !== "none") {
            const spine = binding.getBoundingClientRect();
            if (area.left < spine.right && area.right > spine.left) violations.push("binding overlap");
          }
        }
        return { text, numbers, violations };
      });
      assert.deepEqual(result.violations, []);
      for (const number of result.numbers) assert.equal(number, ++physicalPages);
      allText += result.text;
      const next = page.getByRole("button", { name: /Sonraki Sayfa/ });
      if (!(await next.isEnabled())) break;
      await next.click(); await settle();
    }
    const compact = (value) => value.replace(/\s/g, "");
    assert.equal(compact(allText), compact(summaryBlocks(text).map(blockText).join("")), "every character including the last sentence survives");
    return physicalPages;
  }

  await show("# Kısa özet\nBir kısa paragraf.");
  assert.equal(await indicator(), "1 / 1");
  assert.equal(await verifyAll("# Kısa özet\nBir kısa paragraf."), 1);
  console.log("PASS short summary: one spread");

  const long = Array.from({ length: 18 }, (_, i) => `## Başlık ${i + 1}\n${"Türkçe açıklamalar farklı uzunluklarda satırlara sarılır. ".repeat(i % 3 + 3)}\n- **Önemli madde** ve açıklaması.\n- İkinci madde.`).join("\n\n") + "\nSON CÜMLE KAYBOLMAMALI.";
  await show(long);
  const widePages = await verifyAll(long);
  assert.ok(widePages > 2);
  console.log(`PASS long summary: ${widePages} physical pages, no clipping/footer/binding overlap`);

  const oversized = "# " + "Uzun başlık ".repeat(100) + "\n" + "**Uzun paragraf içeriği** Türkçe sözcükler. ".repeat(300) + "\n- " + "Liste öğesi ".repeat(200) + "\n" + "😀".repeat(200) + "\nSON.";
  await show(oversized);
  await verifyAll(oversized);
  console.log("PASS oversized heading, paragraph, list item, unbroken Unicode and final sentence");

  await show(long.slice(0, 1500), true);
  while (await page.getByRole("button", { name: /Önceki Sayfa/ }).isEnabled()) await page.getByRole("button", { name: /Önceki Sayfa/ }).click();
  const before = await indicator();
  const firstPage = await page.locator(".summary-notebook-page--left .markdown-summary").innerHTML();
  await show(long, true);
  assert.ok((await indicator()).startsWith("1 /"));
  assert.notEqual(await indicator(), before);
  assert.equal(await page.locator(".summary-notebook-page--left .markdown-summary").innerHTML(), firstPage);
  await verifyAll(long);
  await show(long, false);
  await verifyAll(long);
  console.log("PASS streaming growth preserves earlier spread and final summary pagination");

  // Derive edge cases from real typography rather than fixed text lengths.
  const fixtures = await page.evaluate(() => {
    const areas = Array.from(document.querySelectorAll(".summary-notebook > article .summary-notebook-content"));
    const width = Math.min(...areas.map((area) => area.getBoundingClientRect().width));
    const height = Math.min(...areas.map((area) => area.getBoundingClientRect().height));
    const probe = document.createElement("div");
    probe.className = "summary-notebook-content summary-notebook-measurer";
    probe.style.width = `${width}px`;
    document.querySelector(".document-summary-view").append(probe);
    const heading = "19.YÜZYIL ISLAHAT HAREKETLERİ";
    const paragraph = "Yeni açıklamalar ve önemli tarihsel bilgiler. ".repeat(90);
    let opening = "";
    for (const word of paragraph.split(" ")) {
      opening += word + " ";
      probe.innerHTML = `<div class="markdown-summary"><p>${opening}</p></div>`;
      const p = probe.querySelector("p");
      if (p.getBoundingClientRect().height >= parseFloat(getComputedStyle(p).lineHeight) * 3 - 0.5) break;
    }
    const measure = (filler, body) => {
      probe.innerHTML = `<div class="markdown-summary"><p>${filler}</p><h2>${heading}</h2>${body ? `<p>${body}</p>` : ""}</div>`;
      return probe.getBoundingClientRect().height;
    };
    let orphan;
    let keep;
    for (let n = 1; n < 200; n++) {
      const filler = "Önceki açıklama. ".repeat(n);
      const headingOnly = measure(filler, "");
      const together = measure(filler, opening);
      if (headingOnly <= height - 1 && together > height - 1) orphan ??= filler;
      if (together <= height - 1 && together > height * 0.7) keep = filler;
    }
    probe.remove();
    return { orphan, keep, heading, paragraph };
  });
  assert.ok(fixtures.orphan && fixtures.keep);
  const orphanText = `${fixtures.orphan}\n## ${fixtures.heading}\n${fixtures.paragraph}`;
  await show(orphanText);
  while (await page.getByRole("button", { name: /Önceki Sayfa/ }).isEnabled()) await page.getByRole("button", { name: /Önceki Sayfa/ }).click();
  assert.equal(await page.locator(".summary-notebook-page--left h2").count(), 0);
  assert.equal(await page.locator(".summary-notebook-page--right h2").innerText(), fixtures.heading);
  await verifyAll(orphanText);
  const keepText = `${fixtures.keep}\n## ${fixtures.heading}\n${fixtures.paragraph}`;
  await show(keepText);
  while (await page.getByRole("button", { name: /Önceki Sayfa/ }).isEnabled()) await page.getByRole("button", { name: /Önceki Sayfa/ }).click();
  assert.equal(await page.locator(".summary-notebook-page--left h2").innerText(), fixtures.heading);
  const openingSize = await page.locator(".summary-notebook-page--left h2 + p").evaluate((element) => ({
    lines: element.getBoundingClientRect().height / parseFloat(getComputedStyle(element).lineHeight),
    gap: element.closest(".summary-notebook-content").getBoundingClientRect().bottom - element.getBoundingClientRect().bottom,
  }));
  assert.ok(openingSize.lines >= 2.9);
  assert.ok(openingSize.gap < 50, `unused bottom space: ${openingSize.gap}`);
  await verifyAll(keepText);
  await show(`${fixtures.orphan}\n## ${fixtures.heading}`, true);
  await show(orphanText, true);
  await verifyAll(orphanText);
  console.log("PASS measured heading keep-together, three-line opening, usable space and streaming heading arrival");
  await show(long);

  // Container resize, without crossing a viewport breakpoint.
  await page.locator("#root").evaluate((element) => { element.style.width = "850px"; });
  await settle();
  const narrowPages = await verifyAll(long);
  assert.ok(narrowPages > widePages);
  console.log(`PASS ResizeObserver container resize: ${widePages} -> ${narrowPages} pages`);

  for (const width of [1000, 390]) {
    await page.setViewportSize({ width, height: 850 });
    await page.locator("#root").evaluate((element) => { element.style.width = "calc(100% - 32px)"; });
    await settle();
    await verifyAll(long);
    console.log(`PASS responsive ${width}px: every page measured, complete text retained`);
  }
  assert.deepEqual(errors, []);
} finally {
  await browser.close();
}
