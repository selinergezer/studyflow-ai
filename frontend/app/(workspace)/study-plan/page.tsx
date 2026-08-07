import type { Metadata } from "next";
import PlaceholderPage from "@/components/workspace/PlaceholderPage";

export const metadata: Metadata = { title: "Study plan" };

export default function StudyPlanPage() {
  return <PlaceholderPage eyebrow="planning" title="studyPlanTitle" description="studyPlanIntro" action={{ label: "addStudyTask", href: "/courses" }} items={[{ title: "review-sql", titleKey: "reviewSql", detail: "reviewSqlDetail" }, { title: "architecture-quiz", titleKey: "architectureQuiz", detail: "architectureQuizDetail" }, { title: "routing-cards", titleKey: "routingCards", detail: "routingCardsDetail" }]} />;
}
