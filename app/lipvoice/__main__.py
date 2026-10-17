import argparse
import os
import secrets
import sys
import urllib.request
from pathlib import Path

from .paths import Paths, home_dir

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/"
             "float16/1/face_landmarker.task")


def _paths(args) -> Paths:
    return Paths(Path(args.home).expanduser() if args.home else home_dir(), args.profile).ensure()


def cmd_fetch_models(args) -> int:
    p = _paths(args)
    if p.model_file.exists() and not args.force:
        print(f"すでにあります: {p.model_file}")
        return 0
    print("顔検出のモデルを取得します（初回だけネットが必要です）...")
    tmp = p.model_file.with_suffix(".part")
    urllib.request.urlretrieve(MODEL_URL, tmp)
    os.replace(tmp, p.model_file)
    print(f"保存しました: {p.model_file}")
    return 0


def cmd_check(args) -> int:
    from .settings import SettingsHolder
    from .storage import integrity
    from .storage.store import Store
    p = _paths(args)
    holder = SettingsHolder(p.config)
    store = Store(p, holder.get)
    rep = integrity.check(store, repair=args.repair)
    print(f"クリップ {len(store.clip_rows())} 件 / 欠損 {len(rep.missing_files)} / 孤児 {len(rep.orphan_files)} / "
          f"書き込み途中 {len(rep.stale_tmp)}" + (f" / 退避 {rep.moved}" if args.repair else ""))
    return 0 if rep.ok or args.repair else 1


def cmd_cameras(_args) -> int:
    import cv2
    found = []
    for i in range(6):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ok, img = cap.read()
            found.append((i, f"{img.shape[1]}x{img.shape[0]}" if ok else "映像なし"))
        cap.release()
    for i, d in found:
        print(f"camera_source = {i}   ({d})")
    if not found:
        print("カメラが見つかりません")
    return 0 if found else 1


def cmd_bench(args) -> int:
    """1 フレームあたりの処理時間を測る。実機（患者さんの PC）で、検出の頻度を決める材料にする。"""
    import statistics
    import time

    from .capture import open_source
    from .settings import SettingsHolder
    from .vision.crop import MouthCropper
    from .vision.geometry import Landmarks, mouth_geometry, mouth_opening
    from .vision.landmarker import FaceDetector

    p = _paths(args)
    holder = SettingsHolder(p.config)
    if args.source:
        holder.update({"camera_source": args.source})
    if not p.model_file.exists():
        print("モデルがありません。先に: lipvoice fetch-models")
        return 1
    src, det, cropper = open_source(holder.get()), FaceDetector(p.model_file), MouthCropper()
    detect_ms, other_ms, found = [], [], 0
    cpu0, wall0 = time.process_time(), time.perf_counter()
    while time.perf_counter() - wall0 < args.seconds:
        fr = src.read()
        if fr is None:
            continue
        t = time.perf_counter()
        d = det.detect(fr.image, fr.t * 1000)
        detect_ms.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        if d is not None:
            found += 1
            h, w = fr.image.shape[:2]
            lm = Landmarks(d.points)
            g = mouth_geometry(lm, w, h)
            mouth_opening(lm, w, h)
            cropper.update(g)
            cropper.crop(fr.image)
        other_ms.append((time.perf_counter() - t) * 1000)
    wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
    src.close()
    det.close()
    n = len(detect_ms)
    q = lambda xs, f: sorted(xs)[min(len(xs) - 1, int(len(xs) * f))]
    print(f"{src.description}: {n} フレーム / {wall:.1f} 秒 = {n / wall:.1f} fps（顔を検出できた割合 {found / max(n, 1):.0%}）")
    print(f"顔検出  平均 {statistics.mean(detect_ms):.1f} ms / 95% {q(detect_ms, .95):.1f} ms")
    print(f"その他（口の計算・切り出し） 平均 {statistics.mean(other_ms):.2f} ms")
    print(f"このプログラムの CPU 使用: 1 コア換算で {cpu / wall:.0%}（カメラが 30fps なら、実運用ではこれ以下）")
    return 0


def cmd_run(args) -> int:
    import uvicorn

    from .api.app import create_app
    from .collect import CollectSession
    from .engine import Engine
    from .settings import SettingsHolder
    from .storage import integrity
    from .storage.store import Store

    p = _paths(args)
    holder = SettingsHolder(p.config)
    if args.source:
        holder.update({"camera_source": args.source})
    store = Store(p, holder.get)
    rep = integrity.check(store, repair=True)
    if rep.moved or rep.missing_files:
        print(f"整合性: 孤児 {rep.moved} 件を退避、欠損 {len(rep.missing_files)} 件", file=sys.stderr)
    collect = CollectSession(store, holder.get)
    engine = Engine(p.model_file, holder.get, collect)
    token = os.environ.get("LIPVOICE_TOKEN") or secrets.token_urlsafe(24)
    static = Path(__file__).parent / "static"
    dev_origins = ["http://localhost:5173", "http://127.0.0.1:5173"] if args.dev else None
    app = create_app(engine, store, collect, holder, port=args.port, token=token, static_dir=static,
                     dev_origins=dev_origins)
    engine.start()
    url = f"http://127.0.0.1:{args.port}/"
    print(f"起動しました: {url}   （データ: {p.root}）")
    if args.open:
        import webbrowser
        webbrowser.open(url)
    try:
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        engine.stop()
        store.close()
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(prog="lipvoice")
    ap.add_argument("--home", help="データの置き場所（既定: ~/LipVoice）")
    ap.add_argument("--profile", default="default", help="利用者ごとのフォルダ名")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="アプリを起動する")
    r.add_argument("--port", type=int, default=8765)
    r.add_argument("--source", help="カメラ番号、または動画ファイル（試験用）")
    r.add_argument("--open", action="store_true", help="ブラウザを開く")
    r.add_argument("--dev", action="store_true", help="開発用（Vite の画面 localhost:5173 からの接続を許可）")
    r.set_defaults(fn=cmd_run)
    f = sub.add_parser("fetch-models", help="顔検出のモデルを取得する（初回だけネットが必要）")
    f.add_argument("--force", action="store_true")
    f.set_defaults(fn=cmd_fetch_models)
    c = sub.add_parser("check", help="データの整合性を検査する")
    c.add_argument("--repair", action="store_true", help="孤児ファイルを退避し、書き込み途中のファイルを消す")
    c.set_defaults(fn=cmd_check)
    sub.add_parser("cameras", help="使えるカメラを一覧する").set_defaults(fn=cmd_cameras)
    b = sub.add_parser("bench", help="1 フレームあたりの処理時間を測る（実機での負荷の確認用）")
    b.add_argument("--seconds", type=float, default=20)
    b.add_argument("--source", help="カメラ番号、または動画ファイル")
    b.set_defaults(fn=cmd_bench)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
