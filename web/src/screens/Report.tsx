import { useCallback, useEffect, useState } from "react";
import { BigButton } from "../components/BigButton";
import { AutoTrainPanel } from "../components/AutoTrainPanel";
import { ConfusionTable } from "../components/ConfusionTable";
import { NavBar } from "../components/NavBar";
import { api } from "../lib/api";
import type { Judge, Metrics, ModelResult, Rate, ReportPayload } from "../types/report";

const pct = (r: Rate) => (r.rate == null ? "—" : `${(r.rate * 100).toFixed(1)}%`);
const frac = (r: Rate) => `${r.k}/${r.n}`;
const Badge = ({ j, label }: { j?: Judge; label: string }) =>
  <span style={{ marginRight: 12, padding: "2px 8px", borderRadius: 4, background: j?.ok ? "#cfc" : "#fcc" }}>
    {label}: {j?.value == null ? "—" : label === "処理時間" ? `${j.value.toFixed(0)}ms` : `${(j.value * 100).toFixed(1)}%`}（基準 {label === "処理時間" ? `${j?.need}ms 以内` : `${((j?.need ?? 0) * 100).toFixed(0)}% 以上`}）{j?.ok ? " 合格" : " 未達"}
  </span>;

function MetricBlock({ title, m, classes, names }: { title: string; m: Metrics; classes: string[]; names: Record<string, string> }) {
  return (
    <section>
      <h3>{title}</h3>
      <p style={{ fontSize: 20 }}>1 位が正解: <strong>{pct(m.top1)}</strong>（{frac(m.top1)}） ／ 上位 3 に正解: <strong>{pct(m.top3)}</strong>（{frac(m.top3)}）</p>
      <table><tbody>
        {classes.map((c) => m.per_phrase[c] && (
          <tr key={c}><td style={{ paddingRight: 16 }}>{names[c] ?? c}</td><td>1 位 {m.per_phrase[c].top1}/{m.per_phrase[c].n}</td><td style={{ paddingLeft: 12 }}>上位3 {m.per_phrase[c].top3}/{m.per_phrase[c].n}</td></tr>
        ))}
      </tbody></table>
      <h4>取り違え表</h4>
      <ConfusionTable classes={classes} names={names} matrix={m.confusion} />
    </section>
  );
}

export function Report() {
  const [data, setData] = useState<ReportPayload | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  const load = useCallback(() => { api.report().then(setData).catch((e) => setError(String(e.message))); }, []);
  useEffect(() => { load(); api.phrases().then((r) => setNames(Object.fromEntries(r.phrases.map((p) => [p.id, p.text])))).catch(() => undefined); }, []);
  if (!data) return <main style={{ padding: 24 }}><NavBar />{error || "読み込み中…"}</main>;
  const rep = data.report;
  if (!rep) {
    return <main style={{ padding: 24 }}><NavBar /><h2>評価</h2><p>まだ学習していません。データを集めたら、下の「今すぐ学習し直す」を押してください（自動学習の設定が「毎晩」なら、翌日に自動で学習します）。</p>
      <AutoTrainPanel auto={data.auto} pending={data.pending} active={data.models.active} onChanged={load} /></main>;
  }
  const res: ModelResult | undefined = rep.results[rep.active];
  return (
    <main style={{ padding: 24, maxWidth: 1100, margin: "0 auto" }}>
      <NavBar right={`モデル ${rep.version}（${rep.active}）`} />
      <AutoTrainPanel auto={data.auto} pending={data.pending} active={data.models.active} onChanged={load} />
      <h2>評価</h2>
      <p style={{ fontSize: 14, color: "#555" }}>
        学習日時 {rep.created_at} ／ フレーズ {rep.n_pos} 本・負例 {rep.n_neg} 本 ／ 撮影日 {rep.dates.join("、")}（{Object.entries(rep.counts_by_day).map(([d, n]) => `${d}: ${n}`).join("、")}）
      </p>
      {!rep.evaluated && <p style={{ color: "#a60", fontSize: 18 }}>{rep.note}</p>}
      {res && rep.judgement && (
        <>
          <p>合格基準（全日の交差検証）: <Badge j={rep.judgement.lodo.top3} label="上位3" /><Badge j={rep.judgement.lodo.top1} label="1位" /><Badge j={rep.judgement.lodo.latency_ms} label="処理時間" /></p>
          <p style={{ fontSize: 12, color: "#666" }}>処理時間は、判定そのもの（口が止まってからの 1 秒の判定待ちは含まない）。交差検証は、日ごとに「その日を評価、残りの日を学習」を繰り返した結果です。</p>
          <MetricBlock title="全日の交差検証（日ごとに評価して合算）" m={res.lodo} classes={rep.classes} names={names} />
          {res.last_day && <MetricBlock title={`最新日（${rep.dates[rep.dates.length - 1]}）を評価、それ以前を学習（仕様 8.4 の既定の分け方）`} m={res.last_day} classes={rep.classes} names={names} />}
          <h3>日ごとの正解率</h3>
          <table><tbody>{Object.entries(res.by_day).map(([d, m]) => m && (
            <tr key={d}><td style={{ paddingRight: 16 }}>{d}</td><td>1 位 {frac(m.top1)}（{pct(m.top1)}）</td><td style={{ paddingLeft: 12 }}>上位3 {frac(m.top3)}（{pct(m.top3)}）</td></tr>))}</tbody></table>
          <h3>自動発話の判断材料（確信度の閾値ごと）</h3>
          <p style={{ fontSize: 13, color: "#555" }}>棄却の閾値 {res.tau.toFixed(3)}（{res.tau_note}）。誤発話 ＝ 取り違え + フレーズではない動きの誤受理。</p>
          <table style={{ borderCollapse: "collapse" }}>
            <thead><tr><th>確信度≧</th><th>自動で発話する割合</th><th>その中の誤発話率</th><th>負例の誤受理</th></tr></thead>
            <tbody>{res.rejection.map((r) => (
              <tr key={r.conf}><td>{r.conf}</td><td>{pct(r.auto_rate)}（{frac(r.auto_rate)}）</td><td>{pct(r.wrong_rate)}（{frac(r.wrong_rate)}）</td><td>{frac(r.neg_accept)}</td></tr>))}</tbody>
          </table>
        </>
      )}
      <h3>実使用（認識画面で選ばれた結果）の日ごとの正解率</h3>
      {data.real_use.length === 0 ? <p>まだありません</p> : (
        <table><tbody>{data.real_use.map((r) => (
          <tr key={r.date}><td style={{ paddingRight: 16 }}>{r.date}</td><td>{r.n} 件 ／ 1 位 {r.top1}/{r.n} ／ 上位3 {r.top3}/{r.n}</td></tr>))}</tbody></table>
      )}
      <h3>モデルの版</h3>
      <ul>{data.models.versions.map((v) => (
        <li key={v}>{v === data.models.active ? "★ " : ""}{v}{" "}
          {v !== data.models.active && <BigButton style={{ minHeight: 36, fontSize: 14, minWidth: 0 }} onClick={() => api.activateModel(v).then(load).catch((e) => setError(e.message))}>この版を使う</BigButton>}</li>))}</ul>
      <p style={{ fontSize: 14, color: "#555" }}>学習はターミナルの <code>lipvoice train</code> で行います（画面からの実行は、のちのステップ）。</p>
      {error && <p role="alert" style={{ color: "crimson" }}>{error}</p>}
    </main>
  );
}
