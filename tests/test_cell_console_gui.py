"""Real isolated IPython process, shared console namespace and GUI lifecycle."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
import pytest
pytest.importorskip("PySide6")
pytest.importorskip("qtconsole")
from PySide6 import QtCore, QtWidgets
from xlookpy.gui import MainWindow
from test_workspace import script


@pytest.fixture(autouse=True)
def kernel_sockets(tmp_path):
    import socket
    import tempfile
    try:
        with tempfile.TemporaryDirectory(prefix="px-probe-", dir="/tmp") as directory:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                sock.bind(directory+"/probe.sock")
            finally:
                sock.close()
    except OSError as exc:
        if os.environ.get("GITHUB_ACTIONS"):
            pytest.fail(f"CI must exercise the real kernel; sockets unavailable: {exc}")
        pytest.skip(f"Execution sandbox prohibits local sockets; real-kernel test runs in CI: {exc}")


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def wait_until(app, predicate, seconds=30):
    if predicate():
        return
    loop = QtCore.QEventLoop()
    check = QtCore.QTimer()
    check.setInterval(25)
    check.timeout.connect(lambda: loop.quit() if predicate() else None)
    timeout = QtCore.QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(loop.quit)
    check.start()
    timeout.start(int(seconds*1000))
    loop.exec()
    check.stop()
    assert predicate(), "Timed out waiting for IPython/GUI state"


def test_real_kernel_cells_console_invalidation_and_fresh_publication(app, tmp_path):
    path, source = script(tmp_path)
    window = MainWindow(path, tmp_path/"registry")
    window.show()
    try:
        window.select_cell(2)
        window.run_to_here()
        wait_until(app, lambda: window.exp is not None and "v" in window.exp.channels)
        wait_until(app, lambda: not window.kernel.busy)
        assert window.kernel.ready
        np.testing.assert_array_equal(window.exp["slip"].values, [0, 0, 1, 2, 3])
        assert not (tmp_path/"experiment.json").exists()
        assert window.tabs.count() == 0
        window.new_plot()
        assert window.tabs.count() == 1

        # A real QtConsole command operates on the same experiment as the cells.
        window.console.execute('exp.zero_at("d", record=2, output="slip")')
        wait_until(app, lambda: window.exp is not None and "v" not in window.exp.channels)
        wait_until(app, lambda: not window.kernel.busy)
        np.testing.assert_array_equal(window.exp["slip"].values, [0, 0, 0, 1, 2])
        assert "Console trials" in window.workspace_status.text()
        assert window.console_commands.count() >= 1
        assert window.insert_command_button.isEnabled()
        window.select_cell(1)
        before = window.editor.toPlainText()
        window.insert_console_command()
        assert 'record=2, output="slip"' in window.editor.toPlainText()
        assert window.editor.toPlainText() != before
        assert path.read_text() == source  # Insertion doesn't silently save/execute.
        window.editor.setPlainText(source)  # Reject this trial for the next fresh run.

        window.run_all()
        wait_until(app, lambda: (tmp_path/"experiment.json").exists())
        wait_until(app, lambda: "Validated:" in window.workspace_status.text())
        wait_until(app, lambda: not window.kernel.busy)
        np.testing.assert_array_equal(window.exp["slip"].values, [0, 0, 1, 2, 3])
        assert "v" in window.exp.channels
        saved = (tmp_path/"experiment.json").read_bytes()

        # A failed console command never replaces the last published manifest.
        window.console.execute('raise RuntimeError("console failure")')
        wait_until(app, lambda: "Failed/partial" in window.workspace_status.text())
        wait_until(app, lambda: not window.kernel.busy)
        assert (tmp_path/"experiment.json").read_bytes() == saved
        window.restart_workspace()
        wait_until(app, lambda: window.kernel is not None and window.kernel.ready and not window.kernel.busy)
        assert window.exp is None
        assert (tmp_path/"experiment.json").read_bytes() == saved
    finally:
        window.close()
        assert window.kernel is None


def test_legacy_conversion_creates_new_real_working_script_without_overwrite(app, tmp_path):
    path, source = script(tmp_path)
    legacy = 'RAW_FILE = "raw.csv"\ndef reduce(session):\n    # %% Load\n    exp = session.load(RAW_FILE, units={"time":"s", "d":"mm"})\n    session.export(exp)\n'
    path.write_text(legacy)
    window = MainWindow(path, tmp_path/"registry")
    try:
        window.convert_script()
        assert window.script.name == "reduction_cells.py"
        assert path.read_text() == legacy
        assert 'def reduce' not in window.editor.toPlainText()
        assert 'load(RAW_FILE' in window.editor.toPlainText()
        window.run_all()
        wait_until(app, lambda: window.manifest is not None)
        assert len(window.exp) == 5
        assert window.manifest["script"]["path"] == "reduction_cells.py"
    finally:
        window.close()


def test_kernel_interrupt_does_not_publish_a_hanging_cell(app, tmp_path):
    path, source = script(tmp_path)
    path.write_text(source+'\n# %% Hanging\nwhile True:\n    pass\n')
    window = MainWindow(path, tmp_path/"registry")
    try:
        window.start_console()
        wait_until(app, lambda: window.kernel.ready and not window.kernel.busy)
        window.select_cell(4)
        window.run_to_here()
        QtCore.QTimer.singleShot(500, window.cancel)
        wait_until(app, lambda: "Failed/partial" in window.workspace_status.text())
        wait_until(app, lambda: not window.kernel.busy)
        assert not (tmp_path/"experiment.json").exists()
    finally:
        window.close()
