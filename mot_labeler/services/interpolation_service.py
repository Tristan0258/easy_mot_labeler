from __future__ import annotations

from ..core.annotation_store import AnnotationStore
from ..core.models import Annotation, BBox


def interpolate_track(store: AnnotationStore, track_id: int, start_frame: int, end_frame: int, overwrite: bool = False) -> int:
    if end_frame <= start_frame + 1:
        return 0
    start = next((a for a in store.annotations if a.frame == start_frame and a.track_id == track_id), None)
    end = next((a for a in store.annotations if a.frame == end_frame and a.track_id == track_id), None)
    if not start or not end or start.class_id != end.class_id:
        return 0
    made = 0
    span = end_frame - start_frame
    for frame in range(start_frame + 1, end_frame):
        existing = [a for a in store.annotations if a.frame == frame and a.track_id == track_id]
        if existing and not overwrite:
            continue
        ratio = (frame - start_frame) / span
        bbox = BBox(
            start.bbox.x + (end.bbox.x - start.bbox.x) * ratio,
            start.bbox.y + (end.bbox.y - start.bbox.y) * ratio,
            start.bbox.w + (end.bbox.w - start.bbox.w) * ratio,
            start.bbox.h + (end.bbox.h - start.bbox.h) * ratio,
        )
        ann = Annotation.create(frame, track_id, start.class_id, bbox, source="interpolation")
        ann.confirmed = False
        if existing:
            store.remove({a.uuid for a in existing})
        store.add(ann)
        made += 1
    return made
