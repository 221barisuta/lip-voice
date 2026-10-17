import { useEffect, useRef } from "react";

/** ブラウザが前面（フォーカスあり・タブ表示中）の時だけ true。 */
export const isForeground = () => document.hasFocus() && document.visibilityState === "visible";

const isTyping = (t: EventTarget | null) =>
  t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement || t instanceof HTMLSelectElement;

type Handlers = Record<string, () => void>;

/**
 * キー操作。前面の時だけ反応し、長押しの連打は無視する。
 * down: キーを押した時、up: キーを離した時（コード名は e.code。例: "Space"）。
 * 押した時の既定動作（ページのスクロールなど）は、登録したキーでは止める。
 */
export function useForegroundKeys(down: Handlers, up: Handlers = {}): void {
  const ref = useRef({ down, up });
  ref.current = { down, up };
  useEffect(() => {
    const handle = (kind: "down" | "up") => (e: KeyboardEvent) => {
      const fn = ref.current[kind][e.code];
      const registered = e.code in ref.current.down || e.code in ref.current.up;
      if (!registered || isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (!isForeground()) return;
      e.preventDefault();
      if (!fn || e.repeat) return;
      fn();
    };
    const onDown = handle("down"), onUp = handle("up");
    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    return () => {
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
    };
  }, []);
}
