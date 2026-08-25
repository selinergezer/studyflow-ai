"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { useRouter } from "next/navigation";

import {
  apiFetch,
  getDocuments,
  getFlashcards,
  getQuizzes,
  getStudyRoomMessages,
  sendStudyRoomMessage,
  type DocumentData,
  type Flashcard,
  type Quiz,
  type StudyRoomMessage,
} from "@/lib/api";

type Props = {
  roomId: number;
};

type MaterialType = "document" | "quiz" | "flashcard";

type SelectedMaterial = {
  type: MaterialType;
  id: number;
  title: string;
};

type FlashcardGroup = {
  batchId: string;
  documentId: number | null;
  cards: Flashcard[];
};

function getMaterialLabel(type: MaterialType) {
  switch (type) {
    case "document":
      return "PDF / Doküman";
    case "quiz":
      return "Quiz";
    case "flashcard":
      return "Flashcard";
  }
}

function getMaterialIcon(type: MaterialType) {
  switch (type) {
    case "document":
      return "📄";
    case "quiz":
      return "📝";
    case "flashcard":
      return "🧠";
  }
}

export default function StudyRoomChat({ roomId }: Props) {
  const router = useRouter();
  const [messages, setMessages] = useState<StudyRoomMessage[]>([]);
  const [message, setMessage] = useState("");

  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [materialPanelOpen, setMaterialPanelOpen] =
    useState(false);

  const [materialLoading, setMaterialLoading] =
    useState(false);

  const [materialType, setMaterialType] =
    useState<MaterialType>("document");

  const [documents, setDocuments] = useState<DocumentData[]>([]);
  const [quizzes, setQuizzes] = useState<Quiz[]>([]);
  const [flashcards, setFlashcards] = useState<Flashcard[]>([]);

  const [selectedMaterial, setSelectedMaterial] =
    useState<SelectedMaterial | null>(null);

  const messagesEndRef =
    useRef<HTMLDivElement | null>(null);

  const loadMessages = useCallback(
    async (showLoading = false) => {
      try {
        if (showLoading) {
          setLoading(true);
        }

        const data = await getStudyRoomMessages(roomId);

const uniqueMessages = Array.from(
  new Map(
    data.map((item) => [item.id, item]),
  ).values(),
);

setMessages(uniqueMessages);
setError(null);
      } catch (cause) {
        setError(
          cause instanceof Error
            ? cause.message
            : "Mesajlar yüklenemedi.",
        );
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [roomId],
  );

  useEffect(() => {
    queueMicrotask(() => {
      void loadMessages(true);
    });
  }, [loadMessages]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void loadMessages();
    }, 5000);

    return () => window.clearInterval(interval);
  }, [loadMessages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages]);

  async function loadMaterials() {
    try {
      setMaterialLoading(true);
      setError(null);

      const [documentData, quizData, flashcardData] =
        await Promise.all([
          getDocuments(),
          getQuizzes(),
          getFlashcards(),
        ]);

      setDocuments(documentData);
      setQuizzes(quizData);
      setFlashcards(flashcardData);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Materyaller yüklenemedi.",
      );
    } finally {
      setMaterialLoading(false);
    }
  }

  async function handleOpenMaterialPanel() {
    setMaterialPanelOpen(true);

    if (
      documents.length === 0 &&
      quizzes.length === 0 &&
      flashcards.length === 0
    ) {
      await loadMaterials();
    }
  }

  function handleSelectDocument(document: DocumentData) {
    const id = document.id ?? document.document_id;

    if (!id) {
      return;
    }

    setSelectedMaterial({
      type: "document",
      id,
      title: document.filename,
    });

    setMaterialPanelOpen(false);
  }

  function handleSelectQuiz(quiz: Quiz) {
    const id = quiz.id ?? quiz.quiz_id;

    if (!id) {
      return;
    }

    setSelectedMaterial({
      type: "quiz",
      id,
      title: quiz.title,
    });

    setMaterialPanelOpen(false);
  }

  function handleSelectFlashcard(group: FlashcardGroup) {
    const firstCard = group.cards[0];

    if (!firstCard) {
      return;
    }

    setSelectedMaterial({
      type: "flashcard",
      id: firstCard.id,
      title: `Flashcard Seti (${group.cards.length} kart)`,
  });

  setMaterialPanelOpen(false);
}

  async function handleSend() {
    const trimmedMessage = message.trim();

    if (
      sending ||
      (!trimmedMessage && !selectedMaterial)
    ) {
      return;
    }

    try {
      setSending(true);
      setError(null);

      const createdMessage =
        await sendStudyRoomMessage(
          roomId,
          trimmedMessage ||
            `Şu ${getMaterialLabel(
              selectedMaterial!.type,
            ).toLowerCase()} materyalini paylaşıyorum.`,
          selectedMaterial?.type,
          selectedMaterial?.id,
        );

      setMessages((current) => {
  if (
    current.some(
      (item) => item.id === createdMessage.id,
    )
  ) {
    return current;
  }

  return [...current, createdMessage];
});

      setMessage("");
      setSelectedMaterial(null);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Mesaj gönderilemedi.",
      );
    } finally {
      setSending(false);
    }
  }
  

    async function handleOpenMaterial(
  materialType: StudyRoomMessage["material_type"],
  materialId: number | null,
) {
  if (!materialType || materialId == null) {
    return;
  }

  if (materialType === "document") {
    router.push(`/documents/${materialId}`);
    return;
  }

  if (materialType === "quiz") {
    router.push(`/quiz/${materialId}`);
    return;
  }

  if (materialType === "flashcard") {
    try {
      // Çalışma odasındaki local state'e güvenme.
      // Paylaşılan kartı API'den tekrar al.
      const allFlashcards = await getFlashcards();

      const sharedFlashcard = allFlashcards.find(
        (flashcard) => flashcard.id === materialId,
      );

      if (!sharedFlashcard) {
        console.error(
          "Paylaşılan flashcard bulunamadı:",
          materialId,
        );
        return;
      }

      if (sharedFlashcard.document_id == null) {
        console.error(
          "Paylaşılan flashcard'ın document_id'si yok:",
          sharedFlashcard,
        );
        return;
      }

      const url =
        `/documents/${sharedFlashcard.document_id}` +
        `?tab=flashcards&flashcard_id=${sharedFlashcard.id}`;

      console.log(
        "PAYLAŞILAN FLASHCARD YÖNLENDİRMESİ:",
        url,
      );

      router.push(url);
    } catch (error) {
      console.error(
        "Paylaşılan flashcardlar alınamadı:",
        error,
      );
    }

    return;
  }
}

  function handleKeyDown(
    event: React.KeyboardEvent<HTMLTextAreaElement>,
  ) {
    if (
      event.key === "Enter" &&
      !event.shiftKey
    ) {
      event.preventDefault();
      void handleSend();
    }
  }
  const flashcardGroups = Array.from(
  flashcards.reduce((groups, flashcard) => {
    const batchId =
      flashcard.batch_id ?? `single-${flashcard.id}`;

    const existing = groups.get(batchId);

    if (existing) {
      existing.cards.push(flashcard);
    } else {
      groups.set(batchId, {
        batchId,
        documentId: flashcard.document_id,
        cards: [flashcard],
      });
    }

    return groups;
  }, new Map<string, FlashcardGroup>()),
).map(([, group]) => group);

  const currentMaterials =
    materialType === "document"
      ? documents
      : materialType === "quiz"
        ? quizzes
        : flashcards;

  return (
    <section className="study-room-chat">
      <div className="study-room-chat-header">
        <div>
          <p className="study-room-card-label">
            ODA SOHBETİ
          </p>

          <h2>Birlikte konuşun</h2>
        </div>

        <span className="study-room-chat-online">
          ● Canlı
        </span>
      </div>

      <div className="study-room-chat-messages">
        {loading ? (
          <div className="study-room-chat-empty">
            Mesajlar yükleniyor...
          </div>
        ) : messages.length === 0 ? (
          <div className="study-room-chat-empty">
            Henüz mesaj yok.
            <br />
            İlk mesajı sen gönder.
          </div>
        ) : (
          messages.map((item) => (
            <article
              className="study-room-chat-message"
              key={item.id}
            >
              <div className="study-room-chat-avatar">
                {item.username
                  .charAt(0)
                  .toUpperCase()}
              </div>

              <div className="study-room-chat-message-content">
                <div className="study-room-chat-message-meta">
                  <strong>{item.username}</strong>

                  <time>
                    {new Date(
                      `${item.created_at}Z`,
                    ).toLocaleTimeString(
                      "tr-TR",
                      {
                        hour: "2-digit",
                        minute: "2-digit",
                      },
                    )}
                  </time>
                </div>

                {item.message ? (
                  <p>{item.message}</p>
                ) : null}

                {item.material_type &&
                item.material_id ? (
                  <div className="study-room-material-card">
                    <div className="study-room-material-icon">
                      {getMaterialIcon(
                        item.material_type,
                      )}
                    </div>

                    <div className="study-room-material-info">
                      <strong>
                        {getMaterialLabel(
                          item.material_type,
                        )}
                      </strong>

                      <span>
                        Materyal #{item.material_id}
                      </span>
                    </div>

                    <button
  type="button"
  className="study-room-material-button"
  onClick={() =>
    handleOpenMaterial(
      item.material_type,
      item.material_id,
    )
  }
>
  Gör
</button>
                  </div>
                ) : null}
              </div>
            </article>
          ))
        )}

        <div ref={messagesEndRef} />
      </div>

      {error ? (
        <p
          className="study-room-chat-error"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      {selectedMaterial ? (
        <div className="study-room-selected-material">
          <div>
            <span>
              {getMaterialIcon(
                selectedMaterial.type,
              )}
            </span>

            <div>
              <strong>
                {getMaterialLabel(
                  selectedMaterial.type,
                )}
              </strong>

              <p>{selectedMaterial.title}</p>
            </div>
          </div>

          <button
            type="button"
            onClick={() =>
              setSelectedMaterial(null)
            }
            disabled={sending}
          >
            ×
          </button>
        </div>
      ) : null}

      {materialPanelOpen ? (
        <div className="study-room-material-panel">
          <div className="study-room-material-panel-header">
            <div>
              <strong>
                Materyal Paylaş
              </strong>

              <span>
                Odadaki arkadaşlarınla paylaş
              </span>
            </div>

            <button
              type="button"
              onClick={() =>
                setMaterialPanelOpen(false)
              }
            >
              ×
            </button>
          </div>

          <div className="study-room-material-tabs">
            <button
              type="button"
              className={
                materialType === "document"
                  ? "active"
                  : ""
              }
              onClick={() =>
                setMaterialType("document")
              }
            >
              📄 Doküman
            </button>

            <button
              type="button"
              className={
                materialType === "quiz"
                  ? "active"
                  : ""
              }
              onClick={() =>
                setMaterialType("quiz")
              }
            >
              📝 Quiz
            </button>

            <button
              type="button"
              className={
                materialType === "flashcard"
                  ? "active"
                  : ""
              }
              onClick={() =>
                setMaterialType("flashcard")
              }
            >
              🧠 Flashcard
            </button>
          </div>

          <div className="study-room-material-list">
            {materialLoading ? (
              <div className="study-room-material-empty">
                Materyaller yükleniyor...
              </div>
            ) :
  (
    materialType === "flashcard"
      ? flashcardGroups.length === 0
      : currentMaterials.length === 0
  ) ? (
              <div className="study-room-material-empty">
                Bu kategoride paylaşılacak
                materyal bulunamadı.
              </div>
            ) : materialType ===
              "document" ? (
              documents.map((document) => {
                const id =
                  document.id ??
                  document.document_id;

                if (!id) {
                  return null;
                }

                return (
                  <button
                    type="button"
                    className="study-room-material-option"
                    key={id}
                    onClick={() =>
                      handleSelectDocument(
                        document,
                      )
                    }
                  >
                    <span>📄</span>

                    <div>
                      <strong>
                        {document.filename}
                      </strong>

                      <small>
                        {document.page_count} sayfa
                      </small>
                    </div>
                  </button>
                );
              })
            ) : materialType === "quiz" ? (
              quizzes.map((quiz) => {
                const id =
                  quiz.id ?? quiz.quiz_id;

                if (!id) {
                  return null;
                }

                return (
                  <button
                    type="button"
                    className="study-room-material-option"
                    key={id}
                    onClick={() =>
                      handleSelectQuiz(quiz)
                    }
                  >
                    <span>📝</span>

                    <div>
                      <strong>
                        {quiz.title}
                      </strong>

                      <small>
                        {quiz.question_count ??
                          0}{" "}
                        soru
                      </small>
                    </div>
                  </button>
                );
              })
            ) : (
              flashcardGroups.map((group) => {
  const firstCard = group.cards[0];

  if (!firstCard) {
    return null;
  }

  return (
    <button
      type="button"
      className="study-room-material-option"
      key={group.batchId}
      onClick={() =>
        handleSelectFlashcard(group)
      }
    >
      <span>🧠</span>

      <div>
        <strong>
          Flashcard Seti
        </strong>

        <small>
          {group.cards.length} kart
          {group.documentId
            ? ` • Materyal #${group.documentId}`
            : ""}
        </small>
      </div>
    </button>
  );
})
            )}
          </div>
        </div>
      ) : null}

      <div className="study-room-chat-input-area">
        <button
          type="button"
          className="study-room-chat-attach-button"
          onClick={() =>
            void handleOpenMaterialPanel()
          }
          disabled={sending}
          title="Materyal paylaş"
        >
          📎
        </button>

        <textarea
          value={message}
          onChange={(event) =>
            setMessage(event.target.value)
          }
          onKeyDown={handleKeyDown}
          placeholder="Odaya bir mesaj yaz..."
          rows={2}
          disabled={sending}
          maxLength={2000}
        />

        <button
          type="button"
          onClick={handleSend}
          disabled={
            sending ||
            (
              message.trim().length === 0 &&
              !selectedMaterial
            )
          }
          className="study-room-action start"
        >
          {sending
            ? "Gönderiliyor..."
            : "Gönder"}
        </button>
      </div>

      <p className="study-room-chat-hint">
        Enter ile gönder · Shift + Enter ile
        yeni satır · 📎 ile materyal paylaş
      </p>
    </section>
  );
}
