"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createStudyRoom,
  getCourses,
  getMyStudyRooms,
  joinStudyRoom,
  type Course,
  type StudyRoom,
} from "@/lib/api";

type Props = {
  onRoomSelected: (room: StudyRoom) => void;
};

export default function StudyRoomLobby({
  onRoomSelected,
}: Props) {
  const [rooms, setRooms] = useState<StudyRoom[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);

  const [roomName, setRoomName] = useState("");
  const [courseId, setCourseId] = useState("");

  const [roomCode, setRoomCode] = useState("");

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadLobby = useCallback(async () => {
    try {
      setError(null);

      const [roomData, courseData] = await Promise.all([
        getMyStudyRooms(),
        getCourses(),
      ]);

      setRooms(roomData);
      setCourses(courseData);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Çalışma odaları yüklenemedi.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => {
      void loadLobby();
    });
  }, [loadLobby]);

  async function handleCreateRoom() {
    const trimmedName = roomName.trim();

    if (!trimmedName) {
      setError("Lütfen oda adı girin.");
      return;
    }

    if (!courseId) {
      setError("Lütfen bir ders seçin.");
      return;
    }

    try {
      setBusy(true);
      setError(null);

      const room = await createStudyRoom(
        trimmedName,
        Number(courseId),
      );

      setRooms((current) => [room, ...current]);
      setRoomName("");
      setCourseId("");

      onRoomSelected(room);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Çalışma odası oluşturulamadı.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleJoinRoom() {
    const normalizedCode = roomCode.trim().toUpperCase();

    if (!normalizedCode) {
      setError("Lütfen oda kodunu girin.");
      return;
    }

    try {
      setBusy(true);
      setError(null);

      const room = await joinStudyRoom(normalizedCode);

      setRoomCode("");

      onRoomSelected(room);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Odaya katılınamadı.",
      );
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <main className="study-room-page">
        <div className="study-room-loading">
          Çalışma odaları yükleniyor...
        </div>
      </main>
    );
  }

  return (
    <main className="study-room-page">
      <section className="study-room-header">
        <div>
          <p className="study-room-eyebrow">
            ÇALIŞMA ALANI
          </p>

          <h1>Çalışma Odası</h1>

          <p className="study-room-subtitle">
            Birlikte çalış, birbirinizi motive edin.
          </p>
        </div>
      </section>

      {error ? (
        <div className="study-room-inline-error">
          {error}
        </div>
      ) : null}

      <section className="study-room-lobby-grid">
        <div className="study-room-lobby-card">
          <p className="study-room-card-label">
            YENİ ODA
          </p>

          <h2>Çalışma odası oluştur</h2>

          <p className="study-room-form-description">
            Bir ders seç ve arkadaşlarınla paylaşabileceğin
            bir çalışma odası oluştur.
          </p>

          <label className="study-room-field">
            <span>Oda adı</span>

            <input
              type="text"
              value={roomName}
              onChange={(event) =>
                setRoomName(event.target.value)
              }
              placeholder="Örn. Veri Yapıları Çalışma Odası"
              disabled={busy}
            />
          </label>

          <label className="study-room-field">
            <span>Ders</span>

            <select
              value={courseId}
              onChange={(event) =>
                setCourseId(event.target.value)
              }
              disabled={busy}
            >
              <option value="">
                Ders seçin
              </option>

              {courses.map((course) => (
                <option
                  key={course.id}
                  value={course.id}
                >
                  {course.name}
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            className="study-room-action start lobby-button"
            onClick={handleCreateRoom}
            disabled={busy}
          >
            {busy
              ? "İşleniyor..."
              : "Odayı Oluştur"}
          </button>
        </div>

        <div className="study-room-lobby-card">
          <p className="study-room-card-label">
            ODAYA KATIL
          </p>

          <h2>Bir arkadaşının odasına katıl</h2>

          <p className="study-room-form-description">
            Arkadaşından aldığın 6 haneli oda kodunu
            aşağıya gir.
          </p>

          <label className="study-room-field">
            <span>Oda kodu</span>

            <input
              type="text"
              value={roomCode}
              onChange={(event) =>
                setRoomCode(
                  event.target.value
                    .toUpperCase()
                    .slice(0, 6),
                )
              }
              placeholder="Örn. 1OAZAL"
              maxLength={6}
              disabled={busy}
            />
          </label>

          <button
            type="button"
            className="study-room-action start lobby-button"
            onClick={handleJoinRoom}
            disabled={busy}
          >
            {busy
              ? "Katılınıyor..."
              : "Odaya Katıl"}
          </button>
        </div>
      </section>

      <section className="study-room-my-rooms">
        <div className="study-room-card-header">
          <div>
            <p className="study-room-card-label">
              ODALARIM
            </p>

            <h2>Çalışma odalarım</h2>
          </div>

          <span className="study-room-member-count">
            {rooms.length} oda
          </span>
        </div>

        {rooms.length === 0 ? (
          <div className="study-room-empty">
            Henüz bir çalışma odası oluşturmadın.
          </div>
        ) : (
          <div className="study-room-room-list">
            {rooms.map((room) => (
              <button
                type="button"
                className="study-room-room-item"
                key={room.id}
                onClick={() =>
                  onRoomSelected(room)
                }
              >
                <div className="study-room-room-icon">
                  S
                </div>

                <div className="study-room-room-info">
                  <strong>{room.name}</strong>

                  <span>
                    Kod: {room.code}
                  </span>
                </div>

                <span className="study-room-room-arrow">
                  →
                </span>
              </button>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}