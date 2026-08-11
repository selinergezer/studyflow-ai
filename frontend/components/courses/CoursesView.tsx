"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiErrorMessage, apiFetch, type Course, type DocumentData } from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

export default function CoursesView() {
  const { t, language } = useLanguage();
  const router = useRouter();
  const [courses, setCourses] = useState<Course[]>([]);
  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([apiFetch<Course[]>("/courses/"), apiFetch<DocumentData[]>("/documents/")])
      .then(([courseItems, documentItems]) => { setCourses(courseItems); setDocuments(documentItems); })
      .catch((cause) => {
        console.error(cause);
        setError(apiErrorMessage(cause, "Kurslar yüklenirken bir hata oluştu.", "Kurslar şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin."));
      })
      .finally(() => setLoading(false));
  }, []);

  function openCourseForm() {
    setError(null);
    setShowForm(true);
  }

  async function createCourse(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    setError(null);
    try {
      const course = await apiFetch<Course>("/courses/", { method: "POST", body: JSON.stringify({ name, description: description || null }) });
      setCourses((current) => [...current, course]);
      setName("");
      setDescription("");
      setShowForm(false);
    } catch (cause) {
      console.error(cause);
      setError(apiErrorMessage(cause, "Kurs oluşturulamadı.", "Kurslar şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin."));
    } finally {
      setCreating(false);
    }
  }

  function deleteCourse(event: React.MouseEvent, courseId: number) {
    event.preventDefault();
    event.stopPropagation();
    if (!window.confirm("Bu kursu silmek istediğinize emin misiniz?")) return;
    setDeletingId(courseId);
    setError("Kurs silme işlemi backend tarafından henüz desteklenmiyor.");
    setDeletingId(null);
  }

  return <div className="courses-page">
    <header className="courses-heading">
      <div className="courses-glow" aria-hidden="true" />
      <div>
        <p className="courses-eyebrow">{t("courses")}</p>
        <h1>{t("coursesTitle")}</h1>
        <p className="courses-subtitle">{t("coursesIntro")}</p>
      </div>
      <button type="button" className="courses-primary-button" onClick={openCourseForm}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M12 5v14M5 12h14"/></svg>{t("addCourse")}</button>
    </header>

    {showForm ? <section className="courses-form-paper" aria-label={t("addCourse")}><form onSubmit={createCourse}><label><span>{language === "tr" ? "Kurs adı" : "Course name"}</span><input required value={name} onChange={(event) => setName(event.target.value)} /></label><label><span>{language === "tr" ? "Açıklama" : "Description"}</span><input value={description} onChange={(event) => setDescription(event.target.value)} /></label><div className="courses-form-actions"><button type="button" onClick={() => setShowForm(false)} disabled={creating}>{language === "tr" ? "İptal" : "Cancel"}</button><button type="submit" disabled={creating}>{creating ? (language === "tr" ? "Ekleniyor..." : "Adding...") : t("addCourse")}</button></div></form></section> : null}

    {error ? <p className="courses-error" role="alert">{error}</p> : null}
    {loading ? <p className="courses-loading">{t("loading")}</p> : <div className="courses-grid">
      {courses.map((course) => {
        const documentCount = documents.filter((document) => document.course_id === course.id).length;
        return <article id={`course-${course.id}`} key={course.id} className="courses-card" role="link" tabIndex={0} onClick={() => router.push(`/library?course_id=${course.id}`)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") router.push(`/library?course_id=${course.id}`); }}>
          <span className="courses-card-flag" aria-hidden="true" />
          <div className="courses-card-top"><span className="courses-card-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg></span><button type="button" className="courses-delete" disabled={deletingId === course.id} onClick={(event) => deleteCourse(event, course.id)} aria-label={`${course.name} kursunu sil`}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6"/></svg></button></div>
          <h2>{course.name}</h2>
          <p>{course.description || "\u00a0"}</p>
          <span className="courses-card-rule" aria-hidden="true" />
          <span className="courses-document-count">{documentCount} {t("documentsCount")}</span>
        </article>;
      })}
    </div>}
  </div>;
}
