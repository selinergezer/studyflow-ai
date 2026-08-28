import type { Metadata } from "next";
import AskAiView from "@/components/ai/AskAiView";

export const metadata: Metadata = {
  title: "Yapay Zekaya Sor",
};

export default function AskAiPage() {
  return <AskAiView />;
}
