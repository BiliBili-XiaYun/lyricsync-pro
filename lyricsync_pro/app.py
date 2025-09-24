from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QVBoxLayout, QHBoxLayout,
    QListWidget, QPushButton, QTextEdit, QLabel, QSplitter, QStatusBar, QProgressBar, QMessageBox,
    QLineEdit, QListWidgetItem, QDialog, QDialogButtonBox, QTreeView, QFontDialog, QSizePolicy, QStyle, QMenu
)
from PySide6.QtCore import Qt, QThread, Signal, QUrl, QSettings, QPoint
from PySide6.QtGui import QAction, QKeySequence, QTextCharFormat, QColor, QTextCursor, QTextOption, QFont, QActionGroup
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtWidgets import QSlider
from PySide6.QtWidgets import QFileSystemModel
import json
import re
import sys
from pathlib import Path
from typing import List

from .scanner import find_audio_files
from .downloader import LyricDownloader
from .storage import SnapshotStore


AUDIO_EXTS = {".mp3", ".flac", ".wav", ".m4a", ".aac", ".ogg"}


class ScanThread(QThread):
    progress = Signal(int)
    result = Signal(list)

    def __init__(self, root: Path):
        super().__init__()
        self.root = root

    def run(self):
        files = list(find_audio_files(self.root))
        self.result.emit(files)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LyricSync - 歌词下载与编辑工具")
        self.resize(1200, 720)
        self.downloader = LyricDownloader()
        self.snapshot_store = SnapshotStore(Path.cwd() / "snapshots")
        self.player = QMediaPlayer()
        self.audio_out = QAudioOutput()
        self.player.setAudioOutput(self.audio_out)

        # UI
        self._build_menu()
        self._build_ui()
        # Settings storage
        self.settings = QSettings("LyricSync", "LyricSyncPro")
        self.load_settings()

    def _build_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件")
        open_action = QAction("选择文件夹", self)
        open_action.triggered.connect(self.choose_folder)
        file_menu.addAction(open_action)

        save_action = QAction("保存歌词", self)
        save_action.triggered.connect(self.save_current_lyric)
        file_menu.addAction(save_action)

        restore_action = QAction("从快照恢复…", self)
        restore_action.triggered.connect(self.restore_from_snapshot_dialog)
        file_menu.addAction(restore_action)

        settings_menu = menubar.addMenu("设置")
        # App font
        act_app_font = QAction("设置应用字体…", self)
        act_app_font.triggered.connect(self.choose_app_font)
        settings_menu.addAction(act_app_font)

        # Editor font
        act_editor_font = QAction("设置编辑器字体…", self)
        act_editor_font.triggered.connect(self.choose_editor_font)
        settings_menu.addAction(act_editor_font)

        # Zoom submenu
        zoom_menu = settings_menu.addMenu("界面缩放")
        self._zoom_group = QActionGroup(self)
        self._zoom_group.setExclusive(True)
        for label, scale in [("100%", 1.0), ("125%", 1.25), ("150%", 1.5)]:
            act = QAction(label, self)
            act.setCheckable(True)
            if scale == 1.0:
                act.setChecked(True)
            act.triggered.connect(lambda checked, s=scale: self.apply_scale(s))
            self._zoom_group.addAction(act)
            zoom_menu.addAction(act)

        # Whitespace toggle
        self.act_show_ws = QAction("显示空格/换行标记", self)
        self.act_show_ws.setCheckable(True)
        self.act_show_ws.toggled.connect(self.on_toggle_whitespace)
        settings_menu.addAction(self.act_show_ws)

        help_menu = menubar.addMenu("帮助")
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def _build_ui(self):
        # Left panel: folder controls + file tree
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        self.btn_choose = QPushButton("选择文件夹")
        self.btn_choose.clicked.connect(self.choose_folder)
        self.btn_scan = QPushButton("递归搜索音频")
        self.btn_scan.clicked.connect(self.scan_folder)
        self.tree = QTreeView()
        self.tree.setHeaderHidden(True)
        self.tree.setExpandsOnDoubleClick(True)
        self.tree.setUniformRowHeights(True)
        self.fs_model: QFileSystemModel | None = None
        left_layout.addWidget(self.btn_choose)
        left_layout.addWidget(self.btn_scan)
        left_layout.addWidget(QLabel("文件树"))
        left_layout.addWidget(self.tree, 1)
        left_panel.setMinimumWidth(320)

        # Right panel: info, controls, progress, dual editors
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.lbl_current = QLabel("未选择音频")
        # Download / Search
        self.btn_download = QPushButton("自动匹配并下载歌词（按歌曲名）")
        self.btn_download.clicked.connect(self.download_lyric_auto)
        self.btn_search = QPushButton("手动搜索并选择歌词…")
        self.btn_search.clicked.connect(self.manual_search_dialog)

        # Player controls
        self.btn_play = QPushButton("播放/暂停 (Space)")
        self.btn_play.clicked.connect(self.toggle_play)
        self.btn_stamp = QPushButton("打点 (D)")
        self.btn_stamp.clicked.connect(self.insert_timestamp_line)
        self.btn_save = QPushButton("保存歌词 (Ctrl+S)")
        self.btn_save.clicked.connect(self.save_current_lyric)

        # Assign standard icons to avoid emoji fallback rendering issues
        try:
            self.btn_play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
            self.btn_stamp.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
            self.btn_save.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        except Exception:
            pass

        # Combine five buttons into a single row
        controls_row = QHBoxLayout()
        controls_row.setSpacing(8)
        def _expand(btn: QPushButton):
            btn.setMinimumHeight(28)
            btn.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
            return btn
        for b in (_expand(self.btn_download), _expand(self.btn_search), _expand(self.btn_play), _expand(self.btn_stamp), _expand(self.btn_save)):
            controls_row.addWidget(b)

        # Playback slider + time label
        progress_row = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 0)
        self.slider_slider_pressed = False
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.sliderMoved.connect(self._on_slider_moved)
        self.lbl_time = QLabel("00:00 / 00:00")
        progress_row.addWidget(self.slider, 1)
        progress_row.addWidget(self.lbl_time)

        # Dual-pane lyric editors
        self.editor_original = QTextEdit()
        self.editor_original.setReadOnly(True)
        self.editor_original.setPlaceholderText("原始歌词（下载/载入后显示，不可编辑）")
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("编辑歌词：可手动编辑或打点…")
        # Prefer monospace for better alignment of timestamps; can be changed via Settings
        try:
            mono = QFont("Consolas")
            if mono and mono.family():
                self.editor.setFont(mono)
                self.editor_original.setFont(mono)
        except Exception:
            pass
        self.lyrics_splitter = QSplitter()
        self.lyrics_splitter.addWidget(self.editor_original)
        self.lyrics_splitter.addWidget(self.editor)
        self.lyrics_splitter.setStretchFactor(0, 1)
        self.lyrics_splitter.setStretchFactor(1, 1)

        right_layout.addWidget(self.lbl_current)
        right_layout.addLayout(controls_row)
        right_layout.addLayout(progress_row)
        # Header aligned with editors using a synced splitter
        self.header_left = QLabel("原始歌词")
        self.header_left.setAlignment(Qt.AlignCenter)
        self.header_right = QLabel("编辑歌词")
        self.header_right.setAlignment(Qt.AlignCenter)
        # Ensure headers expand to occupy splitter panes
        try:
            self.header_left.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
            self.header_right.setSizePolicy(QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed))
            self.header_left.setMinimumWidth(10)
            self.header_right.setMinimumWidth(10)
        except Exception:
            pass
        self.header_splitter = QSplitter()
        self.header_splitter.setHandleWidth(0)
        self.header_splitter.addWidget(self.header_left)
        self.header_splitter.addWidget(self.header_right)
        self.header_splitter.setStretchFactor(0, 1)
        self.header_splitter.setStretchFactor(1, 1)
        right_layout.addWidget(self.header_splitter)
        right_layout.addWidget(self.lyrics_splitter, 1)

        # keep header sizes in sync with editor splitter
        def _sync_header_sizes(*_):
            self.header_splitter.setSizes(self.lyrics_splitter.sizes())
        self.lyrics_splitter.splitterMoved.connect(_sync_header_sizes)
        _sync_header_sizes()

        # Wheel-driven synchronized scrolling: keep top line aligned
        try:
            self.editor.verticalScrollBar().valueChanged.connect(lambda _v: self._sync_scroll_from(self.editor, self.editor_original))
            self.editor_original.verticalScrollBar().valueChanged.connect(lambda _v: self._sync_scroll_from(self.editor_original, self.editor))
        except Exception:
            pass

        splitter = QSplitter()
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        splitter.setSizes([420, 780])

        # Status bar
        status = QStatusBar()
        self.progress = QProgressBar()
        self.progress.setMaximumHeight(14)
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        status.addPermanentWidget(self.progress)
        self.setStatusBar(status)

        # Central widget
        container = QWidget()
        root_layout = QVBoxLayout(container)
        root_layout.addWidget(splitter, 1)
        self.setCentralWidget(container)

        # Runtime state
        self.current_dir: Path | None = None
        self.current_audio: Path | None = None
        self.current_lrc_path: Path | None = None
        self.used_match_tag: str = ""
        self._lrc_index: list[tuple[float, int]] = []  # (time_sec, block_index)
        self._highlight_format = QTextCharFormat()
        self._highlight_format.setBackground(QColor(255, 255, 0, 80))
        self._highlight_format2 = QTextCharFormat()
        self._highlight_format2.setBackground(QColor(120, 180, 255, 60))
        self._current_line_no = -1
        self._sync_lock = False

        # Player signals
        self.player.durationChanged.connect(self.on_duration_changed)
        self.player.positionChanged.connect(self.on_position_changed)

        # Rebuild LRC index on edits
        self.editor.textChanged.connect(self.rebuild_lrc_index)
        # Sync by line number on caret moves
        self.editor.cursorPositionChanged.connect(self._on_editor_caret_changed)

        # Shortcuts
        self.addAction(self._make_shortcut("Space", self.toggle_play))
        self.addAction(self._make_shortcut("D", self.insert_timestamp_line))
        self.addAction(self._make_shortcut("Ctrl+S", self.save_current_lyric))

        # Settings state: base fonts and scale
        self._base_app_font = QApplication.font()
        self._base_editor_font = self.editor.font()
        self._ui_scale = 1.0

    # ---------------- Settings: Load/Save ----------------
    def _to_bool(self, v, default=False) -> bool:
        if v is None:
            return default
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        return s in ("true", "1", "yes", "y", "t")

    def load_settings(self):
        s = self.settings
        # Fonts
        app_family = s.value("font/appFamily")
        app_pt = s.value("font/appPointSize")
        if app_family and app_pt:
            try:
                f = QFont(str(app_family), int(float(app_pt)))
                self._base_app_font = f
            except Exception:
                pass
        editor_family = s.value("font/editorFamily")
        editor_pt = s.value("font/editorPointSize")
        if editor_family and editor_pt:
            try:
                f = QFont(str(editor_family), int(float(editor_pt)))
                self._base_editor_font = f
                self.editor.setFont(self._base_editor_font)
                self.editor_original.setFont(self._base_editor_font)
            except Exception:
                pass

        # Scale
        scale_val = s.value("ui/scale", 1.0)
        try:
            scale = float(scale_val)
        except Exception:
            scale = 1.0
        self.apply_scale(scale)
        # Update zoom action checked state
        target = int(round(scale * 100))
        for act in self._zoom_group.actions():
            try:
                pct = int(act.text().rstrip('%'))
            except Exception:
                pct = None
            act.setChecked(pct == target)

        # Ensure menubar adopts font on startup
        try:
            mb = self.menuBar()
            if mb:
                mb.setFont(self._base_app_font)
                for menu in mb.findChildren(QMenu):
                    menu.setFont(self._base_app_font)
                mb.updateGeometry()
        except Exception:
            pass

        # Whitespace flag
        show_ws = self._to_bool(s.value("editor/showWhitespace"), False)
        self.act_show_ws.setChecked(show_ws)  # will trigger on_toggle_whitespace

        # Restore last session: dir and file
        last_dir = s.value("session/lastDir")
        last_file = s.value("session/lastFile")
        if last_dir:
            p = Path(str(last_dir))
            if p.exists() and p.is_dir():
                self.current_dir = p
                self.setup_tree(p)
                # If last file is under dir, try select it
                if last_file:
                    fp = Path(str(last_file))
                    if fp.exists() and fp.is_file():
                        try:
                            idx = self.fs_model.index(str(fp))
                            if idx.isValid():
                                self.tree.setCurrentIndex(idx)
                                self.tree.scrollTo(idx)
                        except Exception:
                            pass

    def _save_font_settings(self):
        # Save both app and editor base fonts
        self.settings.setValue("font/appFamily", self._base_app_font.family())
        ps = self._base_app_font.pointSize()
        if ps <= 0:
            ps = max(8, self._base_app_font.pixelSize() or 12)
        self.settings.setValue("font/appPointSize", ps)

        self.settings.setValue("font/editorFamily", self._base_editor_font.family())
        pe = self._base_editor_font.pointSize()
        if pe <= 0:
            pe = max(8, self._base_editor_font.pixelSize() or 12)
        self.settings.setValue("font/editorPointSize", pe)

    def on_toggle_whitespace(self, checked: bool):
        def apply_option(editor: QTextEdit, enabled: bool):
            opt = editor.document().defaultTextOption()
            flags = opt.flags()
            if enabled:
                flags |= QTextOption.ShowTabsAndSpaces
                flags |= QTextOption.ShowLineAndParagraphSeparators
            else:
                flags &= ~QTextOption.ShowTabsAndSpaces
                flags &= ~QTextOption.ShowLineAndParagraphSeparators
            opt.setFlags(flags)
            editor.document().setDefaultTextOption(opt)
            editor.viewport().update()

        apply_option(self.editor, checked)
        apply_option(self.editor_original, checked)
        # Persist flag
        try:
            self.settings.setValue("editor/showWhitespace", bool(checked))
        except Exception:
            pass

    def choose_app_font(self):
        res = QFontDialog.getFont(self._base_app_font, self, "选择应用字体")
        # Some bindings may return (font, ok) or (ok, font); normalize
        font, ok = (res if isinstance(res[0], QFont) else (res[1], res[0]))
        if ok and isinstance(font, QFont):
            self._base_app_font = QFont(font)
            QApplication.setFont(self._base_app_font)
            self._save_font_settings()
            # Reapply scale to propagate size changes globally
            self.apply_scale(self._ui_scale)
            self._force_editors_relayout()
            try:
                mb = self.menuBar()
                if mb:
                    mb.setFont(self._base_app_font)
                    for menu in mb.findChildren(QMenu):
                        menu.setFont(self._base_app_font)
                    mb.updateGeometry()
                    mb.repaint()
            except Exception:
                pass

    def choose_editor_font(self):
        res = QFontDialog.getFont(self._base_editor_font, self, "选择编辑器字体")
        font, ok = (res if isinstance(res[0], QFont) else (res[1], res[0]))
        if ok and isinstance(font, QFont):
            self._base_editor_font = QFont(font)
            self.editor.setFont(self._base_editor_font)
            self.editor_original.setFont(self._base_editor_font)
            self._save_font_settings()
            # Reapply scale to keep consistency and relayout
            self.apply_scale(self._ui_scale)
            self._force_editors_relayout()

    def apply_scale(self, scale: float):
        self._ui_scale = scale
        # Approach: scale base app font point size, and editor font as well
        def scale_font(f: QFont, s: float) -> QFont:
            nf = QFont(f)
            if nf.pointSizeF() > 0:
                nf.setPointSizeF(max(6.0, nf.pointSizeF() * s))
            else:
                # If using pixel size
                if nf.pixelSize() > 0:
                    nf.setPixelSize(max(8, int(nf.pixelSize() * s)))
            return nf

        appf = scale_font(self._base_app_font, scale)
        QApplication.setFont(appf)
        # Ensure menu bar and menus adopt the scaled app font immediately
        try:
            mb = self.menuBar()
            if mb:
                mb.setFont(appf)
                for menu in mb.findChildren(QMenu):
                    menu.setFont(appf)
                mb.updateGeometry()
                mb.repaint()
        except Exception:
            pass
        ef = scale_font(self._base_editor_font, scale)
        self.editor.setFont(ef)
        self.editor_original.setFont(ef)
        # Also enlarge key labels
        self.header_left.setFont(ef)
        self.header_right.setFont(ef)
        # Persist scale
        try:
            self.settings.setValue("ui/scale", float(scale))
        except Exception:
            pass
        # Resync header splitter sizes after font/scale change
        try:
            self.header_splitter.setSizes(self.lyrics_splitter.sizes())
        except Exception:
            pass

    def _force_editors_relayout(self):
        # Force document layout to rebuild after font changes to avoid visual artifacts
        try:
            self.editor.document().documentLayout().update()
            self.editor.viewport().update()
        except Exception:
            pass
        try:
            self.editor_original.document().documentLayout().update()
            self.editor_original.viewport().update()
        except Exception:
            pass

    def _make_shortcut(self, key: str, handler):
        act = QAction(self)
        act.setShortcut(QKeySequence(key))
        act.triggered.connect(handler)
        return act

    def choose_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "选择包含音频的文件夹")
        if directory:
            self.current_dir = Path(directory)
            self.statusBar().showMessage(f"已选择: {self.current_dir}")
            self.setup_tree(self.current_dir)
            try:
                self.settings.setValue("session/lastDir", str(self.current_dir))
            except Exception:
                pass
            # 自动执行一次递归搜索统计
            self.scan_folder()

    def setup_tree(self, root: Path):
        if self.fs_model is None:
            model = QFileSystemModel(self)
            # 显示目录以及匹配的音频文件
            filters = ["*.mp3", "*.flac", "*.wav", "*.m4a", "*.aac", "*.ogg"]
            model.setNameFilters(filters)
            model.setNameFilterDisables(False)  # 仅显示匹配的文件，目录仍显示
            model.setRootPath(str(root))
            self.fs_model = model
            self.tree.setModel(self.fs_model)
            # 仅显示名称列
            for col in range(1, 4):
                self.tree.setColumnHidden(col, True)
            # 连接选择变化
            self.tree.selectionModel().selectionChanged.connect(self.on_tree_selection_changed)
        else:
            self.fs_model.setRootPath(str(root))
        self.tree.setRootIndex(self.fs_model.index(str(root)))

    def scan_folder(self):
        if not self.current_dir:
            QMessageBox.information(self, "提示", "请先选择文件夹")
            return
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.thread = ScanThread(self.current_dir)
        self.thread.result.connect(self.on_scan_result)
        self.thread.finished.connect(lambda: self.progress.setVisible(False))
        self.thread.start()

    def on_scan_result(self, files: List[str]):
        # 仅用于状态汇报，文件显示由树控件负责
        self.statusBar().showMessage(f"找到 {len(files)} 个音频文件")

    def on_tree_selection_changed(self, selected, deselected):
        if not self.fs_model:
            return
        indexes = self.tree.selectionModel().selectedIndexes()
        if not indexes:
            return
        idx = indexes[0]
        path_str = self.fs_model.filePath(idx)
        path = Path(path_str)
        if path.is_dir() or path.suffix.lower() not in AUDIO_EXTS:
            return
        self.load_audio(path)
        try:
            self.settings.setValue("session/lastFile", str(path))
        except Exception:
            pass

    def load_audio(self, path: Path):
        self.current_audio = path
        self.lbl_current.setText(f"🎵 当前音频：{path.name}")
        # Load into player
        try:
            self.player.setSource(QUrl.fromLocalFile(str(path)))
        except Exception:
            pass
        # Persist last file
        try:
            self.settings.setValue("session/lastFile", str(path))
        except Exception:
            pass
        # Load lrc if exists
        lrc_path = path.with_suffix('.lrc')
        self.current_lrc_path = lrc_path
        if lrc_path.exists():
            content = lrc_path.read_text(encoding="utf-8", errors="ignore")
            # 原始/编辑都显示现有内容，原始为只读
            self.editor_original.setPlainText(content)
            self.editor.setPlainText(content)
            self.rebuild_lrc_index()
        else:
            self.editor_original.clear()
            self.editor.clear()
            self._lrc_index = []

    def download_lyric_auto(self):
        if not self.current_audio:
            QMessageBox.information(self, "提示", "请先选择一个音频文件")
            return
        title, artist, duration, fuzzy = self.downloader.extract_metadata(self.current_audio)
        if not title:
            QMessageBox.information(self, "未找到信息", "无法从音频中提取标题，请使用手动搜索。")
            return
        self.used_match_tag = "fuzzy" if fuzzy else "id3"
        self.statusBar().showMessage(f"尝试下载歌词：{title}（依据：{self.used_match_tag}）")
        self.progress.setVisible(True)
        QApplication.processEvents()
        try:
            lrc, chosen = self.downloader.download_lrc(title, duration)
        except Exception as e:
            QMessageBox.warning(self, "下载失败", f"错误：{e}")
            self.progress.setVisible(False)
            return
        self.progress.setVisible(False)
        if not lrc or not chosen:
            QMessageBox.information(self, "未找到", "未找到匹配歌词，请尝试手动搜索。")
            return
        header = self.downloader.build_lrc_header(title=title, artist=artist, length_sec=duration, match_tag=self.used_match_tag)
        full_lrc = header + "\n" + (lrc or "")
        # 双栏显示：左原始，右可编辑
        self.editor_original.setPlainText(full_lrc)
        self.editor.setPlainText(full_lrc)
        if self.current_lrc_path:
            self.current_lrc_path.write_text(full_lrc, encoding="utf-8")
            self.snapshot_store.save_snapshot(self.current_lrc_path.name, full_lrc, cursor_pos=self.editor.textCursor().position())
            self.statusBar().showMessage(f"歌词已保存：{self.current_lrc_path}")

    # ---------------- Manual Search Dialog ----------------
    def manual_search_dialog(self):
        if not self.current_audio:
            QMessageBox.information(self, "提示", "请先选择一个音频文件")
            return
        title, artist, duration, fuzzy = self.downloader.extract_metadata(self.current_audio)
        self.used_match_tag = "fuzzy" if fuzzy else "id3"

        dlg = QDialog(self)
        dlg.setWindowTitle("手动搜索歌词")
        v = QVBoxLayout(dlg)
        inp = QLineEdit(dlg)
        inp.setPlaceholderText("输入歌曲名关键词（建议只输入歌名）")
        if title:
            inp.setText(title)
        btns = QHBoxLayout()
        btn_search = QPushButton("搜索")
        btns.addWidget(btn_search)
        v.addWidget(QLabel("搜索关键词："))
        v.addWidget(inp)
        v.addLayout(btns)
        lst = QListWidget(dlg)
        v.addWidget(QLabel("搜索结果（按与本地时长接近排序；自动排除无歌词条目）："))
        v.addWidget(lst, 1)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        v.addWidget(box)

        picked = {"song": None}

        def do_search():
            kw = inp.text().strip()
            if not kw:
                return
            results = self.downloader.search_songs(kw, limit=20)
            # duration-aware sort
            if duration is not None:
                target = int(duration * 1000)
                results.sort(key=lambda x: abs((x.get("duration_ms") or 0) - target))
            lst.clear()
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                for r in results:
                    # 过滤无歌词的结果，并缓存歌词以避免重复网络请求
                    lrc = self.downloader.get_lyric_by_id(r.get("id")) if r.get("id") else None
                    if not lrc:
                        continue
                    ms = r.get("duration_ms") or 0
                    sec = ms / 1000 if ms else 0
                    item = QListWidgetItem(f"{r.get('name','')} - {r.get('artists','')}  ({sec:.1f}s)  [id={r.get('id')}]")
                    item.setData(Qt.UserRole, {"song": r, "lrc": lrc})
                    lst.addItem(item)
                    QApplication.processEvents()
            finally:
                QApplication.restoreOverrideCursor()

        def on_ok():
            it = lst.currentItem()
            if it is None:
                return
            picked["song"] = it.data(Qt.UserRole)
            dlg.accept()

        def on_cancel():
            dlg.reject()

        btn_search.clicked.connect(do_search)
        box.accepted.connect(on_ok)
        box.rejected.connect(on_cancel)

        do_search()  # initial
        if dlg.exec() == QDialog.Accepted and picked["song"]:
            data = picked["song"]
            chosen = data.get("song") if isinstance(data, dict) else data
            lrc = data.get("lrc") if isinstance(data, dict) else None
            if not lrc and chosen and chosen.get("id"):
                lrc = self.downloader.get_lyric_by_id(chosen.get("id"))
            if not lrc:
                QMessageBox.information(self, "未找到", "该结果无歌词，请选择其他结果或重搜。")
                return
            header = self.downloader.build_lrc_header(title=title or inp.text().strip(), artist=artist, length_sec=duration, match_tag=self.used_match_tag + "+manual")
            full_lrc = header + "\n" + lrc
            self.editor_original.setPlainText(full_lrc)
            self.editor.setPlainText(full_lrc)
            if self.current_lrc_path:
                self.current_lrc_path.write_text(full_lrc, encoding="utf-8")
                self.snapshot_store.save_snapshot(self.current_lrc_path.name, full_lrc, cursor_pos=self.editor.textCursor().position())
                self.statusBar().showMessage(f"歌词已保存：{self.current_lrc_path}")

    # ---------------- Player & Stamping ----------------
    def toggle_play(self):
        if not self.current_audio:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _current_time_sec(self) -> float:
        # QMediaPlayer position in ms
        pos_ms = self.player.position()
        return max(0.0, pos_ms / 1000.0)

    def insert_timestamp_line(self):
        if not self.current_audio:
            return
        sec = self._current_time_sec()
        mm = int(sec // 60)
        ss = int(sec % 60)
        ms = int(round((sec - int(sec)) * 1000))
        # When rounding to 1000 may roll over to 60s, normalize
        if ms >= 1000:
            ms -= 1000
            ss += 1
            if ss >= 60:
                ss -= 60
                mm += 1
        tag = f"[{mm:02d}:{ss:02d}.{ms:03d}]"
        cursor = self.editor.textCursor()
        cursor.insertText(tag)
        cursor.insertBlock()
        self.editor.setTextCursor(cursor)
        # After stamping, rebuild index so new tag participates in highlighting
        self.rebuild_lrc_index()

    def save_current_lyric(self):
        if not self.current_audio or not self.current_lrc_path:
            QMessageBox.information(self, "提示", "请先选择一个音频文件")
            return
        text = self.editor.toPlainText()
        self.current_lrc_path.write_text(text, encoding="utf-8")
        self.snapshot_store.save_snapshot(self.current_lrc_path.name, text, cursor_pos=self.editor.textCursor().position())
        self.statusBar().showMessage("保存成功，并已创建快照")
        QMessageBox.information(self, "保存成功", "歌词已保存并创建快照。")
        # Refresh displays and indices immediately
        try:
            fresh = self.current_lrc_path.read_text(encoding="utf-8", errors="ignore")
            self.editor_original.setPlainText(fresh)
            # 不覆盖右侧正在编辑的光标位置，但同步文本（通常与fresh一致）
            cur = self.editor.textCursor()
            self.editor.setPlainText(fresh)
            self.editor.setTextCursor(cur)
            self.rebuild_lrc_index()
        except Exception:
            pass

    # ---------------- Progress & LRC Highlight ----------------
    def on_duration_changed(self, duration_ms: int):
        self.slider.setRange(0, int(duration_ms or 0))
        self.update_time_label(self.player.position(), duration_ms)

    def on_position_changed(self, pos_ms: int):
        if not self.slider_slider_pressed:
            self.slider.setValue(int(pos_ms))
        self.update_time_label(pos_ms, self.player.duration())
        self.update_lrc_highlight(pos_ms / 1000.0)

    def update_time_label(self, pos_ms: int, dur_ms: int):
        def fmt(ms: int) -> str:
            s = max(0, int(ms // 1000))
            mm = s // 60
            ss = s % 60
            return f"{mm:02d}:{ss:02d}"
        self.lbl_time.setText(f"{fmt(pos_ms)} / {fmt(dur_ms or 0)}")

    def _on_slider_pressed(self):
        self.slider_slider_pressed = True

    def _on_slider_released(self):
        self.slider_slider_pressed = False
        self.player.setPosition(int(self.slider.value()))

    def _on_slider_moved(self, value: int):
        # Preview time on label while dragging
        self.update_time_label(value, self.player.duration())

    def rebuild_lrc_index(self):
        text = self.editor.toPlainText()
        self._lrc_index = []
        for i, line in enumerate(text.splitlines()):
            # support multiple tags in a line; take first for navigation
            for m in re.finditer(r"\[(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?\]", line):
                mm = int(m.group(1))
                ss = int(m.group(2))
                frac = m.group(3) or "0"
                # Normalize fractional part to seconds: 1-3 digits -> /10, /100, /1000
                if len(frac) == 1:
                    frac_sec = int(frac) / 10.0
                elif len(frac) == 2:
                    frac_sec = int(frac) / 100.0
                else:
                    # treat 3+ digits as milliseconds (cap to 3)
                    frac_sec = int(frac[:3]) / 1000.0
                t = mm * 60 + ss + frac_sec
                self._lrc_index.append((t, i))
                break
        self._lrc_index.sort(key=lambda x: x[0])

    def update_lrc_highlight(self, current_sec: float):
        if not self._lrc_index:
            return
        # find last index where time <= current_sec
        idx = 0
        for j, (t, _) in enumerate(self._lrc_index):
            if t <= current_sec:
                idx = j
            else:
                break
        line_no = self._lrc_index[idx][1]
        if line_no != self._current_line_no:
            self._current_line_no = line_no
            # Scroll both to this line (without disturbing editable caret)
            self._scroll_both_to_line(line_no)
            # Apply highlight to both editors
            self._apply_line_highlight(self.editor, line_no, self._highlight_format)
            self._apply_line_highlight(self.editor_original, line_no, self._highlight_format2)

    def _apply_line_highlight(self, editor: QTextEdit, line_no: int, fmt: QTextCharFormat):
        block = editor.document().findBlockByNumber(line_no)
        if not block.isValid():
            return
        cur = editor.textCursor()
        cur.setPosition(block.position())
        sel = QTextEdit.ExtraSelection()
        sel.cursor = cur
        sel.format = fmt
        sel.cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        editor.setExtraSelections([sel])

    def _scroll_both_to_line(self, line_no: int):
        # Avoid recursive loops
        if self._sync_lock:
            return
        self._sync_lock = True
        try:
            # Center target line in both editors without changing user's caret
            self._scroll_editor_view_to_line(self.editor_original, line_no, align="center")
            self._scroll_editor_view_to_line(self.editor, line_no, align="center")
        finally:
            self._sync_lock = False

    def _scroll_editor_view_to_line(self, editor: QTextEdit, line_no: int, align: str = "center"):
        try:
            block = editor.document().findBlockByNumber(line_no)
            if not block.isValid():
                return
            layout = editor.document().documentLayout()
            rect = layout.blockBoundingRect(block)
            y = rect.top()
            # Align mode: top/center/bottom
            vh = editor.viewport().height()
            bh = rect.height()
            if align == "center":
                y = y - (vh - bh) / 2.0
            elif align == "bottom":
                y = y - (vh - bh)
            # Clamp into scrollbar range
            sb = editor.verticalScrollBar()
            v = max(0, min(int(y), sb.maximum()))
            sb.setValue(v)
        except Exception:
            pass

    def _on_editor_caret_changed(self):
        # Do not auto-center on click; wheel-driven sync handles alignment
        return

    def _sync_scroll_from(self, src: QTextEdit, dst: QTextEdit):
        if self._sync_lock:
            return
        self._sync_lock = True
        try:
            # determine top visible line in src
            vp = src.viewport()
            top_pt = QPoint(0, 1)  # a bit inside the viewport
            cur = src.cursorForPosition(top_pt)
            bn = cur.blockNumber()
            # clamp for dst
            bn = max(0, min(bn, dst.document().blockCount() - 1))
            # align dst so that this line appears at top
            self._scroll_editor_view_to_line(dst, bn, align="top")
        finally:
            self._sync_lock = False

    def show_about(self):
        QMessageBox.information(self, "关于", "LyricSync Pro\n智能歌词下载与时间轴校对工具\n版本 0.1.0")

    # ---------------- Snapshot Restore ----------------
    def restore_from_snapshot_dialog(self):
        if not self.current_lrc_path:
            QMessageBox.information(self, "提示", "请先打开一个文件，以便筛选对应的快照。")
            return
        # Collect snapshots for current file
        snaps = []
        for p in self.snapshot_store.list_snapshots():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("filename") == self.current_lrc_path.name:
                    snaps.append((p, data))
            except Exception:
                continue
        if not snaps:
            QMessageBox.information(self, "提示", "没有找到当前文件的快照。")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("从快照恢复")
        v = QVBoxLayout(dlg)
        h = QHBoxLayout()
        v.addLayout(h, 1)

        lst = QListWidget(dlg)
        lst.setMinimumWidth(320)
        for p, data in sorted(snaps, key=lambda x: x[1].get("timestamp", ""), reverse=True):
            item = QListWidgetItem(f"{data.get('timestamp','')} — {p.name}")
            item.setData(Qt.UserRole, (p, data))
            lst.addItem(item)
        h.addWidget(lst)

        preview = QTextEdit(dlg)
        preview.setReadOnly(True)
        h.addWidget(preview, 1)

        box = QDialogButtonBox(QDialogButtonBox.Cancel)
        btn_load = QPushButton("载入到编辑器")
        btn_overwrite = QPushButton("覆盖保存到文件")
        box.addButton(btn_load, QDialogButtonBox.ActionRole)
        box.addButton(btn_overwrite, QDialogButtonBox.ActionRole)
        v.addWidget(box)

        chosen = {"data": None}

        def on_sel_changed():
            it = lst.currentItem()
            if not it:
                preview.clear()
                chosen["data"] = None
                return
            _p, d = it.data(Qt.UserRole)
            chosen["data"] = d
            preview.setPlainText(d.get("content", ""))

        def on_load():
            d = chosen.get("data")
            if not d:
                return
            content = d.get("content", "")
            curpos = int(d.get("cursor_pos") or 0)
            self.editor_original.setPlainText(content)
            self.editor.setPlainText(content)
            c = self.editor.textCursor()
            try:
                c.setPosition(curpos)
                self.editor.setTextCursor(c)
            except Exception:
                pass
            self.rebuild_lrc_index()
            self.statusBar().showMessage("已从快照载入到编辑器（未保存到文件）")
            dlg.accept()

        def on_overwrite():
            if not self.current_lrc_path:
                return
            d = chosen.get("data")
            if not d:
                return
            content = d.get("content", "")
            self.current_lrc_path.write_text(content, encoding="utf-8")
            self.editor_original.setPlainText(content)
            self.editor.setPlainText(content)
            self.rebuild_lrc_index()
            # 也记录新的快照（恢复点）
            self.snapshot_store.save_snapshot(self.current_lrc_path.name, content, cursor_pos=self.editor.textCursor().position())
            self.statusBar().showMessage("已从快照恢复并覆盖保存到文件")
            dlg.accept()

        lst.currentItemChanged.connect(lambda _n, _o: on_sel_changed())
        box.rejected.connect(dlg.reject)
        btn_load.clicked.connect(on_load)
        btn_overwrite.clicked.connect(on_overwrite)
        lst.setCurrentRow(0)
        on_sel_changed()
        dlg.exec()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
