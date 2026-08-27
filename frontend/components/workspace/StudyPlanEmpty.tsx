"use client";

import { useEffect, useMemo, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { apiErrorMessage, apiFetch, isAbortError, type Course, type DocumentData } from "@/lib/api";
import { formatStudyDuration } from "@/lib/formatStudyDuration";
import { useLanguage } from "@/providers/LanguageProvider";

type StudyPlanItem = { day: string; course: string; duration_minutes: number; topics: string[]; reason: string };
type PlannerResponse = { weekly_plan: StudyPlanItem[]; general_advice: string };
type PlannerEvent = { id: number; title: string; description: string | null; event_type: string; course_id: number | null; start_date: string; completed: boolean };
type UploadResponse = { document_id: number; filename: string; page_count: number; summary: string | null };
const isoDateAfter = (days: number) => { const date = new Date(); date.setDate(date.getDate() + days); return date.toISOString().slice(0, 10); };
const documentId = (document: DocumentData) => document.id ?? document.document_id;

export default function StudyPlanEmpty() {
  const { t, language } = useLanguage();
  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [events, setEvents] = useState<PlannerEvent[]>([]);
  const [selectedDocuments, setSelectedDocuments] = useState<number[]>([]);
  const [documentQuery, setDocumentQuery] = useState("");
  const [availableHours, setAvailableHours] = useState("2");
  const [targetDate, setTargetDate] = useState(() => isoDateAfter(7));
  const [goal, setGoal] = useState("regular");
  const [plan, setPlan] = useState<PlannerResponse | null>(null);
  const [planFilter, setPlanFilter] = useState<"today" | "week" | "all">("today");
  const [completedTasks, setCompletedTasks] = useState<number[]>([]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [examOpen, setExamOpen] = useState(false);
  const [examTitle, setExamTitle] = useState("");
  const [examDate, setExamDate] = useState(() => isoDateAfter(14));
  const [examDocuments, setExamDocuments] = useState<number[]>([]);
  const [examSaving, setExamSaving] = useState(false);
  const [referenceTime] = useState(() => Date.now());
  const [examUploadOpen, setExamUploadOpen] = useState(false);
  const [examUploadFile, setExamUploadFile] = useState<File | null>(null);
  const [examUploadCourseId, setExamUploadCourseId] = useState("");
  const [examUploadError, setExamUploadError] = useState<string | null>(null);
  const [examUploadStatus, setExamUploadStatus] = useState<string | null>(null);
  const [examUploading, setExamUploading] = useState(false);
  const examUploadInputRef = useRef<HTMLInputElement>(null);
  const [examCourseFormOpen, setExamCourseFormOpen] = useState(false);
  const [examCourseName, setExamCourseName] = useState("");
  const [examCourseDescription, setExamCourseDescription] = useState("");
  const [examCourseError, setExamCourseError] = useState<string | null>(null);
  const [examCourseCreating, setExamCourseCreating] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      apiFetch<DocumentData[]>("/documents/", { signal: controller.signal }),
      apiFetch<Course[]>("/courses/", { signal: controller.signal }),
      apiFetch<PlannerEvent[]>("/events/", { signal: controller.signal }),
    ]).then(([documentItems, courseItems, eventItems]) => { setDocuments(documentItems); setCourses(courseItems); setEvents(eventItems); }).catch((cause) => {
      if (!isAbortError(cause)) setError(apiErrorMessage(cause, "Planlama verileri yüklenemedi.", t("operationUnavailable")));
    });
    return () => controller.abort();
  }, [t]);

  const courseNames = useMemo(() => new Map(courses.map((course) => [course.id, course.name])), [courses]);
  const visibleDocuments = documents.filter((document) => document.filename.toLocaleLowerCase(language === "tr" ? "tr-TR" : "en-US").includes(documentQuery.trim().toLocaleLowerCase(language === "tr" ? "tr-TR" : "en-US")));
  const exams = events.filter((event) => event.event_type === "exam" && !event.completed);

  function toggleDocument(id: number, exam = false) {
    const setter = exam ? setExamDocuments : setSelectedDocuments;
    setter((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id]);
  }

  async function createPlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const available_hours_per_day = Number(availableHours);
    if (!selectedDocuments.length) return setError(language === "tr" ? "En az bir belge seç." : "Select at least one document.");
    if (!targetDate) return setError(language === "tr" ? "Bir hedef tarih seç." : "Select a target date.");
    if (!Number.isFinite(available_hours_per_day) || available_hours_per_day <= 0 || available_hours_per_day > 24) return setError(t("plannerHoursError"));
    setCreating(true); setError(null);
    try {
      const result = await apiFetch<PlannerResponse>("/ai/planner/", { method: "POST", body: JSON.stringify({ available_hours_per_day }) });
      setPlan({ ...result, weekly_plan: Array.isArray(result.weekly_plan) ? result.weekly_plan : [] }); setPlanFilter("week"); setCompletedTasks([]);
    } catch (cause) { setError(apiErrorMessage(cause, t("plannerCreateFailed"), t("operationUnavailable"))); } finally { setCreating(false); }
  }

  async function addExam(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!examTitle.trim() || !examDate || !examDocuments.length || examSaving) return;
    const chosen = documents.filter((document) => examDocuments.includes(documentId(document) ?? -1));
    const params = new URLSearchParams({ title: examTitle.trim(), event_type: "exam", start_date: new Date(`${examDate}T09:00:00`).toISOString(), description: chosen.map((document) => document.filename).join(", ") });
    params.set("document_ids", examDocuments.join(","));
    if (chosen[0]?.course_id) params.set("course_id", String(chosen[0].course_id));
    setExamSaving(true);
    try {
      await apiFetch(`/events/?${params.toString()}`, { method: "POST" });
      setEvents(await apiFetch<PlannerEvent[]>("/events/")); setExamOpen(false); setExamTitle(""); setExamDocuments([]);
    } catch (cause) { setError(apiErrorMessage(cause, language === "tr" ? "Sınav eklenemedi." : "The exam could not be added.", t("operationUnavailable"))); } finally { setExamSaving(false); }
  }

  function chooseExamPdf(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    if (file && file.type !== "application/pdf" && !file.name.toLocaleLowerCase().endsWith(".pdf")) {
      setExamUploadFile(null);
      setExamUploadError(t("pdfError"));
      event.target.value = "";
      return;
    }
    setExamUploadFile(file);
    setExamUploadError(null);
    setExamUploadStatus(null);
  }

  function closeExamUpload() {
    if (examUploading || examCourseCreating) return;
    setExamUploadOpen(false);
    setExamUploadFile(null);
    setExamUploadCourseId("");
    setExamUploadError(null);
    setExamCourseFormOpen(false);
    setExamCourseName("");
    setExamCourseDescription("");
    setExamCourseError(null);
    if (examUploadInputRef.current) examUploadInputRef.current.value = "";
  }

  async function createExamCourse() {
    if (!examCourseName.trim()) {
      setExamCourseError(language === "tr" ? "Kurs adı zorunludur." : "Course name is required.");
      return;
    }
    setExamCourseCreating(true);
    setExamCourseError(null);
    try {
      const course = await apiFetch<Course>("/courses/", {
        method: "POST",
        body: JSON.stringify({ name: examCourseName.trim(), description: examCourseDescription.trim() || null }),
      });
      setCourses((current) => [...current, course]);
      setExamUploadCourseId(String(course.id));
      setExamCourseFormOpen(false);
      setExamCourseName("");
      setExamCourseDescription("");
      setExamUploadError(null);
    } catch (cause) {
      setExamCourseError(apiErrorMessage(cause, language === "tr" ? "Kurs oluşturulamadı." : "The course could not be created.", t("operationUnavailable")));
    } finally {
      setExamCourseCreating(false);
    }
  }

  async function uploadExamPdf() {
    if (!examUploadCourseId) {
      setExamUploadError(language === "tr" ? "Lütfen bir kurs seçin." : "Please select a course.");
      return;
    }
    if (!examUploadFile) {
      setExamUploadError(t("pdfError"));
      return;
    }
    setExamUploading(true);
    setExamUploadError(null);
    setExamUploadStatus(null);
    try {
      const formData = new FormData();
      formData.append("file", examUploadFile);
      const uploaded = await apiFetch<UploadResponse>(`/documents/upload?course_id=${examUploadCourseId}`, { method: "POST", body: formData });
      const newDocument: DocumentData = { document_id: uploaded.document_id, filename: uploaded.filename, page_count: uploaded.page_count, summary: uploaded.summary ?? "", course_id: Number(examUploadCourseId) };
      setDocuments((current) => [...current, newDocument]);
      setExamDocuments((current) => current.includes(uploaded.document_id) ? current : [...current, uploaded.document_id]);
      setExamUploadStatus(language === "tr" ? "PDF başarıyla eklendi." : "PDF added successfully.");
      setExamUploadOpen(false);
      setExamUploadFile(null);
      setExamUploadCourseId("");
      if (examUploadInputRef.current) examUploadInputRef.current.value = "";
    } catch (cause) {
      setExamUploadError(apiErrorMessage(cause, language === "tr" ? "PDF yüklenemedi." : "The PDF could not be uploaded.", t("operationUnavailable")));
    } finally {
      setExamUploading(false);
    }
  }

  const displayedTasks = plan?.weekly_plan.filter((_, index) => planFilter === "today" ? index < 3 : planFilter === "week" ? index < 7 : true) ?? [];

  return <div className="study-plan-page">
    <aside className="study-planner-settings">
      <header><h1>{language === "tr" ? "Plan Ayarları" : "Plan Settings"}</h1><span aria-hidden="true">☷</span></header>
      <form onSubmit={createPlan}>
        <section className="study-planner-documents"><h2>{language === "tr" ? "Çalışılacak Belgeler" : "Study Documents"}</h2><label className="study-planner-search"><span aria-hidden="true">⌕</span><input value={documentQuery} onChange={(event) => setDocumentQuery(event.target.value)} placeholder={language === "tr" ? "Belge ara..." : "Search documents..."} /></label><div className="study-planner-document-list">{visibleDocuments.map((document) => { const id = documentId(document); return id == null ? null : <label key={id} className="study-planner-document"><input type="checkbox" checked={selectedDocuments.includes(id)} onChange={() => toggleDocument(id)} /><span className="study-planner-pdf">PDF</span><span><strong>{document.filename}</strong><small>{document.page_count} {t("pages")}</small></span></label>; })}</div></section>
        <label className="study-planner-field"><span>{language === "tr" ? "Günlük Çalışma Süresi" : "Daily Study Time"}</span><select value={availableHours} onChange={(event) => setAvailableHours(event.target.value)}>{[1,2,3,4,5,6].map((hour) => <option key={hour} value={hour}>{hour} {language === "tr" ? "saat" : hour === 1 ? "hour" : "hours"}</option>)}</select></label>
        <label className="study-planner-field"><span>{language === "tr" ? "Hedef Tarih" : "Target Date"}</span><input type="date" min={isoDateAfter(0)} value={targetDate} onChange={(event) => setTargetDate(event.target.value)} /></label>
        <fieldset className="study-planner-goals"><legend>{language === "tr" ? "Çalışma Hedefi" : "Study Goal"}</legend>{[["regular","Düzenli çalışma ve konuları öğrenme"],["exam","Sınava hazırlık"],["review","Hızlı tekrar"]].map(([value,label]) => <label key={value}><input type="radio" name="goal" value={value} checked={goal === value} onChange={(event) => setGoal(event.target.value)} /><span>{language === "tr" ? label : value === "regular" ? "Build a regular study habit" : value === "exam" ? "Prepare for an exam" : "Quick review"}</span></label>)}</fieldset>
        {error ? <p className="study-planner-error" role="alert">{error}</p> : null}<button className="study-planner-create" type="submit" disabled={creating}>{creating ? t("plannerCreating") : `✣  ${language === "tr" ? "Plan Oluştur" : "Create Plan"}`}</button>
      </form>
    </aside>

    <main className="study-planner-main">
      <section className="study-planner-schedule"><header className="study-planner-schedule-head"><h2>{language === "tr" ? "Çalışma Planın" : "Your Study Plan"}</h2><div>{(["today","week","all"] as const).map((filter) => <button key={filter} type="button" className={planFilter === filter ? "active" : ""} onClick={() => setPlanFilter(filter)}>{language === "tr" ? filter === "today" ? "Bugün" : filter === "week" ? "Bu Hafta" : "Tümü" : filter}</button>)}</div></header><div className="study-planner-task-scroll">{!plan ? <div className="study-planner-no-plan"><span>◷</span><strong>{language === "tr" ? "Henüz bir çalışma planı oluşturmadın." : "You haven't created a study plan yet."}</strong><p>{language === "tr" ? "Sol taraftan belgelerini ve çalışma ayarlarını seçerek planını oluştur." : "Select documents and settings on the left to create your plan."}</p></div> : displayedTasks.length ? displayedTasks.map((item,index) => <article className="study-planner-task" key={`${item.day}-${index}`}><time><strong>{item.day}</strong><small>{formatStudyDuration(item.duration_minutes, language, "minutes")}</small></time><span className="study-planner-task-icon">{index % 3 === 2 ? "✣" : "PDF"}</span><div><h3>{item.course}</h3><p>{item.topics?.join(", ") || item.reason}</p></div><label><input type="checkbox" checked={completedTasks.includes(index)} onChange={() => setCompletedTasks((current) => current.includes(index) ? current.filter((item) => item !== index) : [...current,index])} /><span>{completedTasks.includes(index) ? (language === "tr" ? "Tamamlandı" : "Completed") : (language === "tr" ? "Yapılmadı" : "Not done")}</span></label></article>) : <div className="study-planner-no-plan"><strong>{t("plannerNoSuitablePlan")}</strong></div>}</div></section>
      <section className="study-planner-exams"><header><h2>{language === "tr" ? "Sınav Takvimi" : "Exam Calendar"}</h2><button type="button" onClick={() => setExamOpen(true)}>＋ {language === "tr" ? "Yeni Sınav Ekle" : "Add Exam"}</button></header><div className="study-planner-exam-list">{exams.length ? exams.map((exam,index) => { const days = Math.max(0, Math.ceil((new Date(exam.start_date).getTime() - referenceTime) / 86_400_000)); return <article key={exam.id}><span className={`study-planner-calendar accent-${index % 3}`}>▣</span><div><strong>{exam.title}</strong><small>{exam.description || courseNames.get(exam.course_id ?? -1) || t("courses")}</small></div><time>{new Intl.DateTimeFormat(language === "tr" ? "tr-TR" : "en-US", { day:"numeric", month:"long", year:"numeric" }).format(new Date(exam.start_date))}</time><b>{days} {language === "tr" ? "gün kaldı" : "days left"}</b><span>⋮</span></article>; }) : <p className="study-planner-exams-empty">{language === "tr" ? "Henüz yaklaşan sınav yok." : "No upcoming exams yet."}</p>}</div></section>
    </main>

    {examOpen ? (
      <div className="study-planner-modal-overlay" onMouseDown={() => setExamOpen(false)}>
        <form className="study-planner-modal" onSubmit={addExam} onMouseDown={(event) => event.stopPropagation()}>
          <header><h2>{language === "tr" ? "Yeni Sınav Ekle" : "Add Exam"}</h2><button type="button" onClick={() => setExamOpen(false)}>×</button></header>
          <label><span>{language === "tr" ? "Sınav adı" : "Exam name"}</span><input value={examTitle} onChange={(event) => setExamTitle(event.target.value)} required /></label>
          <label><span>{language === "tr" ? "Sınav tarihi" : "Exam date"}</span><input type="date" min={isoDateAfter(0)} value={examDate} onChange={(event) => setExamDate(event.target.value)} required /></label>
          <fieldset className="study-planner-modal-documents">
            <legend>{language === "tr" ? "İlgili PDF’ler" : "Related PDFs"}</legend>
            <div className="study-planner-modal-document-list">
              {documents.map((document) => { const id = documentId(document); return id == null ? null : <label key={id}><input type="checkbox" checked={examDocuments.includes(id)} onChange={() => toggleDocument(id, true)} /><span>{document.filename}</span></label>; })}
            </div>
            <button className="study-planner-inline-upload-trigger" type="button" onClick={() => { setExamUploadOpen((current) => !current); setExamUploadError(null); setExamUploadStatus(null); }}>＋ {language === "tr" ? "PDF Ekle" : "Add PDF"}</button>
            {examUploadStatus ? <p className="study-planner-upload-success" role="status">{examUploadStatus}</p> : null}
            {examUploadOpen ? (
              <div className="study-planner-inline-upload">
                <strong>{language === "tr" ? "Yeni PDF" : "New PDF"}</strong>
                <label><span>{language === "tr" ? "Dosya" : "File"}</span><input ref={examUploadInputRef} type="file" accept="application/pdf" onChange={chooseExamPdf} disabled={examUploading} />{examUploadFile ? <small>{examUploadFile.name}</small> : null}</label>
                <label className="study-planner-inline-course"><span>{language === "tr" ? "Kurs" : "Course"}</span><span className="study-planner-inline-course-row"><select value={examUploadCourseId} onChange={(event) => { setExamUploadCourseId(event.target.value); setExamUploadError(null); }} disabled={examUploading || examCourseCreating}><option value="">{language === "tr" ? "Kurs seç" : "Select course"}</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}</select><button type="button" onClick={() => { setExamCourseFormOpen((current) => !current); setExamCourseError(null); }} disabled={examUploading || examCourseCreating}>＋ {language === "tr" ? "Kurs Ekle" : "Add Course"}</button></span></label>
                {examCourseFormOpen ? <div className="study-planner-inline-course-form"><strong>{language === "tr" ? "Yeni Kurs" : "New Course"}</strong><label><span>{language === "tr" ? "Kurs adı" : "Course name"}</span><input value={examCourseName} onChange={(event) => { setExamCourseName(event.target.value); setExamCourseError(null); }} disabled={examCourseCreating} /></label><label><span>{language === "tr" ? "Açıklama" : "Description"} <small>({language === "tr" ? "opsiyonel" : "optional"})</small></span><input value={examCourseDescription} onChange={(event) => setExamCourseDescription(event.target.value)} disabled={examCourseCreating} /></label>{examCourseError ? <p role="alert">{examCourseError}</p> : null}<div><button type="button" onClick={() => { setExamCourseFormOpen(false); setExamCourseName(""); setExamCourseDescription(""); setExamCourseError(null); }} disabled={examCourseCreating}>{language === "tr" ? "İptal" : "Cancel"}</button><button type="button" onClick={createExamCourse} disabled={examCourseCreating}>{examCourseCreating ? (language === "tr" ? "Oluşturuluyor..." : "Creating...") : (language === "tr" ? "Kursu Oluştur" : "Create Course")}</button></div></div> : null}
                {examUploadError ? <p className="study-planner-upload-error" role="alert">{examUploadError}</p> : null}
                <div className="study-planner-inline-upload-actions"><button type="button" onClick={closeExamUpload} disabled={examUploading}>{language === "tr" ? "İptal" : "Cancel"}</button><button type="button" onClick={uploadExamPdf} disabled={examUploading}>{examUploading ? (language === "tr" ? "PDF yükleniyor..." : "Uploading PDF...") : (language === "tr" ? "PDF’yi Ekle" : "Add PDF")}</button></div>
              </div>
            ) : null}
          </fieldset>
          <button type="submit" disabled={examSaving || !examDocuments.length || examUploading}>{examSaving ? (language === "tr" ? "Ekleniyor..." : "Adding...") : (language === "tr" ? "Sınavı Ekle" : "Add Exam")}</button>
        </form>
      </div>
    ) : null}
  </div>;
}
