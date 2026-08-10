import type { Metadata } from "next";
import DocumentWorkspace from "@/components/documents/DocumentWorkspace";

type DocumentPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ tab?: string }>;
};

export async function generateMetadata({ params }: DocumentPageProps): Promise<Metadata> {
  await params;
  return { title: "Belge detayı" };
}

export default async function DocumentPage({ params, searchParams }: DocumentPageProps) {
  const { id } = await params;
  const { tab } = await searchParams;
  const initialTab = tab === "quiz" || tab === "flashcards" ? tab : "summary";
  return <DocumentWorkspace key={`${id}-${initialTab}`} documentId={id} initialTab={initialTab} />;
}
