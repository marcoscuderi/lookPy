"""First desktop shell: script editing, isolated Run all, inspection and picking.

No numerical reduction functions are implemented here. Run section and a
general Python console are intentionally deferred until execution semantics
are defined and tested.
"""
import json
import os
from pathlib import Path
import sys
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg
from .calibration import Registry
from .io import read_state
from .util import file_digest
from .editor import CodeEditor, editor_panel
from . import __version__

pg.setConfigOptions(background="w", foreground="#203647", antialias=False)


class PlotPanel(QtWidgets.QWidget):
    picked = QtCore.Signal(str)

    def __init__(self, exp, spec):
        super().__init__()
        self.exp, self.spec = exp, spec
        self.last_picks = []
        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QHBoxLayout()
        self.auto = QtWidgets.QCheckBox("Fit both Y axes to visible X")
        self.auto.setChecked(True)
        controls.addWidget(self.auto)
        reset = QtWidgets.QPushButton("Reset view")
        controls.addWidget(reset)
        copy = QtWidgets.QPushButton("Copy interval from last 2 picks")
        copy.clicked.connect(self.copy_interval)
        controls.addWidget(copy)
        layout.addLayout(controls)
        self.plot = pg.PlotWidget()
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        layout.addWidget(self.plot)
        self.status = QtWidgets.QLabel("Click near a curve: the exact original record and coordinates are copied and printed below.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.primary = self.plot.getPlotItem()
        self.primary.setLabel("bottom", self.label(spec["x"]))
        self.primary.setLabel("left", self.label(spec["left"]))
        self.secondary = pg.ViewBox()
        self.plot.scene().addItem(self.secondary)
        self.primary.getAxis("right").linkToView(self.secondary)
        self.secondary.setXLink(self.primary.vb)
        self.secondary.setMouseEnabled(x=False, y=False)
        self.primary.vb.sigResized.connect(self.sync_views)
        self.primary.vb.sigXRangeChanged.connect(self.rescale)
        self.curves = []
        x = exp[spec["x"]].values
        monotonic = np.isfinite(x).all() and bool(np.all(np.diff(x) >= 0))
        for axis, channel, color in [(self.primary.vb, spec["left"], "#20658c"),
                                      (self.secondary, spec.get("right"), "#be632f")]:
            if channel is None:
                continue
            y = exp[channel].values
            curve = pg.PlotDataItem(x, y, pen=pg.mkPen(color, width=1), connect="finite")
            # Parent first: enabling clipToView while scene ownership changes can
            # make pyqtgraph temporarily resolve a PlotWidget as the ViewBox.
            axis.addItem(curve)
            if monotonic:
                curve.setDownsampling(auto=True, method="peak")
                curve.setClipToView(True)
            self.curves.append((axis, channel, x, y))
        self.primary.showAxis("right", spec.get("right") is not None)
        if spec.get("right"):
            self.primary.setLabel("right", self.label(spec["right"]))
        self.crosshair = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#9babb4", style=QtCore.Qt.PenStyle.DashLine))
        self.primary.addItem(self.crosshair, ignoreBounds=True)
        self.plot.scene().sigMouseClicked.connect(self.click)
        self.proxy = pg.SignalProxy(self.plot.scene().sigMouseMoved, rateLimit=20, slot=self.hover)
        self.auto.toggled.connect(lambda _: self.rescale())
        reset.clicked.connect(self.reset)
        self.sync_views()
        self.reset()

    def label(self, name):
        return f"{name} [{self.exp[name].unit}]"

    def sync_views(self):
        self.secondary.setGeometry(self.primary.vb.sceneBoundingRect())
        self.secondary.linkedViewChanged(self.primary.vb, self.secondary.XAxis)

    def reset(self):
        x = self.exp[self.spec["x"]].values
        good = x[np.isfinite(x)]
        if len(good):
            self.primary.vb.setXRange(float(good.min()), float(good.max()), padding=.02)
        self.rescale()

    def rescale(self, *args):
        if not self.auto.isChecked():
            return
        lo, hi = self.primary.vb.viewRange()[0]
        for axis, name, x, y in self.curves:
            v = y[np.isfinite(x) & np.isfinite(y) & (x >= lo) & (x <= hi)]
            if len(v):
                low, high = float(v.min()), float(v.max())
                pad = (high-low)*.05 if high > low else max(abs(low)*.05, 1e-6)
                axis.setYRange(low-pad, high+pad, padding=0)

    def hover(self, events):
        position = events[0]
        if self.primary.vb.sceneBoundingRect().contains(position):
            self.crosshair.setValue(self.primary.vb.mapSceneToView(position).x())

    def nearest(self, position):
        """Full-resolution screen-distance picking, including nonmonotonic X."""
        best = None
        for axis, name, x, y in self.curves:
            rect = axis.sceneBoundingRect()
            if not rect.contains(position):
                continue
            (x0, x1), (y0, y1) = axis.viewRange()
            if x1 == x0 or y1 == y0:
                continue
            valid = np.isfinite(x) & np.isfinite(y) & (x >= min(x0, x1)) & (x <= max(x0, x1))
            ids = np.flatnonzero(valid)
            if not len(ids):
                continue
            # Mapping through the ViewBox supports both independently scaled Y axes.
            local = axis.mapSceneToView(position)
            dx = (x[ids]-local.x())/(x1-x0)*rect.width()
            dy = (y[ids]-local.y())/(y1-y0)*rect.height()
            distance = dx*dx+dy*dy
            j = int(np.argmin(distance))
            candidate = (float(distance[j]), int(ids[j]), name)
            if best is None or candidate[0] < best[0]:
                best = candidate
        return best if best and best[0] <= 25**2 else None

    def click(self, event):
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        point = self.nearest(event.scenePos())
        if point is None:
            return
        _, i, channel = point
        record = int(self.exp.record_ids[i])
        self.last_picks = (self.last_picks+[record])[-2:]
        xname = self.spec["x"]
        text = f"record_id={record}; {xname}={self.exp[xname].values[i]:.17g} {self.exp[xname].unit}; {channel}={self.exp[channel].values[i]:.17g} {self.exp[channel].unit}"
        self.status.setText(text)
        QtWidgets.QApplication.clipboard().setText(str(record))
        self.picked.emit(text+"\nCopied record ID to clipboard.")
        self.primary.addItem(pg.InfiniteLine(pos=self.exp[xname].values[i], angle=90,
                             pen=pg.mkPen("#6d8056", style=QtCore.Qt.PenStyle.DotLine)), ignoreBounds=True)

    def copy_interval(self):
        if len(self.last_picks) < 2:
            self.status.setText("Pick two points first.")
            return
        a, b = sorted(self.last_picks)
        text = f"exp.records({a}, {b})"
        QtWidgets.QApplication.clipboard().setText(text)
        self.status.setText("Copied "+text+" (inclusive original record IDs)")
        self.picked.emit("Copied "+text)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, script=None, registry=None):
        super().__init__()
        self.setWindowTitle(f"Xlook Python — {__version__} test implementation")
        self.resize(1600, 950)
        self.registry = Registry(registry)
        self.script = None
        self.exp = None
        self.manifest = None
        self.process = None
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.setCentralWidget(self.tabs)
        self.editor = CodeEditor()
        self.editor.sourceChanged.connect(self.edited)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.info = QtWidgets.QPlainTextEdit()
        self.info.setReadOnly(True)
        self.channels = QtWidgets.QTableWidget(0, 3)
        self.channels.setHorizontalHeaderLabels(["Channel", "Unit", "Invalid"])
        self.channels.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.channels.itemSelectionChanged.connect(self.channel_info)
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.addWidget(self.channels)
        self.selectors = {}
        for key in ("x", "left", "right"):
            left_layout.addWidget(QtWidgets.QLabel(key.upper()+" axis channel"))
            combo = QtWidgets.QComboBox()
            self.selectors[key] = combo
            left_layout.addWidget(combo)
        plot = QtWidgets.QPushButton("Plot selected channels")
        plot.clicked.connect(self.custom_plot)
        left_layout.addWidget(plot)
        left_layout.addWidget(self.info)
        left_dock = self.add_dock("Experiment and channels", left, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        right_dock = self.add_dock("Reduction script", editor_panel(self.editor), QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        bottom_dock = self.add_dock("Execution log and picked points", self.log, QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)
        self.resizeDocks([left_dock, right_dock], [280, 480], QtCore.Qt.Orientation.Horizontal)
        self.resizeDocks([bottom_dock], [160], QtCore.Qt.Orientation.Vertical)
        toolbar = self.addToolBar("Project")
        for title, callback in [("Open script", self.open_dialog), ("Save", self.save),
                                ("Run all", self.run_all), ("Cancel", self.cancel),
                                ("Registry folder", self.choose_registry), ("Import calibration", self.import_calibration),
                                ("List calibrations", self.list_calibrations)]:
            action = toolbar.addAction(title)
            action.triggered.connect(callback)
        self.link_action = toolbar.addAction("Link matching X axes")
        self.link_action.setCheckable(True)
        self.link_action.setChecked(True)
        self.link_action.toggled.connect(self.link_plots)
        self.statusBar().showMessage("Open a reduction.py script to begin.")
        if script:
            self.open_script(Path(script))

    def add_dock(self, title, widget, area):
        dock = QtWidgets.QDockWidget(title, self)
        dock.setWidget(widget)
        self.addDockWidget(area, dock)
        return dock

    def close_tab(self, index):
        widget = self.tabs.widget(index)
        self.tabs.removeTab(index)
        widget.deleteLater()

    def clear_tabs(self):
        while self.tabs.count():
            self.close_tab(0)

    def edited(self):
        if self.script:
            self.statusBar().showMessage("Script edited — save and Run all to update results. Displayed results are from the last successful run.")

    def open_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open reduction", "", "Python (*.py)")
        if path:
            self.open_script(Path(path))

    def open_script(self, path):
        if self.process is not None:
            self.log.appendPlainText("Wait for or cancel the current run before opening another project.")
            return
        self.script = path.expanduser().resolve()
        self.editor.setPlainText(self.script.read_text(encoding="utf-8"))
        self.clear_tabs()
        self.exp = None
        self.channels.setRowCount(0)
        self.setWindowTitle(f"Xlook Python — {self.script}")
        manifest = self.script.parent/"experiment.json"
        if manifest.exists():
            self.load_result()
        else:
            self.statusBar().showMessage("Ready. Run all to load and reduce this experiment.")

    def save(self):
        if self.script:
            self.script.write_text(self.editor.toPlainText(), encoding="utf-8")

    def run_all(self):
        if not self.script or self.process is not None:
            return
        self.save()
        self.running_script = self.script
        self.process = QtCore.QProcess(self)
        self.process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.read_log)
        self.process.finished.connect(self.finished)
        self.process.errorOccurred.connect(self.process_error)
        self.log.appendPlainText(f"\nRun all: {self.script}\nCentral registry: {self.registry.root}")
        self.statusBar().showMessage("Running from fresh state in a separate process…")
        self.process.start(sys.executable, ["-u", "-m", "xlookpy", "run", str(self.script), "--registry", str(self.registry.root)])

    def read_log(self):
        if self.process:
            self.log.appendPlainText(bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace"))

    def process_error(self, error):
        self.log.appendPlainText(f"Worker error: {error}")
        if error == QtCore.QProcess.ProcessError.FailedToStart:
            self.process.deleteLater()
            self.process = None
            self.statusBar().showMessage("Worker could not start. Last successful results retained.")

    def finished(self, code, status):
        self.read_log()
        self.process.deleteLater()
        self.process = None
        if code == 0 and status == QtCore.QProcess.ExitStatus.NormalExit:
            self.load_result()
        else:
            self.statusBar().showMessage("Run failed/cancelled. Last successful results retained.")

    def cancel(self):
        if self.process:
            self.process.kill()

    def load_result(self):
        try:
            manifest = json.loads((self.script.parent/"experiment.json").read_text(encoding="utf-8"))
            if manifest["script"]["path"] != self.script.name:
                raise ValueError("Manifest belongs to another script in this directory.")
            path = self.script.parent/manifest["outputs"]["state"]
            if file_digest(path) != manifest["outputs"]["state_sha256"]:
                raise ValueError("Cached experiment fingerprint mismatch. Run the reduction again.")
            self.exp = read_state(path, manifest)
            self.manifest = manifest
            self.channels.setRowCount(len(self.exp.channels))
            for i, name in enumerate(self.exp.channels):
                c = self.exp[name]
                for j, value in enumerate((name, c.unit, str((~c.valid).sum()))):
                    self.channels.setItem(i, j, QtWidgets.QTableWidgetItem(value))
            for key, combo in self.selectors.items():
                combo.clear()
                if key == "right":
                    combo.addItem("(none)")
                combo.addItems(self.exp.channels)
            if "time" in self.exp.channels:
                self.selectors["x"].setCurrentText("time")
            self.clear_tabs()
            for spec in manifest["plots"]:
                self.add_plot(spec)
            self.info.setPlainText(f"Records: {len(self.exp):,}\nOriginal IDs: {self.exp.record_ids[0]}–{self.exp.record_ids[-1]}\nRun: {manifest['run_id']}\nCalibrations: {len(manifest['calibrations'])}\nRegistry: {self.registry.root}")
            current = self.editor.toPlainText().encode()
            import hashlib
            stale = hashlib.sha256(current).hexdigest() != manifest["script"]["sha256"]
            self.statusBar().showMessage("Script differs from displayed results — Run all to update." if stale else "Successful reduction loaded. Click curves to pick original record IDs.")
        except Exception as exc:
            self.log.appendPlainText(f"Cannot display result: {exc}")

    def add_plot(self, spec):
        panel = PlotPanel(self.exp, spec)
        panel.picked.connect(self.log.appendPlainText)
        self.tabs.addTab(panel, spec["title"])
        self.link_plots()

    def link_plots(self, *args):
        first = {}
        for i in range(self.tabs.count()):
            panel = self.tabs.widget(i)
            key = panel.spec["x"]
            parent = first.get(key) if self.link_action.isChecked() else None
            panel.primary.vb.setXLink(parent)
            if key not in first:
                first[key] = panel.primary.vb

    def custom_plot(self):
        if self.exp is not None:
            right = self.selectors["right"].currentText()
            self.add_plot({"x": self.selectors["x"].currentText(), "left": self.selectors["left"].currentText(),
                           "right": None if right == "(none)" else right, "title": "Custom plot"})

    def channel_info(self):
        rows = self.channels.selectionModel().selectedRows()
        row = rows[0].row() if rows else self.channels.currentRow()
        if self.exp is not None and 0 <= row < len(self.exp.channels):
            name = self.exp.channels[row]
            self.info.setPlainText(json.dumps({"channel": name, "unit": self.exp[name].unit,
                                              "metadata": self.exp[name].metadata}, indent=2))

    def choose_registry(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Central calibration registry", str(self.registry.root))
        if path:
            self.registry = Registry(path)
            self.log.appendPlainText(f"Registry selected for subsequent runs: {path}")

    def import_calibration(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import calibration revision", "", "JSON (*.json)")
        if path:
            try:
                c = self.registry.import_file(path)
                self.log.appendPlainText(f"Imported {c.id}\n"+json.dumps(c.record, indent=2))
            except Exception as exc:
                self.log.appendPlainText(f"Import refused: {exc}")

    def list_calibrations(self):
        try:
            self.log.appendPlainText(f"Registry: {self.registry.root}\n"+"\n".join(c.id for c in self.registry.list()))
        except Exception as exc:
            self.log.appendPlainText(str(exc))

    def closeEvent(self, event):
        if self.process:
            self.process.kill()
            self.process.waitForFinished(3000)
        super().closeEvent(event)


def launch(script=None, registry=None):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    window = MainWindow(script, registry)
    window.show()
    code = app.exec()
    window.deleteLater()
    app.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
    return code
