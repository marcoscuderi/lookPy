"""Operator plot lifecycle and original-row plotting, using offscreen Qt."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from types import SimpleNamespace
import numpy as np
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pyqtgraph")
from PySide6 import QtCore, QtWidgets
from PySide6.QtTest import QTest
from xlookpy import Experiment, Channel, run
from xlookpy.gui import MainWindow, PlotPanel
from xlookpy.io import write_dat
from test_engine import prepare_demo


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def choose(window, x, left, right=None):
    for key, name in (("x", x), ("left", left), ("right", right or "(none)")):
        assert window.selectors[key].findText(name) >= 0
        window.selectors[key].setCurrentText(name)


def loaded_window(tmp_path):
    project, registry = prepare_demo(tmp_path)
    run(project/"reduction.py", registry=registry)
    return MainWindow(project/"reduction.py", registry.root), project, registry


def test_row_coordinate_retains_original_ids_and_is_exported_only_once(tmp_path):
    exp = Experiment({"time": Channel(np.arange(10)*.1, "s", {})})
    original = exp["time"].values.copy()
    part = exp.slice(exp.records(4, 8))
    assert part.plot_columns == ("record_id", "time")
    assert part.channels == ("time",)
    np.testing.assert_array_equal(part["record_id"].values, [4, 5, 6, 7, 8])
    with pytest.raises(ValueError):
        part["record_id"].values[0] = 99
    out = tmp_path/"data.dat"
    write_dat(part, out, ["record_id", "time"])
    assert out.read_text().splitlines()[0] == "record_id\ttime"
    values = np.loadtxt(out, skiprows=2)
    np.testing.assert_array_equal(values[:, 0], part.record_ids)
    np.testing.assert_array_equal(exp["time"].values, original)


def test_no_automatic_tabs_and_explicit_creation_vs_in_place_refresh(app, tmp_path):
    window, project, registry = loaded_window(tmp_path)
    window.show()
    app.processEvents()
    assert window.tabs.count() == 0
    assert window.plot_area.currentWidget() is window.no_plots
    assert window.channels.item(0, 0).text() == "record_id"
    assert window.new_plot_button.isEnabled()
    assert not window.refresh_button.isEnabled()
    choose(window, "time", "shear_stress", "normal_stress")
    assert window.tabs.count() == 0  # Dropdown changes alone do not create plots.
    window.new_plot_button.click()
    panel = window.tabs.currentWidget()
    assert window.tabs.count() == 1
    assert window.plot_area.currentWidget() is window.tabs
    panel.primary.vb.setXRange(20, 22, padding=0)
    app.processEvents()
    choose(window, "time", "friction", "slip_velocity")
    assert panel.spec["left"] == "shear_stress"  # Requires explicit refresh.
    window.refresh_button.click()
    app.processEvents()
    assert window.tabs.count() == 1 and window.tabs.currentWidget() is panel
    assert panel.spec["left"] == "friction" and panel.spec["right"] == "slip_velocity"
    np.testing.assert_allclose(panel.primary.vb.viewRange()[0], [20, 22], atol=1e-10)
    assert len(panel.plot_items) == 2
    choose(window, "record_id", "time")
    window.refresh_button.click()
    app.processEvents()
    assert window.tabs.currentWidget() is panel and window.tabs.count() == 1
    assert panel.spec["x"] == "record_id" and panel.spec["right"] is None
    assert len(panel.plot_items) == 1
    assert panel.primary.vb.viewRange()[0][1] > len(window.exp)-1
    window.new_plot_button.click()
    assert window.tabs.count() == 2
    window.close_tab(1)
    window.close_tab(0)
    assert window.plot_area.currentWidget() is window.no_plots
    assert not window.refresh_button.isEnabled()
    window.refresh_plot()
    assert window.tabs.count() == 0
    window.close()


def test_row_time_plot_shows_rate_change_and_picks_original_row_after_slice(app):
    t = np.r_[np.arange(20.), 20+np.arange(30)*.1]
    base = Experiment({"time": Channel(t, "s", {})})
    exp = base.slice(base.records(10, 40))
    panel = PlotPanel(exp, {"x": "record_id", "left": "time", "right": None})
    panel.resize(900, 550)
    panel.show()
    app.processEvents()
    _axis, _name, x, y = panel.curves[0]
    np.testing.assert_array_equal(x, np.arange(10, 41))
    assert np.diff(y)[0] == pytest.approx(1.)
    assert np.diff(y)[-1] == pytest.approx(.1)
    i = 15
    point = panel.primary.vb.mapViewToScene(QtCore.QPointF(float(x[i]), float(y[i])))
    panel.click(SimpleNamespace(button=lambda: QtCore.Qt.MouseButton.LeftButton, scenePos=lambda: point))
    assert app.clipboard().text() == "25"
    assert panel.last_picks == [25] and len(panel.pick_markers) == 1
    panel.update_plot(exp, {"x": "time", "left": "record_id", "right": None})
    assert panel.last_picks == [] and panel.pick_markers == []
    panel.close()


def test_matching_x_links_relink_safely_when_one_plot_changes_x(app, tmp_path):
    window, project, registry = loaded_window(tmp_path)
    window.show()
    choose(window, "time", "shear_stress")
    window.new_plot()
    first = window.tabs.currentWidget()
    choose(window, "time", "friction")
    window.new_plot()
    second = window.tabs.currentWidget()
    app.processEvents()
    second.primary.vb.setXRange(30, 32, padding=0)
    app.processEvents()
    np.testing.assert_allclose(first.primary.vb.viewRange()[0], [30, 32], atol=1e-8)
    choose(window, "record_id", "time")
    window.refresh_plot()
    app.processEvents()
    np.testing.assert_allclose(first.primary.vb.viewRange()[0], [30, 32], atol=1e-8)
    first.primary.vb.setXRange(40, 42, padding=0)
    app.processEvents()
    assert second.primary.vb.viewRange()[0][1] > len(window.exp)-1
    window.tabs.setCurrentIndex(0)
    assert window.selectors["x"].currentText() == "time"
    window.tabs.setCurrentIndex(1)
    assert window.selectors["x"].currentText() == "record_id"
    window.close()


def test_reload_refreshes_only_user_tabs_and_keeps_panel_zoom(app, tmp_path):
    window, project, registry = loaded_window(tmp_path)
    choose(window, "time", "friction", "shear_stress")
    window.new_plot()
    panel = window.tabs.currentWidget()
    panel.primary.vb.setXRange(50, 52, padding=0)
    previous_run = window.manifest["run_id"]
    run(project/"reduction.py", registry=registry)
    window.load_result()
    app.processEvents()
    assert window.manifest["run_id"] != previous_run
    assert window.tabs.count() == 1 and window.tabs.currentWidget() is panel
    assert panel.exp is window.exp
    np.testing.assert_allclose(panel.primary.vb.viewRange()[0], [50, 52], atol=1e-8)
    window.close()


def test_refresh_new_plot_controls_disabled_before_reduction(app):
    window = MainWindow()
    assert not window.new_plot_button.isEnabled()
    assert not window.refresh_button.isEnabled()
    window.new_plot()
    window.refresh_plot()
    assert window.tabs.count() == 0
    window.close()


def test_interactive_fit_uses_original_record_interval_and_selected_axis(app):
    x = np.array([-2., 0., 4., 2., 3., 1., 6.])
    right = 2*x**2 + 3*x + 4
    right[[0, 3, 6]] = [500., np.nan, 200.]
    exp = Experiment({
        "time": Channel(x, "s", {}),
        "force": Channel(3*x + 2, "kN", {}),
        "slip": Channel(right, "um", {}),
    }, record_ids=np.arange(20, 27))
    window = MainWindow()
    window.exp = exp
    panel = window.add_plot({"x": "time", "left": "force", "right": "slip", "title": "Fit test"})
    window.show()
    app.processEvents()

    def click(axis, y, index):
        point = axis.mapViewToScene(QtCore.QPointF(x[index], y[index]))
        QTest.mouseClick(panel.plot.viewport(), QtCore.Qt.MouseButton.LeftButton,
                         pos=panel.plot.mapFromScene(point))

    panel.fit_degree.setCurrentIndex(panel.fit_degree.findData(2))
    panel.fit_button.click()
    click(panel.secondary, right, 5)
    click(panel.secondary, right, 1)
    axis, overlay = panel.fit_overlay
    assert axis is panel.secondary
    xx, yy = overlay.getData()
    np.testing.assert_allclose(xx[[0, -1]], [0., 4.])
    np.testing.assert_allclose(yy, 2*xx**2 + 3*xx + 4, atol=1e-10)
    assert "records 21–25" in window.log.toPlainText()
    assert "4 samples, R² = 1" in window.log.toPlainText()
    assert "a0 = 4, a1 = 3, a2 = 2" in window.log.toPlainText()
    assert not panel.fit_button.isChecked()
    assert panel.last_picks == []

    panel.fit_degree.setCurrentIndex(panel.fit_degree.findData(1))
    panel.copy_detrend_button.click()
    command = app.clipboard().text()
    assert command == ("exp.detrend('time', 'slip', records=exp.records(21, 25), "
                       "degree=2, output='slip_detrended')")
    trial = Experiment({name: exp[name] for name in exp.channels}, record_ids=exp.record_ids)
    exec(command, {"exp": trial})
    np.testing.assert_allclose(trial["slip_detrended"].values,
                               [np.nan, 0, 0, np.nan, 0, 0, np.nan], atol=1e-10)
    panel.fit_button.click()
    click(panel.primary.vb, exp["force"].values, 1)
    click(panel.primary.vb, exp["force"].values, 4)
    assert panel.fit_overlay[0] is panel.primary.vb
    assert "Slope = 3 kN/s, intercept = 2 kN" in window.log.toPlainText()
    assert exp.channels == ("time", "force", "slip")
    assert exp.history == []

    panel.fit_button.click()
    click(panel.primary.vb, exp["force"].values, 1)
    click(panel.primary.vb, exp["force"].values, 1)
    assert "Fit refused for records 21–21" in window.log.toPlainText()
    assert panel.fit_overlay is not None
    panel.update_plot(exp, {"x": "record_id", "left": "force"})
    assert panel.fit_overlay is None
    assert panel.fit_start is None
    assert not panel.clear_fit_button.isEnabled()
    assert not panel.copy_detrend_button.isEnabled()

    zero = np.zeros_like(x)
    flat = Experiment({"time": exp["time"], "force": Channel(zero, "kN", {})})
    panel.update_plot(flat, {"x": "time", "left": "force"})
    app.processEvents()
    panel.fit_button.click()
    click(panel.primary.vb, zero, 1)
    click(panel.primary.vb, zero, 4)
    assert "Slope = 0 kN/s, intercept = 0 kN" in window.log.toPlainText()
    panel.clear_fit_button.click()
    assert panel.fit_overlay is None
    window.close()
