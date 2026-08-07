"use client";

import { useState, useSyncExternalStore } from "react";
import Button from "@/components/ui/Button";
import { useLanguage } from "@/providers/LanguageProvider";
import type { TranslationKey } from "@/lib/translations";

type Theme = "light" | "dark";
type Modal = "profile" | "connect" | "history" | "materials" | null;

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
  return window.localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
}

function useTheme() {
  const theme = useSyncExternalStore(subscribeToTheme, getThemeSnapshot, (): Theme => "light");

  function setTheme(value: Theme) {
    window.localStorage.setItem(THEME_KEY, value);
    document.documentElement.classList.toggle("dark", value === "dark");
    window.dispatchEvent(new Event(THEME_EVENT));
  }

  return [theme, setTheme] as const;
}

function SettingRow({ title, description, children }: { title: string; description: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-4 py-5 first:pt-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between sm:gap-8">
      <div className="max-w-xl">
        <h3 className="text-sm font-medium text-gray-900">{title}</h3>
        <p className="mt-1 text-sm leading-6 text-gray-500">{description}</p>
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function SettingsSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="grid gap-5 border-b border-gray-200 py-8 first:pt-0 last:border-b-0 lg:grid-cols-[180px_minmax(0,1fr)] lg:gap-12" aria-labelledby={`settings-${title}`}>
      <h2 id={`settings-${title}`} className="text-sm font-semibold text-gray-950">{title}</h2>
      <div className="divide-y divide-gray-100">{children}</div>
    </section>
  );
}

function SegmentedControl<T extends string>({ value, options, onChange, label }: { value: T; options: Array<{ value: T; label: string }>; onChange: (value: T) => void; label: string }) {
  return (
    <div className="inline-flex rounded-xl bg-gray-100 p-1" role="group" aria-label={label}>
      {options.map((option) => (
        <button key={option.value} type="button" onClick={() => onChange(option.value)} aria-pressed={value === option.value} className={`rounded-lg px-3 py-1.5 text-xs font-medium transition focus-visible:outline-2 focus-visible:outline-blue-600 ${value === option.value ? "bg-white text-gray-950 shadow-sm" : "text-gray-500 hover:text-gray-900"}`}>
          {option.label}
        </button>
      ))}
    </div>
  );
}

function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (checked: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)} className={`relative h-6 w-11 rounded-full transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600 ${checked ? "bg-blue-600" : "bg-gray-300"}`}>
      <span className={`absolute top-0.5 size-5 rounded-full bg-white shadow-sm transition-transform ${checked ? "translate-x-5" : "translate-x-0.5"}`} />
    </button>
  );
}

const modalContent: Record<Exclude<Modal, null>, { title: TranslationKey; description: TranslationKey; confirm: TranslationKey }> = {
  profile: { title: "editProfile", description: "profileModalDesc", confirm: "understood" }, connect: { title: "connectAccount", description: "connectModalDesc", confirm: "understood" }, history: { title: "clearHistory", description: "confirmClearHistory", confirm: "clearHistoryButton" }, materials: { title: "clearUploads", description: "confirmClearUploads", confirm: "clearUploadsButton" },
};

export default function SettingsView() {
  const [theme, setTheme] = useTheme();
  const { language, setLanguage, t } = useLanguage();
  const [studyReminders, setStudyReminders] = useState(true);
  const [quizReminders, setQuizReminders] = useState(true);
  const [modal, setModal] = useState<Modal>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function confirmModal() {
    if (modal === "history" || modal === "materials") setNotice(t("requestConfirmed"));
    setModal(null);
  }

  return (
    <div className="mx-auto max-w-5xl px-5 py-10 sm:px-8 sm:py-14">
      <header className="animate-enter border-b border-gray-200 pb-8">
        <h1 className="text-2xl font-semibold tracking-[-0.035em] text-gray-950 sm:text-3xl">{t("settings")}</h1>
        <p className="mt-2 text-sm leading-6 text-gray-500">{t("settingsIntro")}</p>
      </header>

      <div className="animate-enter py-8 [animation-delay:40ms]">
        <SettingsSection title={t("appearance")}>
          <SettingRow title={t("theme")} description={t("themeDesc")}>
            <SegmentedControl<Theme> value={theme} onChange={setTheme} label={t("theme")} options={[{ value: "light", label: t("light") }, { value: "dark", label: t("dark") }]} />
          </SettingRow>
        </SettingsSection>

        <SettingsSection title={t("account")}>
          <SettingRow title={t("profile")} description={t("demoProfile")}>
            <Button variant="secondary" onClick={() => setModal("profile")}>{t("editProfile")}</Button>
          </SettingRow>
          <SettingRow title={t("connectAccount")} description={t("connectDesc")}>
            <Button onClick={() => setModal("connect")}>{t("createAccountLogin")}</Button>
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
            <Button variant="secondary" className="text-red-600 hover:text-red-700" onClick={() => { setNotice(null); setModal("history"); }}>{t("clearHistoryButton")}</Button>
          </SettingRow>
          <SettingRow title={t("clearUploads")} description={t("clearUploadsDesc")}>
            <Button variant="secondary" className="text-red-600 hover:text-red-700" onClick={() => { setNotice(null); setModal("materials"); }}>{t("clearUploadsButton")}</Button>
          </SettingRow>
          {notice ? <p className="pt-4 text-sm text-green-600" role="status">{notice}</p> : null}
        </SettingsSection>

        <section className="pt-8" aria-labelledby="settings-about">
          <h2 id="settings-about" className="text-sm font-semibold text-gray-950">{t("about")}</h2>
          <div className="mt-4 text-sm leading-6 text-gray-500">
            <p className="font-medium text-gray-900">StudyFlow</p>
            <p>{t("version")}</p>
            <p className="mt-2">{t("productDesc")}</p>
          </div>
        </section>
      </div>

      {modal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-gray-950/40 p-4" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) setModal(null); }}>
          <div className="w-full max-w-sm rounded-3xl bg-white p-6 shadow-xl" role="dialog" aria-modal="true" aria-labelledby="settings-modal-title">
            <h2 id="settings-modal-title" className="text-lg font-semibold text-gray-950">{t(modalContent[modal].title)}</h2>
            <p className="mt-2 text-sm leading-6 text-gray-500">{t(modalContent[modal].description)}</p>
            <div className="mt-6 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setModal(null)}>{t("cancel")}</Button>
              <Button onClick={confirmModal} className={modal === "history" || modal === "materials" ? "bg-red-600 hover:bg-red-700 focus-visible:outline-red-600" : ""}>{t(modalContent[modal].confirm)}</Button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
