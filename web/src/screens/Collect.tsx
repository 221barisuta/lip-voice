import { useEffect, useRef, useState } from "react";
import { BigButton } from "../components/BigButton";
import { Calibrate } from "../components/Calibrate";
import { CameraView } from "../components/CameraView";
import { CollectSettings } from "../components/CollectSettings";
import { CollectStats } from "../components/CollectStats";
import { ModeSwitch } from "../components/ModeSwitch";
import { NavBar } from "../components/NavBar";
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
  // スペースは押して離した瞬間に録画開始。Enter＝保存して次へ、Backspace＝撮り直し、Esc＝録画の中止。
  useForegroundKeys(
    { Space: () => undefined, Enter: act(api.save), Backspace: act(api.discard), Escape: act(api.cancel) },
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
    return <main style={{ padding: 24 }}><NavBar />{connected ? "読み込み中…" : "アプリに接続しています…（lipvoice run を起動していますか）"}</main>;
  }
  const left = c.session_remaining_sec ?? c.session_total_sec;
  const mm = Math.floor(left / 60), ss = String(left % 60).padStart(2, "0");

  if (c.phase === "ended") {
    return (
      <main style={{ padding: 24 }}>
        <NavBar />
        <h1>セッション終了（{Math.round(c.session_total_sec / 60)}分）。おつかれさまでした</h1>
        <CollectStats stats={c.stats} phrases={c.phrases} />
        <CollectSettings liveRange={snap.live.live_range} disabled={false} />
        <Calibrate disabled={false} />
        <BigButton tone="primary" onClick={act(api.newSession)}>新しいセッションを始める</BigButton>
      </main>
    );
  }
  const recording = c.phase === "recording";
  const p = c.pending;
  return (
    <main style={{ padding: 24, maxWidth: 1000, margin: "0 auto" }}>
      <NavBar right={`${connected ? "" : "（接続が切れています）"} 撮影日 ${c.date} ／ セッション残り ${mm}:${ss}`} />
      <ModeSwitch state={c} disabled={c.phase !== "idle"} onError={setError} />
      <PhraseCard state={c} remainingSec={snap.live.remaining_sec} />
      <CameraView live={snap.live} mouth={mouth} frame={frame} recording={recording} fullPreview={fullPreview} onFullPreview={setFullPreview} />

      {c.phase === "idle" && (
        <section style={{ marginTop: 8 }}>
          <BigButton tone="primary" onClick={act(api.start)}>録画開始（スペースを離す）</BigButton>
          <BigButton onClick={act(api.skip)} disabled={c.mode !== "phrase"}>スキップ（次のフレーズ）</BigButton>
          <BigButton onClick={act(api.undo)}>直前の保存を取り消す</BigButton>
          {c.last_saved && <p style={{ color: "#161", fontSize: 18 }}>保存しました: 「{c.last_saved.label}」 {c.last_saved.seconds} 秒（今日 {c.last_saved.n} 本目）</p>}
          <p style={{ fontSize: 16 }}>スペースキーを押して離すと録画開始（声は出さずに口パク。口が止まると自動で終わります）</p>
        </section>
      )}
      {recording && <BigButton tone="danger" onClick={act(api.cancel)}>中止（Esc）</BigButton>}
      {c.phase === "review" && p && (
        <section>
          {videoUrl && <video src={videoUrl} autoPlay loop muted style={{ width: 192, imageRendering: "pixelated" }} />}
          <p>録画 {(p.duration_ms / 1000).toFixed(1)} 秒（{STOP_LABEL[p.stop_reason]}）</p>
          {p.fps < 15 && <p style={{ color: "darkorange" }}>処理が遅く、フレーム数が少なくなっています（{p.fps} fps）。他のアプリを閉じてください</p>}
          <p>{p.savable ? "Enter＝保存して次へ ／ Backspace＝撮り直し" : p.problem}</p>
          <BigButton tone="primary" onClick={act(api.save)} disabled={!p.savable}>保存（Enter）</BigButton>
          <BigButton onClick={act(api.discard)}>撮り直し（Backspace）</BigButton>
        </section>
      )}
      {error && <p role="alert" style={{ color: "crimson", fontSize: 18 }}>{error}</p>}
      <CollectSettings liveRange={snap.live.live_range} disabled={recording} />
      <Calibrate disabled={c.phase !== "idle"} />
      <hr />
      <CollectStats stats={c.stats} phrases={c.phrases} />
    </main>
  );
}
