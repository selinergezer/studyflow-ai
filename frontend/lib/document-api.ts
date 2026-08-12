export type DocumentData = {
  document_id: number;
  filename: string;
  page_count: number;
  summary: string;
};

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const LAST_DOCUMENT_KEY = "lastDocument";

export function getAccessToken() {
  return localStorage.getItem("access_token") ?? localStorage.getItem("accessToken");
}

export function getApiErrorMessage(status: number) {
  if (status === 401) return "Oturum süreniz dolmuş. Tekrar giriş yapın.";
  if (status === 404) return "Ders bulunamadı.";
  return "PDF analiz edilirken bir hata oluştu.";
}

export function saveDocument(document: DocumentData) {
  localStorage.setItem(LAST_DOCUMENT_KEY, JSON.stringify(document));
}

export function readDocument(documentId: string): DocumentData | null {
  const value = localStorage.getItem(LAST_DOCUMENT_KEY);
  if (!value) return null;
  try {
    const document = JSON.parse(value) as DocumentData;
    return String(document.document_id) === documentId ? document : null;
  } catch {
    return null;
  }
}
