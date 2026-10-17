import { useEffect, useState } from "react";
import type { Snapshot } from "../types/live";
import { streamEvents } from "./api";

/** Python 側の状態（カメラ・顔検出・録画・収集の進行）をリアルタイムで受け取る。切れたら自動でつなぎ直す。 */
export function useLive() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const [mouth, setMouth] = useState<string>();
  const [frame, setFrame] = useState<string>();

  useEffect(() => {
    const ctl = new AbortController();
    (async () => {
      let wait = 500;
      while (!ctl.signal.aborted) {
        try {
          await streamEvents((s) => {
            setConnected(true);
            wait = 500;
            setSnap(s);
            if (s.mouth) setMouth(s.mouth);
            setFrame(s.frame);
          }, ctl.signal);
        } catch {
          /* 接続が切れた */
        }
        setConnected(false);
        await new Promise((r) => setTimeout(r, wait));
        wait = Math.min(wait * 2, 5000);
      }
    })();
    return () => ctl.abort();
  }, []);

  return { snap, connected, mouth, frame };
}
