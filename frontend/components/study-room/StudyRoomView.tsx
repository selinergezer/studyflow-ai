"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import StudyRoomChat from "@/components/study-room/StudyRoomChat";
import { deleteStudyRoomApi, finishStudyRoom, getCurrentUser, getStudyRoomMembers, getStudyRoomMessages, getStudyRoomStats, leaveStudyRoom, startStudyRoom, type CurrentUser, type StudyRoom, type StudyRoomMember, type StudyRoomMessage, type StudyRoomStats } from "@/lib/api";

type Props = { room: StudyRoom; onRoomDeleted: () => void };
type Filter = "all" | "document" | "quiz" | "flashcard";

function parseUtc(value: string) { return new Date(value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`); }
function formatDuration(seconds: number) {
  const hours = Math.floor(seconds / 3600), minutes = Math.floor((seconds % 3600) / 60), rest = seconds % 60;
  return hours > 0 ? `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}` : `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}
function timeLabel(value: string) { return parseUtc(value).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }); }
function materialIcon(type: StudyRoomMessage["material_type"]) { return type === "document" ? "PDF" : type === "quiz" ? "?" : "▤"; }

export default function StudyRoomView({ room, onRoomDeleted }: Props) {
  const router = useRouter();
  const [members, setMembers] = useState<StudyRoomMember[]>([]);
  const [messages, setMessages] = useState<StudyRoomMessage[]>([]);
  const [stats, setStats] = useState<StudyRoomStats | null>(null);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [chatOpen, setChatOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const loadRoom = useCallback(async (initial = false) => {
    try {
      if (initial) setLoading(true);
      const [memberData, statsData, messageData] = await Promise.all([getStudyRoomMembers(room.id), getStudyRoomStats(room.id), getStudyRoomMessages(room.id)]);
      setMembers(memberData); setStats(statsData);
      setMessages(Array.from(new Map(messageData.map((item) => [item.id, item])).values()));
      setError(null);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Çalışma odası verileri alınamadı."); }
    finally { setLoading(false); }
  }, [room.id]);

  useEffect(() => { queueMicrotask(() => void loadRoom(true)); }, [loadRoom]);
  useEffect(() => { void getCurrentUser().then(setCurrentUser).catch(() => setCurrentUser(null)); }, []);
  useEffect(() => {
    const poll = window.setInterval(() => void loadRoom(), 5000), clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { window.clearInterval(poll); window.clearInterval(clock); };
  }, [loadRoom]);

  const currentMember = useMemo(() => members.find((member) => member.user_id === currentUser?.id), [members, currentUser]);
  const isStudying = currentMember?.status === "studying";
  const elapsed = currentMember?.study_started_at ? Math.max(0, Math.floor((now - parseUtc(currentMember.study_started_at).getTime()) / 1000)) : 0;
  const materials = useMemo(() => {
    const unique = new Map<string, StudyRoomMessage>();
    messages.forEach((item) => { if (item.material_type && item.material_id != null) unique.set(`${item.material_type}-${item.material_id}`, item); });
    return Array.from(unique.values()).reverse();
  }, [messages]);
  const visibleMaterials = materials.filter((item) => filter === "all" || item.material_type === filter);
  const activityMessages = messages.filter((item) => item.material_type !== null);
  const studyingMembers = members.filter((member) => member.status === "studying");

  async function toggleStudy() {
    try { setBusy(true); setError(null); if (isStudying) await finishStudyRoom(room.id); else await startStudyRoom(room.id); await loadRoom(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Oturum güncellenemedi."); }
    finally { setBusy(false); }
  }
  async function copyCode() { await navigator.clipboard.writeText(room.code); setCopied(true); window.setTimeout(() => setCopied(false), 1600); }
  async function invite() {
    const url = `${window.location.origin}/study-room?code=${room.code}`;
    if (navigator.share) await navigator.share({ title: room.name, text: `StudyFlow oda kodu: ${room.code}`, url });
    else { await navigator.clipboard.writeText(url); setCopied(true); }
  }
  async function exitRoom() {
    if (!window.confirm("Bu çalışma odasından ayrılmak istediğinize emin misiniz?")) return;
    try { setBusy(true); await leaveStudyRoom(room.id); onRoomDeleted(); } catch (cause) { setError(cause instanceof Error ? cause.message : "Odadan ayrılamadınız."); setBusy(false); }
  }
  async function deleteRoom() {
    if (!window.confirm(`“${room.name}” odasını silmek istediğinize emin misiniz?`)) return;
    try { setBusy(true); await deleteStudyRoomApi(room.id); onRoomDeleted(); } catch (cause) { setError(cause instanceof Error ? cause.message : "Oda silinemedi."); setBusy(false); }
  }
  function openMaterial(item: StudyRoomMessage) {
    if (item.material_type === "document") router.push(`/documents/${item.material_id}`);
    else if (item.material_type === "quiz") router.push(`/quiz/${item.material_id}`);
    else if (item.material_document_id) router.push(`/documents/${item.material_document_id}?tab=flashcards&flashcard_id=${item.material_id}`);
  }

  if (loading) return <main className="study-room-page"><div className="study-room-loading">Çalışma odası yükleniyor...</div></main>;

  return <main className="study-room-page study-room-dashboard">
    <header className="room-dashboard-top">
      <div className="room-title-mark" aria-hidden="true">♟</div>
      <div className="room-title"><h1>{room.name}</h1><p>Birlikte çalış, paylaş, öğren.</p></div>
      <button className="room-code-card" type="button" onClick={copyCode} title="Oda kodunu kopyala"><span>ODA KODU</span><strong>{room.code}</strong><i>{copied ? "✓" : "▣"}</i></button>
      <section className="room-focus-bar"><div className="room-focus-icon">◷</div><div><span>ORTAK ODAK OTURUMU</span><strong>{formatDuration(elapsed)}</strong></div><div className="room-focus-people"><b>{stats?.currently_studying ?? 0} kişi çalışıyor</b><small>{members.filter((m) => m.status === "studying").map((m) => m.username).slice(0, 2).join(", ") || "Oturum hazır"}</small></div><button type="button" onClick={toggleStudy} disabled={busy}>{busy ? "İşleniyor..." : isStudying ? "Oturumu Bitir" : "Oturuma Katıl"}</button></section>
    </header>
    {error ? <div className="study-room-inline-error room-dashboard-error">{error}</div> : null}

    <div className="room-dashboard-grid">
      <aside className="room-panel room-members-panel">
        <div className="room-panel-heading"><h2>♙ ODA ÜYELERİ ({members.length})</h2></div>
        <div className="room-member-list">{members.length === 0 ? <div className="room-empty">Henüz aktif üye yok.</div> : members.map((member, index) => <div className="room-member-row" key={member.user_id}><span className={`room-avatar avatar-${index % 3}`}>{member.username.charAt(0).toLocaleUpperCase("tr-TR")}</span><div><strong>{member.username}</strong><small className={member.status}><i />{member.status === "studying" ? "Şu anda çalışıyor" : member.status === "idle" ? "Hazır" : "Çevrimdışı"}</small></div>{member.user_id === room.created_by ? <span className="room-owner" title="Oda sahibi">♛</span> : null}</div>)}</div>
        <button className="room-invite" type="button" onClick={invite}>＋ Üye Davet Et</button>
        <div className="room-settings"><h3>ODA AYARLARI</h3><button type="button" disabled title="Yakında">⌁ Oda bilgilerini düzenle</button><button type="button" disabled title="Yakında">♢ Bildirim ayarları</button>{currentUser?.id === room.created_by ? <button className="danger" type="button" onClick={deleteRoom} disabled={busy}>⌫ Odayı sil</button> : <button className="danger" type="button" onClick={exitRoom} disabled={busy}>↪ Odayı terk et</button>}</div>
      </aside>

      <section className="room-panel room-materials-panel">
        <div className="room-panel-heading"><h2>▱ ORTAK MATERYALLER</h2><button type="button" onClick={() => setChatOpen(true)}>＋ Materyal Paylaş</button></div>
        <div className="room-filter-tabs">{([ ["all", "Tümü"], ["document", "PDF'ler"], ["quiz", "Quiz'ler"], ["flashcard", "Kartlar"] ] as const).map(([key, label]) => <button key={key} className={filter === key ? "active" : ""} type="button" onClick={() => setFilter(key)}>{label}<span>{key === "all" ? materials.length : materials.filter((m) => m.material_type === key).length}</span></button>)}</div>
        <div className="room-material-list">{visibleMaterials.length === 0 ? <div className="room-empty room-material-empty"><span>▱</span><strong>Henüz ortak materyal yok.</strong><p>Sohbetten paylaşılan PDF, quiz ve kartlar burada görünür.</p><button type="button" onClick={() => setChatOpen(true)}>İlk materyali paylaş</button></div> : visibleMaterials.map((item) => <article className={`room-material-row type-${item.material_type}`} key={`${item.material_type}-${item.material_id}`}><div className="room-material-icon">{materialIcon(item.material_type)}</div><div className="room-material-copy"><strong>{item.material_title || `${item.material_type === "document" ? "Doküman" : item.material_type === "quiz" ? "Quiz" : "Kart Seti"} #${item.material_id}`}</strong><p>{item.username} tarafından paylaşıldı <i>•</i> {item.material_count != null ? `${item.material_count} ${item.material_type === "document" ? "sayfa" : item.material_type === "quiz" ? "soru" : "kart"}` : ""} <i>•</i> {timeLabel(item.created_at)}</p><div className="room-material-actions"><button type="button" onClick={() => openMaterial(item)}>{item.material_type === "document" ? "PDF'i Aç" : item.material_type === "quiz" ? "Sınava Katıl" : "Kartları Gör"}</button>{item.material_type === "document" ? <><button className="green" type="button" onClick={toggleStudy}>▷ Birlikte Çalış</button><button className="purple" type="button" onClick={() => router.push(`/documents/${item.material_id}?tab=quiz`)}>＋ Quiz Oluştur</button></> : null}{item.material_type === "quiz" ? <button type="button" onClick={() => router.push(`/quiz/${item.material_id}`)}>Sonuçları Gör</button> : null}</div></div></article>)}</div>
        <button className="room-dropzone" type="button" onClick={() => setChatOpen(true)}>⌁ PDF veya çalışma materyali paylaş</button>
      </section>

      <aside className="room-side-stack">
        <section className="room-panel room-activity-panel"><div className="room-panel-heading"><h2>⌁ ODA AKIŞI</h2></div><div className="room-activity-list">{activityMessages.length === 0 && studyingMembers.length === 0 ? <div className="room-empty"><strong>Henüz oda aktivitesi yok.</strong><p>Birlikte çalışmaya başladığınızda aktiviteler burada görünecek.</p></div> : null}{studyingMembers.map((member) => <div className="room-activity" key={`member-${member.user_id}`}><span className="green">●</span><p><strong>{member.username}</strong> çalışmaya başladı</p><time>{member.study_started_at ? timeLabel(member.study_started_at) : "Şimdi"}</time></div>)}{[...activityMessages].reverse().slice(0, 7).map((item) => <div className="room-activity" key={item.id}><span className={item.material_type || "message"}>{materialIcon(item.material_type)}</span><p><strong>{item.username}</strong> {item.material_title || "bir materyal"} paylaştı</p><time>{timeLabel(item.created_at)}</time></div>)}</div></section>
        <section className="room-panel room-performance-panel"><div className="room-panel-heading"><h2>♜ ODA PERFORMANSI</h2></div><div className="room-empty"><span>↗</span><strong>Henüz tamamlanan ortak quiz yok.</strong><p>Ortak quiz sonuçları oluştuğunda burada listelenecek.</p></div></section>
      </aside>
    </div>

    {!chatOpen ? <button className="room-chat-fab" type="button" onClick={() => setChatOpen(true)} aria-label="Oda sohbetini aç" title="Oda sohbeti"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h9a4 4 0 0 1 4 4v8Z"/><path d="M8 9h8M8 13h5"/></svg></button> : null}
    {chatOpen ? <div className="study-room-chat-drawer"><div className="study-room-chat-drawer-top"><div><span>CANLI</span><strong>Oda sohbeti</strong></div><button className="study-room-chat-close" type="button" onClick={() => { setChatOpen(false); void loadRoom(); }}>×</button></div><StudyRoomChat roomId={room.id} /></div> : null}
  </main>;
}
