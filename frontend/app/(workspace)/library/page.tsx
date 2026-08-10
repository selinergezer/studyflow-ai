import type { Metadata } from "next";
import LibraryView from "@/components/library/LibraryView";

export const metadata: Metadata = { title: "Library" };

export default async function LibraryPage({ searchParams }: { searchParams: Promise<{ action?: string }> }) {
  const { action } = await searchParams;
  const selectedAction = action === "quiz" || action === "flashcards" ? action : undefined;
  return <LibraryView action={selectedAction} />;
}
