"""Cell parsing and deterministic rebuild rules, independent of Qt/IPython."""
import ast
from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
import tokenize
from .session import Session, publish
from .workflow import vocabulary, using_session, StopReduction
from .util import file_digest


@dataclass(frozen=True)
class Cell:
    start: int  # Zero-based source line, including the marker.
    end: int
    title: str
    source: str

    @property
    def fingerprint(self):
        return hashlib.sha256(self.source.encode()).hexdigest()


def cells(source):
    """Only top-level # %% / #%% comments delimit cells, not text in strings."""
    import re
    lines = source.splitlines(keepends=True)
    markers = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT and tok.start[1] == 0 and re.match(r"#\s*%%(?:\s|$)", tok.string):
                markers.append((tok.start[0]-1, re.sub(r"^#\s*%%\s*", "", tok.string) or "Untitled"))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass  # Preserve recognized markers while the operator is typing.
    starts = list(markers)
    if not starts or starts[0][0] > 0:
        starts.insert(0, (0, "Setup"))
    return [Cell(a, starts[j+1][0] if j+1 < len(starts) else len(lines), title,
                 "".join(lines[a:starts[j+1][0] if j+1 < len(starts) else len(lines)]))
            for j, (a, title) in enumerate(starts)]


def legacy_source(source):
    try:
        return any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "reduce" for n in ast.parse(source).body)
    except SyntaxError:
        return False


def convert_legacy(source):
    """Unwrap a simple reduce(session), preserving comments and section markers.

    The caller writes a NEW file. Nested functions remain untouched. Inspection
    returns become stop(), so the existing inspection mode still terminates.
    """
    tree = ast.parse(source)
    functions = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "reduce"]
    if len(functions) != 1:
        raise ValueError("Conversion requires exactly one top-level def reduce(session).")
    fn = functions[0]
    if fn.decorator_list or len(fn.args.args) != 1 or fn.args.args[0].arg != "session" or fn.args.defaults or fn.args.vararg or fn.args.kwarg or fn.args.kwonlyargs or fn.args.posonlyargs:
        raise ValueError("Convert only an undecorated def reduce(session) with no additional arguments.")
    lines = source.splitlines(keepends=True)
    if any(not isinstance(n, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign, ast.Expr, ast.FunctionDef, ast.ClassDef)) for n in tree.body if n is not fn):
        raise ValueError("Top-level control flow requires manual conversion; original script was not changed.")
    # Require an ordinary multiline body rather than a one-line function.
    if fn.body[0].lineno == fn.lineno:
        raise ValueError("Use a multiline reduce(session) before conversion.")
    patches = []
    def replace(node, value):
        if node.lineno != node.end_lineno:
            raise ValueError("This construct needs manual conversion; original script was not changed.")
        patches.append((node.lineno-1, node.col_offset, node.end_col_offset, value))
    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            if node is fn:
                for child in node.body:
                    self.visit(child)
        def visit_AsyncFunctionDef(self, node):
            pass
        def visit_ClassDef(self, node):
            pass
        def visit_Return(self, node):
            if node.value is not None:
                raise ValueError("A return value requires manual conversion; original script was not changed.")
            replace(node, "stop()")
        def visit_Attribute(self, node):
            if isinstance(node.value, ast.Name) and node.value.id == "session":
                name = {"load": "load", "export": "save", "calibration": "calibration"}.get(node.attr)
                if name:
                    replace(node, name)
    Visitor().visit(fn)
    for row, a, b, value in sorted(patches, reverse=True):
        # AST column offsets count UTF-8 bytes, including non-ASCII source.
        raw = lines[row].encode()
        lines[row] = (raw[:a]+value.encode()+raw[b:]).decode()
    # Include comments immediately within the body, before its first AST node.
    first = fn.lineno
    end = fn.end_lineno
    indent = fn.body[0].col_offset
    for row in range(first, end):
        if lines[row].strip():
            if not lines[row].startswith(" "*indent):
                raise ValueError("Unusual body indentation requires manual conversion.")
            lines[row] = lines[row][indent:]
    lines[fn.lineno-1] = "# Cell workspace: formerly reduce(session).\n"
    result = "".join(lines)
    compile(result, "<converted reduction>", "exec")
    return result


