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
  if (fallback) return fallback;
  if (status === 401) return "Oturum süreniz dolmuş. Lütfen tekrar giriş yapın.";
  if (status === 404) return "İçerik bulunamadı.";
  if (status >= 500) return "İşlem sırasında bir hata oluştu.";
  return "İşlem sırasında bir hata oluştu.";
}

export function apiErrorMessage(cause: unknown, fallback = "İşlem sırasında bir hata oluştu.", networkFallback = "Veriler şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin.") {
  if (cause instanceof ApiError) return cause.message;
  if (cause instanceof TypeError || (cause instanceof Error && /load failed|failed to fetch|networkerror/i.test(cause.message))) {
    return networkFallback;
  }
  return cause instanceof Error ? cause.message : fallback;
}

async function responseError(response: Response) {
  let detail: string | undefined;
  try {
    const payload = await response.json() as { detail?: string | Array<{ msg?: string }>; message?: string };
    detail = Array.isArray(payload.detail)
      ? payload.detail.map((item) => item.msg).filter(Boolean).join(" ")
      : payload.detail ?? payload.message;
  } catch {}
  return new ApiError(response.status, errorMessage(response.status, detail));
}

export async function publicApiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !(init.body instanceof URLSearchParams) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`${API_URL}${path}`, { ...init, headers });
  if (!response.ok) throw await responseError(response);
  return response.json() as Promise<T>;
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
export type CurrentUser = { id: number; username: string; email: string };
export type DocumentData = { id?: number; document_id?: number; filename: string; page_count: number; summary: string; course_id: number; uploaded_at?: string };
export type QuizQuestion = { id: number; question_type: "multiple_choice" | "true_false" | "classic"; question_text: string; option_a?: string | null; option_b?: string | null; option_c?: string | null; option_d?: string | null; option_e?: string | null };
export type Quiz = { id?: number; quiz_id?: number; title: string; course_id?: number; document_id: number; question_count?: number; questions?: QuizQuestion[]; created_at?: string };
export type Flashcard = { id: number; question: string; answer: string; course_id: number; document_id: number | null; created_at?: string };
