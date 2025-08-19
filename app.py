import os
import sys
import re
import logging
from logging.handlers import RotatingFileHandler
import traceback
from pathlib import Path
from typing import List, Dict, Any

# ----- Logging ---------------------------------------------------------------
LOG_DIR = Path("logs"); LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"
logger = logging.getLogger("searchex"); logger.setLevel(logging.INFO)
_handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_handler)
logger.info("=== Start searchex ===")

# ----- PySide6 ---------------------------------------------------------------
from PySide6.QtCore import Qt, QRunnable, QThreadPool, Signal, QObject, QSize, Slot, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLineEdit,
    QPushButton, QFileDialog, QPlainTextEdit, QCheckBox, QSpinBox, QLabel,
    QListWidget, QListWidgetItem, QProgressBar, QMessageBox, QFrame, QSplitter
)

# ----- Native extension ------------------------------------------------------
try:
    from searchex import searchex_native as sx
except Exception as e:
    sx = None
    logger.error("Failed to import searchex_native: %s", e)

# ----- Styling ---------------------------------------------------------------
DARK_QSS = """
QWidget { background: #101317; color: #e6e6e6; font-size: 12pt; }
QLineEdit, QPlainTextEdit { background: #161a20; border: 1px solid #2b2f36; border-radius: 6px; padding: 6px; }
QPushButton { background: #1d232b; border: 1px solid #2b2f36; padding: 6px 10px; border-radius: 6px; }
QPushButton:hover { background: #232a33; }
QPushButton:disabled { color: #888; }
QProgressBar { border: 1px solid #2b2f36; border-radius: 6px; background: #161a20; text-align: center; }
QProgressBar::chunk { background: #3b82f6; border-radius: 6px; }
QFrame#Tile { background: #131821; border: 1px solid #2b2f36; border-radius: 10px; }
QLabel#Path { color: #9fb0c7; }
"""

# ----- Helpers ---------------------------------------------------------------
def hum_bytes(n: int) -> str:
    for unit in ["B","KB","MB","GB","TB"]:
        if n < 1024.0: return f"{n:.0f}{unit}"
        n /= 1024.0
    return f"{n:.0f}PB"

def is_hidden(p: Path) -> bool:
    if os.name == "nt":
        try:
            import ctypes
            attrs = ctypes.windll.kernel32.GetFileAttributesW(str(p))
            return bool(attrs & 2)
        except Exception:
            return False
    return p.name.startswith(".")

# ----- Worker infra ----------------------------------------------------------
class WorkerSignals(QObject):
    result = Signal(dict)        # { path, hits:[{pattern, positions, lines}], is_binary, error, file_size }
    file_done = Signal(str)
    problem = Signal(str, str)
    all_done = Signal()

class FileScanTask(QRunnable):
    def __init__(self, path: str, patterns: List[str], opts: Dict[str, Any], signals: WorkerSignals):
        super().__init__()
        self.path = path
        self.patterns = patterns
        self.opts = opts
        self.signals = signals

    @Slot()
    def run(self):
        try:
            max_bytes = 0 if self.opts["max_mb"] <= 0 else int(self.opts["max_mb"] * 1024 * 1024)
            if sx:
                res = sx.search_in_file(
                    self.path,
                    self.patterns,
                    self.opts["case_sensitive"],
                    self.opts["use_regex"],
                    self.opts["whole_word"],
                    max_bytes
                )
            else:
                res = self._fallback_py(self.path, self.patterns, self.opts)
            if res.get("error"):
                self.signals.problem.emit(self.path, str(res["error"]))
            self.signals.result.emit(res)
        except Exception as e:
            logger.error("Task error '%s': %s\n%s", self.path, e, traceback.format_exc())
            self.signals.problem.emit(self.path, str(e))
        finally:
            self.signals.file_done.emit(self.path)

    # Minimal Python fallback (slower), also returns lines
    def _fallback_py(self, path, patterns, opts):
        d = {"path": path, "is_binary": False, "error": None, "file_size": 0, "hits": []}
        try:
            data = Path(path).read_bytes()
            d["file_size"] = len(data)
            if opts["max_mb"] > 0 and len(data) > int(opts["max_mb"] * 1024 * 1024):
                d["error"] = "Skipped: file size > limit"
                return d
            is_bin = b"\x00" in data
            d["is_binary"] = is_bin
            text = data.decode("utf-8", errors="ignore")
            for pat in patterns:
                positions, lines = [], []
                if opts["use_regex"]:
                    flags = 0 if opts["case_sensitive"] else re.IGNORECASE
                    for m in re.finditer(pat, text, flags):
                        positions.append(m.start())
                        lines.append(text.count("\n", 0, m.start()) + 1)
                else:
                    hay = text if opts["case_sensitive"] else text.lower()
                    needle = pat if opts["case_sensitive"] else pat.lower()
                    start = 0
                    while True:
                        i = hay.find(needle, start)
                        if i < 0: break
                        if opts["whole_word"]:
                            left_ok = (i == 0) or not (text[i-1].isalnum() or text[i-1] == "_")
                            right_ok = (i+len(pat) >= len(text)) or not (text[i+len(pat)].isalnum() or text[i+len(pat)] == "_")
                            if not (left_ok and right_ok):
                                start = i + 1; continue
                        positions.append(i)
                        lines.append(text.count("\n", 0, i) + 1)
                        start = i + 1
                d["hits"].append({"pattern": pat, "positions": positions, "lines": lines})
        except Exception as e:
            d["error"] = str(e)
        return d

