"use client";

import CollectionCreateModal from "@/components/workspace/CollectionCreateModal";

export default function FlashcardCreateModal({ open, onClose, initialDocumentId }: { open: boolean; onClose: () => void; initialDocumentId?: number }) {
  return <CollectionCreateModal kind="flashcards" open={open} onClose={onClose} initialDocumentId={initialDocumentId} />;
}
