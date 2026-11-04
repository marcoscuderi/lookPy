"""Regression for threaded-client startup ordering without requiring sockets."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from types import SimpleNamespace
import pytest
pytest.importorskip("PySide6")
pytest.importorskip("qtconsole")
from PySide6 import QtWidgets
import xlookpy.console as module


class Signal:
    def connect(self, callback):
        self.callback = callback


class Client:
    def __init__(self, fail=False):
        self.started = False
        self.fail = fail
    def start_channels(self):
        if self.fail:
            raise RuntimeError("channel startup failed")
        self.started = True
    @property
    def iopub_channel(self):
        assert self.started, "Threaded channels require an initialized IOLoop"
        return SimpleNamespace(message_received=Signal())
    shell_channel = iopub_channel
    def execute(self, code, **kwargs):
        return "init-request"
    def stop_channels(self):
        self.started = False


@pytest.mark.parametrize("fail", [False, True])
def test_controller_initializes_channels_first_and_cleans_failed_starts(monkeypatch, tmp_path, fail):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    client = Client(fail)
    flags = {"closed": False}
    manager = SimpleNamespace(kernel_spec=SimpleNamespace(argv=[]), client=lambda: client,
                              start_kernel=lambda **kwargs: None,
                              shutdown_kernel=lambda **kwargs: flags.update(closed=True))
    monkeypatch.setattr(module, "QtKernelManager", lambda **kwargs: manager)
    console = SimpleNamespace(kernel_manager=None, kernel_client=None)
    if fail:
        with pytest.raises(RuntimeError, match="channel startup"):
            module.KernelController(console, tmp_path/"reduction.py", tmp_path/"registry")
    else:
        controller = module.KernelController(console, tmp_path/"reduction.py", tmp_path/"registry")
        assert manager.kernel_spec.argv[0] == sys.executable
        assert console.kernel_client is client and controller.busy
        controller.reply({"parent_header": {"msg_id": "init-request"}, "content": {"status": "ok"}})
        assert controller.ready and not controller.busy
        controller.close()
    assert flags["closed"] and console.kernel_client is None
    assert not client.started
