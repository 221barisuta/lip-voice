import { useCallback, useEffect, useState } from "react";
import { BigButton } from "../components/BigButton";
import { NavBar } from "../components/NavBar";
import { api } from "../lib/api";
import type { PhraseInfo } from "../types/phrase";

/** フレーズの追加・並べ替え・修正・削除。録画のあるフレーズは削除できない（追加のあとは、録って、学習し直すと、認識に出る）。 */
export function Phrases() {
  const [rows, setRows] = useState<PhraseInfo[]>([]);
  const [orig, setOrig] = useState<PhraseInfo[]>([]);
  const [text, setText] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => api.phraseInfo().then((r) => { setRows(r.phrases); setOrig(r.phrases); }).catch((e) => setError(String(e.message ?? e))), []);
  useEffect(() => { load(); }, [load]);

  const dirty = JSON.stringify(rows.map((r) => [r.id, r.text])) !== JSON.stringify(orig.map((r) => [r.id, r.text]));
  const fail = (e: unknown) => setError(e instanceof Error ? e.message : String(e));
  const edit = (i: number, v: string) => setRows(rows.map((r, k) => (k === i ? { ...r, text: v } : r)));
  const move = (i: number, d: number) => {
    const j = i + d;
    if (j < 0 || j >= rows.length) return;
    const next = [...rows];
    [next[i], next[j]] = [next[j], next[i]];
    setRows(next);
  };
  const remove = (i: number) => setRows(rows.filter((_, k) => k !== i));

  const save = () => {
    const renamed = rows.filter((r) => r.clips > 0 && orig.find((o) => o.id === r.id)?.text !== r.text);
    if (renamed.length && !window.confirm(
      `録画のあるフレーズの言葉を変えます（${renamed.map((r) => `「${r.text}」`).join("、")}）。\n過去の録画は、前の言葉で録ったものです。誤字の修正だけにして、別の言葉にしたい時は「追加」してください。`)) return;
    setError(""); setMsg("");
    api.putPhrases(rows.map(({ id, text: t }) => ({ id, text: t.trim() }))).then(() => { setMsg("保存しました"); return load(); }).catch(fail);
  };
  const add = () => {
    setError(""); setMsg("");
    api.addPhrase(text).then(() => { setText(""); setMsg("追加しました。録画して、学習し直すと、認識に出ます"); return load(); }).catch(fail);
  };

  return (
    <main style={{ padding: 24, maxWidth: 900, margin: "0 auto" }}>
      <NavBar />
      <h1>フレーズ</h1>
      <p style={{ fontSize: 15 }}>
        新しく足すフレーズは、既存のものと<strong>口の形がはっきり違う</strong>言い回し（やや長めのもの）が向いています。
        3 音以下の短い言葉どうしは取り違えやすいので、足したあとは「評価」の取り違え表を確認してください。
        別の日が 2 日以上たまるまで、そのフレーズの評価は出ません。
      </p>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead><tr><th align="left">フレーズ</th><th align="right">録画</th><th align="right">日数</th><th>モデル</th><th /></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.id}>
              <td><input value={r.text} onChange={(e) => edit(i, e.target.value)} style={{ width: "100%", fontSize: 18 }} /></td>
              <td align="right">{r.clips} 本</td>
              <td align="right">{r.days}</td>
              <td align="center">{r.in_model ? "✓" : "—"}</td>
              <td style={{ whiteSpace: "nowrap" }}>
                <button onClick={() => move(i, -1)} disabled={i === 0}>▲</button>{" "}
                <button onClick={() => move(i, 1)} disabled={i === rows.length - 1}>▼</button>{" "}
                <button onClick={() => remove(i)} disabled={r.clips > 0 || rows.length <= 1}
                        title={r.clips > 0 ? "録画のあるフレーズは削除できません" : ""}>削除</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        <BigButton tone="primary" onClick={save} disabled={!dirty}>変更を保存</BigButton>
        {dirty && <BigButton onClick={() => setRows(orig)}>変更を取り消す</BigButton>}
        {msg && <span style={{ color: "#161", fontSize: 18 }}> {msg}</span>}
      </p>
      <h2>フレーズを追加</h2>
      <p>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="例: 水がほしい" disabled={dirty}
               style={{ fontSize: 22, width: "60%", padding: 8 }} />{" "}
        <BigButton onClick={add} disabled={!text.trim() || dirty}>追加</BigButton>
      </p>
      {dirty && <p style={{ color: "#a60" }}>未保存の変更があります。先に保存（または取り消し）してください。</p>}
      {error && <p role="alert" style={{ color: "crimson", fontSize: 18 }}>{error}</p>}
    </main>
  );
}
