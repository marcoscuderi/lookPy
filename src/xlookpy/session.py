"""Fresh-session script execution and publication after a successful reduction."""
from copy import deepcopy
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import tempfile
import uuid
from .calibration import Calibration, Registry
from .io import load_file, write_dat, write_state
from .util import digest, file_digest


class Session:
    def __init__(self, project, *, registry=None, pinned=None):
        self.project = Path(project).resolve()
        self.registry = registry if isinstance(registry, Registry) else Registry(registry)
        self.pinned = pinned or {}
        self.calibrations = {}
        self.inputs = []
        self.plots = []
        self.experiment = None
        self.export_channels = None
        self.config = {}

    def load(self, path, *, units=None):
        if self.experiment is not None:
            raise ValueError("Version 0.1 supports one raw experiment per session.")
        path = Path(path).expanduser()
        if not path.is_absolute():
            path = self.project/path
        raw_hash = file_digest(path)
        exp = load_file(path, units=units, session=self)
        if self.pinned:
            old = self.pinned["inputs"]
            if len(old) != 1 or old[0]["sha256"] != raw_hash:
                raise ValueError("Replay raw-file fingerprint differs from the recorded experiment.")
        self.experiment = exp
        self.inputs.append({"path": os.path.relpath(path, self.project), "sha256": raw_hash,
                            "size_bytes": path.stat().st_size, "units": deepcopy(units or {})})
        return exp

    def calibration(self, identifier):
        if self.pinned:
            try:
                saved = self.pinned["calibrations"][identifier]
            except KeyError:
                raise ValueError(f"Replay has no snapshot for calibration {identifier!r}.") from None
            cal = Calibration(saved["record"])
            if cal.fingerprint != saved["sha256"]:
                raise ValueError("Calibration snapshot fingerprint mismatch.")
        else:
            cal = self.registry.get(identifier)
            # Detect external edits to a previously used central revision.
            previous = self.project/"experiment.json"
            if previous.is_file():
                prior = json.loads(previous.read_text(encoding="utf-8"))
                saved = prior.get("calibrations", {}).get(identifier)
                if saved and saved["sha256"] != cal.fingerprint:
                    raise ValueError(f"Central calibration {identifier} changed under the same ID. Import it as a new revision, or replay the saved manifest.")
        return cal

    def _remember(self, cal):
        existing = self.calibrations.get(cal.id)
        if existing and existing["sha256"] != cal.fingerprint:
            raise ValueError("Two definitions of the same calibration ID were used in one run.")
        self.calibrations[cal.id] = {"record": cal.record, "sha256": cal.fingerprint}

    def export(self, exp, *, channels=None):
        """Select the final experiment/channels. Files publish only when the script succeeds."""
        if exp._session is not self:
            raise ValueError("Export must belong to this session.")
        self.experiment = exp
        self.export_channels = list(channels) if channels is not None else None


def run(script, *, registry=None, replay_manifest=None):
    """Execute trusted Python with def reduce(session), from fresh raw state.

    Only this runner's outputs are transactional. Arbitrary user Python file
    writes are outside the transaction; scripts should export through Session.
    """
    from . import __version__
    script = Path(script).expanduser().resolve()
    text = script.read_bytes().decode("utf-8")
    script_sha = file_digest(script)
    pinned = None
    if replay_manifest:
        pinned = json.loads(Path(replay_manifest).read_text(encoding="utf-8"))
        if pinned["script"]["sha256"] != script_sha:
            raise ValueError("Replay script differs from the recorded script. Restore the recorded source or run a new reduction.")
        if pinned["software"]["xlookpy"] != __version__:
            raise ValueError("Replay needs the recorded xlookpy version.")
    session = Session(script.parent, registry=registry, pinned=pinned)
    namespace = {"__name__": "__xlook_reduction__", "__file__": str(script)}
    exec(compile(text, str(script), "exec"), namespace)
    reducer = namespace.get("reduce")
    if not callable(reducer):
        raise ValueError("The script must define reduce(session). See examples/demo/reduction.py.")
    reducer(session)
    exp = session.experiment
    if exp is None:
        raise ValueError("The reduction did not load an experiment.")
    for spec in session.plots:
        for name in (spec["x"], spec["left"], spec["right"]):
            if name is not None:
                exp[name]
    # Detect raw/script changes during the execution before publishing anything.
    if file_digest(script) != script_sha or any(file_digest(script.parent / i["path"]) != i["sha256"] for i in session.inputs):
        raise ValueError("Script or raw data changed while reducing. Rerun from stable files.")
    results = script.parent/"results"
    results.mkdir(exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")+"_"+uuid.uuid4().hex[:8]
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=results))
    destination = results/run_id
    manifest_tmp = None
    published = False
    try:
        selected = write_dat(exp, staging/"reduced.dat", session.export_channels)
        write_state(exp, staging/"state.npz")
        versions = {name: importlib.metadata.version(name) for name in ("numpy", "pint", "nptdms")}
        manifest = {"schema_version": 1, "status": "success", "run_id": run_id,
                    "created_utc": datetime.now(timezone.utc).isoformat(),
                    "software": {"xlookpy": __version__, "python": platform.python_version(), **versions},
                    "script": {"path": script.name, "sha256": script_sha, "source": text},
                    "inputs": session.inputs, "experiment": exp.metadata,
                    "config": session.config, "calibrations": session.calibrations,
                    "operations": exp.history, "channels": exp.summary(), "plots": session.plots,
                    "outputs": {"dat": f"results/{run_id}/reduced.dat", "state": f"results/{run_id}/state.npz",
                                "channels": selected, "dat_sha256": file_digest(staging/"reduced.dat"),
                                "state_sha256": file_digest(staging/"state.npz")},
                    "replay_of": pinned.get("run_id") if pinned else None}
        encoded = json.dumps(manifest, indent=2, allow_nan=False)
        (staging/"manifest.json").write_text(encoded, encoding="utf-8")
        fd, name = tempfile.mkstemp(prefix=".experiment-", suffix=".json", dir=script.parent)
        manifest_tmp = Path(name)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        staging.rename(destination)
        os.replace(manifest_tmp, script.parent/"experiment.json")
        published = True
        print(f"SUCCESS: {len(exp):,} records, {len(exp.channels)} channels. Manifest: {script.parent/'experiment.json'}")
        return manifest
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if manifest_tmp is not None:
            manifest_tmp.unlink(missing_ok=True)
        if not published and destination.exists():
            shutil.rmtree(destination)
