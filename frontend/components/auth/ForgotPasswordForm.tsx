"use client";

import { FormEvent, useState } from "react";
import { publicApiFetch } from "@/lib/api";

export default function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSubmitting) return;

    setIsSubmitting(true);
    setMessage(null);
    setError(null);

    try {
      const data = await publicApiFetch<{ message: string }>(
        `/users/forgot-password?email=${encodeURIComponent(email.trim())}`,
        {
          method: "POST",
        },
      );

      setMessage(data.message);
    } catch {
      setError(
        "İşlem sırasında bir hata oluştu. Lütfen tekrar deneyin.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="auth-notebook">
      <div className="auth-punch-row" aria-hidden="true">
        {Array.from({ length: 5 }, (_, index) => (
          <span key={index} />
        ))}
      </div>

      <div className="auth-paper">
        <span className="auth-active-mark">AÇIK</span>

        <div className="auth-paper-content">
          <p className="auth-form-kicker">STUDYFLOW HESABI</p>

          <h2>Şifreni mi unuttun?</h2>

          <p className="auth-form-description">
            Hesabına kayıtlı e-posta adresini gir. Sana şifreni
            sıfırlayabileceğin bir bağlantı gönderelim.
          </p>
        </div>

        <form className="auth-fields" onSubmit={submit}>
          <label className="auth-field" htmlFor="forgot-password-email">
            <span>E-POSTA</span>

            <input
              id="forgot-password-email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="ornek@email.com"
              autoFocus
            />
          </label>

          {message ? (
            <p className="auth-form-status" role="status">
              {message}
            </p>
          ) : null}

          {error ? (
            <p className="auth-form-error" role="alert">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            className="auth-submit interactive-button"
            disabled={isSubmitting}
          >
            {isSubmitting
              ? "Gönderiliyor..."
              : "Sıfırlama bağlantısı gönder →"}
          </button>
        </form>

        <p className="auth-hand-note">
          E-posta adresini hatırladın mı? Giriş sayfasına dön.
        </p>
      </div>
    </div>
  );
}