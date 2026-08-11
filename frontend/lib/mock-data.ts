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

export const mockCourses: Course[] = [];

export const mockDocuments: StudyDocument[] = [];
