"use client";

import { useCallback, useEffect, useState } from "react";
import { createStudyRoom, getCourses, getMyStudyRooms, getStudyRoomMembers, getStudyRoomStats, joinStudyRoom, type Course, type StudyRoom, type StudyRoomMember, type StudyRoomStats } from "@/lib/api";

type Props = { onRoomSelected: (room: StudyRoom) => void };
type RoomDetails = { members: StudyRoomMember[]; stats: StudyRoomStats | null };

function NetworkArtwork() {
  return <svg className="study-room-network-art" viewBox="0 0 440 190" fill="none" aria-hidden="true"><path d="M92 112c62-67 106-63 148-14 48 56 89 30 116-12"/><g className="study-room-network-user one"><circle cx="91" cy="112" r="34"/><circle cx="91" cy="102" r="10"/><path d="M72 132c5-20 33-20 39 0"/></g><g className="study-room-network-user two"><circle cx="235" cy="79" r="37"/><circle cx="235" cy="68" r="10"/><path d="M215 100c5-21 35-21 41 0"/></g><g className="study-room-network-user three"><circle cx="358" cy="105" r="35"/><circle cx="358" cy="95" r="10"/><path d="M339 125c5-20 33-20 39 0"/></g><path className="study-room-spark" d="m45 57 3 8 8 3-8 3-3 8-3-8-8-3 8-3Zm350-16 3 8 8 3-8 3-3 8-3-8-8-3 8-3Z"/></svg>;
}

