# EasyMOT Labeler

EasyMOT Labeler 是一个基于 **PySide6 + OpenCV** 的桌面端多类别 MOT 标注工具。当前目录保留的是源码版本，可通过 Python 直接运行。

软件面向视频或图像序列数据，支持 bbox 标注、类别管理、Track ID 管理、自动保存、自动跟踪、插值、质量检查，以及多格式标签导出。

## 目录内容

```text
easy_motlabel/
  README.md
  requirements.txt
  mot_labeler/
    __main__.py
    main.py
    core/
    io/
    services/
    ui/
```

主要模块：

- `mot_labeler/main.py`：应用入口。
- `mot_labeler/core/`：数据模型、项目配置、内部标注存储。
- `mot_labeler/io/`：视频/图像序列读取、标签导出。
- `mot_labeler/services/`：质量检查、插值、跟踪、快捷键等服务。
- `mot_labeler/ui/`：主窗口、画布、对话框、项目创建界面和主题。

## 环境要求

建议使用 Python 3.9+。

安装依赖：

```powershell
pip install -r requirements.txt
```

依赖包括：

- `PySide6`
- `opencv-python`
- `numpy`
- `PyYAML`

## 启动软件

在当前目录执行：

```powershell
python -m mot_labeler
```

也可以运行入口文件：

```powershell
python mot_labeler/main.py
```

推荐使用 `python -m mot_labeler`，这样包内相对导入更稳定。

## 基本流程

1. 启动软件。
2. 点击 `新建项目`。
3. 选择 `打开视频` 或 `打开图片序列`。
4. 设置项目名称和保存目录。
5. 进入标注界面。
6. 绘制 bbox，设置类别和 Track ID。
7. 使用复制、插值或自动跟踪提升效率。
8. 运行质量检查。
9. 导出目标格式标签。

## 标注操作

- 鼠标左键拖拽空白区域：新建 bbox。
- 点击 bbox：选中 bbox。
- `Ctrl + 点击` 或 `Shift + 点击`：多选 bbox。
- 拖动 bbox 中间区域：移动 bbox。
- 鼠标靠近边或角：显示十字光标。
- 拖动边或角：实时调整 bbox 大小。
- `Delete` / `Backspace`：删除选中 bbox。
- 数字键 `1-9`：切换或修改类别。

## 帧操作和快捷键

常用快捷键：

| 功能 | 快捷键 |
|---|---|
| 新建项目 | `Ctrl + N` |
| 打开项目 | `Ctrl + O` |
| 保存 | `Ctrl + S` |
| 上一帧 | `A` / `←` |
| 下一帧 | `D` / `→` |
| 播放 / 暂停 | `Space` |
| 复制 | `Ctrl + C` |
| 粘贴 | `Ctrl + V` |
| 复制上一帧 | `Ctrl + Shift + V` |
| 删除选中框 | `Delete` / `Backspace` |
| 自动跟踪 | `T` |
| 跟踪到下一帧 | `Enter` |
| 质量检查 | `F7` |
| 导出 | `Ctrl + E` |

## 自动跟踪

支持以下跟踪方式：

- `AUTO`
- `光流`
- `CSRT`
- `KCF`
- `MOSSE`
- `模板匹配`

工具栏中的 `Enter跟踪器` 可以设置按 `Enter` 时使用的默认跟踪器。

`Enter` 跟踪行为：

- 单选一个框后按 `Enter`：跟踪该框到下一帧。
- 多选多个框后按 `Enter`：同时跟踪多个框到下一帧。
- 跟踪结果会写入下一帧，并自动跳转到下一帧。

`AUTO` 会优先使用 OpenCV tracker；如果当前 OpenCV 环境不支持相关 tracker，会自动退回光流或模板匹配。

## 类别管理

左侧类别表支持：

- 修改类别 ID。
- 修改类别名称。
- 修改类别颜色。
- 修改快捷键。
- 新增类别。
- 删除未使用类别。
- 保存类别到当前项目。
- 从 YAML 文件导入类别。

类别文件示例：

```yaml
classes:
  - id: 1
    name: person
    color: "#ff1744"
    shortcut: "1"
  - id: 2
    name: vehicle
    color: "#00e676"
    shortcut: "2"
```

也支持简单列表：

```yaml
classes:
  - person
  - vehicle
  - bicycle
```

## 项目文件结构

新建项目后会生成类似结构：

```text
project_name/
  project.yaml
  annotations/
    internal.json
    internal.autosave.json
    backups/
  configs/
    classes.yaml
```

说明：

- `project.yaml`：项目配置。
- `annotations/internal.json`：正式内部标注。
- `annotations/internal.autosave.json`：自动保存文件。
- `annotations/backups/`：备份文件。
- `configs/classes.yaml`：类别配置。

## 导出格式

导出窗口支持三种格式。

### MOT 多类别格式

输出：

```text
gt/gt.txt
seqinfo.ini
```

`gt.txt` 字段：

```text
frame,id,x,y,w,h,conf,class,visibility
```

### YOLO 格式

输出：

```text
labels/*.txt
classes.txt
```

每行格式：

```text
class x_center y_center width height
```

坐标为归一化值。

### LabelMe JSON 格式

输出：

```text
labelme/*.json
```

每帧一个 JSON，bbox 保存为 `rectangle`。Track ID 写入 `group_id`，附加信息写入 `flags`。

## 标签合法性检查

导出前可启用自动修复：

- bbox 超出图像边界：自动裁剪。
- bbox 完全在图像外：删除。
- bbox 宽高无效：删除。
- 标注帧号越界：删除。

质量检查还会提示：

- bbox 越界。
- bbox 面积过小。
- 类别为空。
- Track ID 为空。
- 同帧重复 Track ID。
- 同一 Track ID 跨类别。
- 未确认的跟踪或插值框。

## 当前源码运行说明

当前目录没有打包脚本或可执行程序产物。如果需要 Windows exe，建议先添加一个独立入口脚本，例如：

```python
from mot_labeler.main import main

if __name__ == "__main__":
    raise SystemExit(main())
```

然后使用 PyInstaller 的目录模式打包，并通过 `.spec` 文件显式排除无关 Qt 绑定，避免 PySide6 与 PyQt 同时存在时打包失败。

## 注意事项

- 对视频导出 LabelMe JSON 时，`imagePath` 会使用 `frame_000001.jpg` 这类帧名；如果需要和真实图片文件严格对应，建议使用图像序列项目。
- OpenCV 的 `CSRT/KCF/MOSSE` tracker 是否可用取决于当前 OpenCV 构建；不可用时软件会自动使用光流或模板匹配。
- `__pycache__` 文件是 Python 运行后生成的缓存文件，不影响软件运行。
