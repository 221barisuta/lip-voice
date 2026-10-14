/** 口の特徴点 1 点（正規化後）。 */
export type Point3 = [number, number, number];

export interface LandmarkFrame {
  /** 録画開始からの経過ミリ秒 */
  t: number;
  /** 口の特徴点（40 点）。顔が検出できなかったフレームは null */
  points: Point3[] | null;
  /** 表情係数 52 個（blendshape_names と同じ順）。未検出は null */
  blend: number[] | null;
}

export interface LandmarkFile {
  version: 1;
  lip_indices: number[];
  blendshape_names: string[];
  frames: LandmarkFrame[];
}
