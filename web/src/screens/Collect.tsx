import { Link } from "react-router-dom";
import { CameraView } from "../components/CameraView";
import { CollectStats } from "../components/CollectStats";
import { PhraseCard } from "../components/PhraseCard";
import { useForegroundKeys } from "../lib/foregroundKeys";
import { MIN_DETECTED_RATIO, useCollect } from "../lib/useCollect";
import { useMouthCamera } from "../lib/useMouthCamera";

export function Collect() {
  const camera = useMouthCamera(true);
  const c = useCollect(camera, camera.status === "ready");

  // キー操作はブラウザが前面の時だけ有効（foregroundKeys.ts）
  useForegroundKeys({
    Space: c.start,
    Enter: c.save,
    Backspace: c.retake,
  });

  const mm = String(Math.floor(c.remainingSec / 60)).padStart(1, "0");
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

  return (
    <main style={{ padding: 24, maxWidth: 1000, margin: "0 auto" }}>
      <header style={{ display: "flex", justifyContent: "space-between" }}>
        <Link to="/speak">← 戻る</Link>
        <span>残り {mm}:{ss}</span>
      </header>

      {c.phrase && <PhraseCard text={c.phrase.text} phase={c.phase} count={c.count} />}

      <CameraView
        videoRef={camera.videoRef}
        cropCanvas={camera.cropCanvas}
        status={camera.status}
        error={camera.error}
        faceFound={camera.faceFound}
        recording={c.phase === "recording"}
      />

      {c.phase === "idle" && <p style={{ fontSize: 20 }}>スペースキーで開始（声は出さずに口パク）</p>}

      {(c.phase === "review" || c.phase === "saving") && c.clip && (
        <section>
          <video src={c.clip.previewUrl} autoPlay loop muted style={{ width: 192, imageRendering: "pixelated" }} />
          {c.clip.meta.fps_measured < 15 && (
            <p style={{ color: "darkorange" }}>
              処理が遅く、フレーム数が少なくなっています（{c.clip.meta.fps_measured} fps）。他のアプリを閉じてください
            </p>
          )}
          <p>
            {c.clip.detectedRatio < MIN_DETECTED_RATIO
              ? "顔が十分に検出できませんでした。撮り直してください"
              : "Enter＝保存して次へ ／ Backspace＝撮り直し"}
          </p>
          <button onClick={c.save} disabled={c.phase === "saving"}>保存</button>{" "}
          <button onClick={c.retake} disabled={c.phase === "saving"}>撮り直し</button>
        </section>
      )}

      {c.error && <p role="alert" style={{ color: "crimson" }}>{c.error}</p>}

      <hr />
      <CollectStats stats={c.stats} phrases={c.phrases} />
    </main>
  );
}
