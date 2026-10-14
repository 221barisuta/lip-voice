import { useEffect, useRef } from "react";

/** ブラウザが前面（フォーカスあり・タブ表示中）の時だけ true。 */
export const isForeground = () => document.hasFocus() && document.visibilityState === "visible";

/** キー操作。前面の時だけ反応し、長押しの連打は無視する。 */
export function useForegroundKeys(handlers: Record<string, () => void>): void {
  const ref = useRef(handlers);
  ref.current = handlers;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!isForeground() || e.repeat || e.metaKey || e.ctrlKey || e.altKey) return;
      const fn = ref.current[e.code];
      if (!fn) return;
      e.preventDefault();
      fn();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
