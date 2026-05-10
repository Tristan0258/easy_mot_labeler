from __future__ import annotations

import re
from pathlib import Path

import cv2

from ..core.models import MediaInfo

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
VIDEO_EXTS = {".mp4", ".avi", ".mov", ".mkv"}


def natural_key(path: Path) -> list[object]:
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", path.name)]


class MediaReader:
    def __init__(self, info: MediaInfo) -> None:
        self.info = info
        self._cap: cv2.VideoCapture | None = None
        if info.type == "video":
            self._cap = cv2.VideoCapture(info.path)

    def read(self, frame_index: int):
        if self.info.type == "images":
            if frame_index < 0 or frame_index >= len(self.info.image_files):
                return None
            return cv2.imread(self.info.image_files[frame_index])
        if not self._cap:
            self._cap = cv2.VideoCapture(self.info.path)
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = self._cap.read()
        return frame if ok else None

    def close(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None


def inspect_media(path: Path) -> MediaInfo:
    if path.is_dir():
        files = sorted([p for p in path.iterdir() if p.suffix.lower() in IMAGE_EXTS], key=natural_key)
        if not files:
            raise ValueError("图像序列目录中没有可读取的图片。")
        first = cv2.imread(str(files[0]))
        if first is None:
            raise ValueError("无法读取图像序列的第一张图片。")
        height, width = first.shape[:2]
        return MediaInfo("images", str(path), width, height, 25.0, len(files), [str(p) for p in files])
    if path.suffix.lower() not in VIDEO_EXTS:
        raise ValueError("不支持的数据源格式。")
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError("无法读取视频文件。请检查文件是否损坏，或尝试转换为 MP4 格式后重新导入。")
    info = MediaInfo(
        "video",
        str(path),
        int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        float(cap.get(cv2.CAP_PROP_FPS) or 25.0),
        int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
    )
    cap.release()
    return info
