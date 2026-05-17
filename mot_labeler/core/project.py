from __future__ import annotations

import os
from pathlib import Path

import yaml

from .models import ClassDef, MediaInfo, Project


DEFAULT_CLASSES = [
    ClassDef(1, "person", "#ff1744", "1"),
    ClassDef(2, "vehicle", "#00e676", "2"),
    ClassDef(3, "bicycle", "#2979ff", "3"),
]


def _media_to_dict(project: Project) -> dict:
    media = project.media
    data = dict(media.__dict__)
    media_path = Path(media.path)
    data["original_path"] = media.original_path or str(media_path)
    try:
        data["relative_path"] = os.path.relpath(media_path, project.root)
    except ValueError:
        data["relative_path"] = media.relative_path
    if media.type == "images":
        data["image_file_names"] = media.image_file_names or [Path(p).name for p in media.image_files]
        data["image_files"] = list(data["image_file_names"])
    return data


def write_project(project: Project) -> None:
    (project.root / "annotations").mkdir(parents=True, exist_ok=True)
    (project.root / "configs").mkdir(parents=True, exist_ok=True)
    write_classes(project)
    data = {
        "project_name": project.project_name,
        "version": project.version,
        "created_at": project.created_at,
        "media": _media_to_dict(project),
        "annotation_file": "annotations/internal.json",
        "autosave_file": "annotations/internal.autosave.json",
        "classes_file": "configs/classes.yaml",
        "settings_file": "configs/settings.yaml",
    }
    project.project_file.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def write_classes(project: Project) -> None:
    (project.root / "configs").mkdir(parents=True, exist_ok=True)
    project.classes_file.write_text(
        yaml.safe_dump({"classes": [c.__dict__ for c in project.classes]}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _existing_media_path(root: Path, media: MediaInfo) -> Path | None:
    candidates = []
    if media.path:
        candidates.append(Path(media.path))
    if media.relative_path:
        candidates.append(root / media.relative_path)
    if media.original_path:
        candidates.append(Path(media.original_path))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def resolve_media_paths(project: Project) -> bool:
    found = _existing_media_path(project.root, project.media)
    if not found:
        return False
    project.media.path = str(found)
    if project.media.type == "images":
        names = project.media.image_file_names or [Path(p).name for p in project.media.image_files]
        if names and found.is_dir():
            image_files = [found / name for name in names]
            if all(path.exists() for path in image_files):
                project.media.image_files = [str(path) for path in image_files]
                return True
        existing = [Path(p) for p in project.media.image_files if Path(p).exists()]
        if len(existing) == project.media.frame_count:
            project.media.image_files = [str(p) for p in existing]
            return True
        return False
    return found.is_file()


def load_project(path: Path) -> Project:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    root = path.parent
    media_data = dict(data["media"])
    media_fields = set(MediaInfo.__dataclass_fields__)
    media = MediaInfo(**{key: value for key, value in media_data.items() if key in media_fields})
    if media.type == "images" and not media.image_file_names:
        media.image_file_names = [Path(p).name for p in media.image_files]
    classes_path = root / data.get("classes_file", "configs/classes.yaml")
    classes_data = yaml.safe_load(classes_path.read_text(encoding="utf-8")) if classes_path.exists() else {}
    classes = [ClassDef(**item) for item in classes_data.get("classes", [])] or DEFAULT_CLASSES
    project = Project(
        project_name=data["project_name"],
        root=root,
        media=media,
        classes=classes,
        version=str(data.get("version", "1.0")),
        created_at=data.get("created_at", ""),
    )
    resolve_media_paths(project)
    return project
