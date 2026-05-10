from __future__ import annotations

from pathlib import Path

import yaml

from PySide6.QtCore import QTimer, Qt
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDockWidget,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QStackedWidget,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..core.annotation_store import AnnotationStore
from ..core.models import Annotation, BBox, ClassDef, Project, now_text
from ..core.project import load_project, write_classes
from ..io.export_mot import export_annotations
from ..io.media_reader import MediaReader
from ..services.interpolation_service import interpolate_track
from ..services.quality_service import QualityIssue, repair_annotations_in_place, run_quality_check
from ..services.tracker_service import TrackerService
from .canvas_view import CanvasView
from .dialogs import ExportDialog, GoToFrameDialog, InterpolationDialog, TrackerDialog
from .project_dialog import NewProjectDialog


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("EasyMOT Labeler")
        self.project: Project | None = None
        self.reader: MediaReader | None = None
        self.store = AnnotationStore()
        self.current_frame = 0
        self.selected_uuid: str | None = None
        self.selected_uuids: set[str] = set()
        self.current_class_id = 1
        self.clipboard: list[Annotation] = []
        self.quality_issues: list[QualityIssue] = []
        self._updating_classes = False
        self.play_timer = QTimer(self)
        self.play_timer.timeout.connect(self.next_frame)
        self.settings = QSettings()
        self.autosave_timer = QTimer(self)
        self.autosave_timer.setInterval(30_000)
        self.autosave_timer.timeout.connect(self.autosave)
        self.canvas = CanvasView()
        self.canvas.box_created.connect(self.create_box)
        self.canvas.box_selected.connect(self.select_box)
        self.canvas.box_changed.connect(self.update_box)
        self.canvas.mouse_position.connect(self.update_mouse_pos)
        self.stack = QStackedWidget()
        self.startup_page = self._startup_widget()
        self.stack.addWidget(self.startup_page)
        self.stack.addWidget(self.canvas)
        self.setCentralWidget(self.stack)
        self._build_actions()
        self._build_menu()
        self._build_toolbar()
        self._build_docks()
        self._build_timeline()
        self.setStatusBar(QStatusBar())
        self.status_label = QLabel("未打开项目")
        self.statusBar().addPermanentWidget(self.status_label, 1)
        self.autosave_timer.start()
        self.show_start_hint()

    def _build_actions(self) -> None:
        self.actions: dict[str, QAction] = {}
        specs = [
            ("new", "新建项目", "Ctrl+N", self.new_project),
            ("open", "打开项目", "Ctrl+O", self.open_project),
            ("save", "保存", "Ctrl+S", self.save),
            ("prev", "上一帧", "A", self.prev_frame),
            ("next", "下一帧", "D", self.next_frame),
            ("play", "播放/暂停", "Space", self.toggle_play),
            ("copy", "复制", "Ctrl+C", self.copy_selected),
            ("paste", "粘贴", "Ctrl+V", self.paste_clipboard),
            ("copy_prev", "复制上一帧", "Ctrl+Shift+V", self.copy_previous_frame),
            ("delete", "删除", "Delete", self.delete_selected),
            ("interp", "插值", "", self.interpolate),
            ("track", "自动跟踪", "T", self.track_selected),
            ("track_next", "跟踪到下一帧", "", self.track_selected_to_next_frame),
            ("track_all", "跟踪当前帧全部", "", self.track_all),
            ("quality", "质量检查", "F7", self.run_quality),
            ("export", "导出", "Ctrl+E", self.export),
            ("goto", "跳转帧", "Ctrl+G", self.goto_frame),
            ("fit", "适应窗口", "Ctrl+0", self.canvas.fit_to_view),
        ]
        for key, text, shortcut, slot in specs:
            act = QAction(text, self)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(slot)
            self.actions[key] = act
            self.addAction(act)
        self.actions["track_next"].setShortcuts([QKeySequence(Qt.Key_Return), QKeySequence(Qt.Key_Enter)])
        right = QAction("下一帧(→)", self)
        right.setShortcut(QKeySequence(Qt.Key_Right))
        right.triggered.connect(self.next_frame)
        left = QAction("上一帧(←)", self)
        left.setShortcut(QKeySequence(Qt.Key_Left))
        left.triggered.connect(self.prev_frame)
        self.addAction(right)
        self.addAction(left)
        backspace = QAction("删除(Backspace)", self)
        backspace.setShortcut(QKeySequence(Qt.Key_Backspace))
        backspace.triggered.connect(self.delete_selected)
        self.addAction(backspace)
        for i in range(1, 10):
            act = QAction(f"类别 {i}", self)
            act.setShortcut(QKeySequence(str(i)))
            act.triggered.connect(lambda _=False, n=i: self.apply_class_shortcut(n))
            self.addAction(act)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("文件")
        for key in ["new", "open", "save", "export"]:
            file_menu.addAction(self.actions[key])
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close)
        edit_menu = self.menuBar().addMenu("编辑")
        for key in ["copy", "paste", "delete"]:
            edit_menu.addAction(self.actions[key])
        view_menu = self.menuBar().addMenu("视图")
        view_menu.addAction(self.actions["fit"])
        anno_menu = self.menuBar().addMenu("标注")
        for key in ["copy_prev", "interp"]:
            anno_menu.addAction(self.actions[key])
        track_menu = self.menuBar().addMenu("轨迹")
        for key in ["track", "track_next", "track_all", "goto"]:
            track_menu.addAction(self.actions[key])
        tool_menu = self.menuBar().addMenu("工具")
        tool_menu.addAction(self.actions["quality"])
        self.menuBar().addMenu("帮助").addAction("关于", self.about)

    def _build_toolbar(self) -> None:
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        self.addToolBar(tb)
        for key in ["new", "open", "save", "prev", "next", "play", "copy_prev", "interp", "track", "quality", "export"]:
            tb.addAction(self.actions[key])
        tb.addSeparator()
        tb.addWidget(QLabel("Enter跟踪器"))
        self.enter_tracker_combo = QComboBox()
        self.enter_tracker_combo.addItems(["AUTO", "光流", "CSRT", "KCF", "MOSSE", "模板匹配"])
        saved_tracker = self.settings.value("tracking/enter_algorithm", "AUTO")
        index = self.enter_tracker_combo.findText(str(saved_tracker))
        self.enter_tracker_combo.setCurrentIndex(index if index >= 0 else 0)
        self.enter_tracker_combo.currentTextChanged.connect(self.save_enter_tracker_setting)
        self.enter_tracker_combo.setToolTip("按 Enter 跟踪到下一帧时使用的默认跟踪器")
        tb.addWidget(self.enter_tracker_combo)
        for key, tip in {
            "next": "下一帧 (D / →)",
            "prev": "上一帧 (A / ←)",
            "play": "播放 / 暂停 (Space)",
            "copy_prev": "复制上一帧所有框 (Ctrl+Shift+V)",
            "track": "自动跟踪当前目标 (T)",
        }.items():
            self.actions[key].setToolTip(tip)

    def save_enter_tracker_setting(self, value: str) -> None:
        self.settings.setValue("tracking/enter_algorithm", value)

    def _build_docks(self) -> None:
        left = QDockWidget("项目与类别", self)
        self.project_info = QLabel("请新建或打开项目")
        self.class_table = QTableWidget(0, 4)
        self.class_table.setHorizontalHeaderLabels(["颜色", "ID", "类别", "快捷键"])
        self.class_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.class_table.cellClicked.connect(lambda row, _col: self.set_current_class_from_row(row))
        self.class_table.itemChanged.connect(self.class_item_changed)
        add_class_btn = QPushButton("新增类别")
        add_class_btn.clicked.connect(self.add_class)
        delete_class_btn = QPushButton("删除类别")
        delete_class_btn.clicked.connect(self.delete_class)
        save_class_btn = QPushButton("保存类别")
        save_class_btn.clicked.connect(self.save_classes)
        import_class_btn = QPushButton("导入类别YAML")
        import_class_btn.clicked.connect(self.import_classes_yaml)
        class_buttons = QHBoxLayout()
        class_buttons.addWidget(add_class_btn)
        class_buttons.addWidget(delete_class_btn)
        class_buttons.addWidget(save_class_btn)
        class_buttons.addWidget(import_class_btn)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(self.project_info)
        left_layout.addWidget(QLabel("类别列表"))
        left_layout.addWidget(self.class_table)
        left_layout.addLayout(class_buttons)
        left.setWidget(left_widget)
        self.addDockWidget(Qt.LeftDockWidgetArea, left)

        right = QDockWidget("对象 / 属性 / 质检", self)
        tabs = QTabWidget()
        self.object_table = QTableWidget(0, 5)
        self.object_table.setHorizontalHeaderLabels(["ID", "类别", "x,y,w,h", "来源", "确认"])
        self.object_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.object_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.object_table.cellClicked.connect(lambda row, _col: self.select_from_object_row(row))
        tabs.addTab(self.object_table, "当前帧对象")
        tabs.addTab(self._property_widget(), "属性编辑")
        self.quality_table = QTableWidget(0, 6)
        self.quality_table.setHorizontalHeaderLabels(["级别", "类型", "帧", "ID", "类别", "描述"])
        self.quality_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.quality_table.cellClicked.connect(lambda row, _col: self.goto_issue(row))
        tabs.addTab(self.quality_table, "质量检查")
        right.setWidget(tabs)
        self.addDockWidget(Qt.RightDockWidgetArea, right)

    def _property_widget(self) -> QWidget:
        widget = QWidget()
        self.prop_class = QComboBox()
        self.prop_track = QSpinBox()
        self.prop_track.setRange(1, 999999)
        self.prop_x = QSpinBox()
        self.prop_y = QSpinBox()
        self.prop_w = QSpinBox()
        self.prop_h = QSpinBox()
        for spin in [self.prop_x, self.prop_y, self.prop_w, self.prop_h]:
            spin.setRange(-99999, 99999)
        self.prop_visibility = QLineEdit("1.0")
        self.prop_note = QLineEdit()
        self.confirm_btn = QPushButton("确认当前自动框")
        self.confirm_btn.clicked.connect(self.confirm_selected)
        apply_btn = QPushButton("应用修改")
        apply_btn.clicked.connect(self.apply_properties)
        form = QFormLayout(widget)
        form.addRow("类别", self.prop_class)
        form.addRow("Track ID", self.prop_track)
        form.addRow("x", self.prop_x)
        form.addRow("y", self.prop_y)
        form.addRow("width", self.prop_w)
        form.addRow("height", self.prop_h)
        form.addRow("visibility", self.prop_visibility)
        form.addRow("note", self.prop_note)
        form.addRow("", self.confirm_btn)
        form.addRow("", apply_btn)
        return widget

    def _build_timeline(self) -> None:
        dock = QDockWidget("时间轴", self)
        widget = QWidget()
        self.frame_slider = QSlider(Qt.Horizontal)
        self.frame_slider.valueChanged.connect(self.slider_changed)
        self.frame_label = QLabel("0 / 0")
        layout = QHBoxLayout(widget)
        layout.addWidget(self.frame_label)
        layout.addWidget(self.frame_slider, 1)
        dock.setWidget(widget)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)

    def _startup_widget(self) -> QWidget:
        widget = QWidget()
        title = QLabel("EasyMOT Labeler")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 30px; font-weight: 600;")
        subtitle = QLabel("新建项目或打开 project.yaml 开始标注")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("font-size: 15px; color: #b9c0cc;")
        new_btn = QPushButton("新建项目")
        new_btn.clicked.connect(self.new_project)
        open_btn = QPushButton("打开项目")
        open_btn.clicked.connect(self.open_project)
        version = QLabel("版本 0.1.0")
        version.setAlignment(Qt.AlignCenter)
        version.setStyleSheet("color: #8c95a3;")
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(new_btn)
        buttons.addWidget(open_btn)
        buttons.addStretch()
        layout = QVBoxLayout(widget)
        layout.addStretch(2)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(18)
        layout.addLayout(buttons)
        layout.addStretch(2)
        layout.addWidget(version)
        return widget

    def show_start_hint(self) -> None:
        self.stack.setCurrentWidget(self.startup_page)

    def new_project(self) -> None:
        self.maybe_save()
        dlg = NewProjectDialog(self)
        if dlg.exec() and dlg.project:
            self.load_project_object(dlg.project)

    def open_project(self) -> None:
        self.maybe_save()
        path, _ = QFileDialog.getOpenFileName(self, "打开项目", "", "Project (project.yaml)")
        if path:
            try:
                self.load_project_object(load_project(Path(path)))
            except Exception as exc:
                QMessageBox.critical(self, "打开失败", str(exc))

    def load_project_object(self, project: Project) -> None:
        self.project = project
        self.reader = MediaReader(project.media)
        autosave = project.autosave_file
        formal = project.annotation_file
        load_path = formal
        if autosave.exists() and (not formal.exists() or autosave.stat().st_mtime > formal.stat().st_mtime):
            choice = QMessageBox.question(self, "恢复自动保存", "检测到较新的自动保存数据，是否恢复？")
            if choice == QMessageBox.Yes:
                load_path = autosave
        self.store.load(load_path)
        self.current_frame = 0
        self.selected_uuid = None
        self.selected_uuids = set()
        self.current_class_id = project.classes[0].id
        self.refresh_classes()
        self.refresh_project_info()
        self.frame_slider.setRange(0, max(0, project.media.frame_count - 1))
        self.stack.setCurrentWidget(self.canvas)
        self.load_frame()

    def load_frame(self) -> None:
        if not self.project or not self.reader:
            return
        frame = self.reader.read(self.current_frame)
        self.canvas.set_frame(frame)
        self.refresh_frame_annotations()
        self.update_frame_ui()
        self.update_status("已加载帧")

    def update_frame_ui(self) -> None:
        if not self.project:
            self.frame_label.setText("0 / 0")
            return
        self.frame_slider.blockSignals(True)
        self.frame_slider.setRange(0, max(0, self.project.media.frame_count - 1))
        self.frame_slider.setValue(self.current_frame)
        self.frame_slider.blockSignals(False)
        self.frame_label.setText(f"{self.current_frame + 1} / {self.project.media.frame_count}")
        self.frame_slider.update()
        self.frame_label.repaint()

    def refresh_frame_annotations(self) -> None:
        if not self.project:
            return
        anns = self.store.frame_items(self.current_frame)
        frame_uuids = {a.uuid for a in anns}
        self.selected_uuids &= frame_uuids
        if self.selected_uuid not in self.selected_uuids:
            self.selected_uuid = next(iter(self.selected_uuids), None)
        self.canvas.set_annotations(anns, self.project.classes, self.selected_uuids)
        self.refresh_object_table()
        self.refresh_properties()
        self.refresh_project_info()

    def refresh_classes(self) -> None:
        if not self.project:
            return
        self._updating_classes = True
        self.class_table.setRowCount(len(self.project.classes))
        self.prop_class.clear()
        for row, cls in enumerate(self.project.classes):
            self.class_table.setItem(row, 0, QTableWidgetItem(cls.color))
            self.class_table.setItem(row, 1, QTableWidgetItem(str(cls.id)))
            self.class_table.setItem(row, 2, QTableWidgetItem(cls.name))
            self.class_table.setItem(row, 3, QTableWidgetItem(cls.shortcut))
            self.prop_class.addItem(f"{cls.name} ({cls.id})", cls.id)
        self._updating_classes = False

    def class_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating_classes or not self.project:
            return
        row = item.row()
        if row < 0 or row >= len(self.project.classes):
            return
        cls = self.project.classes[row]
        try:
            old_id = cls.id
            new_id = int(self.class_table.item(row, 1).text())
            if new_id <= 0:
                raise ValueError("class id must be positive")
            if any(index != row and other.id == new_id for index, other in enumerate(self.project.classes)):
                QMessageBox.warning(self, "类别 ID 重复", "类别 ID 必须唯一。")
                self.refresh_classes()
                return
            cls.color = self.class_table.item(row, 0).text().strip() or cls.color
            cls.id = new_id
            cls.name = self.class_table.item(row, 2).text().strip() or cls.name
            cls.shortcut = self.class_table.item(row, 3).text().strip()
        except Exception:
            QMessageBox.warning(self, "类别格式错误", "类别 ID 必须是整数，颜色请使用 #RRGGBB 格式。")
            self.refresh_classes()
            return
        if old_id != cls.id:
            for ann in self.store.annotations:
                if ann.class_id == old_id:
                    ann.class_id = cls.id
            self.store.dirty = True
        self.current_class_id = cls.id
        self.refresh_classes()
        self.refresh_frame_annotations()
        self.update_status("类别已修改，点击保存类别写入项目")

    def add_class(self) -> None:
        if not self.project:
            return
        next_id = max([c.id for c in self.project.classes], default=0) + 1
        palette = ["#ffea00", "#ff6d00", "#d500f9", "#00e5ff", "#76ff03", "#ff4081"]
        color = palette[(next_id - 1) % len(palette)]
        self.project.classes.append(ClassDef(next_id, f"class_{next_id}", color, str(next_id) if next_id <= 9 else ""))
        self.refresh_classes()
        self.current_class_id = next_id
        self.update_status("已新增类别")

    def delete_class(self) -> None:
        if not self.project:
            return
        row = self.class_table.currentRow()
        if row < 0 or row >= len(self.project.classes):
            return
        cls = self.project.classes[row]
        used = any(ann.class_id == cls.id for ann in self.store.annotations)
        if used:
            QMessageBox.warning(self, "无法删除", "该类别已被标注使用，请先修改相关标注类别。")
            return
        del self.project.classes[row]
        if self.project.classes:
            self.current_class_id = self.project.classes[0].id
        self.refresh_classes()
        self.refresh_frame_annotations()
        self.update_status("已删除类别")

    def save_classes(self) -> None:
        if not self.project:
            return
        try:
            write_classes(self.project)
            self.update_status("类别已保存到 configs/classes.yaml")
        except Exception as exc:
            QMessageBox.warning(self, "保存类别失败", str(exc))

    def import_classes_yaml(self) -> None:
        if not self.project:
            return
        path, _ = QFileDialog.getOpenFileName(self, "导入类别 YAML", "", "YAML (*.yaml *.yml)")
        if not path:
            return
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
            raw_classes = data.get("classes", data if isinstance(data, list) else [])
            classes: list[ClassDef] = []
            for index, item in enumerate(raw_classes, start=1):
                if isinstance(item, str):
                    classes.append(ClassDef(index, item, self.default_class_color(index), str(index) if index <= 9 else ""))
                elif isinstance(item, dict):
                    class_id = int(item.get("id", index))
                    classes.append(
                        ClassDef(
                            class_id,
                            str(item.get("name", f"class_{class_id}")),
                            str(item.get("color", self.default_class_color(class_id))),
                            str(item.get("shortcut", class_id if class_id <= 9 else "")),
                            bool(item.get("visible", True)),
                            str(item.get("description", "")),
                        )
                    )
            if not classes:
                QMessageBox.warning(self, "导入失败", "YAML 中没有找到 classes 列表。")
                return
            ids = [cls.id for cls in classes]
            if len(ids) != len(set(ids)):
                QMessageBox.warning(self, "导入失败", "类别 ID 存在重复。")
                return
            old_ids = {cls.id for cls in self.project.classes}
            used_ids = {ann.class_id for ann in self.store.annotations}
            missing_used = used_ids - {cls.id for cls in classes}
            if missing_used:
                choice = QMessageBox.question(
                    self,
                    "类别不匹配",
                    f"当前标注中存在类别 ID {sorted(missing_used)}，新类别文件不包含这些 ID。仍然导入吗？",
                )
                if choice != QMessageBox.Yes:
                    return
            self.project.classes = classes
            self.current_class_id = classes[0].id
            self.refresh_classes()
            self.refresh_frame_annotations()
            write_classes(self.project)
            self.update_status("类别 YAML 已导入并保存")
        except Exception as exc:
            QMessageBox.warning(self, "导入类别失败", str(exc))

    def default_class_color(self, class_id: int) -> str:
        palette = ["#ff1744", "#00e676", "#2979ff", "#ffea00", "#ff6d00", "#d500f9", "#00e5ff", "#76ff03", "#ff4081"]
        return palette[(class_id - 1) % len(palette)]

    def refresh_project_info(self) -> None:
        if not self.project:
            return
        m = self.project.media
        done = self.store.annotated_frame_count()
        rate = done / max(1, m.frame_count) * 100
        self.project_info.setText(
            f"项目: {self.project.project_name}\n源: {Path(m.path).name}\n分辨率: {m.width}x{m.height}\nFPS: {m.fps:g}\n总帧数: {m.frame_count}\n已标注帧: {done} ({rate:.1f}%)"
        )

    def refresh_object_table(self) -> None:
        anns = self.store.frame_items(self.current_frame)
        self.object_table.setRowCount(len(anns))
        class_map = {c.id: c.name for c in self.project.classes} if self.project else {}
        for row, ann in enumerate(anns):
            self.object_table.setItem(row, 0, QTableWidgetItem(str(ann.track_id)))
            self.object_table.setItem(row, 1, QTableWidgetItem(class_map.get(ann.class_id, str(ann.class_id))))
            self.object_table.setItem(row, 2, QTableWidgetItem(",".join(f"{v:.1f}" for v in ann.bbox.as_list())))
            self.object_table.setItem(row, 3, QTableWidgetItem(ann.source))
            self.object_table.setItem(row, 4, QTableWidgetItem("是" if ann.confirmed else "否"))
            self.object_table.item(row, 0).setData(Qt.UserRole, ann.uuid)

    def refresh_properties(self) -> None:
        ann = self.selected_annotation()
        enabled = ann is not None
        for widget in [self.prop_class, self.prop_track, self.prop_x, self.prop_y, self.prop_w, self.prop_h, self.prop_visibility, self.prop_note, self.confirm_btn]:
            widget.setEnabled(enabled)
        if not ann:
            return
        idx = self.prop_class.findData(ann.class_id)
        if idx >= 0:
            self.prop_class.setCurrentIndex(idx)
        self.prop_track.setValue(ann.track_id)
        self.prop_x.setValue(round(ann.bbox.x))
        self.prop_y.setValue(round(ann.bbox.y))
        self.prop_w.setValue(round(ann.bbox.w))
        self.prop_h.setValue(round(ann.bbox.h))
        self.prop_visibility.setText(str(ann.visibility))
        self.prop_note.setText(ann.note)

    def selected_annotation(self) -> Annotation | None:
        if not self.selected_uuid:
            return None
        return next((a for a in self.store.annotations if a.uuid == self.selected_uuid), None)

    def selected_annotations(self) -> list[Annotation]:
        if not self.selected_uuids:
            return []
        selected = [a for a in self.store.annotations if a.uuid in self.selected_uuids and a.frame == self.current_frame]
        selected.sort(key=lambda ann: ann.track_id)
        return selected

    def create_box(self, x: float, y: float, w: float, h: float) -> None:
        if not self.project:
            return
        ann = Annotation.create(self.current_frame, self.store.next_track_id(), self.current_class_id, BBox(x, y, w, h))
        self.store.add(ann)
        self.selected_uuid = ann.uuid
        self.selected_uuids = {ann.uuid}
        self.refresh_frame_annotations()
        self.mark_dirty()

    def select_box(self, uuid: str, additive: bool = False) -> None:
        if additive:
            if uuid in self.selected_uuids:
                self.selected_uuids.remove(uuid)
                if self.selected_uuid == uuid:
                    self.selected_uuid = next(iter(self.selected_uuids), None)
            else:
                self.selected_uuids.add(uuid)
                self.selected_uuid = uuid
        else:
            self.selected_uuids = {uuid}
            self.selected_uuid = uuid
        self.refresh_frame_annotations()

    def update_box(self, uuid: str, x: float, y: float, w: float, h: float) -> None:
        ann = next((a for a in self.store.annotations if a.uuid == uuid), None)
        if ann:
            ann.bbox = BBox(x, y, w, h)
            ann.confirmed = True
            ann.updated_at = now_text()
            self.mark_dirty()
            self.refresh_frame_annotations()

    def apply_properties(self) -> None:
        ann = self.selected_annotation()
        if not ann:
            return
        ann.class_id = int(self.prop_class.currentData())
        ann.track_id = self.prop_track.value()
        ann.bbox = BBox(self.prop_x.value(), self.prop_y.value(), self.prop_w.value(), self.prop_h.value())
        try:
            ann.visibility = float(self.prop_visibility.text())
        except ValueError:
            ann.visibility = 1.0
        ann.note = self.prop_note.text()
        ann.confirmed = True
        ann.updated_at = now_text()
        self.mark_dirty()
        self.refresh_frame_annotations()

    def confirm_selected(self) -> None:
        ann = self.selected_annotation()
        if ann:
            ann.confirmed = True
            ann.updated_at = now_text()
            self.mark_dirty()
            self.refresh_frame_annotations()

    def set_current_class_from_row(self, row: int) -> None:
        if not self.project or row < 0:
            return
        self.current_class_id = self.project.classes[row].id
        ann = self.selected_annotation()
        if ann:
            ann.class_id = self.current_class_id
            ann.confirmed = True
            self.mark_dirty()
            self.refresh_frame_annotations()
        self.update_status("当前类别已更新")

    def apply_class_shortcut(self, number: int) -> None:
        if not self.project:
            return
        cls = next((c for c in self.project.classes if c.shortcut == str(number)), None)
        if cls:
            self.current_class_id = cls.id
            ann = self.selected_annotation()
            if ann:
                ann.class_id = cls.id
                ann.confirmed = True
                self.mark_dirty()
                self.refresh_frame_annotations()

    def select_from_object_row(self, row: int) -> None:
        item = self.object_table.item(row, 0)
        if item:
            self.select_box(item.data(Qt.UserRole))

    def delete_selected(self) -> None:
        if not self.selected_uuids:
            return
        if len(self.selected_uuids) > 1:
            choice = QMessageBox.question(self, "删除确认", f"确认删除 {len(self.selected_uuids)} 个标注框吗？")
            if choice != QMessageBox.Yes:
                return
        self.store.remove(set(self.selected_uuids))
        self.selected_uuid = None
        self.selected_uuids = set()
        self.mark_dirty()
        self.refresh_frame_annotations()

    def copy_selected(self) -> None:
        self.clipboard = self.selected_annotations()

    def paste_clipboard(self) -> None:
        if not self.clipboard:
            return
        for ann in self.clipboard:
            self.store.add(ann.clone_to_frame(self.current_frame, source="copy"))
        self.mark_dirty()
        self.refresh_frame_annotations()

    def copy_previous_frame(self) -> None:
        if self.current_frame <= 0:
            return
        existing_ids = {a.track_id for a in self.store.frame_items(self.current_frame)}
        count = 0
        for ann in self.store.frame_items(self.current_frame - 1):
            if ann.track_id not in existing_ids:
                self.store.add(ann.clone_to_frame(self.current_frame, source="copy"))
                count += 1
        self.mark_dirty()
        self.refresh_frame_annotations()
        self.update_status(f"已复制上一帧 {count} 个标注")

    def interpolate(self) -> None:
        ann = self.selected_annotation()
        dlg = InterpolationDialog(self.current_frame, ann.track_id if ann else None, self)
        if dlg.exec():
            count = interpolate_track(self.store, dlg.track_id.value(), dlg.start_frame.value(), dlg.end_frame.value(), dlg.overwrite.isChecked())
            self.mark_dirty()
            self.refresh_frame_annotations()
            QMessageBox.information(self, "插值完成", f"生成 {count} 个插值框。")

    def track_selected(self) -> None:
        anns = self.selected_annotations()
        if not anns or not self.reader:
            QMessageBox.information(self, "无法跟踪", "请先选中一个 bbox。")
            return
        self._track_annotations(anns)

    def track_selected_to_next_frame(self) -> None:
        anns = self.selected_annotations()
        if not anns or not self.reader or not self.project:
            QMessageBox.information(self, "无法跟踪", "请先选中一个 bbox。")
            return
        next_frame = self.current_frame + 1
        if next_frame >= self.project.media.frame_count:
            QMessageBox.information(self, "无法跟踪", "当前已经是最后一帧。")
            return
        selected_track_ids = {ann.track_id for ann in anns}
        existing = [a for a in self.store.annotations if a.frame == next_frame and a.track_id in selected_track_ids]
        overwrite = False
        if existing:
            choice = QMessageBox.question(self, "覆盖确认", f"下一帧已有 {len(existing)} 个同 Track ID 标注，是否覆盖？")
            if choice != QMessageBox.Yes:
                self.current_frame = next_frame
                self.selected_uuid = existing[0].uuid
                self.selected_uuids = {a.uuid for a in existing}
                self.load_frame()
                return
            overwrite = True
        service = TrackerService(self.reader)
        last_error = None
        tracked_results: list[Annotation] = []
        preferred = self.enter_tracker_combo.currentText() if hasattr(self, "enter_tracker_combo") else "AUTO"
        algorithms = [preferred]
        if preferred != "模板匹配":
            algorithms.append("模板匹配")
        for ann in anns:
            results = []
            for algorithm in algorithms:
                try:
                    results = service.track_single(ann, num_frames=1, direction=1, algorithm=algorithm)
                    if results:
                        break
                except Exception as exc:
                    last_error = exc
            if results:
                tracked_results.append(results[0])
        if not tracked_results:
            message = f"跟踪失败：{last_error}" if last_error else "跟踪失败，未能在下一帧生成 bbox。"
            QMessageBox.warning(self, "跟踪失败", message)
            return
        if overwrite and existing:
            self.store.remove({a.uuid for a in existing})
        for tracked in tracked_results:
            self.store.add(tracked)
        self.selected_uuids = {tracked.uuid for tracked in tracked_results}
        self.selected_uuid = tracked_results[-1].uuid
        self.current_frame = next_frame
        self.mark_dirty()
        self.load_frame()
        self.update_status(f"已跟踪 {len(tracked_results)} 个框到下一帧")

    def track_all(self) -> None:
        anns = self.store.frame_items(self.current_frame)
        if not anns:
            QMessageBox.information(self, "无法跟踪", "当前帧没有 bbox。")
            return
        self._track_annotations(anns)

    def _track_annotations(self, anns: list[Annotation]) -> None:
        if not self.reader:
            return
        dlg = TrackerDialog(self)
        if not dlg.exec():
            return
        service = TrackerService(self.reader)
        total = 0
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for ann in anns:
                results = service.track_single(ann, dlg.frames.value(), dlg.direction_value(), dlg.algorithm.currentText())
                for result in results:
                    exists = [a for a in self.store.annotations if a.frame == result.frame and a.track_id == result.track_id]
                    if exists and not dlg.overwrite.isChecked():
                        continue
                    if exists:
                        self.store.remove({a.uuid for a in exists})
                    self.store.add(result)
                    total += 1
        except Exception as exc:
            QMessageBox.warning(self, "自动跟踪失败", str(exc))
        finally:
            QApplication.restoreOverrideCursor()
        self.mark_dirty()
        self.refresh_frame_annotations()
        QMessageBox.information(self, "自动跟踪完成", f"生成 {total} 个未确认跟踪框。")

    def run_quality(self) -> None:
        if not self.project:
            return
        self.autosave()
        self.quality_issues = run_quality_check(self.project, self.store.annotations)
        self.quality_table.setRowCount(len(self.quality_issues))
        for row, issue in enumerate(self.quality_issues):
            for col, value in enumerate([issue.severity, issue.kind, issue.frame + 1, issue.track_id or "", issue.class_id or "", issue.description]):
                self.quality_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.update_status(f"质量检查完成: {len(self.quality_issues)} 项")

    def goto_issue(self, row: int) -> None:
        if row < len(self.quality_issues):
            self.current_frame = self.quality_issues[row].frame
            self.load_frame()

    def export(self) -> None:
        if not self.project:
            return
        self.save()
        self.run_quality()
        dlg = ExportDialog(self)
        if not dlg.exec():
            return
        folder = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not folder:
            return
        try:
            repair_text = ""
            if dlg.auto_repair.isChecked():
                summary = repair_annotations_in_place(self.project, self.store.annotations)
                if summary.clipped or summary.removed:
                    self.store.dirty = True
                    self.save()
                    self.refresh_frame_annotations()
                repair_text = f"\n自动修复: 裁剪 {summary.clipped} 个框，删除 {summary.removed} 个无效框。"
            export_annotations(
                self.project,
                self.store.annotations,
                Path(folder),
                dlg.format_combo.currentText(),
                dlg.include_unconfirmed.isChecked(),
                dlg.include_ignore.isChecked(),
            )
            QMessageBox.information(self, "导出完成", f"已导出 {dlg.format_combo.currentText()} 标注。{repair_text}")
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))

    def save(self) -> None:
        if not self.project:
            return
        try:
            write_classes(self.project)
            self.store.save(self.project.annotation_file, make_backup=True)
            self.update_status(f"已保存 | 自动保存开启 | 最近保存 {now_text()}")
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))

    def autosave(self) -> None:
        if not self.project or not self.store.dirty:
            return
        try:
            self.store.save(self.project.autosave_file, make_backup=False)
            self.store.dirty = True
            self.update_status(f"自动保存成功 {now_text()}")
        except Exception as exc:
            self.update_status(f"自动保存失败: {exc}")

    def maybe_save(self) -> None:
        if self.project and self.store.dirty:
            if QMessageBox.question(self, "保存修改", "当前项目有未保存修改，是否保存？") == QMessageBox.Yes:
                self.save()

    def mark_dirty(self) -> None:
        self.store.dirty = True
        self.update_status("有未保存修改 | 自动保存开启")

    def prev_frame(self) -> None:
        if self.project and self.current_frame > 0:
            self.current_frame -= 1
            self.load_frame()

    def next_frame(self) -> None:
        if self.project and self.current_frame < self.project.media.frame_count - 1:
            self.current_frame += 1
            self.load_frame()
        elif self.play_timer.isActive():
            self.toggle_play()

    def toggle_play(self) -> None:
        if not self.project:
            return
        if self.play_timer.isActive():
            self.play_timer.stop()
        else:
            fps = max(1, min(60, int(self.project.media.fps or 25)))
            self.play_timer.start(int(1000 / fps))

    def slider_changed(self, value: int) -> None:
        if self.project:
            self.current_frame = value
            self.load_frame()

    def goto_frame(self) -> None:
        if not self.project:
            return
        dlg = GoToFrameDialog(self.project.media.frame_count, self)
        if dlg.exec():
            self.current_frame = dlg.frame.value() - 1
            self.load_frame()

    def update_mouse_pos(self, x: float, y: float) -> None:
        self.statusBar().showMessage(f"鼠标: {x:.0f}, {y:.0f}", 1500)

    def update_status(self, text: str) -> None:
        selected = self.selected_annotation()
        cls_name = ""
        if self.project:
            cls = next((c for c in self.project.classes if c.id == self.current_class_id), None)
            cls_name = cls.name if cls else str(self.current_class_id)
        frame_text = f"{self.current_frame + 1}/{self.project.media.frame_count}" if self.project else "0/0"
        self.status_label.setText(f"帧 {frame_text} | 选中 ID {selected.track_id if selected else '-'} | 当前类别 {cls_name} | {text}")

    def about(self) -> None:
        QMessageBox.information(self, "关于", "EasyMOT Labeler 0.1.0\n多类别 MOT 数据标注工具。")

    def closeEvent(self, event) -> None:
        self.maybe_save()
        if self.reader:
            self.reader.close()
        event.accept()
