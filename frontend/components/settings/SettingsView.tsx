"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import Button from "@/components/ui/Button";
import Input from "@/components/ui/Input";
import { useLanguage } from "@/providers/LanguageProvider";
import type { TranslationKey } from "@/lib/translations";
import { ApiError, apiErrorMessage, apiFetch, type CurrentUser } from "@/lib/api";

type Theme = "light" | "dark";
type Modal = "history" | "materials" | "profile" | "password" | null;

const THEME_KEY = "studyflow.theme";
const THEME_EVENT = "studyflow-theme-change";

function subscribeToTheme(callback: () => void) {
  window.addEventListener(THEME_EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(THEME_EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

function getThemeSnapshot(): Theme {
  return window.localStorage.getItem(THEME_KEY) === "light" ? "light" : "dark";
}

function useTheme() {
  const theme = useSyncExternalStore(subscribeToTheme, getThemeSnapshot, (): Theme => "dark");

  function setTheme(value: Theme) {
    window.localStorage.setItem(THEME_KEY, value);
    document.documentElement.classList.toggle("dark", value === "dark");
    window.dispatchEvent(new Event(THEME_EVENT));
  }

  return [theme, setTheme] as const;
}

function SettingRow({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <div className="settings-row">
      <div className="settings-row-copy">
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      <div className="settings-row-action">{children}</div>
    </div>
  );
}

function SettingsSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="settings-paper-section" aria-labelledby={`settings-${title}`}>
      <span className="settings-section-flag" aria-hidden="true" />
      <h2 id={`settings-${title}`}>{title}</h2>
      <div className="settings-section-body">{children}</div>
    </section>
  );
}

function SegmentedControl<T extends string>({ value, options, onChange, label }: { value: T; options: Array<{ value: T; label: string }>; onChange: (value: T) => void; label: string }) {
  return (
    <div className="settings-segmented" role="group" aria-label={label}>
      {options.map((option) => (
        <button key={option.value} type="button" onClick={() => onChange(option.value)} aria-pressed={value === option.value} className={value === option.value ? "active" : ""}>
          {option.label}
        </button>
      ))}
    </div>
  );
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (checked: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)} className={`settings-toggle ${checked ? "active" : ""}`}>
      <span />
    </button>
  );
}

const modalContent: Record<"history" | "materials", { title: TranslationKey; description: TranslationKey; confirm: TranslationKey }> = {
  history: { title: "clearHistory", description: "confirmClearHistory", confirm: "clearHistoryButton" }, materials: { title: "clearUploads", description: "confirmClearUploads", confirm: "clearUploadsButton" },
};

