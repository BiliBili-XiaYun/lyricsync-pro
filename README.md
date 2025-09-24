<div align="center">

# LyricSync Pro

歌词下载与编辑工具（PySide6）

[![Build and Release](https://github.com/yourname/lyricsync-pro/actions/workflows/release.yml/badge.svg)](../../actions)

</div>

## 功能特性

- 递归扫描音频文件（树形视图）
- 网易云搜索并下载 LRC（只按曲名匹配，结合时长优先匹配）
- 手动搜索筛选（自动过滤无歌词项、显示时长、列表预取 LRC）
- 双栏对比：原始歌词（只读）与编辑歌词（可编辑）
- 播放器与打点（Space 播放/暂停，D 打点；进度条/时间显示）
- 歌词时间轴高亮；行号同步滚动（滚轮联动，播放时跟随）
- 显示空格/换行标记（可开关）
- 设置：应用字体、编辑器字体、界面缩放（100/125/150）
- 快照：保存即生成快照；“文件 → 从快照恢复…” 可预览并恢复/覆盖

> 注：接口可能变更，如下载失败可切换镜像/源或扩展至其他平台 API。

## 安装与运行

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python .\main.py
```

## 快照与设置

- 快照目录：`snapshots/`（不会纳入版本控制）
- 设置项（通过 QSettings 持久化）：界面缩放、应用字体、编辑器字体、空白符显示、上次文件夹与文件

## 打包

```powershell
pip install pyinstaller
pyinstaller --noconfirm --windowed --name LyricSyncPro main.py
```

## GitHub Actions 自动发布

仓库已配置工作流：当推送 tag（如 `v0.1.0`）时，会自动在 Windows 上用 PyInstaller 构建并上传 Release 资产。

1. 推送代码到 GitHub。
2. 创建标签并推送：

```bash
git tag v0.1.0
git push origin v0.1.0
```

完成后可在 Releases 页面下载 `LyricSyncPro-windows.zip`。

## 版权与许可

本项目采用 MIT 许可证，见 `LICENSE`。
