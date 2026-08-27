export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const getRequestCache = new Map<
  string,
  {
    data: unknown;
    expiresAt: number;
  }
>();

const pendingGetRequests = new Map<string, Promise<unknown>>();

// Sayfalar arasında geri/ileri giderken aynı koleksiyonları tekrar istemeyelim.
// Tüm mutation'lar aşağıda cache'i temizlediği için bu süre veri yazmalarını
// kullanıcıdan saklamaz.
const GET_CACHE_MS = 30_000;

const API_TIMING_STORAGE_KEY = "studyflow.apiTiming";

type ApiRequestSource = "network" | "cache" | "deduped";

function apiTimingEnabled() {
  return (
    process.env.NEXT_PUBLIC_API_TIMING === "true" ||
    (typeof window !== "undefined" &&
      window.localStorage.getItem(API_TIMING_STORAGE_KEY) === "true")
  );
}

function logApiTiming(
  method: string,
  path: string,
  startedAt: number,
  source: ApiRequestSource,
  status?: number,
) {
  if (!apiTimingEnabled()) return;

  const duration = Math.round((performance.now() - startedAt) * 10) / 10;
  const statusText = status == null ? "" : ` ${status}`;

  console.info(
    `[StudyFlow API] ${method} ${path}${statusText} ${duration}ms (${source})`,
  );
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public kind: "http" | "network" | "abort" = "http",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function isAbortError(cause: unknown) {
  return (
    (cause instanceof ApiError && cause.kind === "abort") ||
    (cause instanceof Error && cause.name === "AbortError")
  );
}

function isNetworkError(cause: unknown) {
  return (
    cause instanceof TypeError ||
    (cause instanceof Error &&
      /load failed|failed to fetch|networkerror|network request failed/i.test(
        cause.message,
      ))
  );
}

export function getToken() {
  return localStorage.getItem("access_token");
}

export function errorMessage(
  status: number,
  fallback?: string,
) {
  if (fallback) return fallback;

  if (status === 401) {
    return "Oturum süreniz dolmuş. Lütfen tekrar giriş yapın.";
  }

  if (status === 404) {
    return "İçerik bulunamadı.";
  }

  if (status >= 500) {
    return "İşlem sırasında bir hata oluştu.";
  }

  return "İşlem sırasında bir hata oluştu.";
}

export function apiErrorMessage(
  cause: unknown,
  fallback = "İşlem sırasında bir hata oluştu.",
  networkFallback =
    "Veriler şu anda yüklenemiyor. Lütfen daha sonra tekrar deneyin.",
) {
  if (cause instanceof ApiError) {
    return cause.kind === "network"
      ? networkFallback
      : cause.message;
  }

  if (isNetworkError(cause)) {
    return networkFallback;
  }

  return cause instanceof Error
    ? cause.message
    : fallback;
}

async function responseError(response: Response) {
  let detail: string | undefined;

  try {
    const payload = (await response.json()) as {
      detail?:
        | string
        | Array<{
            msg?: string;
          }>;
      message?: string;
    };

    detail = Array.isArray(payload.detail)
      ? payload.detail
          .map((item) => item.msg)
          .filter(Boolean)
          .join(" ")
      : payload.detail ?? payload.message;
  } catch {}

  return new ApiError(
    response.status,
    errorMessage(response.status, detail),
  );
}

async function safeFetch(
  path: string,
  init: RequestInit,
) {
  try {
    return await fetch(`${API_URL}${path}`, init);
  } catch (cause) {
    if (isAbortError(cause)) {
      throw new ApiError(
        0,
        "Request aborted",
        "abort",
      );
    }

    if (isNetworkError(cause)) {
      throw new ApiError(
        0,
        "Network request failed",
        "network",
      );
    }

    throw cause;
  }
}

export async function publicApiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const startedAt = performance.now();
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);

  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !(init.body instanceof URLSearchParams) &&
    !headers.has("Content-Type")
  ) {
    headers.set(
      "Content-Type",
      "application/json",
    );
  }

  let response: Response;

  try {
    response = await safeFetch(path, {
      ...init,
      headers,
    });
  } catch (cause) {
    logApiTiming(method, path, startedAt, "network");
    throw cause;
  }

  if (!response.ok) {
    const error = await responseError(response);
    logApiTiming(method, path, startedAt, "network", response.status);
    throw error;
  }

  const data = (await response.json()) as T;
  logApiTiming(method, path, startedAt, "network", response.status);
  return data;
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = getToken();

  if (!token) {
    throw new ApiError(
      401,
      errorMessage(401),
    );
  }

  const method = (
    init.method ?? "GET"
  ).toUpperCase();

  const headers = new Headers(init.headers);

  headers.set(
    "Authorization",
    `Bearer ${token}`,
  );

  if (
    init.body &&
    !(init.body instanceof FormData) &&
    !headers.has("Content-Type")
  ) {
    headers.set(
      "Content-Type",
      "application/json",
    );
  }

  // =====================================================
  // GET REQUEST CACHE + DEDUPLICATION
  // =====================================================

  if (method === "GET") {
    const cacheKey = `${token}:${path}`;
    const startedAt = performance.now();

    const cached =
      getRequestCache.get(cacheKey);

    if (
      cached &&
      cached.expiresAt > Date.now()
    ) {
      logApiTiming(method, path, startedAt, "cache");
      return cached.data as T;
    }

    const existingRequest =
      pendingGetRequests.get(cacheKey);

    if (existingRequest) {
      try {
        return (await existingRequest) as T;
      } finally {
        logApiTiming(method, path, startedAt, "deduped");
      }
    }

    /*
     * Aynı GET isteği birden fazla component tarafından
     * çağrılırsa ortak request kullanıyoruz.
     *
     * Bu yüzden burada AbortSignal'i ortak request'e
     * aktarmıyoruz. Bir component unmount olduğunda
     * diğer component'in isteğini iptal etmesin.
     */
    const requestInit = { ...init };
    delete requestInit.signal;

    const request = (async () => {
      let response: Response;

      try {
        response = await safeFetch(path, {
          ...requestInit,
          method,
          headers,
        });
      } catch (cause) {
        logApiTiming(method, path, startedAt, "network");
        throw cause;
      }

      if (!response.ok) {
        const error =
          await responseError(response);

        logApiTiming(method, path, startedAt, "network", response.status);

        if (response.status === 401) {
          localStorage.removeItem(
            "access_token",
          );

          getRequestCache.clear();
          pendingGetRequests.clear();

          window.dispatchEvent(
            new Event(
              "studyflow-auth-expired",
            ),
          );
        }

        throw error;
      }

      const data =
        (await response.json()) as T;

      logApiTiming(method, path, startedAt, "network", response.status);

      getRequestCache.set(
        cacheKey,
        {
          data,
          expiresAt:
            Date.now() + GET_CACHE_MS,
        },
      );

      return data;
    })();

    pendingGetRequests.set(
      cacheKey,
      request,
    );

    try {
      return await request;
    } finally {
      pendingGetRequests.delete(
        cacheKey,
      );
    }
  }

  // =====================================================
  // POST / PUT / PATCH / DELETE
  // =====================================================

  const startedAt = performance.now();
  let response: Response;

  try {
    response = await safeFetch(path, {
      ...init,
      method,
      headers,
    });
  } catch (cause) {
    logApiTiming(method, path, startedAt, "network");
    throw cause;
  }

  if (!response.ok) {
    const error =
      await responseError(response);

    logApiTiming(method, path, startedAt, "network", response.status);

    if (response.status === 401) {
      localStorage.removeItem(
        "access_token",
      );

      getRequestCache.clear();
      pendingGetRequests.clear();

      window.dispatchEvent(
        new Event(
          "studyflow-auth-expired",
        ),
      );
    }

    throw error;
  }

  /*
   * Veri değiştiren bir işlem yaptıysak
   * eski GET sonuçlarını kullanmayalım.
   */
  getRequestCache.clear();

