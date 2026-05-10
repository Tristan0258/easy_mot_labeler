from __future__ import annotations

import cv2
import numpy as np

from ..core.models import Annotation, BBox
from ..io.media_reader import MediaReader


def create_tracker(name: str):
    upper = name.upper()
    candidates = []
    if upper == "CSRT":
        candidates = [("TrackerCSRT_create", cv2), ("TrackerCSRT_create", getattr(cv2, "legacy", None))]
    elif upper == "KCF":
        candidates = [("TrackerKCF_create", cv2), ("TrackerKCF_create", getattr(cv2, "legacy", None))]
    elif upper == "MOSSE":
        candidates = [("TrackerMOSSE_create", getattr(cv2, "legacy", None))]
    for attr, module in candidates:
        if module is not None and hasattr(module, attr):
            return getattr(module, attr)()
    raise RuntimeError(f"当前 OpenCV 不支持 {name} 跟踪器。")


def clamp_bbox(bbox: BBox, width: int, height: int) -> tuple[int, int, int, int]:
    x = max(0, min(int(round(bbox.x)), width - 1))
    y = max(0, min(int(round(bbox.y)), height - 1))
    w = max(1, min(int(round(bbox.w)), width - x))
    h = max(1, min(int(round(bbox.h)), height - y))
    return x, y, w, h


def template_match_next(prev_frame, frame, bbox: BBox, image_width: int, image_height: int) -> BBox | None:
    x, y, w, h = clamp_bbox(bbox, image_width, image_height)
    if w < 4 or h < 4:
        return None
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    context_x = max(4, int(w * 0.35))
    context_y = max(4, int(h * 0.35))
    tx = max(0, x - context_x)
    ty = max(0, y - context_y)
    tex = min(image_width, x + w + context_x)
    tey = min(image_height, y + h + context_y)
    template = prev_gray[ty:tey, tx:tex]
    if template.size == 0:
        return None
    pad_x = max(24, int(w * 1.5))
    pad_y = max(24, int(h * 1.5))
    sx = max(0, tx - pad_x)
    sy = max(0, ty - pad_y)
    ex = min(image_width, tex + pad_x)
    ey = min(image_height, tey + pad_y)
    search = gray[sy:ey, sx:ex]
    th, tw = template.shape[:2]
    if search.shape[0] < th or search.shape[1] < tw:
        return None
    method = cv2.TM_SQDIFF_NORMED if float(np.std(template)) < 1.0 else cv2.TM_CCOEFF_NORMED
    result = cv2.matchTemplate(search, template, method)
    min_score, max_score, min_loc, max_loc = cv2.minMaxLoc(result)
    if method == cv2.TM_SQDIFF_NORMED:
        score = 1.0 - min_score
        loc = min_loc
    else:
        score = max_score
        loc = max_loc
    if score < 0.12 or not np.isfinite(score):
        return None
    return BBox(float(sx + loc[0] + (x - tx)), float(sy + loc[1] + (y - ty)), float(w), float(h))


