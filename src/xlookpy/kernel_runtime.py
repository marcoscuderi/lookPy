"""Kernel-side workspace bridge. No Qt imports and no access to GUI objects."""
from pathlib import Path
import traceback
import uuid
from .workspace import Workspace
from .workflow import _ACTIVE
from .io import write_state

MIME = "application/vnd.pyxlook.workspace+json"


class KernelRuntime:
    def __init__(self, script, registry, snapshot_dir, shell):
        self.shell = shell
        self.workspace = Workspace(script, registry, namespace=shell.user_ns)
        self.directory = Path(snapshot_dir)
        self._signature = None
        self._last_exp = None
        self._console_token = None
        self._console_source = None
        shell.events.register("pre_run_cell", self.before_console)
        shell.events.register("post_run_cell", self.after_console)

    def before_console(self, info):
        if info.raw_cell.lstrip().startswith("__px_"):
            return
        self._console_source = info.raw_cell
        self.workspace.dirty = True
        self.workspace.published = None
        self.workspace.session._allow_replace = True
        self._console_token = _ACTIVE.set(self.workspace.session)

    def after_console(self, result):
        if self._console_source is None:
            return
        source, self._console_source = self._console_source, None
        if self._console_token is not None:
            _ACTIVE.reset(self._console_token)
            self._console_token = None
        self.workspace.session._allow_replace = False
        error = result.error_before_exec or result.error_in_exec
        if error:
            self.workspace.failed = True
        self.report(error=str(error) if error else None, console_source=source)

    def dispatch(self, action, source=None, index=None):
        error = None
        try:
            if action == "cell":
                self.workspace.execute(source, index)
            elif action == "through":
                self.workspace.execute(source, index, through=True)
            elif action == "all":
                self.workspace.run_all(source)
            elif action == "reset":
                self.workspace.reset()
            else:
                raise ValueError("Unknown workspace action.")
        except BaseException as exc:
            error = f"{type(exc).__name__}: {exc}"
            # A failed arbitrary cell may have changed live objects; never label
            # it as the saved last successful experiment or publish it.
            self.workspace.failed = True
            traceback.print_exc()
        self.report(error=error)

    def report(self, *, error=None, console_source=None, initial=False):
        state = self.workspace.state()
        state.update({"error": error, "console_source": console_source,
                      "source": self.workspace.source, "snapshot": None, "initial": initial})
        exp = self.workspace.session.experiment
        if exp is not None:
            # Immutable Channel instances make identity a cheap change detector.
            signature = (id(exp), tuple((n, id(exp[n])) for n in exp.channels))
            if signature != self._signature:
                name = uuid.uuid4().hex+".npz"
                path = self.directory/name
                write_state(exp, path)
                state["snapshot"] = {"path": str(path), "channels": exp.summary(),
                                     "operations": exp.history, "experiment": exp.metadata}
                self._signature = signature
                self._last_exp = exp
        else:
            self._signature = None
            self._last_exp = None
            state["empty"] = True
        self.shell.display_pub.publish(data={MIME: state})