if (response.status === 204) {
  logApiTiming(method, path, startedAt, "network", response.status);
  return undefined as T;
}

const data = (await response.json()) as T;
logApiTiming(method, path, startedAt, "network", response.status);
return data;
}

export type Course = {
  id: number;
  name: string;
  description: string | null;
};

export type CurrentUser = {
  id: number;
  username: string;
  email: string;
};

export async function getCurrentUser(): Promise<CurrentUser> {
  return apiFetch<CurrentUser>("/users/me");
}

export type DocumentData = {
  id?: number;
  document_id?: number;
  filename: string;
  page_count: number;
  summary: string;
  course_id: number;
  uploaded_at?: string;
};

export type QuizQuestion = {
  id: number;
  question_type:
    | "multiple_choice"
    | "true_false"
    | "classic";
  question_text: string;
  option_a?: string | null;
  option_b?: string | null;
  option_c?: string | null;
  option_d?: string | null;
  option_e?: string | null;
};

export type Quiz = {
  id?: number;
  quiz_id?: number;
  title: string;
  course_id?: number;
  document_id: number;
  question_count?: number;
  questions?: QuizQuestion[];
  created_at?: string;
};

export type Flashcard = {
  id: number;
  question: string;
  answer: string;
  course_id: number;
  document_id: number | null;
  batch_id: string | null;
  created_at?: string;
};

