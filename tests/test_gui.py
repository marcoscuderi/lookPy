"""Desktop checks use offscreen Qt; no physical mouse/display is assumed."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path
from unittest.mock import Mock
import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")
from PySide6 import QtCore, QtTest, QtWidgets
from xlookpy import Experiment, Channel
from xlookpy.gui import PlotPanel, MainWindow
from xlookpy import gui
from test_engine import prepare_demo


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_panels_menu_restores_closed_panels_and_side_workspace_can_shrink(app, tmp_path):
    window = MainWindow(registry=tmp_path/"registry")
    window.show()
    try:
        docks = {dock.windowTitle(): dock for dock in window.findChildren(QtWidgets.QDockWidget)}
        actions = window.panels_menu.actions()
        assert {action.text() for action in actions} == set(docks)
        window.editor.setPlainText("# Current experiment")
        window.log.appendPlainText("Current execution log")
        for action in actions:
            dock = docks[action.text()]
            assert action.isChecked()
            dock.close()
            assert not action.isChecked()
            action.trigger()
            app.processEvents()
            assert action.isChecked()
            assert not dock.visibleRegion().isEmpty(), action.text()
        assert window.editor.toPlainText() == "# Current experiment"
        assert window.log.toPlainText() == "Current execution log"

        log = docks["Execution log and picked points"]
        console = window.console_dock
        for dock in (log, console):
            window.addDockWidget(QtCore.Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        window.tabifyDockWidget(log, console)
        console.raise_()
        window.console_commands.addItem("A long console command " * 5)
        app.processEvents()
        window.resizeDocks([console], [200], QtCore.Qt.Orientation.Horizontal)
        app.processEvents()
        assert console.width() <= 240
    finally:
        window.close()


def test_mac_floating_dock_uses_a_normal_window_and_can_redock(app, tmp_path, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(gui.sys, "platform", "darwin")
        window = MainWindow(registry=tmp_path/"registry")
    window.show()
    try:
        dock = next(dock for dock in window.findChildren(QtWidgets.QDockWidget)
                    if dock.windowTitle() == "Reduction script")
        dock.setFloating(True)
        QtTest.QTest.qWait(100)
        assert dock.isFloating() and dock.isVisible()
        assert dock.windowType() == QtCore.Qt.WindowType.Window
        dock.close()
        dock.toggleViewAction().trigger()
        assert dock.isVisible() and dock.isFloating()
        dock.setFloating(False)
        assert dock.isVisible() and not dock.isFloating()
        dock.setFloating(True)
        QtTest.QTest.qWait(100)
    finally:
        window.close()
    assert not dock.isVisible()


def test_running_cells_keeps_the_execution_log_selected(app, tmp_path, monkeypatch):
    script = tmp_path/"reduction.py"
    script.write_text("# %% First cell\nvalue = 1\n")
    kernel = Mock(ready=True, busy=False)
    monkeypatch.setattr(gui, "KernelController", Mock(return_value=kernel))
    window = MainWindow(script, tmp_path/"registry")
    window.show()
    app.processEvents()
    try:
        assert not window.log.visibleRegion().isEmpty()
        window.run_cell()
        app.processEvents()
        kernel.action.assert_called_once_with("cell", source=script.read_text(), index=0)
        assert not window.log.visibleRegion().isEmpty()
        assert window.console_dock.visibleRegion().isEmpty()

        window.start_console()
        app.processEvents()
        assert not window.console_dock.visibleRegion().isEmpty()
    finally:
        window.close()


def test_full_resolution_point_pick_both_axes_and_interval_copy(app):
    t = np.linspace(0, 10, 20001)
    exp = Experiment({"time": Channel(t, "s", {}),
                      "a": Channel(np.sin(t), "mm", {}),
                      "b": Channel(100+20*np.cos(t), "kN", {})})
    panel = PlotPanel(exp, {"x": "time", "left": "a", "right": "b"})
    panel.resize(1000, 600)
    panel.show()
    app.processEvents()
    for name, axis in [("a", panel.primary.vb), ("b", panel.secondary)]:
        i = 12345
        position = axis.mapViewToScene(QtCore.QPointF(t[i], exp[name].values[i]))
        picked = panel.nearest(position)
        assert picked[1:] == (i, name)
    panel.primary.vb.setXRange(2, 2.5, padding=0)
    app.processEvents()
    for axis, name in [(panel.primary.vb, "a"), (panel.secondary, "b")]:
        lo, hi = axis.viewRange()[1]
        vals = exp[name].values[(t >= 2) & (t <= 2.5)]
        assert lo < vals.min() and hi > vals.max()
        assert hi-lo < 1.2*(vals.max()-vals.min())
    panel.last_picks = [123, 456]
    panel.copy_interval()
    assert app.clipboard().text() == "exp.records(123, 456)"
    panel.close()


def test_desktop_runs_real_worker_and_loads_result(app, tmp_path):
    project, registry = prepare_demo(tmp_path)
    window = MainWindow(project/"reduction.py", registry.root)
    window.show()
    window.run_all()
    loop = QtCore.QEventLoop()
    window.process.finished.connect(loop.quit)
    timer = QtCore.QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(30000)
    loop.exec()
    assert window.process is None, window.log.toPlainText()
    assert window.exp is not None, window.log.toPlainText()
    assert window.tabs.count() == 0
    assert len(window.manifest["plots"]) == 3  # Existing script requests stay compatible.
    window.new_plot_button.click()
    assert window.tabs.count() == 1
    assert len(window.exp) > 20000
    assert (project/"experiment.json").is_file()
    window.editor.appendPlainText("\n# edit")
    assert "edited" in window.statusBar().currentMessage().lower()
    window.close()
