"use client";

import { FormEvent, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { publicApiFetch } from "@/lib/api";

export default function ResetPasswordForm() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const token = searchParams.get("token");

  const [password, setPassword] = useState("");
  const [passwordAgain, setPasswordAgain] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (isSubmitting) return;

    setError(null);
    setMessage(null);

    if (!token) {
      setError("Geçersiz şifre sıfırlama bağlantısı.");
      return;
    }

    if (password.length < 8) {
      setError("Şifre en az 8 karakter olmalıdır.");
      return;
    }

    if (password !== passwordAgain) {
      setError("Şifreler birbiriyle eşleşmiyor.");
      return;
    }

    setIsSubmitting(true);

    try {
      const params = new URLSearchParams({
        token,
        new_password: password,
      });

      const data = await publicApiFetch<{ message: string }>(
        `/users/reset-password?${params.toString()}`,
        {
          method: "POST",
        },
      );

      setMessage(data.message);
      setPassword("");
      setPasswordAgain("");

      setTimeout(() => {
        router.replace("/login");
      }, 1500);
    } catch {
      setError(
        "Şifre sıfırlanamadı. Bağlantının süresi dolmuş veya artık kullanılamıyor olabilir.",
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

          <h2>Yeni şifreni belirle.</h2>

          <p className="auth-form-description">
            Yeni şifreni oluştur. Ardından hesabına yeni şifrenle giriş
            yapabilirsin.
          </p>
        </div>

        <form className="auth-fields" onSubmit={submit}>
          <label className="auth-field" htmlFor="new-password">
            <span>YENİ ŞİFRE</span>

            <input
              id="new-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              autoFocus
            />
          </label>

          <label className="auth-field" htmlFor="new-password-again">
            <span>YENİ ŞİFRE TEKRAR</span>

            <input
              id="new-password-again"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={passwordAgain}
              onChange={(event) => setPasswordAgain(event.target.value)}
              placeholder="••••••••"
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
            {isSubmitting ? "Kaydediliyor..." : "Şifreyi yenile →"}
          </button>
        </form>

        <p className="auth-hand-note">
          Şifreni yeniledikten sonra giriş sayfasına yönlendirileceksin.
        </p>
      </div>
    </div>
  );
}