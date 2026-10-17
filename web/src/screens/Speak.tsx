import { useEffect, useState } from "react";
import { BigButton } from "../components/BigButton";
import { NavBar } from "../components/NavBar";
import { api } from "../lib/api";
import { useForegroundKeys } from "../lib/foregroundKeys";
import { speakText } from "../lib/speech";
import { useLive } from "../lib/useLive";

/** 認識画面（テスト用の手動操作）。実使用は常時監視（ステップ3）。 */
export function Speak() {
  const { snap, connected } = useLive();
  const [error, setError] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [spoken, setSpoken] = useState("");
  const sp = snap?.speak;
  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e));

  const start = () => { setError(""); setShowAll(false); api.speakStart().catch(fail); };
  const choose = (id: string | null, negative = false) => {
    setError("");
    api.speakChoose(id, negative).then((r) => {
      setShowAll(false);
      if (r.choice.text) { speakText(r.choice.text); setSpoken(r.choice.text); }   // 選んだら読み上げ、すぐ待機画面に戻る
    }).catch(fail);
  };
  const cands = sp?.result?.candidates ?? [];
  useForegroundKeys(
    { Space: () => undefined, Digit1: () => cands[0] && choose(cands[0].phrase_id), Digit2: () => cands[1] && choose(cands[1].phrase_id),
      Digit3: () => cands[2] && choose(cands[2].phrase_id), Digit0: () => setShowAll(true),
      Escape: () => { setShowAll(false); void api.speakSkip().catch(fail); } },
    { Space: start },
  );
  useEffect(() => { if (!spoken) return; const t = setTimeout(() => setSpoken(""), 2500); return () => clearTimeout(t); }, [spoken]);

  if (!snap || !sp) {
    return <main style={{ padding: 24 }}><NavBar />{connected ? "読み込み中…" : "アプリに接続しています…"}</main>;
  }
  const r = sp.result;
  const nPhrases = sp.phrases.length;
  return (
    <main style={{ padding: 24, maxWidth: 1100, margin: "0 auto", minHeight: "90vh" }}>
      <NavBar right={sp.model_version ? `モデル ${sp.model_version}` : ""} />
      <p style={{ color: "#a60" }}>テスト用の画面です（利用者は手動の操作ができないため、実使用は常時監視になります）</p>
      {!sp.has_model && <p style={{ fontSize: 24 }}>まだ学習していません。先に「収集」でデータを集め、<code>lipvoice train</code> を実行してください。</p>}
      {error && <p role="alert" style={{ color: "crimson", fontSize: 20 }}>{error}</p>}

      {sp.phase === "idle" && sp.has_model && (
        <section>
          <BigButton tone="primary" style={{ fontSize: 36, minHeight: 120, minWidth: 360 }} onClick={start}>話す（スペースを離す）</BigButton>
          <p style={{ fontSize: 20 }}>{snap.live.face_found ? "顔を検出中" : "顔が見つかりません"}</p>
          {spoken && <p style={{ fontSize: 48, fontWeight: 700 }}>🔊 {spoken}</p>}
        </section>
      )}

      {sp.phase === "recording" && (
        <section style={{ textAlign: "center" }}>
          <div style={{ fontSize: 48 }}>録画中 <strong>残り {Math.ceil(snap.live.remaining_sec ?? 0)} 秒</strong></div>
          <div style={{ fontSize: 32 }}>話し終えたら口を閉じてください</div>
          <BigButton tone="danger" onClick={() => api.cancel().catch(fail)}>中止</BigButton>
        </section>
      )}

      {sp.phase === "result" && r && (
        <section>
          {r.no_motion ? (
            <>
              <p style={{ fontSize: 32 }}>口の動きが検出できませんでした</p>
              <BigButton tone="primary" onClick={() => void api.speakSkip().catch(fail)}>もう一度</BigButton>
            </>
          ) : showAll ? (
            <>
              <p style={{ fontSize: 24 }}>正しいフレーズを選んでください</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
                {sp.phrases.map((p) => <BigButton key={p.id} onClick={() => choose(p.id)} style={{ fontSize: 28 }}>{p.text}</BigButton>)}
              </div>
              <BigButton onClick={() => setShowAll(false)}>戻る</BigButton>
            </>
          ) : (
            <>
              {r.rejected && <p style={{ color: "#a60", fontSize: 20 }}>フレーズに似ていない動きの可能性があります（棄却の閾値を超えました）</p>}
              <div style={{ display: "flex", gap: 16 }}>
                {cands.map((c, i) => (
                  <button key={c.phrase_id} onClick={() => choose(c.phrase_id)}
                    style={{ flex: 1, height: "30vh", minHeight: 160, fontSize: 40, borderRadius: 16, border: "2px solid #235", background: i === 0 ? "#dfe" : "#eef", cursor: "pointer" }}>
                    {c.text}
                    <div style={{ fontSize: 20, color: "#555" }}>{i + 1}　確信度 {(c.confidence * 100).toFixed(0)}%</div>
                  </button>
                ))}
              </div>
              <div style={{ marginTop: 12 }}>
                <BigButton onClick={() => setShowAll(true)}>どれも違う（0）</BigButton>
                <BigButton onClick={() => choose(null, true)}>フレーズではない動き</BigButton>
                <BigButton onClick={() => void api.speakSkip().catch(fail)}>やり直し（Esc）</BigButton>
              </div>
              <p style={{ fontSize: 14, color: "#666" }}>
                モデル {r.version}（{r.model}）／ 判定 {r.latency_ms} ms ／ A と B が{r.agree ? "一致" : "不一致"} ／ 登録フレーズ {nPhrases} 個
              </p>
            </>
          )}
        </section>
      )}
    </main>
  );
}
