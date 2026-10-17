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
    with urllib.request.urlopen(MODEL_URL, timeout=60) as r, open(tmp, "wb") as f:
        f.write(r.read())
    if tmp.stat().st_size < 1_000_000:
        tmp.unlink()
        raise SystemExit("モデルの取得に失敗しました（ファイルが小さすぎます）")
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


def _store(args):
    from .settings import SettingsHolder
    from .storage.store import Store
    p = _paths(args)
    holder = SettingsHolder(p.config)
    return p, holder, Store(p, holder.get)


def cmd_synth(args) -> int:
    """合成データで学習・評価の流れを試す。実データのプロフィールには入れない（名前が synth で始まるものだけ）。"""
    from .ml.synthetic import generate_into_store
    p, holder, store = _store(args)
    if not args.profile.startswith("synth") and not args.force:
        print("合成データは、名前が synth で始まるプロフィールにだけ入れられます（例: --profile synth）")
        return 1
    per_day = [int(v) for v in args.per_day.split(",")]
    ids = [ph["id"] for ph in store.phrases()]
    n = generate_into_store(store, per_day, ids, {"あくび": 6, "咳": 6, "口を湿らせる": 6}, seed=args.seed)
    print(f"合成データを {n} 本作りました（{len(per_day)} 日分）: {p.root}")
    return 0


def cmd_train(args) -> int:
    from .ml.features import FeatureConfig
    from .ml.train import run_training
    p, holder, store = _store(args)
    cfg = FeatureConfig(use_duration=args.use_duration)
    rep = run_training(store, p, cfg, epochs=args.epochs, seed=args.seed, use_cnn=not args.no_cnn,
                       sources=tuple(args.sources.split(",")), activate=not args.no_activate, force_active=args.active)
    print(f"学習済みモデル: {rep['version']}（使うモデル: {rep['active']}）  {rep['seconds']} 秒")
    for k, r in rep.get("results", {}).items():
        m = r["lodo"]
        print(f"  {k}: 上位1 {m['top1']['k']}/{m['top1']['n']}  上位3 {m['top3']['k']}/{m['top3']['n']}  棄却の閾値 {r['tau']:.3f}")
    if rep.get("note"):
        print("  " + rep["note"])
    print(f"レポート: {p.models / 'reports' / 'latest.json'}")
    return 0


def cmd_models(args) -> int:
    from .ml.model_store import active_version, set_active, versions
    p = _paths(args)
    if args.activate:
        set_active(p.models, args.activate)
        print(f"使うモデルを {args.activate} にしました")
        return 0
    act = active_version(p.models)
    for v in versions(p.models):
        print(("* " if v == act else "  ") + v)
    return 0


def cmd_bench(args) -> int:
    """実機（患者さんの PC）での Day 0 の確認。顔の検出率、fps、1 フレームの処理時間、顔の傾き、静止時の口の動きのノイズを測る。
    測っている間は、カメラの正面で、口を閉じて（または楽にして）静止してください。"""
    import statistics
    import time

    from .capture import open_source
    from .settings import SettingsHolder
    from .vision.crop import MouthCropper
    from .vision.geometry import Landmarks, mouth_geometry, mouth_opening, mouth_width_ratio
    from .vision.landmarker import FaceDetector
    from .vision.stillness import StillnessConfig, StillnessDetector

    p = _paths(args)
    holder = SettingsHolder(p.config)
    if args.source:
        holder.update({"camera_source": args.source})
    if not p.model_file.exists():
        print("モデルがありません。先に: lipvoice fetch-models")
        return 1
    s = holder.get()
    src = open_source(s)
    det = FaceDetector(p.model_file, s.face_detection_confidence, s.face_presence_confidence, s.tracking_confidence)
    cropper, live = MouthCropper(), StillnessDetector(StillnessConfig(float("inf"), 1.0, float("inf")))
    detect_ms, other_ms, tilts, rolls, noise, found = [], [], [], [], [], 0
    cpu0, wall0 = time.process_time(), time.perf_counter()
    while time.perf_counter() - wall0 < args.seconds:
        fr = src.read()
        if fr is None:
            continue
        t = time.perf_counter()
        img = fr.image
        d = det.detect(img, fr.t * 1000)
        detect_ms.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        if d is not None:
            found += 1
            h, w = img.shape[:2]
            lm = Landmarks(d.points)
            g = mouth_geometry(lm, w, h)
            live.push(fr.t, (mouth_opening(lm, w, h), mouth_width_ratio(lm, w, h)))
            if time.perf_counter() - wall0 > 3:           # 最初の 3 秒は落ち着くまで除く
                noise.append(live.range)
            cropper.update(g)
            cropper.crop(img)
            if d.tilt_deg is not None:
                tilts.append(d.tilt_deg)
                rolls.append(abs(d.roll_deg or 0.0))
        other_ms.append((time.perf_counter() - t) * 1000)
    wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
    desc = src.description
    src.close()
    det.close()
    n = len(detect_ms)
    q = lambda xs, f: sorted(xs)[min(len(xs) - 1, int(len(xs) * f))]
    fps, ratio = n / wall, found / max(n, 1)
    print(f"{desc}: {n} フレーム / {wall:.1f} 秒 = {fps:.1f} fps（顔を検出できた割合 {ratio:.0%}）")
    print(f"顔検出  平均 {statistics.mean(detect_ms):.1f} ms / 95% {q(detect_ms, .95):.1f} ms")
    print(f"その他（口の計算・切り出し） 平均 {statistics.mean(other_ms):.2f} ms")
    print(f"このプログラムの CPU 使用: 1 コア換算で {cpu / wall:.0%}（カメラが 30fps なら、実運用ではこれ以下）")
    tilt = statistics.median(tilts) if tilts else None
    roll = statistics.median(rolls) if rolls else None
    floor = q(noise, .95) if noise else None
    if tilt is not None:
        print(f"顔の正面からの傾き（中央値）{tilt:.0f}°、画像の中での回転 {roll:.0f}°（検出器の守備範囲は約 45° 以内）")
    if floor is not None:
        print(f"静止時の口の動き（ノイズ）95% {floor:.4f}（録画の閾値の初期値 0.01 はこれより十分大きい必要があります）")
    ok = lambda v: "OK" if v else "要対応"
    print("--- Day 0 の目安 ---")
    print(f"検出率 95% 以上: {ok(ratio >= 0.95)} / fps 15 以上: {ok(fps >= 15)} / 顔検出 50ms 以下: {ok(q(detect_ms, .95) <= 50)}"
          + (f" / 傾き 35° 以下: {ok(tilt <= 35)}" if tilt is not None else "")
          + (f" / 回転 35° 以下: {ok(roll <= 35)}" if roll is not None else "")
          + (f" / ノイズ 0.005 以下: {ok(floor <= 0.005)}" if floor is not None else ""))
    if ratio < 0.5 and roll is None:
        print("顔がほとんど検出できません。カメラの向き（上下逆なら camera_rotate を 180 に）、角度、明るさ、遮蔽を確認してください")
    return 0


