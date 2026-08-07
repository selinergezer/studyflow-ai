import type { Metadata } from "next";
import PlaceholderPage from "@/components/workspace/PlaceholderPage";
import { mockCourses } from "@/lib/mock-data";

export const metadata: Metadata = { title: "Courses" };

export default function CoursesPage() {
  return <PlaceholderPage eyebrow="courses" title="coursesTitle" description="coursesIntro" action={{ label: "addCourse", href: "/upload" }} items={mockCourses.map((course, index) => ({ title: course.name, detail: (["courseProgress72", "courseProgress45", "courseProgress28"] as const)[index] }))} />;
}
