import type { Metadata } from "next";
import DocumentWorkspace from "@/components/documents/DocumentWorkspace";

type DocumentPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{
    tab?: string;
    flashcard_id?: string;
  }>;
};

export async function generateMetadata({ params }: DocumentPageProps): Promise<Metadata> {
  await params;
  return { title: "Belge detayı" };
}

export default async function DocumentPage({ params, searchParams }: DocumentPageProps) {
  const { id } = await params;
  const { tab, flashcard_id } = await searchParams;

const initialTab =
  tab === "quiz" || tab === "flashcards"
    ? tab
    : "summary";

const initialFlashcardId = flashcard_id
  ? Number(flashcard_id)
  : undefined;

return (
  <DocumentWorkspace
    key={`${id}-${initialTab}-${initialFlashcardId ?? ""}`}
    documentId={id}
    initialTab={initialTab}
    initialFlashcardId={initialFlashcardId}
  />
);
}