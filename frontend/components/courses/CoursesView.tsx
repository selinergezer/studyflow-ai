"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { apiErrorMessage, apiFetch, isAbortError, type Course, type DocumentData, deleteCourseApi } from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

type CourseFilter = "all" | "with-documents" | "empty";
const icons = [
  <svg key="monitor" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8M12 17v4"/></svg>,
  <svg key="calculator" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><rect x="5" y="2.5" width="14" height="19" rx="2.5"/><path d="M8 6h8v3H8zM8.5 13h.01M12 13h.01M15.5 13h.01M8.5 17h.01M12 17h.01M15.5 17h.01" strokeLinecap="round"/></svg>,
  <svg key="book" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>,
];

function EducationIllustration() {
  return <svg className="courses-illustration" viewBox="0 0 360 180" fill="none" aria-hidden="true">
    <ellipse cx="180" cy="157" rx="145" ry="11" fill="currentColor" opacity=".09"/>
    <g stroke="#66583f" strokeWidth="1.5" strokeLinejoin="round">
      <path className="book-cover book-cover--bottom" d="M49 119 276 113l17 36-230 7c-14 .4-21-7-19-18l5-19Z"/>
      <path className="book-pages" d="m64 124 211-6 8 24-213 7c-12 .3-17-4-15-13l2-7c1-3 3-5 7-5Z"/>
      <path d="m77 130 190-5M74 139l196-6" opacity=".3"/>
      <path className="book-cover book-cover--middle" d="M54 79 286 84l-5 35-232-5c-12-.3-17-7-15-17l3-9c2-6 7-9 17-9Z"/>
      <path className="book-pages" d="m67 85 207 5-3 23-211-5c-11-.3-15-5-13-13l1-4c2-4 7-6 19-6Z"/>
      <path d="m78 92 187 4M74 101l190 5" opacity=".3"/>
      <path className="book-cover book-cover--top" d="m59 39 227 7-4 35-229-7c-12-.4-17-7-15-17l2-9c2-6 8-9 19-9Z"/>
      <path className="book-pages" d="m214 47 61 2-3 26-59-2c-9-.3-12-5-11-13l1-5c1-6 4-8 11-8Z"/>
      <path d="m215 54 52 2M214 63l52 2" opacity=".3"/>
    </g>
    <path className="book-mark" d="M169 87h10l-1 20-5-5-6 4 2-19Z"/>
    <path className="book-mark" d="M228 121h10l1 18-5-4-5 4-1-18Z"/>
  </svg>;
}

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
  const [menuCourseId, setMenuCourseId] = useState<number | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<CourseFilter>("all");
  const [view, setView] = useState<"grid" | "list">("grid");

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([apiFetch<Course[]>("/courses/", { signal: controller.signal }), apiFetch<DocumentData[]>("/documents/", { signal: controller.signal })])
      .then(([courseItems, documentItems]) => { setCourses(courseItems); setDocuments(documentItems); setError(null); })
      .catch((cause) => { if (!isAbortError(cause)) setError(apiErrorMessage(cause, "Kurslar yüklenirken bir hata oluştu.", "Kurslar şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin.")); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);

  const documentCounts = useMemo(() => {
    const counts = new Map<number, number>();
    documents.forEach((document) => { if (document.course_id != null) counts.set(document.course_id, (counts.get(document.course_id) ?? 0) + 1); });
    return counts;
  }, [documents]);
  const visibleCourses = useMemo(() => {
    const locale = language === "tr" ? "tr-TR" : "en-US";
    const needle = query.trim().toLocaleLowerCase(locale);
    return courses.filter((course) => {
      const count = documentCounts.get(course.id) ?? 0;
      const filterMatch = filter === "all" || (filter === "with-documents" ? count > 0 : count === 0);
      return filterMatch && `${course.name} ${course.description ?? ""}`.toLocaleLowerCase(locale).includes(needle);
    });
  }, [courses, documentCounts, filter, language, query]);

  async function createCourse(event: FormEvent) {
    event.preventDefault(); setCreating(true); setError(null);
    try {
      const course = await apiFetch<Course>("/courses/", { method: "POST", body: JSON.stringify({ name, description: description || null }) });
      setCourses((current) => [...current, course]); setName(""); setDescription(""); setShowForm(false);
    } catch (cause) { setError(apiErrorMessage(cause, "Kurs oluşturulamadı.", "Kurslar şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin.")); }
    finally { setCreating(false); }
  }
  async function deleteCourse(event: React.MouseEvent, courseId: number) {
    event.preventDefault(); event.stopPropagation();
    if (!window.confirm("Bu kursu silmek istediğinize emin misiniz?")) return;
    setDeletingId(courseId); setError(null); setMenuCourseId(null);
    try { await deleteCourseApi(courseId); setCourses((current) => current.filter((course) => course.id !== courseId)); }
    catch (cause) { setError(apiErrorMessage(cause, "Kurs silinemedi.", "Kurs silinirken sunucuya ulaşılamadı.")); }
    finally { setDeletingId(null); }
  }

  return <div className="courses-page">
    <section className="courses-hero">
      <div className="courses-hero-copy"><p className="courses-eyebrow">KURSLAR</p><h1>Kursların</h1><p className="courses-subtitle">Belgelerini, pratiklerini ve çalışma hedeflerini kurslara göre düzenle.</p>
        <div className="courses-stats" aria-label="Kurs istatistikleri"><div><span>▣</span><strong>{courses.length}</strong><small>Kurs</small></div><div><span>▤</span><strong>{documents.length}</strong><small>Belge</small></div></div>
      </div>
      <div className="courses-hero-art"><EducationIllustration /></div>
      <button type="button" className="courses-primary-button" onClick={() => { setError(null); setShowForm(true); }}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4"><path d="M12 5v14M5 12h14"/></svg>{t("addCourse")}</button>
    </section>

    {showForm ? <section className="courses-form-paper" aria-label={t("addCourse")}><form onSubmit={createCourse}><label><span>{language === "tr" ? "Kurs adı" : "Course name"}</span><input required value={name} onChange={(event) => setName(event.target.value)} /></label><label><span>{language === "tr" ? "Açıklama" : "Description"}</span><input value={description} onChange={(event) => setDescription(event.target.value)} /></label><div className="courses-form-actions"><button type="button" onClick={() => setShowForm(false)} disabled={creating}>{language === "tr" ? "İptal" : "Cancel"}</button><button type="submit" disabled={creating}>{creating ? (language === "tr" ? "Ekleniyor..." : "Adding...") : t("addCourse")}</button></div></form></section> : null}

    <div className="courses-toolbar">
      <label className="courses-search"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></svg><span className="sr-only">Kurs ara</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Kurs ara..." /></label>
      <select className="courses-filter" value={filter} onChange={(event) => setFilter(event.target.value as CourseFilter)} aria-label="Kursları filtrele"><option value="all">Tümü</option><option value="with-documents">Belgeli kurslar</option><option value="empty">Boş kurslar</option></select>
      <div className="courses-view-toggle" role="group" aria-label="Görünüm seç"><button type="button" className={view === "grid" ? "active" : ""} onClick={() => setView("grid")} aria-label="Izgara görünümü" aria-pressed={view === "grid"}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="4" y="4" width="6" height="6"/><rect x="14" y="4" width="6" height="6"/><rect x="4" y="14" width="6" height="6"/><rect x="14" y="14" width="6" height="6"/></svg></button><button type="button" className={view === "list" ? "active" : ""} onClick={() => setView("list")} aria-label="Liste görünümü" aria-pressed={view === "list"}><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M5 6h14M5 12h14M5 18h14"/></svg></button></div>
    </div>

    {error ? <p className="courses-error" role="alert">{error}</p> : null}
    {loading ? <p className="courses-loading">{t("loading")}</p> : visibleCourses.length === 0 ? <p className="courses-empty">Aramana uygun kurs bulunamadı.</p> : <div className={`courses-grid courses-grid--${view}`}>
      {visibleCourses.map((course, index) => {
        const documentCount = documentCounts.get(course.id) ?? 0;
        return <article id={`course-${course.id}`} key={course.id} className={`courses-card courses-card--accent-${index % 3}`} role="link" tabIndex={0} onClick={() => router.push(`/courses/${course.id}`)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); router.push(`/courses/${course.id}`); } }}>
          <span className="courses-card-flag" aria-hidden="true"/><div className="courses-card-top"><span className="courses-card-icon">{icons[index % icons.length]}</span><div className="courses-card-menu"><button type="button" className="courses-menu-trigger" onClick={(event) => { event.preventDefault(); event.stopPropagation(); setMenuCourseId(menuCourseId === course.id ? null : course.id); }} aria-label={`${course.name} kursu menüsü`} aria-expanded={menuCourseId === course.id}>•••</button>{menuCourseId === course.id ? <div className="courses-menu-popover"><button type="button" disabled={deletingId === course.id} onClick={(event) => deleteCourse(event, course.id)}>{deletingId === course.id ? "Siliniyor..." : "Kursu sil"}</button></div> : null}</div></div>
          <h2>{course.name}</h2><p>{course.description || "\u00a0"}</p><span className="courses-card-rule" aria-hidden="true"/><div className="courses-card-footer"><span className="courses-document-count"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M6 2h8l4 4v16H6z"/><path d="M14 2v5h5M9 12h6M9 16h6"/></svg>{documentCount} {t("documentsCount")}</span><span className="courses-open-arrow" aria-hidden="true">→</span></div>
        </article>;
      })}
    </div>}
  </div>;
}
