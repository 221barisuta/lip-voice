import { useCallback, useEffect, useRef, useState } from "react";
import type { ClipStats, RecordedClip } from "../types/clip";
import type { Phrase } from "../types/phrase";
import { getClipStats, getPhrases, postClip } from "./api";
import { PhraseQueue } from "./phraseQueue";

export type Phase = "loading" | "idle" | "countdown" | "recording" | "review" | "saving" | "ended";

export const RECORD_MS = 3000;
export const SESSION_MS = 5 * 60 * 1000;   // 仕様 7.1: 1 セッション最大 5 分
export const MIN_DETECTED_RATIO = 0.7;     // これ未満は顔が写っていないとみなし保存させない

interface Camera {
  record: (ms: number) => Promise<RecordedClip>;
  faceFound: boolean;
}

/** データ収集の進行（表示 → カウントダウン → 録画 → 保存/撮り直し → 次へ）。 */
export function useCollect(camera: Camera, cameraReady: boolean) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [phrases, setPhrases] = useState<Phrase[]>([]);
  const [phrase, setPhrase] = useState<Phrase | null>(null);
  const [count, setCount] = useState(3);
  const [clip, setClip] = useState<RecordedClip | null>(null);
  const [stats, setStats] = useState<ClipStats>({ today: 0, per_phrase: {} });
  const [error, setError] = useState("");
  const [remainingSec, setRemainingSec] = useState(SESSION_MS / 1000);
  const queue = useRef<PhraseQueue>();
  const sessionId = useRef(crypto.randomUUID().replace(/-/g, ""));
  const startedAt = useRef<number | null>(null);
  const phaseRef = useRef(phase);
  phaseRef.current = phase;

  useEffect(() => {
    (async () => {
      try {
        const list = await getPhrases(); // 初回ログイン時はここで初期フレーズが作られる
        setPhrases(list);
        queue.current = new PhraseQueue(list);
        setPhrase(queue.current.next());
        setStats(await getClipStats());
        setPhase("idle");
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, []);

  // セッション開始（最初の録画）から 5 分で自動終了
  useEffect(() => {
    const id = setInterval(() => {
      if (startedAt.current === null || phaseRef.current === "ended") return;
      const left = Math.max(0, SESSION_MS - (Date.now() - startedAt.current));
      setRemainingSec(Math.ceil(left / 1000));
      if (left === 0 && phaseRef.current !== "saving" && phaseRef.current !== "recording") {
        discard();
        setPhase("ended");
      }
    }, 500);
    return () => clearInterval(id);
  });

  const discard = () => {
    setClip((c) => {
      if (c) URL.revokeObjectURL(c.previewUrl);
      return null;
    });
  };

  const start = useCallback(async () => {
    if (phaseRef.current !== "idle" || !cameraReady) return;
    if (!camera.faceFound) {
      setError("顔が検出できていません。カメラの正面に顔を向けてください");
      return;
    }
    setError("");
    startedAt.current ??= Date.now();
    for (let n = 3; n >= 1; n--) {
      setPhase("countdown");
      setCount(n);
      await new Promise((r) => setTimeout(r, 1000));
    }
    setPhase("recording");
    try {
      setClip(await camera.record(RECORD_MS));
      setPhase("review");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setPhase("idle");
    }
  }, [camera, cameraReady]);

  const retake = useCallback(() => {
    if (phaseRef.current !== "review") return;
    discard();
    setError("");
    setPhase("idle");
  }, []);

  const save = useCallback(async () => {
    if (phaseRef.current !== "review" || !clip || !phrase) return;
    if (clip.detectedRatio < MIN_DETECTED_RATIO) {
      setError("顔が十分に検出できませんでした。撮り直してください");
      return;
    }
    setPhase("saving");
    try {
      await postClip(clip, phrase.id, sessionId.current);
      discard();
      setStats(await getClipStats());
      setPhrase(queue.current!.next());
      setError("");
      setPhase("idle");
    } catch (e) {
      setError(`保存に失敗しました: ${e instanceof Error ? e.message : e}`);
      setPhase("review");
    }
  }, [clip, phrase]);

  return { phase, phrase, phrases, count, clip, stats, error, remainingSec, start, retake, save };
}
