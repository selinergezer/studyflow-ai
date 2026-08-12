import type { Metadata } from "next";
import StudyPlanEmpty from "@/components/workspace/StudyPlanEmpty";

export const metadata: Metadata = { title: "Study plan" };

export default function StudyPlanPage() {
  return <StudyPlanEmpty />;
}
