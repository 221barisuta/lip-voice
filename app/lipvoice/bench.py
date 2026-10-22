"""実機（患者さんの PC）での Day 0 の確認。

1 段目: 口を閉じて静止して、顔の検出率・fps・処理時間・顔の傾き・静止時の口の動き（ノイズ）を測る。
2 段目: 家族の合図で、フレーズを口パクして、口パク時の動きを測り、SNR と閾値の候補を出す。
結果は logs/bench-<日時>.json に保存する（顔の画像は含まない）。
"""
import json
import statistics
import sys
import time
from datetime import datetime

from .calibrate import percentile, suggest
from .capture import open_source
from .paths import Paths
from .settings import Settings
from .vision.crop import MouthCropper
from .vision.geometry import Landmarks, mouth_geometry, mouth_opening, mouth_width_ratio
from .vision.landmarker import FaceDetector
from .vision.rotate import ROTATIONS, rotate_image
from .vision.stillness import StillnessConfig, StillnessDetector

SETTLE_SEC = 3.0            # 最初の 3 秒は落ち着くまで除く（口パクの段階は、前の合図の後なので 1 秒）


def _measure(src, det, cropper, live, seconds: float, settle: float, rotate: int = 0) -> dict:
    detect_ms, other_ms, tilts, rolls, ranges, found = [], [], [], [], [], 0
    cpu0, wall0 = time.process_time(), time.perf_counter()
    while time.perf_counter() - wall0 < seconds:
        fr = src.read()
        if fr is None:
            continue
        t = time.perf_counter()
        img = rotate_image(fr.image, rotate)
        d = det.detect(img, fr.t * 1000)
        detect_ms.append((time.perf_counter() - t) * 1000)
        t = time.perf_counter()
        if d is not None:
            found += 1
            h, w = img.shape[:2]
            lm = Landmarks(d.points)
            g = mouth_geometry(lm, w, h)
            live.push(fr.t, (mouth_opening(lm, w, h), mouth_width_ratio(lm, w, h)))
            if time.perf_counter() - wall0 > settle:
                ranges.append(live.range)
            cropper.update(g)
            cropper.crop(img)
            if d.tilt_deg is not None:
                tilts.append(d.tilt_deg)
                rolls.append(abs(d.roll_deg or 0.0))
        other_ms.append((time.perf_counter() - t) * 1000)
    wall, cpu = time.perf_counter() - wall0, time.process_time() - cpu0
    n = len(detect_ms)
    return {"frames": n, "seconds": wall, "fps": n / wall if wall else 0.0, "face_ratio": found / max(n, 1),
            "detect_ms_mean": statistics.mean(detect_ms) if detect_ms else 0.0,
            "detect_ms_p95": percentile(detect_ms, .95) if detect_ms else 0.0,
            "other_ms_mean": statistics.mean(other_ms) if other_ms else 0.0,
            "cpu_core_ratio": cpu / wall if wall else 0.0,
            "tilt_median": statistics.median(tilts) if tilts else None,
            "roll_median": statistics.median(rolls) if rolls else None, "ranges": ranges}