# ----- Tile widget -----------------------------------------------------------
class TileWidget(QFrame):
    def __init__(self, info: Dict[str, Any], options: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.setObjectName("Tile")
        self.info = info
        self.options = options
        self._build()

    def _build(self):
        from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout
        path = Path(self.info["path"])
        hits = self.info.get("hits", [])
        total_hits = sum(len(h["positions"]) for h in hits)
        is_bin = self.info.get("is_binary", False)
        err = self.info.get("error")

        # unique line numbers across all patterns
        line_set = set()
        for h in hits:
            for ln in h.get("lines", []):
                line_set.add(int(ln))
        unique_lines = sorted(line_set)
        lines_preview = ", ".join(str(x) for x in unique_lines[:20])
        more = "" if len(unique_lines) <= 20 else f" … (+{len(unique_lines)-20} more)"

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)

        # determine first match once (for the Jump button and preview)
        first_pos = None
        first_pat = None
        for h in hits:
            if h["positions"]:
                first_pos = int(h["positions"][0])
                first_pat = h["pattern"]
                break

        # --- TOP BAR -------------------------------------------------------------
        top = QHBoxLayout()
        name_lbl = QLabel(path.name)
        name_lbl.setStyleSheet("font-weight: 600; font-size: 14pt;")
        path_lbl = QLabel(str(path))
        path_lbl.setObjectName("Path")
        path_lbl.setToolTip(str(path))

        open_btn = QPushButton("Open")
        open_btn.clicked.connect(lambda: os.startfile(str(path)))

        reveal_btn = QPushButton("Reveal in Explorer")
        reveal_btn.clicked.connect(lambda: os.system(f'explorer /select,"{path}"'))

        jump_btn = QPushButton("Jump to first hit")
        jump_btn.setToolTip("Open preview and jump to the first match")
        if first_pos is None:
            jump_btn.setEnabled(False)
        else:
            jump_btn.clicked.connect(
                lambda checked=False, p=path, pos=first_pos, b=is_bin: self.open_preview(p, pos, b)
            )

        top.addWidget(name_lbl)
        top.addStretch(1)
        top.addWidget(open_btn)
        top.addWidget(reveal_btn)
        top.addWidget(jump_btn)   # <-- now in the top bar
        lay.addLayout(top)

        lay.addWidget(path_lbl)

        info_lbl = QLabel(
            f"Matches: {total_hits}   •   Size: {hum_bytes(int(self.info.get('file_size', 0)))}   •   {'Binary' if is_bin else 'Text'}"
        )
        lay.addWidget(info_lbl)

        if unique_lines:
            lay.addWidget(QLabel(f"Lines: {lines_preview}{more}"))

        # First match preview (no extra jump button below anymore)
        if first_pos is not None:
            prev = QPlainTextEdit()
            prev.setReadOnly(True)
            prev.setMinimumHeight(120)
            if is_bin:
                prev.setPlainText(self._read_hex_preview(path, first_pos))
            else:
                text = self._read_text_preview(path, first_pos)
                if first_pat:
                    try:
                        flags = 0 if self.options["case_sensitive"] else re.IGNORECASE
                        rx = re.compile(
                            re.escape(first_pat) if not self.options["use_regex"] else first_pat,
                            flags
                        )
                        text = rx.sub(lambda m: f"«{m.group(0)}»", text)
                    except re.error:
                        pass
                prev.setPlainText(text)
            lay.addWidget(prev)

        if err:
            lay.addWidget(QLabel(f"⚠️ Problem: {err}"))


    def _read_text_preview(self, path: Path, pos: int, span: int = 120) -> str:
        try:
            data = path.read_bytes()
            start = max(0, pos - span); end = min(len(data), pos + span)
            return data[start:end].decode("utf-8", errors="replace")
        except Exception as e:
            return f"[Preview error: {e}]"

    def _read_hex_preview(self, path: Path, pos: int, span: int = 64) -> str:
        try:
            data = path.read_bytes()
            start = max(0, pos - span); end = min(len(data), pos + span)
            chunk = data[start:end]
            return " ".join(f"{b:02X}" for b in chunk)
        except Exception as e:
            return f"[Preview error: {e}]"

    def open_preview(self, path: Path, pos: int, is_bin: bool):
        # Use QPlainTextEdit (supports centerCursor())
        w = QMainWindow(self); w.setWindowTitle(f"Preview – {path.name}")
        txt = QPlainTextEdit(); txt.setReadOnly(True)
        if is_bin:
            txt.setPlainText(self._read_hex_preview(path, pos))
        else:
            try:
                data = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                data = path.read_bytes().decode("latin-1", errors="replace")
            txt.setPlainText(data)
            cur = txt.textCursor()
            cur.setPosition(min(pos, len(data)))
            txt.setTextCursor(cur)
            txt.centerCursor()         # <-- works with QPlainTextEdit
        w.setCentralWidget(txt); w.resize(900, 600); w.show()

