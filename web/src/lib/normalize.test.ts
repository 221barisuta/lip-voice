import { describe, expect, it } from "vitest";
import type { NormalizedLandmark } from "@mediapipe/tasks-vision";
import { normalizeMouth } from "./normalize";
import { LIP_INDICES } from "./mouthRegion";

/** 仮顔。画素空間で (cx,cy) に置き、scale 倍し、rot だけ傾けてから 0〜1 に正規化する。 */
function fakeFace(cx: number, cy: number, scale: number, rot: number, w: number, h: number): NormalizedLandmark[] {
  const lm: NormalizedLandmark[] = Array.from({ length: 478 }, () => ({ x: 0, y: 0, z: 0, visibility: 1 }));
  const put = (i: number, x: number, y: number, z = 0) => {
    const c = Math.cos(rot), s = Math.sin(rot);
    const px = cx * w + scale * h * (x * c - y * s);
    const py = cy * h + scale * h * (x * s + y * c);
    lm[i] = { x: px / w, y: py / h, z: (z * scale * h) / w, visibility: 1 };
  };
  put(33, -0.10, -0.1); put(263, 0.10, -0.1); // 目尻
  put(61, -0.04, 0.12); put(291, 0.04, 0.12); // 口角
  LIP_INDICES.forEach((i, k) => { if (i !== 61 && i !== 291) put(i, -0.03 + 0.0015 * k, 0.12 + 0.01 * (k % 3), 0.01); });
  return lm;
}

describe("normalizeMouth", () => {
  it("位置・大きさ・傾きが違っても同じ値になる", () => {
    const w = 640, h = 480;
    const a = normalizeMouth(fakeFace(0.5, 0.5, 1, 0, w, h), w, h);
    const b = normalizeMouth(fakeFace(0.4, 0.55, 0.6, 0.3, w, h), w, h);
    a.forEach((p, i) => p.forEach((v, k) => expect(b[i][k]).toBeCloseTo(v, 1)));
  });
  it("口角の中点が原点", () => {
    const p = normalizeMouth(fakeFace(0.5, 0.5, 1, 0, 640, 480), 640, 480);
    const l = p[LIP_INDICES.indexOf(61)], r = p[LIP_INDICES.indexOf(291)];
    expect((l[0] + r[0]) / 2).toBeCloseTo(0, 5);
    expect((l[1] + r[1]) / 2).toBeCloseTo(0, 5);
  });
});
