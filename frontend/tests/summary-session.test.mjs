import assert from "node:assert/strict";
import { test } from "node:test";
import { createSummarySession, summaryEvents } from "../lib/summary-session.ts";

const encoder = new TextEncoder();
const frame = (event, data) => encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
const tick = () => new Promise((resolve) => setImmediate(resolve));
async function until(predicate) {
  for (let i = 0; i < 100; i++) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 2));
  }
  assert.fail("Condition was not reached");
}

function backend() {
  const document = { document_id: 10, filename: "test.pdf", summary: "", course_id: 1, page_count: 2 };
  const readers = new Set();
  const events = [];
  const server = {
    document, readers, status: "not_started", generations: 0, streams: 0, statusCalls: 0, documentCalls: 0,
    publish(event, data) {
      const bytes = frame(event, data);
      events.push(bytes);
      for (const reader of readers) reader.enqueue(bytes);
    },
    mount(overrides = {}) {
      const controller = new AbortController();
      const updates = [];
      const state = {};
      const update = (key) => (value) => { state[key] = value; updates.push([key, value]); };
      const session = createSummarySession({
        signal: controller.signal,
        reconnectDelay: 1,
        getStatus: async () => {
          server.statusCalls++;
          return { document_id: 10, status: server.status, has_summary: !!document.summary };
        },
        getDocument: async () => { server.documentCalls++; return { ...document }; },
        openStream: async () => {
          server.streams++;
          if (server.status !== "generating") { server.generations++; server.status = "generating"; }
          let reader;
          return new Response(new ReadableStream({
            start(controller) {
              reader = controller;
              readers.add(reader);
              for (const bytes of events) reader.enqueue(bytes);
            },
            cancel() { readers.delete(reader); },
          }));
        },
        onDocument: update("document"), onText: update("text"), onStatus: update("status"),
        onStreaming: update("streaming"), onProgress: update("progress"), onError: update("error"),
        errorMessage: () => "Retry summary", ...overrides,
      });
      return { session, controller, state, updates };
    },
  };
  return server;
}

test("A: start, leave, resume replay, progress, done; only one generation", async () => {
  const server = backend();
  const first = server.mount();
  await first.session.restore(server.document);
  await tick();
  assert.equal(first.state.status, "not_started");
  assert.equal(server.streams, 0);
  first.session.start();
  first.session.start(); // rapid double click
  await until(() => server.readers.size === 1);
  server.publish("token", { text: "İlk " });
  await until(() => first.state.text === "İlk ");
  first.controller.abort();
  const updatesBefore = first.updates.length;
  await until(() => server.readers.size === 0);
  server.publish("token", { text: "ikinci " });

  const resumed = server.mount();
  await resumed.session.restore(server.document);
  await until(() => resumed.state.text === "İlk ikinci ");
  server.publish("progress", { completed_chunks: 9, total_chunks: 65 });
  server.publish("token", { text: "üçüncü" });
  await until(() => resumed.state.text === "İlk ikinci üçüncü");
  assert.deepEqual(resumed.state.progress, { completed_chunks: 9, total_chunks: 65 });
  assert.equal(server.statusCalls, 3); // no polling beside the active stream
  server.document.summary = "Kaydedilmiş final özet";
  server.status = "completed";
  server.publish("done", { status: "completed" }); // deliberately leave the server connection open
  await until(() => resumed.state.status === "completed");
  assert.equal(resumed.state.text, server.document.summary);
  assert.equal(server.documentCalls, 1);
  assert.equal(server.generations, 1);
  assert.equal(server.streams, 2);
  assert.equal(first.updates.length, updatesBefore);
  resumed.controller.abort();
});

test("B: persisted summary is shown directly without status or SSE", async () => {
  const server = backend();
  server.document.summary = "Saved";
  const client = server.mount();
  await client.session.restore(server.document);
  assert.equal(client.state.text, "Saved");
  assert.equal(client.state.status, "completed");
  assert.equal(server.statusCalls, 0);
  assert.equal(server.streams, 0);
  client.controller.abort();
});

test("completed status with stale document refetches the saved summary", async () => {
  const server = backend();
  server.status = "completed";
  const stale = { ...server.document };
  server.document.summary = "Fresh";
  const client = server.mount();
  await client.session.restore(stale);
  await until(() => client.state.text === "Fresh");
  assert.equal(server.documentCalls, 1);
  assert.equal(server.streams, 0);
  client.controller.abort();
});

test("C: failed status exposes retry; only explicit retry starts a job", async () => {
  const server = backend();
  server.status = "failed";
  const client = server.mount();
  await client.session.restore(server.document);
  await until(() => client.state.status === "failed");
  assert.equal(client.state.streaming, false);
  assert.equal(client.state.error, "Retry summary");
  assert.equal(server.streams, 0);
  client.session.start();
  await until(() => server.streams === 1);
  assert.equal(server.generations, 1);
  server.publish("token", { text: "Partial" });
  server.publish("error", { message: "Generation failed" });
  await until(() => client.state.status === "failed");
  assert.equal(client.state.text, "Partial");
  assert.equal(client.state.error, "Generation failed");
  client.controller.abort();
});

