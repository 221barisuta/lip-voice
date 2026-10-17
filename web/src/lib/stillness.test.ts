import { describe, expect, it } from "vitest";
import { StillnessDetector, type StillnessConfig, type StopReason } from "./stillness";

const cfg: StillnessConfig = { threshold: 0.01, stillSec: 1.0, maxSec: 10 };

/** open(t) を fps で流し、最初に終了が返った時刻と理由を返す。 */
function run(open: (t: number) => number | null, fps = 30, c = cfg) {
  const d = new StillnessDetector(c);
  for (let i = 0; i < 20 * fps; i++) {
    const t = i / fps;
    const r: StopReason | null = d.push(t, open(t));
    if (r) return { t, reason: r };
  }
  return { t: Infinity, reason: null };
}

/** 0〜speakEnd 秒は大きく動き、その後は一定。 */
const speakThenStill = (speakEnd: number) => (t: number) =>
  t < speakEnd ? 0.08 + 0.07 * Math.sin(t * 12) : 0.02;

describe("StillnessDetector", () => {
  it("動き出す前の静止では終わらず、最大秒数で no_motion", () => {
    const r = run(() => 0.02);
    expect(r.reason).toBe("no_motion");
    expect(r.t).toBeCloseTo(10, 0);
  });

  it("話し終えて 1 秒で終わる", () => {
    const r = run(speakThenStill(2.0));
    expect(r.reason).toBe("still");
    expect(r.t).toBeGreaterThan(2.9);
    expect(r.t).toBeLessThan(3.2);
  });

  it("フレームレートが低くても同じ基準（10fps）", () => {
    const r = run(speakThenStill(2.0), 10);
    expect(r.reason).toBe("still");
    // 1.9 秒の標本がたまたま静止値に近いため、30fps より最大 0.1 秒早く判定されうる
    expect(r.t).toBeGreaterThanOrEqual(2.8);
    expect(r.t).toBeLessThan(3.3);
  });

  it("止まらなければ最大秒数で max", () => {
    const r = run((t) => 0.08 + 0.07 * Math.sin(t * 12));
    expect(r.reason).toBe("max");
    expect(r.t).toBeCloseTo(10, 0);
  });

  it("途中の短い休止（1 秒未満）では終わらない", () => {
    // 0〜1 秒話す → 0.6 秒休む → 再び話す → 6 秒で止まる
    const open = (t: number) =>
      t < 1 || (t >= 1.6 && t < 6) ? 0.08 + 0.07 * Math.sin(t * 12) : 0.02;
    const r = run(open);
    expect(r.reason).toBe("still");
    expect(r.t).toBeGreaterThan(6.9);
  });

  it("小さなノイズ（閾値以下）は静止とみなす", () => {
    const open = (t: number) => (t < 1.5 ? 0.1 * Math.abs(Math.sin(t * 9)) : 0.02 + 0.002 * Math.sin(t * 50));
    expect(run(open).reason).toBe("still");
  });

  it("閾値を上げると小さな動きは無視される", () => {
    const small = (t: number) => 0.02 + 0.01 * Math.sin(t * 12); // 変動幅 0.02
    expect(run(small, 30, { ...cfg, threshold: 0.01 }).reason).toBe("max");
    expect(run(small, 30, { ...cfg, threshold: 0.05 }).reason).toBe("no_motion");
  });

  it("顔を見失ったフレーム（null）は無視し、時間は進む", () => {
    const open = (t: number) => (t < 2 ? 0.08 + 0.07 * Math.sin(t * 12) : t < 2.5 ? null : 0.02);
    expect(run(open).reason).toBe("still");
  });

  it("静止秒数・最大秒数を変えられる", () => {
    const r = run(speakThenStill(2.0), 30, { ...cfg, stillSec: 2.0 });
    expect(r.t).toBeGreaterThan(3.9);
    expect(run(() => 0.08 + 0.07 * Math.sin(0), 30, { ...cfg, maxSec: 4 }).t).toBeCloseTo(4, 0);
  });
});
