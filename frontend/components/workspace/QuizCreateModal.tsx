"use client";

import CollectionCreateModal from "@/components/workspace/CollectionCreateModal";

export default function QuizCreateModal({ open, onClose, initialDocumentId }: { open: boolean; onClose: () => void; initialDocumentId?: number }) {
  return <CollectionCreateModal kind="quiz" open={open} onClose={onClose} initialDocumentId={initialDocumentId} />;
}
