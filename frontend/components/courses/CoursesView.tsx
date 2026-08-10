"use client";

import { FormEvent, useEffect, useState } from "react";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Input from "@/components/ui/Input";
import { apiFetch, type Course } from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

export default function CoursesView() {
  const { t, language } = useLanguage();
  const [courses, setCourses] = useState<Course[]>([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<Course[]>("/courses/").then(setCourses).catch((cause) => { console.error(cause); setError(cause instanceof Error ? cause.message : "İşlem sırasında bir hata oluştu."); }).finally(() => setLoading(false));
  }, []);

  async function createCourse(event: FormEvent) {
    event.preventDefault(); setError(null);
    try {
      const course = await apiFetch<Course>("/courses/", { method: "POST", body: JSON.stringify({ name, description: description || null }) });
      setCourses((current) => [...current, course]); setName(""); setDescription(""); setShowForm(false);
    } catch (cause) { console.error(cause); setError(cause instanceof Error ? cause.message : "İşlem sırasında bir hata oluştu."); }
  }

  return <div className="mx-auto max-w-5xl px-5 py-12 sm:px-8 sm:py-16">
    <div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-end"><div><p className="text-sm font-medium text-blue-600">{t("courses")}</p><h1 className="mt-3 text-3xl font-semibold tracking-[-0.04em] text-gray-950 sm:text-4xl">{t("coursesTitle")}</h1><p className="mt-4 text-base text-gray-500">{t("coursesIntro")}</p></div><Button onClick={() => setShowForm((value) => !value)}>{t("addCourse")}</Button></div>
    {showForm ? <Card className="mt-8 p-6"><form onSubmit={createCourse} className="grid gap-4 sm:grid-cols-2"><Input id="course-name" label={language === "tr" ? "Kurs adı" : "Course name"} required value={name} onChange={(event) => setName(event.target.value)} /><Input id="course-description" label={language === "tr" ? "Açıklama" : "Description"} value={description} onChange={(event) => setDescription(event.target.value)} /><div className="sm:col-span-2"><Button type="submit">{t("addCourse")}</Button></div></form></Card> : null}
    {error ? <p className="mt-5 text-sm text-red-600" role="alert">{error}</p> : null}
    {loading ? <p className="mt-10 text-sm text-gray-500">Yükleniyor...</p> : <div className="mt-10 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{courses.map((course) => <Card id={`course-${course.id}`} key={course.id} className="scroll-mt-24 p-5 shadow-none"><h2 className="text-sm font-medium text-gray-950">{course.name}</h2>{course.description ? <p className="mt-2 text-sm leading-6 text-gray-500">{course.description}</p> : null}</Card>)}</div>}
  </div>;
}
