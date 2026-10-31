import { describe, expect, it } from "vitest";
import { isTypingTarget, shouldIgnoreKey, type KeyInfo } from "./foregroundKeys";

const base: KeyInfo = {
  pathname: "/collect", isComposing: false, keyCode: 32, composing: false,
  metaKey: false, ctrlKey: false, altKey: false, target: { tag: "BODY", type: "", isContentEditable: false },
};
const k = (over: Partial<KeyInfo>): KeyInfo => ({ ...base, ...over });

describe("shouldIgnoreKey", () => {
  it("通常の状態では、/collect と /speak で有効", () => {
    expect(shouldIgnoreKey(k({}))).toBe(false);
    expect(shouldIgnoreKey(k({ pathname: "/speak" }))).toBe(false);
  });

  it("日本語入力（IME）の変換中は、すべて無視する", () => {
    expect(shouldIgnoreKey(k({ isComposing: true }))).toBe(true);
    expect(shouldIgnoreKey(k({ keyCode: 229 }))).toBe(true);          // Safari などで、変換確定の Enter が keyCode 229
    expect(shouldIgnoreKey(k({ composing: true }))).toBe(true);       // composition イベントの間
  });

  it("文字入力欄にフォーカスがある時は無視する（input の文字系、textarea、contenteditable、select）", () => {
    for (const type of ["text", "search", "number", "email", "url", "tel", "password"]) {
      expect(shouldIgnoreKey(k({ target: { tag: "INPUT", type, isContentEditable: false } }))).toBe(true);
    }
    expect(shouldIgnoreKey(k({ target: { tag: "TEXTAREA", type: "", isContentEditable: false } }))).toBe(true);
    expect(shouldIgnoreKey(k({ target: { tag: "DIV", type: "", isContentEditable: true } }))).toBe(true);
    expect(shouldIgnoreKey(k({ target: { tag: "SELECT", type: "", isContentEditable: false } }))).toBe(true);
  });

  it("チェックボックス・スライダー・ボタンにフォーカスがあっても、ショートカットは使える", () => {
    for (const type of ["checkbox", "range", "button"]) {
      expect(isTypingTarget({ tag: "INPUT", type, isContentEditable: false })).toBe(false);
    }
    expect(shouldIgnoreKey(k({ target: { tag: "BUTTON", type: "", isContentEditable: false } }))).toBe(false);
  });

  it("/collect と /speak 以外の画面では無効", () => {
    for (const pathname of ["/phrases", "/data", "/report", "/", "/collect/x"]) {
      expect(shouldIgnoreKey(k({ pathname }))).toBe(true);
    }
  });

  it("修飾キーつきは無視する", () => {
    expect(shouldIgnoreKey(k({ ctrlKey: true }))).toBe(true);
    expect(shouldIgnoreKey(k({ metaKey: true }))).toBe(true);
    expect(shouldIgnoreKey(k({ altKey: true }))).toBe(true);
  });
});
