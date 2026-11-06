"""Desktop shell: embedded script editing, explicit plot tabs and picking.

Numerical functions remain in the core. Cell scripts and the console share an
isolated IPython process; legacy reduce(session) scripts keep their batch worker.
"""
import json
import os
from pathlib import Path
import sys
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg
from .analysis import fit_polynomial
from .calibration import Registry
from .io import read_state
from .util import file_digest
from .editor import CodeEditor, editor_panel
from . import __version__
from .workspace import cells, legacy_source, convert_legacy
from .console import WorkspaceConsole, KernelController

pg.setConfigOptions(background="w", foreground="#203647", antialias=False)


class PlotPanel(QtWidgets.QWidget):
    picked = QtCore.Signal(str)

    def __init__(self, exp, spec):
        super().__init__()
        self.exp, self.spec = exp, spec
        self.last_picks = []
        self.pick_markers = []
        self.fit_start = None
        self.fit_marker = None
        self.fit_overlay = None
        self._updating = False
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
        fit_controls = QtWidgets.QHBoxLayout()
        fit_controls.addWidget(QtWidgets.QLabel("Fit degree"))
        self.fit_degree = QtWidgets.QComboBox()
        self.fit_degree.addItem("1 · Linear", 1)
        for degree in range(2, 7):
            self.fit_degree.addItem(str(degree), degree)
        fit_controls.addWidget(self.fit_degree)
        self.fit_button = QtWidgets.QPushButton("Fit interval")
        self.fit_button.setCheckable(True)
        self.fit_button.setToolTip("Click two points on the same curve to fit the records between them.")
        self.fit_button.toggled.connect(self.toggle_fit)
        fit_controls.addWidget(self.fit_button)
        self.clear_fit_button = QtWidgets.QPushButton("Clear fit")
        self.clear_fit_button.clicked.connect(self.clear_fit)
        self.clear_fit_button.setEnabled(False)
        fit_controls.addWidget(self.clear_fit_button)
        fit_controls.addStretch()
        layout.addLayout(fit_controls)
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
        self.plot_items = []
        self.crosshair = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#9babb4", style=QtCore.Qt.PenStyle.DashLine))
        self.primary.addItem(self.crosshair, ignoreBounds=True)
        self.plot.scene().sigMouseClicked.connect(self.click)
        self.proxy = pg.SignalProxy(self.plot.scene().sigMouseMoved, rateLimit=20, slot=self.hover)
        self.auto.toggled.connect(lambda _: self.rescale())
        reset.clicked.connect(self.reset)
        self.sync_views()
        self.update_plot(exp, spec, preserve_x=False)

    def update_plot(self, exp, spec, *, preserve_x=True):
        """Replace axes/data in this widget, retaining X zoom for an unchanged X.

        Full-resolution arrays remain the source for bounds and picking. Remove
        the old curves and picked markers so stale coordinates cannot be reused.
        """
        spec = {"right": None, **spec}
        for name in (spec["x"], spec["left"], spec["right"]):
            if name is not None:
                exp[name]
        keep_range = self.primary.vb.viewRange()[0] if preserve_x and self.curves and self.spec["x"] == spec["x"] else None
        self._updating = True
        self.clear_fit()
        self.primary.vb.setXLink(None)
        for axis, item in self.plot_items:
            axis.removeItem(item)
        self.plot_items.clear()
        for marker in self.pick_markers:
            self.primary.removeItem(marker)
        self.pick_markers.clear()
        self.last_picks.clear()
        self.curves.clear()
        self.exp, self.spec = exp, dict(spec)
        self.primary.setLabel("bottom", self.label(spec["x"]))
        self.primary.setLabel("left", self.label(spec["left"]))
        self.primary.setLabel("right", self.label(spec["right"]) if spec["right"] else "")
        self.primary.showAxis("right", spec["right"] is not None)
        x = exp[spec["x"]].values
        monotonic = np.isfinite(x).all() and bool(np.all(np.diff(x) >= 0))
        for axis, channel, color in [(self.primary.vb, spec["left"], "#20658c"),
                                      (self.secondary, spec["right"], "#be632f")]:
            if channel is None:
                continue
            y = exp[channel].values
            curve = pg.PlotDataItem(x, y, pen=pg.mkPen(color, width=1), connect="finite")
            axis.addItem(curve)  # Parent before enabling clipToView.
            self.plot_items.append((axis, curve))
            if monotonic:
                curve.setDownsampling(auto=True, method="peak")
                curve.setClipToView(True)
            self.curves.append((axis, channel, x, y))
        self._updating = False
        self.status.setText("Click near a curve to print its exact original row and coordinates. Changing plotted axes clears previous picks.")
        if keep_range is None:
            self.reset()
        else:
            self.primary.vb.setXRange(*keep_range, padding=0)
            self.rescale()

    def label(self, name):
        if name == "record_id":
            return "Original row number (record_id)"
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
        if self._updating or not self.auto.isChecked():
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

    def nearest(self, position, *, channel=None):
        """Full-resolution screen-distance picking, including nonmonotonic X."""
        best = None
        for axis, name, x, y in self.curves:
            if channel is not None and channel != name:
                continue
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
        if self.fit_button.isChecked():
            self.pick_fit_endpoint(event.scenePos())
            return
        point = self.nearest(event.scenePos())
        if point is None:
            return
        _, i, channel = point
        record = int(self.exp.record_ids[i])
        self.last_picks = (self.last_picks+[record])[-2:]
        xname = self.spec["x"]
        xu = "row" if xname == "record_id" else self.exp[xname].unit
        yu = "row" if channel == "record_id" else self.exp[channel].unit
        text = f"record_id={record}; {xname}={self.exp[xname].values[i]:.17g} {xu}; {channel}={self.exp[channel].values[i]:.17g} {yu}"
        self.status.setText(text)
        QtWidgets.QApplication.clipboard().setText(str(record))
        self.picked.emit(text+"\nCopied record ID to clipboard.")
        marker = pg.InfiniteLine(pos=self.exp[xname].values[i], angle=90,
                                pen=pg.mkPen("#6d8056", style=QtCore.Qt.PenStyle.DotLine))
        self.primary.addItem(marker, ignoreBounds=True)
        self.pick_markers.append(marker)

    def toggle_fit(self, enabled):
        self.fit_start = None
        if self.fit_marker is not None:
            self.primary.removeItem(self.fit_marker)
            self.fit_marker = None
        self.status.setText("Click the first point on the curve you want to fit."
                            if enabled else "Click near a curve to pick its original record.")

    def clear_fit(self):
        self.fit_button.setChecked(False)
        if self.fit_overlay is not None:
            axis, item = self.fit_overlay
            axis.removeItem(item)
            self.fit_overlay = None
            self.status.setText("Fit cleared. Click near a curve to pick its original record.")
        self.clear_fit_button.setEnabled(False)

    def pick_fit_endpoint(self, position):
        channel = self.fit_start[1] if self.fit_start is not None else None
        point = self.nearest(position, channel=channel)
        if point is None:
            self.status.setText(f"Click near {channel} for the second endpoint." if channel
                                else "Click near a plotted curve for the first endpoint.")
            return
        _, i, channel = point
        xname = self.spec["x"]
        if self.fit_start is None:
            self.fit_start = (i, channel)
            self.fit_marker = pg.InfiniteLine(
                pos=self.exp[xname].values[i], angle=90,
                pen=pg.mkPen("#7943a0", style=QtCore.Qt.PenStyle.DotLine))
            self.primary.addItem(self.fit_marker, ignoreBounds=True)
            self.status.setText(f"First point at record {self.exp.record_ids[i]}. Click the second point on {channel}.")
            return

        start, end = sorted((self.fit_start[0], i))
        first, last = self.exp.record_ids[[start, end]]
        axis, _, x, y = next(curve for curve in self.curves if curve[1] == channel)
        x = x[start:end+1]
        y = y[start:end+1]
        good = np.isfinite(x) & np.isfinite(y)
        x, y = x[good], y[good]
        degree = self.fit_degree.currentData()
        xu = "row" if xname == "record_id" else self.exp[xname].unit
        yu = "row" if channel == "record_id" else self.exp[channel].unit
        try:
            poly, result = fit_polynomial(x, y, degree, x_unit=xu, y_unit=yu)
        except (ValueError, np.linalg.LinAlgError) as exc:
            self.fit_button.setChecked(False)
            message = f"Fit refused for records {first}–{last}: {exc}"
            self.status.setText(message)
            self.picked.emit(message)
            return

        self.clear_fit()
        xx = np.linspace(x.min(), x.max(), 256)
        item = pg.PlotDataItem(xx, poly(xx), pen=pg.mkPen("#7943a0", width=3))
        item.setZValue(10)
        axis.addItem(item, ignoreBounds=True)
        self.fit_overlay = (axis, item)
        self.clear_fit_button.setEnabled(True)
        title = f"Degree {degree} fit · {channel} vs {xname} · records {first}–{last}"
        coefficients = result["coefficients"]
        r_squared = result["r_squared"]
        quality = f"R² = {r_squared:.8g}" if r_squared is not None else "R² undefined"
        rmse = result["rmse"]
        error = f"RMSE = {rmse:.8g} {yu}" if rmse is not None else "RMSE unavailable"
        details = [f"{result['n_points']} samples, {quality}, {error}"]
        if degree == 1:
            # Polynomial.convert() can drop a trailing zero coefficient.
            slope = coefficients[1] if len(coefficients) > 1 else 0.0
            details.append(f"Slope = {slope:.12g} {yu}/{xu}, intercept = {coefficients[0]:.12g} {yu}")
        else:
            terms = ", ".join(f"a{j} = {value:.12g}" for j, value in enumerate(coefficients))
            details.append(f"Coefficients for y = a0 + a1*x + … (X in {xu}, Y in {yu}): {terms}")
        self.status.setText(f"{title}\n{details[-1]}")
        self.picked.emit("\n".join([title, *details]))

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
        self.kernel = None
        self._pending_workspace_action = None
        self._executed_source = ""
        self._workspace_cells = []
        self._updating_cells = False
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.plot_area = QtWidgets.QStackedWidget()
        self.no_plots = QtWidgets.QLabel("No plots open.\n\nRun the reduction, choose X / LEFT / RIGHT channels,\nthen click New plot tab.\n\nRefresh axes updates only the active plot.")
        self.no_plots.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.no_plots.setWordWrap(True)
        self.no_plots.setStyleSheet("color: #526B7A; font-size: 14pt;")
        self.plot_area.addWidget(self.no_plots)
        self.plot_area.addWidget(self.tabs)
        self.setCentralWidget(self.plot_area)
        self._plot_count = 0
        self.editor = CodeEditor()
        self.editor.sourceChanged.connect(self.edited)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.info = QtWidgets.QPlainTextEdit()
        self.info.setReadOnly(True)
        self.channels = QtWidgets.QTableWidget(0, 3)
        self.channels.setHorizontalHeaderLabels(["Channel", "Unit", "Invalid"])
        self.channels.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
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
        self.refresh_button = QtWidgets.QPushButton("Refresh axes")
        self.refresh_button.setObjectName("refreshAxes")
        self.refresh_button.setToolTip("Apply these channels to the active plot. No new tab is created.")
        self.refresh_button.clicked.connect(self.refresh_plot)
        self.new_plot_button = QtWidgets.QPushButton("New plot tab")
        self.new_plot_button.setObjectName("newPlotTab")
        self.new_plot_button.setToolTip("Create an additional plot using the selected channels.")
        self.new_plot_button.clicked.connect(self.new_plot)
        left_layout.addWidget(self.refresh_button)
        left_layout.addWidget(self.new_plot_button)
        self.tabs.currentChanged.connect(self.sync_axis_selectors)
        self.update_plot_controls()
        left_layout.addWidget(self.info)
        left_dock = self.add_dock("Experiment and channels", left, QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        script_panel = editor_panel(self.editor)
        self.workspace_status = QtWidgets.QLabel("Cell workspace not started")
        self.workspace_status.setWordWrap(True)
        script_panel.layout().insertWidget(1, self.workspace_status)
        self.cell_list = QtWidgets.QListWidget()
        self.cell_list.setMaximumHeight(150)
        self.cell_list.currentRowChanged.connect(self.select_cell)
        script_panel.layout().addWidget(self.cell_list)
        self.editor.cursorPositionChanged.connect(self.follow_cell)
        right_dock = self.add_dock("Reduction script", script_panel, QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        bottom_dock = self.add_dock("Execution log and picked points", self.log, QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)
        console_panel = QtWidgets.QWidget()
        console_layout = QtWidgets.QVBoxLayout(console_panel)
        console_controls = QtWidgets.QHBoxLayout()
        self.start_console_button = QtWidgets.QPushButton("Start IPython")
        self.start_console_button.clicked.connect(self.start_console)
        console_controls.addWidget(self.start_console_button)
        self.console_commands = QtWidgets.QComboBox()
        self.console_commands.setMinimumContentsLength(24)
        console_controls.addWidget(self.console_commands, 1)
        self.insert_command_button = QtWidgets.QPushButton("Insert command into script")
        self.insert_command_button.setToolTip("Insert the chosen submitted command at the editor cursor, without executing it.")
        self.insert_command_button.clicked.connect(self.insert_console_command)
        self.insert_command_button.setEnabled(False)
        console_controls.addWidget(self.insert_command_button)
        console_layout.addLayout(console_controls)
        self.console = WorkspaceConsole()
        self.console.banner = "IPython trials share the cell workspace. Run all rebuilds from the saved script."
        self.console._control.setReadOnly(True)
        self.console.executing.connect(self.console_started)
        console_layout.addWidget(self.console)
        self.console_dock = self.add_dock("IPython workspace", console_panel, QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)
        self.tabifyDockWidget(bottom_dock, self.console_dock)
        bottom_dock.raise_()
        self.resizeDocks([left_dock, right_dock], [280, 480], QtCore.Qt.Orientation.Horizontal)
        self.resizeDocks([bottom_dock], [160], QtCore.Qt.Orientation.Vertical)
        toolbar = self.addToolBar("Project")
        for title, callback in [("Open script", self.open_dialog), ("Save", self.save),
                                ("Run all", self.run_all), ("Cancel", self.cancel),
                                ("Registry folder", self.choose_registry), ("Import calibration", self.import_calibration),
                                ("List calibrations", self.list_calibrations)]:
            action = toolbar.addAction(title)
            action.triggered.connect(callback)
        self.cell_actions = {}
        for title, callback in [("Run cell", self.run_cell), ("Run to here", self.run_to_here),
                                ("Restart workspace", self.restart_workspace),
                                ("Convert to cell script", self.convert_script)]:
            action = toolbar.addAction(title)
            action.triggered.connect(callback)
            self.cell_actions[title] = action
        self.cell_shortcut = QtGui.QShortcut(QtGui.QKeySequence("Shift+Return"), self.editor)
        self.cell_shortcut.activated.connect(self.run_cell)
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
        self.link_plots()
        self.update_plot_controls()

    def clear_tabs(self):
        while self.tabs.count():
            self.close_tab(0)

    def edited(self):
        self.refresh_cells()
        if self.script:
            self.workspace_status.setText("Script edited — dependent results are outdated. Run all for reproducible results.")
            self.statusBar().showMessage("Script edited — save and Run all to update results. Displayed results may be outdated.")

    def open_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open reduction", "", "Python (*.py)")
        if path:
            self.open_script(Path(path))

    def open_script(self, path):
        if self.process is not None:
            self.log.appendPlainText("Wait for or cancel the current run before opening another project.")
            return
        self.shutdown_kernel()
        self._executed_source = ""
        self._workspace_cells = []
        self.console_commands.clear()
        self.insert_command_button.setEnabled(False)
        self.script = path.expanduser().resolve()
        self.editor.setPlainText(self.script.read_text(encoding="utf-8"))
        self.clear_tabs()
        self.exp = None
        self.manifest = None
        self._plot_count = 0
        self.channels.setRowCount(0)
        self.info.clear()
        for combo in self.selectors.values():
            combo.clear()
        self.update_plot_controls()
        self.refresh_cells()
        self.workspace_status.setText("Legacy batch script — convert a working copy for cells/console." if legacy_source(self.editor.toPlainText()) else "Cell script ready — Run cell or Run to here to begin.")
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
        self.editor.refresh_highlighting()
        if not self.script or self.process is not None:
            return
        if self.kernel is not None and self.kernel.busy:
            return
        self.save()
        if not legacy_source(self.editor.toPlainText()):
            # A fresh process excludes console-altered imports/module globals,
            # not just variables in the visible script namespace.
            self.shutdown_kernel()
            self.workspace_action("all")
            return
        self.shutdown_kernel()
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
        if self.kernel is not None:
            self.kernel.interrupt()
            self.workspace_status.setText("Interrupt requested. Partial workspace state may require Run to here or restart.")

    def load_result(self):
        try:
            manifest = json.loads((self.script.parent/"experiment.json").read_text(encoding="utf-8"))
            if manifest["script"]["path"] != self.script.name:
                raise ValueError("Manifest belongs to another script in this directory.")
            path = self.script.parent/manifest["outputs"]["state"]
            if file_digest(path) != manifest["outputs"]["state_sha256"]:
                raise ValueError("Cached experiment fingerprint mismatch. Run the reduction again.")
            self.show_experiment(read_state(path, manifest), manifest)
            current = self.editor.toPlainText().encode()
            import hashlib
            stale = hashlib.sha256(current).hexdigest() != manifest["script"]["sha256"]
            self.statusBar().showMessage("Script differs from displayed results — Run all to update." if stale else "Reduction loaded. Choose channels and click New plot tab; Refresh axes updates the active tab.")
        except Exception as exc:
            self.log.appendPlainText(f"Cannot display result: {exc}")

    def show_experiment(self, exp, manifest):
        selected = {key: combo.currentText() for key, combo in self.selectors.items()}
        self.exp = exp
        if manifest.get("run_id") != "interactive":
            self.manifest = manifest
        self.channels.setRowCount(len(self.exp.plot_columns))
        for i, name in enumerate(self.exp.plot_columns):
            c = self.exp[name]
            unit = "row" if name == "record_id" else c.unit
            for j, value in enumerate((name, unit, str((~c.valid).sum()))):
                item = QtWidgets.QTableWidgetItem(value)
                if name == "record_id":
                    item.setToolTip("Original zero-based row number. Select it on an axis and compare with time to inspect sampling-rate changes.")
                self.channels.setItem(i, j, item)
        for key, combo in self.selectors.items():
            combo.clear()
            if key == "right":
                combo.addItem("(none)")
            combo.addItems(self.exp.plot_columns)
        default_x = "time" if "time" in self.exp.channels else "record_id"
        default_left = "shear_stress" if "shear_stress" in self.exp.channels else next(n for n in self.exp.plot_columns if n != default_x)
        defaults = {"x": default_x, "left": default_left, "right": "(none)"}
        for key, combo in self.selectors.items():
            choice = selected[key] if combo.findText(selected[key]) >= 0 else defaults[key]
            combo.setCurrentText(choice)
        # Script plot requests remain in the manifest for compatibility.
        # Only user-created tabs are displayed, including after a rerun.
        self.tabs.blockSignals(True)
        try:
            for index in range(self.tabs.count()-1, -1, -1):
                panel = self.tabs.widget(index)
                missing = [n for n in (panel.spec["x"], panel.spec["left"], panel.spec.get("right")) if n and n not in self.exp.plot_columns]
                if missing:
                    self.log.appendPlainText(f"Closed {panel.spec['title']}: channels unavailable in the new result: {', '.join(missing)}")
                    self.close_tab(index)
                else:
                    panel.update_plot(self.exp, panel.spec)
        finally:
            self.tabs.blockSignals(False)
        self.link_plots()
        self.sync_axis_selectors()
        self.update_plot_controls()
        self.info.setPlainText(f"Records: {len(self.exp):,}\nOriginal IDs: {self.exp.record_ids[0]}–{self.exp.record_ids[-1]}\nRun: {manifest['run_id']}\nCalibrations: {len(manifest['calibrations'])}\nRegistry: {self.registry.root}")

    def current_cell_index(self):
        row = self.editor.textCursor().blockNumber()
        return next((i for i, cell in enumerate(cells(self.editor.toPlainText())) if cell.start <= row < max(cell.end, cell.start+1)), 0)

    def refresh_cells(self):
        if not hasattr(self, "cell_list"):
            return
        source = self.editor.toPlainText()
        parsed = cells(source)
        previous = cells(self._executed_source)
        changed = next((i for i in range(min(len(previous), len(parsed)))
                        if previous[i].fingerprint != parsed[i].fingerprint), min(len(previous), len(parsed)))
        self._updating_cells = True
        self.cell_list.clear()
        for i, cell in enumerate(parsed):
            old = self._workspace_cells[i]["status"] if i < len(self._workspace_cells) else "pending"
            status = old if i < changed else ("outdated" if old == "executed" else old)
            self.cell_list.addItem(f"{i+1}. {cell.title} [{status}]")
        self._updating_cells = False
        self.follow_cell()
        if hasattr(self, "cell_actions"):
            self.workspace_busy(self.kernel.busy if self.kernel is not None else False)

    def follow_cell(self):
        if hasattr(self, "cell_list") and not self._updating_cells:
            self._updating_cells = True
            self.cell_list.setCurrentRow(self.current_cell_index())
            self._updating_cells = False

    def select_cell(self, index):
        if self._updating_cells or index < 0:
            return
        parsed = cells(self.editor.toPlainText())
        if index < len(parsed):
            cursor = self.editor.textCursor()
            cursor.setPosition(self.editor.document().findBlockByNumber(parsed[index].start).position())
            self.editor.setTextCursor(cursor)
            self.editor.setFocus()

    def start_console(self):
        if not self.script or self.process is not None:
            return False
        if legacy_source(self.editor.toPlainText()):
            self.log.appendPlainText("Use Convert to cell script first. Your legacy script and Run all remain available.")
            return False
        if self.kernel is None:
            try:
                self.kernel = KernelController(self.console, self.script, self.registry.root, self)
                self.kernel.state.connect(self.workspace_received)
                self.kernel.output.connect(self.log.appendPlainText)
                self.kernel.busyChanged.connect(self.workspace_busy)
                self.kernel.readyChanged.connect(self.workspace_ready)
                self.workspace_busy(True)
                self.workspace_status.setText("Starting isolated IPython kernel in the current Python environment…")
            except Exception as exc:
                self.kernel = None
                import traceback
                self.log.appendPlainText("Cannot start IPython:\n"+traceback.format_exc())
                self._pending_workspace_action = None
                return False
        self.console_dock.show()
        self.console_dock.raise_()
        return True

    def workspace_ready(self, ready):
        self.console._control.setReadOnly(not ready)
        self.start_console_button.setEnabled(not ready)
        if ready and self._pending_workspace_action:
            action, source, index = self._pending_workspace_action
            self._pending_workspace_action = None
            self.kernel.action(action, source=source, index=index)
        elif ready:
            self.workspace_status.setText("IPython ready. Run cells to load your experiment.")

    def workspace_busy(self, busy):
        legacy = legacy_source(self.editor.toPlainText())
        for title, action in getattr(self, "cell_actions", {}).items():
            action.setEnabled(not busy and self.script is not None and
                              (legacy if title == "Convert to cell script" else not legacy))
        self.cell_shortcut.setEnabled(not busy and not legacy) if hasattr(self, "cell_shortcut") else None

    def console_started(self, source):
        self.workspace_status.setText("Console trial — add accepted commands to the script, then Run all to validate.")

    def workspace_action(self, action):
        self.editor.refresh_highlighting()
        if not self.script or self.process is not None:
            return
        if self.kernel is not None and self.kernel.busy:
            return
        source = self.editor.toPlainText()
        index = self.current_cell_index()
        if not self.start_console():
            return
        if not self.kernel.ready:
            self._pending_workspace_action = (action, source, index)
        else:
            self.kernel.action(action, source=source, index=index)

    def run_cell(self):
        self.workspace_action("cell")

    def run_to_here(self):
        self.workspace_action("through")

    def restart_workspace(self):
        if self.kernel is not None and self.kernel.busy:
            return
        self.shutdown_kernel()
        self._executed_source = ""
        self._workspace_cells = []
        self.clear_interactive_display()
        self.workspace_status.setText("Workspace restarted — variables and cell state cleared. Saved results remain on disk.")
        self.refresh_cells()
        self.start_console()

    def shutdown_kernel(self):
        self._pending_workspace_action = None
        if self.kernel is not None:
            self.kernel.close()
            self.kernel.deleteLater()
            self.kernel = None
        if hasattr(self, "console"):
            self.console._control.setReadOnly(True)
            self.start_console_button.setEnabled(True)

    def clear_interactive_display(self):
        self.clear_tabs()
        self.exp = None
        self.channels.setRowCount(0)
        self.info.clear()
        for combo in self.selectors.values():
            combo.clear()
        self.update_plot_controls()

    def workspace_received(self, state):
        self.editor.refresh_highlighting()
        self._executed_source = state["source"]
        self._workspace_cells = state["cells"]
        snap = state.get("snapshot")
        if snap:
            path = Path(snap["path"])
            try:
                exp = read_state(path, snap)
                self.show_experiment(exp, {"run_id": "interactive", "calibrations": self.manifest.get("calibrations", {}) if self.manifest else {}})
            except Exception as exc:
                self.log.appendPlainText(f"Cannot display workspace snapshot: {exc}")
            finally:
                path.unlink(missing_ok=True)
        elif state.get("empty") and not state.get("initial"):
            self.clear_interactive_display()
        if state.get("published"):
            self.load_result()
        if state.get("console_source"):
            command = state["console_source"]
            self.console_commands.addItem(command.replace("\n", " ")[:100], command)
            self.console_commands.setCurrentIndex(self.console_commands.count()-1)
            self.insert_command_button.setEnabled(True)
        if state.get("error"):
            text = "Failed/partial workspace — Run to here or restart. Last successful saved results remain on disk."
            self.log.appendPlainText(state["error"])
        elif state.get("dirty"):
            text = "Console trials are not in the script — insert accepted commands, then Run all to validate."
        elif state.get("published"):
            text = "Validated: fresh Run all published the saved script and results."
        elif state.get("halted"):
            text = "Inspection stopped by stop(). Pick contacts, edit the script, and Run to here."
        else:
            text = "Interactive cell results — Run all to publish a fresh reproducible reduction."
        if self.editor.toPlainText() != state["source"]:
            text = "Script changed during execution — displayed results are outdated; Run all again."
        self.workspace_status.setText(text)
        self.statusBar().showMessage(text)
        self.refresh_cells()
        # Advance to the next cell after successful sequential execution.
        index = state.get("completed", 0)
        if not state.get("error") and not state.get("console_source") and not state.get("published") and index < self.cell_list.count():
            self.select_cell(index)

    def insert_console_command(self):
        command = self.console_commands.currentData()
        if command:
            cursor = self.editor.textCursor()
            # Insert at a statement boundary and leave the original cell intact.
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.EndOfBlock)
            cursor.insertText("\n"+command.rstrip()+"\n")
            self.editor.setTextCursor(cursor)
            self.editor.setFocus()

    def convert_script(self):
        if not self.script or self.process is not None or (self.kernel is not None and self.kernel.busy):
            return
        try:
            converted = convert_legacy(self.editor.toPlainText())
            path = self.script.with_name(self.script.stem+"_cells.py")
            number = 2
            while path.exists():
                path = self.script.with_name(self.script.stem+f"_cells_{number}.py")
                number += 1
            with path.open("x", encoding="utf-8") as stream:
                stream.write(converted)
            self.open_script(path)
            self.log.appendPlainText(f"Created cell working copy: {path}\nThe original script was not overwritten. Relative raw paths are unchanged.")
        except Exception as exc:
            self.log.appendPlainText(f"Conversion refused: {exc}")


    def add_plot(self, spec):
        panel = PlotPanel(self.exp, spec)
        panel.picked.connect(self.log.appendPlainText)
        self.tabs.addTab(panel, spec["title"])
        self.tabs.setCurrentWidget(panel)
        self.update_plot_controls()
        self.link_plots()
        return panel

    def link_plots(self, *args):
        first = {}
        for i in range(self.tabs.count()):
            self.tabs.widget(i).primary.vb.setXLink(None)
        for i in range(self.tabs.count()):
            panel = self.tabs.widget(i)
            key = panel.spec["x"]
            parent = first.get(key) if self.link_action.isChecked() else None
            panel.primary.vb.setXLink(parent)
            if key not in first:
                first[key] = panel.primary.vb

    def selected_plot_spec(self, title):
        right = self.selectors["right"].currentText()
        return {"x": self.selectors["x"].currentText(), "left": self.selectors["left"].currentText(),
                "right": None if right == "(none)" else right, "title": title}

    def new_plot(self):
        if self.exp is None:
            return
        self._plot_count += 1
        self.add_plot(self.selected_plot_spec(f"Plot {self._plot_count}"))

    def refresh_plot(self):
        panel = self.tabs.currentWidget()
        if self.exp is None or panel is None:
            return
        panel.update_plot(self.exp, self.selected_plot_spec(panel.spec["title"]))
        self.link_plots()
        self.statusBar().showMessage(f"Refreshed {panel.spec['title']} in place. No new tab created.")

    def sync_axis_selectors(self, *args):
        panel = self.tabs.currentWidget()
        if panel is not None:
            for key in ("x", "left", "right"):
                self.selectors[key].setCurrentText(panel.spec.get(key) or "(none)")
        self.update_plot_controls()

    def update_plot_controls(self):
        self.new_plot_button.setEnabled(self.exp is not None)
        self.refresh_button.setEnabled(self.exp is not None and self.tabs.count() > 0)
        self.plot_area.setCurrentWidget(self.tabs if self.tabs.count() else self.no_plots)

    def channel_info(self):
        rows = self.channels.selectionModel().selectedRows()
        row = rows[0].row() if rows else self.channels.currentRow()
        if self.exp is not None and 0 <= row < len(self.exp.plot_columns):
            name = self.exp.plot_columns[row]
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
        self.shutdown_kernel()
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
