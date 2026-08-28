import type { Metadata } from "next";
import { Suspense } from "react";
import AuthLayout from "@/components/auth/AuthLayout";
import ResetPasswordForm from "@/components/auth/ResetPasswordForm";

export const metadata: Metadata = {
  title: "Şifreyi Yenile",
  description: "StudyFlow AI şifreni yenile.",
};

export default function ResetPasswordPage() {
  return (
    <AuthLayout>
      <Suspense fallback={<div className="auth-paper min-h-96" />}>
        <ResetPasswordForm />
      </Suspense>
    </AuthLayout>
  );
}