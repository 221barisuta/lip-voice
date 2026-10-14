import type { MouthGeometry } from "./mouthRegion";

export const CROP_SIZE = 96;

/** カメラ映像から口元を 96×96 グレースケールに切り出す。顔全体はこの canvas に含まれない。 */
export class MouthCropper {
  readonly canvas = document.createElement("canvas");
  private ctx: CanvasRenderingContext2D;
  private state: { cx: number; cy: number; side: number; angle: number } | null = null;

  constructor() {
    this.canvas.width = this.canvas.height = CROP_SIZE;
    this.ctx = this.canvas.getContext("2d", { willReadFrequently: true })!;
  }

  /** g を渡すと切り出し位置を更新（なめらかに追従）。null なら直前の位置で描く。 */
  draw(video: HTMLVideoElement, g: MouthGeometry | null): void {
    if (g) {
      const side = Math.max(g.mouthWidth * 2.0, g.eyeDistance * 0.7);
      const s = this.state;
      const a = 0.5; // 追従の強さ（小さいほど滑らか）
      this.state = s
        ? {
            cx: s.cx + a * (g.center.x - s.cx),
            cy: s.cy + a * (g.center.y - s.cy),
            side: s.side + a * (side - s.side),
            angle: s.angle + a * (g.angle - s.angle),
          }
        : { cx: g.center.x, cy: g.center.y, side, angle: g.angle };
    }
    const s = this.state;
    if (!s) return;
    const { ctx } = this;
    ctx.save();
    ctx.fillStyle = "#000";
    ctx.fillRect(0, 0, CROP_SIZE, CROP_SIZE);
    ctx.translate(CROP_SIZE / 2, CROP_SIZE / 2);
    ctx.scale(CROP_SIZE / s.side, CROP_SIZE / s.side);
    ctx.rotate(-s.angle); // 目尻の線が水平になるよう傾きを補正
    ctx.translate(-s.cx, -s.cy);
    ctx.drawImage(video, 0, 0);
    ctx.restore();
    const img = ctx.getImageData(0, 0, CROP_SIZE, CROP_SIZE);
    const d = img.data;
    for (let i = 0; i < d.length; i += 4) {
      const y = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
      d[i] = d[i + 1] = d[i + 2] = y;
    }
    ctx.putImageData(img, 0, 0);
  }

  reset(): void {
    this.state = null;
  }
}
