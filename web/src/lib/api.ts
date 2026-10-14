import type { ClipStats, RecordedClip } from "../types/clip";
import type { Phrase } from "../types/phrase";
import { getIdToken } from "./auth";

const BASE = import.meta.env.VITE_API_BASE_URL as string;

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await getIdToken();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...init.headers, Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error(`API エラー ${res.status}`);
  return res;
}

export async function getPhrases(): Promise<Phrase[]> {
  const res = await request("/phrases");
  return (await res.json()).phrases;
}

export async function getClipStats(): Promise<ClipStats> {
  return (await request("/clips/stats")).json();
}

export async function postClip(
  clip: RecordedClip,
  phraseId: string,
  sessionId: string,
): Promise<{ clip_id: string }> {
  const form = new FormData();
  form.append(
    "meta",
    JSON.stringify({ ...clip.meta, phrase_id: phraseId, session_id: sessionId, source: "collect" }),
  );
  form.append("landmarks", clip.landmarks, "landmarks.json");
  form.append("video", clip.video, "mouth.webm");
  return (await request("/clips", { method: "POST", body: form })).json();
}
