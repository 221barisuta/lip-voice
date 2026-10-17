import type { NormalizedLandmark } from "@mediapipe/tasks-vision";

/** 口の輪郭（外側 20 点 + 内側 20 点）の Face Mesh インデックス。 */
export const LIP_INDICES: number[] = [
  61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 185, 40, 39, 37, 0, 267, 269, 270, 409,
  78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 191, 80, 81, 82, 13, 312, 311, 310, 415,
];

export const MOUTH_CORNER_L = 61;
export const MOUTH_CORNER_R = 291;
/** 左右の目尻（両目の間隔と傾きの基準） */
export const EYE_OUTER_R = 33;
export const EYE_OUTER_L = 263;

/** 内側の上唇・下唇（口の開きの測定に使う） */
export const LIP_INNER_UPPER = 13;
export const LIP_INNER_LOWER = 14;

export interface Px { x: number; y: number }

export interface MouthGeometry {
  center: Px;          // 口角の中点（px）
  mouthWidth: number;  // 口角間の距離（px）
  eyeDistance: number; // 目尻間の距離（px）
  angle: number;       // 目尻を結ぶ線の傾き（rad）
}

export function toPx(l: NormalizedLandmark, w: number, h: number): Px {
  return { x: l.x * w, y: l.y * h };
}

export function mouthGeometry(lm: NormalizedLandmark[], w: number, h: number): MouthGeometry {
  const a = toPx(lm[MOUTH_CORNER_L], w, h);
  const b = toPx(lm[MOUTH_CORNER_R], w, h);
  const er = toPx(lm[EYE_OUTER_R], w, h);
  const el = toPx(lm[EYE_OUTER_L], w, h);
  return {
    center: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 },
    mouthWidth: Math.hypot(a.x - b.x, a.y - b.y),
    eyeDistance: Math.hypot(er.x - el.x, er.y - el.y),
    angle: Math.atan2(el.y - er.y, el.x - er.x),
  };
}

/** 口の開き（上唇と下唇の距離）。目尻間の距離を 1 とした値で、顔の位置・距離が変わっても同じ尺度。 */
export function mouthOpening(lm: NormalizedLandmark[], w: number, h: number): number {
  const u = toPx(lm[LIP_INNER_UPPER], w, h);
  const l = toPx(lm[LIP_INNER_LOWER], w, h);
  const eye = mouthGeometry(lm, w, h).eyeDistance || 1;
  return Math.hypot(u.x - l.x, u.y - l.y) / eye;
}
