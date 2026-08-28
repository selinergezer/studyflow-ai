import type { Metadata } from "next";
import ApiCollectionView from "@/components/workspace/ApiCollectionView";

export const metadata: Metadata = { title: "Quizzes" };

export default function QuizPage() {
  return <ApiCollectionView kind="quizzes" />;
}
