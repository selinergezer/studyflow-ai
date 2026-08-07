import type { Metadata } from "next";
import PlaceholderPage from "@/components/workspace/PlaceholderPage";

export const metadata: Metadata = { title: "Quizzes" };

export default function QuizPage() {
  return <PlaceholderPage eyebrow="practice" title="quizzesTitle" description="quizzesIntro" action={{ label: "createQuizLower", href: "/library" }} items={[{ title: "Database Fundamentals", detail: "questionsScoreYesterday" }, { title: "Software Design Patterns", detail: "questionsScoreAug" }]} />;
}
