interface Props {
  classes: string[];
  names: Record<string, string>;
  matrix: Record<string, Record<string, number>>;
}

/** 取り違え表。行が正解、列が1位の予想。対角線（正解）以外の数字は、取り違えた回数。 */
export function ConfusionTable({ classes, names, matrix }: Props) {
  const cell = { padding: "2px 8px", textAlign: "right" as const, border: "1px solid #ddd" };
  return (
    <table style={{ borderCollapse: "collapse", fontSize: 14 }}>
      <thead>
        <tr><th style={cell}>正解 ＼ 予想</th>{classes.map((c) => <th key={c} style={cell}>{names[c] ?? c}</th>)}</tr>
      </thead>
      <tbody>
        {classes.map((t) => (
          <tr key={t}>
            <th style={{ ...cell, textAlign: "left" }}>{names[t] ?? t}</th>
            {classes.map((p) => {
              const n = matrix[t]?.[p] ?? 0;
              return <td key={p} style={{ ...cell, background: n === 0 ? "#fff" : t === p ? "#cfc" : "#fcc", fontWeight: n && t !== p ? 700 : 400 }}>{n || ""}</td>;
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
