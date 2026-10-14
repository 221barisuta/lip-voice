import type { ClipStats } from "../types/clip";
import type { Phrase } from "../types/phrase";

interface Props { stats: ClipStats; phrases: Phrase[] }

export function CollectStats({ stats, phrases }: Props) {
  return (
    <div>
      <p style={{ fontSize: 20 }}>今日の録画数: <strong>{stats.today}</strong></p>
      <table>
        <tbody>
          {phrases.map((p) => (
            <tr key={p.id}>
              <td style={{ paddingRight: 16 }}>{p.text}</td>
              <td>{stats.per_phrase[p.id] ?? 0} 本</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
