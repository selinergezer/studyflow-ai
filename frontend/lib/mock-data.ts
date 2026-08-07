import type { TranslationKey } from "@/lib/translations";

export type StudyDocument = {
  id: string;
  name: string;
  course: string;
  uploadedAt: string;
  pageCount: number;
  size: string;
};

export type Course = {
  id: string;
  name: string;
  progress: number;
  lastStudied: TranslationKey;
};

export const mockCourses: Course[] = [
  { id: "database-systems", name: "Database Systems", progress: 72, lastStudied: "studiedYesterday" },
  { id: "software-engineering", name: "Software Engineering", progress: 45, lastStudied: "studiedThreeDaysAgo" },
  { id: "computer-networks", name: "Computer Networks", progress: 28, lastStudied: "studiedAugFirst" },
];

export const mockDocuments: StudyDocument[] = [
  {
    id: "1",
    name: "Software Engineering Week 3.pdf",
    course: "Software Engineering",
    uploadedAt: "2026-08-06",
    pageCount: 42,
    size: "3.8 MB",
  },
  {
    id: "2",
    name: "Database Normalization Notes.pdf",
    course: "Database Systems",
    uploadedAt: "2026-08-04",
    pageCount: 28,
    size: "2.1 MB",
  },
  {
    id: "3",
    name: "Computer Networks — Routing.pdf",
    course: "Computer Networks",
    uploadedAt: "2026-07-30",
    pageCount: 64,
    size: "5.6 MB",
  },
];

export function getMockDocument(id: string) {
  return mockDocuments.find((document) => document.id === id) ?? mockDocuments[0];
}
