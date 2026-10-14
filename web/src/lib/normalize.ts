import type { NormalizedLandmark } from "@mediapipe/tasks-vision";
import type { Point3 } from "../types/landmarks";
import { LIP_INDICES, mouthGeometry } from "./mouthRegion";

/**
 * 口の特徴点を正規化する（仕様 6.3）。
 *  - 口角の中点を原点にする
 *  - 両目尻の距離で大きさを揃える
 *  - 両目尻を結ぶ線が水平になるよう回転する
 * 顔の位置・距離・傾きが変わっても同じ値になる。
 */
export function normalizeMouth(lm: NormalizedLandmark[], w: number, h: number): Point3[] {
  const g = mouthGeometry(lm, w, h);
  const cos = Math.cos(-g.angle);
  const sin = Math.sin(-g.angle);
  const s = g.eyeDistance || 1;
  return LIP_INDICES.map((i) => {
    const dx = lm[i].x * w - g.center.x;
    const dy = lm[i].y * h - g.center.y;
    const dz = lm[i].z * w; // z は x と同じ尺度（MediaPipe の規約）
    return [(dx * cos - dy * sin) / s, (dx * sin + dy * cos) / s, dz / s] as Point3;
  });
}
