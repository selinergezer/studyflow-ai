import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = { title: "Library" };

export default async function LibraryPage({ searchParams }: { searchParams: Promise<{ action?: string; course_id?: string }> }) {
  const { action } = await searchParams;

  if (action === "quiz") redirect("/quiz#quiz-documents");
  if (action === "flashcards") redirect("/flashcards#flashcard-documents");

  redirect("/courses");
}
