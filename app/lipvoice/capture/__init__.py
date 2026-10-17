from ..settings import Settings
from .base import Frame, FrameSource


def open_source(s: Settings) -> FrameSource:
    """camera_source が数字ならカメラ番号、そうでなければ動画ファイル（試験用）。"""
    src = s.camera_source.strip()
    if src.isdigit():
        from .opencv_backend import CameraSource
        return CameraSource(int(src), s.camera_width, s.camera_height, s.camera_fps)
    from .file_backend import FileSource
    return FileSource(src, s.camera_width, s.camera_height)


__all__ = ["Frame", "FrameSource", "open_source"]
