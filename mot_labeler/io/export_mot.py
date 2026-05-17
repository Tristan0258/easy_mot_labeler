from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from ..core.models import Annotation, Project


@dataclass
class ExportSummary:
    export_format: str
    output_dir: str
    label_files: int
    total_frames: int
    annotated_frames: int
    empty_frames: int
    exported_objects: int
    note: str = ""


def filtered_annotations(annotations: list[Annotation], include_ignore: bool = False) -> list[Annotation]:
    return [
        ann
        for ann in annotations
        if include_ignore or not ann.ignore
    ]


def export_mot(project: Project, annotations: list[Annotation], out_dir: Path, include_ignore: bool = False) -> ExportSummary:
    gt_dir = out_dir / "gt"
    gt_dir.mkdir(parents=True, exist_ok=True)
    rows: list[str] = []
    exported = filtered_annotations(annotations, include_ignore)
    for ann in sorted(exported, key=lambda a: (a.frame, a.track_id)):
        x, y, w, h = ann.bbox.as_list()
        rows.append(
            f"{ann.frame + 1},{ann.track_id},{x:.2f},{y:.2f},{w:.2f},{h:.2f},1,{ann.class_id},{ann.visibility:.3f}"
        )
    (gt_dir / "gt.txt").write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
    ext = ".jpg" if project.media.type == "images" else ".jpg"
    seqinfo = "\n".join(
        [
            "[Sequence]",
            f"name={project.project_name}",
            "imDir=img1",
            f"frameRate={project.media.fps:g}",
            f"seqLength={project.media.frame_count}",
            f"imWidth={project.media.width}",
            f"imHeight={project.media.height}",
            f"imExt={ext}",
            "",
        ]
    )
    (out_dir / "seqinfo.ini").write_text(seqinfo, encoding="utf-8")
    annotated_frames = len({ann.frame for ann in exported})
    return ExportSummary(
        "MOT多类别",
        str(out_dir),
        label_files=2,
        total_frames=project.media.frame_count,
        annotated_frames=annotated_frames,
        empty_frames=project.media.frame_count - annotated_frames,
        exported_objects=len(exported),
        note="MOT 使用 gt.txt 按目标行记录，空帧不会写入 gt.txt。",
    )


def frame_stem(project: Project, frame: int) -> str:
    if project.media.type == "images" and project.media.image_files:
        return Path(project.media.image_files[frame]).stem
    return f"frame_{frame + 1:06d}"


def frame_image_name(project: Project, frame: int) -> str:
    if project.media.type == "images" and project.media.image_files:
        return Path(project.media.image_files[frame]).name
    return f"frame_{frame + 1:06d}.jpg"


def export_yolo(project: Project, annotations: list[Annotation], out_dir: Path, include_ignore: bool = False) -> ExportSummary:
    labels_dir = out_dir / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)
    class_ids = [cls.id for cls in project.classes]
    class_to_index = {class_id: index for index, class_id in enumerate(class_ids)}
    names = [cls.name for cls in project.classes]
    (out_dir / "classes.txt").write_text("\n".join(names) + ("\n" if names else ""), encoding="utf-8")
    by_frame: dict[int, list[Annotation]] = {}
    exported = filtered_annotations(annotations, include_ignore)
    for ann in exported:
        by_frame.setdefault(ann.frame, []).append(ann)
    label_files = 0
    for frame in range(project.media.frame_count):
        rows: list[str] = []
        for ann in sorted(by_frame.get(frame, []), key=lambda a: a.track_id):
            if ann.class_id not in class_to_index:
                continue
            x, y, w, h = ann.bbox.as_list()
            xc = (x + w / 2) / project.media.width
            yc = (y + h / 2) / project.media.height
            nw = w / project.media.width
            nh = h / project.media.height
            rows.append(f"{class_to_index[ann.class_id]} {xc:.6f} {yc:.6f} {nw:.6f} {nh:.6f}")
        content = "\n".join(rows) + ("\n" if rows else "")
        (labels_dir / f"{frame_stem(project, frame)}.txt").write_text(content, encoding="utf-8")
        label_files += 1
    annotated_frames = sum(1 for anns in by_frame.values() if anns)
    return ExportSummary(
        "YOLO",
        str(out_dir),
        label_files=label_files,
        total_frames=project.media.frame_count,
        annotated_frames=annotated_frames,
        empty_frames=project.media.frame_count - annotated_frames,
        exported_objects=sum(len(anns) for anns in by_frame.values()),
        note="YOLO 会为空帧生成空 txt。",
    )


def export_labelme(project: Project, annotations: list[Annotation], out_dir: Path, include_ignore: bool = False) -> ExportSummary:
    labelme_dir = out_dir / "labelme"
    labelme_dir.mkdir(parents=True, exist_ok=True)
    class_names = {cls.id: cls.name for cls in project.classes}
    by_frame: dict[int, list[Annotation]] = {}
    exported = filtered_annotations(annotations, include_ignore)
    for ann in exported:
        by_frame.setdefault(ann.frame, []).append(ann)
    label_files = 0
    for frame in range(project.media.frame_count):
        frame_annotations = by_frame.get(frame, [])
        shapes = []
        for ann in sorted(frame_annotations, key=lambda a: a.track_id):
            x, y, w, h = ann.bbox.as_list()
            shapes.append(
                {
                    "label": class_names.get(ann.class_id, str(ann.class_id)),
                    "points": [[x, y], [x + w, y + h]],
                    "group_id": ann.track_id,
                    "description": ann.note,
                    "shape_type": "rectangle",
                    "flags": {
                        "track_id": ann.track_id,
                        "class_id": ann.class_id,
                        "source": ann.source,
                        "confirmed": ann.confirmed,
                        "ignore": ann.ignore,
                    },
                }
            )
        data = {
            "version": "5.0.1",
            "flags": {},
            "shapes": shapes,
            "imagePath": frame_image_name(project, frame),
            "imageData": None,
            "imageHeight": project.media.height,
            "imageWidth": project.media.width,
        }
        (labelme_dir / f"{frame_stem(project, frame)}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        label_files += 1
    annotated_frames = sum(1 for anns in by_frame.values() if anns)
    return ExportSummary(
        "LabelMe JSON",
        str(out_dir),
        label_files=label_files,
        total_frames=project.media.frame_count,
        annotated_frames=annotated_frames,
        empty_frames=project.media.frame_count - annotated_frames,
        exported_objects=sum(len(anns) for anns in by_frame.values()),
        note="LabelMe 会为空帧生成 shapes 为空的 JSON。",
    )


def export_annotations(project: Project, annotations: list[Annotation], out_dir: Path, export_format: str, include_ignore: bool = False) -> ExportSummary:
    fmt = export_format.lower()
    if "mot" in fmt:
        return export_mot(project, annotations, out_dir, include_ignore)
    elif "yolo" in fmt:
        return export_yolo(project, annotations, out_dir, include_ignore)
    elif "labelme" in fmt:
        return export_labelme(project, annotations, out_dir, include_ignore)
    else:
        raise ValueError(f"不支持的导出格式: {export_format}")
