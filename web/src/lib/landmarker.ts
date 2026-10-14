import { FaceLandmarker, FilesetResolver } from "@mediapipe/tasks-vision";

let instance: Promise<FaceLandmarker> | null = null;

/** Face Landmarker を 1 度だけ作る。wasm とモデルは自前配信（public/mediapipe/）。 */
export function getLandmarker(): Promise<FaceLandmarker> {
  instance ??= (async () => {
    const fileset = await FilesetResolver.forVisionTasks("/mediapipe/wasm");
    const create = (delegate: "GPU" | "CPU") =>
      FaceLandmarker.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: "/mediapipe/face_landmarker.task", delegate },
        runningMode: "VIDEO",
        numFaces: 1,
        outputFaceBlendshapes: true,
      });
    // GPU が使えない環境では CPU にフォールバックする
    return create("GPU").catch(() => create("CPU"));
  })();
  instance.catch(() => (instance = null)); // 失敗したら次回やり直せるようにする
  return instance;
}
