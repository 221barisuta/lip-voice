"""口元の切り出し（96×96 グレースケール）を webm にする。"""
import io
from fractions import Fraction

import av
import numpy as np


def encode_webm(frames: list[np.ndarray], t_ms: np.ndarray) -> bytes:
    """フレームごとの実際の時刻（ミリ秒）を使うので、可変フレームレートでも長さが正しい。"""
    if not frames:
        return b""
    buf = io.BytesIO()
    with av.open(buf, mode="w", format="webm") as container:
        stream = container.add_stream("libvpx-vp9", rate=30)
        stream.width, stream.height, stream.pix_fmt = 96, 96, "yuv420p"
        stream.codec_context.time_base = Fraction(1, 1000)
        stream.bit_rate = 400_000
        stream.options = {"crf": "36", "deadline": "realtime", "cpu-used": "8"}
        last = -1
        for img, t in zip(frames, t_ms):
            frame = av.VideoFrame.from_ndarray(img, format="gray").reformat(format="yuv420p")
            pts = max(int(t), last + 1)
            last = pts
            frame.pts = pts
            frame.time_base = Fraction(1, 1000)
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return buf.getvalue()
