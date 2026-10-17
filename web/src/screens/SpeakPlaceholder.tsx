import { Link } from "react-router-dom";

/** 認識画面 /speak は次のステップで実装する。それまでの仮画面。 */
export function SpeakPlaceholder() {
  return (
    <main style={{ padding: 24 }}>
      <h1>認識画面（未実装）</h1>
      <p>認識画面は次のステップで作ります。</p>
      <p><Link to="/collect">データ収集へ</Link></p>
    </main>
  );
}