def optical_flow_next(prev_frame, frame, bbox: BBox, image_width: int, image_height: int) -> BBox | None:
    x, y, w, h = clamp_bbox(bbox, image_width, image_height)
    if w < 6 or h < 6:
        return None
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mask = np.zeros(prev_gray.shape, dtype=np.uint8)
    mask[y : y + h, x : x + w] = 255
    max_corners = max(12, min(120, int(w * h / 18)))
    points = cv2.goodFeaturesToTrack(
        prev_gray,
        maxCorners=max_corners,
        qualityLevel=0.01,
        minDistance=3,
        blockSize=5,
        mask=mask,
    )
    if points is None or len(points) < 4:
        return template_match_next(prev_frame, frame, bbox, image_width, image_height)
    next_points, status, _err = cv2.calcOpticalFlowPyrLK(
        prev_gray,
        gray,
        points,
        None,
        winSize=(21, 21),
        maxLevel=3,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, 0.01),
    )
    if next_points is None or status is None:
        return template_match_next(prev_frame, frame, bbox, image_width, image_height)
    good_prev = points[status.reshape(-1) == 1].reshape(-1, 2)
    good_next = next_points[status.reshape(-1) == 1].reshape(-1, 2)
    if len(good_next) < 4:
        return template_match_next(prev_frame, frame, bbox, image_width, image_height)
    shifts = good_next - good_prev
    median_shift = np.median(shifts, axis=0)
    distances_prev = np.linalg.norm(good_prev - np.median(good_prev, axis=0), axis=1)
    distances_next = np.linalg.norm(good_next - np.median(good_next, axis=0), axis=1)
    valid = distances_prev > 1.0
    if np.any(valid):
        ratios = distances_next[valid] / distances_prev[valid]
        scale = float(np.clip(np.median(ratios), 0.75, 1.35))
    else:
        scale = 1.0
    new_w = float(np.clip(w * scale, 4, image_width))
    new_h = float(np.clip(h * scale, 4, image_height))
    cx = x + w / 2 + float(median_shift[0])
    cy = y + h / 2 + float(median_shift[1])
    new_x = float(np.clip(cx - new_w / 2, 0, max(0, image_width - new_w)))
    new_y = float(np.clip(cy - new_h / 2, 0, max(0, image_height - new_h)))
    return BBox(new_x, new_y, new_w, new_h)


class TrackerService:
    def __init__(self, reader: MediaReader) -> None:
        self.reader = reader

    def track_single(self, start_ann: Annotation, num_frames: int = 30, direction: int = 1, algorithm: str = "CSRT") -> list[Annotation]:
        start_frame = self.reader.read(start_ann.frame)
        if start_frame is None:
            return []
        tracker = None
        algorithm_upper = algorithm.upper()
        use_optical_flow = algorithm_upper in {"OPTICAL_FLOW", "光流"}
        if algorithm_upper not in {"AUTO", "TEMPLATE", "模板匹配", "OPTICAL_FLOW", "光流"}:
            try:
                tracker = create_tracker(algorithm)
                tracker.init(start_frame, tuple(start_ann.bbox.as_list()))
            except RuntimeError:
                tracker = None
        elif algorithm.upper() == "AUTO":
            for candidate in ["CSRT", "KCF", "MOSSE"]:
                try:
                    tracker = create_tracker(candidate)
                    tracker.init(start_frame, tuple(start_ann.bbox.as_list()))
                    break
                except RuntimeError:
                    tracker = None
            if tracker is None:
                use_optical_flow = True
        results: list[Annotation] = []
        last_bbox = start_ann.bbox
        prev_frame = start_frame
        for step in range(1, num_frames + 1):
            frame_index = start_ann.frame + step * direction
            if frame_index < 0 or frame_index >= self.reader.info.frame_count:
                break
            frame = self.reader.read(frame_index)
            if frame is None:
                break
            if tracker is not None:
                ok, bbox_raw = tracker.update(frame)
                if not ok:
                    break
                x, y, w, h = [float(v) for v in bbox_raw]
                bbox = BBox(x, y, w, h)
            elif use_optical_flow:
                bbox = optical_flow_next(prev_frame, frame, last_bbox, self.reader.info.width, self.reader.info.height)
                if bbox is None:
                    break
                x, y, w, h = bbox.as_list()
            else:
                bbox = template_match_next(prev_frame, frame, last_bbox, self.reader.info.width, self.reader.info.height)
                if bbox is None:
                    break
                x, y, w, h = bbox.as_list()
            if w <= 2 or h <= 2:
                break
            cx_jump = abs((x + w / 2) - (last_bbox.x + last_bbox.w / 2))
            cy_jump = abs((y + h / 2) - (last_bbox.y + last_bbox.h / 2))
            if cx_jump > self.reader.info.width * 0.35 or cy_jump > self.reader.info.height * 0.35:
                break
            ann = Annotation.create(frame_index, start_ann.track_id, start_ann.class_id, bbox, source="tracker")
            ann.confirmed = False
            results.append(ann)
            last_bbox = bbox
            prev_frame = frame
        return results
