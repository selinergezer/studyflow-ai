import type { Metadata } from "next";
import LibraryView from "@/components/library/LibraryView";

export const metadata: Metadata = { title: "Library" };

export default async function LibraryPage({ searchParams }: { searchParams: Promise<{ action?: string; course_id?: string }> }) {
  const { action, course_id: courseIdValue } = await searchParams;
  const selectedAction = action === "quiz" || action === "flashcards" ? action : undefined;
  const courseId = courseIdValue && Number.isInteger(Number(courseIdValue)) ? Number(courseIdValue) : undefined;
  return <LibraryView action={selectedAction} courseId={courseId} />;
}
