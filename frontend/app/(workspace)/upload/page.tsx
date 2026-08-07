import type { Metadata } from "next";
import PdfUploader from "@/components/upload/PdfUploader";

export const metadata: Metadata = { title: "Upload material" };

export default function UploadPage() {
  return <PdfUploader />;
}
