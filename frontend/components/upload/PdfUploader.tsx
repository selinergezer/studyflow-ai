"use client";

import {
  ChangeEvent,
  DragEvent,
  FormEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Button from "@/components/ui/Button";
import { useLanguage } from "@/providers/LanguageProvider";
import {
  apiErrorMessage,
  apiFetch,
  isAbortError,
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

export default function PdfUploader({
  initialCourseId,
}: {
  initialCourseId?: number;
}) {
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
  const [showCourseForm, setShowCourseForm] = useState(false);
  const [courseName, setCourseName] = useState("");
  const [courseDescription, setCourseDescription] = useState("");
  const [creatingCourse, setCreatingCourse] = useState(false);
  const [courseError, setCourseError] = useState<string | null>(null);

  const { t } = useLanguage();

  useEffect(() => {
    const controller = new AbortController();
    apiFetch<Course[]>("/courses/", { signal: controller.signal })
      .then((result) => {
        setCourses(result);

        const contextualCourse = result.find(
          (course) => course.id === initialCourseId,
        );
        const defaultCourse = contextualCourse ?? result[0];

        if (defaultCourse) {
          setCourseId(String(defaultCourse.id));
        }
      })
      .catch((cause) => {
        if (isAbortError(cause)) return;
        setError(apiErrorMessage(cause));
      });

    apiFetch<DocumentData[]>("/documents/", { signal: controller.signal })
      .then((result) => {
        setDocuments(result);
        setDocumentsReady(true);
      })
      .catch((cause) => {
        if (isAbortError(cause)) return;

        setError(
          apiErrorMessage(
            cause,
            "Belgeler yüklenirken bir hata oluştu.",
            "Belgeler şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin.",
          ),
        );
      });
    return () => controller.abort();
  }, [initialCourseId]);

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

  function closeCourseForm() {
    if (creatingCourse) return;
    setShowCourseForm(false);
    setCourseError(null);
    setCourseName("");
    setCourseDescription("");
  }

  async function createCourse(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCreatingCourse(true);
    setCourseError(null);

    try {
      const course = await apiFetch<Course>("/courses/", {
        method: "POST",
        body: JSON.stringify({
          name: courseName.trim(),
          description: courseDescription.trim() || null,
        }),
      });

      setCourses((current) => [...current, course]);
      setCourseId(String(course.id));
      setCourseName("");
      setCourseDescription("");
      setShowCourseForm(false);
    } catch (cause) {
      setCourseError(
        apiErrorMessage(
          cause,
          "Kurs oluşturulamadı.",
          "Kurs şu anda oluşturulamıyor. Lütfen daha sonra tekrar deneyin.",
        ),
      );
    } finally {
      setCreatingCourse(false);
    }
  }

  return (
    <div className="upload-page">
      <Link href="/dashboard" className="upload-back-link">← Geri Dön</Link>

      <header className="upload-heading">
        <div>
          <p className="upload-eyebrow">PDF YÜKLE</p>
          <h1>PDF Yükle</h1>
          <p className="upload-intro">
            Ders notlarını veya PDF belgelerini yükle. İçerik analiz edilerek özet hazırlanır.
          </p>
        </div>
      </header>

      <section className="upload-card">
        <div className="upload-course-section">
          <div className="upload-field-heading">
            <label htmlFor="upload-course">Kurs</label>
            <p>Bu belge hangi kursa eklenecek?</p>
          </div>

          <div className="upload-course-picker">
              <select
                id="upload-course"
                value={courseId}
                onChange={(event) => setCourseId(event.target.value)}
                required
              >
                <option value="">Kurs seçin</option>

                {courses.map((course) => (
                  <option key={course.id} value={course.id}>
                    {course.name}
                  </option>
                ))}
              </select>

              <button
                type="button"
                className="upload-new-course-button interactive-button"
                onClick={() => {
                  setCourseError(null);
                  setShowCourseForm(true);
                }}
              >
                <span aria-hidden="true">+</span> Yeni Kurs
              </button>
          </div>
        </div>

        <input ref={inputRef} type="file" accept="application/pdf,.pdf" className="sr-only" onChange={handleInput} aria-label={t("choosePdfFile")} />

        <div
          role="button"
          tabIndex={0}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
          }}
          onDragEnter={(event) => { event.preventDefault(); setDragging(true); }}
          onDragOver={(event) => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
          className={`upload-dropzone${dragging ? " is-dragging" : ""}`}
        >
          <span className="upload-drop-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 15V4" /><path d="M8 8l4-4 4 4" /><path d="M5 14v5h14v-5" />
            </svg>
          </span>
          <h2>{dragging ? "PDF dosyanı bırak" : "PDF dosyanı buraya sürükle veya tıkla"}</h2>
          <p>Sadece PDF dosyaları</p>
          <button type="button" onClick={(event) => { event.stopPropagation(); inputRef.current?.click(); }} className="upload-choose-button interactive-button">
            Dosya Seç
          </button>
        </div>

        {file ? (
          <div className="upload-selected-file">
            <span className="upload-file-icon" aria-hidden="true">PDF</span>
            <div>
              <strong>{file.name}</strong>
              <small>{formatBytes(file.size)} · PDF</small>
            </div>
            <button type="button" onClick={removeFile} disabled={isAnalyzing} aria-label={t("removeFile", { name: file.name })}>×</button>
          </div>
        ) : null}

        {error ? <div className="upload-error" role="alert">{error}</div> : null}

        <footer className="upload-footer">
          <p><span aria-hidden="true">ⓘ</span> PDF yüklendikten sonra içerik otomatik olarak analiz edilir.</p>
          <button type="button" onClick={analyzePdf} disabled={!file || !courseId || isAnalyzing} className="upload-analyze-button interactive-button">
            {isAnalyzing ? "PDF analiz ediliyor..." : "PDF’yi Analiz Et →"}
          </button>
        </footer>
      </section>

      {showCourseForm ? (
        <div
          className="upload-course-modal-overlay"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeCourseForm();
          }}
        >
          <section className="upload-course-modal" role="dialog" aria-modal="true" aria-labelledby="upload-course-modal-title">
            <span className="upload-course-modal-tape" aria-hidden="true" />
            <h2 id="upload-course-modal-title">Yeni Kurs</h2>
            <p>PDF materyalini ekleyeceğin kursu oluştur.</p>
            <form onSubmit={createCourse}>
              <label>
                <span>Kurs adı</span>
                <input required autoFocus value={courseName} onChange={(event) => setCourseName(event.target.value)} disabled={creatingCourse} />
              </label>
              <label>
                <span>Açıklama</span>
                <input value={courseDescription} onChange={(event) => setCourseDescription(event.target.value)} disabled={creatingCourse} />
              </label>
              {courseError ? <div className="upload-course-modal-error" role="alert">{courseError}</div> : null}
              <div className="upload-course-modal-actions">
                <button type="button" onClick={closeCourseForm} disabled={creatingCourse}>İptal</button>
                <button type="submit" disabled={creatingCourse || !courseName.trim()}>{creatingCourse ? "Ekleniyor..." : "Kurs Ekle"}</button>
              </div>
            </form>
          </section>
        </div>
      ) : null}

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
