"use client";

import { ChangeEvent, DragEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import { useLanguage } from "@/providers/LanguageProvider";
import { apiFetch, type Course } from "@/lib/api";

type UploadResponse = {
  document_id: number;
  filename: string;
  page_count: number;
  summary: string;
};

function formatBytes(bytes: number) {
  if (bytes === 0) return "0 KB";
  const megabytes = bytes / (1024 * 1024);
  return megabytes >= 1 ? `${megabytes.toFixed(1)} MB` : `${Math.ceil(bytes / 1024)} KB`;
}

export default function PdfUploader() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState("");
  const { t } = useLanguage();

  useEffect(() => {
    apiFetch<Course[]>("/courses/").then((result) => { setCourses(result); if (result[0]) setCourseId(String(result[0].id)); }).catch((cause) => { console.error(cause); setError(cause instanceof Error ? cause.message : "İşlem sırasında bir hata oluştu."); });
  }, []);

  function selectFile(candidate?: File) {
    if (!candidate) return;
    if (candidate.type !== "application/pdf" && !candidate.name.toLowerCase().endsWith(".pdf")) {
      setError(t("pdfError"));
      return;
    }
    setFile(candidate);
    setError(null);
  }

  function handleInput(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0]);
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files?.[0]);
  }

  function removeFile() {
    setFile(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function analyzePdf() {
    if (!file || !courseId) return;
    setIsAnalyzing(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      const document = await apiFetch<UploadResponse>(`/documents/upload?course_id=${courseId}`, { method: "POST", body: formData });
      localStorage.setItem("lastDocument", JSON.stringify({ ...document, course_id: Number(courseId) }));
      router.push(`/documents/${document.document_id}`);
    } catch (cause) {
      console.error(cause);
      setError(cause instanceof Error ? cause.message : "PDF analiz edilirken bir hata oluştu.");
      setIsAnalyzing(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-5 py-12 sm:px-8 sm:py-16">
      <div className="animate-enter max-w-2xl">
        <p className="text-sm font-medium text-blue-600">{t("materials")}</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-gray-950 sm:text-4xl">{t("analyzePdf")}</h1>
        <p className="mt-4 text-base leading-7 text-gray-500">{t("uploadIntro")}</p>
      </div>

      <Card className="animate-enter mt-10 p-5 [animation-delay:60ms] sm:p-8">
        <label htmlFor="upload-course" className="mb-2 block text-sm font-medium text-gray-800">{t("courses")}</label>
        <select id="upload-course" value={courseId} onChange={(event) => setCourseId(event.target.value)} className="mb-6 h-11 w-full rounded-xl border border-gray-200 bg-white px-3.5 text-sm text-gray-900 outline-none focus:border-blue-600" required><option value="">Kurs seçin</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}</select>
        <input ref={inputRef} type="file" accept="application/pdf,.pdf" className="sr-only" onChange={handleInput} aria-label={t("choosePdfFile")} />

        {!file ? (
          <div
            onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
            onDragOver={(event) => event.preventDefault()}
            onDragLeave={() => setDragging(false)}
            onDrop={handleDrop}
            className={`flex min-h-72 flex-col items-center justify-center rounded-2xl border border-dashed px-6 text-center transition ${dragging ? "border-blue-500 bg-blue-50/50" : "border-gray-300 bg-gray-50/50"}`}
          >
            <span className="flex size-12 items-center justify-center rounded-2xl bg-white text-gray-600 ring-1 ring-gray-200" aria-hidden="true">
              <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M12 15V4m0 0L8 8m4-4 4 4M5 14v5h14v-5" /></svg>
            </span>
            <h2 className="mt-5 text-sm font-medium text-gray-950">{t("dropPdf")}</h2>
            <p className="mt-2 text-sm text-gray-500">{t("chooseFromComputer")}</p>
            <Button variant="secondary" className="mt-6" onClick={() => inputRef.current?.click()}>{t("choosePdf")}</Button>
            <p className="mt-4 text-xs text-gray-400">{t("pdfOnly")}</p>
          </div>
        ) : (
          <div className="flex min-h-56 flex-col justify-between rounded-2xl bg-gray-50 p-5 sm:p-6">
            <div className="flex items-start gap-4">
              <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-red-50 text-red-600 ring-1 ring-red-100" aria-hidden="true">
                <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M7 3.75h6.5L18 8.25v12H7V3.75Zm6.25.5V8.5h4.25" /></svg>
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-gray-950">{file.name}</p>
                <p className="mt-1 text-xs text-gray-500">{formatBytes(file.size)} · {t("pdfDocument")}</p>
              </div>
              <button type="button" onClick={removeFile} disabled={isAnalyzing} className="flex size-9 shrink-0 items-center justify-center rounded-lg text-gray-400 transition hover:bg-gray-200 hover:text-gray-700 focus-visible:outline-2 focus-visible:outline-blue-600" aria-label={t("removeFile", { name: file.name })}>
                <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"><path d="m6 6 12 12M18 6 6 18" /></svg>
              </button>
            </div>
            <p className="mt-8 text-sm leading-6 text-gray-500">{t("readyToAnalyze")}</p>
          </div>
        )}

        {error ? <p className="mt-3 text-sm text-red-600" role="alert">{error}</p> : null}

        <div className="mt-6 flex justify-end">
          <Button onClick={analyzePdf} disabled={!file || !courseId || isAnalyzing} className="w-full sm:w-auto">
            {isAnalyzing ? "PDF analiz ediliyor..." : t("analyzeButton")}
            <svg className="size-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M5 12h14m-5-5 5 5-5 5" /></svg>
          </Button>
        </div>
      </Card>
    </div>
  );
}
