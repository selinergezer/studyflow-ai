"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiErrorMessage, publicApiFetch } from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

type LoginResponse = { access_token: string; token_type: string };
type AuthMode = "login" | "register";

export default function LoginForm() {
  const router = useRouter();
  const { t, language } = useLanguage();
  const [mode, setMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    queueMicrotask(() => {
      if (localStorage.getItem("access_token")) router.replace("/dashboard");
      else setAuthChecked(true);
    });
  }, [router]);

  async function login() {
    const body = new URLSearchParams({ grant_type: "password", username: email, password });
    const data = await publicApiFetch<LoginResponse>("/users/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    localStorage.setItem("access_token", data.access_token);
    router.replace("/dashboard");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      if (mode === "register") {
        await publicApiFetch("/users/", {
          method: "POST",
          body: JSON.stringify({ username, email, password }),
        });
        setMode("login");
        setPassword("");
        setStatusMessage(language === "tr" ? "Hesabınız oluşturuldu. Şimdi giriş yapabilirsiniz." : "Your account was created. You can now sign in.");
        setIsSubmitting(false);
        return;
      }
      await login();
    } catch (cause) {
      const fallback = mode === "login" ? "Giriş yapılamadı. Bilgilerinizi kontrol edin." : "Hesap oluşturulamadı. Kullanıcı adı veya e-posta kullanımda olabilir.";
      console.error(cause);
      setError(apiErrorMessage(cause, language === "tr" ? fallback : "The operation could not be completed. Check your details.", language === "tr" ? "İşlem şu anda gerçekleştirilemiyor. Lütfen daha sonra tekrar deneyin." : "The operation is currently unavailable. Please try again later."));
      setIsSubmitting(false);
    }
  }

  if (!authChecked) return <div className="auth-paper min-h-96" />;

  return (
    <div className="auth-notebook">
      <div className="auth-punch-row" aria-hidden="true">{Array.from({ length: 6 }, (_, index) => <span key={index} />)}</div>
      <div className="auth-paper">
        <span className="auth-active-mark">AKTİF</span>
        <div className="auth-paper-content">
          <p className="auth-form-kicker">{language === "tr" ? "StudyFlow Hesabı" : "StudyFlow Account"}</p>
          <h2>{t("learningReady")}</h2>
          <p className="auth-form-description">{t("learningReadyDesc")}</p>
        </div>

        <div className="auth-tabs" role="tablist" aria-label={language === "tr" ? "Kimlik doğrulama" : "Authentication"}>
          {(["login", "register"] as const).map((item) => (
            <button key={item} type="button" role="tab" aria-selected={mode === item} onClick={() => { setMode(item); setError(null); setStatusMessage(null); }} className={mode === item ? "active" : ""}>
              {item === "login" ? (language === "tr" ? "Giriş Yap" : "Sign In") : (language === "tr" ? "Hesap Oluştur" : "Create Account")}
            </button>
          ))}
        </div>

        <form className="auth-fields" onSubmit={submit}>
          {mode === "register" ? <label className="auth-field" htmlFor="register-username"><span>{language === "tr" ? "Kullanıcı adı" : "Username"}</span><input id="register-username" autoComplete="username" required minLength={2} value={username} onChange={(event) => setUsername(event.target.value)} placeholder={language === "tr" ? "kullanıcı adın" : "your username"} /></label> : null}
          <label className="auth-field" htmlFor="auth-email"><span>{language === "tr" ? "E-posta" : "Email"}</span><input id="auth-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="ornek@email.com" /></label>
          <label className="auth-field" htmlFor="auth-password"><span>{language === "tr" ? "Şifre" : "Password"}</span><input id="auth-password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="••••••••" /></label>
          {statusMessage ? <p className="auth-form-status" role="status">{statusMessage}</p> : null}{error ? <p className="auth-form-error" role="alert">{error}</p> : null}
          <button type="submit" className="auth-submit interactive-button" disabled={isSubmitting}>
            {isSubmitting ? (language === "tr" ? "İşlem yapılıyor..." : "Please wait...") : mode === "login" ? (language === "tr" ? "Giriş Yap →" : "Sign In →") : (language === "tr" ? "Hesap Oluştur →" : "Create Account →")}
          </button>
        </form>
        <p className="auth-hand-note">{mode === "login" ? (language === "tr" ? "şifreni mi unuttun? bir dakika sürer." : "forgot your password? it only takes a minute.") : (language === "tr" ? "yeni bir çalışma sayfası aç." : "open a fresh page for learning.")}</p>
      </div>
    </div>
  );
}
