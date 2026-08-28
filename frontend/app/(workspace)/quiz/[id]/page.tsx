import type { Metadata } from "next";
import QuizSolveView from "@/components/documents/QuizSolveView";

export const metadata: Metadata = { title: "Sınav" };

type QuizPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ document_id?: string }>;
};

export default async function QuizDetailPage({ params, searchParams }: QuizPageProps) {
  const { id } = await params;
  const { document_id: documentId } = await searchParams;
  return <QuizSolveView quizId={id} documentId={documentId} />;
}