export default function SettingsView() {
  const router = useRouter();
  const [theme, setTheme] = useTheme();
  const { language, setLanguage, t } = useLanguage();
  const [studyReminders, setStudyReminders] = useState(true);
  const [quizReminders, setQuizReminders] = useState(true);
  const [modal, setModal] = useState<Modal>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [accountError, setAccountError] = useState<string | null>(null);
  const [profileUsername, setProfileUsername] = useState("");
  const [profileEmail, setProfileEmail] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newPasswordAgain, setNewPasswordAgain] = useState("");
  const [modalError, setModalError] = useState<string | null>(null);
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileNotice, setProfileNotice] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<CurrentUser>("/users/me")
      .then(setUser)
      .catch((cause) => {
        console.error(cause);
        setAccountError(apiErrorMessage(cause, language === "tr" ? "Hesap bilgileri yüklenemedi." : "Account details could not be loaded.", "İşlem şu anda gerçekleştirilemiyor. Lütfen daha sonra tekrar deneyin."));
      });
  }, [language]);

  function openProfileModal() {
    setProfileUsername(user?.username ?? "");
    setProfileEmail(user?.email ?? "");
    setModalError(null);
    setProfileNotice(null);
    setModal("profile");
  }

  function closeProfileModal() {
    if (profileSaving) return;
    setProfileUsername(user?.username ?? "");
    setProfileEmail(user?.email ?? "");
    setModalError(null);
    setModal(null);
  }

  function openPasswordModal() {
    setCurrentPassword("");
    setNewPassword("");
    setNewPasswordAgain("");
    setModalError(null);
    setModal("password");
  }

  async function submitProfile(event: React.FormEvent) {
    event.preventDefault();
    if (profileSaving) return;
    if (!profileUsername.trim() || !profileEmail.trim()) {
      setModalError(language === "tr" ? "Kullanıcı adı ve e-posta alanları boş bırakılamaz." : "Username and email cannot be empty.");
      return;
    }
    setProfileSaving(true); setModalError(null);
    try {
      const updated = await apiFetch<CurrentUser & { message: string }>("/users/me", {
        method: "PUT",
        body: JSON.stringify({ username: profileUsername.trim(), email: profileEmail.trim() }),
      });
      const nextUser: CurrentUser = { id: updated.id, username: updated.username, email: updated.email };
      setUser(nextUser);
      setProfileNotice(language === "tr" ? "Profil başarıyla güncellendi." : "Profile updated successfully.");
      window.dispatchEvent(new CustomEvent<CurrentUser>("studyflow-user-change", { detail: nextUser }));
      setModal(null);
    } catch (cause) {
      console.error(cause);
      setModalError(cause instanceof ApiError && cause.status === 409
        ? cause.message
        : (language === "tr" ? "Profil güncellenemedi. Lütfen tekrar deneyin." : "The profile could not be updated. Please try again."));
    } finally {
      setProfileSaving(false);
    }
  }

  function submitPassword(event: React.FormEvent) {
    event.preventDefault();
    if (!currentPassword || !newPassword || !newPasswordAgain) {
      setModalError("Tüm şifre alanlarını doldurun.");
      return;
    }
    if (newPassword !== newPasswordAgain) {
      setModalError("Yeni şifreler eşleşmiyor.");
      return;
    }
    setModalError(null);
  }

  function confirmModal() {
    if (modal === "history" || modal === "materials") setNotice(t("requestConfirmed"));
    setModal(null);
  }

  function logout() {
    localStorage.removeItem("access_token");
    router.push("/login");
  }

  return (
    <div className="settings-page">
      <header className="settings-heading">
        <div className="settings-glow" aria-hidden="true" />
        <p className="settings-eyebrow">{t("settings")}</p>
        <h1>{t("settings")}</h1>
        <p>{language === "tr" ? "Hesabını ve uygulama tercihlerini buradan yönet." : "Manage your account and application preferences here."}</p>
      </header>

      <div className="settings-sections">
        <SettingsSection title={t("appearance")}>
          <SettingRow title={t("theme")} description={t("themeDesc")}>
            <SegmentedControl<Theme> value={theme} onChange={setTheme} label={t("theme")} options={[{ value: "light", label: t("light") }, { value: "dark", label: t("dark") }]} />
          </SettingRow>
        </SettingsSection>

        <SettingsSection title={t("account")}>
          <SettingRow title={language === "tr" ? "Kullanıcı adı" : "Username"} description={user?.username ?? (language === "tr" ? "Yükleniyor..." : "Loading...")}>
            <Button className="settings-action-button" variant="secondary" disabled={!user} onClick={openProfileModal}>{t("editProfile")}</Button>
          </SettingRow>
          <SettingRow title={language === "tr" ? "E-posta" : "Email"} description={user?.email ?? (language === "tr" ? "Yükleniyor..." : "Loading...")}>
            <span className="text-xs text-gray-400">{language === "tr" ? "Hesap e-postası" : "Account email"}</span>
          </SettingRow>
          <SettingRow title={language === "tr" ? "Şifre" : "Password"} description={language === "tr" ? "Şifrenizi güvenli tutun." : "Keep your password secure."}>
            <Button className="settings-action-button" variant="secondary" disabled={!user} onClick={openPasswordModal}>{language === "tr" ? "Şifreyi Değiştir" : "Change Password"}</Button>
          </SettingRow>
          {accountError ? <p className="py-4 text-sm text-red-600" role="alert">{accountError}</p> : null}
          {profileNotice ? <p className="py-4 text-sm text-green-600" role="status">{profileNotice}</p> : null}
        </SettingsSection>

        <SettingsSection title={language === "tr" ? "Oturum" : "Session"}>
          <SettingRow title={language === "tr" ? "Oturumu kapat" : "Sign out"} description={language === "tr" ? "Bu cihazdaki mevcut oturumunuzu kapatın." : "End your current session on this device."}>
            <Button className="settings-action-button settings-logout-button" variant="secondary" onClick={logout}>{language === "tr" ? "Çıkış Yap" : "Sign Out"}</Button>
          </SettingRow>
        </SettingsSection>

        <SettingsSection title={t("language")}>
          <SettingRow title={t("interfaceLanguage")} description={t("languageDesc")}>
            <SegmentedControl value={language} onChange={setLanguage} label={t("interfaceLanguage")} options={[{ value: "tr", label: t("turkish") }, { value: "en", label: t("english") }]} />
          </SettingRow>
        </SettingsSection>

        <SettingsSection title={t("notifications")}>
          <SettingRow title={t("studyReminders")} description={t("studyRemindersDesc")}>
            <Toggle checked={studyReminders} onChange={setStudyReminders} label={t("studyReminders")} />
          </SettingRow>
          <SettingRow title={t("quizReminders")} description={t("quizRemindersDesc")}>
            <Toggle checked={quizReminders} onChange={setQuizReminders} label={t("quizReminders")} />
          </SettingRow>
        </SettingsSection>

        <SettingsSection title={t("myData")}>
          <SettingRow title={t("clearHistory")} description={t("clearHistoryDesc")}>
            <Button variant="secondary" className="settings-action-button settings-danger-button" onClick={() => { setNotice(null); setModal("history"); }}>{t("clearHistoryButton")}</Button>
          </SettingRow>
          <SettingRow title={t("clearUploads")} description={t("clearUploadsDesc")}>
            <Button variant="secondary" className="settings-action-button settings-danger-button" onClick={() => { setNotice(null); setModal("materials"); }}>{t("clearUploadsButton")}</Button>
          </SettingRow>
          {notice ? <p className="pt-4 text-sm text-green-600" role="status">{notice}</p> : null}
        </SettingsSection>

        <section className="settings-about" aria-labelledby="settings-about">
          <h2 id="settings-about">{t("about")}</h2>
          <div>
            <p>StudyFlow</p>
            <p>{t("version")}</p>
            <p className="mt-2">{t("productDesc")}</p>
          </div>
        </section>
      </div>

      {modal ? (
        <div className="settings-modal-overlay" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) { if (modal === "profile") closeProfileModal(); else setModal(null); } }}>
          {modal === "profile" ? <form onSubmit={submitProfile} className="settings-modal-paper w-full max-w-md p-6" role="dialog" aria-modal="true" aria-labelledby="settings-modal-title">
            <h2 id="settings-modal-title" className="text-lg font-semibold text-gray-950">{t("editProfile")}</h2>
            <p className="mt-2 text-sm leading-6 text-gray-500">{language === "tr" ? "Hesap bilgilerinizi görüntüleyin ve düzenleyin." : "View and edit your account details."}</p>
            <div className="mt-6 space-y-4">
              <Input id="profile-username" label={language === "tr" ? "Kullanıcı adı" : "Username"} value={profileUsername} disabled={profileSaving} onChange={(event) => setProfileUsername(event.target.value)} required />
              <Input id="profile-email" type="email" label={language === "tr" ? "E-posta" : "Email"} value={profileEmail} disabled={profileSaving} onChange={(event) => setProfileEmail(event.target.value)} required />
            </div>
            {modalError ? <p className="mt-4 text-sm text-red-600" role="alert">{modalError}</p> : null}
            <div className="mt-6 flex justify-end gap-2"><Button variant="secondary" disabled={profileSaving} onClick={closeProfileModal}>{t("cancel")}</Button><Button type="submit" disabled={profileSaving}>{profileSaving ? (language === "tr" ? "Kaydediliyor..." : "Saving...") : (language === "tr" ? "Kaydet" : "Save")}</Button></div>
          </form> : null}

          {modal === "password" ? <form onSubmit={submitPassword} className="settings-modal-paper w-full max-w-md p-6" role="dialog" aria-modal="true" aria-labelledby="settings-modal-title">
            <h2 id="settings-modal-title" className="text-lg font-semibold text-gray-950">{language === "tr" ? "Şifreyi Değiştir" : "Change Password"}</h2>
            <p className="mt-2 text-sm leading-6 text-gray-500">{language === "tr" ? "Hesabınız için yeni bir şifre belirleyin." : "Choose a new password for your account."}</p>
            <div className="mt-6 space-y-4">
              <Input id="current-password" type="password" autoComplete="current-password" label={language === "tr" ? "Mevcut şifre" : "Current password"} value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required />
              <Input id="new-password" type="password" autoComplete="new-password" label={language === "tr" ? "Yeni şifre" : "New password"} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required />
              <Input id="new-password-again" type="password" autoComplete="new-password" label={language === "tr" ? "Yeni şifre tekrar" : "Confirm new password"} value={newPasswordAgain} onChange={(event) => setNewPasswordAgain(event.target.value)} required />
            </div>
            <p className="mt-4 rounded-xl bg-gray-50 p-3 text-sm leading-6 text-gray-600">Şifre değiştirme işlemi backend tarafından henüz desteklenmiyor.</p>
            {modalError ? <p className="mt-4 text-sm text-red-600" role="alert">{modalError}</p> : null}
            <div className="mt-6 flex justify-end gap-2"><Button variant="secondary" onClick={() => setModal(null)}>{t("cancel")}</Button><Button type="submit">{language === "tr" ? "Şifreyi Değiştir" : "Change Password"}</Button></div>
          </form> : null}

          {modal === "history" || modal === "materials" ? <div className="settings-modal-paper w-full max-w-sm p-6" role="dialog" aria-modal="true" aria-labelledby="settings-modal-title">
            <h2 id="settings-modal-title" className="text-lg font-semibold text-gray-950">{t(modalContent[modal].title)}</h2>
            <p className="mt-2 text-sm leading-6 text-gray-500">{t(modalContent[modal].description)}</p>
            <div className="mt-6 flex justify-end gap-2"><Button variant="secondary" onClick={() => setModal(null)}>{t("cancel")}</Button><Button onClick={confirmModal} className="bg-red-600 hover:bg-red-700 focus-visible:outline-red-600">{t(modalContent[modal].confirm)}</Button></div>
          </div> : null}
        </div>
      ) : null}
    </div>
  );
}
