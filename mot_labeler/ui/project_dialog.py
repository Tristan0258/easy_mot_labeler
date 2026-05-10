from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from ..core.models import Project
from ..core.project import DEFAULT_CLASSES, write_project
from ..io.media_reader import inspect_media


class NewProjectDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新建 MOT 标注项目")
        self.project: Project | None = None
        self.source_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.root_edit = QLineEdit()
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        video_btn = QPushButton("打开视频")
        video_btn.clicked.connect(self.pick_video)
        images_btn = QPushButton("打开图片序列")
        images_btn.clicked.connect(self.pick_images)
        root_btn = QPushButton("选择保存位置")
        root_btn.clicked.connect(self.pick_root)
        create_btn = QPushButton("开始标注")
        create_btn.clicked.connect(self.create_project)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        form = QFormLayout()
        form.addRow("数据源", self._row(self.source_edit, video_btn, images_btn))
        form.addRow("项目名", self.name_edit)
        form.addRow("保存目录", self._row(self.root_edit, root_btn))
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("默认类别：person / vehicle / bicycle"))
        layout.addWidget(self.summary)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel_btn)
        buttons.addWidget(create_btn)
        layout.addLayout(buttons)

    def _row(self, edit: QLineEdit, *buttons: QPushButton) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addWidget(edit)
        for button in buttons:
            row.addWidget(button)
        return row

    def pick_video(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "选择视频文件", "", "Video (*.mp4 *.avi *.mov *.mkv)")
        if file_path:
            self.set_source(Path(file_path))

    def pick_images(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择图像序列目录")
        if folder:
            self.set_source(Path(folder))

    def set_source(self, path: Path) -> None:
        self.source_edit.setText(str(path))
        self.name_edit.setText(path.stem if path.is_file() else path.name)
        try:
            info = inspect_media(path)
            self.summary.setText(
                f"类型: {info.type}\n帧数: {info.frame_count}\n分辨率: {info.width}x{info.height}\nFPS: {info.fps:g}"
            )
        except Exception as exc:
            QMessageBox.warning(self, "读取失败", str(exc))

    def pick_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "选择项目保存目录")
        if folder:
            self.root_edit.setText(folder)

    def create_project(self) -> None:
        try:
            source = Path(self.source_edit.text())
            base = Path(self.root_edit.text())
            if not source.exists() or not base.exists() or not self.name_edit.text().strip():
                QMessageBox.warning(self, "信息不完整", "请选择数据源、项目名和保存目录。")
                return
            info = inspect_media(source)
            root = base / self.name_edit.text().strip()
            root.mkdir(parents=True, exist_ok=True)
            self.project = Project(self.name_edit.text().strip(), root, info, list(DEFAULT_CLASSES))
            write_project(self.project)
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "创建失败", str(exc))
