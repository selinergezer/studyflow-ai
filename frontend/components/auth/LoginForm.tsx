"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Button from "@/components/ui/Button";
import Card from "@/components/ui/Card";
import Input from "@/components/ui/Input";
import { useLanguage } from "@/providers/LanguageProvider";

type LoginResponse = {
  access_token: string;
  token_type: string;
};

type ErrorResponse = {
  detail?: string | Array<{ msg?: string }>;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function getErrorMessage(payload: ErrorResponse) {
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail.map((item) => item.msg).filter(Boolean).join(" ");
  }
  return "Giriş yapılamadı. Lütfen bilgilerinizi kontrol edin.";
}

export default function LoginForm() {
  const router = useRouter();
  const { t, language } = useLanguage();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    queueMicrotask(() => {
      if (localStorage.getItem("access_token")) {
        router.replace("/dashboard");
        return;
      }
      setAuthChecked(true);
    });
  }, [router]);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);

    const body = new URLSearchParams();
    body.append("grant_type", "password");
    body.append("username", email);
    body.append("password", password);

    try {
      const response = await fetch(`${API_URL}/users/login`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body,
      });
      const data = await response.json() as LoginResponse | ErrorResponse;

      if (!response.ok) throw new Error(getErrorMessage(data as ErrorResponse));
      const loginData = data as LoginResponse;
      localStorage.setItem("access_token", loginData.access_token);
      router.replace("/dashboard");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Giriş yapılamadı. Lütfen bilgilerinizi kontrol edin.");
      setIsSubmitting(false);
    }
  }

  if (!authChecked) return <Card className="min-h-80 p-6 sm:p-8 lg:p-9" />;

  return (
    <Card className="p-6 sm:p-8 lg:p-9">
      <div className="flex size-11 items-center justify-center rounded-2xl bg-blue-50 text-blue-600" aria-hidden="true">
        <svg className="size-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M5 4.5h10.5A2.5 2.5 0 0 1 18 7v12.5H7.5A2.5 2.5 0 0 1 5 17V4.5Z" /><path d="M5 17a2.5 2.5 0 0 1 2.5-2.5H18M9 8h5" /></svg>
      </div>

      <div className="mt-7">
        <h2 className="text-2xl font-semibold tracking-[-0.03em] text-gray-950 sm:text-[28px]">{t("learningReady")}</h2>
        <p className="mt-3 max-w-sm text-sm leading-6 text-gray-500">{t("learningReadyDesc")}</p>
      </div>

      <form className="mt-8 space-y-5" onSubmit={submitLogin}>
        <Input id="login-email" label={language === "tr" ? "E-posta" : "Email"} type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} />
        <Input id="login-password" label={language === "tr" ? "Şifre" : "Password"} type="password" autoComplete="current-password" required minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} />
        {error ? <p className="text-sm text-red-600" role="alert">{error}</p> : null}
        <Button type="submit" fullWidth className="h-12" disabled={isSubmitting}>
          {isSubmitting ? (language === "tr" ? "Giriş yapılıyor..." : "Signing in...") : (language === "tr" ? "Giriş Yap" : "Sign In")}
        </Button>
      </form>
    </Card>
  );
}
