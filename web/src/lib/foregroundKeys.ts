import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

/** ブラウザが前面（フォーカスあり・タブ表示中）の時だけ true。 */
export const isForeground = () => document.hasFocus() && document.visibilityState === "visible";

/** キー操作を有効にする画面。設定・フレーズ・データなど、文字入力がある画面では無効にする。 */
export const SHORTCUT_ROUTES: readonly string[] = ["/collect", "/speak"];

const TEXT_TYPES = new Set(["text", "search", "number", "email", "url", "tel", "password"]);

/** キーの判定に使う、イベントの要点（DOM に依存しない形。テストしやすくするため）。 */
export interface KeyInfo {
  pathname: string;
  isComposing: boolean;
  keyCode: number;
  composing: boolean;                 // compositionstart〜compositionend の間
  metaKey: boolean;
  ctrlKey: boolean;
  altKey: boolean;
  target: { tag: string; type: string; isContentEditable: boolean } | null;
}

/** 文字を入力している要素か（input の文字系、textarea、select、contenteditable）。チェックボックス・ボタンは含めない。 */
export const isTypingTarget = (t: KeyInfo["target"]): boolean =>
  !!t && (t.isContentEditable || t.tag === "TEXTAREA" || t.tag === "SELECT" || (t.tag === "INPUT" && TEXT_TYPES.has(t.type)));

/**
 * ショートカットを無視すべきか。
 * - 日本語入力（IME）の変換中（isComposing、keyCode 229、composition イベントの間）は、すべて無視する
 * - 文字入力欄にフォーカスがある時は無視する
 * - /collect と /speak 以外の画面では無視する
 * - 修飾キー（Ctrl / Meta / Alt）つきは、ブラウザの操作なので無視する
 */
export function shouldIgnoreKey(k: KeyInfo): boolean {
  if (k.isComposing || k.keyCode === 229 || k.composing) return true;
  if (!SHORTCUT_ROUTES.includes(k.pathname)) return true;
  if (isTypingTarget(k.target)) return true;
  return k.metaKey || k.ctrlKey || k.altKey;
}

const describe = (t: EventTarget | null): KeyInfo["target"] =>
  t instanceof HTMLElement
    ? { tag: t.tagName, type: t instanceof HTMLInputElement ? t.type : "", isContentEditable: t.isContentEditable }
    : null;

type Handlers = Record<string, () => void>;

/**
 * キー操作。前面の時だけ反応し、長押しの連打は無視する。
 * down: キーを押した時、up: キーを離した時（コード名は e.code。例: "Space"）。
 * 押した時の既定動作（ページのスクロールなど）は、登録したキーでは止める（無視する場面では止めない）。
 */
export function useForegroundKeys(down: Handlers, up: Handlers = {}): void {
  const { pathname } = useLocation();
  const ref = useRef({ down, up, pathname });
  ref.current = { down, up, pathname };
  useEffect(() => {
    let composing = false;
    const handle = (kind: "down" | "up") => (e: KeyboardEvent) => {
      const fn = ref.current[kind][e.code];
      const registered = e.code in ref.current.down || e.code in ref.current.up;
      if (!registered) return;
      const ignore = shouldIgnoreKey({
        pathname: ref.current.pathname, isComposing: e.isComposing, keyCode: e.keyCode, composing,
        metaKey: e.metaKey, ctrlKey: e.ctrlKey, altKey: e.altKey, target: describe(e.target),
      });
      if (ignore || !isForeground()) return;
      e.preventDefault();
      if (!fn || e.repeat) return;
      fn();
    };
    const onDown = handle("down"), onUp = handle("up");
    const start = () => { composing = true; };
    const end = () => { setTimeout(() => { composing = false; }, 0); };     // 変換を確定した Enter の keydown / keyup が、このあとに来ることがある
    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    window.addEventListener("compositionstart", start);
    window.addEventListener("compositionend", end);
    return () => {
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
      window.removeEventListener("compositionstart", start);
      window.removeEventListener("compositionend", end);
    };
  }, []);
}