def _lower_priority() -> None:
    """Windows では、視線入力ソフトを優先するため、このプログラムの優先度を少し下げる。"""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), 0x4000)  # BELOW_NORMAL
        except Exception:
            pass


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
    from .speak import SpeakSession
    collect = CollectSession(store, holder.get)
    speak = SpeakSession(store, holder.get, p.models)
    engine = Engine(p.model_file, holder.get, collect, speak=speak)
    # 固定のトークンは開発用（--dev）の時だけ。通常は起動のたびに作る
    token = (os.environ.get("LIPVOICE_TOKEN") if args.dev else None) or secrets.token_urlsafe(24)
    _lower_priority()
    static = Path(__file__).parent / "static"
    dev_origins = ["http://localhost:5173", "http://127.0.0.1:5173"] if args.dev else None
    app = create_app(engine, store, collect, holder, port=args.port, token=token, static_dir=static,
                     dev_origins=dev_origins, speak=speak, models_root=p.models)
    engine.start()
    url = f"http://127.0.0.1:{args.port}/"
    print(f"起動しました: {url}   （データ: {p.root}）")
    if args.open:
        import webbrowser
        webbrowser.open(url)
    try:
        # 画面を開いたまま Ctrl+C しても止まるように、接続の待ち時間を短くする（常時つながる配信があるため）
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning", timeout_graceful_shutdown=2)
    finally:
        stopped = engine.stop()
        store.close()
        if not stopped:
            # カメラの処理が戻ってこない時（許可待ちなど）に、プロセスが残らないよう終了する。データは閉じ済み
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(0)
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
    sy = sub.add_parser("synth", help="合成データを作る（試験用。profile 名が synth で始まるものだけ）")
    sy.add_argument("--per-day", default="10,10,5", help="日ごとのフレーズあたりの本数（例 10,10,5）")
    sy.add_argument("--seed", type=int, default=0)
    sy.add_argument("--force", action="store_true")
    sy.set_defaults(fn=cmd_synth)
    tr = sub.add_parser("train", help="学習と評価（日ごとの交差検証）。学習済みモデルを保存する")
    tr.add_argument("--epochs", type=int, default=60)
    tr.add_argument("--seed", type=int, default=0)
    tr.add_argument("--no-cnn", action="store_true", help="段階 A（DTW）だけ")
    tr.add_argument("--use-duration", action="store_true", help="録画の長さを特徴に加える")
    tr.add_argument("--sources", default="collect", help="学習に使う由来（既定 collect。実使用は use）")
    tr.add_argument("--no-activate", action="store_true")
    tr.add_argument("--active", choices=["A", "B"], help="使うモデルを指定（既定は成績の良い方）")
    tr.set_defaults(fn=cmd_train)
    md = sub.add_parser("models", help="学習済みモデルの版の一覧・切り替え（ロールバック）")
    md.add_argument("--activate", help="この版を使う")
    md.set_defaults(fn=cmd_models)
    b = sub.add_parser("bench", help="1 フレームあたりの処理時間を測る（実機での負荷の確認用）")
    b.add_argument("--seconds", type=float, default=20)
    b.add_argument("--source", help="カメラ番号、または動画ファイル")
    b.set_defaults(fn=cmd_bench)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
