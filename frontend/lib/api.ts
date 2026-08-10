export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function getToken() {
  return localStorage.getItem("access_token");
}

export function errorMessage(status: number, fallback?: string) {
  if (status === 401) return "Oturum süreniz dolmuş. Lütfen tekrar giriş yapın.";
  if (status === 404) return "İçerik bulunamadı.";
  if (status >= 500) return "İşlem sırasında bir hata oluştu.";
  return fallback || "İşlem sırasında bir hata oluştu.";
}

async function responseError(response: Response) {
  let detail: string | undefined;
  try {
    const payload = await response.json() as { detail?: string; message?: string };
    detail = payload.detail ?? payload.message;
  } catch {}
  return new ApiError(response.status, errorMessage(response.status, detail));
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  if (!token) throw new ApiError(401, errorMessage(401));
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) {
    const error = await responseError(response);
    if (response.status === 401) {
      localStorage.removeItem("access_token");
      window.dispatchEvent(new Event("studyflow-auth-expired"));
    }
    throw error;
  }
  return response.json() as Promise<T>;
}

export type Course = { id: number; name: string; description: string | null };
export type DocumentData = { id?: number; document_id?: number; filename: string; page_count: number; summary: string; course_id: number; uploaded_at?: string };
export type QuizQuestion = { id: number; question_type: "multiple_choice"; question_text: string; option_a: string; option_b: string; option_c: string; option_d: string; option_e: string };
export type Quiz = { id?: number; quiz_id?: number; title: string; course_id?: number; document_id: number; question_count?: number; questions?: QuizQuestion[]; created_at?: string };
export type Flashcard = { id: number; question: string; answer: string; course_id: number; document_id: number | null; created_at?: string };