def probe_rotation(src, model_file, s: Settings, make_detector=FaceDetector, frames: int = 12, gap_sec: float = 0.25) -> dict:
    """顔が見つからない時に、映像の向き（0/90/180/270°）ごとに検出できる枚数を数える。カメラの向き・取り付けの確認用。"""
    imgs, last = [], 0.0
    t0 = time.perf_counter()
    while len(imgs) < frames and time.perf_counter() - t0 < frames * gap_sec * 4:
        fr = src.read()
        if fr is not None and fr.t - last >= gap_sec:
            imgs.append(fr.image)
            last = fr.t
    conf = min(s.face_detection_confidence, 0.3)                  # 向きの確認は、検出の確信度を下げて試す
    counts, rolls = {}, {}
    for deg in ROTATIONS:
        det = make_detector(model_file, conf, min(s.face_presence_confidence, 0.3), min(s.tracking_confidence, 0.3))
        found = [d for i, im in enumerate(imgs) if (d := det.detect(rotate_image(im, deg), i * 100.0)) is not None]
        det.close()
        counts[deg] = len(found)
        rs = [abs(d.roll_deg) for d in found if getattr(d, "roll_deg", None) is not None]
        rolls[deg] = round(statistics.median(rs), 1) if rs else None
    n = len(imgs)
    # 検出器は 90° 倒れた顔も見つけることがあるので、検出の枚数ではなく、顔が「立って」見える向き（画像内の回転が最小）を選ぶ
    ok = [d for d in ROTATIONS if counts[d] >= max(2, n // 2) and (rolls[d] is None or rolls[d] <= 45)]
    best = min(ok, key=lambda d: (rolls[d] if rolls[d] is not None else 0.0, d != 0)) if ok else None
    return {"frames": n, "counts": counts, "rolls": rolls, "best": best}


def _wait_for_cue(seconds_if_no_tty: float = 3.0) -> None:
    if sys.stdin is not None and sys.stdin.isatty():
        input("家族の合図で Enter を押すと、口パクの測定が始まります（フレーズを 3 回、ふだんどおり口パク）> ")
    else:
        print(f"{seconds_if_no_tty:.0f} 秒後に口パクの測定を始めます")
        time.sleep(seconds_if_no_tty)


def _grade(label: str, value: str, ok: bool | None, warn: bool = False) -> str:
    mark = "—" if ok is None else ("OK" if ok else ("条件付き" if warn else "要対応"))
    return f"  {label}: {value}  → {mark}"


def run(p: Paths, s: Settings, seconds: float, speech_seconds: float) -> int:
    if not p.model_file.exists():
        print("モデルがありません。先に: lipvoice fetch-models")
        return 1
    src = open_source(s)
    det = FaceDetector(p.model_file, s.face_detection_confidence, s.face_presence_confidence, s.tracking_confidence)
    cropper = MouthCropper()
    live = StillnessDetector(StillnessConfig(float("inf"), s.still_sec, float("inf")))
    print(f"カメラ: {src.description}")
    print(f"[1/2] 口を閉じて（楽にして）静止してください。{seconds:.0f} 秒測ります")
    a = _measure(src, det, cropper, live, seconds, SETTLE_SEC, s.camera_rotate)
    b = probe = None
    sideways = (a["roll_median"] or 0) > 45         # 検出はできても顔が倒れて見える（検出器の守備範囲を超えている）
    if a["face_ratio"] < 0.5 or sideways:           # 顔が見つからない・倒れて見える時は、口パクの測定に進まず、映像の向きを調べる
        print("顔が見つからない（または倒れて見える）ので、映像の向き（0/90/180/270°）ごとに調べます…")
        probe = probe_rotation(src, p.model_file, s)
    elif speech_seconds > 0:
        _wait_for_cue()
        print(f"[2/2] フレーズを口パクしてください。{speech_seconds:.0f} 秒測ります")
        b = _measure(src, det, cropper, live, speech_seconds, 1.0, s.camera_rotate)
    src.close()
    det.close()

    sug = suggest(a["ranges"], b["ranges"] if b else None, s.still_sec)
    tilt, roll = a["tilt_median"], a["roll_median"]
    print("")
    print(f"{a['frames']} フレーム / {a['seconds']:.1f} 秒 = {a['fps']:.1f} fps、顔を検出できた割合 {a['face_ratio']:.0%}")
    print(f"顔検出 平均 {a['detect_ms_mean']:.1f} ms / 95% {a['detect_ms_p95']:.1f} ms、その他 平均 {a['other_ms_mean']:.2f} ms")
    print(f"このプログラムの CPU 使用: 1 コア換算で {a['cpu_core_ratio']:.0%}")
    print("--- Day 0 の目安 ---")
    r = a["face_ratio"]
    print(_grade("顔の検出率", f"{r:.0%}（95% 以上で合格、70〜95% は設定・位置の調整を試す）", r >= 0.95, r >= 0.7))
    print(_grade("fps", f"{a['fps']:.1f}（15 以上）", a["fps"] >= 15, a["fps"] >= 10))
    print(_grade("顔検出の処理時間（95%）", f"{a['detect_ms_p95']:.1f} ms（50 ms 以下）", a["detect_ms_p95"] <= 50, a["detect_ms_p95"] <= 80))
    if tilt is not None:
        print(_grade("顔の傾き（中央値）", f"{tilt:.0f}°（35° 以下）", tilt <= 35, tilt <= 45))
        print(_grade("画像内の回転", f"{roll:.0f}°（35° 以下）", roll <= 35, roll <= 45))
    if "noise_p95" in sug:
        print(_grade("静止時の口の動き（ノイズ 95%）", f"{sug['noise_p95']:.4f}、閾値の候補 {sug['threshold']:.4f}", sug["threshold"] < 0.02))
    if "snr" in sug:
        print(_grade("口パクとノイズの差（SNR）", f"{sug['snr']:.1f}（3 以上で合格、2〜3 は調整）", sug["snr"] >= 3, sug["snr"] >= 2))
    for w in sug["warnings"]:
        print(f"  注意: {w}")
    if probe is not None:
        cnt = "、".join(f"{d}°: {n}/{probe['frames']}（顔の回転 {probe['rolls'][d] if probe['rolls'][d] is not None else '-'}°）" for d, n in probe["counts"].items())
        print(f"映像の向きごとの検出（{probe['frames']} 枚中）: {cnt}")
        if probe["best"] is None:
            print("どの向きでも顔を検出できませんでした。顔が映っているか（収集画面の「カメラ位置の確認」）、カメラの番号（IR カメラを掴んでいないか: cameras.cmd）、距離（顔が小さすぎないか）、明るさ、遮蔽を確認してください")
        elif probe["best"] == s.camera_rotate:
            print(f"向き（camera_rotate = {s.camera_rotate}）は合っていますが、検出が不安定です。角度・距離・明るさ・遮蔽を見直してください")
        else:
            print(f"→ config.json の \"camera_rotate\" を {probe['best']} にして、もう一度 bench を実行してください")
    print("※ 視線入力ソフトを動かした状態での CPU 負荷と、試し録画 3 本は、収集画面で確認してください（docs/day0-checklist.md）")
    if "threshold" in sug:
        print(f"閾値の候補: threshold = active_threshold = {sug['threshold']}（収集画面の「校正」で反映できます）")

    rec = {"when": datetime.now().astimezone().isoformat(timespec="seconds"), "camera": src.description,
           "still_sec": s.still_sec, "static": {k: v for k, v in a.items() if k != "ranges"},
           "speech": {k: v for k, v in (b or {}).items() if k != "ranges"} or None, "suggestion": sug,
           "rotate": s.camera_rotate, "rotation_probe": probe}
    p.logs.mkdir(parents=True, exist_ok=True)
    out = p.logs / f"bench-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"結果を保存しました: {out}")
    return 0
