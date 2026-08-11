"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  apiErrorMessage,
  apiFetch,
  type Course,
  type DocumentData,
} from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

type LibraryAction = "quiz" | "flashcards";

export default function LibraryView({
  action,
  courseId,
}: {
  action?: LibraryAction;
  courseId?: number;
}) {
  const router = useRouter();
  const { t, language } = useLanguage();

  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      apiFetch<DocumentData[]>("/documents/"),
      apiFetch<Course[]>("/courses/"),
    ])
      .then(([documentItems, courseItems]) => {
        setDocuments(documentItems);
        setCourses(courseItems);
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
      })
      .finally(() => setLoading(false));
  }, []);

  const courseNames = useMemo(
    () => new Map(courses.map((course) => [course.id, course.name])),
    [courses],
  );

  const locale = language === "tr" ? "tr-TR" : "en-US";

  const normalizedQuery = query.trim().toLocaleLowerCase(locale);

  const filtered = useMemo(
    () =>
      documents.filter((item) => {
        if (courseId != null && item.course_id !== courseId) {
          return false;
        }

        const filename = item.filename.toLocaleLowerCase(locale);

        const courseName = (
          courseNames.get(item.course_id) ?? ""
        ).toLocaleLowerCase(locale);

        return (
          filename.includes(normalizedQuery) ||
          courseName.includes(normalizedQuery)
        );
      }),
    [courseId, courseNames, documents, locale, normalizedQuery],
  );

  function documentId(item: DocumentData) {
    return item.id ?? item.document_id;
  }

  function openDocument(id: number) {
    if (action === "quiz") {
      router.push(`/documents/${id}?tab=quiz`);
    } else if (action === "flashcards") {
      router.push(`/documents/${id}?tab=flashcards`);
    } else {
      router.push(`/documents/${id}`);
    }
  }

  async function deleteDocument(
    event: React.MouseEvent,
    item: DocumentData,
  ) {
    event.preventDefault();
    event.stopPropagation();

    const id = documentId(item);

    if (
      id == null ||
      !window.confirm("Bu belgeyi silmek istediğinize emin misiniz?")
    ) {
      return;
    }

    setDeletingId(id);
    setError(null);

    try {
      await apiFetch(`/documents/${id}`, {
        method: "DELETE",
      });

      setDocuments((current) =>
        current.filter(
          (document) => documentId(document) !== id,
        ),
      );
    } catch (cause) {
      console.error(cause);

      setError(
        apiErrorMessage(
          cause,
          "Belge silinirken bir hata oluştu.",
          "Belge şu anda silinemiyor. Lütfen daha sonra tekrar deneyin.",
        ),
      );
    } finally {
      setDeletingId(null);
    }
  }

  const intro = action
    ? action === "quiz"
      ? t("selectQuizMaterial")
      : t("selectFlashcardMaterial")
    : t("libraryIntro");

  return (
    <div className="library-page">
      <header className="library-heading">
        <div
          className="library-glow"
          aria-hidden="true"
        />

        <div>
          <p className="library-eyebrow">
            {t("library")}
          </p>

          <h1>{t("yourMaterials")}</h1>

          <p className="library-subtitle">
            {intro}
          </p>
        </div>

        <Link
          href="/upload"
          className="library-add-button"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>

          {t("addMaterial")}
        </Link>
      </header>

      <label className="library-search">
        <span className="sr-only">
          {t("searchMaterials")}
        </span>

        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          aria-hidden="true"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m21 21-4.3-4.3" />
        </svg>

        <input
          type="search"
          value={query}
          onChange={(event) =>
            setQuery(event.target.value)
          }
          placeholder={t("searchPlaceholder")}
        />
      </label>

      {error ? (
        <p
          className="library-error"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      {loading ? (
        <p className="library-loading">
          {t("loading")}
        </p>
      ) : filtered.length ? (
        <div className="library-document-grid">
          {filtered.map((item) => {
            const id = documentId(item);

            if (id == null) {
              return null;
            }

            const courseName =
              courseNames.get(item.course_id);

            return (
              <article
                key={id}
                className="library-document-card"
                role="link"
                tabIndex={0}
                onClick={() =>
                  openDocument(id)
                }
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" ||
                    event.key === " "
                  ) {
                    event.preventDefault();
                    openDocument(id);
                  }
                }}
              >
                <span
                  className="library-document-flag"
                  aria-hidden="true"
                />

                <div className="library-document-top">
                  <span className="library-pdf-icon">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <path d="M14 2v6h6" />
                    </svg>
                  </span>

                  <button
                    type="button"
                    className="library-delete"
                    disabled={
                      deletingId === id
                    }
                    onClick={(event) =>
                      deleteDocument(
                        event,
                        item,
                      )
                    }
                    aria-label={`${item.filename} belgesini sil`}
                  >
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6" />
                    </svg>
                  </button>
                </div>

                <div className="library-document-info">
                  <strong>
                    {item.filename}
                  </strong>

                  {courseName ? (
                    <span className="library-course-name">
                      {courseName}
                    </span>
                  ) : null}

                  <span className="library-document-meta">
                    {item.page_count}{" "}
                    {t("pages")}
                  </span>
                </div>

                <div className="library-document-rule" />

                <div className="library-document-footer">
                  <span className="library-open-link">
                    {language === "tr"
                      ? "Aç →"
                      : "Open →"}
                  </span>

                  <span className="library-document-type">
                    PDF
                  </span>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="library-empty">
          <p>
            {query
              ? t("noMaterials")
              : t("noDocumentsYet")}
          </p>

          {!query ? (
            <span>
              {language === "tr"
                ? "İlk materyalini eklemek için Materyal ekle butonunu kullan."
                : "Use the Add material button to upload your first material."}
            </span>
          ) : null}
        </div>
      )}
    </div>
  );
}