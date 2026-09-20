// NOTEBOOK_TEST_TOOLS can point to temporary playwright/esbuild installations.
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
const frontend = fileURLToPath(new URL("../", import.meta.url));
const tools = createRequire(path.join(process.env.NOTEBOOK_TEST_TOOLS ?? frontend, "package.json"));
const { build } = tools("esbuild");
const { chromium } = tools("playwright");
const bundle = await build({
  stdin: { contents: `import React from 'react'; import {createRoot} from 'react-dom/client';
    import QuizPanel from './components/documents/QuizPanel';
    import {LanguageProvider} from './providers/LanguageProvider';
    import {apiFetch, deleteQuizApi} from './lib/api';
    window.listQuizzes = () => apiFetch('/quizzes/', {cache:'no-store'});
    window.deleteQuiz = () => deleteQuizApi(42);
    createRoot(document.getElementById('root')).render(<LanguageProvider><QuizPanel documentId="10"
      onQuizCreated={() => {if(window.failCallback) throw new Error('Test programming defect');}} /></LanguageProvider>);`, resolveDir: frontend, loader: "tsx" },
  tsconfig: path.join(frontend, "tsconfig.json"), bundle: true, write: false,
  define: { "process.env.NEXT_PUBLIC_API_TIMING": '"false"', "process.env.NODE_ENV": '"development"', "process.env.NEXT_PUBLIC_API_URL": '"http://configured-api.test"' },
});
const browser = await chromium.launch({ headless: true });
try {
  for (const mode of ["valid", "expired", "missing", "programming-error"]) {
    const page = await browser.newPage();
    const consoleErrors = [];
    const pageErrors = [];
    const requests = [];
    page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await page.route("**/*", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.hostname === "quiz-ui.test") return route.fulfill({ contentType: "text/html", body: '<div id="root"></div>' });
      const headers = await request.allHeaders();
      requests.push({ host: url.host, path: url.pathname, method: request.method(), authenticated: headers.authorization === "Bearer synthetic-test-session", count: url.searchParams.get("question_count") });
      const cors = { "access-control-allow-origin": "*", "access-control-allow-headers": "authorization,content-type", "access-control-allow-methods": "GET,DELETE,OPTIONS" };
      if (request.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
      if (mode === "expired") return route.fulfill({ status: 401, headers: cors, contentType: "application/json", body: JSON.stringify({ detail: "Geçersiz kimlik bilgileri" }) });
      if (url.pathname.endsWith("/generate/stream")) return route.fulfill({ headers: cors, contentType: "text/event-stream", body: 'event: done\ndata: {"quiz_id":42}\n\n' });
      if (request.method() === "DELETE") return route.fulfill({ status: 204, headers: cors });
      const quiz = { id:42, document_id:10, question_count:5, questions:Array.from({length:5}, (_, i) => ({id:i+1,question_text:`Test sorusu ${i+1}`,question_type:"multiple_choice",option_a:"A",option_b:"B"})) };
      return route.fulfill({ headers: cors, contentType: "application/json", body: JSON.stringify(url.pathname === "/quizzes/" ? [quiz] : quiz) });
    });
    await page.goto("http://quiz-ui.test");
    await page.evaluate((mode) => {
      if (mode !== "missing") localStorage.setItem("access_token", "synthetic-test-session");
      localStorage.setItem("accessToken", "obsolete-key-must-not-be-used");
      window.failCallback = mode === "programming-error";
    }, mode);
    await page.addScriptTag({ content: bundle.outputFiles[0].text });
    if (mode === "valid") {
      assert.equal(await page.evaluate(async () => (await window.listQuizzes()).length), 1);
      await page.evaluate(() => window.deleteQuiz());
    }
    await page.getByRole("button", { name: "5", exact: true }).click();
    await page.getByRole("button", { name: /Sınavı Oluştur/ }).click();
    if (mode === "valid") {
      await page.getByRole("heading", { name: "Test sorusu 1" }).waitFor();
      const actual = requests.filter((request) => request.method !== "OPTIONS");
      assert.ok(actual.every((request) => request.host === "configured-api.test" && request.authenticated));
      assert.equal(actual.find((request) => request.path.endsWith("/generate/stream")).count, "5");
      assert.ok(actual.some((request) => request.path === "/quizzes/"));
      assert.ok(actual.some((request) => request.method === "DELETE"));
    } else if (mode === "programming-error") {
      await page.getByRole("alert").filter({ hasText: "Test programming defect" }).waitFor();
      assert.ok(consoleErrors.some((message) => message.includes("Unexpected quiz streaming error")));
    } else {
      await page.getByRole("alert").filter({ hasText: "Lütfen yeniden giriş yapın" }).waitFor();
      assert.ok(!consoleErrors.some((message) => message.includes("Quiz streaming") || message.includes("Unexpected quiz")));
      if (mode === "missing") assert.equal(requests.length, 0);
    }
    assert.deepEqual(pageErrors, []);
    console.log(`PASS quiz auth: ${mode} (token values omitted)`);
    await page.close();
  }
} finally { await browser.close(); }
