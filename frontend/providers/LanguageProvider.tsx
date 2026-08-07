"use client";

import { createContext, useContext, useSyncExternalStore, type ReactNode } from "react";
import { translations, type Language, type TranslationKey } from "@/lib/translations";

const LANGUAGE_KEY = "studyflow.language";
const LANGUAGE_EVENT = "studyflow-language-change";

type LanguageContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (key: TranslationKey, variables?: Record<string, string | number>) => string;
};

const LanguageContext = createContext<LanguageContextValue | null>(null);

function subscribe(callback: () => void) {
  window.addEventListener(LANGUAGE_EVENT, callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener(LANGUAGE_EVENT, callback);
    window.removeEventListener("storage", callback);
  };
}

function getSnapshot(): Language {
  return window.localStorage.getItem(LANGUAGE_KEY) === "en" ? "en" : "tr";
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const language = useSyncExternalStore(subscribe, getSnapshot, (): Language => "tr");

  function setLanguage(value: Language) {
    window.localStorage.setItem(LANGUAGE_KEY, value);
    document.documentElement.lang = value;
    window.dispatchEvent(new Event(LANGUAGE_EVENT));
  }

  function t(key: TranslationKey, variables: Record<string, string | number> = {}) {
    let value: string = translations[language][key];
    for (const [name, replacement] of Object.entries(variables)) value = value.replaceAll(`{${name}}`, String(replacement));
    return value;
  }

  return <LanguageContext.Provider value={{ language, setLanguage, t }}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const context = useContext(LanguageContext);
  if (!context) throw new Error("useLanguage must be used within LanguageProvider");
  return context;
}
