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
    cfg = FeatureConfig(use_duration=args.use_duration, active_threshold=holder.get().active_threshold)
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


def _transfer_error(fn):
    from .transfer import TransferError
    try:
        return fn()
    except TransferError as e:
        print(f"中止しました: {e}", file=sys.stderr)
        return 1


def cmd_export(args) -> int:
    from . import transfer
    from .settings import SettingsHolder
    p = _paths(args)
    if not p.db.exists():
        print("このプロフィールにはデータがありません")
        return 1

    def go():
        out = transfer.export(p, SettingsHolder(p.config).get(), Path(args.out), with_video=args.with_video,
                              models=not args.no_models, db=not args.models_only, force=args.force)
        print(f"書き出しました: {out}")
        return 0
    return _transfer_error(go)


def cmd_import(args) -> int:
    from . import transfer

    def go():
        t = transfer.import_profile(Path(args.src), home_dir() if not args.home else Path(args.home).expanduser(), args.as_profile)
        print(f"取り込みました: {t.root}（確認: lipvoice --profile {t.profile} check）")
        return 0
    return _transfer_error(go)


def cmd_import_models(args) -> int:
    from . import transfer
    p = _paths(args)

    def go():
        added = transfer.import_models(Path(args.src), p, activate=args.activate)
        print(f"追加したモデル: {', '.join(added) or '（すべて取り込み済み）'}"
              + ("。使うモデルに設定しました" if args.activate else "。使うには lipvoice models --activate <版>"))
        print("起動中の場合は、LipVoice を再起動してください")
        return 0
    return _transfer_error(go)


def cmd_bench(args) -> int:
    """実機（患者さんの PC）での Day 0 の確認（処理は bench.py）。"""
    from .bench import run
    from .settings import SettingsHolder
    p = _paths(args)
    holder = SettingsHolder(p.config)
    if args.source:
        holder.update({"camera_source": args.source})
    return run(p, holder.get(), args.seconds, args.speech_seconds)


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
    ex = sub.add_parser("export", help="データを 1 つのフォルダにまとめて書き出す（USB での持ち出し用）")
    ex.add_argument("out", help="書き出し先のフォルダ（この中に lipvoice-export-... ができる）")
    ex.add_argument("--with-video", action="store_true", help="口元の動画も含める（既定は特徴点だけ）")
    ex.add_argument("--no-models", action="store_true")
    ex.add_argument("--models-only", action="store_true", help="モデルだけを書き出す（Mac → 患者さんの PC）")
    ex.add_argument("--force", action="store_true", help="試験用の撮影日の上書きが設定されていても書き出す")
    ex.set_defaults(fn=cmd_export)
    im = sub.add_parser("import", help="書き出したフォルダを、空のプロフィールに取り込む（--home の下に作る）")
    im.add_argument("src")
    im.add_argument("--as-profile", help="取り込み先のプロフィール名（既定: 書き出し元と同じ）")
    im.set_defaults(fn=cmd_import)
    imm = sub.add_parser("import-models", help="書き出したフォルダから、学習済みモデルの版だけを追加する")
    imm.add_argument("src")
    imm.add_argument("--activate", action="store_true", help="取り込んだ最新の版を使う")
    imm.set_defaults(fn=cmd_import_models)
    b = sub.add_parser("bench", help="1 フレームあたりの処理時間を測る（実機での負荷の確認用）")
    b.add_argument("--seconds", type=float, default=20, help="静止の測定の秒数")
    b.add_argument("--speech-seconds", type=float, default=10, help="口パクの測定の秒数（0 で省略）")
    b.add_argument("--source", help="カメラ番号、または動画ファイル")
    b.set_defaults(fn=cmd_bench)
    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
