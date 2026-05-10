# EasyMOT Labeler

多类别 MOT 数据集桌面标注工具，基于 PySide6 + OpenCV。

## 运行

```powershell
python -m mot_labeler
```

## 已实现

- 新建/打开项目
- 导入视频或图像序列
- 当前帧显示、上一帧/下一帧/播放
- bbox 绘制、选择、移动、缩放、删除
- 类别与 Track ID 编辑
- 自动保存、手动保存、JSON 加载
- 复制上一帧、区间线性插值
- OpenCV 单目标/当前帧多目标跟踪
- 基础质量检查
- MOTChallenge `gt.txt` 和 `seqinfo.ini` 导出

## 项目文件

- `project.yaml`: 项目配置
- `annotations/internal.json`: 正式标注
- `annotations/internal.autosave.json`: 自动保存标注
- `configs/classes.yaml`: 类别配置
