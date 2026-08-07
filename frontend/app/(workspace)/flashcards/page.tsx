import type { Metadata } from "next";
import PlaceholderPage from "@/components/workspace/PlaceholderPage";

export const metadata: Metadata = { title: "Flashcards" };

export default function FlashcardsPage() {
  return <PlaceholderPage eyebrow="review" title="flashcardsTitle" description="flashcardsIntro" action={{ label: "generateFlashcards", href: "/library" }} items={[{ title: "Database Terminology", detail: "cardsReviewedToday" }, { title: "Network Protocols", detail: "cardsReviewedAug" }]} />;
}
