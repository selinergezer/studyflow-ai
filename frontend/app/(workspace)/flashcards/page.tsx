import type { Metadata } from "next";
import ApiCollectionView from "@/components/workspace/ApiCollectionView";

export const metadata: Metadata = { title: "Flashcards" };

export default function FlashcardsPage() {
  return <ApiCollectionView kind="flashcards" />;
}
