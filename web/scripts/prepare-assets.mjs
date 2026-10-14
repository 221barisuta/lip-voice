// MediaPipe の wasm とモデルを自前配信用に public/mediapipe/ へ置く（CDN に依存しない）。
import { cpSync, existsSync, mkdirSync, writeFileSync } from "node:fs";

const MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
const out = "public/mediapipe";
mkdirSync(out, { recursive: true });
cpSync("node_modules/@mediapipe/tasks-vision/wasm", `${out}/wasm`, { recursive: true });

if (!existsSync(`${out}/face_landmarker.task`)) {
  const res = await fetch(MODEL_URL);
  if (!res.ok) throw new Error(`モデルの取得に失敗: ${res.status}`);
  writeFileSync(`${out}/face_landmarker.task`, Buffer.from(await res.arrayBuffer()));
}
console.log("MediaPipe assets ready");
