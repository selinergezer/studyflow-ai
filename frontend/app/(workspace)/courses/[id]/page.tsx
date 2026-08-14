import type { Metadata } from "next";
import CourseWorkspace from "@/components/courses/CourseWorkspace";

export const metadata: Metadata = { title: "Course workspace" };

export default async function CoursePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const courseId = Number(id);

  return <CourseWorkspace courseId={courseId} />;
}
