import type { Phrase } from "../types/phrase";
import type { Stats } from "../types/live";

interface Props { stats: Stats; phrases: Phrase[] }

export function CollectStats({ stats, phrases }: Props) {
  const neg = Object.entries(stats.negatives);
  return (
    <div>
      <p style={{ fontSize: 20 }}>今日の録画数: <strong>{stats.today}</strong>（累計 {stats.total}）</p>
      <table>
        <tbody>
          {phrases.map((p) => (
            <tr key={p.id}>
              <td style={{ paddingRight: 16 }}>{p.text}</td>
              <td>{stats.per_phrase[p.id] ?? 0} 本</td>
            </tr>
          ))}
          {neg.map(([label, n]) => (
            <tr key={label} style={{ color: "#a60" }}>
              <td style={{ paddingRight: 16 }}>（負例）{label}</td>
              <td>{n} 本</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