test("D: repeated mount/unmount keeps a single reader and ignores disposed callbacks", async () => {
  const server = backend();
  server.status = "generating";
  for (let i = 0; i < 5; i++) {
    const client = server.mount();
    await client.session.restore(server.document);
    await until(() => server.readers.size === 1);
    client.session.start();
    assert.equal(server.readers.size, 1);
    client.controller.abort();
    const count = client.updates.length;
    await until(() => server.readers.size === 0);
    assert.equal(client.updates.length, count);
  }
  assert.equal(server.streams, 5);
  assert.equal(server.generations, 0);
});

test("StrictMode cleanup before status resolves never opens the discarded stream", async () => {
  const server = backend();
  server.status = "generating";
  let resolveStatus;
  const old = server.mount({ getStatus: () => new Promise((resolve) => { resolveStatus = resolve; }) });
  await old.session.restore(server.document);
  old.controller.abort();
  const count = old.updates.length;
  const current = server.mount();
  await current.session.restore(server.document);
  resolveStatus({ status: "generating" });
  await until(() => server.readers.size === 1);
  assert.equal(server.streams, 1);
  assert.equal(old.updates.length, count);
  current.controller.abort();
});

test("EOF reconnect checks status and replays without duplicating text", async () => {
  const server = backend();
  server.status = "generating";
  const client = server.mount();
  await client.session.restore(server.document);
  await until(() => server.readers.size === 1);
  server.publish("token", { text: "One " });
  await until(() => client.state.text === "One ");
  for (const reader of server.readers) reader.close();
  server.readers.clear();
  await until(() => server.streams === 2);
  server.publish("token", { text: "two" });
  await until(() => client.state.text === "One two");
  assert.equal(server.generations, 0);
  client.controller.abort();
});

test("old document's delayed final fetch cannot update the new screen", async () => {
  const server = backend();
  server.status = "completed";
  let resolveDocument;
  const old = server.mount({ getDocument: () => new Promise((resolve) => { resolveDocument = resolve; }) });
  await old.session.restore(server.document);
  await until(() => !!resolveDocument);
  old.controller.abort();
  const count = old.updates.length;
  const current = server.mount();
  await current.session.restore({ ...server.document, document_id: 11, summary: "New document" });
  resolveDocument({ ...server.document, summary: "Old document" });
  await tick();
  assert.equal(old.updates.length, count);
  assert.equal(current.state.text, "New document");
  current.controller.abort();
});

test("repeated status network errors eventually expose retry instead of infinite loading", async () => {
  const server = backend();
  const client = server.mount({ getStatus: async () => { throw new Error("offline"); } });
  await client.session.restore(server.document);
  await until(() => client.state.status === "failed");
  assert.equal(client.state.error, "Retry summary");
  assert.equal(server.streams, 0);
  client.controller.abort();
});

test("parser preserves UTF-8, fragmented CRLF frames and multiple events in one read", async () => {
  const bytes = encoder.encode('event: token\r\ndata: {"text":"Özet birkaç kelime"}\r\n\r\nevent: progress\ndata: {"completed_chunks":3}\n\n');
  const body = new ReadableStream({ start(controller) {
    for (const byte of bytes) controller.enqueue(Uint8Array.of(byte));
    controller.close();
  } });
  const events = [];
  for await (const event of summaryEvents(body, new AbortController().signal)) events.push(event);
  assert.deepEqual(events, [
    { event: "token", data: { text: "Özet birkaç kelime" } },
    { event: "progress", data: { completed_chunks: 3 } },
  ]);
  const together = new ReadableStream({ start(controller) { controller.enqueue(bytes); controller.close(); } });
  const replay = [];
  for await (const event of summaryEvents(together, new AbortController().signal)) replay.push(event);
  assert.deepEqual(replay, events);
});

test("unmount cancels a pending reconnect timer", async () => {
  const server = backend();
  server.status = "generating";
  const client = server.mount({ reconnectDelay: 20 });
  await client.session.restore(server.document);
  await until(() => server.readers.size === 1);
  for (const reader of server.readers) reader.close();
  server.readers.clear();
  await until(() => client.state.streaming === false);
  client.controller.abort();
  const count = client.updates.length;
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(server.streams, 1);
  assert.equal(server.statusCalls, 1);
  assert.equal(client.updates.length, count);
});

test("late stream response after unmount is cancelled without state updates", async () => {
  const server = backend();
  server.status = "generating";
  let resolveStream;
  let cancelled = false;
  const client = server.mount({ openStream: () => new Promise((resolve) => { resolveStream = resolve; }) });
  await client.session.restore(server.document);
  await until(() => !!resolveStream);
  client.controller.abort();
  const count = client.updates.length;
  resolveStream(new Response(new ReadableStream({ cancel() { cancelled = true; } })));
  await until(() => cancelled);
  assert.equal(client.updates.length, count);
});

test("reconnect never starts a replacement when status becomes not_started", async () => {
  const server = backend();
  server.status = "generating";
  const client = server.mount();
  await client.session.restore(server.document);
  await until(() => server.readers.size === 1);
  server.status = "not_started";
  for (const reader of server.readers) reader.close();
  server.readers.clear();
  await until(() => client.state.status === "not_started");
  assert.equal(server.streams, 1);
  assert.equal(server.generations, 0);
  client.controller.abort();
});