# ----- Main window -----------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Searchex - Ultimate Searching")
        self.resize(1200, 800)
        self.setAcceptDrops(True)
        self.pool = QThreadPool.globalInstance()

        self._build_ui()
        self._connect()

        self.status = self.statusBar()
        self.pbar = QProgressBar(); self.pbar.setMaximum(0); self.pbar.setValue(0)
        self.status_label = QLabel("Ready.")
        self.status.addPermanentWidget(self.status_label)
        self.status.addPermanentWidget(self.pbar, 1)

        self.cancelled = False
        self.files_total = 0
        self.files_done = 0

        # Responsive UI: batch/queue rendering
        self._pending_results: List[dict] = []
        self._pending_problems: List[tuple] = []
        self._flush_timer = QTimer(self); self._flush_timer.setInterval(30)
        self._flush_timer.timeout.connect(self._flush_queues)
        self._flush_timer.start()
        self._batch_size = 12

        self.current_options: Dict[str, Any] = {}
        self.current_patterns: List[str] = []

        self.error_count = 0
        self._update_error_toggle()

    def _build_ui(self):
        central = QWidget(); root = QVBoxLayout(central); root.setContentsMargins(10,10,10,10); root.setSpacing(10)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(); self.path_edit.setPlaceholderText("Drop a folder/file here or choose …")
        self.btn_browse_dir = QPushButton("Choose folder")
        self.btn_browse_file = QPushButton("Choose file")
        path_row.addWidget(self.path_edit, 1); path_row.addWidget(self.btn_browse_dir); path_row.addWidget(self.btn_browse_file)
        root.addLayout(path_row)

        self.query_edit = QPlainTextEdit()
        self.query_edit.setPlaceholderText("Search patterns (one per line) – optional regex.")
        self.query_edit.setFixedHeight(64)  # smaller input area
        root.addWidget(self.query_edit)

        opts = QHBoxLayout()
        self.chk_case = QCheckBox("Case sensitive")
        self.chk_regex = QCheckBox("Regex")
        self.chk_word = QCheckBox("Whole word")
        self.chk_names = QCheckBox("Match file/folder names")
        self.chk_hidden = QCheckBox("Include hidden")
        self.spin_max_mb = QSpinBox(); self.spin_max_mb.setRange(0, 100000); self.spin_max_mb.setValue(0)
        self.spin_threads = QSpinBox(); self.spin_threads.setRange(1, max(1, os.cpu_count() or 4)); self.spin_threads.setValue(min(8, max(1, os.cpu_count() or 4)))
        opts.addWidget(self.chk_case); opts.addWidget(self.chk_regex); opts.addWidget(self.chk_word)
        opts.addWidget(self.chk_names); opts.addWidget(self.chk_hidden)
        opts.addWidget(QLabel("Max MB (0=∞)")); opts.addWidget(self.spin_max_mb)
        opts.addWidget(QLabel("Threads")); opts.addWidget(self.spin_threads)
        root.addLayout(opts)

        ctrl = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_cancel = QPushButton("Cancel")
        ctrl.addWidget(self.btn_start); ctrl.addWidget(self.btn_cancel); ctrl.addStretch(1)
        root.addLayout(ctrl)

        # Results + Errors area with splitter so errors take minimal space
        self.splitter = QSplitter(Qt.Vertical)
        self.list = QListWidget(); self.list.setSpacing(8)
        # --- Collapsible errors section ---
        err_container = QWidget(); err_layout = QVBoxLayout(err_container); err_layout.setContentsMargins(0,0,0,0); err_layout.setSpacing(4)
        self.err_toggle = QPushButton("")  # text set later
        self.err_toggle.setCheckable(True); self.err_toggle.setChecked(False)  # start collapsed
        self.err_toggle.setFlat(True); self.err_toggle.setStyleSheet("text-align: left; padding: 2px;")
        self.err_toggle.toggled.connect(self._toggle_errors_visible)
        self.problems = QListWidget(); self.problems.setSpacing(3)
        self.problems.setVisible(False)
        err_layout.addWidget(self.err_toggle)
        err_layout.addWidget(self.problems)

        self.splitter.addWidget(self.list)
        self.splitter.addWidget(err_container)
        self.splitter.setSizes([900, 120])   # give most space to results
        root.addWidget(self.splitter, 1)

        self.setCentralWidget(central)

    def _update_error_toggle(self):
        arrow = "▸" if not getattr(self, "err_toggle", None) or not self.err_toggle.isChecked() else "▾"
        text = f"{arrow} Errors / skipped files ({self.error_count})"
        if getattr(self, "err_toggle", None):
            self.err_toggle.setText(text)

    def _toggle_errors_visible(self, checked: bool):
        self.problems.setVisible(checked)
        self._update_error_toggle()

    def _connect(self):
        self.btn_browse_dir.clicked.connect(self.choose_dir)
        self.btn_browse_file.clicked.connect(self.choose_file)
        self.btn_start.clicked.connect(self.on_start)
        self.btn_cancel.clicked.connect(self.on_cancel)

    # DnD
    def dragEnterEvent(self, e): 
        if e.mimeData().hasUrls(): e.acceptProposedAction()
    def dropEvent(self, e):
        urls = e.mimeData().urls()
        if urls: self.path_edit.setText(urls[0].toLocalFile())

    def choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose folder")
        if d: self.path_edit.setText(d)

    def choose_file(self):
        f, _ = QFileDialog.getOpenFileName(self, "Choose file")
        if f: self.path_edit.setText(f)

    def _gather_patterns(self) -> List[str]:
        lines = [ln.strip() for ln in self.query_edit.toPlainText().splitlines()]
        return [ln for ln in lines if ln]

    def _enum_files(self, root_path: Path, include_hidden: bool) -> List[Path]:
        files = []
        if root_path.is_file(): return [root_path]
        for dirpath, dirnames, filenames in os.walk(root_path):
            dpath = Path(dirpath)
            if not include_hidden and is_hidden(dpath): continue
            for fn in filenames:
                p = dpath / fn
                if not include_hidden and is_hidden(p): continue
                files.append(p)
        return files

    def on_start(self):
        base = Path(self.path_edit.text().strip())
        if not base.exists():
            QMessageBox.warning(self, "Error", "Please select an existing folder or file.")
            return
        patterns = self._gather_patterns()
        if not patterns:
            QMessageBox.information(self, "Hint", "Add at least one search pattern (one per line).")
            return

        self.list.clear()
        self.problems.clear()
        self._pending_results.clear()
        self._pending_problems.clear()
        self.cancelled = False
        self.files_done = 0
        self.error_count = 0
        self._update_error_toggle()

        options = {
            "case_sensitive": self.chk_case.isChecked(),
            "use_regex": self.chk_regex.isChecked(),
            "whole_word": self.chk_word.isChecked(),
            "name_match": self.chk_names.isChecked(),
            "include_hidden": self.chk_hidden.isChecked(),
            "max_mb": self.spin_max_mb.value()
        }
        self.current_options = options
        self.current_patterns = patterns

        files = self._enum_files(base, include_hidden=options["include_hidden"])
        self.files_total = len(files)
        self.pbar.setMaximum(max(1, self.files_total)); self.pbar.setValue(0)
        self.status_label.setText(f"{self.files_done}/{self.files_total} files …")
        self.pool.setMaxThreadCount(self.spin_threads.value())

        self.signals = WorkerSignals()
        self.signals.result.connect(self._enqueue_result)
        self.signals.file_done.connect(self.on_file_done)
        self.signals.problem.connect(self._enqueue_problem)
        self.signals.all_done.connect(self.on_all_done)

        # quick name matches
        if options["name_match"]:
            for p in files:
                name = p.name
                if self._name_matches(name, patterns, options):
                    fake = {
                        "path": str(p),
                        "is_binary": False,
                        "error": None,
                        "file_size": p.stat().st_size if p.exists() else 0,
                        "hits": [{"pattern": "(name)", "positions": [0], "lines": [1]}]
                    }
                    self._enqueue_result(fake)

        for p in files:
            if self.cancelled: break
            t = FileScanTask(str(p), patterns, options, self.signals)
            self.pool.start(t)

        def check_done():
            if self.pool.activeThreadCount() == 0:
                self.signals.all_done.emit()
            else:
                QTimer.singleShot(300, check_done)
        QTimer.singleShot(300, check_done)

        self.status_label.setText("Searching …")
        self.btn_start.setEnabled(False)

    def _name_matches(self, name: str, patterns: List[str], options: Dict[str, Any]) -> bool:
        if not patterns: return False
        hay = name if options["case_sensitive"] else name.lower()
        for pat in patterns:
            if options["use_regex"]:
                flags = 0 if options["case_sensitive"] else re.IGNORECASE
                try:
                    if re.search(pat, name, flags): return True
                except re.error:
                    continue
            else:
                needle = pat if options["case_sensitive"] else pat.lower()
                if options["whole_word"]:
                    if re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", hay): return True
                else:
                    if needle in hay: return True
        return False

    def on_cancel(self):
        self.cancelled = True
        self.status_label.setText("Cancel requested (running files will finish).")

    def on_file_done(self, path: str):
        self.files_done += 1
        self.pbar.setValue(self.files_done)
        if self.files_done % 10 == 0 or self.files_done == self.files_total:
            self.status_label.setText(f"{self.files_done}/{self.files_total} files …")

    # ---- Queues + batch flush keeps the UI responsive ----
    @Slot(dict)
    def _enqueue_result(self, d: dict):
        self._pending_results.append(d)

    @Slot(str, str)
    def _enqueue_problem(self, path: str, err: str):
        self._pending_problems.append((path, err))
        self.error_count += 1
        self._update_error_toggle()
        logger.warning("Problem %s: %s", path, err)

    def _flush_queues(self):
        # Render results in small batches
        count = 0
        while self._pending_results and count < self._batch_size:
            info = self._pending_results.pop(0)
            self._add_result_tile(info, self.current_options)
            count += 1
        # Problems can be flushed more aggressively
        pcount = 0
        while self._pending_problems and pcount < 50:
            path, err = self._pending_problems.pop(0)
            it = QListWidgetItem(f"{path} — {err}")
            self.problems.addItem(it)
            pcount += 1

    def _add_result_tile(self, info: Dict[str, Any], options: Dict[str, Any]):
        hits_count = sum(len(h["positions"]) for h in info.get("hits", []))
        if hits_count == 0 and not info.get("error"): return
        w = TileWidget(info, options, self.list)
        it = QListWidgetItem(self.list); it.setSizeHint(QSize(800, 220))
        self.list.setItemWidget(it, w)

    def on_all_done(self):
        # flush remaining queued items
        self._flush_queues()
        self.btn_start.setEnabled(True)
        self.status_label.setText("Done.")
        logger.info("Search finished: %d/%d files", self.files_done, self.files_total)

# ----- Entry point -----------------------------------------------------------
def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    app.setFont(QFont("Segoe UI", 10))

    app.setWindowIcon(QIcon("resources/logo.png"))


    win = MainWindow()
    win.setWindowIcon(QIcon("resources/logo.png"))
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
