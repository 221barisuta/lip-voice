/** ブラウザ標準の読み上げ（フェーズ1）。フレーズごとの音声ファイルは、フェーズ2で差し替える。 */
export function speakText(text: string): void {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "ja-JP";
  window.speechSynthesis.speak(u);
}
