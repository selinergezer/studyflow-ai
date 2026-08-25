"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";

import {
  deleteStudyRoomApi,
  finishStudyRoom,
  getCurrentUser,
  getStudyRoomMembers,
  getStudyRoomStats,
  startStudyRoom,
  type CurrentUser,
  type StudyRoom,
  type StudyRoomMember,
  type StudyRoomStats,
} from "@/lib/api";
import StudyRoomChat from "@/components/study-room/StudyRoomChat";
type Props = {
  room: StudyRoom;
  onRoomDeleted: () => void;
};

function formatDuration(totalSeconds: number) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  if (hours > 0) {
    return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(
      2,
      "0",
    )}:${String(seconds).padStart(2, "0")}`;
  }

  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(
    2,
    "0",
  )}`;
}

function parseUtcDate(dateString: string) {
  if (!dateString.endsWith("Z")) {
    return new Date(`${dateString}Z`);
  }

  return new Date(dateString);
}

function getElapsedSeconds(startedAt: string | null) {
  if (!startedAt) return 0;

  const start = parseUtcDate(startedAt).getTime();
  const now = Date.now();

  return Math.max(
    0,
    Math.floor((now - start) / 1000),
  );
}

export default function StudyRoomView({
  room,
  onRoomDeleted,
}: Props) {
  const [members, setMembers] = useState<StudyRoomMember[]>([]);
  const [stats, setStats] = useState<StudyRoomStats | null>(null);
  const [currentUser, setCurrentUser] =
  useState<CurrentUser | null>(null);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [now, setNow] = useState(() => Date.now());
  const [chatOpen, setChatOpen] = useState(false);

  const loadRoom = useCallback(
    async (showLoading = false) => {
      try {
        if (showLoading) {
          setLoading(true);
        }

        setError(null);

        const [memberData, statsData] = await Promise.all([
          getStudyRoomMembers(room.id),
          getStudyRoomStats(room.id),
        ]);

        setMembers(memberData);
        setStats(statsData);
      } catch (cause) {
        setError(
          cause instanceof Error
            ? cause.message
            : "Çalışma odası verileri alınamadı.",
        );
      } finally {
        setLoading(false);
      }
    },
    [room.id],
  );

  useEffect(() => {
    queueMicrotask(() => {
      void loadRoom(true);
    });
  }, [loadRoom]);

  useEffect(() => {
  void getCurrentUser()
    .then(setCurrentUser)
    .catch(() => {
      setCurrentUser(null);
    });
}, []);

  useEffect(() => {
    const interval = window.setInterval(() => {
      void loadRoom();
    }, 5000);

    return () => window.clearInterval(interval);
  }, [loadRoom]);

  /*
   * Canlı sayaç.
   * Backend'e her saniye istek atmıyoruz.
   * study_started_at üzerinden frontend'de hesaplıyoruz.
   */
  useEffect(() => {
    const interval = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => window.clearInterval(interval);
  }, []);

  const currentMember = useMemo(
  () =>
    currentUser
      ? members.find(
          (member) => member.user_id === currentUser.id,
        )
      : undefined,
  [members, currentUser],
);

  const elapsedSeconds = currentMember?.study_started_at
  ? Math.max(
      0,
      Math.floor(
        (now -
          parseUtcDate(
            currentMember.study_started_at,
          ).getTime()) /
          1000,
      ),
    )
  : 0;

  async function handleStart() {
    try {
      setBusy(true);
      setError(null);

      await startStudyRoom(room.id);
      await loadRoom();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Çalışma başlatılamadı.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleFinish() {
    try {
      setBusy(true);
      setError(null);

      await finishStudyRoom(room.id);
      await loadRoom();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Çalışma tamamlanamadı.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    const confirmed = window.confirm(
      `"${room.name}" adlı çalışma odasını silmek istediğinize emin misiniz?`,
    );

    if (!confirmed) {
      return;
    }

    try {
      setBusy(true);
      setError(null);

      await deleteStudyRoomApi(room.id);

      onRoomDeleted();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Study Room silinemedi.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <main className="study-room-page">
        <div className="study-room-loading">
          <span className="study-room-loading-dot" />
          Çalışma odası yükleniyor...
        </div>
      </main>
    );
  }

  if (error && !stats) {
    return (
      <main className="study-room-page">
        <div className="study-room-error">
          {error}
        </div>
      </main>
    );
  }
  const isOwner =
  currentUser?.id === room.created_by;

  const isStudying =
    currentMember?.status === "studying";

  return (
    <main className="study-room-page">
      <section className="study-room-header">
        <div>
          <p className="study-room-eyebrow">
            ÇALIŞMA ODASI
          </p>

          <h1>{room.name}</h1>

          <p className="study-room-subtitle">
            Birlikte çalış, birbirinizi motive edin.
          </p>
        </div>

        <div className="study-room-code">
          <span>ODA KODU</span>
          <strong>{room.code}</strong>
        </div>
      </section>

      {error ? (
        <div className="study-room-inline-error">
          {error}
        </div>
      ) : null}

      <section className="study-room-grid">
        <div className="study-room-card members-card">
          <div className="study-room-card-header">
            <div>
              <p className="study-room-card-label">
                ODA ÜYELERİ
              </p>

              <h2>Kimler çalışıyor?</h2>
            </div>

            <span className="study-room-member-count">
              {members.length} üye
            </span>
          </div>

          <div className="study-room-members">
            {members.length === 0 ? (
              <div className="study-room-empty">
                Henüz aktif üye yok.
              </div>
            ) : (
              members.map((member) => {
                const memberStudying =
                  member.status === "studying";

                const memberElapsed =
                  member.study_started_at
                    ? getElapsedSeconds(
                        member.study_started_at,
                      )
                    : 0;

                return (
                  <div
                    className="study-room-member"
                    key={member.user_id}
                  >
                    <div className="study-room-avatar">
                      {member.username
                        .charAt(0)
                        .toUpperCase()}
                    </div>

                    <div className="study-room-member-info">
                      <strong>
                        {member.username}
                      </strong>

                      <span
                        className={`study-room-status ${member.status}`}
                      >
                        <i />

                        {memberStudying
                          ? "Çalışıyor"
                          : member.status === "idle"
                            ? "Hazır"
                            : "Çevrimdışı"}
                      </span>
                    </div>

                    {memberStudying ? (
                      <div className="study-room-member-time">
                        {formatDuration(
                          memberElapsed,
                        )}
                      </div>
                    ) : null}
                  </div>
                );
              })
            )}
          </div>
        </div>

        <div className="study-room-card stats-card">
          <div className="study-room-card-header">
            <div>
              <p className="study-room-card-label">
                ODA İSTATİSTİKLERİ
              </p>

              <h2>Bugünkü durum</h2>
            </div>

            <span className="study-room-chart-icon">
              ↗
            </span>
          </div>

          <div className="study-room-stats">
            <div className="study-room-stat">
              <span>Bugün</span>
              <strong>
                {stats?.today_minutes ?? 0} dk
              </strong>
            </div>

            <div className="study-room-stat">
              <span>Toplam</span>
              <strong>
                {stats?.total_minutes ?? 0} dk
              </strong>
            </div>

            <div className="study-room-stat">
              <span>Üye</span>
              <strong>
                {stats?.member_count ?? 0}
              </strong>
            </div>

            <div className="study-room-stat">
              <span>Şu anda çalışan</span>
              <strong>
                {stats?.currently_studying ?? 0}
              </strong>
            </div>
          </div>
        </div>
      </section>

      <section className="study-room-focus">
  <div className="study-room-focus-inner">
    <div
  className={`study-room-desk-lamp ${
    isStudying ? "is-on" : ""
  }`}
  aria-label={
    isStudying
      ? "Çalışma lambası açık"
      : "Çalışma lambası kapalı"
  }
>
  <div className="study-room-lamp-light" />

  <svg
    className="study-room-lamp-svg"
    viewBox="0 0 220 260"
    aria-hidden="true"
  >
    {/* Masa lambasının gölgesi */}
    <ellipse
      cx="108"
      cy="239"
      rx="74"
      ry="10"
      className="lamp-shadow"
    />

    {/* Taban */}
    <path
      d="M45 224
         C45 213 58 206 76 204
         L142 204
         C160 206 174 213 174 224
         C174 232 160 237 110 238
         C60 237 45 232 45 224Z"
      className="lamp-base"
    />

    {/* Taban üstü */}
    <ellipse
      cx="110"
      cy="205"
      rx="48"
      ry="9"
      className="lamp-base-top"
    />

    {/* Alt kol */}
    <path
      d="M92 202
         L82 139"
      className="lamp-arm"
    />

    {/* Alt mafsal */}
    <circle
      cx="82"
      cy="139"
      r="9"
      className="lamp-joint"
    />

    <circle
      cx="82"
      cy="139"
      r="3.5"
      className="lamp-joint-inner"
    />

    {/* Üst kol */}
    <path
      d="M82 139
         L42 72"
      className="lamp-arm"
    />

    {/* Üst mafsal */}
    <circle
      cx="42"
      cy="72"
      r="9"
      className="lamp-joint"
    />

    <circle
      cx="42"
      cy="72"
      r="3.5"
      className="lamp-joint-inner"
    />

    {/* Lamba başlığı bağlantısı */}
    <path
      d="M42 72
         L86 55"
      className="lamp-arm"
    />

    {/* Lamba başlığı */}
    <g className="lamp-head">
      <path
        d="M77 35
           C83 23 99 17 113 21
           L148 33
           C157 36 161 45 157 53
           L140 91
           C136 99 126 103 117 99
           L85 86
           C75 82 71 72 75 63Z"
        className="lamp-shade"
      />

      {/* İç reflektör */}
      <path
        d="M83 62
           C91 51 104 48 116 52
           L145 63
           L132 91
           L103 80
           C91 76 85 70 83 62Z"
        className="lamp-reflector"
      />

      {/* Ampul */}
      <ellipse
        cx="116"
        cy="69"
        rx="17"
        ry="8"
        className="lamp-bulb"
      />
    </g>
  </svg>
</div>

    <div className="study-room-focus-content">
      <p className="study-room-card-label">
        {isStudying
          ? "ÇALIŞMA MODU"
          : "HAZIR MISIN?"}
      </p>

      <div className="study-room-timer">
        {formatDuration(elapsedSeconds)}
      </div>

      <p className="study-room-timer-description">
        {isStudying
          ? "Odaklan ve devam et."
          : "Hazırsan çalışmaya başlayabilirsin."}
      </p>

      {isStudying ? (
        <button
          type="button"
          className="study-room-action finish"
          onClick={handleFinish}
          disabled={busy}
        >
          {busy
            ? "Tamamlanıyor..."
            : "Çalışmayı Bitir"}
        </button>
      ) : (
        <button
          type="button"
          className="study-room-action start"
          onClick={handleStart}
          disabled={busy}
        >
          {busy
            ? "Başlatılıyor..."
            : "Çalışmaya Başla"}
        </button>
      )}

      {isOwner ? (
        <button
          type="button"
          className="study-room-delete"
          onClick={handleDelete}
          disabled={busy}
        >
          {busy
            ? "İşleniyor..."
            : "Çalışma Odasını Sil"}
        </button>
      ) : null}
    </div>
  </div>
</section>
      {!chatOpen ? (
  <button
    type="button"
    className="study-room-chat-trigger"
    onClick={() => setChatOpen(true)}
    aria-label="Sohbeti aç"
  >
    <span className="study-room-chat-trigger-icon">
      💬
    </span>

    <span className="study-room-chat-trigger-text">
      Oda sohbeti
    </span>

    <span className="study-room-chat-trigger-dot" />
  </button>
) : (
  <div className="study-room-chat-drawer">
  <StudyRoomChat roomId={room.id} />

  <button
    type="button"
    className="study-room-chat-close"
    onClick={() => setChatOpen(false)}
    aria-label="Sohbeti kapat"
  >
    ×
  </button>
</div>
  
)}
    </main>
  );
}