export interface StillnessConfig {
  /** 口の開き（目尻間の距離を 1 とした値）の変動幅がこれ以下なら「止まっている」 */
  threshold: number;
  /** 止まった状態がこの秒数続いたら録画を終える */
  stillSec: number;
  /** 止まらなくてもこの秒数で終える */
  maxSec: number;
}

export type StopReason = "still" | "max" | "no_motion";

interface Sample { t: number; v: number }

/**
 * 口の開きの時系列から「話し終えたか」を判定する。
 *  - 直近 stillSec 秒間の開きの変動幅（最大 − 最小）が threshold 以下なら静止とみなす
 *  - 一度動き出すまでは判定しない（録画開始直後の静止で終わらないように）
 *  - 時刻（秒）で数えるので、フレームレートが変わっても同じ基準で動く
 */
export class StillnessDetector {
  private samples: Sample[] = [];
  private moved = false;

  constructor(private cfg: StillnessConfig) {}

  get hasMoved(): boolean {
    return this.moved;
  }

  /** 直近 stillSec 秒間の開きの変動幅（画面表示・調整用） */
  get range(): number {
    if (this.samples.length < 2) return 0;
    let lo = Infinity, hi = -Infinity;
    for (const s of this.samples) { lo = Math.min(lo, s.v); hi = Math.max(hi, s.v); }
    return hi - lo;
  }

  /** t: 録画開始からの秒。v: 口の開き（顔を見失ったら null）。終了すべきなら理由を返す。 */
  push(t: number, v: number | null): StopReason | null {
    if (v !== null) {
      this.samples.push({ t, v });
      // 窓（直近 stillSec 秒）の手前の 1 点は残す。窓の端まで観測できたかを知るため。
      const cutoff = t - this.cfg.stillSec;
      while (this.samples.length > 1 && this.samples[1].t <= cutoff) this.samples.shift();
      if (this.range > this.cfg.threshold) this.moved = true;
    }
    if (t >= this.cfg.maxSec) return this.moved ? "max" : "no_motion";
    const covered = this.samples.length > 0 && this.samples[0].t <= t - this.cfg.stillSec;
    if (this.moved && covered && this.range <= this.cfg.threshold) return "still";
    return null;
  }
}
