import type { Metadata } from "next";
import DocumentWorkspace from "@/components/documents/DocumentWorkspace";
import { getMockDocument } from "@/lib/mock-data";

type DocumentPageProps = {
  params: Promise<{ id: string }>;
};

export async function generateMetadata({ params }: DocumentPageProps): Promise<Metadata> {
  const { id } = await params;
  return { title: getMockDocument(id).name };
}

export default async function DocumentPage({ params }: DocumentPageProps) {
  const { id } = await params;
  return <DocumentWorkspace document={getMockDocument(id)} />;
}
