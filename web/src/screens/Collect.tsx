import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CameraView } from "../components/CameraView";
import { CollectSettings } from "../components/CollectSettings";
import { CollectStats } from "../components/CollectStats";
import { ModeSwitch } from "../components/ModeSwitch";
import { PhraseCard } from "../components/PhraseCard";
import { api } from "../lib/api";
import { useForegroundKeys } from "../lib/foregroundKeys";
import { useLive } from "../lib/useLive";

const STOP_LABEL = { still: "口が止まったので終了", max: "最大時間で終了", no_motion: "口の動きなし" } as const;

export function Collect() {
  const { snap, connected, mouth, frame } = useLive();
  const [error, setError] = useState("");
  const [fullPreview, setFullPreview] = useState(false);
  const [videoUrl, setVideoUrl] = useState<string>();
  const c = snap?.collect;
  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e));
  const act = (fn: () => Promise<unknown>) => () => { setError(""); fn().catch(fail); };

  // キー操作はブラウザが前面の時だけ有効（foregroundKeys.ts）。
  // スペースは押して離した瞬間に録画開始。Enter＝保存して次へ、Backspace＝撮り直し。
  useForegroundKeys(
    { Space: () => undefined, Enter: act(api.save), Backspace: act(api.discard) },
    { Space: act(api.start) },
  );

  // 確認中の口元動画（この PC の中だけ。外には出さない）
  const sig = c?.pending ? `${c.pending.duration_ms}-${c.pending.frames}` : "";
  const last = useRef("");
  useEffect(() => {
    if (!sig || sig === last.current) return;
    last.current = sig;
    let url: string | undefined;
    api.pendingVideo().then((b) => setVideoUrl((url = URL.createObjectURL(b)))).catch(() => undefined);
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [sig]);

  if (!snap || !c) {
    return <main style={{ padding: 24 }}>{connected ? "読み込み中…" : "アプリに接続しています…（lipvoice run を起動していますか）"}</main>;
  }
  const left = c.session_remaining_sec ?? c.session_total_sec;
  const mm = Math.floor(left / 60), ss = String(left % 60).padStart(2, "0");

  if (c.phase === "ended") {
    return (
      <main style={{ padding: 24 }}>
        <h1>セッション終了（{Math.round(c.session_total_sec / 60)}分）</h1>
        <CollectStats stats={c.stats} phrases={c.phrases} />
        <p><button onClick={act(api.newSession)}>新しいセッションを始める</button></p>
      </main>
    );
  }
  const recording = c.phase === "recording";
  const p = c.pending;
  return (
    <main style={{ padding: 24, maxWidth: 1000, margin: "0 auto" }}>
      <header style={{ display: "flex", justifyContent: "space-between" }}>
        <Link to="/speak">認識画面へ</Link>
        <span>{connected ? "" : "（接続が切れています）"} セッション残り {mm}:{ss}</span>
      </header>
      <ModeSwitch state={c} disabled={c.phase !== "idle"} onError={setError} />
      <PhraseCard state={c} remainingSec={snap.live.remaining_sec} />
      <CameraView live={snap.live} mouth={mouth} frame={frame} recording={recording} fullPreview={fullPreview} onFullPreview={setFullPreview} />

      {c.phase === "idle" && (
        <p style={{ fontSize: 20 }}>スペースキーを押して離すと録画開始（声は出さずに口パク。口が止まると自動で終わります）</p>
      )}
      {c.phase === "review" && p && (
        <section>
          {videoUrl && <video src={videoUrl} autoPlay loop muted style={{ width: 192, imageRendering: "pixelated" }} />}
          <p>録画 {(p.duration_ms / 1000).toFixed(1)} 秒（{STOP_LABEL[p.stop_reason]}）</p>
          {p.fps < 15 && <p style={{ color: "darkorange" }}>処理が遅く、フレーム数が少なくなっています（{p.fps} fps）。他のアプリを閉じてください</p>}
          <p>{p.savable ? "Enter＝保存して次へ ／ Backspace＝撮り直し" : p.problem}</p>
          <button onClick={act(api.save)} disabled={!p.savable}>保存</button>{" "}
          <button onClick={act(api.discard)}>撮り直し</button>
        </section>
      )}
      {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
      <CollectSettings liveRange={snap.live.live_range} disabled={recording} />
      <hr />
      <CollectStats stats={c.stats} phrases={c.phrases} />
    </main>
  );
}