export async function deleteCourseApi(
  courseId: number,
): Promise<void> {
  await apiFetch<void>(`/courses/${courseId}`, {
    method: "DELETE",
  });
}

export async function deleteQuizApi(
  quizId: number,
): Promise<void> {
  await apiFetch<void>(`/quizzes/${quizId}`, {
    method: "DELETE",
  });
}

export type StudyRoom = {
  id: number;
  name: string;
  code: string;
  course_id: number;
  created_by: number;
  is_active: boolean;
  created_at: string;
};

export type StudyRoomMember = {
  user_id: number;
  username: string;
  status: "studying" | "idle" | "offline";
  joined_at: string;
  study_started_at: string | null;
};

export type StudyRoomStats = {
  room_id: number;
  today_minutes: number;
  total_minutes: number;
  member_count: number;
  currently_studying: number;
};

export type StudyRoomStartResponse = {
  message: string;
  room_id: number;
  status: "studying";
  study_started_at: string;
};

export type StudyRoomFinishResponse = {
  message: string;
  room_id: number;
  duration_minutes: number;
  status: "idle";
  study_session_id: number;
};

export async function getMyStudyRooms(): Promise<StudyRoom[]> {
  return apiFetch<StudyRoom[]>("/study-rooms/");
}

export async function getStudyRoomMembers(
  roomId: number,
): Promise<StudyRoomMember[]> {
  return apiFetch<StudyRoomMember[]>(
    `/study-rooms/${roomId}/members`,
  );
}

export async function getStudyRoomStats(
  roomId: number,
): Promise<StudyRoomStats> {
  return apiFetch<StudyRoomStats>(
    `/study-rooms/${roomId}/stats`,
  );
}

export async function startStudyRoom(
  roomId: number,
): Promise<StudyRoomStartResponse> {
  return apiFetch<StudyRoomStartResponse>(
    `/study-rooms/${roomId}/start`,
    {
      method: "POST",
    },
  );
}

export async function finishStudyRoom(
  roomId: number,
): Promise<StudyRoomFinishResponse> {
  return apiFetch<StudyRoomFinishResponse>(
    `/study-rooms/${roomId}/finish`,
    {
      method: "POST",
    },
  );
}

export async function createStudyRoom(
  name: string,
  courseId: number,
): Promise<StudyRoom> {
  return apiFetch<StudyRoom>("/study-rooms/", {
    method: "POST",
    body: JSON.stringify({
      name,
      course_id: courseId,
    }),
  });
}

export async function joinStudyRoom(
  code: string,
): Promise<StudyRoom> {
  return apiFetch<StudyRoom>("/study-rooms/join", {
    method: "POST",
    body: JSON.stringify({
      code,
    }),
  });
}

export async function getCourses(): Promise<Course[]> {
  return apiFetch<Course[]>("/courses/");
}

export async function deleteStudyRoomApi(
  roomId: number,
): Promise<void> {
  await apiFetch<void>(`/study-rooms/${roomId}`, {
    method: "DELETE",
  });
}

export type StudyRoomMessage = {
  id: number;
  room_id: number;
  user_id: number;
  username: string;
  message: string;
  material_type: "document" | "quiz" | "flashcard" | null;
  material_id: number | null;
  created_at: string;
};
export async function getDocuments(): Promise<DocumentData[]> {
  return apiFetch<DocumentData[]>("/documents/");
}

export async function getQuizzes(): Promise<Quiz[]> {
  return apiFetch<Quiz[]>("/quizzes/");
}

export async function getFlashcards(): Promise<Flashcard[]> {
  return apiFetch<Flashcard[]>("/flashcards/");
}
export async function getStudyRoomMessages(
  roomId: number,
): Promise<StudyRoomMessage[]> {
  return apiFetch<StudyRoomMessage[]>(
    `/study-rooms/${roomId}/messages`,
  );
}

export async function sendStudyRoomMessage(
  roomId: number,
  message: string,
  materialType?: "document" | "quiz" | "flashcard",
  materialId?: number,
): Promise<StudyRoomMessage> {
  return apiFetch<StudyRoomMessage>(
    `/study-rooms/${roomId}/messages`,
    {
      method: "POST",
      body: JSON.stringify({
        message,
        material_type: materialType ?? null,
        material_id: materialId ?? null,
      }),
    },
  );
}

export async function clearStudyHistory(): Promise<void> {
  await apiFetch<void>("/study-sessions/clear", {
    method: "DELETE",
  });
}

export async function clearUploadedContent(): Promise<void> {
  await apiFetch<void>("/documents/clear", {
    method: "DELETE",
  });
}
