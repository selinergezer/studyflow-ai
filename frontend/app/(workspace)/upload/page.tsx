import type { Metadata } from "next";
import PdfUploader from "@/components/upload/PdfUploader";

export const metadata: Metadata = { title: "Upload material" };

export default async function UploadPage({
  searchParams,
}: {
  searchParams: Promise<{ courseId?: string }>;
}) {
  const { courseId } = await searchParams;
  const parsedCourseId = Number(courseId);
  const initialCourseId =
    courseId && Number.isInteger(parsedCourseId) && parsedCourseId > 0
      ? parsedCourseId
      : undefined;

  return <PdfUploader initialCourseId={initialCourseId} />;
}
