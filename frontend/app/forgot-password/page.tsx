import type { Metadata } from "next";
import AuthLayout from "@/components/auth/AuthLayout";
import ForgotPasswordForm from "@/components/auth/ForgotPasswordForm";

export const metadata: Metadata = {
  title: "Şifremi Unuttum",
  description: "StudyFlow AI şifre sıfırlama",
};

export default function ForgotPasswordPage() {
  return (
    <AuthLayout>
      <ForgotPasswordForm />
    </AuthLayout>
  );
}