class Workspace:
    """One interactive namespace. Reruns rebuild a script prefix from raw state.

    New sequential cells use the live namespace. Reexecuting a completed cell,
    editing an earlier cell, or running after console trials rebuilds the prefix.
    No snapshots of arbitrary mutable Python objects are presented as rollback.
    """
    def __init__(self, script, registry=None, namespace=None):
        self.script = Path(script).resolve()
        self.registry = registry
        self.namespace = {} if namespace is None else namespace
        self.protected = set(self.namespace)
        self.source = ""
        self.cell_list = []
        self.statuses = []
        self.completed = 0
        self.dirty = False
        self.failed = False
        self.halted = False
        self.session = None
        self.published = None
        self.update(self.script.read_text(encoding="utf-8"))
        self.reset()

    def update(self, source):
        new = cells(source)
        old = self.cell_list
        first = next((i for i in range(min(len(new), len(old))) if new[i].fingerprint != old[i].fingerprint), min(len(new), len(old)))
        self.statuses = [self.statuses[i] if i < first else ("outdated" if i < self.completed else "pending") for i in range(len(new))]
        self.completed = min(self.completed, first)
        self.source, self.cell_list = source, new
        return self.statuses

    def reset(self):
        for name in list(self.namespace):
            if name not in self.protected and not name.startswith("__px_"):
                del self.namespace[name]
        self.session = Session(self.script.parent, registry=self.registry)
        self.namespace.update({"__name__": "__xlook_workspace__", "__file__": str(self.script), **vocabulary(self.session)})
        self.statuses = ["pending"]*len(self.cell_list)
        self.completed = 0
        self.dirty = self.failed = self.halted = False
        self.published = None

    def execute(self, source, index, *, through=False):
        if legacy_source(source):
            raise ValueError("Convert this def reduce(session) script to a new cell file first; Run all remains compatible.")
        self.update(source)
        if not 0 <= index < len(self.cell_list):
            raise ValueError("Choose an existing cell.")
        if index > self.completed and not through and not self.dirty and not self.failed:
            raise ValueError("Earlier cells have not run. Choose Run to here to rebuild through this cell.")
        rebuilding = through or index < self.completed or self.dirty or self.failed
        # An earlier edit invalidates previous live state even at the frontier.
        rebuilding |= any(s == "outdated" for s in self.statuses[:index+1])
        if rebuilding:
            self.reset()
            targets = range(index+1)
        else:
            targets = [index]
        self.published = None
        for i in targets:
            if self.halted:
                break
            self._one(i)
        return self.state()

    def _one(self, index):
        if self.halted:
            raise ValueError("Execution stopped for inspection. Edit contacts and use Run to here.")
        cell = self.cell_list[index]
        try:
            with using_session(self.session):
                exec(compile("\n"*cell.start+cell.source, str(self.script), "exec"), self.namespace)
        except StopReduction:
            self.halted = True
        except BaseException:
            self.statuses[index] = "failed"
            self.failed = True
            raise
        self.statuses[index] = "executed"
        self.completed = index+1

    def run_all(self, source):
        if source != self.script.read_text(encoding="utf-8"):
            raise ValueError("Save the script before Run all.")
        self.update(source)
        self.reset()
        script_sha = file_digest(self.script)
        if legacy_source(source):
            # GUI normally keeps legacy execution on the existing worker path.
            with using_session(self.session):
                exec(compile(source, str(self.script), "exec"), self.namespace)
                self.namespace["reduce"](self.session)
        else:
            for i in range(len(self.cell_list)):
                self._one(i)
                if self.halted:
                    break
        self.published = publish(self.session, self.script, source, script_sha)
        return self.published

    def state(self):
        return {"cells": [{"title": c.title, "start": c.start, "end": c.end, "status": status}
                          for c, status in zip(self.cell_list, self.statuses)],
                "dirty": self.dirty, "failed": self.failed, "halted": self.halted,
                "completed": self.completed, "published": self.published is not None}
