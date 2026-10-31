export type PlateFormat = "standard" | "bh";
export type Source = "upload" | "camera";
export type ImageStatus =
  | "ok"
  | "no_plate"
  | "unreadable"
  | "invalid_format"
  | "bad_image"
  | "unsupported_type"
  | "too_large"
  | "error";

export interface Box {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

export interface Plate {
  box: Box;
  text: string;
  raw_text: string;
  det_conf: number;
  ocr_conf: number;
  valid: boolean;
  needs_review: boolean;
  format: PlateFormat | null;
  crop: string;
}

export interface ImageResult {
  filename: string;
  status: ImageStatus;
  message: string | null;
  width: number | null;
  height: number | null;
  plates: Plate[];
  processing_ms: number;
}

export interface DetectResponse {
  results: ImageResult[];
  total_ms: number;
}

export interface LogEntry {
  plate: string;
  timestamp: string;
  source: string;
  det_conf: number | null;
  ocr_conf: number | null;
  format: string | null;
}

export interface LogList {
  items: LogEntry[];
  total: number;
}

export interface ComponentStatus {
  ok: boolean;
  error: string | null;
}

export interface Health {
  status: "ok" | "degraded";
  model: ComponentStatus;
  sheets: ComponentStatus;
}

export class ApiError extends Error {
  constructor(
    public code: string,
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const BASE = import.meta.env.VITE_API_URL ?? "";

function statusMessage(status: number): string {
  if (status === 413) return "Upload is too big. Try fewer or smaller images.";
  if (status === 502 || status === 503 || status === 504)
    return "The server is unavailable right now. Try again in a moment.";
  return "Something went wrong. Please try again.";
}

export function isAbort(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, init);
  } catch (e) {
    if (isAbort(e)) throw e;
    throw new ApiError("NETWORK", 0, "Can't reach the server. Check that the backend is running and try again.");
  }

  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // not JSON (e.g. a proxy error page), handled below
  }

  if (!res.ok) {
    const err = (body as { error?: { code?: string; message?: string } } | null)?.error;
    throw new ApiError(err?.code ?? `HTTP_${res.status}`, res.status, err?.message ?? statusMessage(res.status));
  }
  if (body === null) {
    throw new ApiError("BAD_RESPONSE", res.status, "The server sent an unexpected response.");
  }
  return body as T;
}

export const api = {
  health: (signal?: AbortSignal) => request<Health>("/api/health", { signal }),

  detect(files: File[], signal?: AbortSignal) {
    const form = new FormData();
    files.forEach((f) => form.append("files", f, f.name));
    return request<DetectResponse>("/api/detect", { method: "POST", body: form, signal });
  },

  saveLog: (body: { plate: string; source: Source; det_conf?: number; ocr_conf?: number }) =>
    request<LogEntry>("/api/logs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  logs(params: { q?: string; format?: string; source?: string; limit?: number }, signal?: AbortSignal) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== "") qs.set(k, String(v));
    });
    return request<LogList>(`/api/logs?${qs}`, { signal });
  },
};
