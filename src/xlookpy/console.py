"""Qt frontend for an isolated IPython process using this Conda interpreter."""
import os
os.environ["QT_API"] = "pyside6"
from pathlib import Path
import sys
import tempfile
from PySide6 import QtCore
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.manager import QtKernelManager
from .kernel_runtime import MIME


class WorkspaceConsole(RichJupyterWidget):
    def _handle_display_data(self, msg):
        if MIME not in msg.get("content", {}).get("data", {}):
            super()._handle_display_data(msg)


class KernelController(QtCore.QObject):
    state = QtCore.Signal(dict)
    output = QtCore.Signal(str)
    busyChanged = QtCore.Signal(bool)
    readyChanged = QtCore.Signal(bool)

    def __init__(self, console, script, registry, parent=None):
        super().__init__(parent)
        self.console = console
        self.script = Path(script)
        self.temp = tempfile.TemporaryDirectory(prefix="pyxlook-workspace-", dir="/tmp" if os.name != "nt" else None)
        transport = {"transport": "ipc", "ip": str(Path(self.temp.name)/"kernel")} if os.name != "nt" else {"ip": "127.0.0.1"}
        self.manager = QtKernelManager(kernel_name="python3", autorestart=False, **transport)
        # Never accidentally use a globally installed kernel from another Conda env.
        self.manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        self.client = None
        self.ready = False
        self.busy = False
        self._pending = set()
        self._closed = False
        self.monitor = QtCore.QTimer(self)
        self.monitor.setInterval(1000)
        self.monitor.timeout.connect(self.check_process)
        try:
            self.manager.start_kernel(cwd=str(self.script.parent))
            self.client = self.manager.client()
            # ThreadedKernelClient creates its IOLoop in start_channels. Accessing
            # a channel before that is an assertion failure in jupyter_client 8.
            self.client.start_channels()
            self.client.iopub_channel.message_received.connect(self.iopub)
            self.client.shell_channel.message_received.connect(self.reply)
            console.kernel_manager = self.manager
            console.kernel_client = self.client
            code = ("from xlookpy.kernel_runtime import KernelRuntime as __px_Runtime\n"
                    f"__px_runtime = __px_Runtime({str(self.script)!r}, {str(registry)!r}, {self.temp.name!r}, get_ipython())\n"
                    "__px_runtime.report(initial=True)")
            self.initial = self.send(code)
            self.monitor.start()
        except BaseException:
            self.close()
            raise

    def check_process(self):
        process = getattr(self.manager.provisioner, "process", None)
        if process is not None and process.poll() is not None and not self._closed:
            self.monitor.stop()
            self.ready = False
            self._pending.clear()
            self.set_busy(False)
            self.readyChanged.emit(False)
            self.output.emit("IPython process stopped. Restart workspace to create a fresh kernel; saved results remain on disk.")

    def send(self, code):
        self.set_busy(True)
        msg_id = self.client.execute(code, silent=False, store_history=False)
        self._pending.add(msg_id)
        return msg_id

    def action(self, action, *, source=None, index=None):
        if not self.ready or self.busy:
            return False
        self.send(f"__px_runtime.dispatch({action!r}, source={source!r}, index={index!r})")
        return True

    def set_busy(self, value):
        self.busy = value
        self.busyChanged.emit(value)

    def iopub(self, msg):
        if self._closed:
            return
        kind = msg.get("header", {}).get("msg_type")
        content = msg.get("content", {})
        if kind == "display_data" and MIME in content.get("data", {}):
            self.state.emit(content["data"][MIME])
        elif kind == "stream":
            self.output.emit(content.get("text", ""))
        elif kind == "error":
            self.output.emit("\n".join(content.get("traceback", [])))
        elif kind == "status":
            self.set_busy(content.get("execution_state") == "busy" or bool(self._pending))

    def reply(self, msg):
        parent = msg.get("parent_header", {}).get("msg_id")
        if parent not in self._pending:
            return
        self._pending.discard(parent)
        self.set_busy(bool(self._pending))
        if parent == self.initial:
            self.ready = msg.get("content", {}).get("status") == "ok"
            self.readyChanged.emit(self.ready)
            if not self.ready:
                self.output.emit("IPython workspace failed to initialize; restart it and check the error log.")

    def interrupt(self):
        if not self._closed:
            self.manager.interrupt_kernel()

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.monitor.stop()
        if self.client is not None:
            self.client.stop_channels()
        self.console.kernel_client = None
        self.console.kernel_manager = None
        try:
            self.manager.shutdown_kernel(now=True)
        finally:
            self.temp.cleanup()
