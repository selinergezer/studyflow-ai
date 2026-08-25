"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ApiError,
  apiErrorMessage,
  apiFetch,
  publicApiFetch,
} from "@/lib/api";
import { useLanguage } from "@/providers/LanguageProvider";

type LoginResponse = { access_token: string; token_type: string };
type AuthMode = "login" | "register" | "verify";

function requiresEmailVerification(cause: unknown) {
  if (!(cause instanceof ApiError) || cause.status !== 403) return false;

  const message = cause.message.toLocaleLowerCase("tr-TR");
  return (
    (message.includes("e-posta") && message.includes("doğrula")) ||
    (message.includes("email") && message.includes("verif"))
  );
}

export default function LoginForm() {
  const router = useRouter();
  const { t } = useLanguage();
  const [mode, setMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [verificationCode, setVerificationCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  useEffect(() => {
    queueMicrotask(() => {
      if (localStorage.getItem("access_token")) router.replace("/dashboard");
      else setAuthChecked(true);
    });
  }, [router]);

  function changeMode(nextMode: Exclude<AuthMode, "verify">) {
    if (isSubmitting || isResending) return;
    setMode(nextMode);
    setError(null);
    setStatusMessage(null);
    setVerificationCode("");
  }

  function showRequestError(cause: unknown) {
    setError(
      apiErrorMessage(
        cause,
        t("authOperationUnavailable"),
        t("authOperationUnavailable"),
      ),
    );
  }

  async function login() {
    const body = new URLSearchParams({
      grant_type: "password",
      username: email.trim(),
      password,
    });
    const data = await publicApiFetch<LoginResponse>("/users/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body,
    });
    localStorage.setItem("access_token", data.access_token);

    // Route bundle hazırlanırken dashboard/layout verilerini paralel başlat.
    // İlgili component'ler mount olduğunda apiFetch aynı pending request'leri
    // paylaşır; burada ek ağ çağrısı oluşmaz.
    void Promise.allSettled([
      apiFetch("/users/me"),
      apiFetch("/notifications/unread-count"),
      apiFetch("/courses/"),
      apiFetch("/documents/"),
      apiFetch("/study-sessions/"),
    ]);

    router.replace("/dashboard");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (isSubmitting || isResending) return;

    setIsSubmitting(true);
    setError(null);
    setStatusMessage(null);

    try {
      if (mode === "register") {
        await publicApiFetch("/users/", {
          method: "POST",
          body: JSON.stringify({
            username: username.trim(),
            email: email.trim(),
            password,
          }),
        });
        setPassword("");
        setVerificationCode("");
        setMode("verify");
        setStatusMessage(t("verificationCodeSent"));
        return;
      }

      if (mode === "verify") {
        await publicApiFetch("/users/verify-email", {
          method: "POST",
          body: JSON.stringify({
            email: email.trim(),
            code: verificationCode.trim(),
          }),
        });
        setVerificationCode("");
        setMode("login");
        setStatusMessage(t("emailVerifiedSuccess"));
        return;
      }

      await login();
    } catch (cause) {
      if (mode === "login" && requiresEmailVerification(cause)) {
        setPassword("");
        setVerificationCode("");
        setMode("verify");
        setError(cause instanceof ApiError ? cause.message : null);
      } else {
        showRequestError(cause);
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  async function resendVerification() {
    if (isSubmitting || isResending) return;

    setIsResending(true);
    setError(null);
    setStatusMessage(null);

    try {
      await publicApiFetch("/users/resend-verification", {
        method: "POST",
        body: JSON.stringify({ email: email.trim() }),
      });
      setStatusMessage(t("verificationCodeResent"));
    } catch (cause) {
      showRequestError(cause);
    } finally {
      setIsResending(false);
    }
  }

  if (!authChecked) return <div className="auth-paper min-h-96" />;

  const verificationMode = mode === "verify";

  return (
    <div className="auth-notebook">
      <div className="auth-punch-row" aria-hidden="true">
        {Array.from({ length: 5 }, (_, index) => <span key={index} />)}
      </div>
      <div className="auth-paper">
        <span className="auth-active-mark">{t("authOpen")}</span>
        <div className="auth-paper-content">
          <p className="auth-form-kicker">{t("studyflowAccount")}</p>
          <h2>{verificationMode ? t("emailVerification") : t("learningReady")}</h2>
          <p className="auth-form-description">
            {verificationMode ? t("emailVerificationDescription") : t("learningReadyDesc")}
          </p>
        </div>

        <div className="auth-tabs" role="tablist" aria-label={t("authentication")}>
          {(["login", "register"] as const).map((item) => (
            <button
              key={item}
              type="button"
              role="tab"
              aria-selected={mode === item || (item === "register" && verificationMode)}
              onClick={() => changeMode(item)}
              className={mode === item || (item === "register" && verificationMode) ? "active" : ""}
              disabled={isSubmitting || isResending}
            >
              {item === "login" ? t("signIn") : t("createAccount")}
            </button>
          ))}
        </div>

        <form className="auth-fields" onSubmit={submit}>
          {verificationMode ? (
            <>
              <p className="auth-verification-email">{t("verificationSentTo")} <strong>{email}</strong></p>
              <label className="auth-field" htmlFor="verification-code">
                <span>{t("verificationCode")}</span>
                <input
                  id="verification-code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  required
                  value={verificationCode}
                  onChange={(event) => setVerificationCode(event.target.value)}
                  placeholder={t("verificationCodePlaceholder")}
                  autoFocus
                />
              </label>
            </>
          ) : (
            <>
              {mode === "register" ? (
                <label className="auth-field" htmlFor="register-username">
                  <span>{t("username")}</span>
                  <input id="register-username" autoComplete="username" required minLength={2} value={username} onChange={(event) => setUsername(event.target.value)} placeholder={t("usernamePlaceholder")} />
                </label>
              ) : null}
              <label className="auth-field" htmlFor="auth-email">
                <span>{t("email")}</span>
                <input id="auth-email" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="ornek@email.com" />
              </label>
              <label className="auth-field" htmlFor="auth-password">
                <span>{t("password")}</span>
                <input id="auth-password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="••••••••" />
              </label>
            </>
          )}

          {statusMessage ? <p className="auth-form-status" role="status">{statusMessage}</p> : null}
          {error ? <p className="auth-form-error" role="alert">{error}</p> : null}

          <button type="submit" className="auth-submit interactive-button" disabled={isSubmitting || isResending}>
            {isSubmitting ? t("authProcessing") : verificationMode ? t("verifyEmailButton") : mode === "login" ? t("signInButton") : t("createAccountButton")}
          </button>

          {verificationMode ? (
            <button type="button" className="auth-resend-button" onClick={resendVerification} disabled={isSubmitting || isResending}>
              {isResending ? t("resendingCode") : t("resendCode")}
            </button>
          ) : null}
        </form>
        {verificationMode ? (
  <p className="auth-hand-note">
    {t("verificationHandNote")}
  </p>
) : mode === "login" ? (
  <p className="auth-hand-note">
    <button
      type="button"
      className="auth-forgot-password"
      onClick={() => router.push("/forgot-password")}
    >
      {t("forgotPasswordNote")}
    </button>
  </p>
) : (
  <p className="auth-hand-note">
    {t("registerHandNote")}
  </p>
)}
      </div>
    </div>
  );
}
