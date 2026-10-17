import { useCallback, useEffect, useState } from "react";
import { BigButton } from "../components/BigButton";
import { NavBar } from "../components/NavBar";
import { api } from "../lib/api";
import type { ClipRow, ClipsPayload } from "../types/data";

const STOP = { still: "口が止まって終了", max: "最大時間で終了", no_motion: "口の動きなし" } as const;
const PAGE = 50;

/** 撮れたデータの確認。家族が「撮れているか」を見て、撮り直しの要否を判断する（口元の動画だけ。顔全体は保存していない）。 */
export function Data() {
  const [date, setDate] = useState("");
  const [kind, setKind] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<ClipsPayload | null>(null);
  const [sel, setSel] = useState<ClipRow | null>(null);
  const [video, setVideo] = useState<string>();
  const [error, setError] = useState("");

  const load = useCallback(() => {
    const q = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
    if (date) q.set("date", date);
    if (kind) q.set("kind", kind);
    api.clips(q.toString()).then(setData).catch((e) => setError(String(e.message ?? e)));
  }, [date, kind, offset]);
  useEffect(load, [load]);

  useEffect(() => {
    if (!sel) { setVideo(undefined); return; }
    let url: string | undefined;
    let alive = true;
    api.clipVideo(sel.id).then((b) => { if (alive) setVideo((url = URL.createObjectURL(b))); }).catch(() => setVideo(undefined));
    return () => { alive = false; if (url) URL.revokeObjectURL(url); };
  }, [sel]);

  const remove = (c: ClipRow) => {
    if (!window.confirm(`「${c.label}」（${c.date}）の録画を削除します。元に戻せません。`)) return;
    setError("");
    api.deleteClip(c.id).then(() => { setSel(null); load(); }).catch((e) => setError(String(e.message ?? e)));
  };

  return (
    <main style={{ padding: 24, maxWidth: 1000, margin: "0 auto" }}>
      <NavBar />
      <h1>データの確認</h1>
      <p>
        日付: <select value={date} onChange={(e) => { setDate(e.target.value); setOffset(0); }}>
          <option value="">すべて</option>
          {data?.dates.map((d) => <option key={d}>{d}</option>)}
        </select>{" "}
        種類: <select value={kind} onChange={(e) => { setKind(e.target.value); setOffset(0); }}>
          <option value="">すべて</option><option value="phrase">フレーズ</option><option value="negative">フレーズではない動き</option>
        </select>{" "}
        {data && `${data.total} 本`}
      </p>
      {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
      <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
        <table style={{ borderCollapse: "collapse", flex: 1 }}>
          <thead><tr><th align="left">フレーズ</th><th align="left">日付</th><th align="right">秒</th><th align="right">検出率</th><th align="left">終了</th><th /></tr></thead>
          <tbody>
            {data?.clips.map((c) => (
              <tr key={c.id} onClick={() => setSel(c)} style={{ cursor: "pointer", background: sel?.id === c.id ? "#dfe9ff" : undefined }}>
                <td>{c.label}{c.source === "use" ? "（実使用）" : ""}</td><td>{c.date}</td>
                <td align="right">{(c.duration_ms / 1000).toFixed(1)}</td>
                <td align="right" style={{ color: c.detected_ratio < 0.9 ? "#a60" : undefined }}>{Math.round(c.detected_ratio * 100)}%</td>
                <td>{STOP[c.stop_reason] ?? c.stop_reason}</td>
                <td><button onClick={(e) => { e.stopPropagation(); remove(c); }}>削除</button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <aside style={{ minWidth: 220 }}>
          {sel ? (
            <>
              <p><strong>{sel.label}</strong>（{sel.date}）</p>
              {video && <video src={video} autoPlay loop muted controls style={{ width: 192, imageRendering: "pixelated" }} />}
              <BigButton tone="danger" onClick={() => remove(sel)}>この録画を削除</BigButton>
            </>
          ) : <p>行を選ぶと、口元の動画を再生します。</p>}
        </aside>
      </div>
      {data && data.total > PAGE && (
        <p>
          <BigButton onClick={() => setOffset(Math.max(0, offset - PAGE))} disabled={offset === 0}>前へ</BigButton>
          <BigButton onClick={() => setOffset(offset + PAGE)} disabled={offset + PAGE >= data.total}>次へ</BigButton>
        </p>
      )}
    </main>
  );
}
