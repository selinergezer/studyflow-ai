import type { DocumentData, DocumentSummaryStatus, SummaryGenerationStatus } from "./api";

export type SummaryProgress = { completed_chunks: number; total_chunks?: number };

type SummarySessionOptions = {
  signal: AbortSignal;
  getStatus: () => Promise<DocumentSummaryStatus>;
  getDocument: () => Promise<DocumentData>;
  openStream: () => Promise<Response>;
  onDocument: (document: DocumentData) => void;
  onText: (text: string) => void;
  onStatus: (status: SummaryGenerationStatus) => void;
  onStreaming: (streaming: boolean) => void;
  onProgress: (progress: SummaryProgress) => void;
  onError: (message: string | null) => void;
  errorMessage: () => string;
  reconnectDelay?: number;
};

// Decode complete SSE frames immediately, retaining only an incomplete frame.
export async function* summaryEvents(body: ReadableStream<Uint8Array>, signal: AbortSignal) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const cancel = () => { void reader.cancel().catch(() => {}); };
  signal.addEventListener("abort", cancel, { once: true });
  try {
    while (!signal.aborted) {
      const { value, done } = await reader.read();
      if (signal.aborted) return;
      buffer += decoder.decode(value, { stream: !done });
      let boundary: RegExpExecArray | null;
      while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
        const frame = buffer.slice(0, boundary.index);
        buffer = buffer.slice(boundary.index + boundary[0].length);
        let event = "message";
        const data: string[] = [];
        for (const line of frame.split(/\r?\n/)) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
        }
        if (data.length) {
          yield { event, data: JSON.parse(data.join("\n")) as Record<string, unknown> };
        }
      }
      if (done) return;
    }
  } finally {
    signal.removeEventListener("abort", cancel);
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}

export function createSummarySession(options: SummarySessionOptions) {
  const { signal } = options;
  let busy = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let failures = 0;

  signal.addEventListener("abort", () => clearTimeout(timer), { once: true });

  function fail(message = options.errorMessage()) {
    options.onStatus("failed");
    options.onError(message);
  }

  async function refreshDocument() {
    const document = await options.getDocument();
    if (signal.aborted) return;
    if (!document.summary?.trim()) throw new Error(options.errorMessage());
    options.onDocument(document);
    options.onText(document.summary);
    options.onStatus("completed");
    options.onError(null);
  }

  function scheduleReconnect() {
    if (signal.aborted) return;
    clearTimeout(timer);
    // Poll only after disconnection; never alongside an active SSE reader.
    timer = setTimeout(() => { void checkStatus(false); }, options.reconnectDelay ?? 4_000);
  }

  async function consumeStream() {
    options.onStatus("generating");
    options.onStreaming(true);
    options.onError(null);
    try {
      const response = await options.openStream();
      if (signal.aborted) {
        await response.body?.cancel();
        return;
      }
      if (!response.ok || !response.body) throw new Error(options.errorMessage());
      // The endpoint replays the existing job from cursor zero on every attach.
      let text = "";
      options.onText(text);
      for await (const { event, data } of summaryEvents(response.body, signal)) {
        if (signal.aborted) return;
        if (event === "error") {
          fail(typeof data.message === "string" ? data.message : undefined);
          return;
        }
        if (event === "done") {
          await refreshDocument();
          return;
        }
        if (event === "status" || event === "progress") {
          options.onProgress({
            completed_chunks: typeof data.completed_chunks === "number" ? data.completed_chunks : 0,
            total_chunks: typeof data.total_chunks === "number" ? data.total_chunks : undefined,
          });
        }
        if (event === "token" && typeof data.text === "string") {
          text += data.text;
          options.onText(text);
          failures = 0;
        }
      }
      // EOF without done is a dropped connection, not successful generation.
      if (!signal.aborted) scheduleReconnect();
    } finally {
      if (!signal.aborted) options.onStreaming(false);
    }
  }

  async function checkStatus(allowStart: boolean) {
    if (signal.aborted || busy) return;
    busy = true;
    clearTimeout(timer);
    try {
      const status = await options.getStatus();
      if (signal.aborted) return;
      options.onStatus(status.status);
      if (status.status === "completed") {
        await refreshDocument();
      } else if (status.status === "generating" || allowStart) {
        // Only a user action may start a not_started/failed job. Resume merely
        // attaches to the running job through the same backend GET endpoint.
        await consumeStream();
      } else if (status.status === "failed") {
        fail();
      }
    } catch {
      if (signal.aborted) return;
      failures += 1;
      if (failures >= 3) fail();
      else scheduleReconnect();
    } finally {
      busy = false;
    }
  }

  return {
    async restore(document: DocumentData) {
      if (signal.aborted) return;
      options.onText(document.summary ?? "");
      options.onStreaming(false);
      options.onProgress({ completed_chunks: 0 });
      options.onError(null);
      if (document.summary?.trim()) {
        options.onStatus("completed");
        return;
      }
      // Do not block the workspace's initial load on the lifetime of the stream.
      void checkStatus(false);
    },
    start() {
      if (signal.aborted || busy) return;
      failures = 0;
      void checkStatus(true);
    },
  };
}
