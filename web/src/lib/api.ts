import type { Snapshot } from "../types/live";

/** トークンは、Python が画面を配信する時だけ HTML に埋め込む（他のサイトは読めない）。 */
const token = (): string =>
  document.querySelector('meta[name="lipvoice-token"]')?.getAttribute("content") ??
  (import.meta.env.VITE_LIPVOICE_TOKEN as string | undefined) ??
  "";

export class ApiError extends Error {}

async function raw(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(path, {
    ...init,
    headers: { "X-LipVoice-Token": token(), ...(init.body ? { "Content-Type": "application/json" } : {}), ...init.headers },
  });
  if (!res.ok) {
    let detail = `エラー ${res.status}`;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* 本文が JSON でない */
    }
    throw new ApiError(detail);
  }
  return res;
}

const json = async <T>(path: string, init?: RequestInit): Promise<T> => (await raw(path, init)).json();
const post = <T>(path: string, body?: unknown) =>
  json<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  start: () => post("/api/collect/start"),
  save: () => post("/api/collect/save"),
  discard: () => post("/api/collect/discard"),
  newSession: () => post("/api/collect/session"),
  setMode: (mode: "phrase" | "negative", negative_label?: string) => post("/api/collect/mode", { mode, negative_label }),
  preview: (full: boolean) => post("/api/preview", { full }),
  settings: <T>() => json<T>("/api/settings"),
  putSettings: <T>(changes: Record<string, unknown>) => json<T>("/api/settings", { method: "PUT", body: JSON.stringify(changes) }),
  pendingVideo: async (): Promise<Blob> => (await raw("/api/collect/pending/video")).blob(),
};

/** Server-Sent Events を fetch で読む（EventSource は独自ヘッダを付けられないため）。 */
export async function streamEvents(onSnapshot: (s: Snapshot) => void, signal: AbortSignal): Promise<void> {
  const res = await raw("/api/events", { signal });
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) return;
    buf += decoder.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const line = buf.slice(0, i).split("\n").find((l) => l.startsWith("data: "));
      buf = buf.slice(i + 2);
      if (line) onSnapshot(JSON.parse(line.slice(6)));
    }
  }
}
