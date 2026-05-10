from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..core.models import Annotation, BBox, Project


@dataclass
class QualityIssue:
    severity: str
    kind: str
    frame: int
    track_id: int | None
    class_id: int | None
    description: str


@dataclass
class RepairSummary:
    clipped: int = 0
    removed: int = 0


def repair_annotations_in_place(project: Project, annotations: list[Annotation]) -> RepairSummary:
    summary = RepairSummary()
    kept: list[Annotation] = []
    width = project.media.width
    height = project.media.height
    for ann in annotations:
        x, y, w, h = ann.bbox.as_list()
        x1 = max(0.0, min(float(width), x))
        y1 = max(0.0, min(float(height), y))
        x2 = max(0.0, min(float(width), x + w))
        y2 = max(0.0, min(float(height), y + h))
        new_w = x2 - x1
        new_h = y2 - y1
        if ann.frame < 0 or ann.frame >= project.media.frame_count or new_w <= 0 or new_h <= 0:
            summary.removed += 1
            continue
        if abs(x1 - x) > 1e-6 or abs(y1 - y) > 1e-6 or abs(new_w - w) > 1e-6 or abs(new_h - h) > 1e-6:
            ann.bbox = BBox(x1, y1, new_w, new_h)
            summary.clipped += 1
        kept.append(ann)
    annotations[:] = kept
    return summary


def run_quality_check(project: Project, annotations: list[Annotation]) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    by_frame_id: dict[tuple[int, int], int] = defaultdict(int)
    class_by_track: dict[int, int] = {}
    for ann in annotations:
        x, y, w, h = ann.bbox.as_list()
        if ann.frame < 0 or ann.frame >= project.media.frame_count:
            issues.append(QualityIssue("错误", "帧号越界", ann.frame, ann.track_id, ann.class_id, "标注帧号超出数据范围"))
        if w <= 0 or h <= 0:
            issues.append(QualityIssue("错误", "bbox尺寸错误", ann.frame, ann.track_id, ann.class_id, "宽度或高度小于等于 0"))
        if w * h < 16:
            issues.append(QualityIssue("警告", "bbox面积过小", ann.frame, ann.track_id, ann.class_id, "bbox 面积过小"))
        if x < 0 or y < 0 or x + w > project.media.width or y + h > project.media.height:
            issues.append(QualityIssue("错误", "bbox越界", ann.frame, ann.track_id, ann.class_id, "bbox 坐标超出图像范围"))
        if not ann.class_id:
            issues.append(QualityIssue("错误", "类别为空", ann.frame, ann.track_id, ann.class_id, "标注缺少类别"))
        if not ann.track_id:
            issues.append(QualityIssue("错误", "Track ID为空", ann.frame, ann.track_id, ann.class_id, "标注缺少 Track ID"))
        if not ann.confirmed and ann.source in {"tracker", "interpolation"}:
            issues.append(QualityIssue("提示", "未确认自动框", ann.frame, ann.track_id, ann.class_id, f"{ann.source} 生成框尚未确认"))
        by_frame_id[(ann.frame, ann.track_id)] += 1
        if ann.track_id in class_by_track and class_by_track[ann.track_id] != ann.class_id:
            issues.append(QualityIssue("错误", "ID跨类别", ann.frame, ann.track_id, ann.class_id, "同一 Track ID 被用于不同类别"))
        class_by_track.setdefault(ann.track_id, ann.class_id)
    for (frame, track_id), count in by_frame_id.items():
        if track_id and count > 1:
            issues.append(QualityIssue("错误", "同帧重复ID", frame, track_id, None, "同一帧中相同 Track ID 出现多次"))
    return issues
