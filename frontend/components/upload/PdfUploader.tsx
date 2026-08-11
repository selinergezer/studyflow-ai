"use client";

import {
  ChangeEvent,
  DragEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import Button from "@/components/ui/Button";
import { useLanguage } from "@/providers/LanguageProvider";
import {
  apiErrorMessage,
  apiFetch,
  type Course,
  type DocumentData,
} from "@/lib/api";

type UploadResponse = {
  document_id: number;
  filename: string;
  page_count: number;
  summary: string;
};

function formatBytes(bytes: number) {
  if (bytes === 0) return "0 KB";

  const megabytes = bytes / (1024 * 1024);

  return megabytes >= 1
    ? `${megabytes.toFixed(1)} MB`
    : `${Math.ceil(bytes / 1024)} KB`;
}

export default function PdfUploader() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  const [courses, setCourses] = useState<Course[]>([]);
  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [documentsReady, setDocumentsReady] = useState(false);

  const [pendingDuplicate, setPendingDuplicate] =
    useState<File | null>(null);

  const [courseId, setCourseId] = useState("");

  const { t } = useLanguage();

  useEffect(() => {
    apiFetch<Course[]>("/courses/")
      .then((result) => {
        setCourses(result);

        if (result[0]) {
          setCourseId(String(result[0].id));
        }
      })
      .catch((cause) => {
        console.error(cause);
        setError(apiErrorMessage(cause));
      });

    apiFetch<DocumentData[]>("/documents/")
      .then((result) => {
        setDocuments(result);
        setDocumentsReady(true);
      })
      .catch((cause) => {
        console.error(cause);

        setError(
          apiErrorMessage(
            cause,
            "Belgeler yüklenirken bir hata oluştu.",
            "Belgeler şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin.",
          ),
        );
      });
  }, []);

  function normalizedFilename(filename: string) {
    return filename.trim().toLocaleLowerCase("tr-TR");
  }

  function selectFile(candidate?: File) {
    if (!candidate) return;

    if (!documentsReady) {
      setError(
        "Belgeler şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin.",
      );

      if (inputRef.current) {
        inputRef.current.value = "";
      }

      return;
    }

    if (
      candidate.type !== "application/pdf" &&
      !candidate.name.toLowerCase().endsWith(".pdf")
    ) {
      setError(t("pdfError"));
      return;
    }

    const duplicate = documents.some(
      (document) =>
        normalizedFilename(document.filename) ===
        normalizedFilename(candidate.name),
    );

    if (duplicate) {
      setPendingDuplicate(candidate);
      setError(null);
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

    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  function cancelDuplicate() {
    setPendingDuplicate(null);

    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  function acceptDuplicate() {
    if (pendingDuplicate) {
      setFile(pendingDuplicate);
    }

    setPendingDuplicate(null);
    setError(null);
  }

  async function analyzePdf() {
    if (!file || !courseId) return;

    setIsAnalyzing(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const document = await apiFetch<UploadResponse>(
        `/documents/upload?course_id=${courseId}`,
        {
          method: "POST",
          body: formData,
        },
      );

      localStorage.setItem(
        "lastDocument",
        JSON.stringify({
          ...document,
          course_id: Number(courseId),
        }),
      );

      router.push(`/documents/${document.document_id}`);
    } catch (cause) {
      console.error(cause);

      setError(
        apiErrorMessage(
          cause,
          "PDF analiz edilirken bir hata oluştu.",
          "PDF şu anda analiz edilemiyor. Lütfen tekrar deneyin.",
        ),
      );

      setIsAnalyzing(false);
    }
  }

  return (
    <div className="relative mx-auto max-w-5xl px-5 py-14 sm:px-8 sm:py-16">
      {/* Glow */}
      <div
        className="pointer-events-none absolute -left-52 -top-40 h-[560px] w-[560px]"
        style={{
          background:
            "radial-gradient(circle, rgba(232,163,61,.16) 0%, rgba(232,163,61,.055) 40%, transparent 70%)",
        }}
      />

      {/* Başlık */}
      <div className="relative mb-10">
        <div className="mb-4 flex items-center gap-3 font-mono text-xs tracking-[0.14em] text-[#7fe0c4]">
          <span className="h-px w-6 bg-[#7fe0c4]" />
          MATERYALLER
        </div>

        <h1 className="font-[Bricolage_Grotesque] text-4xl font-semibold tracking-[-0.035em] text-[var(--heading)] sm:text-5xl">
          PDF Analiz Et
        </h1>

        <p className="mt-4 max-w-2xl text-[15px] leading-7 text-[var(--text)]">
          Özetler, sınavlar ve bilgi kartları oluşturmak için bir ders
          belgesi yükle.
        </p>
      </div>

      {/* Defter */}
      <section
        className="upload-notebook relative overflow-hidden rounded-md bg-[#ece5d3] text-[#241f13] shadow-[0_35px_70px_-38px_rgba(0,0,0,.9)]"
        style={{
          backgroundImage: `
            linear-gradient(
              to right,
              transparent 62px,
              rgba(190,75,70,.28) 62px,
              rgba(190,75,70,.28) 63px,
              transparent 63px
            ),
            repeating-linear-gradient(
              to bottom,
              transparent 0px,
              transparent 31px,
              rgba(80,110,145,.11) 32px
            )
          `,
        }}
      >
        {/* Bant */}
        <div className="absolute -top-1 right-16 h-7 w-24 rotate-2 bg-[#7fe0c4]/70 shadow-sm" />

        <div className="px-7 pb-8 pt-10 sm:px-12 sm:pb-10 sm:pl-[92px]">
          {/* Küçük başlık */}
          <div className="mb-8 max-w-2xl">
            <p className="font-mono text-[11px] font-bold tracking-[0.12em] text-[#7a6e4e]">
              MATERYAL HAZIRLA
            </p>

            <p className="mt-3 text-sm leading-6 text-[#6f654c]">
              PDF dosyanı hangi kurs için kullanacağını seç ve
              materyalini çalışma alanına ekle.
            </p>
          </div>

          {/* Kurs */}
          <div className="mb-8 max-w-2xl">
            <label
              htmlFor="upload-course"
              className="mb-2 block font-mono text-[10px] uppercase tracking-[0.1em] text-[#8a7d55]"
            >
              Kurs
            </label>

            <select
              id="upload-course"
              value={courseId}
              onChange={(event) => setCourseId(event.target.value)}
              className="h-12 w-full rounded-lg border border-[#241f13]/15 bg-[#fffdf8]/60 px-4 text-sm text-[#241f13] outline-none transition focus:border-[#e8a33d] focus:ring-4 focus:ring-[#e8a33d]/10"
              required
            >
              <option value="">Kurs seçin</option>

              {courses.map((course) => (
                <option key={course.id} value={course.id}>
                  {course.name}
                </option>
              ))}
            </select>
          </div>

          <input
            ref={inputRef}
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            onChange={handleInput}
            aria-label={t("choosePdfFile")}
          />

          {/* PDF seçilmediyse */}
          {!file ? (
            <div
              onDragEnter={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragOver={(event) => {
                event.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={handleDrop}
              className={`flex min-h-[275px] flex-col items-center justify-center rounded-lg border border-dashed px-6 text-center transition-all ${
                dragging
                  ? "scale-[1.005] border-[#e8a33d] bg-[#e8a33d]/10 shadow-[0_0_30px_rgba(232,163,61,.13)]"
                  : "border-[#241f13]/25 bg-[#fffdf8]/25 hover:border-[#c07f28] hover:bg-[#fffdf8]/40"
              }`}
            >
              <div className="flex size-12 items-center justify-center rounded-full bg-[#e8a33d]/15 text-[#b87521]">
                <svg
                  className="size-5"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 15V4" />
                  <path d="M8 8l4-4 4 4" />
                  <path d="M5 14v5h14v-5" />
                </svg>
              </div>

              <h2 className="mt-5 font-[Bricolage_Grotesque] text-lg font-semibold">
                {dragging
                  ? "PDF dosyanı bırak"
                  : "PDF dosyanı buraya bırak"}
              </h2>

              <p className="mt-2 text-sm text-[#8a7d55]">
                veya bilgisayarından bir dosya seç
              </p>

              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="mt-6 rounded-lg border border-[#241f13]/20 bg-[#fffdf8]/55 px-5 py-2.5 text-sm font-semibold text-[#241f13] transition hover:border-[#e8a33d] hover:bg-[#e8a33d]"
              >
                PDF Seç
              </button>

              <p className="mt-4 font-mono text-[9px] uppercase tracking-[0.08em] text-[#9a8f68]">
                Yalnızca PDF dosyaları
              </p>
            </div>
          ) : (
            /* PDF seçildiyse */
            <div className="flex min-h-[220px] items-center justify-center rounded-lg border border-dashed border-[#241f13]/20 bg-[#fffdf8]/25 p-6">
              <div className="flex w-full max-w-2xl items-center gap-4 rounded-lg border border-[#241f13]/15 bg-[#fffdf8]/55 p-5 shadow-sm">
                <div className="flex size-14 shrink-0 items-center justify-center rounded-lg bg-[#e0786e]/15 font-mono text-xs font-bold text-[#bd564d]">
                  PDF
                </div>

                <div className="min-w-0 flex-1">
                  <p className="truncate font-[Bricolage_Grotesque] text-base font-semibold">
                    {file.name}
                  </p>

                  <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.06em] text-[#8a7d55]">
                    {formatBytes(file.size)} · PDF
                  </p>

                  <p className="mt-2 text-xs font-medium text-[#438c75]">
                    Analiz için hazır
                  </p>
                </div>

                <button
                  type="button"
                  onClick={removeFile}
                  disabled={isAnalyzing}
                  className="flex size-9 shrink-0 items-center justify-center rounded-md text-[#8a7d55] transition hover:bg-[#241f13]/10 hover:text-[#bd564d]"
                  aria-label={t("removeFile", {
                    name: file.name,
                  })}
                >
                  <svg
                    className="size-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinecap="round"
                  >
                    <path d="m6 6 12 12M18 6 6 18" />
                  </svg>
                </button>
              </div>
            </div>
          )}

          {/* Hata */}
          {error ? (
            <div
              className="mt-5 rounded-md border border-[#bd564d]/25 bg-[#bd564d]/10 px-4 py-3 text-sm text-[#9f4139]"
              role="alert"
            >
              {error}
            </div>
          ) : null}

          {/* Footer */}
          <div className="mt-7 flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="font-[Kalam] text-[15px] text-[#857951]">
              <span className="text-[#c07f28]">not:</span>{" "}
              PDF yüklendikten sonra özet otomatik hazırlanır.
            </p>

            <button
              type="button"
              onClick={analyzePdf}
              disabled={!file || !courseId || isAnalyzing}
              className="inline-flex min-w-[190px] items-center justify-center gap-2 rounded-lg bg-[#e8a33d] px-5 py-3 text-sm font-bold text-[#241705] shadow-[0_14px_28px_-14px_rgba(232,163,61,.75)] transition hover:-translate-y-0.5 hover:shadow-[0_18px_30px_-14px_rgba(232,163,61,.9)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0"
            >
              {isAnalyzing
                ? "PDF analiz ediliyor..."
                : "PDF’yi Analiz Et →"}
            </button>
          </div>
        </div>
      </section>

      {/* Duplicate modal */}
      {pendingDuplicate ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-[#080b12]/70 p-5 backdrop-blur-sm"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              cancelDuplicate();
            }
          }}
        >
          <div
            className="upload-duplicate-paper relative w-full max-w-md overflow-hidden rounded-md bg-[#ece5d3] p-7 text-[#241f13] shadow-2xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="duplicate-file-title"
            style={{
              backgroundImage: `
                repeating-linear-gradient(
                  to bottom,
                  transparent 0px,
                  transparent 31px,
                  rgba(80,110,145,.09) 32px
                )
              `,
            }}
          >
            <div className="absolute -top-1 right-9 h-6 w-20 rotate-2 bg-[#f0d878]/70" />

            <div className="flex size-10 items-center justify-center rounded-lg bg-[#e8a33d]/20 font-mono font-bold text-[#b87521]">
              !
            </div>

            <h2
              id="duplicate-file-title"
              className="mt-5 font-[Bricolage_Grotesque] text-xl font-semibold"
            >
              Bu dosya daha önce yüklenmiş.
            </h2>

            <p className="mt-3 text-sm leading-6 text-[#6f654c]">
              Aynı isimde bir PDF kütüphanende bulunuyor. Tekrar
              eklemek istiyor musun?
            </p>

            <div className="mt-7 flex justify-end gap-3">
              <Button
                variant="secondary"
                onClick={cancelDuplicate}
              >
                İptal
              </Button>

              <button
                type="button"
                onClick={acceptDuplicate}
                className="rounded-lg bg-[#e8a33d] px-4 py-2.5 text-sm font-semibold text-[#241705]"
              >
                Tekrar Ekle
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
