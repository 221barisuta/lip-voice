import { useState } from "react";
import { Link } from "react-router-dom";
import { CameraView } from "../components/CameraView";
import { CollectSettings } from "../components/CollectSettings";
import { CollectStats } from "../components/CollectStats";
import { PhraseCard } from "../components/PhraseCard";
import { loadSettings, saveSettings, type RecordingSettings as Settings } from "../lib/recordingSettings";
import { useForegroundKeys } from "../lib/foregroundKeys";
import { isSavable, unsavableReason, useCollect } from "../lib/useCollect";
import { useMouthCamera } from "../lib/useMouthCamera";

const STOP_LABEL = { still: "口が止まったので終了", max: "最大時間で終了", no_motion: "口の動きなし" } as const;

export function Collect() {
  const [settings, setSettings] = useState<Settings>(loadSettings);
  const camera = useMouthCamera(true, settings.stillSec);
  const c = useCollect(camera, camera.status === "ready", settings);

  const change = (next: Settings) => {
    setSettings(next);
    saveSettings(next);
  };

  // キー操作はブラウザが前面の時だけ有効（foregroundKeys.ts）。
  // スペースは押して離した瞬間に録画開始。Enter＝保存して次へ、Backspace＝撮り直し。
  useForegroundKeys({ Space: () => undefined, Enter: c.save, Backspace: c.retake }, { Space: c.start });

  const mm = String(Math.floor(c.remainingSec / 60));
  const ss = String(c.remainingSec % 60).padStart(2, "0");

  if (c.phase === "ended") {
    return (
      <main style={{ padding: 24 }}>
        <h1>セッション終了（5分）</h1>
        <CollectStats stats={c.stats} phrases={c.phrases} />
        <p><button onClick={() => window.location.reload()}>新しいセッションを始める</button></p>
        <Link to="/speak">戻る</Link>
      </main>
    );
  }

  const recording = c.phase === "recording";
  return (
    <main style={{ padding: 24, maxWidth: 1000, margin: "0 auto" }}>
      <header style={{ display: "flex", justifyContent: "space-between" }}>
        <Link to="/speak">← 戻る</Link>
        <span>セッション残り {mm}:{ss}</span>
      </header>

      {c.phrase && <PhraseCard text={c.phrase.text} phase={c.phase} remainingSec={camera.remainingSec} />}

      <CameraView
        videoRef={camera.videoRef}
        cropCanvas={camera.cropCanvas}
        status={camera.status}
        error={camera.error}
        faceFound={camera.faceFound}
        recording={recording}
      />

      {c.phase === "idle" && (
        <p style={{ fontSize: 20 }}>スペースキーを押して離すと録画開始（声は出さずに口パク。口が止まると自動で終わります）</p>
      )}

      {(c.phase === "review" || c.phase === "saving") && c.clip && (
        <section>
          <video src={c.clip.previewUrl} autoPlay loop muted style={{ width: 192, imageRendering: "pixelated" }} />
          <p>
            録画 {(c.clip.durationMs / 1000).toFixed(1)} 秒（{STOP_LABEL[c.clip.stopReason]}）
          </p>
          {c.clip.meta.fps_measured < 15 && (
            <p style={{ color: "darkorange" }}>
              処理が遅く、フレーム数が少なくなっています（{c.clip.meta.fps_measured} fps）。他のアプリを閉じてください
            </p>
          )}
          <p>{isSavable(c.clip) ? "Enter＝保存して次へ ／ Backspace＝撮り直し" : unsavableReason(c.clip)}</p>
          <button onClick={c.save} disabled={c.phase === "saving" || !isSavable(c.clip)}>保存</button>{" "}
          <button onClick={c.retake} disabled={c.phase === "saving"}>撮り直し</button>
        </section>
      )}

      {c.error && <p role="alert" style={{ color: "crimson" }}>{c.error}</p>}

      <CollectSettings value={settings} onChange={change} liveRange={camera.liveRange} disabled={recording} />
      <hr />
      <CollectStats stats={c.stats} phrases={c.phrases} />
    </main>
  );
}