export default function StudyRoomLobby({ onRoomSelected }: Props) {
  const [rooms, setRooms] = useState<StudyRoom[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [roomDetails, setRoomDetails] = useState<Record<number, RoomDetails>>({});
  const [roomName, setRoomName] = useState("");
  const [courseId, setCourseId] = useState("");
  const [roomCode, setRoomCode] = useState("");
  const [roomView, setRoomView] = useState<"list" | "grid">("list");
  const [roomSort, setRoomSort] = useState("recent");
  const [copyStatus, setCopyStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadLobby = useCallback(async () => {
    try {
      setError(null);
      const [roomData, courseData] = await Promise.all([getMyStudyRooms(), getCourses()]);
      setRooms(roomData);
      setCourses(courseData);
      const details = await Promise.all(roomData.map(async (room) => {
        try {
          const [members, stats] = await Promise.all([getStudyRoomMembers(room.id), getStudyRoomStats(room.id)]);
          return [room.id, { members, stats }] as const;
        } catch { return [room.id, { members: [], stats: null }] as const; }
      }));
      setRoomDetails(Object.fromEntries(details));
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Çalışma odaları yüklenemedi."); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { queueMicrotask(() => { void loadLobby(); }); }, [loadLobby]);

  async function handleCreateRoom() {
    if (!roomName.trim()) return setError("Lütfen oda adı girin.");
    if (!courseId) return setError("Lütfen bir ders seçin.");
    try { setBusy(true); setError(null); const room = await createStudyRoom(roomName.trim(), Number(courseId)); setRooms((current) => [room, ...current]); setRoomName(""); setCourseId(""); onRoomSelected(room); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Çalışma odası oluşturulamadı."); }
    finally { setBusy(false); }
  }

  async function handleJoinRoom() {
    const code = roomCode.trim().toUpperCase();
    if (!code) return setError("Lütfen oda kodunu girin.");
    try { setBusy(true); setError(null); const room = await joinStudyRoom(code); setRoomCode(""); onRoomSelected(room); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Odaya katılınamadı."); }
    finally { setBusy(false); }
  }

  async function copyRoomCode(room: StudyRoom) { await navigator.clipboard.writeText(room.code); setCopyStatus(room.code); window.setTimeout(() => setCopyStatus(null), 1800); }
  async function shareRoom(room: StudyRoom) { const url = `${window.location.origin}/study-room?code=${room.code}`; if (navigator.share) await navigator.share({ title: room.name, text: `StudyFlow oda kodu: ${room.code}`, url }); else await navigator.clipboard.writeText(url); }

  const courseNames = new Map(courses.map((course) => [course.id, course.name]));
  const visibleRooms = [...rooms].sort((a, b) => roomSort === "name" ? a.name.localeCompare(b.name, "tr") : Date.parse(b.created_at) - Date.parse(a.created_at));

  if (loading) return <main className="study-room-page"><div className="study-room-loading">Çalışma odaları yükleniyor...</div></main>;

  return <main className="study-room-page study-room-lobby-page">
    <section className="study-room-lobby-hero">
      <div className="study-room-lobby-hero-copy"><p className="study-room-eyebrow">ÇALIŞMA ALANI</p><h1>Çalışma Odası</h1><p className="study-room-subtitle">Birlikte çalış, birbirinizi motive edin.</p><div className="study-room-features"><article><span>♧</span><div><strong>Odalar oluştur</strong><p>Dersine uygun çalışma odaları oluştur.</p></div></article><article><span>↗</span><div><strong>Arkadaşlarınla paylaş</strong><p>Davet linkini paylaşarak arkadaşlarını çağır.</p></div></article><article><span>◎</span><div><strong>Verimli çalış</strong><p>Birlikte çalışarak hedeflerine daha hızlı ulaş.</p></div></article></div></div>
      <NetworkArtwork />
    </section>

    {error ? <div className="study-room-inline-error">{error}</div> : null}

    <section className="study-room-lobby-grid">
      <div className="study-room-lobby-card study-room-create-card"><div className="study-room-card-art desk" aria-hidden="true">⌑</div><p className="study-room-card-label">YENİ ODA</p><h2>Çalışma odası oluştur</h2><p className="study-room-form-description">Bir ders seç ve arkadaşlarınla paylaşabileceğin bir çalışma odası oluştur.</p><div className="study-room-create-fields"><label className="study-room-field"><span>Oda adı</span><input value={roomName} onChange={(event) => setRoomName(event.target.value)} placeholder="Örn. Veri Yapıları Çalışma Odası" disabled={busy}/></label><label className="study-room-field"><span>Ders</span><select value={courseId} onChange={(event) => setCourseId(event.target.value)} disabled={busy}><option value="">Ders seçin</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.name}</option>)}</select></label></div><button type="button" className="study-room-action start lobby-button" onClick={handleCreateRoom} disabled={busy}>{busy ? "İşleniyor..." : "＋ Oda Oluştur"}</button></div>
      <div className="study-room-lobby-card study-room-join-card"><div className="study-room-card-art door" aria-hidden="true">↪</div><p className="study-room-card-label">ODAYA KATIL</p><h2>Bir arkadaşının odasına katıl</h2><p className="study-room-form-description">Arkadaşından aldığın 6 haneli oda kodunu aşağıya gir.</p><label className="study-room-field"><span>Oda kodu</span><input value={roomCode} onChange={(event) => setRoomCode(event.target.value.toUpperCase().slice(0,6))} placeholder="Örn. 1OAZAL" maxLength={6} disabled={busy}/></label><button type="button" className="study-room-action start lobby-button" onClick={handleJoinRoom} disabled={busy}>{busy ? "Katılınıyor..." : "Odaya Katıl  →"}</button></div>
    </section>

    <section className="study-room-my-rooms">
      <div className="study-room-card-header"><div><p className="study-room-card-label">ODALARIM</p><h2>Çalışma odalarım</h2></div><div className="study-room-list-controls"><select value={roomSort} onChange={(event) => setRoomSort(event.target.value)}><option value="recent">Son aktif</option><option value="name">Ada göre</option></select><span><button type="button" className={roomView === "grid" ? "active" : ""} onClick={() => setRoomView("grid")}>▦</button><button type="button" className={roomView === "list" ? "active" : ""} onClick={() => setRoomView("list")}>☷</button></span></div></div>
      {rooms.length === 0 ? <div className="study-room-empty">Henüz bir çalışma odası oluşturmadın.</div> : <div className={`study-room-room-list study-room-room-list--${roomView}`}>{visibleRooms.map((room) => { const details = roomDetails[room.id]; const members = details?.members ?? []; return <article className="study-room-room-item" key={room.id}><button type="button" className="study-room-room-main" onClick={() => onRoomSelected(room)}><span className="study-room-room-icon">♟</span><span className="study-room-room-info"><strong>{room.name}</strong><span><b>Kod: {room.code}</b><i>♙ {details?.stats?.member_count ?? members.length} üye</i><i>▣ {courseNames.get(room.course_id) ?? "Ders"}</i><i>◷ {new Intl.DateTimeFormat("tr-TR", { day:"numeric", month:"short", year:"numeric" }).format(new Date(room.created_at))}</i></span></span></button><div className="study-room-room-members">{members.slice(0,3).map((member,index) => <span key={member.user_id} className={`avatar-${index}`}>{member.username.slice(0,1).toLocaleUpperCase("tr-TR")}</span>)}</div><span className="study-room-room-menu">⋮</span><div className="study-room-room-actions"><button type="button" onClick={() => void copyRoomCode(room)}>▣ {copyStatus === room.code ? "Kopyalandı" : "Kod'u Kopyala"}</button><button type="button" onClick={() => void shareRoom(room)}>♧ Linki Paylaş</button><button type="button" onClick={() => onRoomSelected(room)}>Odaya Gir　→</button></div></article>; })}</div>}
    </section>
  </main>;
}
