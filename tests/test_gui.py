"""Desktop checks use offscreen Qt; no physical mouse/display is assumed."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path
import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")
from PySide6 import QtCore, QtWidgets
from xlookpy import Experiment, Channel
from xlookpy.gui import PlotPanel, MainWindow
from test_engine import prepare_demo


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


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
    assert window.tabs.count() == 3
    assert len(window.exp) > 20000
    assert (project/"experiment.json").is_file()
    window.editor.appendPlainText("\n# edit")
    assert "edited" in window.statusBar().currentMessage().lower()
    window.close()
